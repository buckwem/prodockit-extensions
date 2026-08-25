---
icon: lucide/shield-check
---

{{ heading_counter_reset(page) }}

# Version pinning and drift {: #pinning-version-pinning-and-drift }

A documentation build has more inputs than its own source, which creates
\index{dependency drift} when declared or installed versions diverge. `zensical`
renders the site, `weasyprint` lays out the PDF, and both are ordinary
Python packages that resolve to whatever is newest unless you say
otherwise.

That matters more than it first appears, because the way an upgrade shows
up here is **not** a failed build. It is a published document that quietly
differs from the one you reviewed.

!!! example "What this looks like in practice"
    Zensical 0.0.52 bumped its bundled Font Awesome from 7.2.0 to 7.3.1,
    which redrew the GitHub brand icon. Every page of this project's own
    website changed. The PDF was byte-identical. Nothing failed, nothing
    was committed, and the site simply looked slightly different the next
    time it deployed.

    A `weasyprint` upgrade is sharper still: it decides pagination, so a
    release that lays out one paragraph differently shifts every page
    number after it - and those page numbers are *content*, resolved into
    the [back-of-book index](../extensions/index-terms.md) and the table of
    contents.

The \index{commands!`prodockit pins`} command supports two halves that only
work together:

1. **Pin the build inputs**, so output changes when someone decides it
   should.
2. **Watch for newer releases**, so pinning does not mean going quietly
   stale.

## Maintain a dependency safely

/// steps

//// step | Check that the repository agrees with itself

```bash
prodockit pins --check --offline
```

This does not contact PyPI. It answers the pull-request question: do the
version declarations already present in `pyproject.toml` and the workflows
agree? It is the form used by `ci.yml`, because a new upstream release should
not make an unrelated pull request fail.

////

//// step | Review drift information

The scheduled `drift.yml` workflow asks the separate maintenance question:
are newer releases available, and would they change the website or PDF? Read
the issue it opens or run the workflow manually before selecting versions.

For a quick inventory from a terminal:

```bash
prodockit pins
```

This contacts PyPI and offers the newest version, but it does not compare
rendered artifacts for you.

////

//// step | Move every declaration together

Set an reviewed version explicitly:

```bash
prodockit pins --set zensical=0.0.57
```

The tool preserves the role of each declaration: a library floor remains a
floor and a publishing workflow's exact pin remains exact.

////

//// step | Rebuild in publishing order

```bash
prodockit pdf
zensical build --clean --strict
pytest
```

Compare the website and PDF with the pinned baseline recorded by the drift
issue. Review pagination, generated indexes, diagrams, code blocks, and icons—not
only whether the commands returned zero.

////

//// step | Confirm consistency before committing

```bash
prodockit pins --check --offline
git diff --check
git status --short
```

The final offline check prevents a partial version bump from reaching the pull
request. The pull request then runs the same consistency gate in `ci.yml`.

////

///

## Where a version gets declared {: #pinning-where-declared }

Pinning creates its own problem: the same version ends up written in
several files at once, and nothing keeps them in step.

| File | Typically declares | Why that form |
| --- | --- | --- |
| `pyproject.toml` | `zensical>=0.0.57` | A **floor**. An exact pin in a library's metadata propagates to every consumer and conflicts with any project needing a different Zensical. |
| CI docs/build job | `zensical==0.0.57` | An **exact pin**. The site and PDF are artifacts; they should change deliberately. |
| CI test job | `weasyprint==69.0` | An **exact pin**. Tests that assert on where things land in a rendered PDF treat the layout engine as an input, not an implementation detail. |
| Drift job | both, exactly | The baseline it compares the newest release against. |

Both forms are correct in their own place. What is not correct is them
disagreeing, which is easy to do by hand and invisible when it happens.

## `prodockit pins` {: #pinning-prodockit-pins }

Reads every declaration across all of those files, shows what is
currently set against what is newest on PyPI, and moves them together.

```bash
prodockit pins
```

```text
zensical
  pyproject.toml:34  zensical>=0.0.53
  .github/workflows/docs.yml:164  zensical==0.0.53
  .github/workflows/drift.yml:69  zensical==0.0.53
  newest on PyPI: 0.0.53  <- newer available

weasyprint
  .github/workflows/ci.yml:59  weasyprint==69.0
  .github/workflows/docs.yml:164  weasyprint==69.0
  newest on PyPI: 69.0

markdown
  pyproject.toml:25  markdown>=3.10.3
  .github/workflows/docs.yml:164  markdown==3.10.3
  .github/workflows/drift.yml:69  markdown==3.10.3
  newest on PyPI: 3.10.3

pymdown-extensions
  .github/workflows/docs.yml:164  pymdown-extensions==11.0.2
  .github/workflows/drift.yml:69  pymdown-extensions==11.0.2
  newest on PyPI: 11.0.2

zensical: version to set [0.0.53]:
```

`Markdown` and `pymdown-extensions` are in that list even though nothing
installs them directly - they arrive under Zensical, which declares only
floors for them. See [the limitations below](#pinning-limitations) for why
pinning Zensical alone left them free to move.

Press ++enter++ to take the newest release, or type a version. Each site
keeps **its own operator** - the floor stays a floor, the pins stay
pinned - so one answer updates every file correctly.

### Options {: #pinning-options }

| Option | What it does |
| --- | --- |
| `-r`, `--root` | Project root to scan. Defaults to the current directory. |
| `-p`, `--package` | Package to manage, repeatable. Defaults to `zensical`, `weasyprint`, `prodockit`, `Markdown`, `pymdown-extensions` and `pandoc`. |
| `--set PACKAGE=VERSION` | Set a version without prompting, repeatable. Implies `--no-input`. |
| `--latest` | Take PyPI's newest for every package without prompting. Implies `--no-input`. |
| `--no-input` | Never prompt. Packages given a version are updated; the rest are reported and left untouched. |

## Keep shared files with the pinned release {: #pinning-shared-files }

Some documentation assets belong to the Prodockit release rather than to one
site. The full `extra.css` is one of them: extensions, template and user-guide
use identical CSS, then select site-specific behaviour through configuration
switches. Copying it by hand allowed one site to retain a duplicated older
rule without any build failing.

Prodockit therefore carries the canonical file in its wheel. A repository opts
in with `.prodockit-shared-files.toml`:

```toml
version = 1

[[files]]
source = "extra.css"
target = "docs/stylesheets/extra.css"
```

Check without writing:

```bash
prodockit shared-files --check
```

Restore a missing or different file, then review it:

```bash
prodockit shared-files --apply
git diff -- docs/stylesheets/extra.css
```

When the manifest is present, `prodockit pins --check --offline` performs the
same content check after checking version declarations. This makes the normal
CI gate protect the versions and the shared files supplied by that installed
version. It reads only the installed wheel and local project: no sibling
checkout, GitHub branch, checksum list or network request is involved.

Use `prodockit shared-files --verbose` when investigating a mismatch; it adds
the expected and actual SHA-256 values to the ordinary author-facing report.
| `--check` | Report and exit non-zero if anything is behind or inconsistent. Writes nothing. |
| `--offline` | Skip the PyPI lookup and only report what the files declare. |

`--set` is the unattended form, so it suppresses the prompt for **every**
package, not only the one it names:

```bash
prodockit pins --set zensical=0.0.53
```

```text
  pyproject.toml:34  zensical>=0.0.52 -> zensical>=0.0.53
  .github/workflows/docs.yml:136  zensical==0.0.52 -> zensical==0.0.53

Left untouched (no version given): weasyprint

Updated 2 declaration(s). Rebuild and diff before committing.
```

A package it was not given is reported and its files are not opened - name
it with its own `--set` to move it, or leave it where it is. That is what
makes the command safe in a script: it can neither hang on a prompt nor
half-finish because one appeared.

`--check` is the one to put in CI:

```bash
prodockit pins --check --offline
```

It fails when a package is behind PyPI **or** when the files disagree with
each other - the second being the failure that pinning across several
files invites.

!!! tip "Add `--offline` when it gates a pull request"

    Those two failures belong in different places. *Files disagreeing* is a
    property of the repository: a real mistake, introduced by a commit,
    fixable by its author. *Behind PyPI* is a property of the world, and
    turns every open pull request red the day upstream ships a release,
    with nothing in the branch having changed and nothing the author can do
    about it. A gate that fails for reasons outside the contributor's
    control is one people learn to ignore.

    `--offline` keeps the first check and drops the second, and needs no
    network. Leave "is there something newer" to a
    [drift job](#pinning-watching-for-drift), which reports on a schedule
    rather than failing a build. This project's own `ci.yml` runs the
    offline form for exactly this reason.

### What it scans {: #pinning-what-it-scans }

Both CI hosts, so the same command works either way:

- `pyproject.toml`, `setup.cfg`
- `.github/workflows/*.yml` — GitHub Actions
- `.gitlab-ci.yml` and `.gitlab/**/*.yml` — GitLab CI
- `requirements*.txt`, `constraints*.txt` at the project root

Build output and virtualenvs (`site/`, `public/`, `.venv/`,
`node_modules/`, …) are skipped, so a stale copy of a workflow inside one
is not mistaken for a declaration.

Four shapes of declaration are recognised, because a build input is not
always a pip package:

| Shape | Example | Where |
| --- | --- | --- |
| pip specifier | `zensical==0.0.52`, `zensical>=0.0.52` | anywhere |
| runner label | `runs-on: ubuntu-24.04` | GitHub Actions |
| image tag | `image: python:3.13` | GitLab CI, or any container |
| CI variable | `PANDOC_VERSION: "3.10.1"` | a GitHub `env:` block, a GitLab `variables:` block |

!!! info "Why prodockit is managed by default"
    It was not, for a long time, and the omission had exactly the
    consequence the managed set exists to prevent. `prodockit-template`
    pinned `prodockit==0.35.0` and drifted two releases behind with
    nothing noticing, because the one command that looks at pins was not
    looking at this one - moving it needed `-p prodockit` typed by hand,
    which is the step nobody remembers
    ([prodockit-template#173](https://github.com/buckwem/prodockit-template/issues/173)).

    It belongs there on the merits too: prodockit renders the PDF and
    generates the back-of-book index, so its version changes a project's
    published output as directly as Zensical's does.

    Including it is safe even in prodockit's own repository, where the
    name appears in `pyproject.toml` as the project's identity rather
    than as a dependency. The specifier pattern requires a version
    operator after the name, so `name = "prodockit"` and the adjacent
    `version = "..."` are not declarations - without that, the command
    would offer to rewrite the release number of the package being built.

!!! info "Why pandoc is managed by default"
    Pandoc is not a Python package, so it never appears as a pip specifier
    - it is a build-provided binary, pinned as a `<PACKAGE>_VERSION`
    variable the way `prodockit pdf`'s publishing workflow does. It earns a
    place in the default set for the same reason Zensical
    and WeasyPrint do: pandoc is not always compatible with itself across
    releases, and one of its changes broke every fenced code block in this
    project's own PDF while the build kept reporting success.

    The CI variable's name keeps its case on rewrite - `PANDOC_VERSION`,
    not `pandoc_VERSION` - since a workflow step reading
    `{% raw %}${{ env.PANDOC_VERSION }}{% endraw %}` needs the name unchanged,
    only the value.

### Pandoc version drift {: #pinning-pandoc-version-drift }

Distribution Pandoc packages can lag several major versions behind upstream.
Ubuntu 24.04, for example, supplies an older release than the one this
repository currently tests and publishes with. Installing the distribution
package locally while CI downloads a current release means the two builds can
parse identical HTML differently.

That happened here when one Pandoc release accepted highlighted
`<pre><code>` content that a newer release interpreted differently. Every
fenced code block reflowed as ordinary justified prose in one environment,
while the other environment continued publishing a correct PDF. Both builds
reported success.

Pin Pandoc as a `PANDOC_VERSION` workflow variable and move it through
`prodockit pins`, then compare complete PDF and website artifacts before and
after the change. Pinning does not prevent incompatibility; it makes the
change arrive in a reviewed commit instead of with an unannounced runner
update.

!!! note "Only versioned declarations are found"
    A dependency installed with no version at all is not a declaration
    site, so it will not appear - pin it once by hand and the tool manages
    it from then on. The same applies to `runs-on: ubuntu-latest`, which
    names no version to move.

## Watching for drift {: #pinning-watching-for-drift }

Pinning trades one risk for another: nothing tells you a newer release
exists, or what it would do to your output.

The check worth running is not "is there a new version" - PyPI can answer
that - but **"would taking it change what we publish?"** That needs a real
build, twice.

The shape is the same on either host:

1. Build the docs with the pinned versions. Keep the result.
2. Upgrade to the newest and build again.
3. Diff the two, byte for byte.
4. Run your built-output checks against the *newer* build.
5. Report - do not fail.

Both builds run in the same job, so pandoc, Chrome, fonts and the runner
image are identical between them and any difference is attributable to the
upgraded packages alone.

!!! warning "Two things make or break this"
    **Build order.** `zensical build` copies the PDF into the site
    directory, so it must run *after* `prodockit pdf`. Reversed, the
    copied PDF lags a generation and every comparison is a false positive
    that looks exactly like nondeterminism.

    **Determinism.** The diff only means something if identical inputs
    give identical output. Verify that first - two builds of the same
    version should produce a byte-identical site and PDF. They do for this
    project; confirm it for yours before trusting a diff.

### Reporting, not failing {: #pinning-reporting-not-failing }

A newer release is information, not a broken build. A scheduled job that
goes red every week trains everyone to ignore it, so open an issue
instead - and keep **one** open at a time, updating it in place rather
than filing a fresh one every Monday until somebody acts.

### GitHub Actions {: #pinning-github-actions }

This project ships [`drift.yml`](https://github.com/buckwem/prodockit-extensions/blob/main/.github/workflows/drift.yml)
doing exactly this. The essentials:

```yaml
name: Dependency drift
on:
  schedule:
    - cron: "0 6 * * 1"   # Mondays, 06:00 UTC
  workflow_dispatch:
permissions:
  contents: read
  issues: write           # needed to open the issue
jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      # ... same build tooling as your docs job ...
      - name: Build with the pinned versions
        run: |
          pip install -e ".[testing]" "zensical==0.0.57" "weasyprint==69.0" "Markdown==3.10.3" "pymdown-extensions==11.0.2"
          prodockit pdf                      # PDF first ...
          zensical build --clean --strict    # ... then the site
          cp -R site /tmp/pinned-site
          cp docs/site_documentation.pdf /tmp/pinned.pdf

      - name: Build with the newest versions
        run: |
          pip install -qU zensical weasyprint
          prodockit pdf
          zensical build --clean --strict

      - name: Compare
        env:
          GH_TOKEN: {% raw %}${{ github.token }}{% endraw %}
        run: |
          cmp -s /tmp/pinned.pdf docs/site_documentation.pdf \
            && echo "PDF identical" || echo "PDF differs"
          diff -rq /tmp/pinned-site site | wc -l
          # ... then gh issue create / gh issue comment
```

### GitLab CI {: #pinning-gitlab-ci }

The same job, with GitLab's own scheduling and API. Add a
[pipeline schedule](https://docs.gitlab.com/ee/ci/pipelines/schedules.html)
running weekly, and a project access token with the `api` scope exposed as
`DRIFT_TOKEN` so the job can open an issue.

```yaml
drift:
  image: python:3.13
  rules:
    # Only on the schedule - never on a normal push pipeline.
    - if: $CI_PIPELINE_SOURCE == "schedule"
  before_script:
    - apt-get update && apt-get install -y pandoc libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 jq curl
  script:
    - pip install -e ".[testing]" "zensical==0.0.57" "weasyprint==69.0" "Markdown==3.10.3" "pymdown-extensions==11.0.2"
    - prodockit pdf                     # PDF first ...
    - zensical build --clean --strict   # ... then the site
    - cp -R site /tmp/pinned-site && cp docs/site_documentation.pdf /tmp/pinned.pdf
    - pip install -qU zensical weasyprint
    - PINNED=$(pip show zensical | awk '/^Version:/{print $2}')
    - prodockit pdf
    - zensical build --clean --strict
    - LATEST=$(pip show zensical | awk '/^Version:/{print $2}')
    - |
      if [ "$PINNED" = "$LATEST" ]; then
        echo "Pins are current."; exit 0
      fi
      CHANGED=$(diff -rq /tmp/pinned-site site | wc -l)
      cmp -s /tmp/pinned.pdf docs/site_documentation.pdf && PDF=identical || PDF=differs
      # One open issue at a time.
      EXISTING=$(curl -sf --header "PRIVATE-TOKEN: $DRIFT_TOKEN" \
        "$CI_API_V4_URL/projects/$CI_PROJECT_ID/issues?state=opened&search=Dependency+drift" \
        | jq -r '.[0].iid // empty')
      BODY="zensical $PINNED -> $LATEST. PDF: $PDF. Website: $CHANGED files differ."
      if [ -n "$EXISTING" ]; then
        curl -sf --request POST --header "PRIVATE-TOKEN: $DRIFT_TOKEN" \
          --data-urlencode "body=$BODY" \
          "$CI_API_V4_URL/projects/$CI_PROJECT_ID/issues/$EXISTING/notes" > /dev/null
      else
        curl -sf --request POST --header "PRIVATE-TOKEN: $DRIFT_TOKEN" \
          --data-urlencode "title=Dependency drift: newer build inputs than the docs pins" \
          --data-urlencode "description=$BODY" \
          "$CI_API_V4_URL/projects/$CI_PROJECT_ID/issues" > /dev/null
      fi
  allow_failure: true
```

`allow_failure: true` keeps the pipeline green: the job's purpose is the
issue it opens, not its own exit status.

## The input pip cannot reach {: #pinning-runner-image }

`prodockit pins` manages Python packages. The CI runner image is the other
half, and nothing in `pyproject.toml` or a workflow's `pip install` line
touches it:

- **`pandoc`** comes from the image's own package archive. Distribution
  packages lag upstream far enough that some Markdown edge cases parse
  differently—see [Pandoc version drift](#pinning-pandoc-version-drift).
- **Fonts** the PDF embeds (`fonts-inter`, `fonts-jetbrains-mono`).
- **Chrome**, which rasterises Mermaid diagrams.

On `runs-on: ubuntu-latest` all three move the day the label migrates to a
new LTS, with nothing committed - the same silent change the package pins
exist to prevent, one layer down. Naming the image freezes them together:

```yaml
jobs:
  deploy:
    runs-on: ubuntu-24.04   # not ubuntu-latest
```

GitLab's equivalent is the job `image:`, which most projects already pin by
habit - `python:3.13` rather than `python:latest`.

`prodockit pins` manages both, so the image is inventoried and moved the
same way as everything else - name it with `-p`:

```bash
prodockit pins -p ubuntu       # runs-on: ubuntu-24.04, across every workflow
prodockit pins -p python       # image: python:3.13, in GitLab CI
```

```text
ubuntu
  .github/workflows/ci.yml:11  ubuntu-24.04
  .github/workflows/docs.yml:69  ubuntu-24.04
  .github/workflows/drift.yml:36  ubuntu-24.04
  .github/workflows/publish.yml:10  ubuntu-24.04
  not on PyPI - set the version yourself

ubuntu: version to set [24.04]:
```

There is no suggested version for these: PyPI has nothing to say about a
runner image, and asking it for "ubuntu" would at best miss and at worst
find an unrelated package of that name and propose a nonsense upgrade. The
default is what is currently set, so ++enter++ is a no-op and you type the
new one deliberately - which suits a change you make once every couple of
years.

`--check` still applies, and catches the failure that matters here: some
jobs left on the old image after a partial migration.

!!! note "What this costs"
    `ubuntu-latest` already *is* 24.04 today, so pinning changes nothing
    immediately. It takes effect at the migration - which is the point.

    Pinned images are retired roughly a year after the following LTS, and
    the job then fails outright rather than drifting. That is the better
    failure: loud, and at a time you choose. Treat a retirement notice as
    the prompt to rebuild, diff, and move up deliberately.

## Taking an upgrade {: #pinning-taking-an-upgrade }

When drift reports something worth having, use the complete maintenance flow
above. The short command sequence is:

```bash
prodockit pins --set zensical=0.0.57
prodockit pdf
zensical build --clean --strict
pytest
prodockit pins --check --offline
```

Substitute the package and reviewed version reported by drift. Then diff the
built output against the previous version before committing. That is the step
the whole arrangement exists to make possible: seeing what an upgrade does to
your document *before* your readers do.

## Limitations and workarounds {: #pinning-limitations }

See [Implementation limitations](limitations.md) for the general list.
Specific to pinning:

- **A floor still floats.** `zensical>=0.0.57` in `pyproject.toml` records
  a version; it does not control one. Only the exact pin in the build job
  does. Both exist deliberately - see the table above.
- **A pinned package's own dependencies float too**, which is the sharper
  version of the same trap: pinning a direct dependency exactly does
  nothing for the transitive ones underneath it, because *their* versions
  come from floors in *its* metadata. Zensical is pinned exactly here, and
  still declares only floors for `Markdown` and `pymdown-extensions` - the
  two packages that actually turn every page into HTML. A build pinning
  Zensical alone therefore rendered with whatever those two resolved to on
  the morning it ran. Both are now pinned alongside it, and both are
  managed by `prodockit pins`
  ([#178](https://github.com/buckwem/prodockit-extensions/issues/178)).
  If your project pins something whose rendering you depend on, check what
  it pulls in: `pip show <package>` lists its requirements, and a floor
  there is a version you are not controlling.
- **Only pip packages are watched.** `pandoc` and Chrome arrive from the
  runner image, so a drift job that installs both builds in one job cannot
  see them change between weeks. Pinning the image is the lever for those -
  see below.
- **Comments are not scanned.** A version specifier written in prose -
  explaining why something is pinned, say - is deliberately not treated as
  a declaration, so it is neither reported nor rewritten by `--set`. Only
  the part of a line before a `#` is read
  ([#184](https://github.com/buckwem/prodockit-extensions/issues/184)); a
  trailing comment after a real declaration still leaves that declaration
  findable.
- **`prodockit pins` needs network** for `--latest` and the suggested
  default. Use `--offline` to report what the files declare without asking
  PyPI.
