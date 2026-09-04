# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Generates the CSS a WeasyPrint-built PDF needs on top of a project's own
website stylesheet.

A live Zensical site and a compiled PDF share the same authored content and
CSS (the caller layers the generated renderer foundation first, followed by
managed ``pdk.css``/``pdk-pdf.css`` and author-owned
``extra.css``/``print.css``),
but a paginated, single-document PDF has structural needs no website page
does: page-break behaviour tuned to real WeasyPrint quirks (see each rule's
own comment below for the specific bug it works around), running
header/footer boxes, footnotes anchored via ``float: footnote``, and
generic layout for the shapes :mod:`prodockit.pdf.html` and :mod:`prodockit.pdf.lua`
reconstruct (tabbed sets, grid cards, figure/table captions).

Values a caller's own project config controls (fonts, page size/margins,
header/footer styling) are ``__PLACEHOLDER__``-substituted rather than
templated with f-strings directly, so the literal ``{``/``}`` in the CSS
itself (custom properties, ``@page`` blocks) never collides with Python's
own string formatting.
"""

from __future__ import annotations


def build_structural_guard_css() -> str:
    """Return non-customisable rules that keep the PDF canvas valid.

    These rules are appended after project styles. They remove website shell
    geometry that cannot survive in a paginated document; presentation stays
    earlier in the cascade and remains author-overridable.
    """

    return """
html, body, main, div, article, section, .md-container, .md-main, .md-content,
.md-content__inner {
    display: block !important;
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    overflow: visible !important;
    position: static !important;
    float: none !important;
    background: transparent !important;
}
html, body, main, .md-container, .md-main, .md-main__inner, .md-content,
.md-content__inner {
    margin-left: 0 !important;
    margin-right: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
header, nav, footer, .md-sidebar, .md-header, .md-footer, .md-search, #search {
    display: none !important;
}
"""


def build_css(
    main_font: str,
    mono_font: str,
    site_name: str,
    page_size: str = "A4",
    margin_top: str = "2cm",
    margin_right: str = "2cm",
    # Deeper than the other three, deliberately. The running footer sits in
    # this margin, top-aligned below a divider rule, and grows *downward* as
    # it gains lines - so the space left between it and the paper edge is
    # whatever the margin does not use. A two-line footer (this project's
    # own: a copyright line plus a "Made with" credit) left only 6.1mm at
    # 2cm, measured on a real render. Consumer and office printers commonly
    # cannot print within 5-6.4mm of the edge, so the second line was at
    # real risk of being cropped (prodockit-extensions#139). 2.5cm leaves
    # 11.4mm, which clears that comfortably.
    #
    # Raising the margin rather than moving the footer within it: both
    # footer boxes are top-aligned with a matching `margin-top`/
    # `padding-top` so their border-tops form one continuous rule across the
    # page. Bottom-aligning them to guarantee clearance instead would let a
    # two-line box and the one-line page number sit at different heights and
    # break that rule.
    margin_bottom: str = "2.5cm",
    margin_left: str = "2cm",
    double_sided: bool = False,
    margin_inner: str = "2cm",
    margin_outer: str = "2cm",
    header_footer_font_size: str = "10pt",
    header_footer_color: str = "#555555",
    header_footer_divider_color: str = "#e2e8f0",
    reference_style_global: bool = False,
    reference_spacing_european: str = "-0.8em",
    reference_indent_global: str = "1.27cm",
    reference_spacing_global: str = "2em",
) -> str:
    """Returns the complete compiled CSS for a PDF build.

    `site_name` should already be CSS-content-string-safe (escaped quotes,
    non-ASCII characters as CSS ``\\XXXX `` escapes) before being passed in -
    this function only substitutes it into a ``content: "..."`` declaration,
    it doesn't escape it itself.

    There's no `copyright_text` parameter here (unlike `site_name`, which is
    still a plain ``content: "..."`` string) - the copyright footer box
    instead reads ``content: element(prodockit-pdf-copyright)`` (CSS Paged
    Media's ``position: running()``/``content: element()``, confirmed
    directly against real WeasyPrint output), cloning whatever real DOM
    element with class ``prodockit-pdf-copyright`` the caller placed
    somewhere in the document body (see `prodockit.pdf.build.build_pdf`) -
    onto every page's footer, not just the one it's actually written on.
    Unlike a generated ``content`` string, a cloned real element can contain
    a real, clickable ``<a href="...">`` link - the whole reason for this
    approach: `project.copyright`/`pdf_copyright` can now contain a real
    HTML fragment (e.g. crediting Zensical/prodockit with actual links),
    matching Zensical's own website-side ``copyright`` setting, which
    already accepts one. A cloned element keeps only its *own* CSS (the
    `.prodockit-pdf-copyright` rule below), not whatever's declared on the
    ``@bottom-left``/``@bottom-right`` box itself (confirmed directly) - so
    typography (font/size/color) lives on that selector instead, while the
    box itself keeps only true box-layout properties (border/padding/
    margin/width/text-align), which *do* still apply to a cloned element.

    `reference_style_global` mirrors a project's own website-side
    reference-style macro (typically driven by a
    ``project.extra.reference_style`` config value in ``zensical.toml``):
    False (the default, "european") gives every ``.reference``/``.acronym``/
    ``.glossary`` paragraph tight, single-line spacing with no indent
    between entries; True ("global") gives ``.reference`` paragraphs
    (only - ``.acronym``/``.glossary`` are unaffected either way) double
    spacing between entries with a hanging indent on wrapped lines (the
    common APA/MLA/Chicago style). These three classes have no equivalent
    styling on the website side without a ``.md-typeset`` ancestor wrapper -
    Pandoc's HTML output has no such wrapper, so these plain, unscoped
    selectors are what actually applies either style in a PDF.

    `double_sided` (default off) switches to a duplex-printing layout via
    CSS Paged Media's ``:left``/``:right`` page selectors: right-hand
    (recto) pages keep the same header/footer arrangement as a single-sided
    build (chapter title top-right, site name top-left, page number
    bottom-right, copyright bottom-left), while left-hand (verso) pages
    mirror all four - chapter title and page number always land on the
    outer, fore-edge corner and site name/copyright always on the inner,
    spine-side corner, whichever physical side that is. `margin_inner`/
    `margin_outer` then replace `margin_left`/`margin_right` for real page
    margins (confirmed directly that WeasyPrint applies ``@page
    :left``/``:right`` correctly). Every numbered heading also starts on
    its own recto page in this mode (a blank page inserted if needed - pure
    CSS `break-before: recto`, confirmed directly rather than assumed).
    """
    css = """
/* ==========================================================================
   DYNAMIC TYPOGRAPHY CONFIGURATION (Injected from settings)
   ========================================================================== */
body {
    font-family: "__MAIN_FONT__", sans-serif !important;
    font-size: 11pt !important;
}
h1, h2, h3, h4, h5, h6 {
    font-family: "__MAIN_FONT__", sans-serif !important;
}
pre, code {
    font-family: "__MONO_FONT__", monospace !important;
    font-weight: 500 !important;
}
/* Scale inline and fenced code relative to its surrounding text, following
   Zensical's 0.85em convention. Apply the size to code only: setting it on
   both pre and its code child would compound the relative scale for fenced
   blocks. The monospace face otherwise appears optically larger than the
   surrounding proportional face at the same nominal size. */
code { font-size: 0.85em !important; }

/* ==========================================================================
   WEB-ONLY / PDF-ONLY CONTENT
   ========================================================================== */
/* A project marks content meant only for the live website (e.g. a
   "Download PDF" link/button) with class="web-only" - always hidden here,
   since this stylesheet only ever applies to the PDF. No project-side CSS
   needed for this half; the complementary "pdf-only" (content meant only
   for the PDF, e.g. a cover page's automated word count) needs one line in
   the project's own website stylesheet instead, since this stylesheet has
   no reach into the live site - see the "Web-only / PDF-only content"
   section in the PDF generation docs for that snippet. */
.web-only {
    display: none !important;
}

/* ==========================================================================
   PAGE LAYOUT & UNIFIED HEADER/FOOTER CONFIGURATION
   ========================================================================== */
@page {
    size: __PDF_PAGE_SIZE__;
    margin: __PDF_MARGIN_TOP__ __PDF_MARGIN_RIGHT__ __PDF_MARGIN_BOTTOM__ __PDF_MARGIN_LEFT__ !important;
    @top-center { content: none !important; }
    @top-left {
        content: "__SITE_NAME__" !important;
        font-family: "__MAIN_FONT__", sans-serif !important;
        font-size: __PDF_HEADER_FOOTER_FONT_SIZE__ !important;
        color: __PDF_HEADER_FOOTER_COLOR__ !important;
        vertical-align: bottom !important;
        border-bottom: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-bottom: 8px !important;
        /* Margin (not padding) below the border: pushes the box's bottom
           edge away from the content boundary, so content that lands
           flush against a page break (e.g. a table/tabbox continuation
           fragment) never touches the header divider line. */
        margin-bottom: 3mm !important;
        width: 50% !important;
        text-align: left !important;
    }
    /* Current chapter title, set via string-set on h1 below - stays empty
       until the first numbered h1 (i.e. through the cover and Table of
       Contents pages), then holds that chapter's title for every page until
       the next h1. Shares the header width evenly with @top-left (rather
       than being squeezed into whatever's left of an unconstrained box),
       so longer chapter titles don't wrap onto a second line; its own
       matching border-bottom lines up with @top-left's to form one
       continuous divider. */
    @top-right {
        content: string(chapter-title) !important;
        font-family: "__MAIN_FONT__", sans-serif !important;
        font-size: __PDF_HEADER_FOOTER_FONT_SIZE__ !important;
        color: __PDF_HEADER_FOOTER_COLOR__ !important;
        vertical-align: bottom !important;
        border-bottom: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-bottom: 8px !important;
        margin-bottom: 3mm !important;
        width: 50% !important;
        text-align: right !important;
    }
    @bottom-center { content: none !important; }
    @bottom-left {
        /* See prodockit.pdf.build.build_pdf's own copyright_text docs, and
           this module's docstring above, for why this is content: element()
           (a cloned real DOM node - real <a href="..."> links survive)
           instead of a generated content: "..." string. Only true box-
           layout properties belong here - font/color live on the cloned
           element's own .prodockit-pdf-copyright rule below instead;
           confirmed directly that a box's own font-family/font-size/color/
           white-space have no effect on a content: element()'d node. */
        content: element(prodockit-pdf-copyright) !important;
        vertical-align: top !important;
        border-top: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-top: 8px !important;
        margin-top: 3mm !important;
        width: 70% !important;
        text-align: left !important;
    }
    /* 30% gives both the page count and its section update date enough room
       to remain on their own lines, including a 3-digit page count. */
    @bottom-right {
        content: "Page " counter(page) " of " counter(pages) "\\A " string(revision-date) !important;
        font-family: "__MAIN_FONT__", sans-serif !important;
        font-size: __PDF_HEADER_FOOTER_FONT_SIZE__ !important;
        color: __PDF_HEADER_FOOTER_COLOR__ !important;
        vertical-align: top !important;
        border-top: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-top: 8px !important;
        margin-top: 3mm !important;
        width: 30% !important;
        text-align: right !important;
        white-space: pre-line !important;
        line-height: 1.25 !important;
    }
}

/* The real DOM element `prodockit.pdf.build.build_pdf` places once in the
   document, cloned into the @bottom-left (or, double-sided, verso
   @bottom-right) box above on every page via content: element() - see this
   module's own docstring for why. Styled directly (a box's own font/color
   don't apply to a cloned element); its own <a> links inherit this same
   color rather than a browser/Pandoc default link color, matching plain
   copyright text either side of them. position: running() itself needs
   !important - confirmed directly that without it, the "CRITICAL WEASYPRINT
   STRUCTURAL CANVAS RESET" rule above (div { position: static !important })
   otherwise wins despite this selector's higher specificity, since a
   plain (non-!important) declaration always loses to any !important one
   regardless of specificity - leaving this element in normal flow as an
   ordinary, visible block instead of pulling it out as running content. */
.prodockit-pdf-copyright {
    position: running(prodockit-pdf-copyright) !important;
    font-family: "__MAIN_FONT__", sans-serif !important;
    font-size: __PDF_HEADER_FOOTER_FONT_SIZE__ !important;
    color: __PDF_HEADER_FOOTER_COLOR__ !important;
}
.prodockit-pdf-copyright a {
    color: __PDF_HEADER_FOOTER_COLOR__ !important;
}

__PDF_DOUBLE_SIDED_PAGE_RULES__
@page :first {
    @top-left { content: none !important; border-bottom: none !important; }
    @top-right { content: none !important; }
    @bottom-left { content: none !important; border-top: none !important; }
    @bottom-right { content: none !important; border-top: none !important; }
}

/* Wrap anything in <div class="landscape-page"> to give it its own
   landscape page(s) - a wide table, a diagram, a chart, whatever does not
   fit across a portrait page. This does NOT use a CSS transform: rotating a
   large/paginating box was confirmed directly to make WeasyPrint clip it to a
   single page instead of splitting across pages, and to push its own heading
   row and first few rows off-page entirely. Instead, the block is diverted
   onto its own landscape-sized page (same configured page size, width/height
   swapped) via the standard CSS Paged Media "page" property, so normal
   pagination/page-break rules - including thead's own repeat-on-every-page
   behaviour - apply exactly as they would on any other table.

   That landscape page is then left alone. It used to be given the PDF's
   own per-page /Rotate flag, which a reader honours by displaying a
   landscape page as *portrait* with the table running sideways - so the
   page a reader actually saw was portrait, which is not what wrapping
   content in this class is asking for (prodockit-extensions#469). The
   box was landscape the whole time; only the display flag disagreed.

   Mixed orientations are fine to print: a reader rotates each page to
   fit the paper by itself. */
@page landscape-page {
    size: __PDF_PAGE_SIZE__ landscape;
    margin: __PDF_MARGIN_TOP__ __PDF_MARGIN_RIGHT__ __PDF_MARGIN_BOTTOM__ __PDF_MARGIN_LEFT__ !important;
}
.landscape-page {
    page: landscape-page;
    break-before: page !important;
    break-after: page !important;
}

.page-break, .cover-page {
    page-break-after: always;
    break-after: always;
}
h1 { break-before: __PDF_H1_BREAK_BEFORE__ !important; }
.cover-page h1 { break-before: auto !important; }
/* A generic "h1..h6 { page-break-after: avoid }" website print rule keeps a
   heading from being the last thing on a page - reasonable for h1/h2 (a
   chapter/section title followed by a short intro), but confirmed directly
   (isolated A/B rebuild) to backfire for h3-h6 whenever the heading's own
   following content is large (its own intro paragraph, an "Install X"
   sub-heading, then a whole grid card of per-OS tabs): WeasyPrint couldn't
   satisfy "heading can't be alone at the bottom of the page" without
   pulling in far more content than intended, so it pushed the *entire*
   heading (with nothing before it moved) onto a fresh page instead - even
   with hundreds of points of genuinely blank space left on the previous
   page. h1/h2 keep the "avoid" behaviour (inherited from the caller's own
   website print CSS, if any); h3-h6 override back to "auto" here. */
h3, h4, h5, h6 { page-break-after: auto !important; break-after: auto !important; }
/* A plain <p> has no break-inside/orphans/widows protection by default.
   Making every <p> unsplittable (page-break-inside: avoid) over-corrects:
   a short paragraph immediately after a heading becomes atomic with that
   heading too (the heading's own "stay with next" requirement needs the
   *whole* next block to fit when that block can't split), and if the
   combined size doesn't fit the remaining page, the whole pair gets pushed
   to a fresh page - a blank-gap regression, confirmed directly. orphans/
   widows alone (no avoid) fixes that, but only if the threshold is low
   enough to actually allow a split - orphans: 3 / widows: 3 (6 combined)
   is taller than many real intro paragraphs (a 2-3 line paragraph can't
   legally split at all under that threshold, so the whole paragraph moves
   away from its heading instead, orphaning the heading alone at the bottom
   of the previous page). orphans: 1 / widows: 2 (3 combined) is short
   enough to let even a 2-3 line paragraph split if it must, while still
   avoiding an ugly single-line widow for longer ones. */
p {
    orphans: 1;
    widows: 2;
}
/* Feeds @top-right above: skips the Table of Contents' own "Table of
   Contents" h1 (and the hidden cover-page h1) via .unnumbered, the same
   class the numbering Lua filter already uses to identify non-chapter
   headings, so the running title only starts once real content begins. */
h1:not(.unnumbered) { string-set: chapter-title content() !important; }
/* One hidden marker per source page supplies the date used by the running
   page-number footer. It follows the first heading, so an h1's forced page
   break cannot leave the marker at the foot of the previous section. */
.prodockit-revision-date {
    string-set: revision-date content() !important;
    height: 0 !important;
    overflow: hidden !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    font-size: 0 !important;
    line-height: 0 !important;
}
/* A page's own `recto_title` front matter (see prodockit.pdf.html and
   prodockit.pdf.build) inserts one of these directly after that page's
   real h1 - later in document order, so its own string-set here
   supersedes the h1's own for the rest of this page's own running header,
   without touching the h1 (still numbered/rendered normally) itself.
   Applies to both single- and double-sided layouts - the running chapter
   title appears in both, just in a different header corner. */
.prodockit-recto-title { string-set: chapter-title content() !important; }
/* The generated index's own title heading. It carries `unnumbered` (it is
   not a chapter, and must not take a number or a Table of Contents entry),
   so the rule above deliberately skips it - which is right for the Table
   of Contents, sitting at the *front* where `chapter-title` is still
   empty, but wrong for the index, which is always the very last thing in
   the document. There, skipping it left the previous chapter's own title
   standing in the running header for every index page - this project's
   own PDF showed "18. License" across its index. Setting it here restores
   the standard back-of-book behaviour: the index's own pages are headed
   "Index" (or whatever `prodockit.index`'s `title` setting says). */
h1.prodockit-index-title { string-set: chapter-title content() !important; }

/* WeasyPrint bookmarks every h1-h6 into the PDF's outline (the navigation
   pane a PDF reader shows down the side) straight from its own UA
   stylesheet - no heading class affects that by default. So `.unlisted`
   (which keeps a heading off the *generated Table of Contents page*
   instead - Pandoc's own pandoc.structure.table_of_contents(), honoured by
   the Lua filter in prodockit.pdf.lua) still leaves it in the outline, and
   because outline nesting follows heading level, every later, lower-level
   heading nests underneath it instead of under its real chapter
   (prodockit-extensions#173).

   `.unlisted` can't simply gain this rule itself: prodockit stamps
   `unnumbered unlisted` on headings that *should* stay in the outline -
   the back-of-book index's own A/B/C letter headings
   (prodockit.pdf.index.render_index_content), the "Table of Contents"
   title (prodockit.pdf.build.build_pdf) and every cover-page heading
   (prodockit.pdf.html.fix_up_page_html) - so reusing `.unlisted` here would
   remove all of them from the outline too. `.unbookmarked` is a second,
   separate class an author adds themselves (nothing prodockit emits
   carries it, so no existing PDF's outline moves) for a heading that
   should also disappear from the outline - e.g. an illustrative heading in
   documentation (see this project's own docs/extensions/refs.md). */
h1.unbookmarked, h2.unbookmarked, h3.unbookmarked,
h4.unbookmarked, h5.unbookmarked, h6.unbookmarked { bookmark-level: none; }

/* ==========================================================================
   CROSS-REFERENCES
   ========================================================================== */
/* `\autoref{id}` (see prodockit.refs) renders the target heading's own
   name, and nothing more, on the website - where the section is one click
   away and a page number would be meaningless. On paper it is the opposite:
   "see Introduction" gives a reader holding a printout nothing to turn to.
   This is the whole reason \autoref exists alongside \ref.

   target-counter() reads the referenced anchor's own page number at layout
   time, so no second pass is needed - unlike the back-of-book index, which
   has to deduplicate a term repeated on one page and therefore cannot use
   it (see prodockit.pdf.index's own module docstring for that comparison).

   Scoped to in-document links: an unresolved \autoref carries no href at
   all, and any other link would resolve to nothing, printing a stray "on
   page" with no number after it. */
a.prodockit-autoref[href^="#"]::after {
    content: " on page " target-counter(attr(href url), page) !important;
}

/* ==========================================================================
   TABLE LAYOUT
   ========================================================================== */
table {
    border-collapse: collapse !important;
    border: 0.05rem solid rgba(0, 0, 0, 0.12) !important;
    width: 100% !important;
    margin: 1.2em 0 !important;
    page-break-inside: auto !important;
    break-inside: auto !important;
}
/* prodockit.tables' own <colgroup>-based column widths only take effect
   under table-layout: fixed - scoped to its own marker class so a plain
   table's existing auto-layout/content-driven column sizing is unaffected. */
table.prodockit-table-sized {
    table-layout: fixed !important;
}
/* Rows never split mid-row - a page break only ever falls between rows */
table tr {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
}
/* Repeats the header row on every page the table spans across */
thead {
    display: table-header-group;
}
/* pymdownx.blocks.caption always wraps its caption text in a <p> - inside
   a native <figcaption> for the default append-position case (still a
   <figure> - see the "figure {}"/"figure.prodockit-table-caption" rules
   below), or as the first child <p> once prepend-position unwraps the
   <figcaption> into a <div> (see prodockit.pdf.html). */
figcaption p,
div.prodockit-table-caption > p:first-child,
div.prodockit-figure-caption > p:first-child {
    text-align: center !important;
    font-style: italic !important;
    margin-bottom: 8px !important;
    page-break-after: avoid !important;
    break-after: avoid-page !important;
}
table th { background-color: rgba(0, 0, 0, 0.05) !important; font-weight: bold !important; text-align: center !important; }
table th.prodockit-table-cell-shaded,
table td.prodockit-table-cell-shaded {
    background-color: rgba(0, 0, 0, var(--prodockit-table-cell-shade)) !important;
}
table th.prodockit-table-cell-unshaded,
table td.prodockit-table-cell-unshaded {
    background-color: transparent !important;
}
/* text-align/font-size set explicitly here, not left to inherit - a
   table-caption's own wrapping div (div.prodockit-table-caption above, or
   the "figure {}" rule below for an append-position table caption) sets
   text-align: center to keep its caption text centered, which every cell's
   content otherwise silently inherits too (confirmed directly: table body
   text was rendering center-aligned with no explicit rule anywhere
   overriding it). font-size is reduced from the inherited body size,
   matching how a dense grid of short cells reads better smaller - same
   reasoning as .tabbox-header/.admonition-title's own explicit smaller
   sizes below. */
table th, table td {
    padding: 8px 12px !important;
    /* Match the website's light-scheme --md-typeset-table-color and line
       width, while remaining self-contained when no theme variables exist. */
    border: 0.05rem solid rgba(0, 0, 0, 0.12) !important;
    font-size: 10pt !important;
    vertical-align: top !important;
}
table td { text-align: left !important; }
table th.prodockit-table-cell-valign-top,
table td.prodockit-table-cell-valign-top {
    vertical-align: top !important;
}
table th.prodockit-table-cell-valign-middle,
table td.prodockit-table-cell-valign-middle {
    vertical-align: middle !important;
}
table th.prodockit-table-cell-valign-bottom,
table td.prodockit-table-cell-valign-bottom {
    vertical-align: bottom !important;
}
/* A dense table, marked `{: .compact }` on a header cell.

   The website's problem is the theme's `min-width: 5rem` on every header
   cell; the PDF has no such minimum, so only the padding is at stake
   here. It is tightened by the same proportion for the same reason: a
   14-column table spends most of its width on padding, and on the
   columns that need it least (prodockit-extensions#489).

   Set here as well as in the website stylesheet so a table marked
   compact is compact in both outputs. A difference between the two is
   the failure this project keeps meeting. */
table.prodockit-table-compact th, table.prodockit-table-compact td {
    padding: 3px 5px !important;
}
/* A header turned on its side, from `{: rotate=270 width="..." }`.

   `transform` rather than `writing-mode`: WeasyPrint ignores the latter
   entirely and silently - measured, the text comes out horizontal while
   the column still narrows, so the heading looks merely wrapped rather
   than broken. The website uses the same mechanism, because one that
   behaves the same in both outputs is worth more than two that have to
   agree (prodockit-extensions#474). */
th.prodockit-rotate {
    vertical-align: bottom !important;
    text-align: center !important;
    padding: 4px 2px !important;
}
span.prodockit-rotate {
    display: inline-block !important;
    transform-origin: center center !important;
    white-space: normal !important;
}
table tr:first-child th, table tr:first-child td { border-top: none !important; }
table tr:last-child td { border-bottom: none !important; }

/* ==========================================================================
   ADMONITIONS & TABS LAYOUT
   ========================================================================== */
blockquote {
    background-color: #f8fafc !important; border-left: 4px solid #cbd5e1 !important;
    padding: 12px 16px !important; margin: 1em 0 !important;
}
/* Renders footnotes at the bottom of the page they're referenced on (like a
   printed book). Zensical's own markdown pipeline renders a footnote as a
   <sup id="fnref:N"> at the reference point plus a <div class="footnote">
   collecting every footnote's own text at the *end* of the page - never a
   Pandoc-native Note element. prodockit.pdf.html moves each footnote's text
   inline into a <span class="pdf-footnote"> at its own reference point
   instead, so float: footnote can anchor it to the correct page. */
.pdf-footnote {
    float: footnote !important;
    font-size: 9pt !important;
    /* Deliberately sets no width: WeasyPrint sizes the footnote area to the
       page's content width on its own, and a width override is silently
       ignored for floated footnote content anyway.

       This used to carry a "KNOWN LIMITATION" note claiming WeasyPrint 69
       rendered footnote-area text in a fixed narrow column that no CSS
       could widen. That was a misdiagnosis (see issue #101): the real
       cause was pandoc's HTML writer hard-wrapping its output at ~72
       columns, inserting newlines inside this span, which WeasyPrint's
       float: footnote width computation treats as hard break opportunities
       - collapsing the rendered text to ~304pt rather than the ~475pt
       content width. prodockit.pdf.build passes --wrap=none to fix that,
       so don't reintroduce a width here. */
}
/* A caller's own ".pdf-only" convention (content meant to show only in the
   PDF, e.g. a cover page's word-count/repo-link markers) is commonly hidden
   by default on the live website - override that back to visible here. */
.pdf-only {
    display: block !important;
    margin-bottom: 0 !important;
}
/* Collapses the gap between consecutive .pdf-only lines (e.g. word count
   directly above a repo link) without affecting the normal paragraph
   spacing above the first one. Both margin-bottom above and margin-top here
   need zeroing - CSS margin collapsing takes the max of the two, so zeroing
   only one side still leaves the other's margin as the visible gap. */
.pdf-only + .pdf-only {
    margin-top: 0 !important;
}
/* An image is *not* one of the things ".pdf-only" should turn into a block.
   The "figure {}" rule above centres its image with text-align, which only
   positions inline content - so display: block above left a ".pdf-only"
   image flush against the left edge of its own centred caption. Measured
   inside the figure at 0.00pt left / 163.96pt right, against 80.98/82.98
   for the same image without the class (prodockit-extensions#462).

   Restoring inline is the fix rather than "margin-left/right: auto",
   which reads like the textbook answer and does nothing here: WeasyPrint
   leaves a block-level replaced element at the left edge even with auto
   margins on both sides (confirmed directly, with and without this
   project's own CSS). Inline also keeps one centring mechanism for every
   image rather than two that must agree.

   Still display, not visibility: the point of the rule above is to undo a
   website's "display: none", and inline does that just as well. */
img.pdf-only {
    display: inline !important;
}
/* Renders TeX math ($...$/$$...$$, see https://zensical.org/docs/authoring/math/)
   as pre-rendered SVGs, since WeasyPrint has no JS engine to run MathJax
   client-side like the live Zensical site does. The Lua filter's Math()
   function (see prodockit.pdf.lua) replaces each formula with one of these
   images at build time. */
.pdf-math-display {
    display: block !important;
    margin: 1em auto !important;
    text-align: center !important;
    page-break-inside: avoid !important;
    break-inside: avoid !important;
}
.pdf-math-inline {
    display: inline !important;
    height: 1em !important;
    width: auto !important;
    vertical-align: middle !important;
}
@page {
    @footnote {
        border-top: 0.5pt solid #cbd5e1;
        padding-top: 6px;
        margin-top: 8px;
    }
}
.tabbox-container {
    border: 1px solid #cbd5e1; border-radius: 4px; margin: 1em 0;
    page-break-inside: auto !important; break-inside: auto !important;
    -webkit-box-decoration-break: clone !important; box-decoration-break: clone !important;
}
.tabbox-header {
    background-color: rgba(0, 0, 0, 0.05) !important; color: #000000 !important;
    border-radius: 4px 4px 0 0;
    font-weight: bold; padding: 8px 12px; font-size: 10pt;
    page-break-after: avoid !important; break-after: avoid !important;
}
.tabbox-body {
    background-color: rgba(0, 0, 0, 0.01) !important; padding: 12px;
    border-radius: 0 0 4px 4px;
    page-break-inside: auto !important; break-inside: auto !important;
    -webkit-box-decoration-break: clone !important; box-decoration-break: clone !important;
}
/* Opt in only for tab groups whose individual panels are known to be short.
   The general tab rule must remain splittable because a panel can exceed a
   page. For short operating-system command panels, however, keeping each
   reconstructed header/body pair together prevents an empty body fragment at
   the foot of one page with all of its content on the next. */
.pdf-keep-tab-pages .tabbox-container {
    page-break-inside: avoid !important;
    break-inside: avoid-page !important;
}
.admonition {
    border-left: 4px solid #448aff !important; background-color: #f8fafc !important;
    padding: 14px 18px !important; margin: 1.2em 0 !important;
    page-break-inside: auto !important; break-inside: auto !important;
    -webkit-box-decoration-break: clone !important; box-decoration-break: clone !important;
}
.admonition-title {
    font-weight: bold !important; margin-bottom: 8px !important; font-size: 10.5pt !important;
    color: #000000 !important;
    /* auto, not avoid: same WeasyPrint quirk as h3-h6's own page-break-after
       above - confirmed directly: even though .admonition itself already
       uses page-break-inside: auto, the title's own avoid-after still
       forced the *entire* admonition onto a fresh page rather than letting
       it start on the current one, leaving a large blank gap behind -
       despite the admonition's own body commonly being just 2-3 short
       lines, easily small enough to have fit. */
}

.admonition.note     { border-left-color: #448aff !important; background-color: rgba(68, 138, 255, 0.05) !important; }
.admonition.abstract { border-left-color: #00b0ff !important; background-color: rgba(0, 176, 255, 0.05) !important; }
.admonition.info     { border-left-color: #00b8d4 !important; background-color: rgba(0, 184, 212, 0.05) !important; }
.admonition.tip      { border-left-color: #00bfa5 !important; background-color: rgba(0, 191, 165, 0.05) !important; }
.admonition.success  { border-left-color: #00c853 !important; background-color: rgba(0, 200, 83, 0.05) !important; }
.admonition.question { border-left-color: #64dd17 !important; background-color: rgba(100, 221, 23, 0.05) !important; }
.admonition.warning  { border-left-color: #ff9100 !important; background-color: rgba(255, 145, 0, 0.05) !important; }
.admonition.failure  { border-left-color: #ff5252 !important; background-color: rgba(255, 82, 82, 0.05) !important; }
.admonition.danger   { border-left-color: #ff1744 !important; background-color: rgba(255, 23, 68, 0.05) !important; }
.admonition.bug      { border-left-color: #ec407a !important; background-color: rgba(236, 64, 122, 0.05) !important; }
.admonition.example  { border-left-color: #651fff !important; background-color: rgba(101, 31, 255, 0.05) !important; }
.admonition.quote    { border-left-color: #9e9e9e !important; background-color: rgba(158, 158, 158, 0.05) !important; }

/* ==========================================================================
   GRID CARDS
   ========================================================================== */
/* Zensical's own native grid-card HTML (<div class="grid cards" markdown>
   wrapping a bullet list - see "Grid cards" in Zensical's authoring docs)
   is a plain <div class="grid cards ..."><ul><li>...</li></ul></div> -
   Pandoc reads the real <div>/<ul>/<li> as-is, no translation needed.
   Each <li> is a card, and the card's leading paragraph (its own
   "__bold title__") is styled as the title.
   WeasyPrint's CSS Grid support is too limited to trust for an actual
   side-by-side multi-column layout, so every card - one-column or not -
   renders as one full-width box per row, stacked. */
div.grid.cards > ul {
    list-style: none !important; margin: 1.5em 0 !important; padding: 0 !important;
}
div.grid.cards > ul > li {
    background-color: #f4f8ff !important; border: none !important;
    padding: 16px !important; margin-bottom: 1em !important; border-radius: 4px !important;
    /* auto, not avoid: a real Zensical grid card commonly wraps a whole
       tabbed-set (e.g. per-OS install instructions, all tabs stacked since
       WeasyPrint can't do interactive tabs) - often taller than a full
       page. "avoid" forces the entire oversized card onto a fresh page as
       one atomic unit (unable to actually fit there either), leaving a
       large blank gap on the previous page - confirmed directly. Same
       "auto" convention as .tabbox-container/.admonition above, for the
       same reason. */
    page-break-inside: auto !important; break-inside: auto !important; list-style: none !important;
}
div.grid.cards > ul > li > p:first-child {
    font-weight: bold !important; font-size: 13pt !important; margin-bottom: 12px !important;
    color: #111111 !important; page-break-after: avoid !important; break-after: avoid !important;
}

/* Use a 4% foreground shade for both inline and fenced code. The nested code
   inside pre is transparent so two rgba backgrounds cannot compound into a
   much darker shade. A medium weight gives the glyphs enough print contrast
   without making them as prominent as bold text. */
pre, code { font-family: "__MONO_FONT__", monospace !important; }
/* text-align isn't otherwise set anywhere on pre/code, so a fenced code
   block nested inside a centered ancestor (figure {}, div.prodockit-*-caption,
   a grid card title, an admonition/tab that happens to be inside one of
   those, etc.) would silently inherit centered text-align, ragging every
   code line's left edge - same class of inheritance bug as the table
   text-align fix above. Explicit left keeps code blocks left-aligned
   regardless of ancestor context. */
pre { text-align: left !important; }
/* A generic "img, pre, blockquote { page-break-inside: avoid }" website
   print rule is fine for img/blockquote (naturally short/atomic), but hits
   the same WeasyPrint quirk already fixed above for grid cards/table
   captions/admonitions/headings when a code block is large: a ~30+ line
   fenced example forces itself entirely onto a fresh page rather than
   splitting, leaving a large blank gap on the previous page - confirmed
   directly. Overridden back to auto here, inherited "avoid" (if any, from
   the caller's own website print CSS) kept for img/blockquote. */
pre { page-break-inside: auto !important; break-inside: auto !important; }
pre { padding: 10px !important; border-radius: 4px !important; margin: 1em 0 !important; white-space: pre-wrap !important; background-color: rgba(0, 0, 0, 0.04) !important; }
/* The reduced mono face shares the text baseline but sits optically low beside
   the larger proportional face. Raise inline code by half a point; reset the
   multi-line fenced child below so every code line stays on its normal grid. */
code { padding: 2px 4px !important; border-radius: 3px !important; background-color: rgba(0, 0, 0, 0.04) !important; vertical-align: 0.05em !important; }
/* Multi-line <code> inside <pre> is a single inline box split across hard line
   breaks; without this, the padding above lands only on the first line (default
   box-decoration-break: slice), making it look indented relative to the rest. */
pre code { padding: 0 !important; background-color: transparent !important; vertical-align: baseline !important; }

/* Syntax colours match Zensical's light website palette. Zensical/Pygments
   token classes are preserved across Pandoc by the HTML/Lua bridge; scoping
   these rules to the restored wrapper keeps unrelated author classes free. */
.prodockit-highlight .hll { background-color: #4287ff1a !important; }
.prodockit-highlight .c, .prodockit-highlight .ch,
.prodockit-highlight .cm, .prodockit-highlight .cp,
.prodockit-highlight .cpf, .prodockit-highlight .c1,
.prodockit-highlight .cs { color: #0000008c !important; }
.prodockit-highlight .k, .prodockit-highlight .kc,
.prodockit-highlight .kd, .prodockit-highlight .kn,
.prodockit-highlight .kp, .prodockit-highlight .kr,
.prodockit-highlight .kt { color: #3f6ec6 !important; }
.prodockit-highlight .l, .prodockit-highlight .ld,
.prodockit-highlight .ne, .prodockit-highlight .nt {
    color: #db1457 !important;
}
.prodockit-highlight .n, .prodockit-highlight .na,
.prodockit-highlight .nb, .prodockit-highlight .nc,
.prodockit-highlight .ni, .prodockit-highlight .nl,
.prodockit-highlight .nn, .prodockit-highlight .nx,
.prodockit-highlight .py, .prodockit-highlight .bp {
    color: #263238 !important;
}
.prodockit-highlight .o, .prodockit-highlight .ow,
.prodockit-highlight .p { color: #0000008c !important; }
.prodockit-highlight .m, .prodockit-highlight .mb,
.prodockit-highlight .mf, .prodockit-highlight .mh,
.prodockit-highlight .mi, .prodockit-highlight .mo,
.prodockit-highlight .il { color: #d52a2a !important; }
.prodockit-highlight .s, .prodockit-highlight .sa,
.prodockit-highlight .sb, .prodockit-highlight .sc,
.prodockit-highlight .dl, .prodockit-highlight .sd,
.prodockit-highlight .s2, .prodockit-highlight .se,
.prodockit-highlight .sh, .prodockit-highlight .si,
.prodockit-highlight .sx, .prodockit-highlight .sr,
.prodockit-highlight .s1, .prodockit-highlight .ss {
    color: #1c7d4d !important;
}
.prodockit-highlight .no { color: #6e59d9 !important; }
.prodockit-highlight .nd, .prodockit-highlight .nf,
.prodockit-highlight .fm { color: #a846b9 !important; }
.prodockit-highlight .nv, .prodockit-highlight .vc,
.prodockit-highlight .vg, .prodockit-highlight .vi,
.prodockit-highlight .vm, .prodockit-highlight .gd,
.prodockit-highlight .ge, .prodockit-highlight .gr,
.prodockit-highlight .gh, .prodockit-highlight .gi,
.prodockit-highlight .go, .prodockit-highlight .gp,
.prodockit-highlight .gs, .prodockit-highlight .gu,
.prodockit-highlight .gt { color: #0000008c !important; }
.prodockit-highlight .ge { font-style: italic !important; }
.prodockit-highlight .gh, .prodockit-highlight .gs,
.prodockit-highlight .gu { font-weight: bold !important; }

/* pymdownx.keys (++key+combo++) box styling - reproduces a common
   --md-typeset-kbd-* look, since a caller's own website theme CSS may not
   reach a standalone PDF (e.g. only configured project CSS is pulled in, not
   the theme's own main/palette CSS). */
kbd {
    background-color: #fafafa !important;
    border-radius: 3px !important;
    box-shadow: 0 2px 0 1px #b8b8b8, 0 2px 0 #b8b8b8, 0 -2px 3px #ffffff inset !important;
    display: inline-block !important;
    font-size: 0.75em !important;
    padding: 0 0.6em !important;
    border: 1px solid #b8b8b8 !important;
    font-family: "__MONO_FONT__", monospace !important;
}

/* Keeps an image and its /// caption /// figcaption together as one atomic
   unit, so the caption can never be pushed to a page apart from its image.
   text-align: center centers the <img> itself (a naturally inline-level
   element, so its parent's text-align controls its horizontal position) -
   without it, only the figcaption text ends up centered (its own
   centering comes from WeasyPrint's UA stylesheet default for figcaption),
   leaving the image sitting at its default left-aligned position and
   visibly misaligned under its own caption. Applies both to a hand-built
   figure-caption/table-caption structure and to Pandoc's own implicit
   figures (any standalone image Pandoc auto-wraps in <figure>). */
figure {
    page-break-inside: avoid !important;
    break-inside: avoid-page !important;
    text-align: center !important;
    /* HTML's own default for <figure> is "margin: 1em 40px" - an inset of
       40px on each side, which no website ever shows because every theme
       resets it. Nothing reset it here, so a captioned figure was 60pt
       narrower than the text around it: an image asking for width: 100%
       came out at 410pt in a 470pt column, short of the margin on both
       sides while the paragraph above it ran the full width.

       The horizontal margin goes; the vertical stays, because the space
       above and below a figure is wanted. Written as left/right rather
       than a margin shorthand so it cannot silently take the vertical
       spacing with it.

       This reaches captioned tables too - "figure.prodockit-table-caption"
       is a <figure> - which is the same bug wearing different content
       (prodockit-extensions#485). */
    margin-left: 0 !important;
    margin-right: 0 !important;
}
/* A prepend-position figure-caption is retagged from <figure> to <div> in
   prodockit.pdf.html (so its caption keeps original document order through
   Pandoc) - same page-break/centering treatment as the "figure {}" rule
   above (an image can't be split anyway, so keeping it atomic with its
   caption is safe), which no longer matches once it's a <div>. */
div.prodockit-figure-caption {
    page-break-inside: avoid !important;
    break-inside: avoid-page !important;
    text-align: center !important;
}
/* A CSS table shrink-wraps to the image after every constraint has been
   applied - including max-height reducing both height and width - while a
   table-caption receives exactly that final width. prodockit.headings moves
   an explicit image width onto the figure, so percentages keep resolving
   against the document column rather than against their own shrink-wrapped
   parent. The prepend form is a div because Pandoc otherwise moves a leading
   figcaption to the end (see prodockit.pdf.html). */
figure.prodockit-figure-caption,
div.prodockit-figure-caption {
    display: table !important;
    max-width: 100% !important;
    margin-left: auto !important;
    margin-right: auto !important;
}
figure.prodockit-figure-caption > p,
div.prodockit-figure-caption > p:not(:first-child) {
    display: table-row !important;
}
/* Do not match either half of a web/PDF image pair here. Matching web-only
   would restore the hidden website variant; matching pdf-only would override
   img.pdf-only's inline display above and defeat the figure's text centring.
   Ordinary captioned images remain block-level table content. */
figure.prodockit-figure-caption > p > img:not(.web-only):not(.pdf-only),
div.prodockit-figure-caption > p > img:not(.web-only):not(.pdf-only),
figure.prodockit-figure-caption > img:not(.web-only):not(.pdf-only),
div.prodockit-figure-caption > img:not(.web-only):not(.pdf-only) {
    display: block !important;
    max-width: 100% !important;
}
figure.prodockit-figure-caption > figcaption,
div.prodockit-figure-caption > p:first-child {
    display: table-caption !important;
    width: auto !important;
}
figure.prodockit-figure-caption > figcaption:first-child,
div.prodockit-figure-caption > p:first-child {
    caption-side: top !important;
}
figure.prodockit-figure-caption > figcaption:last-child {
    caption-side: bottom !important;
}
/* Unlike a figure-caption, a table-caption's content (the table itself)
   routinely runs longer than one page - inheriting "figure {}"'s
   page-break-inside: avoid (or copying it verbatim to the div case above)
   forces the whole caption+table onto a fresh page as one atomic unit,
   unable to actually fit there either, leaving a large blank gap on the
   previous page (confirmed directly). "auto" here overrides that for both
   the default append-position case (still a native <figure>) and the
   prepend-position case (retagged to a <div> above) - each row is still
   individually protected from splitting by "table tr" above. */
figure.prodockit-table-caption, div.prodockit-table-caption {
    page-break-inside: auto !important;
    break-inside: auto !important;
    text-align: center !important;
}
/* An image must not be drawn past the edge of the paper.

   The website gets this from the theme's own "img { max-width: 100% }".
   The PDF had no equivalent, and nothing else clamps an image: a 1600px
   screenshot came out 1200pt wide on a 595pt page, most of it off the
   trim edge (prodockit-extensions#480). Anything wider than about 627px
   overflowed, which is most screenshots taken on a modern display.

   The comment in prodockit.pdf.html about "a generic img { max-width:
   100% } rule elsewhere in the same stylesheet" was reasoning about this
   rule - it described the intended behaviour, and the rule itself was
   missing. That reasoning holds again now, so the icon encoder's use of
   a class rather than a bare width/height attribute stays correct.

   Held to the containing block rather than the page, which is what a
   reader means by "fits": an image in a figure, a table cell or an
   admonition follows that box, not the paper.

   The two rules that deliberately size an image themselves are both more
   specific and keep winning regardless of order - "img.twemoji" (an
   inline icon, max-width: none) and ".cover-page img" (65%). An explicit
   width, whether from a "{ width="50%" }" attribute or an inline style,
   is also unaffected: max-width only ever narrows, and a percentage
   width resolves against the same containing block. */
img {
    max-width: 100% !important;
}
img.screenshot {
    border: 1px solid #d0d0d0 !important;
    border-radius: 4px !important;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15) !important;
}
img.twemoji, i.fa-solid, i.fa-regular, i.fa-brands, i.material-icons, i[class*="fa-"], span[class*="octicon-"], .octicon {
    image-resolution: 96dpi !important;
    font-size: 1.1em !important;
    height: 1.1em !important;
    width: 1.1em !important;
    max-width: none !important;
    max-height: none !important;
    display: inline-block !important;
    vertical-align: -0.2em !important;
    margin: 0 2px !important;
    background: transparent !important;
}
.cover-page img {
    display: block !important;
    margin: 0.5cm auto 0.2cm auto !important;
    max-width: 65% !important;
    max-height: 3.5cm !important;
    object-fit: contain !important;
    image-resolution: 96dpi !important;
}
.text-center img, .text-center-italic img {
    display: inline-block !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

/* Inline vector mappings.
 *
 * Two selectors for one icon, because pandoc rewrites the first into the
 * second: an inline <svg> comes back as <img src="data:image/svg+xml;
 * base64,...">, carrying no class of its own. Nothing then matched it,
 * and an icon that was 1.1em on the website rendered at its intrinsic
 * size in the PDF - a folder icon the height of three lines, pushed out
 * of the text flow (prodockit-extensions#379). */
.twemoji svg,
.twemoji img {
    width: 1.1em;
    height: 1.1em;
    vertical-align: -0.2em;
}

/* ==========================================================================
   COVER PAGE & GENERAL PRINT ALIGNMENT UTILITIES
   ========================================================================= */
.cover-page {
    padding-top: 4cm;
}
.title-ctr-1, .title-ctr-2, .title-ctr-3, .title-ctr-4, .title-ctr-5, .title-ctr-6,
.title-ctr-b1, .title-ctr-b2, .title-ctr-b3, .title-ctr-b4, .title-ctr-b5, .title-ctr-b6 { text-align: center; display: block; }
.title-left-1, .title-left-2, .title-left-3, .title-left-4, .title-left-5, .title-left-6,
.title-left-b1, .title-left-b2, .title-left-b3, .title-left-b4, .title-left-b5, .title-left-b6 { text-align: left; display: block; }
.title-ctr-b1, .title-ctr-b2, .title-ctr-b3, .title-ctr-b4, .title-ctr-b5, .title-ctr-b6,
.title-left-b1, .title-left-b2, .title-left-b3, .title-left-b4, .title-left-b5, .title-left-b6 { font-weight: bold; }
[class*="title-"][class*="-1"] { font-size: 26pt; line-height: 32pt; margin-bottom: 0.6em; }
[class*="title-"][class*="-2"] { font-size: 22pt; line-height: 28pt; margin-bottom: 0.6em; }
[class*="title-"][class*="-3"] { font-size: 18pt; line-height: 24pt; margin-bottom: 0.6em; }
[class*="title-"][class*="-4"] { font-size: 15pt; line-height: 20pt; margin-bottom: 0.6em; }
[class*="title-"][class*="-5"] { font-size: 13pt; line-height: 17pt; margin-bottom: 0.6em; }
[class*="title-"][class*="-6"] { font-size: 11pt; line-height: 15pt; margin-bottom: 0.6em; }

.text-center, .text-center-italic { text-align: center !important; }
.text-right, .text-right-italic { text-align: right !important; }
.text-justify, .text-justify-italic { text-align: justify !important; }
.text-center-italic, .text-right-italic, .text-justify-italic { font-style: italic !important; }

.text-center, .text-right, .text-justify,
.text-center-italic, .text-right-italic, .text-justify-italic {
    page-break-inside: auto !important;
    break-inside: auto !important;
}

/* ==========================================================================
   BACK-OF-BOOK INDEX (prodockit.pdf.index)
   ========================================================================== */
/* Traditional two-column index layout - the same shape as a printed book's
   own back-of-book index. WeasyPrint's CSS Multi-column support (confirmed
   directly) correctly reflows content across both columns and, in turn,
   across as many pages as the index needs. column-fill: auto (rather than
   the "balance" default outside paged media) is what actually guarantees
   the expected reading order - fill the left column all the way down
   first, then continue at the top of the right column - "balance" would
   instead try to even out both columns' heights on the index's own last,
   partially-filled page. */
#prodockit-index-content {
    column-count: 2 !important;
    column-fill: auto !important;
    column-gap: 1.5cm !important;
    column-rule: 0.5pt solid #e2e8f0 !important;
}
h2.prodockit-index-letter {
    /* Matches prodockit-template/prodockit-userguide's own shared cover
       page hero graphic (docs/assets/cover-hero-*.svg) - its innermost,
       most saturated ring's own stroke colour. The light variant's value
       specifically (light and dark now share the same green palette, but
       a PDF always shows the light hero graphic regardless of a
       project's own website light/dark toggle - confirmed directly
       against a real rendered PDF). */
    color: #22c55e !important;
    font-size: 14pt !important;
    font-weight: bold !important;
    /* Generous top margin - clear air setting each new letter section
       apart from the previous one's list of entries. */
    margin: 1.8em 0 0.3em 0 !important;
    break-after: avoid-column !important;
    break-inside: avoid-column !important;
}
/* A <div>, not a <p> - see prodockit.pdf.index's own render_index_content()
   docstring for why: Pandoc's Para AST node has no attribute field at all,
   so a plain <p class="..."> here would silently lose its class (and with
   it, every level's own indentation below) by the time Pandoc's reader is
   done with it. */
div.prodockit-index-entry {
    margin: 0 !important;
    break-inside: avoid-column !important;
    /* An index term is frequently a single unbroken token with no space
       to wrap at - a dotted module path, a long option name, a function
       signature. Without this, such a term overflows its own column box
       instead of wrapping: it runs straight over the column rule and
       into the entries of the next column, and off the page edge
       entirely from the right-hand one. Confirmed directly against a
       real render before and after. break-word (not break-all) so
       ordinary multi-word terms still break at their spaces first, and
       only a token with nowhere else to break is split mid-word. */
    overflow-wrap: break-word !important;
}
/* Fixed indent step per nesting level (see prodockit.pdf.index's own
   IndexEntry/render_index_content docs) - level 1 sits flush with the
   column margin; each deeper level steps in by another 12pt. */
div.prodockit-index-level-2 {
    margin-left: 12pt !important;
}
div.prodockit-index-level-3 {
    margin-left: 24pt !important;
}
"""

    # Right-hand (recto) pages keep the default @page block above as-is -
    # margin only needs restating in terms of inner/outer, header/footer
    # content already matches (chapter title outer/top-right, site name
    # inner/top-left, page number outer/bottom-right, copyright inner/
    # bottom-left). Left-hand (verso) pages mirror all four corners plus
    # margin, since their spine is on the opposite physical side. Inserted
    # (see the placeholder above) *before* the existing "@page :first"
    # rule, so :first - unchanged, later in source - still wins the
    # cascade on the cover page even though it's also :right, keeping the
    # cover page's header/footer fully blank either way.
    double_sided_css = (
        """
@page :right {
    margin: __PDF_MARGIN_TOP__ __PDF_MARGIN_OUTER__ __PDF_MARGIN_BOTTOM__ __PDF_MARGIN_INNER__ !important;
}
@page :left {
    margin: __PDF_MARGIN_TOP__ __PDF_MARGIN_INNER__ __PDF_MARGIN_BOTTOM__ __PDF_MARGIN_OUTER__ !important;
    @top-left {
        content: string(chapter-title) !important;
        font-family: "__MAIN_FONT__", sans-serif !important;
        font-size: __PDF_HEADER_FOOTER_FONT_SIZE__ !important;
        color: __PDF_HEADER_FOOTER_COLOR__ !important;
        vertical-align: bottom !important;
        border-bottom: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-bottom: 8px !important;
        margin-bottom: 3mm !important;
        width: 50% !important;
        text-align: left !important;
    }
    @top-right {
        content: "__SITE_NAME__" !important;
        font-family: "__MAIN_FONT__", sans-serif !important;
        font-size: __PDF_HEADER_FOOTER_FONT_SIZE__ !important;
        color: __PDF_HEADER_FOOTER_COLOR__ !important;
        vertical-align: bottom !important;
        border-bottom: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-bottom: 8px !important;
        margin-bottom: 3mm !important;
        width: 50% !important;
        text-align: right !important;
    }
    @bottom-left {
        content: "Page " counter(page) " of " counter(pages) "\\A " string(revision-date) !important;
        font-family: "__MAIN_FONT__", sans-serif !important;
        font-size: __PDF_HEADER_FOOTER_FONT_SIZE__ !important;
        color: __PDF_HEADER_FOOTER_COLOR__ !important;
        vertical-align: top !important;
        border-top: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-top: 8px !important;
        margin-top: 3mm !important;
        width: 30% !important;
        text-align: left !important;
        white-space: pre-line !important;
        line-height: 1.25 !important;
    }
    @bottom-right {
        /* See the single-sided @bottom-left rule above for why this is
           content: element() - the copyright box just lives on the
           opposite corner on a verso page. */
        content: element(prodockit-pdf-copyright) !important;
        vertical-align: top !important;
        border-top: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-top: 8px !important;
        margin-top: 3mm !important;
        width: 70% !important;
        text-align: right !important;
    }
}
"""
        if double_sided
        else ""
    )

    css = (
        css.replace("__PDF_DOUBLE_SIDED_PAGE_RULES__", double_sided_css)
        .replace("__PDF_H1_BREAK_BEFORE__", "recto" if double_sided else "page")
        .replace("__MAIN_FONT__", main_font)
        .replace("__MONO_FONT__", mono_font)
        .replace("__SITE_NAME__", site_name)
        .replace("__PDF_PAGE_SIZE__", page_size)
        .replace("__PDF_MARGIN_TOP__", margin_top)
        .replace("__PDF_MARGIN_RIGHT__", margin_right)
        .replace("__PDF_MARGIN_BOTTOM__", margin_bottom)
        .replace("__PDF_MARGIN_LEFT__", margin_left)
        .replace("__PDF_MARGIN_INNER__", margin_inner)
        .replace("__PDF_MARGIN_OUTER__", margin_outer)
        .replace("__PDF_HEADER_FOOTER_FONT_SIZE__", header_footer_font_size)
        .replace("__PDF_HEADER_FOOTER_COLOR__", header_footer_color)
        .replace("__PDF_HEADER_FOOTER_DIVIDER_COLOR__", header_footer_divider_color)
    )

    # PDF equivalent of a website's own reference-style macro: a project's
    # "global" reference style switches the References page from the
    # default "european" look (single line spacing throughout, no indent)
    # to single line spacing within each entry but double spacing *between*
    # entries, with a hanging indent on wrapped lines. Selectors here
    # deliberately don't use ".md-typeset" - unlike a website, Pandoc's HTML
    # output has no such wrapper element, so these plain ".reference"/
    # ".acronym"/".glossary" selectors are what actually apply either style
    # in a PDF.
    if reference_style_global:
        reference_css = f"""
p.reference {{
    padding-left: {reference_indent_global} !important;
    text-indent: -{reference_indent_global} !important;
}}
p.reference + p.reference {{
    margin-top: {reference_spacing_global} !important;
}}
"""
    else:
        reference_css = f"""
p.reference + p.reference {{
    margin-top: {reference_spacing_european} !important;
}}
"""

    acronym_css = f"""
p.acronym + p.acronym {{
    margin-top: {reference_spacing_european} !important;
}}
"""

    glossary_css = f"""
p.glossary + p.glossary {{
    margin-top: {reference_spacing_european} !important;
}}
"""

    return css + "\n\n" + reference_css + "\n\n" + acronym_css + "\n\n" + glossary_css
