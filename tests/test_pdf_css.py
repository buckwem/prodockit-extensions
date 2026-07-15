# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from zendoc.pdf.css import build_css


def test_font_family_placeholders_are_substituted() -> None:
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert '"Inter", sans-serif' in css
    assert '"Fira Code", monospace' in css
    assert "__MAIN_FONT__" not in css
    assert "__MONO_FONT__" not in css


def test_page_size_and_margins_are_substituted() -> None:
    css = build_css(
        "Inter", "Fira Code", "Copyright 2026", "My Site",
        page_size="Letter", margin_top="1in", margin_right="1in", margin_bottom="1in", margin_left="1in",
    )
    assert "size: Letter;" in css
    assert "margin: 1in 1in 1in 1in" in css


def test_copyright_and_site_name_are_substituted_into_page_margin_boxes() -> None:
    css = build_css("Inter", "Fira Code", "My Copyright Text", "My Site Name")
    assert 'content: "My Copyright Text"' in css
    assert 'content: "My Site Name"' in css


def test_no_placeholder_tokens_remain_after_substitution() -> None:
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    for placeholder in (
        "__MAIN_FONT__", "__MONO_FONT__", "__COPYRIGHT__", "__SITE_NAME__",
        "__PDF_PAGE_SIZE__", "__PDF_MARGIN_TOP__", "__PDF_MARGIN_RIGHT__",
        "__PDF_MARGIN_BOTTOM__", "__PDF_MARGIN_LEFT__",
        "__PDF_HEADER_FOOTER_FONT_SIZE__", "__PDF_HEADER_FOOTER_COLOR__",
        "__PDF_HEADER_FOOTER_DIVIDER_COLOR__",
    ):
        assert placeholder not in css


def test_h3_through_h6_override_page_break_after_to_auto() -> None:
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert "h3, h4, h5, h6 { page-break-after: auto !important" in css


def test_default_reference_style_is_european_tight_spacing_only() -> None:
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert "p.reference + p.reference {" in css
    assert "padding-left" not in css
    assert "text-indent" not in css


def test_global_reference_style_adds_hanging_indent_and_wider_spacing() -> None:
    css = build_css(
        "Inter", "Fira Code", "Copyright 2026", "My Site",
        reference_style_global=True,
        reference_indent_global="1.5cm",
        reference_spacing_global="3em",
    )
    assert "padding-left: 1.5cm !important" in css
    assert "text-indent: -1.5cm !important" in css
    assert "margin-top: 3em !important" in css


def test_acronym_and_glossary_spacing_use_the_european_value_regardless_of_style() -> None:
    css = build_css(
        "Inter", "Fira Code", "Copyright 2026", "My Site",
        reference_style_global=True,
        reference_spacing_european="-0.5em",
    )
    assert "p.acronym + p.acronym {\n    margin-top: -0.5em !important;" in css
    assert "p.glossary + p.glossary {\n    margin-top: -0.5em !important;" in css


def test_dead_gridcard_matrix_classes_are_not_present() -> None:
    """Regression guard: .gridcard-matrix/-item/-title was the old regex
    pipeline's own hand-built HTML convention (retired in zendoc-template#92)
    - Zensical's real grid-card HTML never produces this structure, so this
    CSS was never ported here at all (only the real div.grid.cards rules
    were)."""
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert ".gridcard-matrix" not in css
    assert ".gridcard-item" not in css
    assert ".gridcard-title" not in css
