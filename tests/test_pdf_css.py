# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from prodockit.pdf.css import build_css


def test_font_family_placeholders_are_substituted() -> None:
    css = build_css("Inter", "Fira Code", "My Site")
    assert '"Inter", sans-serif' in css
    assert '"Fira Code", monospace' in css
    assert "__MAIN_FONT__" not in css
    assert "__MONO_FONT__" not in css


def test_web_only_content_is_always_hidden() -> None:
    css = build_css("Inter", "Fira Code", "My Site")
    assert ".web-only {" in css
    rule = css.split(".web-only {")[1].split("}")[0]
    assert "display: none !important;" in rule


def test_page_size_and_margins_are_substituted() -> None:
    css = build_css(
        "Inter", "Fira Code", "My Site",
        page_size="Letter", margin_top="1in", margin_right="1in", margin_bottom="1in", margin_left="1in",
    )
    assert "size: Letter;" in css
    assert "margin: 1in 1in 1in 1in" in css


def test_site_name_is_substituted_into_the_top_left_page_margin_box() -> None:
    css = build_css("Inter", "Fira Code", "My Site Name")
    assert 'content: "My Site Name"' in css


def test_copyright_box_reads_a_cloned_running_element_not_a_content_string() -> None:
    """No copyright_text parameter/content string any more - the copyright
    footer box clones whatever real DOM element with class
    prodockit-pdf-copyright the caller (prodockit.pdf.build.build_pdf)
    placed in the document, via CSS Paged Media's position: running()/
    content: element() (confirmed directly against real WeasyPrint output -
    unlike a generated content string, a cloned element's own <a href="...">
    links survive as real, clickable links). This is what makes it possible
    to give copyright_text real HTML at all."""
    css = build_css("Inter", "Fira Code", "My Site")
    assert "content: element(prodockit-pdf-copyright) !important;" in css
    assert ".prodockit-pdf-copyright {" in css
    rule = css.split(".prodockit-pdf-copyright {")[1].split("}")[0]
    assert "position: running(prodockit-pdf-copyright) !important;" in rule
    assert "font-size:" in rule
    assert "color:" in rule


def test_no_placeholder_tokens_remain_after_substitution() -> None:
    css = build_css("Inter", "Fira Code", "My Site")
    for placeholder in (
        "__MAIN_FONT__", "__MONO_FONT__", "__SITE_NAME__",
        "__PDF_PAGE_SIZE__", "__PDF_MARGIN_TOP__", "__PDF_MARGIN_RIGHT__",
        "__PDF_MARGIN_BOTTOM__", "__PDF_MARGIN_LEFT__",
        "__PDF_HEADER_FOOTER_FONT_SIZE__", "__PDF_HEADER_FOOTER_COLOR__",
        "__PDF_HEADER_FOOTER_DIVIDER_COLOR__",
    ):
        assert placeholder not in css


def test_h3_through_h6_override_page_break_after_to_auto() -> None:
    css = build_css("Inter", "Fira Code", "My Site")
    assert "h3, h4, h5, h6 { page-break-after: auto !important" in css


def test_index_letter_heading_matches_the_hero_graphics_green() -> None:
    """h2.prodockit-index-letter's colour is meant to match the cover
    hero graphic's own innermost stroke colour (docs/assets/
    cover-hero-*.svg - both light and dark variants share this green) -
    a PDF always shows the light hero graphic regardless of a project's
    own website light/dark toggle."""
    css = build_css("Inter", "Fira Code", "My Site")
    assert "h2.prodockit-index-letter {" in css
    rule = css.split("h2.prodockit-index-letter {")[1].split("}")[0]
    assert "color: #22c55e !important;" in rule


def test_rotated_table_page_uses_the_configured_page_size_landscape() -> None:
    css = build_css(
        "Inter", "Fira Code", "My Site",
        page_size="Letter", margin_top="1in", margin_right="1in", margin_bottom="1in", margin_left="1in",
    )
    assert "@page prodockit-rotated {" in css
    assert "size: Letter landscape;" in css
    assert "margin: 1in 1in 1in 1in" in css.split("@page prodockit-rotated {")[1]


def test_rotated_table_class_forces_a_break_before_and_after() -> None:
    css = build_css("Inter", "Fira Code", "My Site")
    assert ".prodockit-table-rotated {" in css
    rule = css.split(".prodockit-table-rotated {")[1].split("}")[0]
    assert "page: prodockit-rotated;" in rule
    assert "break-before: page !important;" in rule
    assert "break-after: page !important;" in rule


def test_default_reference_style_is_european_tight_spacing_only() -> None:
    css = build_css("Inter", "Fira Code", "My Site")
    assert "p.reference + p.reference {" in css
    assert "padding-left" not in css
    assert "text-indent" not in css


def test_global_reference_style_adds_hanging_indent_and_wider_spacing() -> None:
    css = build_css(
        "Inter", "Fira Code", "My Site",
        reference_style_global=True,
        reference_indent_global="1.5cm",
        reference_spacing_global="3em",
    )
    assert "padding-left: 1.5cm !important" in css
    assert "text-indent: -1.5cm !important" in css
    assert "margin-top: 3em !important" in css


def test_acronym_and_glossary_spacing_use_the_european_value_regardless_of_style() -> None:
    css = build_css(
        "Inter", "Fira Code", "My Site",
        reference_style_global=True,
        reference_spacing_european="-0.5em",
    )
    assert "p.acronym + p.acronym {\n    margin-top: -0.5em !important;" in css
    assert "p.glossary + p.glossary {\n    margin-top: -0.5em !important;" in css


def test_single_sided_h1_breaks_before_a_plain_page() -> None:
    css = build_css("Inter", "Fira Code", "My Site")
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
    css = build_css("Inter", "Fira Code", "My Site", double_sided=True)
    assert "h1 { break-before: recto !important; }" in css


def test_double_sided_adds_right_and_left_page_margin_rules() -> None:
    css = build_css(
        "Inter", "Fira Code", "My Site",
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
    css = build_css("Inter", "Fira Code", "My Site", double_sided=True)
    left_block = css.split("@page :left {")[1].split("\n@page")[0]
    assert "content: string(chapter-title)" in left_block.split("@top-left {")[1].split("}")[0]
    assert 'content: "My Site"' in left_block.split("@top-right {")[1].split("}")[0]
    assert 'content: "Page " counter(page) " of " counter(pages)' in (
        left_block.split("@bottom-left {")[1].split("}")[0]
    )
    assert "content: element(prodockit-pdf-copyright) !important;" in (
        left_block.split("@bottom-right {")[1].split("}")[0]
    )


def test_double_sided_recto_title_string_set_rule_always_present() -> None:
    css_single = build_css("Inter", "Fira Code", "My Site")
    css_double = build_css("Inter", "Fira Code", "My Site", double_sided=True)
    for css in (css_single, css_double):
        assert ".prodockit-recto-title { string-set: chapter-title content() !important; }" in css


def test_no_placeholder_tokens_remain_after_substitution_double_sided() -> None:
    css = build_css(
        "Inter", "Fira Code", "My Site",
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
    css = build_css("Inter", "Fira Code", "My Site")
    assert ".gridcard-matrix" not in css
    assert ".gridcard-item" not in css
    assert ".gridcard-title" not in css


def test_index_entry_breaks_a_long_term_instead_of_overflowing_its_column() -> None:
    """An index term is often one unbroken token with nowhere to wrap - a
    dotted module path, a long option name. Without overflow-wrap it runs
    straight out of its own column, over the column rule and into the next
    column's entries (and off the page from the right-hand column). See
    test_pdf_build.py for the real-render check that it actually stays
    inside the column; this pins the rule itself."""
    css = build_css("Inter", "Fira Code", "My Site")
    assert "div.prodockit-index-entry {" in css
    rule = css.split("div.prodockit-index-entry {")[1].split("}")[0]
    assert "overflow-wrap: break-word !important;" in rule


def test_index_title_heading_sets_the_running_chapter_title() -> None:
    """The index's own h1 carries `unnumbered`, so the general
    `h1:not(.unnumbered)` string-set rule skips it. That is right for the
    Table of Contents - it sits at the front, where chapter-title is still
    empty - but wrong for the index, which is always the very last thing
    in the document: the previous chapter's title would otherwise head
    every index page. Needed in both layouts, since the running chapter
    title appears in both (just in a different header corner)."""
    rule = "h1.prodockit-index-title { string-set: chapter-title content() !important; }"
    assert rule in build_css("Inter", "Fira Code", "My Site")
    assert rule in build_css("Inter", "Fira Code", "My Site", double_sided=True)


def test_bottom_margin_default_is_deeper_than_the_others() -> None:
    """The running footer sits in the bottom margin and grows downward as it
    gains lines, so what is left between it and the paper edge is whatever
    the margin does not use. A two-line footer left only 6.1mm at 2cm, well
    inside the 5-6.4mm many printers cannot print at all
    (prodockit-extensions#139). See test_pdf_build.py for the real-render
    measurement; this pins the default that produces it."""
    css = build_css("Inter", "Fira Code", "My Site")

    assert "margin: 2cm 2cm 2.5cm 2cm !important;" in css


def test_autoref_gets_a_page_number_in_the_pdf() -> None:
    """`\\autoref{id}` renders only the heading's name on the website, where
    the section is one click away. On paper that is useless, so the PDF
    stylesheet appends the target's own page number.

    `target-counter()` resolves it at layout time, so no second pass is
    needed - unlike the back-of-book index, which has to deduplicate a term
    repeated on one page and therefore cannot use it."""
    css = build_css("Inter", "Fira Code", "My Site")

    assert 'a.prodockit-autoref[href^="#"]::after {' in css
    rule = css.split('a.prodockit-autoref[href^="#"]::after {')[1].split("}")[0]
    assert "target-counter(attr(href url), page)" in rule


def test_unbookmarked_headings_are_removed_from_the_pdf_outline() -> None:
    """WeasyPrint bookmarks every h1-h6 into the PDF's outline regardless of
    `.unlisted` (that class only keeps a heading off the generated Table of
    Contents *page* - see prodockit.pdf.lua). `.unbookmarked` is the
    separate class this stylesheet gives `bookmark-level: none`, so an
    author can remove a heading from the outline too, without also
    reusing `.unlisted` and regressing the headings prodockit itself marks
    `unnumbered unlisted` (index letters, the Table of Contents title,
    cover-page headings) that must stay in the outline
    (prodockit-extensions#173)."""
    css = build_css("Inter", "Fira Code", "My Site")

    selector = (
        "h1.unbookmarked, h2.unbookmarked, h3.unbookmarked,\n"
        "h4.unbookmarked, h5.unbookmarked, h6.unbookmarked {"
    )
    assert selector in css
    rule = css.split(selector)[1].split("}")[0]
    assert "bookmark-level: none;" in rule


def test_unlisted_alone_does_not_get_bookmark_level_none() -> None:
    """A heading marked only `.unlisted` (no `.unbookmarked`) must keep its
    default bookmark-level - this is exactly what prodockit itself stamps
    on the back-of-book index's A/B/C letter headings
    (prodockit.pdf.index), the Table of Contents title
    (prodockit.pdf.build) and every cover-page heading (prodockit.pdf.html),
    all of which must stay in the PDF's outline. Keying the bookmark-level
    rule off `.unlisted` instead of the new `.unbookmarked` class would
    silently remove all three from the outline."""
    css = build_css("Inter", "Fira Code", "My Site")

    assert ".unlisted {" not in css
    assert "h1.unlisted" not in css


def test_autoref_page_number_is_scoped_to_in_document_links() -> None:
    """An unresolved \\autoref carries no href at all, and an external link
    resolves to nothing - either would print a stray "on page" with no
    number after it."""
    css = build_css("Inter", "Fira Code", "My Site")

    assert "a.prodockit-autoref::after" not in css
