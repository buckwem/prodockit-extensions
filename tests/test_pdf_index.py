# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from prodockit.pdf.index import (  # noqa: E402
    INDEX_CONTENT_ID,
    IndexEntry,
    build_index_entries,
    extract_term_pages,
    format_pages,
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
    result_html, terms, code_flags = mark_index_terms(html)
    assert terms == []
    assert code_flags == []
    assert result_html == html


def test_mark_index_terms_extracts_terms_in_order() -> None:
    html = (
        '<p>A <span class="index">Widget</span> and a '
        '<span class="index">Gadget</span>.</p>'
    )
    _, terms, _code_flags = mark_index_terms(html)
    assert terms == ["Widget", "Gadget"]


def test_mark_index_terms_inserts_a_sequential_marker_after_each_occurrence() -> None:
    html = (
        '<span class="index">Widget</span>'
        '<span class="index">Gadget</span>'
    )
    result_html, _terms, _code_flags = mark_index_terms(html)
    assert "⟦prodockit-index-1⟧" in result_html
    assert "⟦prodockit-index-2⟧" in result_html
    assert result_html.index("⟦prodockit-index-1⟧") < result_html.index("⟦prodockit-index-2⟧")


def test_mark_index_terms_marker_is_near_invisible() -> None:
    html = '<span class="index">Widget</span>'
    result_html, _, _code_flags = mark_index_terms(html)
    assert "font-size: 0.1pt" in result_html


def test_mark_index_terms_repeated_term_gets_its_own_occurrence_each_time() -> None:
    html = '<span class="index">Widget</span><span class="index">widget</span>'
    _, terms, _code_flags = mark_index_terms(html)
    assert terms == ["Widget", "widget"]


def test_mark_index_terms_reads_the_full_path_from_data_index_term() -> None:
    html = '<span class="index" data-index-term="Git!ssh keys">ssh keys</span>'
    _, terms, _code_flags = mark_index_terms(html)
    assert terms == ["Git!ssh keys"]


def test_mark_index_terms_reads_the_code_flag() -> None:
    html = (
        '<span class="index" data-index-code="true" data-index-term="git commit">'
        "<code>git commit</code></span>"
        '<span class="index">Widget</span>'
    )
    _, terms, code_flags = mark_index_terms(html)
    assert terms == ["git commit", "Widget"]
    assert code_flags == [True, False]


def test_mark_index_terms_extracts_plain_text_from_a_term_containing_a_link() -> None:
    """A markdown link inside \\index{} (see prodockit.index) resolves to a
    real <a> - get_text() (the fallback for a flat term with no
    data-index-term attribute) already strips it correctly, the same way
    it already strips <em>/<code>."""
    html = '<span class="index"><a href="https://git-scm.com/">Git</a></span>'
    _, terms, _code_flags = mark_index_terms(html)
    assert terms == ["Git"]


def test_mark_index_terms_finds_a_term_nested_inside_an_admonition() -> None:
    """An admonition wraps its content in a <div class="admonition"> - a
    plain find_all("span", class_="index") reaches into it regardless of
    ancestor nesting, so this needs no special-casing (unlike, say, a
    heading's own text - see build_pdf()'s own TOC/Index title handling)."""
    html = (
        '<div class="admonition note">'
        '<p class="admonition-title">Note</p>'
        '<p>This mentions <span class="index">Widget</span> inside an admonition.</p>'
        "</div>"
    )
    _, terms, _code_flags = mark_index_terms(html)
    assert terms == ["Widget"]


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
# format_pages
# ---------------------------------------------------------------------------


def test_format_pages_empty_list_returns_empty_string() -> None:
    assert format_pages([]) == ""


def test_format_pages_single_page() -> None:
    assert format_pages([4]) == "4"


def test_format_pages_non_consecutive_pages_are_comma_separated() -> None:
    assert format_pages([64, 175]) == "64, 175"


def test_format_pages_consecutive_pages_collapse_to_an_en_dash_range() -> None:
    assert format_pages([67, 68, 69, 70]) == "67–70"


def test_format_pages_two_consecutive_pages_still_collapse_to_a_range() -> None:
    assert format_pages([27, 28]) == "27–28"


def test_format_pages_mixes_ranges_and_singles() -> None:
    assert format_pages([1, 2, 3, 5, 7, 8, 9]) == "1–3, 5, 7–9"


def test_format_pages_deduplicates_and_sorts() -> None:
    assert format_pages([5, 3, 3, 4]) == "3–5"


# ---------------------------------------------------------------------------
# build_index_entries
# ---------------------------------------------------------------------------


def test_build_index_entries_groups_case_insensitively_keeping_first_casing() -> None:
    terms = ["Widget", "widget"]
    occurrence_pages = {1: 2, 2: 5}

    entries = build_index_entries(terms, occurrence_pages)

    assert list(entries.values()) == [IndexEntry("Widget", [2, 5], {})]


def test_build_index_entries_deduplicates_same_page() -> None:
    terms = ["Widget", "Widget"]
    occurrence_pages = {1: 4, 2: 4}

    entries = build_index_entries(terms, occurrence_pages)

    assert list(entries.values()) == [IndexEntry("Widget", [4], {})]


def test_build_index_entries_sorts_pages_and_alphabetises_terms() -> None:
    terms = ["Zebra", "Apple"]
    occurrence_pages = {1: 9, 2: 3}

    entries = build_index_entries(terms, occurrence_pages)

    assert [entry.display for entry in entries.values()] == ["Apple", "Zebra"]


def test_build_index_entries_drops_occurrences_with_no_resolved_page() -> None:
    terms = ["Widget"]
    occurrence_pages = {1: None}

    entries = build_index_entries(terms, occurrence_pages)

    assert entries == {}


def test_build_index_entries_alphabetises_ignoring_leading_punctuation() -> None:
    terms = ["--set-upstream option (git push)", "-u option (git branch)", "SSH"]
    occurrence_pages = {1: 242, 2: 148, 3: 89}

    entries = build_index_entries(terms, occurrence_pages)

    # "-u option..." sorts under U (before "--set-upstream..." under S is
    # wrong here - S < U), so alphabetical order once dashes are ignored is
    # "--set-upstream option..." (s), "SSH" (s), "-u option..." (u).
    assert [entry.display for entry in entries.values()] == [
        "--set-upstream option (git push)",
        "SSH",
        "-u option (git branch)",
    ]


def test_build_index_entries_builds_a_nested_tree_from_bang_separated_paths() -> None:
    terms = ["Staging area", "Staging area!files!adding", "Staging area!files!modified"]
    occurrence_pages = {1: 27, 2: 36, 3: 205}

    entries = build_index_entries(terms, occurrence_pages)

    staging_area = entries["staging area"]
    assert staging_area.display == "Staging area"
    assert staging_area.pages == [27]
    files = staging_area.children["files"]
    assert files.display == "files"
    assert files.pages == []  # a pure grouping node - no page of its own
    assert [entry.display for entry in files.children.values()] == ["adding", "modified"]
    assert files.children["adding"].pages == [36]
    assert files.children["modified"].pages == [205]


def test_build_index_entries_merges_repeated_hierarchical_paths() -> None:
    terms = ["Git!ssh keys", "Git!ssh keys"]
    occurrence_pages = {1: 13, 2: 89}

    entries = build_index_entries(terms, occurrence_pages)

    git = entries["git"]
    assert git.pages == []
    assert git.children["ssh keys"].pages == [13, 89]


def test_build_index_entries_defaults_code_to_false_without_code_flags() -> None:
    entries = build_index_entries(["Widget"], {1: 4})
    assert entries["widget"].code is False


def test_build_index_entries_marks_the_leaf_node_as_code() -> None:
    entries = build_index_entries(
        ["Git!git commit"], {1: 4}, code_flags=[True]
    )
    git = entries["git"]
    assert git.code is False
    assert git.children["git commit"].code is True


def test_build_index_entries_any_code_occurrence_marks_the_merged_entry() -> None:
    terms = ["git commit", "git commit"]
    occurrence_pages = {1: 4, 2: 9}

    entries = build_index_entries(terms, occurrence_pages, code_flags=[False, True])

    assert entries["git commit"].code is True


# ---------------------------------------------------------------------------
# render_index_content
# ---------------------------------------------------------------------------


def test_render_index_content_empty_entries_returns_empty_string() -> None:
    assert render_index_content({}) == ""


def test_render_index_content_renders_one_paragraph_per_term() -> None:
    content = render_index_content(
        {"gadget": IndexEntry("Gadget", [4], {}), "widget": IndexEntry("Widget", [1, 3], {})}
    )
    assert '<div class="prodockit-index-entry prodockit-index-level-1">Gadget, 4</div>' in content
    assert '<div class="prodockit-index-entry prodockit-index-level-1">Widget, 1, 3</div>' in content


def test_render_index_content_groups_entries_under_a_letter_heading() -> None:
    content = render_index_content(
        {
            "apple": IndexEntry("Apple", [1], {}),
            "avocado": IndexEntry("Avocado", [2], {}),
            "banana": IndexEntry("Banana", [3], {}),
        }
    )
    letter_a = '<h2 class="prodockit-index-letter unnumbered unlisted">A</h2>'
    letter_b = '<h2 class="prodockit-index-letter unnumbered unlisted">B</h2>'
    assert content.index(letter_a) < content.index("Apple")
    assert content.index("Apple") < content.index("Avocado")
    assert content.count(letter_a) == 1
    assert letter_b in content
    assert content.index("Avocado") < content.index(letter_b)


def test_render_index_content_renders_nested_children_with_increasing_level_classes() -> None:
    content = render_index_content(
        {
            "staging area": IndexEntry(
                "Staging area",
                [27],
                {
                    "files": IndexEntry(
                        "files",
                        [],
                        {
                            "adding": IndexEntry("adding", [36], {}),
                            "modified": IndexEntry("modified", [205], {}),
                        },
                    )
                },
            )
        }
    )
    assert '<div class="prodockit-index-entry prodockit-index-level-1">Staging area, 27</div>' in content
    # "files" has no page of its own - no trailing ", N" at all.
    assert '<div class="prodockit-index-entry prodockit-index-level-2">files</div>' in content
    assert '<div class="prodockit-index-entry prodockit-index-level-3">adding, 36</div>' in content
    assert '<div class="prodockit-index-entry prodockit-index-level-3">modified, 205</div>' in content
    # Only one letter heading overall - "files"/"adding"/"modified" don't
    # start their own letter sections, only the top-level "Staging area" does.
    assert content.count('class="prodockit-index-letter') == 1


def test_render_index_content_escapes_html_in_term_text() -> None:
    content = render_index_content({"<script>": IndexEntry("<script>", [1], {})})
    assert "<script>" not in content
    assert "&lt;script&gt;" in content


def test_render_index_content_wraps_a_code_styled_entry_in_code_tags() -> None:
    content = render_index_content(
        {"git commit": IndexEntry("git commit", [4, 9], {}, code=True)}
    )
    assert (
        '<div class="prodockit-index-entry prodockit-index-level-1">'
        "<code>git commit</code>, 4, 9</div>" in content
    )


def test_render_index_content_leaves_a_plain_entry_unwrapped() -> None:
    content = render_index_content({"widget": IndexEntry("Widget", [4], {})})
    assert "<code>" not in content
    assert '<div class="prodockit-index-entry prodockit-index-level-1">Widget, 4</div>' in content


def test_index_content_id_is_a_stable_constant() -> None:
    assert INDEX_CONTENT_ID == "prodockit-index-content"
