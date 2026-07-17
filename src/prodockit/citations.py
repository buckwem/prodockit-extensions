# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""prodockit.citations: define a citation source once, cite it by key anywhere.

Mark a source's paragraph (or any block) with an id and a short display
text via ``attr_list``:

    Skoulikari, A. (2023) *Learning Git*. Sebastopol, CA: O'Reilly Media.
    {: #skou2023 .reference data-cite-text="Skoulikari, 2023" }

then cite it from anywhere in the build with ``\\cite{skou2023}``, which
resolves to a linked, bracketed citation: ``[Skoulikari, 2023]``. Multiple
keys in one citation (``\\cite{skou2023,chacon2014}``) render as
``[Skoulikari, 2023; Chacon and Straub, 2014]``.

Unlike prodockit.headings/prodockit.refs, defining and citing are bundled into one
extension here rather than split in two: a definition is useless without a
place to cite it, and a citation is meaningless without something defined
to point at - there's no independently useful "just defining" half the way
prodockit.headings' ids/numbers are useful even without prodockit.refs.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree

from markdown import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor

from prodockit._zensical import page_source, preseed_attr_from_nav, share
from prodockit.util import CitationRegistry, cross_page_href

CITE_RE = r"\\cite\{([^}]+)\}"

# Shared across every page of a single Zensical build - see prodockit._zensical
# and CitationsExtension.extendMarkdown. Never touched unless Zensical's
# per-page context is actually detected.
_ZENSICAL_SHARED_REGISTRY = CitationRegistry()


class CitationDefTreeprocessor(Treeprocessor):
    """Registers every element carrying a ``data-cite-text`` attribute
    (typically set via ``attr_list``, e.g. ``{: #skou2023 data-cite-text="Skoulikari, 2023" }``)
    in a shared :class:`~prodockit.util.CitationRegistry`, keyed by the current
    document's source name, then strips the attribute - it's internal
    bookkeeping, not meant to leak into the rendered HTML.

    Runs at a lower priority than 'attr_list' (registered at 8) so it always
    sees the id/attribute attr_list assigned, rather than racing it.
    """

    def __init__(
        self, md: Markdown, registry: CitationRegistry, source: str, strict: bool = True
    ) -> None:
        super().__init__(md)
        self.registry = registry
        self.source = source
        self.strict = strict

    def run(self, root: etree.Element) -> None:
        self.registry.clear_source(self.source)
        for el in root.iter():
            text = el.get("data-cite-text")
            if text is None:
                continue
            del el.attrib["data-cite-text"]
            citation_id = el.get("id")
            if not citation_id:
                continue
            self.registry.register(
                source=self.source,
                id=citation_id,
                text=text,
                strict=self.strict,
            )


class CiteInlineProcessor(InlineProcessor):
    """Matches ``\\cite{id}`` or ``\\cite{id1,id2,...}`` and emits an
    unresolved placeholder ``<span>`` carrying the raw, comma-separated keys
    in a ``data-prodockit-cite`` attribute.

    Registered at a low inline-pattern priority so it runs after 'backtick'
    (190) and 'escape' (180) - meaning inline code spans are already stashed
    out of reach by the time this pattern runs, so ``\\cite{...}`` shown as
    literal example syntax survives untouched, the same protection fenced
    code blocks get from being stashed even earlier, during preprocessing.
    """

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        el = etree.Element("span")
        el.set("data-prodockit-cite", m.group(1))
        return el, m.start(0), m.end(0)


class CiteResolverTreeprocessor(Treeprocessor):
    """Resolves the placeholder ``<span data-prodockit-cite="...">`` elements
    left by :class:`CiteInlineProcessor` into a bracketed citation, once the
    current document's own citation definitions have been registered.

    Runs at a lower priority than 'prodockit-citations-def' so a citation can
    reference a source defined further down the same document - or on a
    page not yet built in a Zensical multi-page site, which instead falls
    back to `unresolved` for that key, the same way prodockit.refs does.
    """

    def __init__(
        self, md: Markdown, registry: CitationRegistry, source: str, unresolved: str = "?"
    ) -> None:
        super().__init__(md)
        self.registry = registry
        self.source = source
        self.unresolved = unresolved

    def run(self, root: etree.Element) -> None:
        for el in root.iter("span"):
            raw_keys = el.get("data-prodockit-cite")
            if raw_keys is None:
                continue
            del el.attrib["data-prodockit-cite"]
            el.set("class", "prodockit-cite")
            keys = [key.strip() for key in raw_keys.split(",") if key.strip()]
            el.text = "["
            last = len(keys) - 1
            for i, key in enumerate(keys):
                record = self.registry.get(key)
                a = etree.SubElement(el, "a")
                if record is None:
                    a.text = self.unresolved
                    a.set("class", "prodockit-cite-unresolved")
                else:
                    a.text = record.text
                    a.set("href", cross_page_href(record.source, self.source, key))
                a.tail = "]" if i == last else "; "


class CitationsExtension(Extension):
    """Python-Markdown extension providing citation-key definitions and the
    ``\\cite{id}`` syntax."""

    def __init__(self, **kwargs: object) -> None:
        # See prodockit.headings.HeadingsExtension for why this is popped
        # rather than run through Extension's own config/setConfig
        # machinery.
        registry = kwargs.pop("registry", None)
        self._registry_explicit = isinstance(registry, CitationRegistry)
        self.registry: CitationRegistry = (
            registry if isinstance(registry, CitationRegistry) else CitationRegistry()
        )
        self.config = {
            "source": [
                "",
                "Identifier for the current document (e.g. its path), used "
                "to scope this document's own citation definitions in the "
                "registry.",
            ],
            "unresolved": [
                "?",
                "Text rendered for a \\cite{id} key that doesn't resolve to "
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
                preseed_attr_from_nav(registry, "data-cite-text")
        registry = share(md, "prodockit_citation_registry", registry)
        self.registry = registry
        unresolved: str = self.getConfig("unresolved")
        md.treeprocessors.register(
            CitationDefTreeprocessor(md, registry, source, strict=strict),
            "prodockit-citations-def",
            6,
        )
        md.inlinePatterns.register(
            CiteInlineProcessor(CITE_RE, md),
            "prodockit-cite",
            44,
        )
        md.treeprocessors.register(
            CiteResolverTreeprocessor(md, registry, source, unresolved),
            "prodockit-cite-resolver",
            1,
        )


def makeExtension(**kwargs: object) -> CitationsExtension:
    return CitationsExtension(**kwargs)
