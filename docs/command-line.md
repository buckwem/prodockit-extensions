---
icon: lucide/terminal
---

{{ heading_counter_reset(page) }}

# Command-line tools

This page inventories the public \index{command-line interface} (CLI) for document authors and project
maintainers. It keeps command names, aliases, safe defaults, write behaviour,
and automation semantics visible in one place.

Start with the [Authoring reference](authoring.md) to choose a document feature,
or [Publish a document](publishing.md) to see deployment commands in their
workflow. Run a command from the project
root—the directory containing `zensical.toml`—unless an option explicitly
names another location.

Use the shorter `pdk` executable when you prefer it; it is an exact alias.
`bootstrap` also answers to `boot`, and `source-bundle` to `source`.

## Check the installation

Confirm which prodockit release is active and inspect the commands it provides:

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

\ref{tab-command-line-choose-a-command} identifies the safe starting form and
write behaviour of each public command.

| Command {: width="34%" } | Use it when | Safe first run | Writes |
|---|---|---|---|
| [`prodockit diag`](#diagnose-an-environment-and-project) | A command, dependency, renderer, configuration, or checkout does not behave as expected | `prodockit diag` | Nothing; network checks are opt-in with `--online` |
| [`prodockit config`](#check-resolved-configuration) | You need to see the Prodockit settings that will actually be used, or check that the source project is complete | `prodockit config` | Nothing; add `--check` for a CI-friendly non-zero exit when problems exist |
| [`prodockit adopt`](adopt.md) | An existing Zensical document needs selected prodockit components without machine, Git or editor setup | `prodockit adopt` | Local project files only with `--apply`; optional choices use `--configure` |
| [`prodockit bootstrap`](devcons/bootstrap.md) | A machine or a project based on `prodockit-template` is not ready to build and publish | `prodockit bootstrap` | Only with `--apply`; configuration questions use `--configure` |
| [`prodockit init-tools`](pdf.md#mermaid-diagrams-and-tex-maths) | The project needs local Mermaid or MathJax rendering tools | `prodockit init-tools` | Tool manifests, scripts, and ignore entries; existing files require `--force` |
| [`prodockit init-mathjax`](pdf.md#mermaid-diagrams-and-tex-maths) | The website needs the installed MathJax bundle copied into its assets | `prodockit init-mathjax` | Website JavaScript assets, the package licence, and, unless disabled, `.gitignore` |
| [`prodockit update-dates`](publishing.md#build-with-revision-dates) | A completed website should show when each page was last updated | `prodockit update-dates` after the normal site build | The configured `site_dir`; source Markdown and configuration remain unchanged |
| [`prodockit pdf`](pdf.md) | You need one PDF containing the pages in `nav` | `prodockit pdf` | The configured PDF output |
| [`prodockit source-bundle`](pdf.md#bundling-source-into-a-pdf) | A submission needs the Markdown and configuration as a separate PDF | `prodockit source-bundle` | The configured source-bundle output |
| [`prodockit sync-repo`](devcons/repo-metadata.md) | Repository links or badges must match the current remote | `prodockit sync-repo --check` | `zensical.toml` and the managed README badge block without `--check` |
| [`prodockit pins`](devcons/pinning-drift.md) | Build-input versions disagree or need a reviewed upgrade | `prodockit pins --check --offline` | Matching version declarations when a version is selected |
| [`prodockit shared-files`](devcons/pinning-drift.md#pinning-shared-files) | A shared site asset may have missed a cascade | `prodockit shared-files --check` | Missing or different declared files, only with `--apply` |
| [`prodockit template-sync`](devcons/template-sync.md) | A generated project needs later template fixes | `prodockit template-sync` | With `--apply`, template-owned/shared files on a new branch; always appends its ignored log |
/// table-caption | <
    attrs: {id: tab-command-line-choose-a-command}

Choose a command
///

\ref{tab-command-line-choose-a-command} is the quickest way to select a safe
starting form. The narrower website asset command is `prodockit
init-mathjax`\index{commands!`prodockit init-mathjax`}; use `init-tools` when
preparing both Mermaid and maths for PDF output. It copies the pinned package's
Apache-2.0 licence beside the browser bundle, so a published self-contained site
also publishes the licence that governs that third-party code.

## Diagnose an environment and project {: #diagnose-an-environment-and-project }

Run one read-only diagnostic before changing an installation or project:

```bash
pdk diag
```

It checks the running Python and selected commands, installed package metadata
and dependency conflicts, resolved project configuration and source inputs,
version pins and shared files, configured rendering tools, and Git/template
metadata. A missing optional renderer is a warning; a renderer required by the
current configuration is a failure. A virtual environment is supported but not
required: matching pipx, Conda, system-Python, and CI installations are valid.

The default run is deterministic and offline. Add `--online` to check published
package versions and the recorded template revision, or `--verbose` to include
the evidence behind passing checks. For a project whose configuration is named
or located differently, use `-f PATH` or `--config-file PATH`.

When asking for support, attach the machine-readable report rather than a
screenshot:

```bash
pdk diag --json > prodockit-diagnostics.json
```

The JSON schema is stable and reports pass, warning, and failure counts. The
command exits non-zero only for an actionable failure; warnings alone still
exit zero. It never installs, repairs, generates, or changes project files.
The [diagnostics guide](devcons/diagnostics.md) explains every stable check ID
and the remediation required from a document author.

## Check resolved configuration {: #check-resolved-configuration }

Zensical accepts project-specific values in `[project.extra]`, and
Python-Markdown extension tables can contain arbitrary keys. That flexibility
also means a misspelled Prodockit setting can otherwise be ignored while the
build succeeds with its default value. Inspect the values Prodockit will use
before investigating an unexpected PDF or extension result:

```bash
prodockit config
```

The report separates explicit values from defaults, shows every enabled
`prodockit.*` extension option, and reports whether the optional package for a
back-of-book index is installed. It also identifies obsolete names such as
`pdf_include_index` and suggests close matches for misspellings. The report
also checks local style sheets and scripts, navigation pages, Markdown images,
an explicitly selected CSL file, configured renderers, and Prodockit syntax
whose extension has been switched off.

Use the strict form in a local check or CI job:

```bash
prodockit config --check
```

It exits non-zero for obsolete, unknown or invalid Prodockit settings, missing
project inputs, unavailable configured renderers, and index generation enabled
without `prodockit[index]`. It validates only names owned by Prodockit. Other
Zensical `[project.extra]` values and third-party Markdown extension settings
are deliberately left alone.

The command reads the same source configuration model as the public PDF
renderer. Zensical still owns the website build; this check does not invoke
Zensical or change any file.

## Build and preview {: #publish-and-verify }

Zensical owns both the live preview and static build. Prodockit can optionally
add per-page revision dates after the static build:

```bash
zensical serve
zensical build --clean --strict
prodockit update-dates
```

`serve` watches the source and rebuilds a local preview. The second command
creates the static site and treats broken links, missing anchors, and other
validation warnings as failures. `prodockit update-dates` then changes only
the generated HTML. It does not invoke Zensical or write dates into the
author's files. Omit that final command when the website does not need page
dates; the Zensical build is already complete.

`prodockit update-dates` is independent of adoption. It can post-process an
existing Zensical project without adding Prodockit extensions, shared
stylesheets, macros, template files, or publishing workflows. Only the
Prodockit package itself must be installed in the active environment.

Prodockit builds the additional artifacts:

```bash
prodockit pdf
prodockit source-bundle
```

When building both the complete PDF and site, keep this order:

```bash
zensical build --clean --strict
prodockit pdf
prodockit update-dates
```

The PDF command consumes the completed site and does not invoke Zensical.
The final `update-dates` line remains optional and can be left out when dates
are not displayed.

To render one page while developing PDF styles, use:

```bash
prodockit pdf --markdown-file extensions/tables.md
```

That ignores `nav` and is a quick diagnostic, not a substitute for the final
complete build.

## Maintain without changing files

Each maintenance command answers a different question. Begin with their
report-only forms so you can inspect the result before changing the project:

```bash
prodockit sync-repo --check
prodockit config --check
prodockit pins --check --offline
prodockit shared-files --check
prodockit template-sync
prodockit bootstrap
```

These answer six different questions:

1. Does repository metadata match `origin`?
2. Are Prodockit's resolved settings valid and free from ignored stale names?
3. Do declared build versions and shared files agree with the installed release?
4. Do the shared files agree when checked directly?
5. Has the source template changed files it owns?
6. Is this machine and checkout ready to build?

Do not replace one with another merely because they all use the word “check”.

## Apply and verify a maintenance change

Treat every maintenance change as a short review cycle: understand the report,
apply only that change, inspect the diff, and rebuild the outputs.

/// steps

//// step | Read the report

Run the non-writing or check form first. A maintenance command should tell you
which files or stages are involved before you authorise writes.

////

//// step | Apply only the reported change

Examples:

```bash
prodockit sync-repo
prodockit pins --set zensical=0.0.57
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
prodockit config --check
prodockit pins --check --offline
prodockit template-sync
prodockit bootstrap
```

The second run should be clean or explain any remaining manual work. Do not
treat a changed file as proof that the intended state was reached.

////

//// step | Build and inspect

```bash
zensical build --clean --strict
prodockit pdf
prodockit update-dates
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
prodockit pins --set zensical=0.0.57
```

Important exit-status behaviour:

\ref{tab-command-line-use-commands-in-automation} records the success and failure exit statuses that automation can rely on.

| Command {: width="35%" } | Exit zero means |
|---|---|
| `diag` | The active installation and every required project capability passed; warnings may describe unused optional tools or available updates |
| `sync-repo --check` | Managed repository metadata is already current |
| `config --check` | Prodockit settings are valid, local project inputs exist, configured renderers are available, and any enabled PDF index has its optional dependency |
| `pins --check --offline` | Every discovered declaration agrees; no network comparison was attempted |
| `pins --check` | Declarations agree and none of the selected PyPI packages is behind |
| `shared-files --check` | Every file declared in `.prodockit-shared-files.toml` matches the installed release |
| `prodockit update-dates` | Revision dates were resolved and added to the completed site |
| `pytest` | The selected source or built-output checks passed |
/// table-caption | <
    attrs: {id: tab-command-line-use-commands-in-automation}

Use commands in automation
///

The exit-zero meanings in \ref{tab-command-line-use-commands-in-automation}
are the automation contract. The ordinary interactive `prodockit pins` command
is for a terminal, not CI.
Likewise, `template-sync --push` asks before committing, merging, and pushing;
it is an assisted maintainer operation rather than an unattended deployment
step.

## Find the next guide

Use the guide that matches the task you are about to perform:

- [Maintain prodockit](project-maintenance.md) provides the complete recurring cycle.
- [Add prodockit to an existing document](adopt.md) explains adoption.
- [Set up a machine](devcons/bootstrap.md) takes a new computer through its first successful publish.
- [Manual installation](installation.md) covers direct package and tool setup.
- [Repository metadata](devcons/repo-metadata.md) explains every derived link and badge.
- [Version pinning and drift](devcons/pinning-drift.md) covers controlled upgrades and scheduled comparisons.
- [Staying in step with the template](devcons/template-sync.md) protects project-owned writing while updating shared infrastructure.
- [Build and release](devcons/releasing.md) covers the package release from branch to PyPI and verified Pages deployment.
