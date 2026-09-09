# Adopt message review

Review of the command presentation in `cli.py`, assessment/application in
`adopt.py`, settings review, runtime/package-manager/browser helpers, and shared
installer progress/recovery. This is a review and proposed output contract,
not an implemented message redesign.

## Recommended default output

Every item requiring a decision should answer three questions:

- **Why:** what will not work, or why this change is needed.
- **Change:** what Adopt will do, including effects outside this project.
- **Next:** the action the reader must take, or that no action is needed.

Keep the existing phase/activity structure and colour palette. Use purple for
changes/decisions and amber for warnings/recovery; retain text labels so colour
is never the only signal. Healthy items need one short line. Omitted features
should say “Not selected”, not imply software was removed or never installed.

Example (only when dependency installation is actually needed):

```text
Activity [3/11] Software needed by this project
Why:    Some installed software does not match this Prodockit release.
Change: Install the supported versions in the active Python environment.
        [List actual packages and version changes here.]
        This may upgrade or downgrade those packages.

Make these changes? [Y/n]:
```

A declaration-only change needs different wording: “The project records a
different software version. Update the project settings; no software install
is needed.” Do not infer these distinctions by matching free-form strings.

## Findings by message family

| Area | Problem for the reader | Recommendation |
| --- | --- | --- |
| Startup | Long project/choices/source report arrives before the outcome. | Show project, preview/apply mode and selected optional features. Put snapshot identity, cache and choice-file provenance in verbose output. |
| Healthy checks | Paths, package details and internal configuration statements dominate the report. | “Ready — no change needed.” Keep technical evidence in verbose output. |
| Change activities | `Current` and `Will do` frequently repeat the same detail. | Separate reason, intended change and user action. Retain actual package version changes before confirmation. |
| Core configuration | Lists of extension identifiers do not explain the benefit. | Explain that this enables Prodockit formatting and connects shared styles/scripts; user customisations are retained. List keys/files in verbose output. |
| Choices | Ledger/manifest terminology obscures why saving matters. | “Save your choices so future runs use the same options.” Verbose shows the filename and source of inferred choices. |
| PDF software | “Native dependencies”, library paths and font-cache details lack context. | Explain that PDF generation needs extra software/fonts. Say whether the change affects the computer or only the current environment. |
| Node/npm | Assumes users know why these tools are needed. | Explain that selected diagram/maths features need Node.js. State automatic installation and possible administrator approval. |
| Mermaid/browser | Puppeteer, executable and architecture terminology appears without purpose. | Explain that a browser draws diagrams for the PDF and Adopt installs/reuses it automatically. Preserve explicit invalid-path values in actionable errors. |
| Maths | “Scaffold MathJax” describes implementation rather than outcome. | “Install the software that renders mathematical notation and connect it to your site.” |
| Citation style | CSL acronym and file validation lack meaning. | “Download the style that controls how citations and references look.” Show the configured style and preserve existing custom styles. |
| Settings snapshot/cache | Commit hashes, TOML validation and cache errors are presented as primary problems. | “Could not load the default settings. No changes made. Check your connection and try again.” Offer compatible local configuration as an advanced alternative; retain technical cause in verbose/log output. |
| Retry | “Transient operation failure” does not tell the reader whether to intervene. | “The download was interrupted. Retrying in 2 seconds (attempt 2 of 3). You do not need to do anything.” Use neutral wording if the failure was not a download. |
| Progress | “Installing with bash/python” names a wrapper, not the task. | Pass the activity's human-readable label to progress reporting, e.g. “Installing PDF software — 30 seconds elapsed.” |
| Timeout | “Check child processes” is not an actionable instruction for a novice. | State installation did not finish, what cleanup was confirmed, and why retry is paused. Provide platform-specific recovery; never claim detached installers stopped. |
| Finished | “Configuration verified” can be mistaken for a verified website/PDF. | “Setup is complete. Now check your project:” followed by `pdk diag` and the correct build command. Explain that a build tests the site; do not claim publishing occurred. |
| Nothing changed | Already-configured exit omits a useful next action. | Give the same short diagnostic/build next steps as a successful changed run. |
| Partial completion | Raw errors can obscure that earlier activities succeeded. | State what remains incomplete and that rerunning resumes checks. Do not claim “no changes” after earlier successful changes. |

## Correctness fixes before shortening output

1. `_adopt_blocker_summary` recommends installing Node whenever Mermaid or maths
   has a blocker. This is wrong for browser overrides, offline browser downloads
   and unsupported hosts. Use the specific problem's recovery instructions.
2. The restart banner in `adopt_node.apply` treats every failed post-install
   check as requiring a terminal restart. Distinguish stale command lookup from
   failed installation; a restart is not a general repair.
3. An unselected maths item says “MathJax is not installed”. An explicit opt-out
   can leave an existing installation present. Say “Not selected for this run”.
4. The newer-project guard currently reports through an “Existing documentation
   project” item. Label compatibility separately, and provide the platform's
   usable upgrade command, preserving requested extras where applicable.
5. Do not bury package downgrade warnings, administrator approval, machine-wide
   changes, overwritten managed files, restart instructions or errors in verbose.
6. Printing every native installer command can expose a long PowerShell script
   in normal output. Show its purpose and scope before approval; `--verbose`
   can expose the command itself.

## Verbose and support evidence

Keep in normal output: outcome, selected features, significant version changes,
permission/scope warnings, required choices and exact recovery commands.

Move to `--verbose`: healthy probe details, interpreter and cache paths,
snapshot revisions, extension identifiers, full file lists, raw commands,
successful installer output, retry internals and tracebacks.

Do not require users to repeat a modifying command just to recover lost failure
details. Preserve diagnostic output in a bounded local log and print its path.
Review redaction of credentials and private URLs before adding persistent logs.
This logging is a separate implementation task; the current runner uses
temporary capture files and does not provide this persistent failure log.

## Message acceptance tests

- Capture normal and verbose output for fresh/default, both-renderer, aligned,
  declaration-only, install/upgrade/downgrade, declined and partially failed runs.
- Cover wrong environment, newer project release, missing Homebrew, missing
  WinGet, administrator refusal, offline misses, browser override, download
  retries, timeout/interruption and restart-required states on each platform.
- Assert normal output contains a reason, scope and next action where needed.
- Assert verbose adds evidence without changing execution or hiding warnings.
- Check colour enabled/disabled, redirected output and narrow terminal widths.
- Ensure success distinguishes setup checks, site build, PDF build and publishing.
- Verify optional features disabled does not make false claims about files removed.

Native Windows/Ubuntu acceptance is still outstanding; this review does not
mark the cross-platform installer test programme complete.

## Implementation checkpoint

The first message implementation now provides Why/Change descriptions, concise
healthy checks and normal/verbose separation for snapshot/choice provenance,
file lists and installer commands. Dependency and renderer version details,
warnings and recovery information remain in normal output. Declaration-only
alignment explicitly says no software installation is needed.

It removes generic Node-install advice from renderer blockers, describes
unselected features without claiming their files are absent, makes a restart
conditional after failed Node verification, and warns that earlier completed
changes remain after an activity fails. Completed/no-change runs give diagnostic
and build commands and distinguish local building from publication.

Remaining improvements from this review: persistent redacted failure logs,
human-readable progress labels passed into every installer, structured runtime
reason/recovery fields instead of technical detail strings, and platform-specific
novice timeout recovery. Raw failure evidence remains visible until it can be
preserved reliably; it has not simply been hidden behind verbose output.

Verification: **2,966 passed, 11 skipped, 17 deselected** in the full regression
suite after edits stopped. Focused tests cover normal/verbose differences,
colour/plain output, visible downgrade warnings, declaration-only updates and
browser-specific blockers. Lint, formatting and whitespace checks pass.
