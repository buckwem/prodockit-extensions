# Command-line tools

Run `prodockit --help` for the commands installed by the current release, and
`prodockit COMMAND --help` for every option. This page is the map: it puts each
command in the part of the workflow where it belongs and links to the detailed
guide.

The shorter `pdk` executable is an alias for `prodockit`. `bootstrap` also has
the `boot` alias, and `source-bundle` has the `source` alias.

## Create and preview content

The site itself uses Zensical's commands:

| Command | Purpose |
| --- | --- |
| `zensical new .` | Create a starter project |
| `zensical serve` | Run a rebuilding local preview |
| `zensical build` | Build the static site |

Start with [Build your first site](getting-started.md).

## Publish and verify

| Command or feature | Purpose | Guide |
| --- | --- | --- |
| `prodockit pdf` | Build the site navigation as one printable PDF | [PDF generation](pdf.md) |
| `prodockit source-bundle` | Build a separate PDF containing the documentation source | [Source bundle](pdf.md#bundling-source-into-a-pdf) |
| `prodockit init-tools` | Scaffold the optional Mermaid and MathJax Node tools used by PDF builds | [PDF requirements](pdf.md#mermaid-diagrams-and-tex-maths) |
| `prodockit init-mathjax` | Copy the installed MathJax bundle into the website for matching, offline maths | [PDF requirements](pdf.md#mermaid-diagrams-and-tex-maths) |
| `prodockit.testing` | Test already-built website and PDF artifacts | [Testing](devcons/testing.md) |

`init-tools` and `init-mathjax` write project files. The build commands write
their configured outputs.

## Set up and maintain a project

| Command | Purpose | Writes by default? |
| --- | --- | --- |
| [`prodockit bootstrap`](devcons/bootstrap.md) | Check or set up a machine and project toolchain | No; use `--apply` |
| [`prodockit sync-repo`](devcons/repo-metadata.md) | Match site metadata and README badges to a git remote | Yes; use `--check` to report only |
| [`prodockit pins`](devcons/pinning-drift.md) | Find and update version declarations across project files | Prompts before updates; `--check` reports only |
| [`prodockit template-sync`](devcons/template-sync.md) | Compare a generated project with its source template | No; use `--apply` |

These commands solve different problems. None is required merely to enable a
Markdown extension or run `zensical serve`.
