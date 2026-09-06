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

## Synopsis {: #cmd-diag-synopsis }

```text
pdk diag [OPTIONS]
pdk diag --dry-run [--apply-check CHECK_ID ...]
pdk diag --apply [--apply-check CHECK_ID ...]
```

## Working directory {: #cmd-diag-working-directory }

Run Diagnostics from the **project root**, the directory containing
`zensical.toml`, `.venv`, and normally `.git`. To inspect another configuration
deliberately, pass `--config-file PATH`.

From the wrong directory, the report normally contains `FAIL Project
configuration could not be loaded` followed by `project configuration not
found: .../zensical.toml`. It may also warn that the directory is not a Git
repository. These are location errors; change directory rather than repairing
the unrelated folder.

## Options {: #cmd-diag-options }

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

| Result | Exit status |
|---|---|
| `PASS` | Zero. Every required check passed. |
| `WARN` | Zero. Required checks passed but the warnings need review. |
| `FAIL` | Non-zero. At least one required check failed. |

## Related commands {: #cmd-diag-related-commands }

- [`pdk adopt`](adopt.md) applies project integration stages named by the
  Adopt-readiness check.
- [`pdk pins`](pins.md) owns reviewed version-selection decisions.
- [`pdk template-sync`](template-sync.md) checks and applies remote template
  changes.
