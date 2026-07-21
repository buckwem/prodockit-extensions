# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from prodockit.pdf.css import build_css


def test_font_family_placeholders_are_substituted() -> None:
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert '"Inter", sans-serif' in css
    assert '"Fira Code", monospace' in css
    assert "__MAIN_FONT__" not in css
    assert "__MONO_FONT__" not in css


def test_web_only_content_is_always_hidden() -> None:
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert ".web-only {" in css
    rule = css.split(".web-only {")[1].split("}")[0]
    assert "display: none !important;" in rule


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


def test_an_unescaped_quote_in_copyright_text_corrupts_the_content_string() -> None:
    """Documents the real failure mode build_css()'s own docstring warns
    about but never demonstrates: copyright_text/site_name are substituted
    into a CSS `content: "..."` declaration with no escaping at all - a
    caller passing a raw, un-pre-escaped quote silently truncates the
    generated content string rather than raising or producing valid CSS
    for the full text."""
    css = build_css("Inter", "Fira Code", 'Copyright "2026" Corp', "My Site")
    # The quote inside the value closes the CSS string early - only the
    # text up to that quote survives as the actual `content` value.
    assert 'content: "Copyright "2026" Corp"' in css
    assert 'content: "Copyright \\"2026\\" Corp"' not in css


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


def test_index_letter_heading_matches_the_hero_graphics_green() -> None:
    """h2.prodockit-index-letter's colour is meant to match the cover
    hero graphic's own innermost stroke colour (docs/assets/
    cover-hero-*.svg - both light and dark variants share this green) -
    a PDF always shows the light hero graphic regardless of a project's
    own website light/dark toggle."""
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert "h2.prodockit-index-letter {" in css
    rule = css.split("h2.prodockit-index-letter {")[1].split("}")[0]
    assert "color: #22c55e !important;" in rule


def test_rotated_table_page_uses_the_configured_page_size_landscape() -> None:
    css = build_css(
        "Inter", "Fira Code", "Copyright 2026", "My Site",
        page_size="Letter", margin_top="1in", margin_right="1in", margin_bottom="1in", margin_left="1in",
    )
    assert "@page prodockit-rotated {" in css
    assert "size: Letter landscape;" in css
    assert "margin: 1in 1in 1in 1in" in css.split("@page prodockit-rotated {")[1]


def test_rotated_table_class_forces_a_break_before_and_after() -> None:
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert ".prodockit-table-rotated {" in css
    rule = css.split(".prodockit-table-rotated {")[1].split("}")[0]
    assert "page: prodockit-rotated;" in rule
    assert "break-before: page !important;" in rule
    assert "break-after: page !important;" in rule


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


def test_single_sided_h1_breaks_before_a_plain_page() -> None:
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert "h1 { break-before: page !important; }" in css
    assert "@page :right {" not in css
    assert "@page :left {" not in css


def test_double_sided_h1_breaks_before_a_recto_page() -> None:
    """The exact-string match matters here, not just substring presence:
    this selector is a bare `h1`, deliberately *not* scoped with
    `:not(.unnumbered)` the way the sibling `string-set: chapter-title`
    rule further down is - so the Index/Table of Contents trigger heading
    (both `.unnumbered`) still gets forced onto its own recto page too,
    the same as any real chapter heading. Confirmed end-to-end with a
    real pandoc+weasyprint build in
    test_pdf_build.py::test_index_starts_on_a_recto_page_under_double_sided."""
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site", double_sided=True)
    assert "h1 { break-before: recto !important; }" in css


def test_double_sided_adds_right_and_left_page_margin_rules() -> None:
    css = build_css(
        "Inter", "Fira Code", "Copyright 2026", "My Site",
        double_sided=True, margin_top="1cm", margin_bottom="1cm",
        margin_inner="2.5cm", margin_outer="1.5cm",
    )
    assert "@page :right {" in css
    right_rule = css.split("@page :right {")[1].split("}")[0]
    assert "margin: 1cm 1.5cm 1cm 2.5cm !important;" in right_rule

    assert "@page :left {" in css
    left_block = css.split("@page :left {")[1]
    assert "margin: 1cm 2.5cm 1cm 1.5cm !important;" in left_block


def test_double_sided_verso_page_swaps_all_four_header_footer_corners() -> None:
    css = build_css("Inter", "Fira Code", "My Copyright", "My Site", double_sided=True)
    left_block = css.split("@page :left {")[1].split("\n@page")[0]
    assert "content: string(chapter-title)" in left_block.split("@top-left {")[1].split("}")[0]
    assert 'content: "My Site"' in left_block.split("@top-right {")[1].split("}")[0]
    assert 'content: "Page " counter(page) " of " counter(pages)' in (
        left_block.split("@bottom-left {")[1].split("}")[0]
    )
    assert 'content: "My Copyright"' in left_block.split("@bottom-right {")[1].split("}")[0]


def test_double_sided_recto_title_string_set_rule_always_present() -> None:
    css_single = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    css_double = build_css("Inter", "Fira Code", "Copyright 2026", "My Site", double_sided=True)
    for css in (css_single, css_double):
        assert ".prodockit-recto-title { string-set: chapter-title content() !important; }" in css


def test_no_placeholder_tokens_remain_after_substitution_double_sided() -> None:
    css = build_css(
        "Inter", "Fira Code", "Copyright 2026", "My Site",
        double_sided=True, margin_inner="2.5cm", margin_outer="1.5cm",
    )
    for placeholder in (
        "__PDF_MARGIN_INNER__", "__PDF_MARGIN_OUTER__",
        "__PDF_DOUBLE_SIDED_PAGE_RULES__", "__PDF_H1_BREAK_BEFORE__",
    ):
        assert placeholder not in css


def test_dead_gridcard_matrix_classes_are_not_present() -> None:
    """Regression guard: .gridcard-matrix/-item/-title was an older,
    hand-built HTML convention some consuming projects have retired in
    favour of Zensical's own native grid-card HTML, which never produces
    this structure - so this CSS was never ported here at all (only the
    real div.grid.cards rules were)."""
    css = build_css("Inter", "Fira Code", "Copyright 2026", "My Site")
    assert ".gridcard-matrix" not in css
    assert ".gridcard-item" not in css
    assert ".gridcard-title" not in css
