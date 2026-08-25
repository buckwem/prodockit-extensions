---
icon: lucide/terminal
---

{{ heading_counter_reset(page) }}

# Command-line tools

This page inventories the public \index{command-line interface} (CLI) for document authors and project
maintainers. It keeps command names, aliases, safe defaults, write behaviour,
and automation semantics visible in one place.

Start with [Publish a document](publishing.md) to see each command in the task
that needs it. Run a command from the project
root—the directory containing `zensical.toml`—unless an option explicitly
names another location.

Use the shorter `pdk` executable when you prefer it; it is an exact alias.
`bootstrap` also answers to `boot`, and `source-bundle` to `source`.

## Check the installation

```bash
prodockit --version
prodockit --help
```

The first prints the installed release. The second lists the commands supplied
by that release. Ask an individual command for its current options:

```bash
prodockit pins --help
```

If a guide and local help disagree, the local help describes the code you are
actually running. Check `prodockit --version`, then compare it with the version
pinned by the project before assuming an option is unavailable.

## Choose a command

| Command | Use it when | Safe first run | Writes |
|---|---|---|---|
| [`prodockit adopt`](adopt.md) | An existing Zensical document needs selected prodockit components without machine, Git or editor setup | `prodockit adopt` | Local project files only with `--apply`; optional choices use `--configure` |
| [`prodockit bootstrap`](devcons/bootstrap.md) | A machine or checkout is not ready to build and publish | `prodockit bootstrap` | Only with `--apply`; configuration questions use `--configure` |
| [`prodockit init-tools`](pdf.md#mermaid-diagrams-and-tex-maths) | The project needs local Mermaid or MathJax rendering tools | `prodockit init-tools` | Tool manifests, scripts, and ignore entries; existing files require `--force` |
| [`prodockit init-mathjax`](pdf.md#mermaid-diagrams-and-tex-maths) | The website needs the installed MathJax bundle copied into its assets | `prodockit init-mathjax` | Website JavaScript assets and, unless disabled, `.gitignore` |
| [`prodockit pdf`](pdf.md) | You need one PDF containing the pages in `nav` | `prodockit pdf` | The configured PDF output |
| [`prodockit source-bundle`](pdf.md#bundling-source-into-a-pdf) | A submission needs the Markdown and configuration as a separate PDF | `prodockit source-bundle` | The configured source-bundle output |
| [`prodockit sync-repo`](devcons/repo-metadata.md) | Repository links or badges must match the current remote | `prodockit sync-repo --check` | `zensical.toml` and the managed README badge block without `--check` |
| [`prodockit pins`](devcons/pinning-drift.md) | Build-input versions disagree or need a reviewed upgrade | `prodockit pins --check --offline` | Matching version declarations when a version is selected |
| [`prodockit template-sync`](devcons/template-sync.md) | A generated project needs later template fixes | `prodockit template-sync` | With `--apply`, template-owned/shared files on a new branch; always appends its ignored log |

The \index{commands!`prodockit init-mathjax`} command is the narrower website
asset command; use `init-tools` when preparing both Mermaid and maths for PDF
output.

## Build and preview {: #publish-and-verify }

Zensical owns the live website commands:

```bash
zensical serve
zensical build --clean --strict
```

`serve` watches the source and rebuilds a local preview. The strict build is
the final website check: it starts clean and treats broken links, missing
anchors, and other validation warnings as failures.

Prodockit builds the additional artifacts:

```bash
prodockit pdf
prodockit source-bundle
```

When building both the complete PDF and site, keep this order:

```bash
prodockit pdf
zensical build --clean --strict
```

Zensical copies the finished PDF into the site directory. Reversing the order
can publish the PDF from the previous build while every command exits
successfully.

To render one page while developing PDF styles, use:

```bash
prodockit pdf --markdown-file extensions/tables.md
```

That ignores `nav` and is a quick diagnostic, not a substitute for the final
complete build.

## Maintain without changing files

Begin with report-only forms:

```bash
prodockit sync-repo --check
prodockit pins --check --offline
prodockit template-sync
prodockit bootstrap
```

These answer four different questions:

1. Does repository metadata match `origin`?
2. Do declared build versions agree across files?
3. Has the source template changed files it owns?
4. Is this machine and checkout ready to build?

Do not replace one with another merely because they all use the word “check”.

## Apply and verify a maintenance change

/// steps

//// step | Read the report

Run the non-writing or check form first. A maintenance command should tell you
which files or stages are involved before you authorise writes.

////

//// step | Apply only the reported change

Examples:

```bash
prodockit sync-repo
prodockit pins --set zensical=0.0.55
prodockit template-sync --apply
prodockit bootstrap --apply
```

`pins --set` is unattended and leaves unnamed packages untouched.
`template-sync --apply` stages its work on a branch but does not commit it.
`bootstrap --apply` performs only outstanding stages and verifies each one.

////

//// step | Repeat the check

```bash
prodockit sync-repo --check
prodockit pins --check --offline
prodockit template-sync
prodockit bootstrap
```

The second run should be clean or explain any remaining manual work. Do not
treat a changed file as proof that the intended state was reached.

////

//// step | Build and inspect

```bash
prodockit pdf
zensical build --clean --strict
git diff --check
git status --short
```

Open the website and PDF when the change can affect rendering. Automated
checks catch known failures; visual review answers whether the output is the
document you intended to publish.

////

///

## Use commands in automation

Automation must not wait for a prompt. Use explicit non-interactive forms:

```bash
prodockit sync-repo --check
prodockit pins --check --offline
prodockit pins --set zensical=0.0.55
```

Important exit-status behaviour:

| Command | Exit zero means |
|---|---|
| `sync-repo --check` | Managed repository metadata is already current |
| `pins --check --offline` | Every discovered declaration agrees; no network comparison was attempted |
| `pins --check` | Declarations agree and none of the selected PyPI packages is behind |
| `zensical build --clean --strict` | The site built without a strict validation error |
| `pytest` | The selected source or built-output checks passed |

The ordinary interactive `prodockit pins` command is for a terminal, not CI.
Likewise, `template-sync --push` asks before committing, merging, and pushing;
it is an assisted maintainer operation rather than an unattended deployment
step.

## Find the next guide

- [Maintain prodockit](project-maintenance.md) provides the complete recurring cycle.
- [Set up a machine](devcons/bootstrap.md) takes a new computer through its first successful publish.
- [Repository metadata](devcons/repo-metadata.md) explains every derived link and badge.
- [Version pinning and drift](devcons/pinning-drift.md) covers controlled upgrades and scheduled comparisons.
- [Staying in step with the template](devcons/template-sync.md) protects project-owned writing while updating shared infrastructure.
- [Build and release](devcons/releasing.md) covers the package release from branch to PyPI and verified Pages deployment.
