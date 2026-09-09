---
icon: lucide/files
---

{{ heading_counter_reset(page) }}

# `pdk source-bundle`

`pdk source-bundle` creates a separate PDF containing the document's Markdown
source and project configuration. `pdk source` is an exact shorter alias.

## Synopsis {: #cmd-source-bundle-synopsis }

Use either command name to build the same source artifact.

```text
pdk source-bundle [--config-file PATH]
pdk source [OPTIONS]
```

## Working directory {: #cmd-source-bundle-working-directory }

Run this command from the **project root** so the default `zensical.toml` and
the project's documentation sources are selected together. A Git repository
is not required.
Use `--config-file PATH` for another project deliberately.

From the wrong directory it normally reports `project configuration not found:
.../zensical.toml`. Change to the intended project's root before retrying.

## Options {: #cmd-source-bundle-options }

\ref{tab-cmd-source-bundle-options} lists the source-selection control.

| Option {: width="38%" } | Behaviour |
|---|---|
| `-f`, `--config-file PATH` | Read another Zensical configuration; defaults to `zensical.toml`. |
| `-h`, `--help` | Show installed help and exit. |
/// table-caption | <
    attrs: {id: tab-cmd-source-bundle-options}

Source-bundle options
///

## Inputs and output {: #cmd-source-bundle-inputs-and-output }

The command reads the configured document sources and writes the configured
source-bundle output. It is separate from the rendered documentation PDF so a
project can build either or both artifacts.

For a Git repository, Git selects tracked and untracked files using its normal
ignore rules. Without a repository, the command selects the root `README.md`,
Markdown under the configured documentation directory, and the site configuration.
It honours local and nested `.gitignore` files, skips hidden directories,
virtual environments and generated tooling, and never follows symbolic links.

Use it when an assessment, archive, or review requires the authored source in
addition to the rendered document. It does not alter the Markdown or
configuration it includes.

## Related commands {: #cmd-source-bundle-related-commands }

Use these commands to build or validate the companion rendered artifact:

- [`pdk pdf`](pdf.md) creates the rendered document.
- [`pdk config`](config.md) validates the source project before either build.
