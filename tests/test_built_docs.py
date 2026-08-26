# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Checks this project's own built site and PDF, using the pytest plugin
this project ships.

Everything else under `tests/` exercises the library against synthetic
documents in `tmp_path`. Nothing looked at what `prodockit pdf` actually
produced from `docs/` - which is how the Mermaid diagram in
`extensions/bibliography.md` reached every published PDF as raw
`flowchart LR ...` source until 0.12.0, on the very page documenting how
Mermaid fences are pre-rendered. The build warning added then makes that
visible; these make it fail.

Marked `built` because they need `prodockit pdf` and `zensical build` to
have run. The ordinary unit run deselects them (see pyproject.toml's
`addopts`); `docs.yml` runs them after building. Deselecting rather than
skipping is deliberate - a skip in an unbuilt checkout looks like a pass.

This is also the only place prodockit's own pytest plugin is used against a
real project rather than a synthetic one, so it doubles as a check that the
plugin resolves a real config correctly.
"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import Any

import pytest

from prodockit._zensical import _front_matter_flag, _scan_page_headings
from prodockit.pdf.index import DEFAULT_INDEX_TITLE, MARKER_ID_PREFIX
from prodockit.pdf.site import page_metadata
from prodockit.settings import flatten_nav
from prodockit.testing import assert_no_unrendered_mermaid, assert_no_unrendered_tex

pytestmark = pytest.mark.built

#: Mermaid's default node fill (#ECECFF). Every node shape in a rendered
#: diagram is painted with it, and nothing else in these docs uses it, so it
#: distinguishes a real diagram from ordinary page furniture - unlike
#: `page.get_drawings()` being non-empty, which is true of every page.
MERMAID_NODE_FILL = (0.925, 0.925, 1.0)
FILL_TOLERANCE = 0.02

#: The two shapes a leaked index marker can take in the text layer: the
#: current design's marker `id` (`prodockit-index-mark-N`, which reaches
#: the PDF only as a named destination, never as text) and the literal
#: `⟦prodockit-index-N⟧` token the pre-0.17.0 design deposited next to
#: every marked term (prodockit-extensions#133).
#:
#: Both require a real digit, and that is load-bearing here rather than
#: incidental: the equivalent synthetic test in `test_pdf_build.py` can
#: assert the far blunter `"prodockit-index" not in full_text`, but these
#: docs would fail that check while being entirely correct.
#: Generated examples may legitimately quote `⟦prodockit-index-N⟧`
#: verbatim (with a literal "N") or name the
#: `h2.prodockit-index-letter` CSS class. Both are prose about the feature
#: and legitimately reach the text layer.
INDEX_MARKER_LEAK_PATTERNS = (
    re.compile(re.escape(MARKER_ID_PREFIX) + r"\d+"),
    re.compile(r"⟦\s*prodockit-index-\d+\s*⟧"),
)

#: One rendered index entry line: the term, then its page list -
#: `format_pages()`'s own output, so a single page ("widget, 49"), an
#: en-dash range of consecutive pages ("Widget, 67–70"), or a
#: comma-separated mix of both ("staging area, 64, 175"). Anchored at both
#: ends so the running header/footer sharing the index page ("Page 119 of
#: 119", the copyright line) can't be mistaken for an entry.
INDEX_ENTRY_RE = re.compile(
    r"^(?P<term>\S.*?)\s*,\s*"
    r"(?P<pages>\d+(?:\s*[–-]\s*\d+)?(?:\s*,\s*\d+(?:\s*[–-]\s*\d+)?)*)$"
)

#: Load-bearing entries from the real documentation index, selected across
#: flat, nested, code-styled, multi-word, command, configuration, and platform
#: terms. Demonstration-only Result panes are deliberately excluded so the
#: book index remains useful to a reader.
EXPECTED_INDEX_TERMS = (
    "prodockit pdf",
    "DYLD_FALLBACK_LIBRARY_PATH",
    "PyMdown Blocks",
    "width",
    "include",
    "running footer",
    "Pandoc",
)

#: A numbered chapter in the PDF's bookmark outline - "4. Refs". The cover,
#: "Table of Contents" and the generated index are level-1 outline entries
#: too, but carry no number, which is what separates them here.
OUTLINE_CHAPTER_RE = re.compile(r"^\d+\.\s+\S")

#: `prodockit.headings`' own `appendix_attr` default - the front matter flag
#: naming a page that gets a letter ("Appendix A") rather than a number, and
#: so sits outside the numbered sequence checked below.
APPENDIX_ATTR = "is_appendix"


def _mermaid_node_shapes(page):
    shapes = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if fill and all(
            abs(channel - expected) <= FILL_TOLERANCE
            for channel, expected in zip(fill, MERMAID_NODE_FILL, strict=False)
        ):
            shapes.append(drawing)
    return shapes


def test_the_pdf_built_and_has_pages(prodockit_pdf):
    assert prodockit_pdf.page_count > 5


@pytest.fixture(scope="session")
def documents_own_chapters(prodockit_paths, prodockit_resolved_config) -> list[str]:
    """Each nav page's own first numbered h1, in nav order - what the PDF's
    chapters *should* be, read from the markdown rather than from the PDF.

    Scanned with `prodockit.headings`' own `_scan_page_headings()`, the
    scanner that drives the website's continuous numbering, so a mismatch
    against the PDF means the two pipelines disagree about what a chapter
    is - not that this test picked a different rule.

    The cover page is excluded because `prodockit.pdf` forces every heading
    on it unnumbered (see `prodockit.pdf.html.fix_page_html`), and an
    appendix because it is lettered instead of numbered. A page carrying
    `pdf_include: false` is website-only and therefore not a PDF chapter.
    """
    chapters = []
    for page_position, page in enumerate(flatten_nav(prodockit_resolved_config.get("nav") or [])):
        if page_position == 0 and page.get("is_index"):
            continue
        source = prodockit_paths.docs_dir / page["url"]
        text = source.read_text(encoding="utf-8")
        if page_metadata(source).get("pdf_include", True) is False:
            continue
        if _front_matter_flag(text, APPENDIX_ATTR):
            continue
        first_h1 = next(
            (
                title
                for level, title, _, unnumbered in _scan_page_headings(text)
                if level == 1 and not unnumbered
            ),
            None,
        )
        if first_h1 is not None:
            chapters.append(first_h1)
    return chapters


def test_the_pdf_outline_lists_the_documents_own_chapters_and_nothing_else(
    prodockit_pdf, documents_own_chapters
):
    """A heading that isn't this document's structure must not reach the
    PDF's bookmark outline as a chapter.

    The regression that shipped for real: `extensions/refs.md` illustrates
    `\\ref{}` by showing its real rendered output, which on that page means
    real `<h1>`/`<h2>` elements. Pandoc numbered that example `<h1>` as a
    chapter of its own, so every later chapter was renumbered one too high
    and the page's own sections nested under the example instead of under
    the page.

    Neither half of that is caught by looking at the outline alone - the
    numbering stays internally consistent, just wrong - so this compares it
    against the markdown, and asserts on the whole span from the first
    numbered chapter to the last rather than on the numbered entries
    within it: an example heading marked `.unnumbered` but still bookmarked
    would otherwise slip through the gaps between chapters unnoticed, while
    still swallowing the sections that follow it.
    """
    level_one = [title for level, title, _ in prodockit_pdf.get_toc() if level == 1]
    numbered = [i for i, title in enumerate(level_one) if OUTLINE_CHAPTER_RE.match(title)]
    assert numbered, f"No numbered chapter in the PDF outline at all: {level_one}"

    expected = [f"{n}. {title}" for n, title in enumerate(documents_own_chapters, 1)]
    assert level_one[numbered[0] : numbered[-1] + 1] == expected


def test_no_page_contains_unrendered_mermaid_source(prodockit_pdf_page_texts):
    """The regression that shipped for real: `extensions/bibliography.md`'s
    architecture diagram reaching the PDF as its own source text."""
    assert_no_unrendered_mermaid(prodockit_pdf_page_texts)


def test_no_page_contains_unrendered_tex_source(prodockit_pdf_page_texts):
    assert_no_unrendered_tex(prodockit_pdf_page_texts)


def test_code_blocks_kept_their_preformatted_layout(prodockit_pdf):
    """A code block that lost its `<pre>` reflows as justified prose, and
    the giveaway in the finished PDF is a hole between two monospace
    glyphs that are adjacent in the text flow - justification padding a
    word gap that a fixed-pitch font should never have
    (prodockit-extensions#207).

    Guards the built artefact rather than the intermediate HTML: the unit
    test in test_pdf_html.py fixes the shape handed to Pandoc, but only
    this notices if some later stage undoes it again.
    """
    offenders = []
    for pno in range(prodockit_pdf.page_count):
        for block in prodockit_pdf[pno].get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                chars = [(c, s) for s in line["spans"] for c in s["chars"]]
                for (c1, s1), (c2, s2) in pairwise(chars):
                    if "Mono" not in s1["font"] or "Mono" not in s2["font"]:
                        continue
                    if s1["size"] != s2["size"]:
                        continue
                    gap = c2["bbox"][0] - c1["bbox"][2]
                    # JetBrains Mono advances 0.6em; half of one is far
                    # more than kerning noise and far less than a space.
                    if gap > s1["size"] * 0.6 * 0.5:
                        text = "".join(c["c"] for c, _ in chars)
                        offenders.append(
                            f"page {pno + 1}: {gap:.1f}pt after {c1['c']!r} in {text[:60]!r}"
                        )
    assert not offenders, "monospace runs with justification holes:\n" + "\n".join(offenders[:10])


def test_the_architecture_diagram_actually_rendered(prodockit_pdf):
    """The counterpart to the check above, which would still pass if the
    diagram vanished from the PDF entirely rather than reaching it as text.

    Asserts on Mermaid's own node fill rather than the presence of any
    vector content: every page has drawings (headers, rules), so a
    non-empty `get_drawings()` proves nothing.
    """
    total = sum(len(_mermaid_node_shapes(page)) for page in prodockit_pdf)
    assert total > 0, (
        "No shape in the PDF is filled with Mermaid's node colour - the "
        "diagram in extensions/bibliography.md did not render"
    )


def _index_page_index(page_texts: list[str], title: str) -> int:
    """The 0-based position of the generated index page in `page_texts`.

    Fails rather than skips if it isn't there: this project turns
    `prodockit.index`'s `include` setting on in `zensical.toml`, so a missing index page is
    the regression, not a reason to opt out of the checks below.

    Matched on the page's whole first *line*, and searched from the back.
    `startswith(title)` was neither, and both halves of that were wrong for
    the same reason: the index title is an ordinary English word, so any
    page whose text merely begins with something spelled like it matched
    first and won. `docs/pdf.md`'s API reference for `IndexEntry` did
    exactly that once a page break happened to fall in front of it, since
    `"IndexEntry(...".startswith("Index")` is true. Every page from there
    to the end was then read as index entries, parsing code samples into
    terms and page numbers that pointed past the end of the document
    (prodockit-extensions#186).

    Searching backwards is the safer direction on its own terms:
    `prodockit.pdf.index` places the generated index last precisely so its
    own length cannot shift the page numbers it records, so the last match
    is the right one even if an earlier page ever legitimately opens with
    the same word.
    """
    for i in range(len(page_texts) - 1, -1, -1):
        lines = page_texts[i].strip().splitlines()
        if lines and lines[0].strip() == title:
            return i
    raise AssertionError(
        f"No page begins with the index title {title!r} on a line of its own "
        "- the back-of-book index is missing from the built PDF. Is "
        "prodockit.index include=true still set in zensical.toml, and does "
        "docs/extensions/index-terms.md still mark terms live in its "
        "'=== \"Result\"' tabs?"
    )


def _index_page_texts(page_texts: list[str], title: str) -> list[str]:
    """Every page of the generated index, not just the first.

    The index is always the last thing in the document (see
    `prodockit.pdf.index` for why that position is load-bearing), so it
    runs from its title page to the end. Reading only the first page
    silently under-checks as soon as the index outgrows one page - which
    it did the moment this project marked more than a handful of terms.
    """
    return page_texts[_index_page_index(page_texts, title) :]


def _parse_index_entries(index_text: str) -> list[tuple[str, list[int]]]:
    """Every `("term", [pages])` in the rendered index, ranges expanded
    to the individual pages they stand for (`format_pages()` only ever
    collapses genuinely consecutive pages into a range, so every page in
    one really does carry the term)."""
    # A long entry wraps in the two-column layout, putting its page list on
    # the next extracted line ("pdf_header_footer_font_size ,\n57"). Rejoin
    # those first - otherwise exactly the longest, most breakable entries
    # are the ones silently skipped.
    lines: list[str] = []
    for raw in index_text.split("\n"):
        line = raw.strip()
        if lines and lines[-1].endswith(",") and re.fullmatch(r"[\d,\s–-]+", line):
            lines[-1] += " " + line
        else:
            lines.append(line)

    entries = []
    for line in lines:
        match = INDEX_ENTRY_RE.match(line.strip())
        if not match:
            continue
        pages: list[int] = []
        for part in match["pages"].split(","):
            bounds = [int(n) for n in re.findall(r"\d+", part)]
            pages.extend(range(bounds[0], bounds[-1] + 1))
        entries.append((match["term"].strip(), pages))
    return entries


@pytest.fixture(scope="session")
def index_title(prodockit_resolved_config: dict[str, Any]) -> str:
    index_config = (prodockit_resolved_config.get("mdx_configs") or {}).get("prodockit.index") or {}
    assert index_config.get("include"), (
        "prodockit.index include=true is not set in zensical.toml - the index "
        "checks below would pass vacuously against a PDF that never had an "
        "index to begin with"
    )
    return index_config.get("title") or DEFAULT_INDEX_TITLE


def test_index_markers_leave_no_trace_in_the_pdf_text_layer(prodockit_pdf_page_texts):
    """prodockit-extensions#133: every `\\index{Term}` used to deposit a
    `⟦prodockit-index-N⟧` token beside the word it marked - invisible on
    the page, but real text in the file, so it surfaced in copy and
    paste, in the reader's own search, in text extraction and, worst, in
    screen readers, mid-sentence. (67 of them in the separate User Guide
    that found this; six here, one per marker in `index-terms.md`.)

    `test_pdf_build.py` covers this against a synthetic document, but only
    behind `real_pandoc_and_weasyprint_required` - so it is deselected in
    the CI `test` job, which installs neither, and the shipped fix has no
    permanent guard there. This is that guard: `docs.yml` has already run
    a real `prodockit pdf` by the time these run.
    """
    leaked = []
    for page_number, text in enumerate(prodockit_pdf_page_texts, start=1):
        for pattern in INDEX_MARKER_LEAK_PATTERNS:
            leaked += [(page_number, match.group(0)) for match in pattern.finditer(text)]
    assert not leaked, f"Index markers reached the PDF's text layer: {leaked}"


def test_the_back_of_book_index_was_generated(prodockit_pdf_page_texts, index_title):
    """The other half of the check above, which deleting the markers
    outright would satisfy on its own while destroying the feature."""
    index_text = "\n".join(_index_page_texts(prodockit_pdf_page_texts, index_title))
    entries = _parse_index_entries(index_text)
    assert entries, "The index page was generated but lists no entries at all"

    found = {term.casefold() for term, _ in entries}
    missing = [term for term in EXPECTED_INDEX_TERMS if term.casefold() not in found]
    assert not missing, (
        f"Marked terms missing from the generated index: {missing} (found {sorted(found)})"
    )


def test_every_index_entry_cites_a_page_containing_its_term(prodockit_pdf_page_texts, index_title):
    """Each entry's page number must be the page the term is actually
    marked on - the half of the fix that a marker resolving to the wrong
    named destination, or to none at all, would break silently.

    The index cites printed page numbers, which in this document match
    PDF page order 1:1 (the cover is page 1, no roman-numbered front
    matter) - asserted below rather than assumed.
    """
    index_page = _index_page_index(prodockit_pdf_page_texts, index_title)
    assert (
        prodockit_pdf_page_texts[index_page]
        .rstrip()
        .endswith(f"Page {index_page + 1} of {len(prodockit_pdf_page_texts)}")
    ), "Printed page numbers no longer match PDF page order - this check's page lookup is invalid"

    index_text = "\n".join(_index_page_texts(prodockit_pdf_page_texts, index_title))
    # A multi-word term is line-wrapped wherever it happens to fall ("the
    # PDF's running\nfooter"), so compare on whitespace-normalised text -
    # otherwise every such entry looks like a wrong page number.
    normalised = [" ".join(text.split()).casefold() for text in prodockit_pdf_page_texts]

    wrong = []
    off_the_end = []
    for term, pages in _parse_index_entries(index_text):
        needle = " ".join(term.split()).casefold()
        for page in pages:
            # A parent entry ("Git") groups children marked elsewhere, so
            # only its own cited pages are checked - which is all this
            # loop ever sees, a grouping node with no pages of its own
            # rendering with no page list at all.
            #
            # Bounds-checked rather than indexed straight into: an entry
            # citing a page the document does not have used to surface as a
            # bare IndexError from this line, saying nothing about which
            # entry or why. That is exactly how #186 presented - the real
            # fault being that _index_page_index had picked the wrong page,
            # so ordinary prose was being parsed as entries - and the
            # traceback pointed here rather than at the cause.
            if not 1 <= page <= len(normalised):
                off_the_end.append((term, page))
            elif needle not in normalised[page - 1]:
                wrong.append((term, page))
    assert not off_the_end, (
        f"Index entries cite a page outside the document (it has "
        f"{len(normalised)} pages): {off_the_end} - most likely the index "
        "itself was not located correctly, so ordinary prose is being read "
        "as index entries"
    )
    assert not wrong, (
        "Index entries cite a page that doesn't contain the term: "
        f"{wrong} - the marker resolved to the wrong page"
    )


def test_the_site_built(prodockit_site_dir, prodockit_site_html_files):
    assert (prodockit_site_dir / "index.html").is_file()
    assert len(prodockit_site_html_files) > 5


def test_every_nav_page_reached_the_site(prodockit_nav_pages, prodockit_site_dir):
    """A nav entry that silently failed to build would otherwise only show up
    as a 404 on the published site."""
    missing = []
    for page in prodockit_nav_pages:
        stem = page.removesuffix(".md")
        candidates = [
            prodockit_site_dir / f"{stem}.html",
            prodockit_site_dir / stem / "index.html",
        ]
        if stem == "index":
            candidates.append(prodockit_site_dir / "index.html")
        if not any(candidate.is_file() for candidate in candidates):
            missing.append(page)
    assert not missing, f"Nav pages missing from the built site: {missing}"
