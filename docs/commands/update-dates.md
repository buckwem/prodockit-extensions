---
icon: lucide/calendar-clock
---

{{ heading_counter_reset(page) }}

# `pdk update-dates`

`pdk update-dates` adds per-page revision dates to an already-built website.
It changes generated HTML, never source Markdown or configuration.

Use the [page update dates guide](../update-dates.md) to configure placement
and understand the website/PDF relationship.

## Synopsis {: #cmd-update-dates-synopsis }

```text
pdk update-dates [--config-file PATH] [--modification-dates]
```

## Working directory {: #cmd-update-dates-working-directory }

Run this command from the **project root**, after Zensical has built the site.
Use `--config-file PATH` when deliberately updating another project's built
output.

From the wrong directory it normally reports `project configuration not found:
.../zensical.toml`. If the configuration exists but its generated site does
not, expect `built site not found: ...; run zensical build first`.

## Options {: #cmd-update-dates-options }

| Option {: width="40%" } | Behaviour |
|---|---|
| `-f`, `--config-file PATH` | Read another Zensical configuration; defaults to `zensical.toml`. |
| `--modification-dates` | Use source-file modification times instead of Git author dates. |
| `-h`, `--help` | Show installed help and exit. |

## Inputs and effects {: #cmd-update-dates-inputs-and-effects }

Run Zensical before this command. By default, Git supplies the last author date
for each tracked page. An untracked page or non-Git project falls back to its
source modification time; configured manual or existing dates are retained
where applicable.

The command updates only the configured `site_dir`. A later clean website build
replaces generated HTML, so run the date update at the documented point in the
publishing workflow.

## Related commands {: #cmd-update-dates-related-commands }

- [`pdk sync-repo`](sync-repo.md) aligns other repository-derived website
  metadata.
- [`pdk pdf`](pdf.md) reads revision information through the configured PDF
  pipeline.
