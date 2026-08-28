---
icon: lucide/wrench
---

{{ heading_counter_reset(page) }}

# Maintain prodockit

This section is for maintainers of the prodockit repository. It covers the
package's own source, test matrix, documentation artifacts, pinned build
inputs, GitHub Actions workflows, PyPI release, and public documentation
deployment.

If you are writing and publishing a document with prodockit, use
[Publish a document](publishing.md) instead. Machine setup, `prodockit-template`,
template syncing, PDF generation, and Pages publication belong to that author
workflow.

## The maintenance cycle

The \index{maintenance cycle} below keeps repository identity, dependency
versions, generated artifacts, and release automation under review.

/// steps

//// step | Start from a clean default branch

Update the branch GitHub publishes and confirm that no local work will be
mixed into the maintenance change:

```bash
git switch main
git pull --ff-only
git status --short
```

Create a branch for the work rather than maintaining directly on `main`:

```bash
git switch -c maintenance/update-build-inputs
```

////

//// step | Check repository identity

Confirm that the website links, edit buttons, brand icon, and README badges
still describe the remote this checkout uses:

```bash
prodockit sync-repo --check
```

If it reports drift, run `prodockit sync-repo`, review the diff, and repeat
the check. See [Repository metadata](devcons/repo-metadata.md).

////

//// step | Check pinned build inputs

First check that every file agrees without asking the network for newer
releases:

```bash
prodockit pins --check --offline
```

Use the scheduled drift workflow to decide whether to adopt a newer release.
Do not upgrade merely to clear a notification: rebuild and compare the output
first. See [Version pinning and drift](devcons/pinning-drift.md).

////

//// step | Build the deliverables locally

Build in the same order as GitHub Actions. The PDF consumes the completed
Zensical site, so the website comes first:

```bash
zensical build --clean --strict
prodockit pdf
```

Then run the checks appropriate to the repository. For prodockit itself:

```bash
ruff check .
mypy src
prodockit pins --check --offline
pytest
```

////

//// step | Review, push, and use the pull request gates

Review both source and generated output. Commit the source changes, push the
branch, and open a pull request:

```bash
git diff --check
git status --short
git add <reviewed-files>
git commit -m "Maintain project build inputs"
git push -u origin HEAD
gh pr create
```

GitHub Actions runs the test matrix and strict documentation build on the pull
request. Merge only after those required checks pass. Package releases have
additional gates described in [Build and release](devcons/releasing.md).

////

///

## Choose the right maintenance tool

Match the maintenance need to its safest starting tool in
\ref{tab-project-maintenance-choose-the-right-maintenance-tool}.

| Need | Start with | What changes |
|---|---|---|
| A fork, mirror, or renamed repository points at the wrong place | `prodockit sync-repo --check` | Repository URLs, edit links, host icon, and managed README badges |
| CI files disagree about dependency versions | `prodockit pins --check --offline` | Version declarations, preserving each file's existing operator |
| A newer dependency may change published output | GitHub's `drift.yml` result | Nothing automatically; it opens or updates an issue with the comparison |
| A prodockit release is ready | The release checklist | Package version, release notes, GitHub release, PyPI package, and rebuilt documentation |
/// table-caption | <
    attrs: {id: tab-project-maintenance-choose-the-right-maintenance-tool}

Choose the right maintenance tool
///

## What automation does—and does not—prove

The workflows deliberately divide responsibility:

\ref{tab-project-maintenance-what-automation-does-and-does-not-prove} separates the checks performed by automation from the decisions that still need a person.

| Workflow {: width="30%" } | Trigger | Answer |
|---|---|---|
| `ci.yml` | Pull requests and pushes to `main` | Does the code work across supported Python versions, and do the docs build strictly? |
| `docs.yml` | Pushes to `main` and manual dispatch | Can the complete website and PDF be built, tested, deployed, and verified live? |
| `drift.yml` | Weekly schedule and manual dispatch | Would newer rendering dependencies change the published artifacts? |
| `publish.yml` | Published GitHub release | Can the tagged source build and publish to PyPI through Trusted Publishing? |
| `release-redeploy.yml` | Published GitHub release | Can `docs.yml` be rerun against `main` so the site sees the new tag? |
/// table-caption | <
    attrs: {id: tab-project-maintenance-what-automation-does-and-does-not-prove}

What automation does—and does not—prove
///

A green workflow proves the question in its own row in
\ref{tab-project-maintenance-what-automation-does-and-does-not-prove}, not every
row. In
particular, a passing pull request does not publish PyPI, and a successful
Pages deployment does not by itself prove the public URL serves the new bytes.
The deployment workflow performs that final delivery check separately.

## Suggested cadence

\ref{tab-project-maintenance-suggested-cadence} turns the maintenance tools
into a practical event-based routine.

| When | Maintenance |
|---|---|
| Every pull request | Repository and pin consistency, tests, lint, typing, strict docs build |
| Weekly | Let `drift.yml` compare pinned and newest renderers; triage the issue it opens |
| After moving or forking a repository | Run `sync-repo`, rebuild, and inspect canonical/edit links and badges |
| Before a package release | Complete the local build gates, merge the release PR, publish a GitHub release, verify PyPI and Pages |
/// table-caption | <
    attrs: {id: tab-project-maintenance-suggested-cadence}

Suggested cadence
///

The [command-line map](command-line.md) inventories the public CLI that a
maintainer must keep consistent. The pages after it explain each repository
maintenance job in depth.
