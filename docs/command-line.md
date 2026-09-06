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

Before interpreting a long report, see [Reading command
output](commands/output.md) for the shared phase, stage, colour, decision, and
status language used across the commands.

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
| [`prodockit diag`](commands/diag.md) | A command, dependency, renderer, configuration, or checkout does not behave as expected | `prodockit diag` | Nothing by default or with `--dry-run`; `--apply` asks before each supported repair |
| [`prodockit config`](commands/config.md) | You need to see the Prodockit settings that will actually be used, or check that the source project is complete | `prodockit config` | Nothing; add `--check` for a CI-friendly non-zero exit when problems exist |
| [`prodockit adopt`](commands/adopt.md) | An existing Zensical document needs selected prodockit components without machine, Git or editor setup | `prodockit adopt` | Local project files only with `--apply`; optional choices use `--configure` |
| [`prodockit bootstrap`](commands/bootstrap.md) | A machine or a project based on `prodockit-template` is not ready to build and publish | `prodockit bootstrap` | Only with `--apply`; configuration questions use `--configure` |
| [`prodockit init-tools`](commands/init-tools.md) | The project needs local Mermaid or MathJax rendering tools | `prodockit init-tools` | Tool manifests, scripts, and ignore entries; existing files require `--force` |
| [`prodockit init-mathjax`](commands/init-mathjax.md) | The website needs the installed MathJax bundle copied into its assets | `prodockit init-mathjax` | Website JavaScript assets, the package licence, and, unless disabled, `.gitignore` |
| [`prodockit update-dates`](commands/update-dates.md) | A completed website should show when each page was last updated | `prodockit update-dates` after the normal site build | The configured `site_dir`; source Markdown and configuration remain unchanged |
| [`prodockit pdf`](commands/pdf.md) | You need one PDF containing the pages in `nav` | `prodockit pdf` | The configured PDF output |
| [`prodockit source-bundle`](commands/source-bundle.md) | A submission needs the Markdown and configuration as a separate PDF | `prodockit source-bundle` | The configured source-bundle output |
| [`prodockit sync-repo`](commands/sync-repo.md) | Repository links or badges must match the current remote | `prodockit sync-repo --check` | `zensical.toml` and the managed README badge block without `--check` |
| [`prodockit pins`](commands/pins.md) | Build-input versions disagree or need a reviewed upgrade | `prodockit pins --check --offline` | Matching version declarations when a version is selected |
| [`prodockit shared-files`](commands/shared-files.md) | A shared site asset may have missed a cascade | `prodockit shared-files --check` | Missing or different declared files, only with `--apply` |
| [`prodockit template-sync`](commands/template-sync.md) | A generated project needs later template fixes | `prodockit template-sync` | With `--apply`, template-owned/shared files on a new branch; always appends its ignored log |
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

## Use diagnostics, Adopt, pins, and template sync together

These four commands overlap in what they inspect, but they own different
decisions. \ref{tab-command-line-diag-adopt-pins-template-sync} separates their
responsibilities.

| Command {: width="22%" } | Question it answers | What it may change |
|---|---|---|
| `pdk diag` | Is this environment and project internally healthy now? | Nothing by default. `--apply` offers only bounded repairs, one default-No confirmation at a time. It does not fetch or apply a template, and a supported-combination warning directs you to `pdk pins`. |
| `pdk adopt` | Does this existing project contain the selected Prodockit components and supported local toolchain? | With `--apply`, only the active project environment and local project files. It does not fetch template changes, configure Git, or publish anything. |
| `pdk pins` | Do all dependency declarations agree with the reviewed software combination? | The selected package versions wherever they are declared, preserving each file's existing constraint form. It does not copy template files or repair an installed renderer. |
| `pdk template-sync` | What changed in the template since this project last applied it? | With `--apply`, template-owned and managed shared files plus the prerequisite Adopt alignment, normally on a review branch. It protects author-edited files and does not replace the final health check. |
/// table-caption | <
    attrs: {id: tab-command-line-diag-adopt-pins-template-sync}

Diagnostics, Adopt, Pins, and Template Sync responsibilities
///

For an unexpected failure, start with `pdk diag`. If it reports version
declarations outside the supported combination, run `pdk pins`, accept only the
reviewed defaults, then rerun `pdk diag`. This keeps diagnosis separate from the
decision to update versions.

For a routine template update, start with the read-only `pdk template-sync`
preview. Its applied workflow verifies the exact Prodockit release paired with
the incoming template and reuses Adopt to align the supported toolchain. After
the pull or merge request is merged, rerun `pdk template-sync` to confirm there
are no remaining template changes, then run `pdk diag`, the strict website
build, and `pdk pdf` as the final checks.

If either workflow reports an unrelated environment failure, stop that update
and use `pdk diag` first. A clean diagnostic does not mean that no remote
template update exists: the default diagnostic is offline, whereas
`template-sync` performs the template comparison.

The [project check and update sequence](project-check-update.md) gives students
one task-based procedure using all four commands in the right order. Use that
page when checking a template project or applying an update; use the command
reference pages when you need the precise interface or exit behaviour.

## Build the reviewed outputs

After a command changes project files or dependencies, build the website before
the PDF so both artifacts use the same completed site:

```bash
zensical build --clean --strict
prodockit pdf
```

Review both outputs before committing or publishing the change.

The common mode options also have consistent short forms: `-a` for `--apply`,
`-n` for `--dry-run`, `-v` for `--verbose`, and `-o` for `--online`. The steps
spell out the long forms while students learn what each action means. Use `-h`
or `--help` for the main command and every subcommand. Options such as
`--force`, `--push`, and `--review-all` deliberately remain long-only.

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
- [Manual installation](installation.md) covers direct package setup, while
  [Requirements and dependencies](requirements-dependencies.md) records the
  supported tools and versions.
- [Repository metadata](devcons/repo-metadata.md) explains every derived link and badge.
- [Version pinning and drift](devcons/pinning-drift.md) covers controlled upgrades and scheduled comparisons.
- [Staying in step with the template](devcons/template-sync.md) protects project-owned writing while updating shared infrastructure.
- [Build and release](devcons/releasing.md) covers the package release from branch to PyPI and verified Pages deployment.
