# Release Notes

## 0.10.0 (2026-07-15)

- New `zendoc.zensical_macros`: Jinja variables/macros for Zensical's own
  macros plugin - `{{ word_count }}` (site-wide prose word count, excluding
  the cover page and any page flagged `exclude_from_word_count: true`),
  `{{ repo_url }}` (git-detected repository URL), `{{ site_name }}`, and
  `heading_counter_reset(page)`/`reference_style()`/`acronym_style()`/
  `glossary_style()` macros. Add it alongside a project's own `macros.py`
  via `zensical.toml`'s `modules = ["zendoc.zensical_macros"]` - or use it
  alone if the project has no macros of its own.
- New `zendoc.wordcount`: the generic prose word-count utility
  (`count_words()`/`compute_word_count()`) behind both `zendoc.pdf`'s
  `{WORDCOUNT}`-style cover-page use and `zendoc.zensical_macros`'
  `{{ word_count }}` - previously duplicated independently by each
  downstream project needing both.
- New `zendoc.settings`: `flatten_nav()`, `heading_numbering_enabled()`, and
  `reference_style_values()` - the `project.extra.*` reading shared by
  `zendoc.pdf.config` and `zendoc.zensical_macros`, so the two agree on one
  set of fallback defaults instead of each hand-maintaining its own copy.
  `zendoc.pdf.config.build_pdf_from_zensical_config()` now uses these too
  (previously inlined), and its `pdf_math_dir` setting is now created
  automatically if configured to a directory that doesn't already exist
  (matching the auto-detected default's existing behaviour).

## 0.9.0 (2026-07-15)

- New `zendoc pdf` command: builds a complete PDF with no Python required,
  reading everything - nav, docs directory, fonts, page size, and all
  PDF-specific settings - from the project's own `zensical.toml`, the same
  way `zensical build`/`zensical serve` do. Installing `zendoc` now
  registers a `zendoc` console script (`pip install zendoc` is enough - no
  separate build script to write). See the new `zendoc.pdf.config` module
  (`build_pdf_from_zensical_config()`) for the config-to-`build_pdf()`
  orchestration this wraps: nav-tree flattening, per-page `is_appendix`
  front-matter detection, and auto-detection of a local `mmdc`
  (Mermaid) binary and MathJax `tex2svg` script, so a typical project
  needs no extra configuration beyond what it likely already has.
- `build_pdf()` gained `include_table_of_contents`/`table_of_contents_title`
  parameters (both used automatically by `zendoc pdf`): a generated table
  of contents is now inserted by default, right after a cover page if one
  is marked `is_index=True`, or at the very start otherwise.
- Rewrote the [PDF generation](../pdf.md) docs page around the `zendoc pdf`
  command as the primary, and for most projects only necessary, way to use
  `zendoc.pdf` - `build_pdf()` and the individual pipeline pieces are now
  documented as the advanced, scripting-your-own-pipeline path.

## 0.8.0 (2026-07-15)

- New `zendoc.pdf.build_pdf()`: a one-call convenience wrapper around the
  rest of `zendoc.pdf` - hand it a list of already-rendered pages
  (`zendoc.pdf.Page`) and where to write the PDF, and it fixes up each
  page's HTML, generates the Lua filter and CSS, concatenates everything,
  and runs `pandoc`/WeasyPrint for you. Takes `output_path` (the PDF's own
  destination path) plus font/page-size/margin/header-footer/reference-
  style/numbering/math parameters, all with sensible defaults. Raises the
  new `zendoc.pdf.PdfBuildError` (with the underlying `pandoc` exit code
  and stderr attached) if the build fails, rather than failing silently.
  `zendoc.pdf.html`/`.lua`/`.css`/`.icons`/`.mermaid` remain directly
  importable if you need more control over how the pieces fit together.
- Rewrote the [PDF generation](../pdf.md) docs page around `build_pdf()` as
  the primary documented way to use `zendoc.pdf`, leading with a short,
  practical quick-start example rather than the implementation-level detail
  of how Pandoc/WeasyPrint's own quirks are worked around (that detail is
  still there, now further down, for anyone who wants it).

## 0.7.0 (2026-07-15)

- New `zendoc.pdf`: a Pandoc/WeasyPrint pipeline for building a standalone
  PDF from Zensical-rendered HTML - not a Python-Markdown extension (no
  `markdown.extensions` entry point), a plain function library, since a PDF
  build pipeline isn't a Markdown syntax extension:
    - `zendoc.pdf.html`: `fix_up_page_html()` and link/anchor/image helpers
      - fixes up one page's already-rendered HTML for Pandoc's own reader/
        writer quirks (attribute loss on `<p>`, raw `<svg>` not surviving
        the round trip to WeasyPrint, footnote/caption structural
        mismatches, cross-page link rewriting for a concatenated multi-page
        PDF, and more).
    - `zendoc.pdf.lua`: `build_lua_filter()` - chapter/appendix numbering,
      caption chapter-prefix numbering, tabbed-set reconstruction, and
      MathJax pre-rendering, generated as a parameterized Lua filter.
    - `zendoc.pdf.css`: `build_css()` - the compiled CSS a PDF needs on top
      of a project's own website stylesheet, including WeasyPrint-specific
      page-break tuning for headings, paragraphs, tables, code blocks,
      figures/captions, admonitions, and grid cards.
    - `zendoc.pdf.icons` / `zendoc.pdf.mermaid`: admonition icon resolution
      and Mermaid diagram pre-rendering, as standalone helpers.
  - Fixed a real bug found while writing tests: the iframe→"Watch Video"
    admonition link builder stripped the video id from every single
    conversion (a replace-then-split ordering removed the just-added
    `?v=...` too) - now produces a working YouTube watch link.
  - No formal, versioned public API surface yet (see zendoc-extension#7) -
    import whatever's needed directly, the same informal way as the rest of
    this package.
  - New dependency: `beautifulsoup4` (>= 4.12).
- Broadened the package's own description: zendoc is now framed as a family
  of extensions for Zensical needed for professional and academic
  documentation, rather than "Python-Markdown extensions" specifically -
  `zendoc.pdf` isn't one, and the framing was due to broaden anyway now
  that PDF generation is in scope alongside cross-references/citations/
  glossary.

## 0.6.0 (2026-07-14)

- `zendoc.headings`: new `numbering="continuous"` option (Zensical only) -
  `h1` numbering carries on from wherever the previous nav page left off,
  instead of restarting at 1 on every page. Fixes `\ref{id}` showing the
  wrong number for a heading on a different page (it previously always
  showed that page's own per-document number, not the number actually
  displayed on the page - see zendoc-template#89).
- New `appendix_attr` option (default `is_appendix`): a page whose front
  matter sets this flag is numbered with a letter instead - "A", "A.1",
  "A.1.1" - and doesn't consume a number from the numeric sequence, so
  later pages aren't left with a gap. Letters are assigned sequentially in
  nav order.
- New public `zendoc.headings.prescan(appendix_attr="is_appendix")`
  function: returns the same `(start_counts, appendix_letters)` pre-scan
  `HeadingsExtension` uses internally, for a consuming project's own build
  tooling (e.g. a template macro driving a presentational CSS
  counter-reset) to stay in sync automatically rather than re-deriving the
  same page-order/heading-count logic independently.

## 0.5.1 (2026-07-14)

- `zendoc.glossary`: a resolved `\gls{id}` now always renders with
  `class="zendoc-gls"` (previously it had no class at all), matching
  `zendoc.refs`' always-present base class. The unresolved case now
  renders `class="zendoc-gls zendoc-gls-unresolved"` (previously just
  `zendoc-gls-unresolved`, missing the base class), so a stylesheet has
  one stable hook (`.zendoc-gls`) regardless of resolution state, with
  `.zendoc-gls-unresolved` layered on top only when needed.

## 0.5.0 (2026-07-14)

- New `zendoc.glossary` extension: define a term once via `attr_list` (an
  id plus a `data-term` short display string), then insert it by id from
  anywhere with `\gls{id}`, which resolves to the term's own text, linked
  to its definition - e.g. `\gls{css}` → `CSS`. Unlike `zendoc.citations`'
  `\cite{id}` (which generates new bracketed citation text), `\gls{id}`
  inserts the term's own registered text in place - closer to LaTeX's
  `glossaries` package.
- One shared `GlossaryRegistry` covers both acronym-style and
  glossary-style entries - they're the same kind of thing (an id with a
  short display text), so acronym and glossary pages can reference each
  other, or be referenced from any other page, with no special wiring.
- Supports forward references within a document, an `unresolved` marker
  (`?` by default) for an unknown id, and the same automatic Zensical
  cross-page registry sharing and nav pre-scan (for citing/using a term
  before its defining page has been converted) that `zendoc.citations` got
  in 0.4.0.
- Refactored the nav pre-scan logic (previously private to
  `zendoc.citations`) into a shared, generic
  `zendoc._zensical.preseed_attr_from_nav` helper, since `zendoc.glossary`
  needed the identical scan.

## 0.4.0 (2026-07-14)

Fixes found migrating a real multi-page site's references page to
`zendoc.citations` for real - all discovered by actually building a
real multi-page site, not just single-document tests:

- **Fixed a real correctness bug**: `zendoc.refs`/`zendoc.citations` were
  emitting a bare `#id` fragment for *every* resolved link, including a
  cross-page one - which only works by coincidence in a single concatenated
  PDF document, but 404s on an actual multi-page website (an `#id` fragment
  only navigates within the *current* page). Both now emit a real relative
  link (e.g. `references.md#id`, correctly adjusted for the citing page's
  own directory depth) when the target is on a different page, which
  Zensical already knows how to rewrite into the right clean URL - the
  same way a hand-typed cross-page Markdown link already works.
- New: `zendoc.citations` pre-scans every page in a Zensical build's nav
  for citation definitions before any page is actually converted, so citing
  a source *before* it's defined - the common case, since a references page
  is usually kept at the end of nav as an appendix - resolves correctly in
  a single `zensical build` pass, rather than only working from
  `zensical serve`'s live-reload. New `CitationRegistry.preseed()` method
  backs this; a real registration always supersedes a preseeded stub.
- `RefsExtension` gained a `source` option (mirroring `HeadingsExtension`'s),
  needed for the same-page-vs-cross-page link decision above.
- Fixed the nav pre-scan matching a citation-definition attr_list example
  shown literally inside a fenced code block in documentation - it now
  skips fenced content, the same protection `CitationDefTreeprocessor`
  already gets for free from the real Python-Markdown parser.

## 0.3.0 (2026-07-14)

- New `zendoc.citations` extension: define a source once via `attr_list`
  (an id plus a `data-cite-text` short display string), then cite it by key
  from anywhere with `\cite{id}` (or `\cite{id1,id2,...}` for multiple),
  auto-generating a bracketed, linked citation - `[Skoulikari, 2023]` -
  instead of hand-typing the link and text at every citation site.
- Supports forward references within a document, an `unresolved` marker
  (`?` by default) for an unknown key, and the same automatic Zensical
  cross-page registry sharing (with soft-fail on key collisions) that
  `zendoc.headings`/`zendoc.refs` got in 0.2.0.
- Auto-generating the references page's own listing from structured
  bibliographic data isn't built yet - see the extension's docs for the
  current scope.
- Fixed the `zensical.toml` installation examples in the docs: nested
  `[project.markdown_extensions.zendoc.headings]` tables don't work
  (Zensical only hoists the `pymdownx`/`zensical` namespaces that way) -
  the quoted-key form (`[project.markdown_extensions."zendoc.headings"]`)
  is required.

## 0.2.0 (2026-07-14)

- `zendoc.headings`/`zendoc.refs` now share their registry automatically
  under Zensical, without any explicit `registry`/`source` configuration:
  each extension detects Zensical's per-page rendering context and derives
  a stable `source` from the page's own path, fixing cross-page `\ref{id}`
  references not resolving.
- A heading id collision across two different sources, when detected via
  this automatic Zensical sharing, now logs a warning and keeps the first
  registration instead of raising `DuplicateIdError` - so two unrelated
  pages that happen to share a heading title (e.g. both have an "Overview"
  section) no longer break the build. Explicitly-shared registries (the
  manual multi-page pattern) still raise on a collision, unchanged.
- Fixed an extension-ordering bug: `zendoc.headings` and `zendoc.refs` now
  find and share each other's registry regardless of which order they're
  listed in - previously, only `zendoc.headings`-then-`zendoc.refs` worked
  reliably, and Zensical's own TOML-to-extension-list conversion doesn't
  preserve list order at all.

## 0.1.0 (2026-07-14)

Initial release.

- `zendoc.headings`: heading ids and hierarchical section numbering,
  backed by a shared `IdRegistry`.
- `zendoc.refs`: `\ref{id}` section cross-references, resolving to the
  target's current section number, including forward references within a
  document and across a shared registry.
- Documentation site built with Zensical, published at
  [buckwem.github.io/zendoc-extension](https://buckwem.github.io/zendoc-extension/).
