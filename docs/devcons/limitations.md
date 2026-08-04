# Limitations and workarounds

Confirmed \index{limitations} across prodockit's three surfaces - the Python-
Markdown extensions, `prodockit.pdf`, and `prodockit.zensical_macros` -
and the workaround each one gets, so a project hitting unexpected output
has somewhere to check *why* before assuming it's a bug.

## Extensions {: #limitations-extensions }

**Cross-page resolution can go stale under `zensical serve`'s live
reload**: every prodockit extension that resolves something defined on a
*different* page (`prodockit.refs`' `\ref{id}`, `prodockit.citations`/
`prodockit.glossary`'s definitions, `prodockit.bibliography`'s `\cite{id}`/
`\bibliography`, and `prodockit.headings`' own continuous-numbering
pre-scan) does so via a pre-scan of every nav page's raw text, since
`zensical build`'s single, one-shot pass can't otherwise resolve a forward
reference to a page it hasn't rendered yet. Under `zensical build` that's
all it has to do. Under `zensical serve`, the pre-scan itself now picks up
an edited or deleted definition correctly (keyed on every page's mtime/
size, not just computed once at server startup) - but that only fixes what
a page's *own* re-render sees, not whether Zensical re-renders that page at
all: verified directly against a live `zensical serve`, editing page A does
not cause page B to re-render, so B's own displayed output still only
catches up once B itself is rebuilt (e.g. by editing it, or restarting the
server) → no full fix available here, since that half is Zensical's own
incremental-rebuild behaviour, not prodockit's.

**Duplicate heading names across pages**: `prodockit.headings`' automatic
Zensical registry sharing (see [Sharing a registry across a multi-page
build](../extensions/headings.md#sharing-a-registry-across-a-multi-page-build))
logs a warning and keeps the first registration rather than raising, and
*which* page's registration wins isn't stable across builds - see the
warning admonition partway through that same section for why, and the fix
(an explicit, unique, page-prefixed id via `attr_list`).

**`prodockit.bibliography` matches a single citation key only** -
`\cite{id1,id2}` isn't supported, unlike `prodockit.citations`' own
`\cite{id1,id2,...}` → falls through as literal text rather than being
silently mishandled; see [Comparing the two
approaches](../extensions/bibliography.md#comparing-the-two-approaches) for
why.

**`prodockit.index`'s nested sub-entries are visually capped at three
levels**: `\index{Parent!Child!Grandchild}` nests correctly to any depth
the parser itself supports, but the generated index's own CSS only
defines an indent step up to the third level → a fourth level and beyond
is clamped to that same, deepest available indent rather than continuing
to step outward.

## PDF generation {: #limitations-pdf-generation }

`prodockit.pdf` pipes your site's own rendered HTML through Pandoc and
WeasyPrint to produce the PDF - two tools with their own reader/writer
quirks and no JS engine, quite different from a browser rendering your
live website. This section documents the confirmed limitations that
shape `prodockit.pdf.html`/`.lua`/`.css`, and the workaround each one gets.

**No JS engine (WeasyPrint can't run client-side JS)**

- Mermaid diagrams: no JS engine to run Mermaid.js client-side → each
  ` ```mermaid ` fence is pre-rendered to a static SVG via `mermaid-cli`
  before Pandoc ever sees it (see [`prodockit.pdf.mermaid`](../pdf.md#prodockitpdfmermaid)).
    - Mermaid's default node/edge labels are HTML `<foreignObject>`
      content, which WeasyPrint's SVG renderer can't display (text
      silently vanishes) → `htmlLabels` is forced off, so Mermaid emits
      plain SVG `<text>`/`<tspan>` labels instead.
- Math (`$...$`/`$$...$$`, `pymdownx.arithmatex`): no JS engine to run
  MathJax client-side → each formula is pre-rendered to a static SVG via
  a Lua filter `Math()` handler piping to a `tex2svg` script (see
  [`prodockit.pdf.lua`](../pdf.md#prodockitpdflua)).
    - `arithmatex`'s *generic*-mode math (`<div class="arithmatex">`/
      `<span class="arithmatex">`) has no native Math AST node in
      Pandoc's *HTML* reader (unlike its *markdown* reader, which
      recognises `$...$` as a real Math node) → matched by CSS class in
      dedicated `Div()`/`Span()` Lua handlers instead of the `Math()`
      function.

!!! warning "Both renderers are optional, and their absence is announced"

    `mermaid-cli` and the `tex2svg` script are external Node tools, not
    Python dependencies, so neither is guaranteed to be present. When one
    is missing, the affected content is left exactly as it is rather than
    failing the build - a document with no diagrams and no maths should
    never need either tool installed.

    The catch is that a document which *does* use them then gets a PDF
    containing raw `flowchart LR ...` source or literal LaTeX, with
    nothing having gone wrong as far as the build is concerned. Since
    0.12.0, `prodockit pdf` prints a warning naming the missing renderer
    and how to install it whenever that combination occurs.
- A live site's own header repo widget (release/version info) fetches it
  client-side via JS; Pandoc/WeasyPrint has no JS engine to do the same →
  a project embedding similar info in a PDF cover page needs to fetch and
  substitute it directly before the page ever reaches `build_pdf()`.

!!! warning "The website and the PDF resolve the release differently"

    The two release values come from deliberately different sources, and
    they can disagree:

    | | Source |
    | --- | --- |
    | `{{ release }}` (website, and any macro-rendered page) | `git describe --tags` on the local checkout |
    | `{RELEASE}` (PDF cover marker) | The host's releases API |

    Each is right for its own context. `{{ release }}` is re-evaluated on
    every website rebuild, including every save under `zensical serve`, so
    it must not make a network call. `{RELEASE}` serves a cover page that
    isn't part of a macro-rendered site at all, so a local git lookup isn't
    always available to it.

    They diverge when a tag exists with no published release (the website
    shows a version, the PDF drops the line), when a release exists but the
    checkout has no tags (the reverse - usually a shallow clone), and during
    the window in a release where the version-bump commit is pushed before
    its tag.

    Since 0.16.0 neither is silent about it: `prodockit pdf` warns when the
    two will show different things, and the macros pass warns when
    `{{ release }}` came back empty *because* the clone was shallow, naming
    `fetch-depth: 0` / `GIT_DEPTH`. A project with no tags at all is a
    normal state and says nothing.

    If you need them guaranteed identical, set the value explicitly rather
    than relying on either mechanism.

**Multi-page → single-document concatenation**

- A link that resolves fine on a website (a separate page) has nothing to
  point at once every page is concatenated into one PDF - Pandoc treats it
  as a link to an external file at whatever absolute path the PDF happened
  to be built from → rewritten to in-document anchors instead (see
  `build_page_anchor_map()`/`build_virtual_page_map()` in
  [`prodockit.pdf.html`](../pdf.md#prodockitpdfhtml)).
- Local image/file references can't depend on relative paths resolving
  correctly from wherever Pandoc happens to run in a standalone document →
  base64-embedded as `data:` URIs directly in the HTML (see
  `to_base64_data_uri()`).
- A PDF has no light/dark toggle to make the mkdocs-material/Zensical
  `#only-light`/`#only-dark`/`#gh-light-mode-only`/`#gh-dark-mode-only`
  image convention meaningful → the `#only-dark`/`#gh-dark-mode-only`
  half of a pair is dropped entirely rather than embedded, since
  `to_base64_data_uri()`'s resulting `data:` URI has no trace of the
  fragment left for any stylesheet to hide it by (this used to leave both
  halves of every such pair permanently visible, stacked one after the
  other).
- A CSS `url()` reference (e.g. in your own website stylesheet, passed via
  `extra_css`) resolved relative to wherever Pandoc runs is meaningless
  (and can leak a local file path) to anyone reading the PDF → a project
  passing its own CSS through `extra_css` should rewrite any such
  reference to a stable, absolute URL (e.g. the file's canonical GitHub/
  GitLab "blob" URL) before handing it to `build_pdf()`.

**Raw `<svg>` doesn't survive Pandoc's HTML→HTML round trip through to
WeasyPrint at all** (confirmed directly, isolated test) - affects
admonition icons, grid-card title icons, and pre-rendered Mermaid diagrams
alike → every `<svg>` is converted to a base64 `data:` URI `<img>` instead
(see [`prodockit.pdf.icons`](../pdf.md#prodockitpdficons)).

**Content tabs (`pymdownx.blocks.tab`)**: each tab's label renders as an
inline `<label>` sibling with no block boundary between them; Pandoc's
HTML reader merges adjacent inline-level siblings with no block boundary
into one `Plain` block, collapsing every label in a tabbed-set into one
unseparated run of text with no way to recover the boundary afterward in a
Lua filter → each `<label>` is rewritten into its own `<p>` *before*
Pandoc's reader ever sees it, then the Lua filter reconstructs the
`tabbed-set`/`tabbed-labels`/`tabbed-content` structure into a `tabbox`
shape (see [`prodockit.pdf.lua`](../pdf.md#prodockitpdflua)).

**Figure/table captions in "prepend" position**: Pandoc's `Figure` AST
node stores `Caption` and content as two separate, independently-typed
fields rather than ordered children reflecting DOM position, and Pandoc's
own HTML writer always re-emits a `Figure`'s `<figcaption>` *after* its
content when serializing back to HTML - confirmed directly (a
`<figcaption>` placed first in source HTML still comes out last from
Pandoc's own HTML writer), discarding "prepend" positioning entirely
regardless of input order → any figure/table whose caption comes first is
retagged from `<figure>` to `<div>` before Pandoc parses it (a `Div`'s
children *are* emitted in original document order), with the
`<figcaption>` unwrapped into the div's first child block.

**Pandoc's native `Para` AST node has no attribute field at all** (unlike
`Div`/`Header`/`CodeBlock`/`Table`/`Figure`, which all carry one) -
confirmed: a `<p id="..." class="...">` comes out the other end as a bare
`Para` with both the `id` and the `class` silently gone, with no error.
This is exactly the shape every `attr_list` citation/acronym/glossary
definition takes (see [prodockit.citations](../extensions/citations.md)/
[prodockit.glossary](../extensions/glossary.md)) → any `<p>` carrying an `id` or
`class` is retagged to a `<div>` instead (which Pandoc's reader does
preserve attributes on).

**Lightbox-wrapped images**: an `<a class="glightbox">` wrapping an
`<img>` resolves its `href` one directory level differently than the
`<img>`'s own `src` (an artifact of Zensical's URL cleaning), which
Pandoc/WeasyPrint then fails to resolve as a broken link → the lightbox
`<a>` is unwrapped, leaving just the `<img>`.

**Embedded `<iframe>` (e.g. a YouTube video)**: left as-is, produces a
stray unwanted heading in the compiled PDF (WeasyPrint attempts to fetch
the iframe's `src`, and something in that response ends up parsed as real
page content) → replaced with a link-styled reference to the video instead
- a static PDF can't embed a live video player regardless.

**No Jinja evaluation**: Pandoc/`prodockit.pdf` never evaluates Jinja - a
`{{ site_name }}` placeholder that resolves via macro evaluation on the
live site (see [prodockit.zensical_macros](../macros.md)) is left as literal
text unless a project substitutes it directly in its own page HTML before
handing it to `build_pdf()`.

**No `.md-typeset` wrapper**: unlike a Zensical website, Pandoc's HTML
output has no `.md-typeset` wrapper element, so website CSS rules scoped
to `.md-typeset ...` (reference/acronym/glossary spacing, a `.screenshot`
class, and so on) never match in the PDF → `prodockit.pdf.css` duplicates the
relevant rules as plain, unscoped selectors instead (see
[`prodockit.pdf.css`](../pdf.md#prodockitpdfcss)).

**Footnotes**: Pandoc's default behaviour collects every footnote in the
whole document into one section at the very end of the PDF, rather than at
the bottom of the page it's referenced on like a printed book → a Lua
filter handler replaces each footnote reference with an inline span styled
via CSS `float: footnote` instead (see [`prodockit.pdf.lua`](../pdf.md#prodockitpdflua)/
[`prodockit.pdf.css`](../pdf.md#prodockitpdfcss)).

**WeasyPrint's CSS Grid support is too limited to trust for an actual
side-by-side multi-column layout** → a Zensical grid-cards block renders
as one full-width stacked box per row instead of a real grid.

**`<figcaption>` centering doesn't extend to its sibling `<img>`**:
WeasyPrint's UA stylesheet centers `<figcaption>` text by default via
`text-align`, but that doesn't affect the sibling image, which stays
left-aligned and visibly misaligned under its own caption → explicit CSS
centers the whole figure/wrapping element instead.

**Two-space vs. four-space nested-list indentation discrepancy**:
Pandoc's markdown reader nests a sub-list at just 2-space indentation (no
4-space requirement), unlike Python-Markdown's stricter 4-space rule.
Only relevant if you write markdown by hand for a *separate* Pandoc-only
input rather than feeding `prodockit.pdf` your already-rendered HTML (the
normal, documented path) - the HTML-based pipeline sidesteps this
entirely, since Pandoc's HTML reader has no such indentation rule to
begin with.

**General "every markdown extension needs its own bespoke translation"
limitation, and why `prodockit.pdf` avoids it**: Pandoc is a completely
different parser from Python-Markdown/Zensical, so a pipeline built
around hand-translating each markdown feature into a Pandoc-compatible
dialect needs a new bespoke translation for every extension a project
enables (admonitions, tabs, grid cards, captions, `attr_list` spans,
`{% if %}` conditionals, and so on) - fragile, and it grows without bound.
`prodockit.pdf` sidesteps this by feeding Pandoc your site's own already-
rendered HTML (via `zensical.markdown.render.render()`, the same pipeline
that builds your live website) instead of raw markdown - Pandoc's own HTML
reader already understands standard HTML correctly, with no per-feature
translation needed. The fixups documented above are what's left after
that: genuine gaps in Pandoc/WeasyPrint's own HTML handling, not gaps in
markdown-dialect translation.

**`prodockit.bibliography` is a partial exception to this pattern, worth
flagging explicitly**: resolving `\cite{id}`/`\bibliography` itself calls
out to a *separate*, independent `pandoc --citeproc` invocation at
markdown-render time (see
[prodockit.bibliography](../extensions/bibliography.md#bibliography-requirements)) -
unrelated to, and already finished well before, `prodockit.pdf`'s own
`pandoc --pdf-engine=weasyprint` call below. By the time `prodockit.pdf`
sees the page, citations and the reference list are already resolved,
ordinary HTML - `id`-bearing `<div>`s and `<a>` links like any other
content - so none of the fixups documented above apply to it specially;
a build using both ends up invoking Pandoc twice, for two entirely
unrelated reasons.

## Website macros {: #limitations-website-macros }

**`heading_counter_reset(page)` inherits the same `zensical serve`
staleness bound as extensions above**: it calls
[`prodockit.headings.prescan()`](../extensions/headings.md#looking-up-the-same-numbers-from-your-own-build-tooling)
directly - the identical pre-scan continuous numbering itself uses - so a
page's displayed chapter/section number can lag behind an edit to an
*earlier* page's heading count until that later page is itself rebuilt
under `zensical serve`'s live reload. Not an issue for a one-shot
`zensical build`.

**`{{ repo_url }}` reflects the local checkout's own git remote, not
`project.repo_url`**: computed from `git config --get remote.origin.url`
directly, deliberately, so it reflects wherever *this* checkout actually
points (e.g. a CI job's own token-embedded remote, stripped before
display) - in practice this usually, but isn't guaranteed to, match
`zensical.toml`'s configured `repo_url` (used elsewhere for the sidebar
repository link). A fork or a differently-configured clone can show a
different URL from the two.

**`{{ word_count }}` assumes the first page in `nav` is a cover page** and
unconditionally excludes it from the count, on top of any page explicitly
flagged `exclude_from_word_count: true` - a project whose `nav` doesn't
start with a dedicated cover page gets a word count silently short by
that first page's own prose.

**`heading_counter_reset()`/`reference_style()`/`acronym_style()`/
`glossary_style()` all emit CSS targeting Zensical/Material for MkDocs'
own internal class names and counters** (`.md-typeset`, `.md-nav--secondary`,
`counter(h1-count)`/`counter(toc1)`, and so on) - undocumented
implementation details of the theme itself, not a public API it commits
to - so a future Zensical theme restructuring could change or remove them
without warning, silently breaking the numbering/spacing display with no
error raised.

These CSS-shape couplings are the theme-side counterpart to the Python
ones - see [Zensical coupling](zensical-coupling.md) for the full list of
undocumented Zensical APIs prodockit depends on, and what regression
testing a Zensical upgrade actually needs.
