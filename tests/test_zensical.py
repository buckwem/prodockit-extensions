# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Direct unit tests for prodockit._zensical's internal helpers - the pieces
prescan_headings() is built from, and prescan_headings() itself, kept
separate from the full markdown-conversion integration tests in
test_zensical_integration.py so a regression here (e.g. in the fence/comment
skipping) points straight at the broken primitive."""

from pathlib import Path

import pytest

import prodockit._zensical as prodockit_zensical
from prodockit._zensical import _count_top_level_headings, _front_matter_flag, prescan_headings


def test_front_matter_flag_true_when_set() -> None:
    text = "---\nis_appendix: true\n---\n\n# Heading\n"
    assert _front_matter_flag(text, "is_appendix") is True


def test_front_matter_flag_false_when_absent() -> None:
    text = "---\nicon: lucide/book-open\n---\n\n# Heading\n"
    assert _front_matter_flag(text, "is_appendix") is False


def test_front_matter_flag_false_without_front_matter() -> None:
    assert _front_matter_flag("# Heading\n", "is_appendix") is False


def test_front_matter_flag_is_case_insensitive() -> None:
    text = "---\nis_appendix: TRUE\n---\n\n# Heading\n"
    assert _front_matter_flag(text, "is_appendix") is True


def test_count_top_level_headings_counts_only_h1() -> None:
    text = "# One\n\n## Sub\n\n# Two\n"
    assert _count_top_level_headings(text) == 2


def test_count_top_level_headings_skips_fenced_examples() -> None:
    text = "# Real\n\n```markdown\n# Not a heading\n```\n"
    assert _count_top_level_headings(text) == 1


def test_count_top_level_headings_skips_html_comments() -> None:
    text = "<!--\n# Not a heading\n-->\n\n# Real\n"
    assert _count_top_level_headings(text) == 1


def test_count_top_level_headings_skips_unnumbered() -> None:
    text = "# Cover {.unnumbered}\n\n# Real\n"
    assert _count_top_level_headings(text) == 1


# ---------------------------------------------------------------------------
# Setext h1s (#106)
#
# Nothing else in either pipeline distinguishes setext from ATX - Zensical's
# renderer and Pandoc both produce a real h1 either way - so an uncounted
# setext heading silently desynchronised continuous chapter numbering:
# later pages' start counts came out short, duplicating a chapter number on
# the website and leaving it one behind the PDF. Each expectation below was
# checked against the real renderer's own output rather than assumed.
# ---------------------------------------------------------------------------

def test_count_top_level_headings_counts_setext_h1() -> None:
    assert _count_top_level_headings("Title\n=====\n") == 1


def test_count_top_level_headings_counts_a_single_equals_underline() -> None:
    """One "=" is enough for the real renderer, so it has to be enough here."""
    assert _count_top_level_headings("Title\n=\n") == 1


def test_count_top_level_headings_allows_trailing_space_after_the_underline() -> None:
    assert _count_top_level_headings("Title\n=====   \n") == 1


def test_count_top_level_headings_ignores_a_dash_underline() -> None:
    """A "-" underline is a setext *h2*, not an h1."""
    assert _count_top_level_headings("Title\n-----\n") == 0


def test_count_top_level_headings_ignores_an_underline_after_a_two_line_paragraph() -> None:
    """The renderer produces no heading at all here - a setext underline
    only applies to a single text line - so neither should this."""
    assert _count_top_level_headings("Line one\nLine two\n========\n") == 0


def test_count_top_level_headings_ignores_an_underline_split_from_its_text() -> None:
    assert _count_top_level_headings("Title\n\n=====\n") == 0


def test_count_top_level_headings_ignores_an_indented_setext_block() -> None:
    """Four spaces makes it an indented code block, not a heading."""
    assert _count_top_level_headings("    Title\n    =====\n") == 0


def test_count_top_level_headings_skips_setext_inside_a_fence() -> None:
    assert _count_top_level_headings("```\nTitle\n=====\n```\n") == 0


def test_count_top_level_headings_skips_setext_inside_an_html_comment() -> None:
    assert _count_top_level_headings("<!--\nTitle\n=====\n-->\n") == 0


def test_count_top_level_headings_skips_unnumbered_setext() -> None:
    """attr_list attaches a setext heading's own attributes to the *text*
    line, not the line after the underline."""
    assert _count_top_level_headings("Title {: .unnumbered }\n=====\n") == 0


def test_count_top_level_headings_does_not_double_count_an_atx_heading() -> None:
    """A "=====" line under an ATX heading is a paragraph to the renderer,
    not a second heading - the ATX line has already counted itself."""
    assert _count_top_level_headings("# Title\n=====\n") == 1


def test_count_top_level_headings_counts_mixed_atx_and_setext() -> None:
    assert _count_top_level_headings("# One\n\nTwo\n===\n\n# Three\n") == 3


def test_prescan_headings_returns_none_outside_zensical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prodockit_zensical, "nav_pages", lambda: None)
    assert prescan_headings("is_appendix") is None


def test_prescan_headings_computes_cumulative_start_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "page1.md").write_text("# One\n\n## Sub\n", encoding="utf-8")
    (docs_dir / "page2.md").write_text("# Two\n", encoding="utf-8")
    (docs_dir / "page3.md").write_text("# Three\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["page1.md", "page2.md", "page3.md"]),
    )
    result = prescan_headings("is_appendix")
    assert result is not None
    start_counts, appendix_letters = result
    assert start_counts == {"page1.md": 0, "page2.md": 1, "page3.md": 2}
    assert appendix_letters == {}


def test_prescan_headings_letters_appendix_pages_and_skips_them_from_the_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "page1.md").write_text("# One\n", encoding="utf-8")
    (docs_dir / "acronyms.md").write_text(
        "---\nis_appendix: true\n---\n\n# Acronyms\n", encoding="utf-8"
    )
    (docs_dir / "glossary.md").write_text(
        "---\nis_appendix: true\n---\n\n# Glossary\n", encoding="utf-8"
    )
    (docs_dir / "page2.md").write_text("# Two\n", encoding="utf-8")
    monkeypatch.setattr(
        prodockit_zensical,
        "nav_pages",
        lambda: (str(docs_dir), ["page1.md", "acronyms.md", "glossary.md", "page2.md"]),
    )
    result = prescan_headings("is_appendix")
    assert result is not None
    start_counts, appendix_letters = result
    # page2 continues the numeric sequence as if the two appendix pages
    # were never there - "1" (from page1), not "3".
    assert start_counts == {"page1.md": 0, "page2.md": 1}
    assert appendix_letters == {"acronyms.md": "A", "glossary.md": "B"}


def test_prescan_headings_respects_a_custom_appendix_attr_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "appendix.md").write_text(
        "---\ncustom_flag: true\n---\n\n# Appendix\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        prodockit_zensical, "nav_pages", lambda: (str(docs_dir), ["appendix.md"])
    )
    result = prescan_headings("custom_flag")
    assert result is not None
    _, appendix_letters = result
    assert appendix_letters == {"appendix.md": "A"}
