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
uses a separate generation; cleanup of old generations is manual in this prototype.

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
Source locations for replacements are recorded in the manifest. Prepared
Markdown uses LF line endings.

Unsupported cases fail explicitly: nested affected syntax, Setext headings,
caption blocks, custom slugging, macros, snippets, generated navigation/plugins,
custom theme directories, file-visibility settings, symlinked sources, YAML
configuration, page-local bibliographies, citation/glossary extensions and
Prodockit table diagnostics. These remain work for later stages, not silently
disabled features. The prototype requires explicit `attr_list` and `toc`
configuration when migrated extensions are enabled.

`pdk -p serve` watches original sources and dependencies, builds and validates a
candidate generation, and restarts native Zensical serve only after success.
Invalid edits leave the previous preview available. It currently requires
`docs_dir/index.md` and a localhost/127.0.0.1 preview address. A restart causes a
short interruption. The two-process `prepare --watch` workflow, automatic
publication to the original destination and `pdk -p pdf` are not implemented.

Qualification covers prepared content on the current Python-Markdown-based
Zensical CLI. It does not establish compatibility with an unreleased Rust
renderer or complete authoring parity. Search receives resolved content as
input; browser-level search behaviour remains an acceptance gate for promotion.

Run the focused checks with:

```sh
pytest tests/test_portable.py tests/test_bibliography.py tests/test_zensical_api_boundaries.py
pytest tests/test_semantics.py tests/test_headings.py tests/test_refs.py tests/test_zensical.py
```

The live-preview test needs permission to bind a loopback port. It checks edits,
recovery from a failed reference, interruption cleanup and a switch back to
ordinary serve. Other checks make private Prodockit context access fatal in both
the parent compiler and the child build, verify source preservation, and compare
normal → portable → normal builds.
