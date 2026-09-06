---
icon: lucide/pin
---

{{ heading_counter_reset(page) }}

# `pdk pins`

`pdk pins` finds version declarations across a project and moves the selected
package versions together while preserving each declaration's existing
operator. With no options it prompts once per managed package and offers the
combination tested with the installed Prodockit release.

Use the [version maintenance task guide](../devcons/pinning-drift.md) when
evaluating an upgrade or comparing generated output.

Pins uses the shared [decision and field
language](output.md#command-output-decisions), although its shorter report does
not need the complete phase-and-stage frame.

## Synopsis {: #cmd-pins-synopsis }

Use interactive selection, read-only checking, or explicit version assignments.

```text
pdk pins [OPTIONS]
pdk pins --check --offline
pdk pins --set PACKAGE=VERSION [--set PACKAGE=VERSION ...]
```

## Working directory {: #cmd-pins-working-directory }

Run Pins from the **project root** so it can find every declaration in the
workflows, requirements files, toolchain file, and Python version file. Use
`--root PATH` when deliberately managing a different project.

From an unrelated directory, Pins usually does not fail: it reports `not
declared anywhere` for each package and ends with `No version declarations
found. Nothing to do.` That means the directory is wrong; it does not mean the
project has no versions to maintain.

## Options {: #cmd-pins-options }

\ref{tab-cmd-pins-options} lists package-selection and check controls.

| Option {: width="36%" } | Behaviour |
|---|---|
| `-r`, `--root PATH` | Scan another project root; defaults to the current directory. |
| `-p`, `--package NAME` | Manage one package; repeat to select several. |
| `--set PACKAGE=VERSION` | Set an explicit version without prompting; repeatable and implies `--no-input`. |
| `--latest` | Select the newest PyPI release for every managed package without prompting. |
| `--no-input` | Never prompt; update only packages already selected by `--set` or `--latest`. |
| `--check` | Report drift or disagreement and write nothing. |
| `--offline` | Skip PyPI and use only declarations plus Prodockit's tested combination. |
| `-h`, `--help` | Show installed help and exit. |
/// table-caption | <
    attrs: {id: tab-cmd-pins-options}

Pins options
///

The default managed set is Zensical, WeasyPrint, Prodockit, Markdown,
PyMdown Extensions, Pandoc, and Python.

## Effects {: #cmd-pins-effects }

Pins changes only discovered version declarations. A minimum constraint stays
a minimum constraint and an exact CI pin stays exact. It does not install the
selected software, copy template files, or repair renderer binaries. When a
shared-file manifest is present, check mode also reports shared-file drift.

`--latest` is an explicit decision to move beyond the combination tested with
the installed Prodockit release. Rebuild and compare both website and PDF
before retaining such a change.

## Exit status {: #cmd-pins-exit-status }

Normal interactive or set mode exits non-zero on an invalid selection or a
file that cannot be updated safely. `--check` exits non-zero when declarations
disagree, a managed release is behind the checked source, or a declared shared
file differs.

## Related commands {: #cmd-pins-related-commands }

Use these commands to diagnose, install, or synchronize the selected versions:

- [`pdk diag`](diag.md) reports unsupported combinations and points to Pins for
  the version decision.
- [`pdk adopt`](adopt.md) installs and aligns the supported project toolchain.
- [`pdk template-sync`](template-sync.md) follows the incoming template's paired
  Prodockit release before applying template files.
