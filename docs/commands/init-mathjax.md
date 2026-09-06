---
icon: lucide/sigma
---

{{ heading_counter_reset(page) }}

# `pdk init-mathjax`

`pdk init-mathjax` copies the MathJax browser bundle and its licence from the
project's locked installation into the website assets used by Zensical.

## Synopsis {: #cmd-init-mathjax-synopsis }

```text
pdk init-mathjax [--root PATH] [--no-gitignore]
```

## Working directory {: #cmd-init-mathjax-working-directory }

Run this command from the **project root**, after installing the locked package
under `tools/mathjax`. Use `--root PATH` when deliberately targeting another
project.

From the wrong directory it normally reports that
`tools/mathjax/node_modules/mathjax-full/...` `is not there` and tells you to
run `npm ci --prefix tools/mathjax`. Before installing anything, confirm that
you are in the intended project.

## Options {: #cmd-init-mathjax-options }

| Option {: width="34%" } | Behaviour |
|---|---|
| `--root PATH` | Install into another project directory; defaults to the current directory. |
| `--no-gitignore` | Do not add generated MathJax assets to `.gitignore`. |
| `-h`, `--help` | Show installed help and exit. |

## Effects {: #cmd-init-mathjax-effects }

The command copies `tex-svg-full.js` and the upstream licence from the installed
`mathjax-full` package. By default, it also records the generated asset paths in
`.gitignore`. It does not download a different MathJax release or modify author
content.

Rerun it after the locked MathJax dependency changes so the website and PDF use
the same release.

## Related commands {: #cmd-init-mathjax-related-commands }

- [`pdk init-tools`](init-tools.md) creates the locked MathJax manifest and PDF
  conversion script.
- [`pdk diag`](diag.md) checks that the script, package inputs, and website
  assets are complete.
