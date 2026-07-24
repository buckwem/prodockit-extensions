# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

r"""prodockit.bibliography: a BibTeX/BibLaTeX ``.bib`` file as the single
source of truth for a document's references, formatted via any Citation
Style Language (CSL) style - APA, IEEE, Harvard, Vancouver, and hundreds
more, the same open, actively-maintained style ecosystem Zotero/Mendeley/
EndNote already use.

An alternative to :mod:`prodockit.citations`, covering the same job a
different way - rather than a hand-authored ``data-cite-text`` paragraph
elsewhere in the document (you write the formatted reference-list entry
yourself, once, by hand), prodockit.bibliography resolves against
structured bibliographic data in a ``.bib`` file and generates the
formatted entry - inline citation and reference-list entry alike - for
you.

Uses its own ``\citebib{id}`` syntax, deliberately distinct from
prodockit.citations' ``\cite{id}`` - both extensions can be enabled in the
same build without conflict (e.g. this project's own docs, demonstrating
both side by side), even though a typical single project only needs one
workflow or the other.

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

Only single-key ``\citebib{id}`` is supported (not
prodockit.citations' ``\cite{id1,id2,...}``) - Pandoc's own multi-source
citation formatting (``[@id1; @id2]``) returns one joined, opaque string
per CSL style's own rules for how to combine them, which can't be reliably
split back into individually-linkable pieces afterward. A multi-key
`\citebib{...}` is therefore left completely unmatched by this extension's
own syntax (falls through as literal text) rather than silently mishandled.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as etree
from functools import cache
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from markdown import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor

from prodockit._zensical import page_source, prescan_bibliography, share
from prodockit.util import cross_page_href

CITE_RE = r"\\citebib\{([^}\s,]+)\}"
BIBLIOGRAPHY_RE = r"\\bibliography(?!\w)(?:\{([^{}]*)\})?(?:\{(true|false)\})?"

_NOT_FOUND_RE = re.compile(r"citeproc: citation (\S+) not found", re.IGNORECASE)
_BIB_ENTRY_KEY_RE = re.compile(r"^@\w+\{\s*([^,\s]+)\s*,", re.MULTILINE)


@cache
def _bib_file_keys(path: str) -> frozenset[str]:
    """Returns the set of entry keys defined in a `.bib` file, via a plain
    regex over its raw text - not a BibTeX/CSL reimplementation, just
    "does this file define key X", which is all that's needed to know
    which specific file's marker a `\\citebib{id}` should cross-link to,
    and to correctly scope a `cited_only=True` marker to just its own
    file's entries (see _BibliographyCache.bibliography_html). Actual
    citation/bibliography *formatting* is still delegated entirely to
    `pandoc --citeproc` - this never touches formatting, only key
    discovery. Returns an empty set if `path` can't be read.

    Memoized for the lifetime of the process (a `.bib` file doesn't change
    mid-build) - called once per distinct file rather than once per
    citation/marker, since a real build may resolve many citations against
    the same file."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    return frozenset(m.group(1) for m in _BIB_ENTRY_KEY_RE.finditer(text))


class BibliographyError(RuntimeError):
    """Raised when the underlying `pandoc` invocation fails, or isn't
    found on `PATH` at all."""


class _BibliographyCache:
    """Per-(default bib_file, csl_style) cache of Pandoc-formatted output,
    shared across every page of a single Zensical build (one Python
    process per `zensical build`/`zensical serve` invocation - see
    prodockit._zensical) - a `.bib` file's entries are all defined once,
    centrally, unlike prodockit.citations'/prodockit.glossary's
    per-page-scanned definitions, so there's no cross-page
    registry-merging problem to solve here, just a cache to avoid
    re-running `pandoc` for the same key/file/mode twice.

    A build may reference more than one distinct `.bib` file - each
    `\\bibliography{file}{...}` marker can name its own - so a single
    `\\citebib{id}` needs to resolve against the *union* of every distinct
    file referenced anywhere (`all_bib_files`), while each individual
    marker's own generated list (`bibliography_html`) is scoped to just
    its own one file.
    """

    def __init__(self, default_bib_file: str, csl_style: str) -> None:
        self.default_bib_file = default_bib_file
        self.csl_style = csl_style
        self._citations: dict[str, tuple[str, bool]] = {}
        self._bibliography_html: dict[tuple[str, bool], str] = {}
        # Populated once, up front, from _zensical.prescan_bibliography() -
        # see BibliographyExtension.extendMarkdown.
        self.all_bib_files: list[str] = [default_bib_file]
        self.all_cited_keys: set[str] = set()
        self.first_page_for_file: dict[str, str] = {}

    def resolve_citation(self, key: str) -> tuple[str, bool]:
        """Returns (formatted_inline_html, resolved) for one citation key,
        running `pandoc` once per distinct key (searching every distinct
        `.bib` file referenced anywhere in the build, so `key` resolves
        regardless of which specific marker/page it'll end up cross-linked
        to) and caching the result for the rest of this build."""
        if key not in self._citations:
            stdout, stderr = _run_pandoc_citeproc(
                f"[@{key}]\n", bib_files=self.all_bib_files, csl_style=self.csl_style
            )
            resolved = not _NOT_FOUND_RE.search(stderr)
            soup = BeautifulSoup(stdout, "html.parser")
            span = soup.find("span", class_="citation")
            inner_html = span.decode_contents() if isinstance(span, Tag) else stdout.strip()
            self._citations[key] = (inner_html, resolved)
        return self._citations[key]

    def bibliography_html(self, bib_file: str, cited_only: bool) -> str:
        """Returns the complete, formatted `<div id="refs">` bibliography
        list for one `\\bibliography{bib_file}{cited_only}` marker,
        memoized per (bib_file, cited_only) pair for the rest of this
        build.

        `cited_only=False` (the default, and the only mode before this
        marker gained parameters): every entry in `bib_file`, via Pandoc's
        own `nocite: '@*'` metadata, the same "include every entry
        regardless of whether it's actually cited" idiom LaTeX's
        `\\nocite{*}` provides.

        `cited_only=True`: only entries in `bib_file` that were also
        actually `\\citebib{}`-cited somewhere in this build
        (`self.all_cited_keys`, from the nav pre-scan) - built as one
        `[@key]` citation per matching key and handed to Pandoc with *no*
        `nocite` front matter at all, so its own normal citeproc behaviour
        (only cite what's actually in the body) does the filtering -
        reusing the exact same `_run_pandoc_citeproc` call as an
        individual citation, not a new code path."""
        cache_key = (bib_file, cited_only)
        if cache_key not in self._bibliography_html:
            if cited_only:
                keys = sorted(self.all_cited_keys & _bib_file_keys(bib_file))
                body = "".join(f"[@{key}]\n\n" for key in keys)
                stdout, _ = _run_pandoc_citeproc(
                    body, bib_files=[bib_file], csl_style=self.csl_style
                )
            else:
                stdout, _ = _run_pandoc_citeproc(
                    "", bib_files=[bib_file], csl_style=self.csl_style,
                    front_matter="---\nnocite: '@*'\n---\n\n",
                )
            soup = BeautifulSoup(stdout, "html.parser")
            refs_div = soup.find("div", id="refs")
            if not isinstance(refs_div, Tag):
                html = ""
            else:
                for entry in refs_div.find_all("div", class_="csl-entry"):
                    classes = entry.get("class", [])
                    if "reference" not in classes:
                        entry["class"] = [*classes, "reference"]
                html = str(refs_div)
            self._bibliography_html[cache_key] = html
        return self._bibliography_html[cache_key]


# Shared across every page of a single Zensical build - see prodockit._zensical
# and BibliographyExtension.extendMarkdown. Keyed by (default bib_file,
# csl_style) so two differently-configured instances (unusual, but not
# prevented) don't share a cache that doesn't apply to both.
_ZENSICAL_SHARED_CACHES: dict[tuple[str, str], _BibliographyCache] = {}



def _run_pandoc_citeproc(
    body: str, *, bib_files: list[str], csl_style: str, front_matter: str = ""
) -> tuple[str, str]:
    """Runs `pandoc --citeproc` over `front_matter + body` (Pandoc's own
    markdown citation syntax, e.g. `[@key]`), returning (stdout, stderr) as
    HTML/diagnostic text. `bib_files` may name more than one `.bib` file -
    Pandoc merges repeated `--bibliography=` flags natively. Raises
    `BibliographyError` if `pandoc` isn't on `PATH` at all, or if it exits
    non-zero (an unresolved citation key is *not* a non-zero exit - see
    module docstring - only a genuinely broken invocation is, e.g. a
    malformed `.bib` file)."""
    if shutil.which("pandoc") is None:
        raise BibliographyError(
            "pandoc not found on PATH - prodockit.bibliography formats citations "
            "and bibliography entries via `pandoc --citeproc`, the same tool "
            "prodockit.pdf already needs (see https://pandoc.org/installing.html) "
            "- required here even for a website-only build with no PDF."
        )
    cmd = ["pandoc", "-f", "markdown", "-t", "html", "--citeproc"]
    cmd += [f"--bibliography={bib_file}" for bib_file in bib_files]
    if csl_style:
        cmd.append(f"--csl={csl_style}")
    result = subprocess.run(cmd, input=front_matter + body, capture_output=True, text=True)
    if result.returncode != 0:
        raise BibliographyError(
            f"pandoc exited with status {result.returncode} formatting a "
            f"citation/bibliography (bib_files={bib_files!r}): {result.stderr}"
        )
    return result.stdout, result.stderr


class BibCiteInlineProcessor(InlineProcessor):
    """Matches `\\citebib{id}` (a single key only - see module docstring) and
    emits an unresolved placeholder `<span>` carrying the key in a
    `data-prodockit-bib-cite` attribute.

    Registered at a low inline-pattern priority so it runs after 'backtick'
    (190) and 'escape' (180) - meaning inline code spans are already
    stashed out of reach by the time this pattern runs, so `\\citebib{...}`
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
    """Matches a `\\bibliography`/`\\bibliography{file.bib}`/
    `\\bibliography{file.bib}{true|false}` marker and emits an empty
    placeholder `<span>` carrying the (optional) file/cited-only
    parameters as attributes, resolved by
    BibliographyResolverTreeprocessor into the complete, formatted
    reference list. Put it on its own paragraph/line - the resolver
    replaces that whole paragraph, not just this inline placeholder, once
    resolved."""

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        el = etree.Element("span")
        el.set("data-prodockit-bibliography-file", (m.group(1) or "").strip())
        el.set("data-prodockit-bibliography-cited-only", m.group(2) or "false")
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
        # Same-page fallback: if this page's own tree contains a
        # \bibliography{...} marker for a given file, treat this page as
        # that file's link target even if the nav pre-scan didn't already
        # find one - covers both a marker/citation sharing one page (nav
        # order would find this page anyway) and plain, non-Zensical usage
        # (no nav to pre-scan at all, so first_page_for_file starts empty).
        # setdefault() never overrides an already-prescanned entry, so the
        # real "first page in nav order" answer still wins when one exists.
        for el in root.iter():
            if el.get("data-prodockit-bibliography-file") is not None:
                file = el.get("data-prodockit-bibliography-file") or self.cache.default_bib_file
                self.cache.first_page_for_file.setdefault(file, self.source)

        # Built once up front (etree.Element has no parent pointers) -
        # needed for the bibliography-marker case below, which may have to
        # remove the marker's own *parent*, not just the marker itself.
        parent_map = {child: parent for parent in root.iter() for child in parent}

        for el in list(root.iter()):
            if el.get("data-prodockit-bib-cite") is not None:
                self._resolve_citation(el)
            elif el.get("data-prodockit-bibliography-file") is not None:
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

        bib_file = marker.get("data-prodockit-bibliography-file") or self.cache.default_bib_file
        cited_only = marker.get("data-prodockit-bibliography-cited-only") == "true"
        html = self.cache.bibliography_html(bib_file, cited_only)
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
        target_page = self._link_target_for_key(key)
        if target_page is not None:
            href = cross_page_href(target_page, self.source, f"ref-{key}")
            link = etree.Element("a", href=href)
            link.text = el.text
            el.text = None
            for child in list(el):
                el.remove(child)
                link.append(child)
            el.append(link)

    def _link_target_for_key(self, key: str) -> str | None:
        """Which page's `\\bibliography{...}` marker actually lists `key`'s
        entry - determined by which distinct `.bib` file defines `key`
        (checking every file referenced anywhere in the build), since
        that's the file whose marker page is guaranteed to include it. In
        the common single-file build there's only one distinct file, so
        this always picks the one page with a `\\bibliography` marker,
        exactly matching this extension's original, single-file-only
        behaviour."""
        for bib_file in self.cache.all_bib_files:
            if key in _bib_file_keys(bib_file):
                page = self.cache.first_page_for_file.get(bib_file)
                if page is not None:
                    return page
        return None


class BibliographyExtension(Extension):
    """Python-Markdown extension resolving `.bib`-backed `\\citebib{id}`
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
                "Text rendered by \\citebib{id} when id doesn't resolve to a "
                ".bib entry.",
            ],
            "source": [
                "",
                "Identifier for the current document (e.g. its path), used "
                "to build a correct link from a \\citebib{id} to \\bibliography's "
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
            prescanned = prescan_bibliography(CITE_RE, BIBLIOGRAPHY_RE, bib_file)
            if prescanned is not None:
                all_cited_keys, first_page_for_file = prescanned
                new_cache.all_cited_keys = all_cited_keys
                new_cache.first_page_for_file = first_page_for_file
                new_cache.all_bib_files = sorted({bib_file, *first_page_for_file})
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
