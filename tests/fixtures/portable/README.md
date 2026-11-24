# Portable build feasibility prototype

This fixture exercises the initial slice of [issue #1072](https://github.com/buckwem/prodockit-extensions/issues/1072).
The selector is `--portable`, or `-p`. Omit it to use the existing approach.
Both approaches use the same original sources and configuration.

Install this checkout with `pip install -e '.[portable]'`. For bibliography
preparation, supply an installed Pandoc explicitly; the portable prototype does
not install a runtime. For example, from the repository root on macOS or Linux:

```sh
pdk -p build -f tests/fixtures/portable/zensical.toml --pandoc "$(command -v pandoc)"
pdk -p serve -f tests/fixtures/portable/zensical.toml --pandoc "$(command -v pandoc)" -a 127.0.0.1:8000
```

On Windows use `--pandoc C:\path\to\pandoc.exe`. Windows preview process handling
still requires qualification; the real live-preview acceptance test currently
runs on POSIX systems.

The compiler copies inputs into a new generation beneath the fixture's
`.pdk/portable/generations/` directory. It prints the exact configuration,
manifest and site locations. The ordinary `site/` directory and original files
remain untouched. Generated state carries its own Git ignore file. Each command
uses a separate generation. Failed candidates are removed automatically.
Cleanup of earlier successful generations is manual.

For separate preparation, invocation and validation:

```sh
pdk -p prepare -f tests/fixtures/portable/zensical.toml --pandoc "$(command -v pandoc)"
# Change into the directory containing the printed prepared configuration.
cd GENERATED_DIRECTORY
zensical build --clean --strict -f zensical.toml
pdk -p validate --manifest manifest.json
```

Running the separate Zensical command inside its generation also isolates its
default cache. Return to the original repository directory before switching modes.

Portable build always uses strict Zensical validation. The `--strict` option on
ordinary `pdk build` retains Zensical's normal optional strictness.

To switch back, stop the portable preview, then omit `-p`:

```sh
pdk build -f tests/fixtures/portable/zensical.toml --clean --strict
pdk serve -f tests/fixtures/portable/zensical.toml -a 127.0.0.1:8000
```

The existing bibliography extension retains its existing managed-Pandoc policy.
For that approach, run in the fixture directory if its bibliography requires
runtime preparation. The portable mode's explicit `--pandoc` option does not
change the ordinary extension's runtime behaviour.

Supported in this increment: top-level ATX headings, automatic or explicit IDs,
per-document/continuous reference numbering, appendices A–Z, `\ref`, `\autoref`,
global `\cite`/`\bibliography` output via the existing citeproc formatter, and
top-level image-hotspot fences. Ordinary code examples and tables are left for
Zensical. Only the migrated extension/formatter registrations are removed from
the generated configuration.

Preparation uses a structural tokenizer and makes edits at mapped source spans.
It parses only headings with Python-Markdown to obtain their IDs and text;
it does not render whole documents to HTML in Python. Both build approaches
use `prodockit.semantics` for page numbering, target collection and reference
labels. Portable preparation no longer invokes the legacy heading treeprocessor.
The shared core itself has no Markdown or Zensical dependency.

Navigation order determines continuous chapter starts and appendix letters.
Pages outside navigation keep per-document numbering, including those with an
appendix flag. The manifest records each page's starting count and appendix
letter alongside its original source identity. Reordering navigation or editing
headings produces a fresh plan in the next generation.

Sources with ambiguous duplicate IDs
are refused in this prototype instead of taking the legacy first-wins route.
Prepared Markdown uses LF line endings.

Preparation captures the configuration, Markdown, assets and bibliography/CSL
dependencies as bytes before compiling. It parses that captured configuration
and uses the captured images and bibliography files throughout compilation.
A second input check rejects edits detected during preparation. Failed preparation
removes its incomplete generation and leaves previous generations available.
This is a consistency check, not a filesystem-wide atomic snapshot: an edit
that is restored between checks may go undetected, but compilation still uses
the captured bytes.

Each completed generation contains:

```text
generation-.../
  .inputs/config.toml
  .inputs/docs/...
  .inputs/dependencies/...   # Original external bibliography/CSL bytes
  docs/...                  # Prepared Markdown and copied assets
  zensical.toml
  manifest.json
  site/...                  # Created by Zensical
```

The captured tree is outside the generated documentation and site directories.
Schema 2 manifests include every input hash, the exact generated-file inventory,
original/captured/generated page paths, toolchain versions and a `content_id`.
Identical inputs at the same original paths, with the same toolchain, produce
the same content ID even though each invocation has a distinct generation name.
This fingerprint checks consistency; it is not a signature or authentication.
Validation rejects changed, missing or added prepared inputs, manifest fingerprint
mismatches and toolchain changes. Older prototype manifests must be recreated
with `pdk -p prepare`. The wrapper's completed-site receipt records both the
generation and content ID; separate public CLI builds can be validated without
a wrapper receipt.

Each page's `source_map` covers copied text as well as transformed constructs.
Spans use half-open Unicode character offsets (not UTF-8 byte offsets) and
one-based lines/columns. Original offsets preserve CRLF/CR line endings;
line and column positions treat each as a single newline. Copied spans retain
exact locations; expanded references, bibliographies and hotspots map to their
original construct. `source_paths` identifies the original file for diagnostics.
Validation checks coverage and copied text against the captured and prepared
files. These maps are preparation metadata; native Zensical diagnostics are not
automatically rewritten by this prototype.

When `prodockit.tables` is enabled, preparation checks original table
attributes and reports errors with the original filename and line number.
Zensical still runs the existing table formatter and the checks on parsed
tables. For example, write `| Name {: width="30%" } | Value |` with a space
before the attribute list.

With `prodockit.glossary` enabled, define terms on top-level paragraphs
using a separate attribute line. For example:

```markdown
See \gls{gui}.

**GUI** is short for graphical user interface.
{: #gui .acronym data-term="Graphical user interface" }
```

Definitions can be on the same page or on another page, including forward
references. Keep the ID unique across the project. The portable compiler
reports an original source location for duplicate or unknown keys. Run
either build approach on the same files.

With `prodockit.citations` enabled, use the same paragraph form for manually
defined citations:

```markdown
See \citeref{guide, handbook}.

Guide to the example.
{: #guide .reference data-cite-text="Example Guide, 2026" }

Example handbook.
{: #handbook .reference data-cite-text="Example Handbook, 2025" }
```

The compiler preserves citation order and resolves links to definitions on
the same page or a different page. A citation key and a glossary key can
share the same name. Missing keys, duplicate citation keys and nested
citation syntax produce an error at the original location. This syntax is
separate from Pandoc's `\cite` and bibliography commands.

For a page-local Pandoc bibliography, put `\pagebibliography` on its own
line in a top-level paragraph. The prepared build appends the heading and list
after the authored content and before website footnotes. Use
`\pagebibliography{background.bib}{Sources used on this page}` to choose a
file and a plain-text heading. Empty lists produce no heading. Repeated
citations have separate return destinations when `page_backlinks` is enabled.
The heading is ordinary Markdown before the section so Zensical can include
it in the contents. Put a global list with overlapping entries on a separate
page, where its anchors cannot collide with the page-local ones.

Portable captions use the existing `pymdownx.blocks.caption` extension and
its numbered `figure-caption` and `table-caption` types. Put them after their
image or table, either at the top level or with four spaces per list level.
Both selector IDs and `attrs: {id: example}` work. Portable builds supply the
full caption number before rendering so the visible label and references
agree. Manual caption numbers and other PyMdown block types are outside
this slice.

A project-local `theme.custom_dir` may contain templates, partials, icons
and assets. Preparation captures those files and points the generated
configuration at its private copy. Zensical continues to render the theme.
Edits to overrides trigger a new portable preview generation.

Portable builds retain the native `pymdownx.snippets` extension for whole-file,
UTF-8 includes inside top-level fenced code blocks. Use a quoted path relative
to the project root, for example `--8<-- "LICENSE.md"` inside a `text` fence.
Only the referenced files are captured. An include that would introduce
another directive or change the fence is rejected at its original location.

Portable macro support accepts a local module that re-exports
`prodockit.zensical_macros.define_env`. Put `{{ pdk_heading_counter_reset(page) }}`
or its legacy alias in a top-level paragraph. Preparation inserts CSS from
the same numbering plan as portable references. With website numbering
enabled, use continuous numbering, explicit navigation and the default
`is_appendix` flag. The reference, acronym, glossary and festive styling
calls still run through native Zensical macros when used in their own
top-level paragraphs. Use a Jinja raw block inside code to show a literal
template example.

Native admonitions, collapsible details and content tabs can contain ordinary
Markdown, including nested admonitions, links, inline code and aligned, closed
SuperFences blocks. Preparation leaves these containers in the Markdown for
Zensical to render. It checks their contents and reports affected syntax such
as active Prodockit references, numbered headings, caption targets and
definitions at the original source line. For literal examples of those
constructs, use a code span or a closed fence.

Portable preparation also recognises balanced `/// steps` and `//// step`
blocks when `prodockit.steps` is enabled. The existing renderer still formats
titles and honours `start` and `attrs`. A child block needs a longer slash
fence than its parent, and each closing fence must match its opener. Ordinary
Markdown and supported native containers can remain inside a step. Affected
references, headings, captions, definitions and hotspots inside steps still
report an error at the original source line.

Unsupported cases fail explicitly: other nested affected syntax, containers
inside lists and block quotes, Setext headings,
custom slugging, project-specific macro modules and conditional templates,
snippets outside the fenced form, generated
navigation and plugins, file-visibility settings, symlinked sources and YAML
configuration.
The prototype requires explicit `attr_list` and `toc`
configuration when migrated extensions are enabled.

`pdk -p serve` watches original sources and dependencies, builds and validates a
candidate generation, and restarts native Zensical serve only after success.
Invalid edits leave the previous preview available. It currently requires
`docs_dir/index.md` and a localhost/127.0.0.1 preview address. A restart causes a
short interruption. If the replacement cannot start, Prodockit restarts the
previous successful generation and retries an unchanged candidate after five
seconds. A new edit can trigger a retry straight away. Rename or delete a page
and update its navigation and references to replace the previous preview.
Once the replacement is serving, removed URLs are no longer available.

Use the manifest printed by `pdk -p build` to render a PDF from that generation.

```sh
pdk -p pdf --manifest PATH/TO/manifest.json
pdk -p pdf --manifest PATH/TO/manifest.json -m guide/install.md
```

The PDF command uses the existing renderer and the original project's PDF
settings. It reads the generated HTML and captured Markdown and assets, and
writes to the generation's `pdf/` directory. Rebuild with `pdk -p build` if
the source inputs or site files have changed, or if you created the site with
a direct Zensical command or an older portable build. Use `pdk pdf` for the
ordinary website and its usual PDF output.

The two-process `prepare --watch` workflow and automatic publication to the
original destination remain open.

Qualification covers prepared content on the current Python-Markdown-based
Zensical CLI. It does not establish compatibility with an unreleased Rust
renderer or complete authoring parity. Search receives resolved content as
input; browser-level search behaviour remains an acceptance gate for promotion.

Run the focused checks with:

```sh
pytest tests/test_portable.py tests/test_portable_source_map.py tests/test_bibliography.py tests/test_zensical_api_boundaries.py
pytest tests/test_semantics.py tests/test_headings.py tests/test_refs.py tests/test_zensical.py
```

The live-preview test needs permission to bind a loopback port. It checks edits,
recovery from a failed reference, interruption cleanup and a switch back to
ordinary serve. Other checks make private Prodockit context access fatal in both
the parent compiler and the child build, verify source preservation, and compare
normal → portable → normal builds.
