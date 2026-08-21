---
icon: lucide/refresh-cw
---

# Staying in step with the template {: #tsync-staying-in-step }

A project generated from `prodockit-template` is a copy, not a link. The
moment it is created it starts to age: the template gains a CI fix, a
stylesheet rule, a newer Node pin, and the copy keeps the version it was
born with. Nothing tells you, because nothing breaks - the site still
builds, the PDF still renders, and the difference only shows up as a
document that looks slightly unlike everyone else's.

The \index{commands!`prodockit template-sync`} command closes that gap without touching a word of your
writing.

Use it periodically while a project is active and before a final release. A
long gap is supported, but it produces a larger change that is harder to
review and more likely to combine a CI migration with a visual change.

## Choose how far the command should go

| Command | Stops after | Use it for |
|---|---|---|
| `prodockit template-sync` | A report | Routine checking and learning what changed upstream |
| `prodockit template-sync --apply` | A new branch with changes staged | The normal reviewed pull-request workflow |
| `prodockit template-sync --apply --push` | Confirmed commit, merge to the host's default branch, and push | A project where you may merge your own maintenance directly |
| `prodockit template-sync --apply --force PATH` | Staged update including the named edited file | A deliberate decision to replace your local version with the template's |

Protected repositories should normally use `--apply`, inspect the branch, and
open a pull request. `--push` is not a bypass for branch protection; it is an
assisted path for repositories whose maintainer is allowed to merge directly.

## Complete a template update

/// steps

//// step | Start clean and preview

```bash
git status --short
prodockit template-sync
```

Uncommitted chapters are allowed, but uncommitted changes to template-owned
files stop the run before it writes. Read the classification counts and any
files reported as locally edited.

////

//// step | Apply on the generated branch

```bash
prodockit template-sync --apply
```

The command creates or safely resumes `template-update-...`, writes only the
permitted files, and stages them. It does not commit.

////

//// step | Resolve kept files and sidecars

For an edited template-owned file, compare the current file with its `.new`
sidecar. Merge the useful upstream change by hand, or rerun with one explicit
`--force PATH` if the template's complete version should win. Delete resolved
sidecars so they cannot be mistaken for unfinished work.

////

//// step | Build the complete outputs

```bash
prodockit pdf
zensical build --clean --strict
```

Run the project's tests as well. A template update commonly changes workflows,
stylesheets, Node tooling, or pins; a source diff alone cannot show whether the
published PDF and site still look right.

////

//// step | Commit and publish through the normal gate

```bash
git diff --cached
git commit -m "Update from prodockit template"
git push -u origin HEAD
gh pr create
```

Merge after CI passes. If the repository deliberately permits the automated
finish, use `prodockit template-sync --apply --push` instead and confirm the
printed commit, merge, and push plan.

////

//// step | Confirm the next run is clean

After merging or pushing the updated default branch:

```bash
prodockit template-sync
```

“Already in step with the template” is the verification. A remaining report
usually means an unresolved sidecar, an intentionally kept file, or a baseline
that was not advanced by the expected branch.

////

///

## What it will and will not write {: #tsync-what-it-writes }

The split is decided by a **manifest** that lives in the template, not by
the command, and every file the template ships is classified in it. A file
that is in neither list stops the run rather than being guessed at.

| Group | Examples | What happens |
| --- | --- | --- |
| Template-owned | `.github/workflows/`, `docs/stylesheets/extra.css`, `macros.py`, `tools/` | Replaced, unless you have edited it |
| Project-owned | `docs/*.md`, `bibliography.bib`, `docs/assets/` | Never written, never read |
| Seeds | `.vale.ini`, starter pages | Written only if absent |
| Shared | `.gitignore`, `zensical.toml` | Merged line by line, never replaced |
| Excluded | `CONTRIBUTING.md`, issue templates | Not delivered at all |

Within the shared `zensical.toml`, an existing `project.extra.pdf_*` value is
author-owned. Template sync adds a PDF parameter introduced by a newer
template when the project does not have it, but never overwrites an existing
page size, margin, duplex-layout, header/footer, stylesheet, output-path, or
future PDF setting. Those values describe the document the author intends to
publish; restoring defaults such as A4 paper and 2 cm margins would be a
content-changing operation, not maintenance.

!!! warning "Your writing is not in scope"
    The report, its figures and its bibliography are never written, and
    never even read for comparison. A sync cannot lose your work because
    it never opens it.

## Running it {: #tsync-running-it }

Run it from the root of the project - the same directory as `.git`. It
refuses anywhere else rather than half-working, because every path it
writes is relative to where it started.

```bash
prodockit template-sync
```

That reports and writes no project file. Read the report, then:

```bash
prodockit template-sync --apply
```

`--apply` starts a branch of its own, writes, and **stages without
committing**. The commit is yours to write, so nothing lands in your
history that you have not read first.

### The branch it works on {: #tsync-the-branch }

The branch is named after the template version you are moving from, so a
second run against the same version continues on the branch the first one
made rather than starting again.

That name outlives the run, though, and a branch left over from months ago
will not contain anything you have committed since. Continuing on it would
sync your project against older files and report success, so a leftover
branch that does not contain the commit you are on is refused:

```text
Error: the branch template-update-6fbbbbeb8 already exists and does not
contain the commit you are on, so continuing would run this against older
work. Merge it, or delete it with `git branch -D template-update-6fbbbbeb8`,
and run this again
```

You are left on the branch you were already on, with nothing written.

A follow-up run can also make a *second* branch, and that surprises
people. The name comes from the baseline you are moving from, so once a
run has recorded a stamp, the next one is moving from a different place
and branches accordingly - a `--force` run straight after an ordinary one
lands on `template-update-<new baseline>` rather than back on the first
branch.

Nothing is lost or duplicated: the second branch is made *from* the first,
so it contains it, and one merge picks up both. Merging them separately
just makes the first look like it did nothing.

### Finishing where the pipeline can see it {: #tsync-push }

`--apply` stops at staged, on its own branch. That is deliberate - the
commit is yours - but it also means **nothing is published**. Both hosts
build only from the default branch, so a sync sitting on a
`template-update-...` branch produces no pipeline and no rebuilt site,
even after you commit and push it. The steps are spelled out
[below](#tsync-finish-by-hand) if you would rather not use this flag.

`--push` finishes the job:

```bash
prodockit template-sync --apply --push
```

It commits the staged sync, merges it into the branch your host builds
from, and pushes - which is what starts the pipeline. It always shows
what it is about to do and waits:

```text
--push would now, on your confirmation:
  commit  9 file(s) on template-update-6fbbbbeb8
  merge   template-update-6fbbbbeb8 into main
  push    main to origin - which is what starts the pipeline

Go ahead? [y/N]:
```

Answer anything but yes and the run stops with everything still staged
and nothing merged or pushed.

!!! note "Uncommitted writing is fine"
    You do not have to commit your chapters first. A project being
    written always has work in progress, and it travels across the branch
    switch untouched. Only uncommitted changes to *template-owned* files
    stop a run, and those are refused earlier, before anything is written.

Which branch it merges into comes from the remote itself, not from your
local `origin/HEAD` - that is a cache written when you cloned, and it goes
stale. A merge into the branch the sync was written on is refused
outright.

#### Or finish it by hand {: #tsync-finish-by-hand }

If you would rather do it yourself, the steps are the ones `--push`
performs — and the middle one is the one people miss:

```bash
git commit -m "Sync with the template"
```

```bash
git checkout main && git merge --no-ff template-update-6fbbbbeb8
```

```bash
git push
```

**Committing alone does nothing**, and neither does pushing the update
branch. A commit is local, so the host never sees it - and neither host
builds from a branch like this one. GitLab's `pages` job is guarded by
`if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'`; GitHub's docs workflow
lists `branches: [master, main]`. Different mechanisms, same answer: a
pushed `template-update-...` branch produces no pipeline at all.

It is the merge into the default branch, and the push of *that*, which
rebuilds the site. A run that appears to have had no effect has almost
always stopped at one of those two steps.

!!! warning "This merges straight into your default branch"
    `--push` assumes you merge your own work directly - no merge request,
    no review, no approval step. That is the assumption this is built on,
    and it matches how a student works on their own report.

    If your project *does* gate the default branch behind merge requests,
    do not use `--push`: it would either bypass that gate or be rejected
    by a protected branch. Use `--apply` on its own and open a merge
    request from the `template-update-...` branch instead.

### A file you have edited {: #tsync-edited-files }

A template-owned file you have changed is *kept*, and the template's
version is written beside it as `<name>.new` for you to compare. Nothing
is overwritten silently.

**"Edited" does not always mean you changed it.** A file counts as edited
when it does not match the baseline the run settled on - which is equally
true of a file you customised and one you simply never received an update
for. The tool cannot tell those apart, and you usually can, at a glance:

```bash
diff .gitlab-ci.yml .gitlab-ci.yml.new
```

If the differences are all yours - your module code, your group, your
wording - keep what you have. If they are all *the template's own
history* - newer pins, a step you have never seen, a comment referring to
an issue you did not raise - then you are simply behind, and taking the
template's version is right.

!!! example "What that looks like in practice"
    Syncing a real assignment repository, both files reported as edited
    turned out to contain nothing project-specific whatsoever. One was a
    `.gitlab-ci.yml` still pinning `prodockit==0.21.0` against the
    template's `0.39.0`, missing a `prodockit init-mathjax` step added
    months earlier - so every page that pipeline had built showed raw TeX
    instead of maths. Neither file had been edited at all; both had just
    never been updated.

#### Taking the template's version {: #tsync-force }

```bash
prodockit template-sync --apply --force .gitlab-ci.yml --force .github/workflows/docs.yml
```

Three things to know about `--force`:

- **Exact paths, one flag each.** No globs, and no bare `--force` meaning
  "everything". That friction is the point: this is the only option that
  can overwrite your own work, so each file is named deliberately.
- **Paths are as the report prints them**, relative to the project root. A
  leading `./` is tolerated; anything else will not match.
- **A `--force` that matches nothing is ignored**, not warned about. So
  the check is the report itself - it should say `forced 2` where it
  previously said `keep 2`.

#### Then delete the sidecars {: #tsync-sidecars }

Once you have taken the template's version, the `.new` file beside it is
byte-identical to the real one and has no further use. **The tool will not
remove it** - it never deletes anything from your project - so it lingers,
and gets committed:

```bash
git rm .gitlab-ci.yml.new .github/workflows/docs.yml.new
```

If you decided to keep *your* version instead, delete the sidecar just the
same once you have read it. Leaving it behind means the next reader cannot
tell whether it is a decision you made or one you have not got to yet.

### Where the template comes from {: #tsync-template-source }

By default it follows your `origin`: a project on Surrey's GitLab tracks
the Surrey mirror, because a student there may have no GitHub access at
all. Everything else tracks the canonical GitHub copy. Override it with
`--github` or `--surrey`, bare for that host's usual template or with a
`group/repo` to name another.

You do not need a copy of the template yourself. The first run clones it
into a cache - `~/Library/Caches/prodockit` on macOS, `~/.cache/prodockit`
on Linux, `%LOCALAPPDATA%\prodockit\cache` on Windows, or wherever
`PRODOCKIT_CACHE` points - and later runs bring that copy up to date. Each
host and namespace gets its own entry, so the Surrey and GitHub templates
never stand in for one another.

The line under the remote says which of three things happened:

| | |
| --- | --- |
| `fetched just now` | first run - the template was cloned |
| `fetched, up to date` | the cached copy was brought current |
| `cached copy - could not reach the host…` | the host was unreachable; the run continued on what was already cached |

The third is a real answer, not a failure. A run on a train still shows
you what your project would do - it just says plainly that the template
it compared against may be behind.

!!! note "A checkout beside your project wins"
    If a `prodockit-template` checkout sits next to the project, that is
    used instead of the cache. This is how the repositories are laid out
    during development, so a maintainer working across them gets the copy
    they are editing. `--template-path` names one outright.

## Running it through a project {: #tsync-repeatedly }

This is meant to be run repeatedly - every few weeks through a report's
development, not once at the start. Most of those runs find nothing, and
that case is the one built for.

A run with nothing to do says so and stops:

```text
Already in step with the template - nothing to write.
```

No branch, no staged change, nothing to commit. That matters more than it
sounds: a run that branched regardless left an empty branch behind, and
the branch name comes from the template version, so the *next* run found
it in the way.

When the template has moved on, the run branches, writes and stages as
usual. A file you have edited keeps its `.new` sidecar from the previous
run rather than being rewritten with identical bytes, so `git status` only
ever shows what genuinely changed.

!!! note "Simulated over six weeks"
    Six syncs across two template versions, with writing committed
    between each: two produced real updates and branched, four reported
    "already in step" and left the working tree clean. Two `.new`
    sidecars at the end - one per edited file, not one per run - all six
    chapters intact, and the recorded baseline moved forward with the
    template.

A template release that only reclassifies files leaves every file
identical, so nothing is written - but the recorded baseline still moves
forward, because leaving it stale would make the next run compare against
the wrong version and report unedited files as edited.

### After a long gap {: #tsync-long-gap }

A project that has not synced for months takes every upstream release at
once. That is the point, but it is worth knowing before you look at the
result: in one real catch-up the CI pin moved from `prodockit==0.21.0` to
`0.39.0` and `zensical==0.0.53` to `0.0.55` in a single commit - eighteen
prodockit releases and two Zensical ones.

So after a large catch-up, **look at the built output**, not just at the
diff. If something in the site or the PDF renders differently, the
upstream jump is a far more likely cause than the sync itself, and
[version pinning and drift](pinning-drift.md) is the page that covers
comparing before and after.

## The log {: #tsync-the-log }

Every run - reporting or applying, succeeding or failing - appends a full
account of itself to `.prodockit-template.log`, and adds that file to
`.gitignore` if it is not already there.

```text
=== 2026-08-19T14:37:35+01:00  started  prodockit template-sync
template  git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git

  template      15 files  (replace where unedited)
      .github/workflows/docs.yml
      ...
=== 2026-08-19T14:37:39+01:00  finished
```

Two things about it are deliberate:

- **It always holds the `--verbose` form**, listing every file, whatever
  the terminal was asked for. The run someone reports a problem with is
  almost always the one they ran with no flags at all.
- **It is written even when the run fails.** A run that stopped partway is
  the one most worth reading afterwards.

!!! tip "Reporting a problem"
    Send `.prodockit-template.log`. It carries the command line, both
    timestamps and the full classification, which is most of what anyone
    would otherwise have to ask you for.

Entries are appended, never overwritten, so the log is a history rather
than a snapshot. Delete it whenever you like; the next run starts a new
one.
