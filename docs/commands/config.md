---
icon: lucide/file-check-2
---

{{ heading_counter_reset(page) }}

# `pdk config`

`pdk config` loads the same resolved project configuration used by Prodockit's
build commands and reports the settings and local inputs it finds.

## Synopsis {: #cmd-config-synopsis }

```text
pdk config [--config-file PATH] [--check]
```

## Working directory {: #cmd-config-working-directory }

Run this command from the **project root**, where `zensical.toml` is located.
Use `--config-file PATH` to inspect a different project configuration; paths
inside that file are resolved relative to the configuration's directory.

From the wrong directory, the command exits with `Error: project configuration
not found: .../zensical.toml`. Change directory or supply the intended
configuration path.

## Options {: #cmd-config-options }

| Option {: width="36%" } | Behaviour |
|---|---|
| `-f`, `--config-file PATH` | Read another Zensical configuration; defaults to `zensical.toml`. |
| `--check` | Exit non-zero for invalid settings or missing project inputs. |
| `-h`, `--help` | Show installed help and exit. |

## Behaviour {: #cmd-config-behaviour }

The command validates Prodockit settings, configured source files, navigation,
stylesheets, JavaScript, citation style, and renderer paths without building
the website or PDF. Check mode is suitable for CI because actionable findings
produce a non-zero exit status.

The command is read-only. Use the reported setting path to correct the source
configuration, or use [`pdk diag --apply`](diag.md) when Diagnostics offers a
specific bounded correction.

## Related commands {: #cmd-config-related-commands }

- [`pdk diag`](diag.md) includes the configuration result within the complete
  project health report.
- [`pdk pdf`](pdf.md) consumes the resolved PDF settings.
