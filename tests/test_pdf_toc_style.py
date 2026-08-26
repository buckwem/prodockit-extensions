# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The PDF contents page is deliberately styled by the shared stylesheet.

Keeping these checks outside the generated renderer CSS protects the public
customisation point: projects receive ``extra.css`` through the normal shared
file cascade and can change the presentation there.
"""

from pathlib import Path

EXTRA_CSS = Path(__file__).resolve().parents[1] / "docs" / "stylesheets" / "extra.css"


def test_pdf_contents_links_use_document_text_styling() -> None:
    css = EXTRA_CSS.read_text(encoding="utf-8")
    contents = css.split("/* PDF table of contents.", 1)[1].split("prodockit.steps", 1)[0]

    assert "#TOC a," in contents
    assert "#TOC a:visited" in contents
    assert "color: inherit;" in contents
    assert "text-decoration: none;" in contents
    assert "margin-inline-end: -1.25em;" in contents
    assert "padding-inline-start: 1.25em;" in contents
    assert "text-indent: -1.25em;" in contents
    assert "font-variant-numeric: tabular-nums;" in contents


def test_pdf_contents_nested_levels_have_compact_configurable_spacing() -> None:
    css = EXTRA_CSS.read_text(encoding="utf-8")
    contents = css.split("/* PDF table of contents.", 1)[1].split("prodockit.steps", 1)[0]

    level_one = contents.split("#TOC > ul > li > a {", 1)[1].split("}", 1)[0]
    level_two = contents.split("#TOC > ul > li > ul > li {", 1)[1].split("}", 1)[0]
    level_three = contents.split("#TOC > ul > li > ul > li > ul > li {", 1)[1].split(
        "}", 1
    )[0]

    assert "font-weight: bold;" in level_one
    assert "line-height: 1;" in level_two
    assert "line-height: 0.9;" in level_three
    assert "margin-block: 0;" in level_three
