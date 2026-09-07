---
icon: lucide/activity
---

{{ heading_counter_reset(page) }}

# `pdk diag`

`pdk diag` inspects the active Python environment, project configuration,
dependency declarations, managed files, renderers, repository, and template
metadata. The default run is deterministic, offline, and read-only.

For the complete catalogue of stable check IDs and their remediation, use the
[Diagnostics guide](../devcons/diagnostics.md).

The shared [status guide](output.md#command-output-status) explains normal
`PASS`, `WARN`, and `FAIL` results.

## Synopsis {: #cmd-diag-synopsis }

Use the read-only report first; add dry-run or apply only for bounded repairs.

```text
pdk diag [OPTIONS]
pdk diag --dry-run [--apply-check CHECK_ID ...]
pdk diag --apply [--apply-check CHECK_ID ...]
```

## Working directory {: #cmd-diag-working-directory }

Run Diagnostics from the **project root**, the directory containing
`zensical.toml`, `.venv`, and normally `.git`. To inspect another configuration
deliberately, pass `--config-file PATH`.

After Bootstrap, complete [the project activation and checks](../devcons/bootstrap.md#bootstrap-project-checks)
first. The parent setup environment stays active when you merely change directory.

If the project has a `.venv` but another Python environment is active,
Diagnostics reports that mismatch and stops after the environment preflight.
Renderer failures and Adopt work would describe the wrong environment, so they
are deliberately not assessed. Deactivate the current environment, activate
the project's `.venv`, and rerun `pdk diag` for the complete report.

If the current directory holds one or more project repositories, Diagnostics
refuses to start and names them:

```text
Error: C:\path\to\workspace holds projects rather than being one (report-student).
Open a terminal in the project you want checked, or cd into it.
```

In another wrong directory, the report can instead contain `FAIL Project
configuration could not be loaded` followed by `project configuration not
found: .../zensical.toml`. These are location errors; change directory rather
than repairing the unrelated folder.

## Options {: #cmd-diag-options }

\ref{tab-cmd-diag-options} lists diagnostic reporting and repair controls.

| Option {: width="34%" } | Behaviour |
|---|---|
| `-f`, `--config-file PATH` | Read a configuration other than `zensical.toml`. |
| `-v`, `--verbose` | Show resolved paths, versions, and passing evidence. |
| `-o`, `--online` | Also query PyPI, npm advisories, and the recorded template revision. |
| `--json` | Emit stable structured output for CI or a support request. |
| `-n`, `--dry-run` | Show every bounded repair option and command; change nothing. |
| `-a`, `--apply` | Consider supported repairs, with a separate default-No confirmation before every mutation. |
| `--apply-check CHECK_ID` | Limit dry-run or apply mode to one stable check ID; repeat as needed. |
| `-h`, `--help` | Show installed help and exit. |
/// table-caption | <
    attrs: {id: tab-cmd-diag-options}

Diagnostics options
///

## Repair-plan output {: #cmd-diag-repair-plan-output }

\ref{fig-cmd-diag-repair-output} shows the repair-plan structure. Use [section
29.1, Scan phases and stages](output.md#command-output-structure) for the
complete explanation of dry-run and apply output:

![A left-aligned terminal report with separate callouts identifying a phase, stage, review-first changes, and warning](../assets/diagrams/command-output-anatomy.svg){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-cmd-diag-repair-output}

Diagnostics repair-plan output structure
///

## Repair boundary {: #cmd-diag-repair-boundary }

`--apply` is not a blanket fixer. It prints the complete plan first, then asks
for a decision and an exact `y` confirmation for each eligible action. It
refuses redirected input and CI use. Repairs are independent of
`prodockit-template`; template updates remain the responsibility of
`template-sync`.

## Network use {: #cmd-diag-network-use }

The default is offline. `--online` adds current-release, advisory, and remote
template checks. Renderer installation is considered only when online mode is
explicitly selected.

## Exit status {: #cmd-diag-exit-status }

\ref{tab-cmd-diag-exit-status} separates cautions from required failures.

| Result {: width="20%" } | Exit status |
|---|---|
| `PASS` | Zero. Every required check passed. |
| `WARN` | Zero. Required checks passed but the warnings need review. |
| `FAIL` | Non-zero. At least one required check failed. |
/// table-caption | <
    attrs: {id: tab-cmd-diag-exit-status}

Diagnostics exit status
///

## Related commands {: #cmd-diag-related-commands }

Use the command named by the diagnostic result rather than treating apply as a
blanket repair:

- [`pdk adopt`](adopt.md) applies project integration stages named by the
  Adopt-readiness check.
- [`pdk pins`](pins.md) owns reviewed version-selection decisions.
- [`pdk template-sync`](template-sync.md) checks and applies remote template
  changes.
