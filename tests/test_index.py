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


def test_term_can_be_a_markdown_link() -> None:
    """Same reasoning as the nested-emphasis case above - a term isn't
    exempted from later inline-pattern passes, so a markdown link inside
    \\index{} resolves to a real <a>, not literal `[Text](url)` text.
    prodockit.pdf.index's own mark_index_terms() still extracts the plain
    term text correctly via BeautifulSoup's get_text(), which strips the
    nested <a> tag the same way it already strips <em>/<code>."""
    html = _convert(r"\index{[Git](https://git-scm.com/)} is a version control system.")
    assert '<span class="index"><a href="https://git-scm.com/">Git</a></span>' in html


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


def test_code_styled_flat_term() -> None:
    html = _convert(r"Run \index{`git commit`} to save your changes.")
    assert (
        '<span class="index" data-index-code="true" data-index-term="git commit">'
        "<code>git commit</code></span>" in html
    )


def test_code_styled_hierarchical_term() -> None:
    html = _convert(r"Run \index{Git!`git commit`} to save your changes.")
    assert (
        '<span class="index" data-index-code="true" data-index-term="Git!git commit">'
        "<code>git commit</code></span>" in html
    )


def test_code_styled_three_level_hierarchical_term() -> None:
    html = _convert(r"See \index{Git!commands!`git commit`} for details.")
    assert (
        '<span class="index" data-index-code="true" '
        'data-index-term="Git!commands!git commit"><code>git commit</code></span>' in html
    )


def test_code_styled_term_is_not_reprocessed_for_nested_markdown() -> None:
    """Unlike a plain \\index{Term}'s own display text, code-styled text
    sits inside a real <code> element - Python-Markdown's own inline
    processing doesn't recurse into it, so e.g. a literal asterisk stays
    literal rather than becoming emphasis, matching how any other code
    span behaves."""
    html = _convert(r"Run \index{`git *rebase*`} carefully.")
    assert "<code>git *rebase*</code>" in html
    assert "<em>" not in html


def test_inline_backticks_do_not_protect_the_code_styled_syntax() -> None:
    """Confirmed directly: unlike the plain \\index{Term} pattern (kept at
    the usual low priority, so a real code span always gets first look),
    the code-styled pattern is registered *above* 'backtick' - it has to
    be, to recognise its own inner backticks before 'backtick' stashes
    them first (see this module's own docstring). One consequence: inline
    backticks wrapped around the *whole* call from the outside don't
    protect it the way they do for the plain syntax - it's still live-
    processed either way. Showing the code-styled syntax as literal
    example text (as this project's own docs do) needs a fenced code
    block instead, which - unlike inline backticks - stashes its content
    at the block-parsing stage, before any inline pattern (this one
    included) ever runs."""
    md = markdown.Markdown(extensions=[IndexExtension()])
    html = md.convert(r"Use `\index{`Term`}` to mark a code term.")
    assert '<span class="index"' in html


def test_fenced_code_block_does_protect_the_code_styled_syntax() -> None:
    """See test_inline_backticks_do_not_protect_the_code_styled_syntax's own
    docstring - a fenced code block, unlike inline backticks, stashes its
    content before any inline pattern runs at all, so it's the safe way to
    show this syntax as literal example text (as this project's own docs
    do for every prodockit extension's syntax, including this one)."""
    md = markdown.Markdown(extensions=[IndexExtension(), "fenced_code"])
    html = md.convert("```md\nRun \\index{`git commit`} to save.\n```")
    assert '<span class="index"' not in html
    assert "<code" in html


def test_plain_index_still_works_alongside_the_code_pattern() -> None:
    html = _convert(r"A \index{widget} and a \index{`git commit`} in one line.")
    assert '<span class="index">widget</span>' in html
    assert 'data-index-term="git commit"><code>git commit</code></span>' in html
