# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""prodockit.headings: gives every heading an id and a hierarchical section
number, recorded in a shared :class:`~prodockit.util.IdRegistry` that other
prodockit extensions (currently :mod:`prodockit.refs`) look entries up in.
"""

from __future__ import annotations

import re
import warnings
import xml.etree.ElementTree as etree
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError, version

from markdown import Markdown
from markdown.extensions import Extension
from markdown.extensions.toc import TocExtension
from markdown.treeprocessors import Treeprocessor

from prodockit._markdown_toc import MarkdownTocAPIError, toc_slugging
from prodockit._zensical import (
    nav_signature,
    page_source,
    prescan_headings,
    preseed_heading_ids_from_nav,
    share,
)
from prodockit.util import IdRegistry

#: The caption blocks this numbers, and the word each is labelled with.
#: Keyed by the class `pymdownx.blocks.caption` is configured to add - see
#: the template's `zensical.toml`, which names the same two.
CAPTION_KINDS = {
    "prodockit-figure-caption": "Figure",
    "prodockit-table-caption": "Table",
}

#: Captions are registered at a level no heading uses, so a reference can
#: tell one from a section without a second lookup.
CAPTION_LEVEL = 0

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _css_image_width(value: str) -> str | None:
    """Return an image ``width`` attribute as a CSS figure width.

    Percentage and CSS-unit values already mean the same thing on the
    containing figure. A unitless HTML image width is pixels, so make that
    implicit browser rule explicit when moving it to ``style``.
    """
    value = value.strip()
    if not value:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return f"{value}px"
    if re.fullmatch(
        r"\d+(?:\.\d+)?(?:%|px|pt|pc|in|cm|mm|q|em|rem|vw|vh|vmin|vmax)",
        value,
        flags=re.IGNORECASE,
    ):
        return value
    return None


def _fit_figure_to_authored_image_width(figure: etree.Element) -> None:
    """Make one authored image width size its numbered figure as a unit.

    A percentage on the image is resolved against the full content column.
    Leaving it there while shrink-wrapping the figure creates a circular
    percentage and leaves the caption wider than the rendered image. Move
    that declaration to the figure and let the image fill it. The Markdown
    author still writes the width once, on the image where it belongs.
    """
    classes = (figure.get("class") or "").split()
    if "prodockit-figure-caption" not in classes:
        return
    image = figure.find(".//img")
    if image is None:
        return
    width = _css_image_width(image.get("width") or "")
    if width is None:
        return
    style = (figure.get("style") or "").strip()
    if re.search(r"(?:^|;)\s*width\s*:", style, flags=re.IGNORECASE):
        return
    separator = " " if style.endswith(";") or not style else "; "
    figure.set("style", f"{style}{separator}width: {width};".strip())
    del image.attrib["width"]
    image_style = (image.get("style") or "").strip()
    image_separator = " " if image_style.endswith(";") or not image_style else "; "
    image.set("style", f"{image_style}{image_separator}width: 100%;".strip())


def _slugify(text: str) -> str:
    """Minimal fallback slug, used only when 'toc' hasn't already assigned an
    id. Enable Python-Markdown's own 'toc' extension for slugs that match the
    rest of a 'toc'-rendered document exactly (unicode handling, custom
    separators, etc.) - this fallback exists only so the registry still works
    if a caller genuinely doesn't want a table of contents.
    """
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"\s+", "-", slug)


# Shared across every page of a single Zensical build (one Python process per
# `zensical build`/`zensical serve` invocation) - see prodockit._zensical and
# HeadingsExtension.extendMarkdown. Never touched unless Zensical's per-page
# context is actually detected, so it has no effect under any other tool, or
# on a caller who passes their own explicit registry/source.
_ZENSICAL_SHARED_REGISTRY = IdRegistry()

# The numbering settings the nav-wide heading pre-scan last ran with in this
# process, or None if it hasn't successfully run yet. Not a plain bool for two
# reasons: the scan reads every nav page, so repeating it per page would be
# O(pages^2) file reads for no benefit; but it also has to re-run if a
# differently-configured HeadingsExtension turns up later, since the numbers it
# computes depend on these settings. That happens routinely - extension order
# isn't guaranteed, so prodockit.refs may create a *default* HeadingsExtension
# (numbering="per-document") and trigger the first scan through it before the
# project's own configured instance runs. See _preseed_from_nav.
#
# Also keyed on nav_signature() - every nav page's mtime/size - so the cached
# scan is invalidated when a page changes on disk, not just when the settings
# do. Under `zensical build` the files never change mid-run, so this is
# constant and the scan still happens once; under `zensical serve`'s
# long-lived process it's what stops a reference resolving against a stale
# pre-scan of a page edited since (issue #99).
_ZENSICAL_PRESEED_STATE: tuple[tuple[bool, str], tuple[tuple[str, int, int], ...] | None] | None = (
    None
)

# A moved Python-Markdown TOC representation affects every page in the same
# process. Report it once rather than burying the build log in duplicates.
_MARKDOWN_TOC_API_WARNED = False


def _warn_toc_api_moved(error: MarkdownTocAPIError) -> None:
    """Report a changed TOC compatibility contract without failing silently."""
    global _MARKDOWN_TOC_API_WARNED
    if _MARKDOWN_TOC_API_WARNED:
        return
    _MARKDOWN_TOC_API_WARNED = True
    try:
        installed = version("Markdown")
    except PackageNotFoundError:
        installed = "unknown"
    warnings.warn(
        "prodockit could not read Python-Markdown's active TOC slugging "
        f"settings: {error}. Markdown {installed} appears to have moved that "
        "representation. Cross-page references to automatically generated "
        "heading ids may remain unresolved. Please report this at "
        "https://github.com/buckwem/prodockit-extensions/issues.",
        RuntimeWarning,
        stacklevel=3,
    )


def _caption_text(el: etree.Element) -> Iterator[str]:
    """A caption's own words, without its auto-number prefix."""
    for node in el.iter():
        classes = (node.get("class") or "").split()
        if "caption-prefix" in classes:
            if node.tail:
                yield node.tail
            continue
        if node.text:
            yield node.text


def _heading_text(el: etree.Element) -> Iterator[str]:
    """A heading's authored text, without TOC-generated permalink controls.

    The TOC treeprocessor runs first so this extension can reuse its final
    heading ids. With ``permalink`` enabled, it also appends an anchor whose
    pilcrow is control text rather than part of the heading's label. Walk the
    tree explicitly so ordinary inline markup remains included while only a
    ``headerlink`` subtree is omitted.
    """
    if el.text:
        yield el.text
    for child in el:
        classes = (child.get("class") or "").split()
        if "headerlink" not in classes:
            yield from _heading_text(child)
        if child.tail:
            yield child.tail


class HeadingsTreeprocessor(Treeprocessor):
    """Records every h1-h6 element's id, and its hierarchical section number,
    in a shared :class:`IdRegistry`, keyed by the current document's source
    name.

    Numbering is per-document by default: h1 is a top-level counter, h2
    nests under the nearest preceding h1 ("1.1", "1.2", ...), and so on
    through h6 - reset from scratch on every call, so reordering headings
    within a document always produces correct numbers on the next build. A
    heading with an ``unnumbered`` class (e.g. via ``# Title {: .unnumbered
    }``) is still given an id but excluded from numbering - its counter
    position is skipped entirely - so its registered ``number`` is ``None``.
    A shallower level with no heading of its own yet (a skipped level, a
    document starting below h1, or a numbered heading nested directly under
    an ``unnumbered`` one) is treated as an implicit first one rather than
    left at 0 - e.g. h1 followed directly by h3 (no h2) numbers the h3
    "1.1.1", not "1.0.1".

    With ``start_count`` set (see ``HeadingsExtension``'s ``numbering``
    config), h1 numbering continues from that value instead of starting at
    0, so numbering can continue seamlessly across pages. With
    ``appendix_letter`` set, h1 (and everything nested beneath it) is
    numbered using that letter instead of a digit - "A", "A.1", "A.1.1" -
    and ``start_count`` is ignored, since a lettered page doesn't consume a
    number from the numeric sequence at all.

    Runs at a lower priority than 'toc' (registered at 5) so it always reads
    the final id 'toc' assigned - including one already set explicitly via
    'attr_list' - rather than racing it.
    """

    def __init__(
        self,
        md: Markdown,
        registry: IdRegistry,
        source: str,
        strict: bool = True,
        start_count: int = 0,
        appendix_letter: str | None = None,
    ) -> None:
        super().__init__(md)
        self.registry = registry
        self.source = source
        self.strict = strict
        self.start_count = start_count
        self.appendix_letter = appendix_letter

    def _register_caption(
        self,
        el: etree.Element,
        counters: list[int],
        captions: dict[str, int],
    ) -> None:
        """Numbers a captioned figure or table, and registers its id.

        Numbered here rather than anywhere else because this is where the
        chapter number already exists: `counters[0]` is the same value the
        stylesheet reaches for as `counter(h1-count)`, and an appendix's
        letter is already substituted for it. Numbering captions in a
        second pass would mean deriving that a second time.

        Only a caption carrying an id is registered. An unreferenced
        figure still gets its visible number from the stylesheet, exactly
        as before; this adds nothing to a document that never points at
        one.
        """
        _fit_figure_to_authored_image_width(el)
        classes = (el.get("class") or "").split()
        kind = next((k for k in CAPTION_KINDS if k in classes), None)
        if kind is None:
            # No class to go on, so read the figure itself. The classes are
            # a project's own `pymdownx.blocks.caption` configuration - the
            # template sets them, a bare Markdown build does not - and a
            # reference must not depend on how somebody named them.
            kind = "prodockit-table-caption" if el.find(".//table") is not None else (
                "prodockit-figure-caption"
            )
        captions[kind] += 1
        caption_id = el.get("id")
        if not caption_id:
            return
        # pymdownx.blocks.caption gives every automatically numbered caption
        # a page-local implementation id such as ``__table-caption_1``. The
        # counter restarts on every Markdown page, so that id is useful as an
        # anchor within the generated page but is not an authored cross-page
        # reference target. Registering it in Zensical's shared registry made
        # the first unlabelled table on two pages look like a duplicate id.
        # Explicit author ids do not use this reserved shape and continue to
        # be registered normally.
        generated_id = rf"__{re.escape(kind.removeprefix('prodockit-'))}_\d+(?:_\d+)*"
        if re.fullmatch(generated_id, caption_id):
            return
        chapter = (
            self.appendix_letter
            if self.appendix_letter is not None
            else str(counters[0] or 1)
        )
        label = CAPTION_KINDS[kind]
        # The caption's own auto-number is skipped. It lives in a
        # `caption-prefix` span, holds whatever the project's prefix
        # template produced ("1." here, "Figure 1." in a bare build), and
        # would be repeated inside a reference already rendering a number.
        text = " ".join(
            part
            for child in el
            if child.tag in {"figcaption", "div"}
            for part in _caption_text(child)
        ).strip()
        self.registry.register(
            source=self.source,
            id=caption_id,
            level=CAPTION_LEVEL,
            text=text,
            number=f"{label} {chapter}.{captions[kind]}",
            strict=self.strict,
        )

    def run(self, root: etree.Element) -> None:
        self.registry.clear_source(self.source)
        counters = [self.start_count, 0, 0, 0, 0, 0]
        captions = dict.fromkeys(CAPTION_KINDS, 0)
        for el in root.iter():
            if el.tag == "figure":
                self._register_caption(el, counters, captions)
                continue
            if el.tag not in HEADING_TAGS:
                continue
            text = "".join(_heading_text(el))
            heading_id = el.get("id")
            if not heading_id:
                heading_id = _slugify(text)
                el.set("id", heading_id)

            level = int(el.tag[1])
            classes = (el.get("class") or "").split()
            if "unnumbered" in classes:
                number = None
            else:
                # A shallower level that's never actually appeared yet (the
                # document skipped straight from h1 to h3, started below
                # h1, or nested this heading under an .unnumbered one) is
                # backfilled to 1 rather than left at 0 - otherwise the
                # number below would show a literal "0" segment (e.g.
                # "1.0.1"), which is worse than treating the missing level
                # as an implicit first one. Doesn't touch start_count
                # itself when it's already non-zero (continuous numbering
                # legitimately seeding this page's h1 counter from earlier
                # pages) since that's not a gap to fill.
                for shallower in range(level - 1):
                    if counters[shallower] == 0:
                        counters[shallower] = 1
                counters[level - 1] += 1
                for deeper in range(level, 6):
                    counters[deeper] = 0
                first = (
                    self.appendix_letter if self.appendix_letter is not None else str(counters[0])
                )
                number = ".".join([first] + [str(c) for c in counters[1:level]])

            self.registry.register(
                source=self.source,
                id=heading_id,
                level=level,
                text=text,
                number=number,
                strict=self.strict,
            )


class HeadingsExtension(Extension):
    """Python-Markdown extension assigning ids and section numbers to headings."""

    def __init__(self, **kwargs: object) -> None:
        # Popped rather than run through Extension's own config/setConfig:
        # that machinery bool-coerces any config value whose *current*
        # default is None (see markdown.util.parseBoolValue), which would
        # silently corrupt a real IdRegistry object passed in explicitly.
        registry = kwargs.pop("registry", None)
        self._registry_explicit = isinstance(registry, IdRegistry)
        self.registry: IdRegistry = (
            registry if isinstance(registry, IdRegistry) else IdRegistry()
        )
        self.config = {
            "source": [
                "",
                "Identifier for the current document (e.g. its path), used "
                "to scope this document's own entries in the registry.",
            ],
            "numbering": [
                "per-document",
                "Either \"per-document\" (default - every document's h1 "
                "starts at 1) or \"continuous\" (h1 numbering continues "
                "across pages in Zensical nav order, and a page whose "
                "front matter sets `appendix_attr` gets letter-based "
                "numbering - \"A\", \"A.1\" - instead of continuing the "
                "numeric sequence, and doesn't consume a number from it). "
                "Only meaningful under Zensical, where nav order is known; "
                "ignored otherwise.",
            ],
            "appendix_attr": [
                "is_appendix",
                "Front matter flag name marking a page for letter-based "
                "appendix numbering when numbering=\"continuous\".",
            ],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)
        # Heading ids are 'toc''s job (including respecting one 'attr_list'
        # already set) - reuse it rather than re-deriving slugs here, but
        # don't clobber a caller's own 'toc' config (e.g. permalink=True) if
        # they've already enabled it themselves.
        if "toc" not in md.treeprocessors:
            TocExtension().extendMarkdown(md)
        source: str = self.getConfig("source")
        registry = self.registry
        strict = True
        # Only kick in when the caller hasn't configured anything themselves
        # (an explicit registry and/or source means a deliberate multi-page
        # setup - see the docs - which should keep raising on a genuine
        # collision, not silently paper over it).
        if not self._registry_explicit and not source:
            detected_source = page_source(md)
            if detected_source is not None:
                source = detected_source
                registry = _ZENSICAL_SHARED_REGISTRY
                strict = False
                self._preseed_from_nav(md, registry)
        registry = share(md, "prodockit_registry", registry)
        self.registry = registry

        start_count = 0
        appendix_letter = None
        if self.getConfig("numbering") == "continuous":
            prescan = prescan_headings(self.getConfig("appendix_attr"))
            if prescan is not None:
                start_counts, appendix_letters = prescan
                start_count = start_counts.get(source, 0)
                appendix_letter = appendix_letters.get(source)

        md.treeprocessors.register(
            HeadingsTreeprocessor(
                md,
                registry,
                source,
                strict=strict,
                start_count=start_count,
                appendix_letter=appendix_letter,
            ),
            "prodockit-headings",
            4,
        )

    def _preseed_from_nav(self, md: Markdown, registry: IdRegistry) -> None:
        """Provisionally registers every nav page's heading and caption
        ids/numbers, so a `\\ref{id}` resolves even when the page defining it
        was never rendered in *this* Python context - see
        prodockit._zensical.preseed_heading_ids_from_nav and
        prodockit-extensions#54.

        Runs once per process per distinct numbering configuration: the scan
        reads every nav page, so repeating it for every page would be
        pointless work, but the numbers it computes depend on `numbering`/
        `appendix_attr`, so a later instance configured differently has to be
        allowed to redo it. That isn't hypothetical - extension order isn't
        guaranteed, so prodockit.refs can create a *default*
        HeadingsExtension and trigger the first scan through it (numbering
        per-document) before the project's own `numbering="continuous"`
        instance runs, which without this would leave every cross-page
        reference showing a per-document number. Previous provisional
        entries are dropped first, since `preseed()` is otherwise
        first-wins.

        Slugs come from the 'toc' treeprocessor's own configured slugify/
        separator (already registered by the caller above), so a preseeded id
        matches exactly what 'toc' will assign when that page really is
        converted - including a project's own custom slugify.
        """
        global _ZENSICAL_PRESEED_STATE
        settings = (
            self.getConfig("numbering") == "continuous",
            self.getConfig("appendix_attr"),
        )
        # Keyed on the nav's on-disk state as well as the settings, so an
        # edit to a page this render doesn't touch still invalidates the
        # cached scan. Cheap enough to check per page (one stat() each)
        # unlike the scan itself, which reads and parses every nav page.
        state = (settings, nav_signature())
        if state == _ZENSICAL_PRESEED_STATE:
            return
        try:
            slugging = toc_slugging(md)
        except MarkdownTocAPIError as error:
            _warn_toc_api_moved(error)
            return
        if slugging is None:
            return
        if _ZENSICAL_PRESEED_STATE is not None:
            registry.clear_preseeded()
        ran = preseed_heading_ids_from_nav(
            registry,
            appendix_attr=settings[1],
            continuous=settings[0],
            slugify=slugging.slugify,
            separator=slugging.separator,
        )
        # Only latch on a scan that actually happened - outside a Zensical
        # build (or before its config is populated) there's nothing to
        # record, and a later page may well succeed.
        if ran:
            _ZENSICAL_PRESEED_STATE = state


def prescan(appendix_attr: str = "is_appendix") -> tuple[dict[str, int], dict[str, str]] | None:
    """Public wrapper around the internal Zensical nav pre-scan
    ``HeadingsExtension`` itself uses for ``numbering="continuous"`` mode -
    for a consuming project's own build tooling (e.g. a template's macro
    that emits a CSS counter-reset override matching the numbers this
    extension computes) to look up the exact same start-count/appendix-
    letter values, so the two stay in sync automatically instead of
    re-deriving them a second, independent way.

    Returns ``(start_counts, appendix_letters)``, both keyed by nav-relative
    page path - see ``prodockit._zensical.prescan_headings`` for the full
    description. Returns None outside a Zensical build.
    """
    return prescan_headings(appendix_attr)


def makeExtension(**kwargs: object) -> HeadingsExtension:
    return HeadingsExtension(**kwargs)
