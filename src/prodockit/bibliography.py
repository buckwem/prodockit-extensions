# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

r"""prodockit.bibliography: a BibTeX/BibLaTeX ``.bib`` file as the single
source of truth for a document's references, formatted via any Citation
Style Language (CSL) style - APA, IEEE, Harvard, Vancouver, and hundreds
more, the same open, actively-maintained style ecosystem Zotero/Mendeley/
EndNote already use.

An alternative to :mod:`prodockit.citations`, not a companion to it - both
provide ``\cite{id}``, so enable one or the other, not both. Where
prodockit.citations resolves a citation against a hand-authored
``data-cite-text`` paragraph elsewhere in the document (you write the
formatted reference-list entry yourself, once, by hand),
prodockit.bibliography resolves against structured bibliographic data in a
``.bib`` file and generates the formatted entry - inline citation and
reference-list entry alike - for you.

The actual citation-style formatting is delegated to Pandoc's own
``--citeproc`` (confirmed directly: a plain ``.bib`` file plus a chosen
``.csl`` style produces a correctly formatted, sorted bibliography with no
custom code at all) rather than reimplemented here - the same reasoning
:mod:`prodockit.pdf` already documents for why it feeds Pandoc real HTML
instead of hand-translating every markdown feature: CSL processing
(sorting, disambiguation, locale-specific formatting) is a mature-tool-
sized problem, not a small one. This makes `pandoc` a required, on-PATH
dependency for this extension specifically - including for a project that
never builds a PDF at all, unlike every other prodockit extension, which
needs nothing beyond Python-Markdown itself.

Only single-key ``\cite{id}`` is supported (not
prodockit.citations' ``\cite{id1,id2,...}``) - Pandoc's own multi-source
citation formatting (``[@id1; @id2]``) returns one joined, opaque string
per CSL style's own rules for how to combine them, which can't be reliably
split back into individually-linkable pieces afterward. A multi-key
`\cite{...}` is therefore left completely unmatched by this extension's
own syntax (falls through as literal text) rather than silently mishandled.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as etree

from bs4 import BeautifulSoup, Tag
from markdown import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor

from prodockit._zensical import find_page_with_marker, page_source, share
from prodockit.util import cross_page_href

BIBLIOGRAPHY_MARKER = "\\bibliography"

CITE_RE = r"\\cite\{([^}\s,]+)\}"
BIBLIOGRAPHY_RE = r"\\bibliography\b"

_NOT_FOUND_RE = re.compile(r"citeproc: citation (\S+) not found", re.IGNORECASE)


class BibliographyError(RuntimeError):
    """Raised when the underlying `pandoc` invocation fails, or isn't
    found on `PATH` at all."""


class _BibliographyCache:
    """Per-(bib_file, csl_style) cache of Pandoc-formatted output, shared
    across every page of a single Zensical build (one Python process per
    `zensical build`/`zensical serve` invocation - see prodockit._zensical) -
    a `.bib` file's entries are all defined once, centrally, unlike
    prodockit.citations'/prodockit.glossary's per-page-scanned definitions, so
    there's no cross-page registry-merging problem to solve here, just a
    cache to avoid re-running `pandoc` for the same key twice.
    """

    def __init__(self, bib_file: str, csl_style: str) -> None:
        self.bib_file = bib_file
        self.csl_style = csl_style
        self._citations: dict[str, tuple[str, bool]] = {}
        self._bibliography_html: str | None = None
        self.bibliography_source: str | None = None

    def resolve_citation(self, key: str) -> tuple[str, bool]:
        """Returns (formatted_inline_html, resolved) for one citation key,
        running `pandoc` once per distinct key and caching the result for
        the rest of this build."""
        if key not in self._citations:
            stdout, stderr = _run_pandoc_citeproc(
                f"[@{key}]\n", bib_file=self.bib_file, csl_style=self.csl_style
            )
            resolved = not _NOT_FOUND_RE.search(stderr)
            soup = BeautifulSoup(stdout, "html.parser")
            span = soup.find("span", class_="citation")
            inner_html = span.decode_contents() if isinstance(span, Tag) else stdout.strip()
            self._citations[key] = (inner_html, resolved)
        return self._citations[key]

    def bibliography_html(self) -> str:
        """Returns the complete, formatted `<div id="refs">` bibliography
        list for every entry in `bib_file` (via Pandoc's own `nocite: '@*'`
        metadata, the same "include every entry regardless of whether it's
        actually cited" idiom LaTeX's `\\nocite{*}` provides) - computed
        once and cached for the rest of this build."""
        if self._bibliography_html is None:
            stdout, _ = _run_pandoc_citeproc(
                "", bib_file=self.bib_file, csl_style=self.csl_style,
                front_matter="---\nnocite: '@*'\n---\n\n",
            )
            soup = BeautifulSoup(stdout, "html.parser")
            refs_div = soup.find("div", id="refs")
            if not isinstance(refs_div, Tag):
                self._bibliography_html = ""
            else:
                for entry in refs_div.find_all("div", class_="csl-entry"):
                    classes = entry.get("class", [])
                    if "reference" not in classes:
                        entry["class"] = [*classes, "reference"]
                self._bibliography_html = str(refs_div)
        return self._bibliography_html


# Shared across every page of a single Zensical build - see prodockit._zensical
# and BibliographyExtension.extendMarkdown. Keyed by (bib_file, csl_style) so
# two differently-configured instances (unusual, but not prevented) don't
# share a cache that doesn't apply to both.
_ZENSICAL_SHARED_CACHES: dict[tuple[str, str], _BibliographyCache] = {}



def _run_pandoc_citeproc(
    body: str, *, bib_file: str, csl_style: str, front_matter: str = ""
) -> tuple[str, str]:
    """Runs `pandoc --citeproc` over `front_matter + body` (Pandoc's own
    markdown citation syntax, e.g. `[@key]`), returning (stdout, stderr) as
    HTML/diagnostic text. Raises `BibliographyError` if `pandoc` isn't on
    `PATH` at all, or if it exits non-zero (an unresolved citation key is
    *not* a non-zero exit - see module docstring - only a genuinely broken
    invocation is, e.g. a malformed `.bib` file)."""
    if shutil.which("pandoc") is None:
        raise BibliographyError(
            "pandoc not found on PATH - prodockit.bibliography formats citations "
            "and bibliography entries via `pandoc --citeproc`, the same tool "
            "prodockit.pdf already needs (see https://pandoc.org/installing.html) "
            "- required here even for a website-only build with no PDF."
        )
    cmd = ["pandoc", "-f", "markdown", "-t", "html", "--citeproc", f"--bibliography={bib_file}"]
    if csl_style:
        cmd.append(f"--csl={csl_style}")
    result = subprocess.run(cmd, input=front_matter + body, capture_output=True, text=True)
    if result.returncode != 0:
        raise BibliographyError(
            f"pandoc exited with status {result.returncode} formatting a "
            f"citation/bibliography (bib_file={bib_file!r}): {result.stderr}"
        )
    return result.stdout, result.stderr


class BibCiteInlineProcessor(InlineProcessor):
    """Matches `\\cite{id}` (a single key only - see module docstring) and
    emits an unresolved placeholder `<span>` carrying the key in a
    `data-prodockit-bib-cite` attribute.

    Registered at a low inline-pattern priority so it runs after 'backtick'
    (190) and 'escape' (180) - meaning inline code spans are already
    stashed out of reach by the time this pattern runs, so `\\cite{...}`
    shown as literal example syntax survives untouched, the same
    protection fenced code blocks get from being stashed even earlier,
    during preprocessing."""

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        el = etree.Element("span")
        el.set("data-prodockit-bib-cite", m.group(1))
        return el, m.start(0), m.end(0)


class BibliographyMarkerInlineProcessor(InlineProcessor):
    """Matches a bare `\\bibliography` marker and emits an empty
    placeholder `<span>`, resolved by BibliographyResolverTreeprocessor
    into the complete, formatted reference list. Put it on its own
    paragraph/line - the resolver replaces that whole paragraph, not just
    this inline placeholder, once resolved."""

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        el = etree.Element("span")
        el.set("data-prodockit-bibliography", "1")
        return el, m.start(0), m.end(0)


class BibliographyResolverTreeprocessor(Treeprocessor):
    """Resolves the placeholder elements left by BibCiteInlineProcessor/
    BibliographyMarkerInlineProcessor, once per page.

    Runs at a low treeprocessor priority (after 'inline', so every
    placeholder already exists in the tree)."""

    def __init__(
        self,
        md: Markdown,
        cache: _BibliographyCache,
        source: str,
        unresolved: str,
    ) -> None:
        super().__init__(md)
        self.cache = cache
        self.source = source
        self.unresolved = unresolved

    def run(self, root: etree.Element) -> None:
        if self.cache.bibliography_source is None:
            for el in root.iter():
                if el.get("data-prodockit-bibliography") is not None:
                    self.cache.bibliography_source = self.source
                    break

        # Built once up front (etree.Element has no parent pointers) -
        # needed for the bibliography-marker case below, which may have to
        # remove the marker's own *parent*, not just the marker itself.
        parent_map = {child: parent for parent in root.iter() for child in parent}

        for el in list(root.iter()):
            if el.get("data-prodockit-bib-cite") is not None:
                self._resolve_citation(el)
            elif el.get("data-prodockit-bibliography") is not None:
                self._replace_bibliography_marker(parent_map, el)

    def _replace_bibliography_marker(
        self, parent_map: dict[etree.Element, etree.Element], marker: etree.Element
    ) -> None:
        container = parent_map.get(marker)
        if container is None:
            return
        # The documented usage - \bibliography alone on its own paragraph -
        # means `container` is a <p> whose sole content is the marker.
        # Splicing the generated bibliography (a <div> of <div>s) directly
        # inside that <p> would be invalid HTML, so this replaces the
        # whole <p> in *its* own parent instead, not just the marker
        # within the <p>. A marker mixed inline with other text (not the
        # documented usage) falls back to replacing just the marker.
        if len(container) == 1 and not (container.text or "").strip():
            grandparent = parent_map.get(container)
            if grandparent is not None:
                target, node = grandparent, container
            else:
                target, node = container, marker
        else:
            target, node = container, marker

        html = self.cache.bibliography_html()
        # Parses the pre-built HTML fragment as a tree of real elements
        # (not left as a raw string, which Python-Markdown's own tree
        # can't hold) via etree directly - wrapped in a throwaway <div>
        # first since a fragment with multiple top-level <div>s and no
        # single root can't otherwise be parsed safely.
        wrapped = etree.fromstring(f"<div>{html}</div>")
        index = list(target).index(node)
        target.remove(node)
        for i, child in enumerate(wrapped):
            target.insert(index + i, child)

    def _resolve_citation(self, el: etree.Element) -> None:
        key = el.get("data-prodockit-bib-cite")
        assert key is not None
        del el.attrib["data-prodockit-bib-cite"]
        formatted_html, resolved = self.cache.resolve_citation(key)
        if not resolved:
            el.text = self.unresolved
            el.set("class", "prodockit-bib-cite prodockit-bib-cite-unresolved")
            return
        inner = etree.fromstring(f"<span>{formatted_html}</span>")
        el.text = inner.text
        for child in inner:
            el.append(child)
        el.set("class", "prodockit-bib-cite")
        if self.cache.bibliography_source is not None:
            href = cross_page_href(self.cache.bibliography_source, self.source, f"ref-{key}")
            link = etree.Element("a", href=href)
            link.text = el.text
            el.text = None
            for child in list(el):
                el.remove(child)
                link.append(child)
            el.append(link)


class BibliographyExtension(Extension):
    """Python-Markdown extension resolving `.bib`-backed `\\cite{id}`
    citations and a `\\bibliography` reference-list marker via Pandoc's own
    `--citeproc`."""

    def __init__(self, **kwargs: object) -> None:
        self.config = {
            "bib_file": [
                "references.bib",
                "Path to a BibTeX/BibLaTeX .bib file, relative to wherever "
                "zensical build/serve (or your own script) is run from - "
                "typically your project root.",
            ],
            "csl_style": [
                "",
                "Path to a Citation Style Language (.csl) file controlling "
                "citation/bibliography formatting (APA, IEEE, Harvard, "
                "Vancouver, and hundreds more - the same open style "
                "ecosystem Zotero/Mendeley/EndNote use). Uses Pandoc's own "
                "default style if unset.",
            ],
            "unresolved": [
                "?",
                "Text rendered by \\cite{id} when id doesn't resolve to a "
                ".bib entry.",
            ],
            "source": [
                "",
                "Identifier for the current document (e.g. its path), used "
                "to build a correct link from a \\cite{id} to \\bibliography's "
                "own page. Auto-detected under Zensical if not set.",
            ],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)
        bib_file: str = self.getConfig("bib_file")
        csl_style: str = self.getConfig("csl_style")
        unresolved: str = self.getConfig("unresolved")
        source: str = self.getConfig("source") or page_source(md) or ""

        cache_key = (bib_file, csl_style)
        if cache_key not in _ZENSICAL_SHARED_CACHES:
            new_cache = _BibliographyCache(bib_file, csl_style)
            new_cache.bibliography_source = find_page_with_marker(BIBLIOGRAPHY_MARKER)
            _ZENSICAL_SHARED_CACHES[cache_key] = new_cache
        cache = share(md, "prodockit_bibliography_cache", _ZENSICAL_SHARED_CACHES[cache_key])

        md.inlinePatterns.register(
            BibCiteInlineProcessor(CITE_RE, md),
            "prodockit-bib-cite",
            44,
        )
        md.inlinePatterns.register(
            BibliographyMarkerInlineProcessor(BIBLIOGRAPHY_RE, md),
            "prodockit-bibliography-marker",
            44,
        )
        md.treeprocessors.register(
            BibliographyResolverTreeprocessor(md, cache, source, unresolved),
            "prodockit-bibliography-resolver",
            1,
        )


def makeExtension(**kwargs: object) -> BibliographyExtension:
    return BibliographyExtension(**kwargs)
