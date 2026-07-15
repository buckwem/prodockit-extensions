# PDF generation

`zendoc.pdf` builds a standalone PDF from your Zensical site - the kind of
downloadable, submittable document professional and academic reports
commonly need alongside the website itself. It reads the same
`zensical.toml` your site already has, so there's nothing new to learn or
configure beyond a couple of optional settings.

## Requirements

The PDF is built via [Pandoc](https://pandoc.org/) and
[WeasyPrint](https://weasyprint.org/), so both need to be installed and on
your `PATH`:

```bash
pip install weasyprint
```

then follow [Pandoc's own install instructions](https://pandoc.org/installing.html)
for your platform (e.g. `brew install pandoc` on macOS).

## Quick start

From your project root (wherever `zensical.toml` lives):

```bash
zendoc pdf
```

That's it. Every page in your `nav` is rendered, in order, into
`docs/site_documentation.pdf` (or wherever `extra.pdf_output` says - see
below), complete with a generated table of contents, chapter numbering, and
your site's own admonitions, code blocks, tables, and Mermaid diagrams.

If a build fails (a missing `pandoc`, a WeasyPrint error, and so on), the
command prints the underlying error and exits with a non-zero status,
rather than silently producing a broken or missing file.

## Configuration

Everything is read from your project's own `zensical.toml` - nothing is
passed on the command line beyond, optionally, which config file to use:

```bash
zendoc pdf --config-file zensical.toml   # -f for short; this is the default
```

Most of what the PDF needs, it already gets from settings your site likely
has for other reasons: `site_name`, `copyright`, `repo_url`, `docs_dir`,
`theme.font.text`/`.code`, and `theme.icon.admonition`. The rest lives
under `[project.extra]`, all optional:

| Setting | Default | What it does |
|---|---|---|
| `pdf_output` | `"<docs_dir>/site_documentation.pdf"` | Where the PDF is written. |
| `pdf_page_size` | `"A4"` | Any WeasyPrint-supported CSS page size (`"Letter"`, ...). |
| `pdf_margin_top` / `_right` / `_bottom` / `_left` | `"2cm"` each | Page margins, as CSS lengths. |
| `pdf_header_footer_font_size` / `_color` / `_divider_color` | `"10pt"` / `"#555555"` / `"#e2e8f0"` | Running header/footer styling. |
| `heading_numbering` | `true` | Chapter/appendix numbering on headings and captions. |
| `reference_style` | `"european"` | `"european"` (tight, single-line citation entries) or `"global"` (double-spaced, hanging indent - the common APA/MLA/Chicago style). |
| `pdf_include_table_of_contents` | `true` | Whether to generate and insert a table of contents. |
| `pdf_table_of_contents_title` | `"Table of Contents"` | That page's own heading text. |
| `pdf_mmdc_bin` | auto-detected | Path to a [mermaid-cli](https://github.com/mermaid-js/mermaid-cli) `mmdc` binary, for pre-rendering Mermaid diagrams. Diagrams are left unrendered if none is found. |
| `pdf_tex2svg_script` / `pdf_math_dir` | auto-detected | A local MathJax `tex2svg`-style Node script, for pre-rendering TeX math (WeasyPrint has no JS engine to run MathJax client-side). Formulas are left as literal text if none is found. |

A page's own front matter `is_appendix: true` gives it letter-based
numbering ("A", "A.1", ...) instead of numeric, matching
[zendoc.headings](extensions/headings.md)' own `appendix_attr` convention.

## Advanced usage: the Python API

If you're scripting your own build pipeline and want to call into
`zendoc.pdf` directly rather than through `zensical.toml`, `build_pdf()` is
a one-call function you can import instead of shelling out to the `zendoc`
command:

```python
from zendoc.pdf import Page, build_pdf

build_pdf(
    [
        Page(docs_rel_path="index.md", html=rendered_html["index.md"], is_index=True),
        Page(docs_rel_path="chapter1.md", html=rendered_html["chapter1.md"]),
        Page(docs_rel_path="chapter2.md", html=rendered_html["chapter2.md"]),
    ],
    "dist/report.pdf",
    site_name="My Report",
    copyright_text="Copyright 2026 Jane Doe",
)
```

`Page.html` is a page's own already-rendered HTML (not yet fixed up for
Pandoc - `build_pdf` does that internally for you); `Page.docs_rel_path` is
that page's path relative to your docs directory, e.g.
`"starthere/installtooling.md"`. Mark exactly one page `is_index=True` if
you have a dedicated cover/title page - its headings are treated as
decorative rather than real chapters. `build_pdf` raises
`zendoc.pdf.PdfBuildError` with the underlying error message attached if
the build fails.

### `build_pdf`

```python
build_pdf(
    pages: list[Page],
    output_path: str,
    *,
    docs_dir: str = "docs",
    extra_css: str = "",
    repo_url: str = "",
    admonition_icon_config: dict[str, Any] | None = None,
    icon_registry: dict[str, str] | None = None,
    render_mermaid: Callable[[str], str | None] | None = None,
    main_font: str = "Inter",
    mono_font: str = "JetBrains Mono",
    copyright_text: str = "",
    site_name: str = "",
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
    heading_numbering_enabled: bool = True,
    mathjax_available: bool = False,
    math_dir: str | None = None,
    tex2svg_script: str = "",
    include_table_of_contents: bool = True,
    table_of_contents_title: str = "Table of Contents",
    work_dir: str | None = None,
    keep_work_dir: bool = False,
) -> None
```

Its two required arguments are the page list and `output_path` (where the
PDF gets written - any path, absolute or relative; its parent directory
must already exist). Everything else mirrors the `zensical.toml` settings
above one-for-one, plus a few options only meaningful from Python:

**Content**

- `docs_dir`: your project's docs root, used to resolve each page's own
  relative image/link references.
- `extra_css`: your own website stylesheet's content, layered underneath
  the CSS `build_pdf` generates, so its own `!important` rules can still
  override a website-only style that doesn't make sense in a paginated PDF.
- `admonition_icon_config`/`icon_registry`: give an admonition its own icon
  in the PDF (Zensical's admonition HTML has none by default outside a
  website) - see [zendoc.pdf.icons](#zendocpdficons).
- `render_mermaid`: called with each Mermaid diagram's own source text,
  should return an image path/`data:` URI or `None` if rendering failed -
  see [zendoc.pdf.mermaid](#zendocpdfmermaid) for a ready-made renderer.

**Working files**

`pandoc` needs a few intermediate files on disk (the concatenated HTML, the
generated Lua filter, the compiled CSS) - written under `work_dir` if
given, or a fresh temporary directory otherwise (always cleaned up
regardless of `keep_work_dir` - there's no path left to inspect
afterwards). `keep_work_dir=True` with an explicit `work_dir` leaves those
files in place, useful for checking exactly what Pandoc/WeasyPrint received
when a build succeeds but the PDF looks wrong.

### `Page`

```python
@dataclass
class Page:
    docs_rel_path: str
    html: str
    is_index: bool = False
    is_appendix: bool = False
```

One page to include in the PDF. `html` is this page's own already-rendered
HTML (not yet fixed up for Pandoc - `build_pdf` does that for you).
`is_appendix` gives this page's first heading a letter instead of a number
("A", "A.1", ...) if you enable `heading_numbering_enabled`.

### `PdfBuildError`

Raised by `build_pdf` when the underlying `pandoc` invocation fails.
`returncode` and `stderr` are attached for logging or troubleshooting.

## Building your own pipeline

If `build_pdf`'s shape doesn't fit how your project is put together - e.g.
you want to fix up and inspect each page's HTML individually before
concatenating them yourself, or drive `pandoc` with your own extra
arguments - the pieces `build_pdf` is built from are all directly
importable too:

| Module | What it does |
|---|---|
| [`zendoc.pdf.html`](#zendocpdfhtml) | Fixes up one page's rendered HTML for Pandoc's own reader/writer quirks - the biggest piece, and what `build_pdf` calls per page internally. |
| [`zendoc.pdf.lua`](#zendocpdflua) | Generates the Pandoc Lua filter (chapter numbering, caption ordering, tab reconstruction, math). |
| [`zendoc.pdf.css`](#zendocpdfcss) | Generates the compiled CSS a paginated PDF needs on top of your website's own stylesheet. |
| [`zendoc.pdf.icons`](#zendocpdficons) | Resolves an admonition type to its accent-coloured icon SVG. |
| [`zendoc.pdf.mermaid`](#zendocpdfmermaid) | Pre-renders a Mermaid diagram to a static SVG via `mermaid-cli`. |

### `zendoc.pdf.html`

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

Applies every HTML fixup a page needs - a raw inline `<svg>` (icons, emoji,
diagrams) doesn't survive Pandoc's HTML-to-HTML round trip through to
WeasyPrint at all; Pandoc's `Para` AST node has no attribute field,
silently dropping any `id`/`class` a `<p>` carries; a caption meant to
appear *before* its table/figure always ends up *after* it once Pandoc's
own HTML writer re-serializes the page; a multi-page site concatenated
into one PDF document needs cross-page links rewritten to in-document
anchors; and more.

A few standalone helpers, used once up front across every page rather than
from within `fix_up_page_html` itself:

| Function | Purpose |
|---|---|
| `build_page_anchor_map(md_files)` | Maps each page to a deterministic in-document anchor id, for cross-page link rewriting. |
| `build_virtual_page_map(md_files)` | Same mapping, keyed by Zensical's own clean-URL "virtual directory" path instead of the raw filename. |
| `virtual_page_path(docs_rel_path)` | The clean-URL virtual directory a single page's path maps to. |
| `to_base64_data_uri(img_src, base_dir)` | Resolves a (possibly relative) image src to an absolute path and returns it as a base64 `data:` URI. |

### `zendoc.pdf.lua`

```python
build_lua_filter(
    heading_numbering_enabled: bool,
    mathjax_available: bool,
    math_dir: str,
    tex2svg_script: str,
) -> str
```

Generates the complete Pandoc Lua filter source as a string - write it to a
file and pass it to Pandoc with `--lua-filter=`.

### `zendoc.pdf.css`

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

Generates the complete compiled CSS a PDF needs, layered on top of your own
website stylesheet. Covers running header/footer boxes, footnotes anchored
via `float: footnote`, and page-break tuning for headings, paragraphs,
tables, code blocks, figures/captions, admonitions, tabbed sets, and grid
cards - every rule here exists because a plausible-looking print CSS rule
forced a real, confirmed blank-page gap or an orphaned heading in
WeasyPrint specifically.

### `zendoc.pdf.icons`

```python
admonition_icon_svg(
    adm_type: str,
    admonition_icon_config: dict[str, Any] | None,
    icon_registry: dict[str, str],
) -> str | None
```

Resolves an admonition type (note, warning, tip, ...) to its accent-
coloured icon SVG markup. `discover_icon_dirs()`/`build_icon_registry()`
find and index the Material/Zensical/FontAwesome `.icons` directories your
project's own icon shortcodes already draw from.

### `zendoc.pdf.mermaid`

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
WeasyPrint has no JS engine to run Mermaid.js client-side.

## Status

No formal, versioned public API stability contract yet (see
[zendoc-extension#7](https://github.com/buckwem/zendoc-extension/issues/7)).
