---
icon: lucide/files
---

{{ heading_counter_reset(page) }}

# `pdk shared-files`

`pdk shared-files` checks or restores files declared in
`.prodockit-shared-files.toml` from the installed Prodockit release. It does not
read a sibling repository or fetch a template.

## Synopsis {: #cmd-shared-files-synopsis }

```text
pdk shared-files [--root PATH] [--check] [--verbose]
pdk shared-files --apply
```

## Working directory {: #cmd-shared-files-working-directory }

Run this command from the **project root** containing
`.prodockit-shared-files.toml`. Use `--root PATH` when deliberately checking a
different project.

From the wrong directory, it normally exits successfully with `No shared-file
manifest found. Nothing to check.` Treat that message as evidence that you
should confirm the directory, not as confirmation that the intended project's
managed files are current.

## Options {: #cmd-shared-files-options }

| Option {: width="34%" } | Behaviour |
|---|---|
| `-r`, `--root PATH` | Use another project root; defaults to the current directory. |
| `--check` | Exit non-zero if a declared file is missing or differs; write nothing. |
| `-a`, `--apply` | Replace missing or different files from the installed release. |
| `-v`, `--verbose` | Show expected and actual SHA-256 hashes. |
| `-h`, `--help` | Show installed help and exit. |

`--check` and `--apply` cannot be combined.

## Effects {: #cmd-shared-files-effects }

Apply mode touches only paths named by the manifest. Review local changes
before committing them. Move project-specific CSS or JavaScript into the
documented project-owned override files before replacing a managed shared
asset.

## Related commands {: #cmd-shared-files-related-commands }

- [`pdk pins`](pins.md) includes shared-file drift in its project consistency
  check when the manifest exists.
- [`pdk diag`](diag.md) reports each missing or different managed file and can
  offer an individually confirmed replacement.
