---
icon: lucide/list-tree
---

{{ heading_counter_reset(page) }}

# Reading command output

Prodockit's longer commands use one presentation language for checks,
decisions, changes, and verification. Learn it once, then use the same visual
landmarks in Bootstrap, Adopt, diagnostic repairs, and Template Sync. Pins uses
the same decision vocabulary without the complete phase-and-activity frame.

The words are authoritative: colour helps you scan a long report, but never
carries meaning on its own.

## Scan phases and activities {: #command-output-structure }

A phase groups related work. An activity is one check or decision inside that
phase. The current and total numbers show where you are without implying that
every activity needs a change.

\ref{fig-command-output-anatomy} keeps the command's own counters separate from
the labels that explain its colour and structure. Select the figure to enlarge
it.

![A left-aligned terminal report with separate callouts identifying a phase, activity, review-first changes, and warning](../assets/diagrams/command-output-anatomy.svg){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-command-output-anatomy}

How to scan a phase-and-activity report
///

`Activity [3/5]` means the third displayed activity out of five; it is not an error
count. `CHECK` normally means no change, while `ALIGN`, `CONFIGURE`, `INSTALL`,
`REPAIR`, or `CHOOSE` names work an applied run may perform.

## Follow a decision {: #command-output-decisions }

Commands that can change state separate inspection from action. They show the
plan before asking, and a potentially consequential action defaults to no.

<figure class="pdk-output-flow-figure">
  <div class="pdk-output-flow" aria-label="Preview, review, decide, confirm and verify sequence">
    <div><strong>Preview</strong><span>read-only</span></div>
    <span class="pdk-output-flow__arrow" aria-hidden="true">→</span>
    <div class="pdk-output-flow__change"><strong>Review</strong><span>purple lines and diffs</span></div>
    <span class="pdk-output-flow__arrow" aria-hidden="true">→</span>
    <div class="pdk-output-flow__warning"><strong>Decide</strong><span>safe default: no or skip</span></div>
    <span class="pdk-output-flow__arrow" aria-hidden="true">→</span>
    <div><strong>Confirm</strong><span>type <code>y</code> when required</span></div>
    <span class="pdk-output-flow__arrow" aria-hidden="true">→</span>
    <div><strong>Verify</strong><span>recheck the result</span></div>
  </div>
  <figcaption>The standard path from inspection to a verified change</figcaption>
</figure>

Preview and dry-run modes do not make decisions or change state. Apply mode
still does not imply blanket consent: where the command offers alternatives,
choose one; where it warns about a mutation, type an exact `y` to confirm it.
Pressing Enter accepts the safe default instead.

## Read the fields {: #command-output-fields }

\ref{tab-command-output-fields} defines the recurring labels shown beneath a
activity heading.

| Field {: width="24%" } | Meaning |
|---|---|
| `Action` | Classification of the work, such as `CHECK`, `ALIGN`, `INSTALL`, or `CHOOSE`. |
| `Current` | What the command found before making any change. |
| `Required` or `Goal` | The supported or requested state against which current state is compared. |
| `Will do` | The bounded action available in an applied run. |
| `Command` | The external command that could run. Read it before confirming. |
| `File` or `Affects` | Project-relative paths or system state within the action's scope. |
| `Network` | Whether the action may contact a package service, mirror, or Git host. |
| `Recovery` | What can be restored or where a recovery record will be kept. |
| `Result` | Outcome of the activity, phase, plan, or complete command. |
/// table-caption | <
    attrs: {id: tab-command-output-fields}

Common output fields
///

## Read status labels {: #command-output-status }

The three cards below separate a completed check from a caution or failure.

<div class="pdk-output-statuses">
  <div><strong>PASS</strong><span>The required check succeeded.</span></div>
  <div><strong class="pdk-terminal-key__warning">WARN</strong><span>Required checks may pass, but review this condition.</span></div>
  <div><strong class="pdk-terminal-key__change">FAIL</strong><span>A required check failed or an action could not complete.</span></div>
</div>

`WARN` is not a synonym for failure. Diagnostics exits successfully when it has
warnings but no failures. A warning can still identify optional software,
protected work, drift, or a decision worth resolving before publication.

## Use plain or redirected output {: #command-output-without-colour }

Prodockit removes terminal escape codes when output is redirected and writes
plain-text logs. Labels such as `Phase`, `Activity`, `Action`, `WARN`, `WARNING`,
`Decision`, and `Result` therefore retain the complete meaning without colour.
Do not infer success from colour alone; read the final result and exit status.

## Find command-specific meaning {: #command-output-command-details }

\ref{tab-command-output-details} identifies which parts of the shared language
each longer command uses.

| Command {: width="20%" } | Shared presentation | Command-specific reference |
|---|---|---|
| Bootstrap | Phases, activities, actions, warnings, and applied verification | [`pdk bootstrap`](bootstrap.md) |
| Diagnostics | Status labels normally; phases, activities, choices, recovery, and verification with `--dry-run` or `--apply` | [`pdk diag`](diag.md) |
| Adopt | Four phases, selected activities, toolchain actions, and final verification | [`pdk adopt`](adopt.md) |
| Pins | Current, supported, and selected versions plus explicit package decisions | [`pdk pins`](pins.md) |
| Template Sync | Four phases, protected-file decisions, diffs, and template release movement | [`pdk template-sync`](template-sync.md) |
/// table-caption | <
    attrs: {id: tab-command-output-details}

Commands that use the shared output language
///
