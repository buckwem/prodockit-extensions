---
icon: lucide/link-2
---

{{ heading_counter_reset(page) }}

# Zensical coupling {: #coupling-zensical-coupling }

\index{Zensical coupling} Prodockit integrates with Zensical mainly through
its documented command-line build and the website that build produces. One
feature still depends on an undocumented Zensical Python implementation
detail. This page explains that dependency and the controls that contain it.

## Supported boundaries {: #coupling-supported-boundaries }

The public PDF implementation uses these supported boundaries:

| Need | Boundary |
| --- | --- |
| Build a website | `zensical build --clean --config-file ...` |
| Identify the installed release | `zensical --version` |
| Read project settings | Prodockit's own TOML/YAML reader |
| Obtain rendered pages for a PDF | Completed HTML under `site_dir` |
| Obtain theme admonition icons | Compiled CSS under `site_dir` |
| Read page front matter | Source Markdown YAML |
| Test the real integration | An installed wheel invoking the Zensical CLI |
/// table-caption | <
    attrs: {id: tab-devcons-zensical-coupling-supported-boundaries}

Supported boundaries
///

The public `prodockit pdf` command follows these boundaries. It runs a clean
Zensical build before extracting the configured pages from the completed
site.

Zensical's CLI commands are supported interfaces. Generated HTML and CSS are
still formats that can evolve, but they are the product of the documented
build and can be validated without importing Zensical's implementation.

The project reader deliberately implements only the settings Prodockit uses.
It does not attempt to reproduce Zensical's private resolved configuration.
Zensical remains the authority for building the website.

## Final Zensical dependency {: #coupling-remaining-api }

The public execution paths have one private Zensical Python contract:

```text
ContextPreprocessor.from_markdown(markdown).page.path
```

During a Zensical build, each page is converted by a fresh Python-Markdown
instance. The documented Markdown extension interface supplies that instance,
but not the source path it represents.

Current-page identity is required to:

- assign headings, labelled figures and tables, references, citations,
  glossary terms and bibliography entries to their source page;
- clear only one page's stale registry records during a live rebuild;
- select the correct chapter or appendix counters;
- distinguish a same-page `#fragment` from a cross-page link; and
- calculate the correct relative link from a page in a nested directory.

The target alone is not sufficient. For example, a target in `references.md`
needs a different link from `index.md` than it does from
`guide/installation.md`.

Prodockit exposes the interface it would ideally receive from Zensical:

```python
current_page_path(markdown) -> str | None
```

All knowledge of the current private representation is isolated in
`prodockit._zensical_page_context`. Feature extensions call Prodockit's
adapter and never import or inspect Zensical internals. If Zensical exposes a
public equivalent, only that adapter needs to change.

!!! warning "Why this cannot fail silently"
    Treating a moved API as “no page context” can let the build succeed while
    cross-page references become `??`. The adapter therefore distinguishes an
    ordinary non-Zensical Markdown conversion from a changed or broken
    Zensical contract. The latter produces a warning naming the failed
    contract and installed `zensical --version`.

The compatibility tests cover a removed `ContextPreprocessor`, a changed
factory signature, a missing or null `page.path`, an unusable path value, an
import failure inside an installed Zensical, and Zensical genuinely not being
installed. Only the last case is treated as an ordinary absence of page
context.

### Can it be removed? {: #coupling-can-page-context-be-removed }

Not as a safe drop-in change with the currently documented Zensical and
Python-Markdown interfaces. The investigation tested the plausible
alternatives rather than assuming the private representation was necessary:

| Alternative | Finding |
| --- | --- |
| Process completed HTML | The output identifies its page, but it arrives after the Markdown extensions have assigned numbers, selected and cleared registries, and resolved links. Replacing those operations would be a substantial redesign and would also need an equivalent for `zensical serve`. |
| Read Zensical's links processor | It is another private representation, is added later in the rendering lifecycle, and would only exchange one undocumented dependency for another. |
| Delegate links to Zensical autorefs | A real build experiment produced correct clean links from nested pages, but using the generated `<autoref>` protocol would add another undocumented dependency. Rewriting reference syntax before inline parsing would be substantial, and autorefs still would not provide the page ownership needed by numbering and registries. |
| Infer the page from its Markdown | Identical, empty, generated, macro-expanded and non-navigation pages make content matching ambiguous. |
| Obtain the page through macros | Page fields are not documented, macros are optional, and macro rendering can be disabled for a page. |
| Configure `source` on the extension | One static configuration value cannot vary for every page in the build. |
| Use root-relative or absolute URLs | These break subpath deployments, offline output or movable sites. |
/// table-caption | <
    attrs: {id: tab-devcons-zensical-coupling-can-it-be-removed}

Can it be removed?
///

Processing completed build output remains the right way to remove private
Zensical APIs from the PDF pipeline. It is not a replacement for current-page
identity inside extensions that must also work during an ordinary website
build and live preview.

A hidden rollback command, `prodockit pdf-legacy`, also retains:

```text
zensical.config.parse_config()
zensical.markdown.render.render()
```

These calls are deliberately confined to `pdf/config.py`. They no longer run
through the public `prodockit pdf` command and remain only so a release can be
diagnosed or rolled back while the new renderer settles. Removing the hidden
legacy command must remove both imports and their architecture-inventory
entries at the same time.

Prodockit also needs the active heading slugifier and separator from
Python-Markdown's configured TOC extension. Python-Markdown documents its
extension registries and both TOC configuration options, but does not expose
a public method that returns their resolved values from an already-configured
Markdown instance. The current representation is:

```text
markdown.treeprocessors["toc"].slugify
markdown.treeprocessors["toc"].sep
```

This representation is isolated in `prodockit._markdown_toc`, behind the
interface Prodockit would ideally consume:

```python
toc_slugging(markdown) -> TocSlugging | None
```

The heading extension never inspects the processor itself. If the registered
processor exists but its representation has changed, the adapter raises a
distinct compatibility error and the build warns once that cross-page
references to automatically generated heading ids may remain unresolved.

## Migration progress {: #coupling-removed-dependencies }

Issue #561 removed these undocumented dependencies from production code:

- `zensical.config.get_config()` and its process-global state;
- `zensical.version()` as a Python call;
- the macro environment's private `env.conf` attribute;
- Zensical's installed `templates/.icons` directory layout;
- private Zensical test helpers such as `ContextExtension`, `Page` and
  `MacroEnv`.

The built-site renderer has replaced the legacy renderer in the public
command after matching it on complete real documents, including Mermaid,
maths, cover markers, index entries, assets and pagination. The old path is
now available only through the hidden rollback command.

## Architecture controls {: #coupling-controls }

The boundary is enforced in several layers:

1. An AST test inventories every static or literal dynamic production import
   whose module begins with `zensical`. It permits only the page-context
   adapter and the hidden legacy implementation in `pdf/config.py`; a new
   import anywhere else fails CI. Removing the rollback command must remove
   the PDF entries.
2. Unit tests exercise genuine absence, removed symbols, changed signatures,
   missing values and internal import failures at the page-context boundary.
3. Documentation rendering tests run the public Zensical build and inspect
   its generated pages.
4. Installed-wheel acceptance tests build a real site and PDF on Windows,
   Ubuntu and macOS, across x64 and Arm64 runners.
5. The acceptance harness checks page order, metadata, cross-page
   references, steps, trees and optional renderers rather than merely
   checking an exit status.
6. A second AST guard confines direct access to the registered Python-Markdown
   TOC processor to `_markdown_toc.py`.

### Forward-reference regression {: #coupling-forward-reference-regression }

The installed-wheel acceptance test includes the reported issue #512 shape:

- an earlier Markdown page refers to two figures defined in a later page;
- both figure-caption blocks are nested beneath an ordered-list item using
  four-space indentation;
- the source and target pages are in different nested directories;
- the references resolve to `Figure 3.1` and `Figure 3.2`;
- their final links contain the correct `../` traversal and Zensical clean
  directory URLs; and
- neither reference contains the unresolved `??` marker.

Focused integration tests separately exercise the original `Figure 2.1` and
`Figure 2.2` report, same-page fragments, nested relative paths, pages not
rendered in the current Python context and live-reload invalidation. This
combination protects both the Markdown behaviour and the real documented
`zensical build` boundary.

## Generated-output coupling {: #coupling-generated-output }

Processing a documented build removes Python API coupling, but its output
still has a contract. Prodockit currently locates:

- `article.md-content__inner.md-typeset` in each generated page;
- page paths derived from `use_directory_urls`;
- local stylesheets linked from the generated index page; and
- `--md-admonition-icon--TYPE` CSS variables containing SVG data URIs.

Each lookup validates what it found and raises a focused error when the
expected structure is absent. Local stylesheets are processed in cascade
order, and external stylesheets are never fetched. This makes a layout change
visible and recoverable without depending on an installed package path.

The article extractor removes website controls that Zensical places inside
the article rather than in the surrounding theme: direct action or promotion
links, direct article footers, tags and feedback controls. These are not
document content and otherwise produce edit buttons, feedback rules or even a
blank final PDF page. Unit tests cover every excluded shape.

The direct config reader also carries Zensical's documented Material-theme
font defaults, Roboto and Roboto Mono. A source config does not have to name
them, while Zensical's former resolved mapping did. Omitting that distinction
changed line wrapping on adopted sites even though their source configuration
had not changed.

### Full-build plugin output {: #coupling-full-build-plugins }

A documented build runs the complete Zensical plugin lifecycle. The private
`zensical.markdown.render()` baseline does not. Most sites therefore produce
the same article through both paths, but a plugin that adds or restructures
page content during a full build can deliberately make the public PDF
different. That is not generated website chrome and must not be stripped by a
generic selector: it is part of the completed document requested from
Zensical.

The external acceptance corpus includes this case. FastAPI's ordinary pages
render identically, while its generated API reference uses plugin-produced
semantic HTML and differs from the legacy private-render output. The
public renderer preserves the completed build, including clearer separation of
type/default labels that the legacy PDF merges. Promotion testing records
such differences separately from content loss or visual regressions.

## Regression testing a Zensical upgrade {: #coupling-regression-testing }

For a Zensical update:

1. Run the full test suite and the installed-wheel matrix.
2. Build the documentation website and PDF from a clean checkout.
3. Check cross-page `\ref`, `\citeref` and `\gls` resolution explicitly;
   these are the features that depend on current-page context.
4. Compare the generated PDF and site with the accepted release, because an
   icon or theme change can alter output while every command still exits
   successfully.
5. Confirm the adapter test against the new release before changing the
   exact dependency pin.

## Desired upstream API {: #coupling-desired-upstream-api }

The final private dependency disappears when a Markdown extension can obtain
the current source page through a supported Zensical interface during both
`zensical build` and `zensical serve`. The minimum useful contract is a stable
function or documented Markdown attribute that returns a docs-directory-
relative source Markdown path, returns `None` outside page rendering, and
does not use the same result for a broken contract. Prodockit does not require
access to Zensical's `Page`, context preprocessor or internal configuration
objects.

## Related {: #coupling-related }

- [Implementation limitations](limitations.md) covers HTML and CSS shape
  coupling rather than Python APIs.
- [Version pinning and drift](pinning-drift.md) covers controlled dependency
  updates.
- [PDF internals](pdf-internals.md) describes how the completed website is
  assembled into a PDF.
