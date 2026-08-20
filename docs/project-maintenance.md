---
icon: lucide/wrench
---

# Project maintenance

A documentation project needs occasional maintenance after its first
successful publish. Repository links change, build tools release new versions,
the source template improves, and a release must be built from exactly the
change that was reviewed.

This section turns those separate jobs into one repeatable cycle. Start here
when you inherit a project, return to it before a release, and use the detailed
pages when a check reports work to do.

## The maintenance cycle

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

//// step | Compare with the project template

Projects created from `prodockit-template` are copies, so they do not receive
later CI, stylesheet, or tooling fixes automatically. Preview the difference:

```bash
prodockit template-sync
```

Apply only after reading the report. The command creates its own branch and
stages rather than commits by default. See
[Staying in step with the template](devcons/template-sync.md).

////

//// step | Build the deliverables locally

Build in the same order as GitHub Actions. The PDF comes first because
`zensical build` copies it into the published site:

```bash
prodockit pdf
zensical build --clean --strict
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

| Need | Start with | What changes |
|---|---|---|
| A fork, mirror, or renamed repository points at the wrong place | `prodockit sync-repo --check` | Repository URLs, edit links, host icon, and managed README badges |
| CI files disagree about dependency versions | `prodockit pins --check --offline` | Version declarations, preserving each file's existing operator |
| A newer dependency may change published output | GitHub's `drift.yml` result | Nothing automatically; it opens or updates an issue with the comparison |
| A generated project is behind its template | `prodockit template-sync` | Template-owned files and selected shared configuration, on a branch |
| A machine cannot build or publish yet | `prodockit bootstrap` | Tooling and project setup; see [Set up a machine](devcons/bootstrap.md) under Publishing |
| A prodockit release is ready | The release checklist | Package version, release notes, GitHub release, PyPI package, and rebuilt documentation |

## What automation does—and does not—prove

The workflows deliberately divide responsibility:

| Workflow | Trigger | Answer |
|---|---|---|
| `ci.yml` | Pull requests and pushes to `main` | Does the code work across supported Python versions, and do the docs build strictly? |
| `docs.yml` | Pushes to `main` and manual dispatch | Can the complete website and PDF be built, tested, deployed, and verified live? |
| `drift.yml` | Weekly schedule and manual dispatch | Would newer rendering dependencies change the published artifacts? |
| `publish.yml` | Published GitHub release | Can the tagged source build and publish to PyPI through Trusted Publishing? |
| `release-redeploy.yml` | Published GitHub release | Can `docs.yml` be rerun against `main` so the site sees the new tag? |

A green workflow proves the question in its own row, not every row. In
particular, a passing pull request does not publish PyPI, and a successful
Pages deployment does not by itself prove the public URL serves the new bytes.
The deployment workflow performs that final delivery check separately.

## Suggested cadence

| When | Maintenance |
|---|---|
| Every pull request | Repository and pin consistency, tests, lint, typing, strict docs build |
| Weekly | Let `drift.yml` compare pinned and newest renderers; triage the issue it opens |
| After moving or forking a repository | Run `sync-repo`, rebuild, and inspect canonical/edit links and badges |
| Every few weeks in a template-derived project | Preview `template-sync`; apply and review when upstream moved |
| Before a package release | Complete the local build gates, merge the release PR, publish a GitHub release, verify PyPI and Pages |

The [command-line map](command-line.md) gives the safe default and write
behaviour for every command. The pages after it explain each maintenance job
in depth.
