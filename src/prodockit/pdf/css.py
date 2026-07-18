# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Generates the CSS a WeasyPrint-built PDF needs on top of a project's own
website stylesheet.

A live Zensical site and a compiled PDF share the same authored content and
CSS (the caller is expected to layer its own website stylesheet - Zensical's
theme CSS plus any project ``extra.css``/``print.css`` - underneath this),
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


def build_css(
    main_font: str,
    mono_font: str,
    copyright_text: str,
    site_name: str,
    page_size: str = "A4",
    margin_top: str = "2cm",
    margin_right: str = "2cm",
    margin_bottom: str = "2cm",
    margin_left: str = "2cm",
    header_footer_font_size: str = "10pt",
    header_footer_color: str = "#555555",
    header_footer_divider_color: str = "#e2e8f0",
    reference_style_global: bool = False,
    reference_spacing_european: str = "-0.8em",
    reference_indent_global: str = "1.27cm",
    reference_spacing_global: str = "2em",
) -> str:
    """Returns the complete compiled CSS for a PDF build.

    `copyright_text`/`site_name` should already be CSS-content-string-safe
    (escaped quotes, non-ASCII characters as CSS ``\\XXXX `` escapes) before
    being passed in - this function only substitutes them into ``content:
    "..."`` declarations, it doesn't escape them itself.

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
    """
    css = """
/* ==========================================================================
   DYNAMIC TYPOGRAPHY CONFIGURATION (Injected from settings)
   ========================================================================== */
body {
    font-family: "__MAIN_FONT__", sans-serif !important;
}
h1, h2, h3, h4, h5, h6 {
    font-family: "__MAIN_FONT__", sans-serif !important;
}
pre, code {
    font-family: "__MONO_FONT__", monospace !important;
}

/* ==========================================================================
   CRITICAL WEASYPRINT STRUCTURAL CANVAS RESET
   ========================================================================== */
html, body, main, div, article, section, .md-container, .md-main, .md-content {
    display: block !important;
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    overflow: visible !important;
    position: static !important;
    float: none !important;
    background: transparent !important;
}
header, nav, footer, .md-sidebar, .md-header, .md-footer, .md-search, #search {
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
        content: "__COPYRIGHT__" !important;
        font-family: "__MAIN_FONT__", sans-serif !important;
        font-size: __PDF_HEADER_FOOTER_FONT_SIZE__ !important;
        color: __PDF_HEADER_FOOTER_COLOR__ !important;
        vertical-align: top !important;
        border-top: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-top: 8px !important;
        margin-top: 3mm !important;
        width: 80% !important;
        text-align: left !important;
    }
    /* 20% (not 15%) so "Page X of Y" has room to stay on one line once the
       page count reaches 3 digits - at 15% wide, e.g. "Page 98 of 999"
       already wrapped onto two lines (digit glyph widths vary, so this
       isn't a clean "3 digits" cutoff - some 2-digit page numbers hit it
       too). Verified up to a 999-page document at this width. */
    @bottom-right {
        content: "Page " counter(page) " of " counter(pages) !important;
        font-family: "__MAIN_FONT__", sans-serif !important;
        font-size: __PDF_HEADER_FOOTER_FONT_SIZE__ !important;
        color: __PDF_HEADER_FOOTER_COLOR__ !important;
        vertical-align: top !important;
        border-top: 1px solid __PDF_HEADER_FOOTER_DIVIDER_COLOR__ !important;
        padding-top: 8px !important;
        margin-top: 3mm !important;
        width: 20% !important;
        text-align: right !important;
    }
}
@page :first {
    @top-left { content: none !important; border-bottom: none !important; }
    @top-right { content: none !important; }
    @bottom-left { content: none !important; border-top: none !important; }
    @bottom-right { content: none !important; border-top: none !important; }
}

/* Wrap a table (plus its own caption) in <div class="prodockit-table-rotated">
   to print it sideways on its own page(s) - e.g. a wide reference table that
   doesn't fit a portrait page. This does NOT use a CSS transform: rotating a
   large/paginating box was confirmed directly to make WeasyPrint clip it to a
   single page instead of splitting across pages, and to push its own heading
   row and first few rows off-page entirely. Instead, the block is diverted
   onto its own landscape-sized page (same configured page size, width/height
   swapped) via the standard CSS Paged Media "page" property, so normal
   pagination/page-break rules - including thead's own repeat-on-every-page
   behaviour - apply exactly as they would on any other table. The actual
   90-degree anticlockwise rotation is applied afterwards, directly on the
   finished PDF's own per-page /Rotate flag (see prodockit.pdf.rotate) -
   /Rotate only changes how a page is displayed/printed, not its own content
   layout, so it can't undo the correct pagination already computed above. */
@page prodockit-rotated {
    size: __PDF_PAGE_SIZE__ landscape;
    margin: __PDF_MARGIN_TOP__ __PDF_MARGIN_RIGHT__ __PDF_MARGIN_BOTTOM__ __PDF_MARGIN_LEFT__ !important;
}
.prodockit-table-rotated {
    page: prodockit-rotated;
    break-before: page !important;
    break-after: page !important;
}

.page-break, .cover-page {
    page-break-after: always;
    break-after: always;
}
h1 { break-before: page !important; }
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

/* ==========================================================================
   TABLE LAYOUT
   ========================================================================== */
table {
    border-collapse: collapse !important;
    border: 0.5pt solid #555555 !important;
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
table th { background-color: rgba(0, 0, 0, 0.1) !important; font-weight: bold !important; text-align: center !important; }
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
    border: 0.5pt solid #555555 !important;
    font-size: 10pt !important;
}
table td { text-align: left !important; }
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
    /* KNOWN LIMITATION: WeasyPrint 69's float: footnote renders the
       footnote-area text in a fixed, narrow column (confirmed directly -
       neither an explicit percentage nor absolute-point width override
       changes it), instead of the page's full content width, so a
       footnote often wraps to 2-3 short lines rather than one. Correct
       page and font-size are unaffected. Tracked upstream rather than
       worked around here, since no CSS-side override changes it. */
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
    background-color: #e5e5e5 !important; color: #000000 !important;
    font-weight: bold; padding: 8px 12px; font-size: 10pt;
    page-break-after: avoid !important; break-after: avoid !important;
}
.tabbox-body {
    background-color: #f2f2f2 !important; padding: 12px;
    page-break-inside: auto !important; break-inside: auto !important;
    -webkit-box-decoration-break: clone !important; box-decoration-break: clone !important;
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

/* #dddddd is a 5% darker shade of a Material/Zensical default theme's own
   --md-code-bg-color (#f5f5f5) - kept identical between inline code and
   code blocks here, matching the website's own convention if a caller's
   own stylesheet uses the same variable. */
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
pre { padding: 10px !important; border-radius: 4px !important; margin: 1em 0 !important; white-space: pre-wrap !important; background-color: #dddddd !important; }
code { padding: 2px 4px !important; border-radius: 3px !important; background-color: #dddddd !important; }
/* Multi-line <code> inside <pre> is a single inline box split across hard line
   breaks; without this, the padding above lands only on the first line (default
   box-decoration-break: slice), making it look indented relative to the rest. */
pre code { padding: 0 !important; }

/* pymdownx.keys (++key+combo++) box styling - reproduces a common
   --md-typeset-kbd-* look, since a caller's own website theme CSS may not
   reach a standalone PDF (e.g. only extra.css/print.css are pulled in, not
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

/* Inline vector mappings */
.twemoji svg {
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
"""

    css = (
        css.replace("__MAIN_FONT__", main_font)
        .replace("__MONO_FONT__", mono_font)
        .replace("__COPYRIGHT__", copyright_text)
        .replace("__SITE_NAME__", site_name)
        .replace("__PDF_PAGE_SIZE__", page_size)
        .replace("__PDF_MARGIN_TOP__", margin_top)
        .replace("__PDF_MARGIN_RIGHT__", margin_right)
        .replace("__PDF_MARGIN_BOTTOM__", margin_bottom)
        .replace("__PDF_MARGIN_LEFT__", margin_left)
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
