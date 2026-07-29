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
from typing import Any

import pytest

from prodockit.pdf.index import DEFAULT_INDEX_TITLE, MARKER_ID_PREFIX
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
#: `about/changelog.md`'s own 0.17.0 entry quotes `⟦prodockit-index-N⟧`
#: verbatim (with a literal "N") while explaining the fix, and an earlier
#: entry names the `h2.prodockit-index-letter` CSS class - both are prose
#: about the feature, and both legitimately reach the text layer.
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

#: One term per supported marker shape, pinned so the checks below can't
#: quietly pass against an index that lost whichever shape stopped
#: working. The first five are `index-terms.md`'s own `=== "Result"` tab
#: demos - a flat term, a nested `Parent!Child`, a code-styled
#: `` \index{`git commit`} ``, and a linked `\index{[Git](...)}` (whose
#: entry text is the link's own text). The rest are load-bearing entries
#: from the real index the docs now carry: a code-styled term nested under
#: a plain parent, a multi-word term (which the PDF line-wraps, so it also
#: pins the whitespace normalising below), and a plain top-level term.
EXPECTED_INDEX_TERMS = (
    "gadget",
    "widget",
    "Git",
    "ssh keys",
    "git commit",
    "pdf_include_index",
    "running footer",
    "Pandoc",
)


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


def test_no_page_contains_unrendered_mermaid_source(prodockit_pdf_page_texts):
    """The regression that shipped for real: `extensions/bibliography.md`'s
    architecture diagram reaching the PDF as its own source text."""
    assert_no_unrendered_mermaid(prodockit_pdf_page_texts)


def test_no_page_contains_unrendered_tex_source(prodockit_pdf_page_texts):
    assert_no_unrendered_tex(prodockit_pdf_page_texts)


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
    `pdf_include_index` on in `zensical.toml`, so a missing index page is
    the regression, not a reason to opt out of the checks below.
    """
    for i, text in enumerate(page_texts):
        if text.strip().startswith(title):
            return i
    raise AssertionError(
        f"No page starts with the index title {title!r} - the back-of-book "
        "index is missing from the built PDF. Is extra.pdf_include_index "
        "still set in zensical.toml, and does docs/extensions/index-terms.md "
        "still mark terms live in its '=== \"Result\"' tabs?"
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
    extra = prodockit_resolved_config.get("extra") or {}
    assert extra.get("pdf_include_index"), (
        "extra.pdf_include_index is not set in zensical.toml - the index "
        "checks below would pass vacuously against a PDF that never had an "
        "index to begin with"
    )
    return extra.get("pdf_index_title") or DEFAULT_INDEX_TITLE


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
    for term, pages in _parse_index_entries(index_text):
        needle = " ".join(term.split()).casefold()
        for page in pages:
            # A parent entry ("Git") groups children marked elsewhere, so
            # only its own cited pages are checked - which is all this
            # loop ever sees, a grouping node with no pages of its own
            # rendering with no page list at all.
            if needle not in normalised[page - 1]:
                wrong.append((term, page))
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
