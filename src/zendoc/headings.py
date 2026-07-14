# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""zendoc.headings: gives every heading an id and a hierarchical section
number, recorded in a shared :class:`~zendoc.util.IdRegistry` that other
zendoc extensions (currently :mod:`zendoc.refs`) look entries up in.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree

from markdown import Markdown
from markdown.extensions import Extension
from markdown.extensions.toc import TocExtension
from markdown.treeprocessors import Treeprocessor

from zendoc._zensical import page_source, prescan_headings, share
from zendoc.util import IdRegistry

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


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
# `zensical build`/`zensical serve` invocation) - see zendoc._zensical and
# HeadingsExtension.extendMarkdown. Never touched unless Zensical's per-page
# context is actually detected, so it has no effect under any other tool, or
# on a caller who passes their own explicit registry/source.
_ZENSICAL_SHARED_REGISTRY = IdRegistry()


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

    def run(self, root: etree.Element) -> None:
        self.registry.clear_source(self.source)
        counters = [self.start_count, 0, 0, 0, 0, 0]
        for el in root.iter():
            if el.tag not in HEADING_TAGS:
                continue
            text = "".join(el.itertext())
            heading_id = el.get("id")
            if not heading_id:
                heading_id = _slugify(text)
                el.set("id", heading_id)

            level = int(el.tag[1])
            classes = (el.get("class") or "").split()
            if "unnumbered" in classes:
                number = None
            else:
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
        registry = share(md, "zendoc_registry", registry)
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
            "zendoc-headings",
            4,
        )


def prescan(appendix_attr: str = "is_appendix") -> tuple[dict[str, int], dict[str, str]] | None:
    """Public wrapper around the internal Zensical nav pre-scan
    ``HeadingsExtension`` itself uses for ``numbering="continuous"`` mode -
    for a consuming project's own build tooling (e.g. a template's macro
    that emits a CSS counter-reset override matching the numbers this
    extension computes) to look up the exact same start-count/appendix-
    letter values, so the two stay in sync automatically instead of
    re-deriving them a second, independent way.

    Returns ``(start_counts, appendix_letters)``, both keyed by nav-relative
    page path - see ``zendoc._zensical.prescan_headings`` for the full
    description. Returns None outside a Zensical build.
    """
    return prescan_headings(appendix_attr)


def makeExtension(**kwargs: object) -> HeadingsExtension:
    return HeadingsExtension(**kwargs)
