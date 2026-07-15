# PDF generation

## Overview

`zendoc.pdf` is a Pandoc/WeasyPrint pipeline for building a standalone PDF
from Zensical-rendered HTML - the kind of downloadable, submittable document
professional and academic reports commonly need alongside the website
itself, which Zensical doesn't produce on its own.

Unlike `zendoc.headings`/`zendoc.refs`/`zendoc.citations`/`zendoc.glossary`,
`zendoc.pdf` is **not** a Python-Markdown extension - there's no
`markdown.extensions` entry point for it, and nothing to add to
`zensical.toml`. A PDF build pipeline isn't a Markdown syntax extension: it
runs *after* Zensical has already rendered a page to HTML, fixing that HTML
up for Pandoc (a different parser from Python-Markdown, with its own reader/
writer quirks) and generating the Lua filter and CSS a compiled, paginated
document needs that a live website doesn't. Import what you need directly
from `zendoc.pdf.html`/`.lua`/`.css`/`.icons`/`.mermaid`, the same way as any
other zendoc module - see [zendoc-extension#7](https://github.com/buckwem/zendoc-extension/issues/7)
for why there's no bundled "build the whole PDF" entry point yet.

## Why this exists

Pandoc is a completely different parser from Python-Markdown/Zensical, with
no awareness of Zensical/`pymdownx`-specific markup at all. Feeding it a
page's real, already-rendered HTML (rather than hand-translating markdown
syntax into a Pandoc-compatible dialect) means Pandoc's own HTML reader
already understands standard HTML correctly - no per-feature translation
needed - but a handful of real HTML constructs still trip up Pandoc's
reader/writer, or WeasyPrint's rendering, in ways that need working around
before/after Pandoc sees them. `zendoc.pdf` collects those workarounds so a
consuming project doesn't have to rediscover them:

- A raw inline `<svg>` (icons, emoji, diagrams) doesn't survive Pandoc's
  HTML-to-HTML round trip through to WeasyPrint at all.
- Pandoc's native `Para` AST node has no attribute field, silently dropping
  any `id`/`class` a `<p>` carries (attr_list-based citation/glossary
  definitions, styled paragraphs).
- Pandoc's `Figure` AST node stores its caption and content as two separate
  fields rather than ordered children, so a caption meant to appear
  *before* its table/figure always ends up *after* it once Pandoc's own
  HTML writer re-serializes the page.
- A multi-page site concatenated into one PDF document needs cross-page
  links rewritten to in-document anchors, and local images/repo file links
  rewritten so they don't depend on relative paths resolving from wherever
  Pandoc happens to run.
- WeasyPrint has no JS engine, so client-side Mermaid diagrams and MathJax
  formulas need pre-rendering to static images before Pandoc ever sees them.
- A handful of WeasyPrint-specific `page-break-inside`/`page-break-after`
  quirks need CSS tuned specifically for them - a rule that's fine for a
  live website's print stylesheet can force an entire heading, admonition,
  or code block onto a blank page in WeasyPrint's own paginated output.

## Pipeline

A typical caller builds a PDF roughly like this, for each page in a
project's nav, then once for the whole concatenated document:

```python
from zendoc.pdf.css import build_css
from zendoc.pdf.html import build_page_anchor_map, fix_up_page_html
from zendoc.pdf.lua import build_lua_filter
from zendoc.pdf.mermaid import render_mermaid_diagram

# Once, up front, across every page in the build:
page_anchor_map = build_page_anchor_map(nav_markdown_files)

# Per page: render through Zensical's own Markdown pipeline first...
rendered_html = zensical_render(markdown_source, page_path)

# ...then fix up the result for Pandoc/WeasyPrint:
fixed_html = fix_up_page_html(
    rendered_html,
    current_docs_rel_path=page_path,
    docs_dir=docs_dir,
    page_anchor_map=page_anchor_map,
    render_mermaid=lambda source: render_mermaid_diagram(
        source, mmdc_bin, mermaid_output_dir, next_diagram_index()
    ),
)

# Once, for the whole build: concatenate every page's fixed_html into one
# HTML document, then hand it to Pandoc alongside a generated Lua filter
# and compiled CSS:
lua_filter = build_lua_filter(heading_numbering_enabled=True, mathjax_available=True,
                               math_dir=math_dir, tex2svg_script=tex2svg_script)
css = build_css(main_font="Inter", mono_font="JetBrains Mono",
                 copyright_text="Copyright 2026", site_name="My Report")

# pandoc concatenated.html -o out.pdf --pdf-engine=weasyprint \
#   --lua-filter=filter.lua --css=compiled.css -f html
```

## `zendoc.pdf.html`

```python
fix_up_page_html(
    html: str,
    *,
    current_docs_rel_path: str,
    docs_dir: str,
    page_anchor_map: dict[str, str],
    is_index: bool = False,
    is_appendix: bool = False,
    repo_url: str = "",
    admonition_icon_config: dict[str, Any] | None = None,
    icon_registry: dict[str, str] | None = None,
    render_mermaid: Callable[[str], str | None] | None = None,
) -> str
```

The main entry point - applies every HTML fixup a page needs, in the order
they need to happen, and returns the fixed-up HTML to feed to Pandoc.
`current_docs_rel_path` is this page's own docs-directory-relative path
(e.g. `"starthere/installtooling.md"`); `page_anchor_map` is shared across
every page in the build (see below), used to rewrite cross-page links to
in-document anchors. `is_index` marks this as the document's cover page -
every heading on it becomes decorative (unnumbered/unlisted/hidden), and
its content is wrapped in a `.cover-page` div. `is_appendix` gives this
page's first heading an `appendix` class, for `zendoc.pdf.lua`'s own
`Header()` handler to letter instead of number it.

A few standalone helpers are exported separately, since a caller building a
multi-page PDF needs to call them once, up front, across every page - not
just from within `fix_up_page_html` itself:

| Function | Purpose |
|---|---|
| `build_page_anchor_map(md_files)` | Maps each nav markdown file to a deterministic in-document anchor id, for cross-page link rewriting. |
| `build_virtual_page_map(md_files)` | Same mapping, keyed by Zensical's own clean-URL "virtual directory" path instead of the raw filename. |
| `virtual_page_path(docs_rel_path)` | The clean-URL virtual directory a single page's path maps to. |
| `to_base64_data_uri(img_src, base_dir)` | Resolves a (possibly relative) image src to an absolute path and returns it as a base64 `data:` URI. |

`render_mermaid`, if given, is called with each Mermaid diagram's own source
text and should return an image src (a file path or `data:` URI), or `None`
if rendering failed - see `zendoc.pdf.mermaid.render_mermaid_diagram` for a
ready-made renderer to wire up as this callback.

## `zendoc.pdf.lua`

```python
build_lua_filter(
    heading_numbering_enabled: bool,
    mathjax_available: bool,
    math_dir: str,
    tex2svg_script: str,
) -> str
```

Generates the complete Pandoc Lua filter source as a string - write it to a
file and pass it to Pandoc with `--lua-filter=`. `math_dir` is where a
pre-rendered formula's SVG is written; `tex2svg_script` is a Node script
that renders one TeX formula to SVG (formula on stdin, SVG on stdout,
invoked as `node tex2svg_script <display|inline>`) - both are ignored when
`mathjax_available` is `False`. Handles:

- Chapter-number/appendix-letter prefixing on every heading, carried over
  onto figure/table caption numbers too.
- Reconstructing `pymdownx.blocks.tab`'s tabbed-set HTML into one
  header/body pair per tab (each tab's label is rewritten to its own `<p>`
  by `zendoc.pdf.html` first, since Pandoc's HTML reader would otherwise
  merge adjacent inline labels into one unseparated run of text).
- Pre-rendering TeX math to static SVGs via a Node `tex2svg`-style script,
  since WeasyPrint has no JS engine to run MathJax client-side.
- Inserting the generated Table of Contents at its own heading.

## `zendoc.pdf.css`

```python
build_css(
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
) -> str
```

Generates the complete compiled CSS a PDF needs, layered on top of a
project's own website stylesheet (the caller is expected to concatenate its
own theme CSS/`extra.css`/print stylesheet underneath this). Covers running
header/footer boxes, footnotes anchored via `float: footnote`, and
WeasyPrint-specific page-break tuning for headings, paragraphs, tables,
code blocks, figures/captions, admonitions, tabbed sets, and grid cards -
every rule here exists because a plausible-looking print CSS rule (`avoid`
where `auto` was needed, or vice versa) forced a real, confirmed blank-page
gap or an orphaned heading in WeasyPrint specifically. Values a project's
own config controls (fonts, page size/margins, header/footer styling,
reference-list spacing) are function parameters, substituted into the
generated CSS.

`reference_style_global` mirrors a project's own website-side reference-
style choice: `False` (the default, "european") gives every
`.reference`/`.acronym`/`.glossary` paragraph tight, single-line spacing
with no indent between entries; `True` ("global") gives `.reference`
paragraphs (only) double spacing between entries with a hanging indent on
wrapped lines (the common APA/MLA/Chicago style). These three classes have
no equivalent styling on a website without a `.md-typeset`-style ancestor
wrapper - Pandoc's HTML output has none, so `build_css()`'s own plain,
unscoped selectors are what actually applies either style in a PDF.

## `zendoc.pdf.icons`

```python
admonition_icon_svg(
    adm_type: str,
    admonition_icon_config: dict[str, Any] | None,
    icon_registry: dict[str, str],
) -> str | None
```

Zensical's own admonition HTML has no icon markup at all in a standalone
document - the website draws one via a CSS trick referencing a theme asset
that doesn't exist outside it. `discover_icon_dirs()`/`build_icon_registry()`
find and index the same Material/Zensical/FontAwesome `.icons` directories a
project's own icon shortcodes already draw from, so `admonition_icon_svg()`
can resolve an admonition type to its accent-coloured icon SVG markup for
`zendoc.pdf.html` to insert.

## `zendoc.pdf.mermaid`

```python
render_mermaid_diagram(
    diagram_source: str,
    mmdc_bin: str,
    output_dir: str,
    index: int,
    timeout: int = 60,
) -> str | None
```

Pre-renders one Mermaid diagram's source to a static SVG via a local
[mermaid-cli](https://github.com/mermaid-js/mermaid-cli) install, since
WeasyPrint has no JS engine to run Mermaid.js client-side. Forces Mermaid's
`htmlLabels` option off internally, so diagram labels render as plain SVG
text WeasyPrint can actually display, instead of the `<foreignObject>`-based
default it silently can't.

## Status

Ported from [zendoc-template](https://github.com/buckwem/zendoc-template)'s
own `build_pdf.py` (see [zendoc-template#96](https://github.com/buckwem/zendoc-template/issues/96)),
where it's still the production build script as of this release -
`zendoc-template` hasn't yet been cut over to import from here. No formal,
versioned public API contract yet either (see
[zendoc-extension#7](https://github.com/buckwem/zendoc-extension/issues/7)) -
import whatever's needed directly, the same informal way as the rest of
this package.
