---
icon: lucide/package-open
---

{{ heading_counter_reset(page) }}

# `pdk bootstrap`

`pdk bootstrap` prepares a machine and a project created from
`prodockit-template`. `pdk boot` is an exact shorter alias.

For the installation procedure and explanations of the 23 stages, use the
[Bootstrap task guide](../devcons/bootstrap.md). This page is the command
interface reference.

Bootstrap uses Prodockit's shared phases, stages, actions, and warning colours.
Use [section 29.1, Scan phases and
stages](output.md#command-output-structure) to interpret this visual summary:

![A left-aligned terminal report with separate callouts identifying a phase, stage, review-first changes, and warning](../assets/diagrams/command-output-anatomy.svg)

## Synopsis {: #cmd-bootstrap-synopsis }

Use one mutually exclusive mode for each Bootstrap run.

```text
pdk bootstrap [--check | --dry-run | --apply | --configure] [--config PATH]
pdk boot [OPTIONS]
```

With no mode option, Bootstrap checks every stage and changes nothing. The four
mode options are mutually exclusive.

## Working directory {: #cmd-bootstrap-working-directory }

Run Bootstrap from the **setup directory containing `.pdkboot.toml`**, not from
inside the generated project. It also accepts a directory below that setup
directory because it searches the current directory and its parents. Use
`--config PATH` only when the configuration is deliberately elsewhere.

If Bootstrap cannot find the intended file, it treats the current directory as
a new setup location and asks for missing configuration. Stop if the proposed
project path or configuration questions are unexpected; do not save a second
`.pdkboot.toml` in the wrong directory.

## Options {: #cmd-bootstrap-options }

\ref{tab-cmd-bootstrap-options} lists the machine and project setup controls.

| Option {: width="34%" } | Behaviour |
|---|---|
| `--check` | Report each stage and change nothing. This is also the default. |
| `-n`, `--dry-run` | Print the commands an applied run could use without running them. |
| `-a`, `--apply` | Set up outstanding stages, asking before each change. |
| `--configure` | Ask the configuration questions again, save the answers, then stop. |
| `--config PATH` | Use a specific Bootstrap configuration instead of the nearest `.pdkboot.toml`. |
| `--version` | Print the Bootstrap/Prodockit version and exit. |
| `-h`, `--help` | Show installed help and exit. |
/// table-caption | <
    attrs: {id: tab-cmd-bootstrap-options}

Bootstrap options
///

## Effects and prompts {: #cmd-bootstrap-effects-and-prompts }

An applied run can install machine software, create or update a project
environment, configure Git and SSH, clone a project, configure the editor, and
publish the first site. It presents work as stages, warns before consequential
changes, and asks where a decision is required. Rerunning it skips stages that
already pass.

The configuration file contains personal and project choices. Bootstrap keeps
it outside the generated project where possible and excludes it from Git.

## Network use {: #cmd-bootstrap-network-use }

Checks use local state where possible. Installation, host authentication,
cloning, pushing, and publication can contact package services or the selected
Git host. A dry run does not execute the reported installation commands.

## Result {: #cmd-bootstrap-result }

A successful check reports that all stages are set up. A blocking inspection,
invalid configuration, declined required action, or failed applied stage is
reported with the stage that needs attention.

## Related commands {: #cmd-bootstrap-related-commands }

Use these commands for narrower project integration and maintenance tasks:

- [`pdk adopt`](adopt.md) integrates Prodockit into an existing document
  without Bootstrap's machine, repository, editor, or publishing setup.
- [`pdk diag`](diag.md) checks the resulting project and environment.
- [`pdk template-sync`](template-sync.md) applies later template changes.
