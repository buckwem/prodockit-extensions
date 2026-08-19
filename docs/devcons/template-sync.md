# Staying in step with the template {: #tsync-staying-in-step }

A project generated from `prodockit-template` is a copy, not a link. The
moment it is created it starts to age: the template gains a CI fix, a
stylesheet rule, a newer Node pin, and the copy keeps the version it was
born with. Nothing tells you, because nothing breaks - the site still
builds, the PDF still renders, and the difference only shows up as a
document that looks slightly unlike everyone else's.

`prodockit template-sync` closes that gap without touching a word of your
writing.

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

### Finishing where the pipeline can see it {: #tsync-push }

`--apply` stops at staged, on its own branch. That is deliberate - the
commit is yours - but it also means **nothing is published**. Both hosts
build only from the default branch, so a sync sitting on a
`template-update-...` branch produces no pipeline and no rebuilt site,
even after you commit and push it.

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

If you want the template's version after all, name the file:

```bash
prodockit template-sync --apply --force .gitlab-ci.yml
```

`--force` reaches only files the report lists as kept. Anything else is
unaffected, however you spell it.

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
