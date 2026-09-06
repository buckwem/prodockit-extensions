---
icon: lucide/refresh-cw
---

{{ heading_counter_reset(page) }}

# `pdk template-sync`

`pdk template-sync` compares a generated project with its recorded template,
protects author-edited files, and coordinates a reviewed update. The default
run is a preview.

Use the [Template Sync task guide](../devcons/template-sync.md) for the complete
review, merge, and verification workflow.

## Synopsis {: #cmd-template-sync-synopsis }

Use preview mode first, then apply with any protected files selected for review.

```text
pdk template-sync [OPTIONS]
pdk template-sync --apply [--review-all]
```

## Working directory {: #cmd-template-sync-working-directory }

Run Template Sync from the **top of the project repository**. It deliberately
has no `--root` option: branch creation, protected-file comparison, staging,
and the review request must all refer to the same checkout.

From a subdirectory it reports that the directory is inside a project and
prints the `cd` command for its root. From a workspace holding several projects
it says that the directory `holds projects rather than being one`; elsewhere it
reports `is not a git repository`. Change directory and rerun it.

## Options {: #cmd-template-sync-options }

\ref{tab-cmd-template-sync-options} lists update, review, source, and prerequisite controls.

| Option {: width="38%" } | Behaviour |
|---|---|
| `-a`, `--apply` | Apply the report on a separate branch and send it for pull- or merge-request review. |
| `-v`, `--verbose` | Show sources, comparison evidence, and individual paths. |
| `--push` | After confirmation, update `main` directly instead of using a review request; requires `--apply`. |
| `--local-only` | Apply and stage locally without committing or sending; requires `--apply`. |
| `--force FILE-PATH` | Select one edited file for a diff and overwrite, `.new`, or skip decision. Repeatable. |
| `--review-all` | Select every edited template file for individual diff review. |
| `--github [OWNER/REPO]` | Use the usual or named GitHub template. |
| `--surrey [GROUP/REPO]` | Use the usual or named Surrey GitLab template. |
| `--template-path PATH` | Compare with an existing local template checkout. |
| `--offline` | Use only the wheelhouse and validated native cache for prerequisites. |
| `--accept-prodockit` | Authorise an exact prerequisite Prodockit replacement without prompting. |
| `--accept-adopt` | Authorise prerequisite Adopt alignment without prompting. |
| `-h`, `--help` | Show installed help and exit. |
/// table-caption | <
    attrs: {id: tab-cmd-template-sync-options}

Template Sync options
///

## Output {: #cmd-template-sync-output }

Use [section 29.1, Scan phases and
stages](output.md#command-output-structure) to interpret Template Sync's phase,
stage, action, warning, and decision output:

![A left-aligned terminal report with separate callouts identifying a phase, stage, review-first changes, and warning](../assets/diagrams/command-output-anatomy.svg)

## Protected-file decisions {: #cmd-template-sync-protected-file-decisions }

An edited template-owned file is unchanged until explicitly selected.
`--review-all` selects the complete protected set; `--force` selects named
files. The applied run shows the complete diff for each and offers:

\ref{tab-cmd-template-sync-decisions} shows the three decisions available for
each selected protected file.

| Choice {: width="22%" } | Result |
|---|---|
| `overwrite` | Replace the project copy with the incoming template copy. |
| `new` | Keep the project copy and write the incoming version as `FILE-PATH.new`. |
| `skip` | Keep the project copy and create no sidecar. This is the default. |
/// table-caption | <
    attrs: {id: tab-cmd-template-sync-decisions}

Protected-file decisions
///

## Prerequisites and effects {: #cmd-template-sync-prerequisites-and-effects }

Before copying template files, the command verifies the exact Prodockit release
paired with the incoming template and reuses Adopt for supported-toolchain and
component alignment. Template Sync orchestrates those commands; it does not
duplicate their repair logic.

A normal applied update creates a branch and one consistent commit. GitLab
merge requests are created automatically; GitHub receives the branch and a
pull-request link. Project writing, figures, bibliography, and project-owned
component choices are not template-owned.

## Related commands {: #cmd-template-sync-related-commands }

Use these commands to verify or align the project around a template update:

- [`pdk diag`](diag.md) verifies local health before and after an update.
- [`pdk adopt`](adopt.md) owns the independent integration stages.
- [`pdk pins`](pins.md) owns explicit dependency-version choices.
