# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from prodockit.pdf.index import (  # noqa: E402
    INDEX_CONTENT_ID,
    build_index_entries,
    extract_term_pages,
    mark_index_terms,
    render_index_content,
)


def _build_test_pdf(path: Path, pages_markers: list[list[str]]) -> None:
    """Builds a real, minimal multi-page PDF with the given marker text on
    each page, via pymupdf's own `insert_htmlbox()` (unlike its simpler
    `insert_text()`, confirmed directly to actually support the
    non-ASCII bracket characters `mark_index_terms()` uses - `insert_text()`
    silently substitutes an unrelated placeholder glyph instead) - avoids
    needing a real WeasyPrint install just to test extract_term_pages()."""
    doc = pymupdf.open()
    for markers in pages_markers:
        page = doc.new_page()
        text = " ".join(f"filler {m} filler" for m in markers) or "filler only"
        page.insert_htmlbox(pymupdf.Rect(20, 20, 500, 200), text)
    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# mark_index_terms
# ---------------------------------------------------------------------------


def test_mark_index_terms_returns_unchanged_html_and_no_terms_when_none_marked() -> None:
    html = "<p>Nothing marked here.</p>"
    result_html, terms = mark_index_terms(html)
    assert terms == []
    assert result_html == html


def test_mark_index_terms_extracts_terms_in_order() -> None:
    html = (
        '<p>A <span class="index">Widget</span> and a '
        '<span class="index">Gadget</span>.</p>'
    )
    _, terms = mark_index_terms(html)
    assert terms == ["Widget", "Gadget"]


def test_mark_index_terms_inserts_a_sequential_marker_after_each_occurrence() -> None:
    html = (
        '<span class="index">Widget</span>'
        '<span class="index">Gadget</span>'
    )
    result_html, _terms = mark_index_terms(html)
    assert "⟦prodockit-index-1⟧" in result_html
    assert "⟦prodockit-index-2⟧" in result_html
    assert result_html.index("⟦prodockit-index-1⟧") < result_html.index("⟦prodockit-index-2⟧")


def test_mark_index_terms_marker_is_near_invisible() -> None:
    html = '<span class="index">Widget</span>'
    result_html, _ = mark_index_terms(html)
    assert "font-size: 0.1pt" in result_html


def test_mark_index_terms_repeated_term_gets_its_own_occurrence_each_time() -> None:
    html = '<span class="index">Widget</span><span class="index">widget</span>'
    _, terms = mark_index_terms(html)
    assert terms == ["Widget", "widget"]


# ---------------------------------------------------------------------------
# extract_term_pages
# ---------------------------------------------------------------------------


def test_extract_term_pages_maps_occurrence_to_the_correct_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"
    _build_test_pdf(
        pdf_path,
        [
            ["⟦prodockit-index-1⟧"],
            [],
            ["⟦prodockit-index-2⟧", "⟦prodockit-index-3⟧"],
        ],
    )

    pages = extract_term_pages(str(pdf_path), 3)

    assert pages == {1: 1, 2: 3, 3: 3}


def test_extract_term_pages_none_for_an_occurrence_not_found(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"
    _build_test_pdf(pdf_path, [["⟦prodockit-index-1⟧"]])

    pages = extract_term_pages(str(pdf_path), 2)

    assert pages == {1: 1, 2: None}


# ---------------------------------------------------------------------------
# build_index_entries
# ---------------------------------------------------------------------------


def test_build_index_entries_groups_case_insensitively_keeping_first_casing() -> None:
    terms = ["Widget", "widget"]
    occurrence_pages = {1: 2, 2: 5}

    entries = build_index_entries(terms, occurrence_pages)

    assert entries == {"Widget": [2, 5]}


def test_build_index_entries_deduplicates_same_page() -> None:
    terms = ["Widget", "Widget"]
    occurrence_pages = {1: 4, 2: 4}

    entries = build_index_entries(terms, occurrence_pages)

    assert entries == {"Widget": [4]}


def test_build_index_entries_sorts_pages_and_alphabetises_terms() -> None:
    terms = ["Zebra", "Apple"]
    occurrence_pages = {1: 9, 2: 3}

    entries = build_index_entries(terms, occurrence_pages)

    assert list(entries.keys()) == ["Apple", "Zebra"]


def test_build_index_entries_drops_occurrences_with_no_resolved_page() -> None:
    terms = ["Widget"]
    occurrence_pages = {1: None}

    entries = build_index_entries(terms, occurrence_pages)

    assert entries == {}


# ---------------------------------------------------------------------------
# render_index_content
# ---------------------------------------------------------------------------


def test_render_index_content_empty_entries_returns_empty_string() -> None:
    assert render_index_content({}) == ""


def test_render_index_content_renders_one_paragraph_per_term() -> None:
    content = render_index_content({"Gadget": [4], "Widget": [1, 3]})
    assert '<p class="prodockit-index-entry">Gadget, 4</p>' in content
    assert '<p class="prodockit-index-entry">Widget, 1, 3</p>' in content


def test_render_index_content_groups_entries_under_a_letter_heading() -> None:
    content = render_index_content({"Apple": [1], "Avocado": [2], "Banana": [3]})
    letter_a = '<h2 class="prodockit-index-letter unnumbered unlisted">A</h2>'
    letter_b = '<h2 class="prodockit-index-letter unnumbered unlisted">B</h2>'
    assert content.index(letter_a) < content.index("Apple")
    assert content.index("Apple") < content.index("Avocado")
    assert content.count(letter_a) == 1
    assert letter_b in content
    assert content.index("Avocado") < content.index(letter_b)


def test_render_index_content_escapes_html_in_term_text() -> None:
    content = render_index_content({"<script>": [1]})
    assert "<script>" not in content
    assert "&lt;script&gt;" in content


def test_index_content_id_is_a_stable_constant() -> None:
    assert INDEX_CONTENT_ID == "prodockit-index-content"
