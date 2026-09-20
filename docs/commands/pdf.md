---
icon: lucide/file-text
---

{{ heading_counter_reset(page) }}

# `pdk pdf`

`pdk pdf` builds one PDF from the completed Zensical website and the PDF
settings in the project configuration.

Use the [PDF generation task guide](../pdf.md) to prepare renderers, configure
the document, and resolve build failures.

## Synopsis {: #cmd-pdf-synopsis }

Use the complete-document form or select one Markdown page for focused review.

```text
pdk pdf [--config-file PATH] [--markdown-file PAGE]
pdk pdf --prepare COMPONENT [--prepare COMPONENT ...]
```

## Working directory {: #cmd-pdf-working-directory }

Run this command from the **project root**, after building the website there.
Use `--config-file PATH` when deliberately building another configuration;
`--markdown-file` remains relative to that configuration's `docs_dir`.

From the wrong directory it normally reports `project configuration not found:
.../zensical.toml`. If the configuration is found but the website has not been
built, expect `built site not found: ...; run zensical build first` instead.

## Options {: #cmd-pdf-options }

\ref{tab-cmd-pdf-options} lists the PDF source-selection controls.

| Option {: width="38%" } | Behaviour |
|---|---|
| `-f`, `--config-file PATH` | Read another Zensical configuration; defaults to `zensical.toml`. |
| `-m`, `--markdown-file PAGE` | Build only one Markdown page relative to `docs_dir`, ignoring `nav` for the PDF contents. |
| `--prepare COMPONENT` | Validate and prepare one project-local PDF component without requiring a built site or producing a PDF; repeat it or use `all` for every component supported on the current platform. |
| `-h`, `--help` | Show installed help and exit. |
/// table-caption | <
    attrs: {id: tab-cmd-pdf-options}

PDF build options
///

## Inputs and output {: #cmd-pdf-inputs-and-output }

The command uses the completed `site_dir`; build the website first with
`zensical build --clean --strict`. It assembles the pages in configured
navigation order, processes PDF-only features, then asks Pandoc and WeasyPrint
to write the configured PDF path.

The single-page option still reads layout, fonts, styles, and renderer settings
from the configuration. It changes only the scope of the PDF contents.

### PDF runtime policy {: #cmd-pdf-runtime-policy }

Optional runtime policy lives in `pdk-pdf.toml` beside the selected Zensical
configuration. A missing file uses supported defaults and an ordinary build
does not create one. The minimal file is:

```toml
schema_version = 1
```

Renderer overrides may select `latest`, `supported`, or an exact version and
may set `preload = true`. Runtime overrides may select a version. G1 accepts
only `location = "cache"`: it means the derived project-local store at
`.prodockit/cache/pdf/`, never an absolute path committed to the repository.
Resolved versions, hashes, platform identity and last-known-good state are
recorded inside that store rather than in `pdk-pdf.toml`.

The preparation interface is intentionally provider-gated. Pandoc 3.10.1 and
the Inter 4.1/JetBrains Mono 2.304 font bundle are available on supported
macOS, Linux, and Windows x64 targets; Windows x64 also provides WeasyPrint 70.
A healthy cache is a fast local validation with no provider or network call.

## Exit status {: #cmd-pdf-exit-status }

A missing or mismatched environment, incomplete built site, invalid PDF
configuration, renderer failure, or unwritable output produces a non-zero exit
and preserves the underlying tool's useful error detail.

## Related commands {: #cmd-pdf-related-commands }

Use these commands to validate inputs or build the companion source artifact:

- [`pdk config`](config.md) checks PDF settings and inputs without building.
- [`pdk source-bundle`](source-bundle.md) renders the underlying source as a
  separate submission artifact.
