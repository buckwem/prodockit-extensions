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
| [`prodockit diag`](#diagnose-an-environment-and-project) | A command, dependency, renderer, configuration, or checkout does not behave as expected | `prodockit diag` | Nothing by default or with `--dry-run`; `--apply` asks before each supported repair |
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

### Student project check and update sequence {: #student-project-check-and-update-sequence }

Use this sequence for a project created from `prodockit-template`. It gives one
repeatable starting point whether you only want to confirm that the project is
healthy or you expect a template update.

/// steps

//// step | Activate the project's environment

Open a terminal in the folder containing `zensical.toml`, then activate that
project's `.venv`. Do not run the checks from the parent Bootstrap environment.

////

//// step | Establish the current health baseline

```bash
pdk diag
```

Resolve every `FAIL` before attempting a template update. If Diagnostics offers
a bounded repair, inspect it with `pdk diag --dry-run` before deciding whether
to run `pdk diag --apply`. A run containing only `PASS` results establishes that
the local project is healthy; it does not check whether the remote template has
changed.

////

//// step | Align the selected project components when requested

If Diagnostics reports that Adopt has integration stages to apply, preview
exactly those local changes:

```bash
pdk adopt --dry-run
```

Review the stages, then use `pdk adopt --apply` if they are correct. Adopt can
install or align the supported local toolchain and save the project's selected
components, but it never downloads or applies a template. Rerun `pdk diag`
afterward and resolve any remaining failure before continuing.

////

//// step | Check the dependency declarations

```bash
pdk pins --check --offline
```

If this passes and you only wanted to check the project, continue to the final
verification step. If Diagnostics or Pins says the declarations are outside
the supported combination, run `pdk pins`, review the versions, and accept only
the tested defaults. Then rerun both the offline Pins check and `pdk diag`.

////

//// step | Preview and apply a template update when one is needed

```bash
pdk template-sync
```

If the preview says the project is already up to date, no template action is
needed. Otherwise review the reported files, then run:

```bash
pdk template-sync --apply
```

Use `--review-all` when the preview lists several edited template files. For
each file, inspect the diff and choose overwrite, `.new`, or skip; skip is the
safe default. Review and merge the generated pull or merge request before
continuing.

////

//// step | Confirm the applied template and pins agree

After the update has been merged and your local project contains that merge,
run:

```bash
pdk template-sync
pdk pins --check --offline
```

The first command should report that no template file changes are needed. The
second should report that every dependency declaration agrees. Investigate any
remaining result rather than repeatedly applying the update.

////

//// step | Run the final health and output checks

```bash
pdk diag
zensical build --clean --strict
pdk pdf
```

The project is ready when Diagnostics passes, the website build reports no
issues, and the PDF is written successfully. Review the website and PDF before
submitting or publishing them.

////

///

The common mode options also have consistent short forms: `-a` for `--apply`,
`-n` for `--dry-run`, `-v` for `--verbose`, and `-o` for `--online`. The steps
spell out the long forms while students learn what each action means. Use `-h`
or `--help` for the main command and every subcommand. Options such as
`--force`, `--push`, and `--review-all` deliberately remain long-only.

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

The default run is deterministic and offline, and explicitly reports that the
npm advisory lookup was skipped. Add `--online` to check published package
versions, Mermaid's production dependencies against npm advisories, and the
recorded template revision, or `--verbose` to include the evidence behind passing checks. For a project whose configuration is named
or located differently, use `-f PATH` or `--config-file PATH`.

Preview every bounded repair alternative without selecting or running one:

```bash
pdk diag --dry-run
```

The dry run says what each command or internal repair **could** do because a
finding may have several valid choices. It shows affected paths, prerequisites,
network requirements, recovery information, and warnings. Independent
project-local repairs use supported Prodockit commands such as `prodockit
adopt`, `pdk pins`, `pdk shared-files`, `pdk init-tools`, and `pdk
init-mathjax`; they do not depend on `prodockit-template`. Template state is
never treated as an automatic diagnostic repair.

Use `--apply-check CHECK_ID` with `--dry-run` to limit this preview. The option is
repeatable. `--dry-run` and `--apply` cannot be combined.

To consider supported repairs, use an interactive terminal:

```bash
pdk diag --apply
```

The command prints the complete plan before asking anything. Every mutation has
its own `Apply this repair? [y/N]:` prompt and only a single `y` or `Y` confirms
that action; Enter, `n`, `yes`, end-of-input, and every other answer decline it.
Warnings are repeated immediately before confirmation. Redirected input and CI
runs are refused, with no `--yes`, `--force`, or environment-variable bypass.
The text presentation follows bootstrap: bright-blue phase boundaries separate
inspection, repair decisions, and final verification; blue stage headings keep
each finding visible; yellow identifies warnings or declined work; and magenta
identifies a repair or rollback failure. Redirected logs retain the same phase
and stage labels without relying on colour.

Template Sync uses the same visual hierarchy for a long update preview. Purple
marks the change summaries, affected relative paths, and decisions that need
attention; yellow marks warnings and protected files. Its ignored
`.prodockit-template.log` contains the same wording without terminal colour
codes.

The repair engine can apply unambiguous `installation.metadata` repairs,
restore one declared shared file at a time, align bounded dependency pins,
rebuild project-local Mermaid or MathJax installations from valid lockfiles,
and make narrowly lossless `zensical.toml` corrections. Renderer installation
requires `--online`, healthy Node and npm, and a lockfile consistent with a
script-free project manifest. Configuration repair is limited to unique
Prodockit spelling corrections, obsolete index-setting moves, extensions
uniquely required by detected syntax, and known existing Prodockit CSS or
MathJax assets. Invalid values, missing author files, YAML, custom renderer
paths, and ambiguous choices remain unchanged with remediation guidance.

Each confirmed action records hashes and relative recovery paths under
`.prodockit-quarantine/diagnostics/<UTC timestamp>/manifest.json`, verifies
its postcondition, and rolls that action back if verification fails. Existing
shared-file bytes and pin declaration files are backed up before the existing
typed `shared-files` or `pins` service is called. Writes are atomic and pin
rewrites preserve operators, extras, comments, encoding, and CRLF/LF endings.
No diagnostic repair reads or invokes `prodockit-template` or `template-sync`.

When asking for support, attach the machine-readable report rather than a
screenshot:

```bash
pdk diag --json > prodockit-diagnostics.json
```

JSON schema version 2 reports pass, warning, and failure counts plus the repair
disposition for every stable check. `pdk diag --dry-run --json` adds every
available choice and represents possible commands as argument arrays rather
than executable shell strings. Interactive `pdk diag --apply --json` keeps its
plan and result as valid JSON on stdout while human context and prompts go to
stderr; its top-level `before`, `repair`, and `after` objects record selections,
confirmations, outcomes, changed paths, and the recovery manifest. The
schema number is a compatibility boundary: consumers may accept added fields
within version 2 but must reject a larger `schema_version` until reviewed.
Existing version-2 fields retain their meaning and type. The
command exits non-zero only for an actionable failure; warnings alone still
exit zero. The ordinary and dry-run forms never install, repair, generate, or
change project files.
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
- [Manual installation](installation.md) covers direct package setup, while
  [Requirements and dependencies](requirements-dependencies.md) records the
  supported tools and versions.
- [Repository metadata](devcons/repo-metadata.md) explains every derived link and badge.
- [Version pinning and drift](devcons/pinning-drift.md) covers controlled upgrades and scheduled comparisons.
- [Staying in step with the template](devcons/template-sync.md) protects project-owned writing while updating shared infrastructure.
- [Build and release](devcons/releasing.md) covers the package release from branch to PyPI and verified Pages deployment.
