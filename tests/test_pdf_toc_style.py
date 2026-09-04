# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The PDF contents page is deliberately styled by the managed PDF stylesheet.

Keeping these checks outside the generated renderer CSS protects the public
customisation point: projects receive ``pdk-pdf.css`` through the normal
shared-file cascade and can override its presentation in ``print.css``.
"""

from pathlib import Path

PDK_PDF_CSS = (
    Path(__file__).resolve().parents[1] / "docs" / "stylesheets" / "pdk-pdf.css"
)


def test_pdf_contents_links_use_document_text_styling() -> None:
    contents = PDK_PDF_CSS.read_text(encoding="utf-8")

    assert "#TOC a," in contents
    assert "#TOC a:visited" in contents
    assert "list-style-type: none !important;" in contents
    assert "color: inherit !important;" in contents
    assert "text-decoration: none !important;" in contents
    assert "margin-inline-end: -1.25em !important;" in contents
    assert "padding-inline-start: 1.25em !important;" in contents
    assert "text-indent: -1.25em !important;" in contents
    assert 'content: " " leader(dotted) " " target-counter(attr(href), page);' in contents
    assert "font-variant-numeric: tabular-nums !important;" in contents


def test_pdf_contents_nested_levels_have_compact_configurable_spacing() -> None:
    contents = PDK_PDF_CSS.read_text(encoding="utf-8")

    level_one = contents.split("#TOC > ul > li > a {", 1)[1].split("}", 1)[0]
    level_two_list = contents.split("#TOC > ul > li > ul {", 1)[1].split("}", 1)[0]
    level_two = contents.split("#TOC > ul > li > ul > li {", 1)[1].split("}", 1)[0]
    level_three_list = contents.split(
        "#TOC > ul > li > ul > li > ul {", 1
    )[1].split("}", 1)[0]
    level_three = contents.split("#TOC > ul > li > ul > li > ul > li {", 1)[1].split(
        "}", 1
    )[0]

    assert "font-size: 12pt !important;" in level_one
    assert "font-weight: bold !important;" in level_one
    assert "padding-inline-start: 1.21em !important;" in level_two_list
    assert "line-height: 1.1 !important;" in level_two
    assert "padding-inline-start: 1.64em !important;" in level_three_list
    assert "line-height: 1.1 !important;" in level_three
    assert "margin-block: 0 !important;" in level_three
