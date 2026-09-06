---
icon: lucide/files
---

{{ heading_counter_reset(page) }}

# `pdk source-bundle`

`pdk source-bundle` creates a separate PDF containing the document's Markdown
source and project configuration. `pdk source` is an exact shorter alias.

## Synopsis {: #cmd-source-bundle-synopsis }

```text
pdk source-bundle [--config-file PATH]
pdk source [OPTIONS]
```

## Working directory {: #cmd-source-bundle-working-directory }

Run this command from the **project root** so the default `zensical.toml` and
the project's Git-tracked and untracked source files are selected together.
Use `--config-file PATH` for another project deliberately.

From the wrong directory it normally reports `project configuration not found:
.../zensical.toml`. A configuration path outside the current repository may
instead reach `git ls-files failed`; change to that project's root before
retrying so the bundle cannot draw files from the wrong repository.

## Options {: #cmd-source-bundle-options }

| Option {: width="38%" } | Behaviour |
|---|---|
| `-f`, `--config-file PATH` | Read another Zensical configuration; defaults to `zensical.toml`. |
| `-h`, `--help` | Show installed help and exit. |

## Inputs and output {: #cmd-source-bundle-inputs-and-output }

The command reads the configured document sources and writes the configured
source-bundle output. It is separate from the rendered documentation PDF so a
project can build either or both artifacts.

Use it when an assessment, archive, or review requires the authored source in
addition to the rendered document. It does not alter the Markdown or
configuration it includes.

## Related commands {: #cmd-source-bundle-related-commands }

- [`pdk pdf`](pdf.md) creates the rendered document.
- [`pdk config`](config.md) validates the source project before either build.
