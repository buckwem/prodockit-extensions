# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""prodockit.refs: ``\\ref{id}`` section cross-reference syntax, resolving to
the referenced heading's current section number - similar in spirit to
LaTeX's ``\\ref``. Builds on the id registry from :mod:`prodockit.headings`,
which is auto-enabled with matching defaults if not already present.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree

from markdown import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor

from prodockit._zensical import page_source, share
from prodockit.headings import HeadingsExtension
from prodockit.util import IdRegistry, cross_page_href

REF_RE = r"\\ref\{([^}\s]+)\}"

#: ``\autoref{id}`` - the same target as ``\ref{id}``, rendered as the
#: heading's own *text* instead of its number, and followed by "on page N"
#: in a PDF (see `prodockit.pdf.css`). Registered as its own pattern rather
#: than an option on ``\ref``, because which one to use is a per-reference
#: decision: a number reads better mid-sentence in a document nobody
#: prints, a name and page number is what a printed one needs.
AUTOREF_RE = r"\\autoref\{([^}\s]+)\}"


class RefInlineProcessor(InlineProcessor):
    """Matches ``\\ref{id}`` and emits an unresolved placeholder ``<a>``
    carrying the referenced id in a ``data-prodockit-ref`` attribute.

    Registered at a low inline-pattern priority so it runs after 'backtick'
    (190) and 'escape' (180) - meaning inline code spans are already stashed
    out of reach by the time this pattern runs, so ``\\ref{...}`` shown as
    literal example syntax inside `` `code` `` survives untouched, the same
    protection fenced code blocks already get from being stashed even
    earlier, during preprocessing.

    The placeholder can't be resolved to a real section number here: inline
    patterns run before the current document's own headings have been
    numbered (see HeadingsTreeprocessor, priority 4, which runs after this
    pattern's containing 'inline' treeprocessor, priority 20) - resolution
    happens later, in RefResolverTreeprocessor.
    """

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        el = etree.Element("a")
        el.set("data-prodockit-ref", m.group(1))
        el.set("class", "prodockit-ref")
        return el, m.start(0), m.end(0)


class AutoRefInlineProcessor(InlineProcessor):
    """Matches ``\\autoref{id}`` and emits an unresolved placeholder ``<a>``
    carrying the referenced id in a ``data-prodockit-autoref`` attribute.

    Same deferral as :class:`RefInlineProcessor` - the heading being
    referenced may not be registered yet when this pattern runs - and the
    same inline-pattern priority, so the syntax is equally safe to show
    inside a code span.
    """

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        el = etree.Element("a")
        el.set("data-prodockit-autoref", m.group(1))
        el.set("class", "prodockit-autoref")
        return el, m.start(0), m.end(0)


class RefResolverTreeprocessor(Treeprocessor):
    """Resolves the placeholder ``<a data-prodockit-ref="id">`` elements left by
    :class:`RefInlineProcessor` to the referenced heading's section number,
    once the current document's own headings have been numbered.

    Runs at a lower priority than 'prodockit-headings' (4) so every heading in
    *this* document - including one defined further down the page than
    where it's referenced - is already registered by the time resolution
    happens. A reference to a heading in a document not yet processed in
    this build (e.g. a later page in a multi-page site) can't be resolved
    yet either; both cases fall back to `unresolved`, the same way an
    undefined LaTeX \\ref shows "??" until a later compilation pass.
    """

    def __init__(
        self, md: Markdown, registry: IdRegistry, source: str, unresolved: str = "??"
    ) -> None:
        super().__init__(md)
        self.registry = registry
        self.source = source
        self.unresolved = unresolved

    def run(self, root: etree.Element) -> None:
        for el in root.iter("a"):
            ref_id = el.get("data-prodockit-ref")
            if ref_id is not None:
                del el.attrib["data-prodockit-ref"]
                self._resolve(el, ref_id, "prodockit-ref")
                continue
            auto_id = el.get("data-prodockit-autoref")
            if auto_id is not None:
                del el.attrib["data-prodockit-autoref"]
                self._resolve(el, auto_id, "prodockit-autoref")

    def _resolve(self, el: etree.Element, ref_id: str, css_class: str) -> None:
        """Renders a reference as the target heading's number and name.

        Both syntaxes render the same text - "1.1 Configuration", or
        "A.1 Terms" for an appendix, whose letter is already the first
        segment of its number. A bare "1.1" tells a reader nothing about
        what they are being sent to, and having to look it up defeats the
        cross-reference; the number alone was what ``\\ref{id}`` used to
        render.

        The only difference between the two is that ``\\autoref{id}``
        additionally gets " on page N" in a PDF, from
        `prodockit.pdf.css` - which is why they need separate classes even
        though the resolution is identical.

        An *unnumbered* heading (a cover page, appendix front matter) has
        no number but does have a name, so it renders as just the name
        rather than falling back to `unresolved` - it is a perfectly good
        thing to point at. Only a genuinely unknown id is unresolved.
        """
        record = self.registry.get(ref_id)
        if record is None:
            el.text = self.unresolved
            el.set("class", f"{css_class} {css_class}-unresolved")
            return
        el.text = f"{record.number} {record.text}" if record.number else record.text
        el.set("href", cross_page_href(record.source, self.source, ref_id))


class RefsExtension(Extension):
    """Python-Markdown extension providing the ``\\ref{id}`` and
    ``\\autoref{id}`` syntaxes."""

    def __init__(self, **kwargs: object) -> None:
        # See HeadingsExtension for why this is popped rather than run
        # through Extension's own config/setConfig machinery. None here
        # means "discover the registry from a sibling HeadingsExtension",
        # not "use an empty registry" - that distinction can't be made once
        # a value has round-tripped through setConfig.
        registry = kwargs.pop("registry", None)
        self.registry: IdRegistry | None = registry if isinstance(registry, IdRegistry) else None
        self.config = {
            "source": [
                "",
                "Identifier for the current document (e.g. its path), used "
                "to build a correct link when a \\ref{id} target lives on a "
                "different page. Auto-detected under Zensical if not set.",
            ],
            "unresolved": [
                "??",
                "Text rendered by \\ref{id} when id doesn't resolve to a "
                "numbered heading - unknown id, or a heading marked "
                "unnumbered.",
            ],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)
        registry = self.registry
        if registry is None:
            # Order-independent: if prodockit.headings already ran on this page
            # (in either list order), it stashed its registry on md - reuse
            # that directly rather than searching md.registeredExtensions,
            # which only works if headings happened to run first.
            existing = getattr(md, "prodockit_registry", None)
            if isinstance(existing, IdRegistry):
                registry = existing
            else:
                headings_ext = next(
                    (ext for ext in md.registeredExtensions if isinstance(ext, HeadingsExtension)),
                    None,
                )
                if headings_ext is None:
                    headings_ext = HeadingsExtension()
                    headings_ext.extendMarkdown(md)
                registry = headings_ext.registry
        registry = share(md, "prodockit_registry", registry)
        source: str = self.getConfig("source") or page_source(md) or ""
        unresolved: str = self.getConfig("unresolved")
        md.inlinePatterns.register(
            RefInlineProcessor(REF_RE, md),
            "prodockit-ref",
            45,
        )
        # Above \ref's own priority so `\autoref{id}` is matched whole -
        # REF_RE would otherwise never see it (it requires a literal
        # `\ref{`), but registering the more specific pattern first keeps
        # that independent of REF_RE's exact wording.
        md.inlinePatterns.register(
            AutoRefInlineProcessor(AUTOREF_RE, md),
            "prodockit-autoref",
            46,
        )
        md.treeprocessors.register(
            RefResolverTreeprocessor(md, registry, source, unresolved),
            "prodockit-ref-resolver",
            2,
        )


def makeExtension(**kwargs: object) -> RefsExtension:
    return RefsExtension(**kwargs)
