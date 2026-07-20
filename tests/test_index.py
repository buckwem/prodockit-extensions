# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import markdown

from prodockit.index import IndexExtension


def _convert(text: str) -> str:
    md = markdown.Markdown(extensions=[IndexExtension()])
    return md.convert(text)


def test_marks_a_term_as_a_span() -> None:
    html = _convert(r"A \index{widget} is here.")
    assert '<span class="index">widget</span>' in html


def test_marks_multiple_terms_in_one_line() -> None:
    html = _convert(r"A \index{widget} and a \index{gadget}.")
    assert '<span class="index">widget</span>' in html
    assert '<span class="index">gadget</span>' in html


def test_repeated_term_marks_each_occurrence_separately() -> None:
    html = _convert(r"A \index{widget}, and later another \index{widget}.")
    assert html.count('<span class="index">widget</span>') == 2


def test_term_can_contain_spaces() -> None:
    html = _convert(r"See the \index{border image} property.")
    assert '<span class="index">border image</span>' in html


def test_term_text_still_gets_normal_inline_markdown_processing() -> None:
    """Confirmed directly: unlike \\ref{id}/\\cite{id}/\\gls{id} (each
    resolving a short id, not display text), the span this emits isn't
    exempted from Python-Markdown's own later inline-pattern passes - a
    term behaves exactly like the surrounding prose would. Harmless for
    indexing purposes either way: prodockit.pdf.index's own
    mark_index_terms() reads the span's plain text via BeautifulSoup's
    get_text(), which already strips any nested tags regardless."""
    html = _convert(r"A \index{*widget*} here.")
    assert '<span class="index"><em>widget</em></span>' in html


def test_literal_backslash_index_in_a_code_span_is_left_untouched() -> None:
    html = _convert(r"Use `\index{Term}` to mark a term.")
    assert "<code>" in html
    assert '<span class="index">' not in html


def test_no_marker_leaves_plain_text_unchanged() -> None:
    html = _convert("Nothing marked here.")
    assert "Nothing marked here." in html
    assert '<span class="index">' not in html


def test_hierarchical_term_displays_only_the_last_segment() -> None:
    html = _convert(r"Now generate the \index{Git!ssh keys}.")
    assert '<span class="index" data-index-term="Git!ssh keys">ssh keys</span>' in html


def test_three_level_hierarchical_term() -> None:
    html = _convert(r"See \index{Staging area!files!adding} for details.")
    assert (
        '<span class="index" data-index-term="Staging area!files!adding">adding</span>'
        in html
    )


def test_hierarchical_term_strips_whitespace_around_bang_separators() -> None:
    html = _convert(r"\index{ Git ! ssh keys }")
    assert '<span class="index" data-index-term="Git!ssh keys">ssh keys</span>' in html


def test_flat_term_has_no_data_index_term_attribute() -> None:
    html = _convert(r"A \index{widget} is here.")
    assert "data-index-term" not in html
