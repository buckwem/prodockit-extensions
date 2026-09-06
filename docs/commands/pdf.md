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

## Exit status {: #cmd-pdf-exit-status }

A missing or mismatched environment, incomplete built site, invalid PDF
configuration, renderer failure, or unwritable output produces a non-zero exit
and preserves the underlying tool's useful error detail.

## Related commands {: #cmd-pdf-related-commands }

Use these commands to validate inputs or build the companion source artifact:

- [`pdk config`](config.md) checks PDF settings and inputs without building.
- [`pdk source-bundle`](source-bundle.md) renders the underlying source as a
  separate submission artifact.
