---
icon: lucide/boxes
---

{{ heading_counter_reset(page) }}

# `pdk init-tools`

`pdk init-tools` creates the locked project-local Node manifests and scripts
used to render Mermaid diagrams and TeX mathematics into PDFs.

Use [Prepare the PDF tools](../pdf.md#pdf-requirements) for the installation
task and operating-system prerequisites.

## Synopsis {: #cmd-init-tools-synopsis }

```text
pdk init-tools [OPTIONS]
```

## Working directory {: #cmd-init-tools-working-directory }

Run this command from the **project root**. Its default `--dir tools` is relative
to the current directory. A deliberate custom directory must also match the
renderer paths configured in `zensical.toml`.

There may be **no error** when it is run from the wrong directory: it can create
new `tools/mermaid` and `tools/mathjax` trees there and report `Wrote ...`.
If the paths are outside the project, remove the unintended files and rerun the
command from the project root.

## Options {: #cmd-init-tools-options }

| Option {: width="38%" } | Behaviour |
|---|---|
| `--dir PATH` | Scaffold beneath another directory; defaults to `tools`. |
| `--mermaid`, `--no-mermaid` | Include or omit Mermaid CLI tooling; included by default. |
| `--mathjax`, `--no-mathjax` | Include or omit MathJax tooling; included by default. |
| `--force` | Overwrite an existing scaffold file instead of preserving it. |
| `-h`, `--help` | Show installed help and exit. |

## Effects {: #cmd-init-tools-effects }

The command writes manifests, lockfiles, renderer scripts, licence information,
and ignore entries beneath the selected project directory. It does not run npm
installation itself. Existing files are preserved unless `--force` is
explicitly supplied.

The default `tools` paths match Prodockit's PDF configuration. A custom
directory must also be configured in `zensical.toml`.

## Related commands {: #cmd-init-tools-related-commands }

- [`pdk init-mathjax`](init-mathjax.md) copies the installed MathJax browser
  bundle into website assets.
- [`pdk diag`](diag.md) verifies both project-local renderer installations.
