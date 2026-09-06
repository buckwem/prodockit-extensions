---
icon: lucide/blocks
---

{{ heading_counter_reset(page) }}

# `pdk adopt`

`pdk adopt` adds selected Prodockit components and the supported toolchain to
an existing Zensical document. It is project-scoped: it does not configure Git,
SSH, an editor, a remote, or Pages, and it never commits or pushes.

Use the [Adopt task guide](../adopt.md) for the preparation and review workflow.

## Synopsis {: #cmd-adopt-synopsis }

Use the assessment form first, then choose configuration, preview, or apply.

```text
pdk adopt [OPTIONS]
pdk adopt --configure
pdk adopt --dry-run
pdk adopt --apply
```

With no mode option, Adopt assesses the project and reports outstanding stages.

## Working directory {: #cmd-adopt-working-directory }

Run Adopt from the **root of the existing project**, where its Zensical
configuration and `.venv` are located. Adopt has no project-path option because
its safety checks and changes are intentionally scoped to the current project.

If the current directory holds one or more project repositories, Adopt refuses
to start and names them:

```text
Error: C:\path\to\workspace holds projects rather than being one (report-student).
Open a terminal in the project you want adopted, or cd into it.
```

In another wrong directory, the first assessment reports `Existing
documentation project — no Zensical configuration is here` and tells you to
run the command from the directory containing the configuration. Stop there
and change directory; do not create a configuration merely to satisfy Adopt.

## Options {: #cmd-adopt-options }

\ref{tab-cmd-adopt-options} lists the available project-integration controls.

| Option {: width="34%" } | Behaviour |
|---|---|
| `--configure` | Choose optional components and save them in `.prodockit-components.toml`. |
| `-n`, `--dry-run` | Show stages, files, and changes without writing or installing. |
| `-a`, `--apply` | Apply required stages, asking before each change. |
| `--offline` | Use only the configured wheelhouse and validated native cache. |
| `--mermaid`, `--no-mermaid` | Select or omit project-local Mermaid rendering. |
| `--maths`, `--no-maths` | Select or omit MathJax rendering. |
| `-v`, `--verbose` | Show the files and commands behind each stage summary. |
| `-h`, `--help` | Show installed help and exit. |
/// table-caption | <
    attrs: {id: tab-cmd-adopt-options}

Adopt options
///

## Output {: #cmd-adopt-output }

\ref{fig-cmd-adopt-output} shows the output structure. Use [section 28.1, Scan
phases and stages](output.md#command-output-structure) for the complete
explanation of the phase, stage, action, warning, and decision language:

![A left-aligned terminal report with separate callouts identifying a phase, stage, review-first changes, and warning](../assets/diagrams/command-output-anatomy.svg){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-cmd-adopt-output}

Adopt output structure
///

## Effects and ownership {: #cmd-adopt-effects-and-ownership }

Adopt can install, upgrade, or downgrade software in the active project
environment to the combination supported by the installed Prodockit release.
It can also align version declarations, enable the standard extensions and
styles, save component choices, and initialise selected project-local
renderers. System-native libraries remain outside its repair boundary.

`.prodockit-components.toml` belongs to the project. When it is missing, Adopt
infers established Mermaid and maths choices from the project configuration and
offers to save them rather than silently selecting new features.

## Result {: #cmd-adopt-result }

Assessment and dry-run modes report the number of stages needing work. Apply
mode verifies each completed stage and finishes by naming the strict local
build command. A blocking project or environment check stops the integration.

Adopt is independent of Bootstrap. If a virtual environment is active and the
project has its own `.venv`, they must match; otherwise Adopt stops before
configuration or package changes. An intentionally named environment is accepted
when the project has no `.venv`. With no active virtual environment, Adopt warns
that package changes will affect the running Python installation. Create and
activate an environment first unless that is intentional.

## Related commands {: #cmd-adopt-related-commands }

Use these commands before or after Adopt for their separate responsibilities:

- [`pdk diag`](diag.md) reports when Adopt integration remains and verifies the
  result.
- [`pdk pins`](pins.md) makes an explicit version-selection decision across
  declarations.
- [`pdk template-sync`](template-sync.md) invokes Adopt as a prerequisite but
  separately owns template files and review branches.
