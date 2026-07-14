# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""zendoc.citations: define a citation source once, cite it by key anywhere.

Mark a source's paragraph (or any block) with an id and a short display
text via ``attr_list``:

    Skoulikari, A. (2023) *Learning Git*. Sebastopol, CA: O'Reilly Media.
    {: #skou2023 .reference data-cite-text="Skoulikari, 2023" }

then cite it from anywhere in the build with ``\\cite{skou2023}``, which
resolves to a linked, bracketed citation: ``[Skoulikari, 2023]``. Multiple
keys in one citation (``\\cite{skou2023,chacon2014}``) render as
``[Skoulikari, 2023; Chacon and Straub, 2014]``.

Unlike zendoc.headings/zendoc.refs, defining and citing are bundled into one
extension here rather than split in two: a definition is useless without a
place to cite it, and a citation is meaningless without something defined
to point at - there's no independently useful "just defining" half the way
zendoc.headings' ids/numbers are useful even without zendoc.refs.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree
from pathlib import Path

from markdown import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor

from zendoc._zensical import nav_pages, page_source, share
from zendoc.util import CitationRegistry, cross_page_href

CITE_RE = r"\\cite\{([^}]+)\}"
_ATTR_RE = re.compile(r"\{:\s*([^}]+?)\s*\}")
_ID_RE = re.compile(r"#([\w-]+)")
_CITE_TEXT_RE = re.compile(r'data-cite-text="([^"]*)"')
_FENCE_RE = re.compile(
    r"^[ \t]*```.*?^[ \t]*```[ \t]*$|^[ \t]*~~~.*?^[ \t]*~~~[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def _strip_fences(text: str) -> str:
    """Blanks out fenced code blocks before a raw-text regex scan, so a
    documentation page showing zendoc.citations' own definition syntax as a
    *literal example* inside a fenced code block doesn't get mistaken for a
    real definition by :func:`_preseed_from_nav` (which, unlike
    :class:`CitationDefTreeprocessor`, scans raw text directly rather than
    the parsed, fence-aware Python-Markdown tree)."""
    return _FENCE_RE.sub("", text)

# Shared across every page of a single Zensical build - see zendoc._zensical
# and CitationsExtension.extendMarkdown. Never touched unless Zensical's
# per-page context is actually detected.
_ZENSICAL_SHARED_REGISTRY = CitationRegistry()


def _preseed_from_nav(registry: CitationRegistry) -> None:
    """Pre-scans every page in the current Zensical build's nav for
    ``data-cite-text`` attr_list definitions - the same syntax
    :class:`CitationDefTreeprocessor` looks for - provisionally registering
    each one (via :meth:`CitationRegistry.preseed`) before any page has
    actually been converted.

    Fixes the classic "cited before defined" ordering problem: a source is
    usually cited from an early chapter but defined on a references page
    kept at the end of nav, which - without this - is a forward reference
    to a page `zensical build`'s single, one-shot process hasn't rendered
    yet (unlike `zensical serve`'s live-reload, which eventually rebuilds
    every page at least once). Reads raw file text directly rather than
    waiting for Python-Markdown to parse it - safe here because a citation
    definition's id/text are already literal attr_list attribute values,
    unlike zendoc.headings' section numbers, which genuinely depend on
    running the real Python-Markdown pipeline to compute.
    """
    located = nav_pages()
    if located is None:
        return
    docs_dir, pages = located
    for rel_path in pages:
        try:
            text = (Path(docs_dir) / rel_path).read_text(encoding="utf-8")
        except OSError:
            continue
        text = _strip_fences(text)
        for attr_match in _ATTR_RE.finditer(text):
            attrs = attr_match.group(1)
            id_match = _ID_RE.search(attrs)
            cite_text_match = _CITE_TEXT_RE.search(attrs)
            if id_match and cite_text_match:
                registry.preseed(rel_path, id_match.group(1), cite_text_match.group(1))


class CitationDefTreeprocessor(Treeprocessor):
    """Registers every element carrying a ``data-cite-text`` attribute
    (typically set via ``attr_list``, e.g. ``{: #skou2023 data-cite-text="Skoulikari, 2023" }``)
    in a shared :class:`~zendoc.util.CitationRegistry`, keyed by the current
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
    in a ``data-zendoc-cite`` attribute.

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
        el.set("data-zendoc-cite", m.group(1))
        return el, m.start(0), m.end(0)


class CiteResolverTreeprocessor(Treeprocessor):
    """Resolves the placeholder ``<span data-zendoc-cite="...">`` elements
    left by :class:`CiteInlineProcessor` into a bracketed citation, once the
    current document's own citation definitions have been registered.

    Runs at a lower priority than 'zendoc-citations-def' so a citation can
    reference a source defined further down the same document - or on a
    page not yet built in a Zensical multi-page site, which instead falls
    back to `unresolved` for that key, the same way zendoc.refs does.
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
            raw_keys = el.get("data-zendoc-cite")
            if raw_keys is None:
                continue
            del el.attrib["data-zendoc-cite"]
            el.set("class", "zendoc-cite")
            keys = [key.strip() for key in raw_keys.split(",") if key.strip()]
            el.text = "["
            last = len(keys) - 1
            for i, key in enumerate(keys):
                record = self.registry.get(key)
                a = etree.SubElement(el, "a")
                if record is None:
                    a.text = self.unresolved
                    a.set("class", "zendoc-cite-unresolved")
                else:
                    a.text = record.text
                    a.set("href", cross_page_href(record.source, self.source, key))
                a.tail = "]" if i == last else "; "


class CitationsExtension(Extension):
    """Python-Markdown extension providing citation-key definitions and the
    ``\\cite{id}`` syntax."""

    def __init__(self, **kwargs: object) -> None:
        # See zendoc.headings.HeadingsExtension for why this is popped
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
                _preseed_from_nav(registry)
        registry = share(md, "zendoc_citation_registry", registry)
        self.registry = registry
        unresolved: str = self.getConfig("unresolved")
        md.treeprocessors.register(
            CitationDefTreeprocessor(md, registry, source, strict=strict),
            "zendoc-citations-def",
            6,
        )
        md.inlinePatterns.register(
            CiteInlineProcessor(CITE_RE, md),
            "zendoc-cite",
            44,
        )
        md.treeprocessors.register(
            CiteResolverTreeprocessor(md, registry, source, unresolved),
            "zendoc-cite-resolver",
            1,
        )


def makeExtension(**kwargs: object) -> CitationsExtension:
    return CitationsExtension(**kwargs)
