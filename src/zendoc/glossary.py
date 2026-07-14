# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""zendoc.glossary: define a term once, insert it by key anywhere.

Mark a term's paragraph (or any block) with an id and its display text via
``attr_list``:

    **CSS** - Cascading Style Sheets.
    {: #css .acronym data-term="CSS" }

then insert it from anywhere in the build with ``\\gls{css}``, which
resolves to the term's own text, linked to its definition: ``CSS``.

Unlike :mod:`zendoc.citations`' ``\\cite{id}`` (which generates new
bracketed citation text), ``\\gls{id}`` inserts the term's *own* text
in-line - closer to LaTeX's ``glossaries`` package (``\\gls{key}`` expands
to the term's own name) than to a citation. One shared registry covers
both acronym and glossary entries (and anything else you want to define a
short term for) - they're the same kind of thing (an id with a short
display text), just organised across two conventionally-named pages.

Like zendoc.citations, defining and inserting are bundled into one
extension: a definition is useless without somewhere to use it, so there's
no independently useful "just defining" half to split out.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree

from markdown import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor

from zendoc._zensical import page_source, preseed_attr_from_nav, share
from zendoc.util import GlossaryRegistry, cross_page_href

GLS_RE = r"\\gls\{([^}\s]+)\}"

# Shared across every page of a single Zensical build - see zendoc._zensical
# and GlossaryExtension.extendMarkdown. Never touched unless Zensical's
# per-page context is actually detected.
_ZENSICAL_SHARED_REGISTRY = GlossaryRegistry()


class GlossaryDefTreeprocessor(Treeprocessor):
    """Registers every element carrying a ``data-term`` attribute
    (typically set via ``attr_list``, e.g. ``{: #css data-term="CSS" }``)
    in a shared :class:`~zendoc.util.GlossaryRegistry`, keyed by the current
    document's source name, then strips the attribute - it's internal
    bookkeeping, not meant to leak into the rendered HTML.

    Runs at a lower priority than 'attr_list' (registered at 8) so it always
    sees the id/attribute attr_list assigned, rather than racing it.
    """

    def __init__(
        self, md: Markdown, registry: GlossaryRegistry, source: str, strict: bool = True
    ) -> None:
        super().__init__(md)
        self.registry = registry
        self.source = source
        self.strict = strict

    def run(self, root: etree.Element) -> None:
        self.registry.clear_source(self.source)
        for el in root.iter():
            text = el.get("data-term")
            if text is None:
                continue
            del el.attrib["data-term"]
            term_id = el.get("id")
            if not term_id:
                continue
            self.registry.register(
                source=self.source,
                id=term_id,
                text=text,
                strict=self.strict,
            )


class GlsInlineProcessor(InlineProcessor):
    """Matches ``\\gls{id}`` and emits an unresolved placeholder ``<a>``
    carrying the referenced id in a ``data-zendoc-gls`` attribute.

    Registered at a low inline-pattern priority so it runs after 'backtick'
    (190) and 'escape' (180) - meaning inline code spans are already stashed
    out of reach by the time this pattern runs, so ``\\gls{...}`` shown as
    literal example syntax survives untouched, the same protection fenced
    code blocks get from being stashed even earlier, during preprocessing.
    """

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        el = etree.Element("a")
        el.set("data-zendoc-gls", m.group(1))
        return el, m.start(0), m.end(0)


class GlsResolverTreeprocessor(Treeprocessor):
    """Resolves the placeholder ``<a data-zendoc-gls="id">`` elements left
    by :class:`GlsInlineProcessor` to the referenced term's own text, once
    the current document's own term definitions have been registered.

    Runs at a lower priority than 'zendoc-glossary-def' so a reference can
    point at a term defined further down the same document - or on a page
    not yet built in a Zensical multi-page site, which instead falls back
    to `unresolved` for that id, the same way zendoc.refs/zendoc.citations
    do.
    """

    def __init__(
        self, md: Markdown, registry: GlossaryRegistry, source: str, unresolved: str = "?"
    ) -> None:
        super().__init__(md)
        self.registry = registry
        self.source = source
        self.unresolved = unresolved

    def run(self, root: etree.Element) -> None:
        for el in root.iter("a"):
            term_id = el.get("data-zendoc-gls")
            if term_id is None:
                continue
            del el.attrib["data-zendoc-gls"]
            record = self.registry.get(term_id)
            if record is None:
                el.text = self.unresolved
                el.set("class", "zendoc-gls-unresolved")
            else:
                el.text = record.text
                el.set("href", cross_page_href(record.source, self.source, term_id))


class GlossaryExtension(Extension):
    """Python-Markdown extension providing term definitions and the
    ``\\gls{id}`` syntax."""

    def __init__(self, **kwargs: object) -> None:
        # See zendoc.headings.HeadingsExtension for why this is popped
        # rather than run through Extension's own config/setConfig
        # machinery.
        registry = kwargs.pop("registry", None)
        self._registry_explicit = isinstance(registry, GlossaryRegistry)
        self.registry: GlossaryRegistry = (
            registry if isinstance(registry, GlossaryRegistry) else GlossaryRegistry()
        )
        self.config = {
            "source": [
                "",
                "Identifier for the current document (e.g. its path), used "
                "to scope this document's own term definitions in the "
                "registry, and to build a correct link when a \\gls{id} "
                "target lives on a different page.",
            ],
            "unresolved": [
                "?",
                "Text rendered for a \\gls{id} key that doesn't resolve to "
                "a definition.",
            ],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)
        source: str = self.getConfig("source")
        registry = self.registry
        strict = True
        # Only kick in when the caller hasn't configured anything
        # themselves - see HeadingsExtension.extendMarkdown for the same
        # pattern and rationale.
        if not self._registry_explicit and not source:
            detected_source = page_source(md)
            if detected_source is not None:
                source = detected_source
                registry = _ZENSICAL_SHARED_REGISTRY
                strict = False
                preseed_attr_from_nav(registry, "data-term")
        registry = share(md, "zendoc_glossary_registry", registry)
        self.registry = registry
        unresolved: str = self.getConfig("unresolved")
        md.treeprocessors.register(
            GlossaryDefTreeprocessor(md, registry, source, strict=strict),
            "zendoc-glossary-def",
            6,
        )
        md.inlinePatterns.register(
            GlsInlineProcessor(GLS_RE, md),
            "zendoc-gls",
            43,
        )
        md.treeprocessors.register(
            GlsResolverTreeprocessor(md, registry, source, unresolved),
            "zendoc-gls-resolver",
            1,
        )


def makeExtension(**kwargs: object) -> GlossaryExtension:
    return GlossaryExtension(**kwargs)
