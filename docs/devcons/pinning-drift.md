# Version pinning and drift {: #pinning-version-pinning-and-drift }

A documentation build has more inputs than its own source. `zensical`
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

The answer is two halves that only work together:

1. **Pin the build inputs**, so output changes when someone decides it
   should.
2. **Watch for newer releases**, so pinning does not mean going quietly
   stale.

## Where a version gets declared {: #pinning-where-declared }

Pinning creates its own problem: the same version ends up written in
several files at once, and nothing keeps them in step.

| File | Typically declares | Why that form |
| --- | --- | --- |
| `pyproject.toml` | `zensical>=0.0.53` | A **floor**. An exact pin in a library's metadata propagates to every consumer and conflicts with any project needing a different Zensical. |
| CI docs/build job | `zensical==0.0.53` | An **exact pin**. The site and PDF are artifacts; they should change deliberately. |
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
  .github/workflows/docs.yml:164  pymdown-extensions==11.0.1
  .github/workflows/drift.yml:69  pymdown-extensions==11.0.1
  newest on PyPI: 11.0.1

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
| `-p`, `--package` | Package to manage, repeatable. Defaults to `zensical`, `weasyprint`, `Markdown` and `pymdown-extensions`. |
| `--set PACKAGE=VERSION` | Set a version without prompting, repeatable. Implies `--no-input`. |
| `--latest` | Take PyPI's newest for every package without prompting. Implies `--no-input`. |
| `--no-input` | Never prompt. Packages given a version are updated; the rest are reported and left untouched. |
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
prodockit pins --check
```

It fails when a package is behind PyPI **or** when the files disagree with
each other - the second being the failure that pinning across several
files invites.

### What it scans {: #pinning-what-it-scans }

Both CI hosts, so the same command works either way:

- `pyproject.toml`, `setup.cfg`
- `.github/workflows/*.yml` — GitHub Actions
- `.gitlab-ci.yml` and `.gitlab/**/*.yml` — GitLab CI
- `requirements*.txt`, `constraints*.txt` at the project root

Build output and virtualenvs (`site/`, `public/`, `.venv/`,
`node_modules/`, …) are skipped, so a stale copy of a workflow inside one
is not mistaken for a declaration.

Three shapes of declaration are recognised, because a build input is not
always a pip package:

| Shape | Example | Where |
| --- | --- | --- |
| pip specifier | `zensical==0.0.52`, `zensical>=0.0.52` | anywhere |
| runner label | `runs-on: ubuntu-24.04` | GitHub Actions |
| image tag | `image: python:3.13` | GitLab CI, or any container |

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
          pip install -e ".[testing]" "zensical==0.0.53" "weasyprint==69.0" "Markdown==3.10.3" "pymdown-extensions==11.0.1"
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
          GH_TOKEN: ${{ github.token }}
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
    - pip install -e ".[testing]" "zensical==0.0.53" "weasyprint==69.0" "Markdown==3.10.3" "pymdown-extensions==11.0.1"
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
  packages lag upstream far enough that some markdown edge cases parse
  differently - see [Pandoc version drift](continuous-integration.md#ci-pandoc-version).
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

When drift reports something worth having:

```bash
prodockit pins            # accept the suggested version, or type one
prodockit pdf             # rebuild - PDF first ...
zensical build --clean    # ... then the site
```

Then diff the built output against the previous version before committing.
That is the step the whole arrangement exists to make possible: seeing what
an upgrade does to your document *before* your readers do.

## Limitations and workarounds {: #pinning-limitations }

See [Limitations and workarounds](limitations.md) for the general list.
Specific to pinning:

- **A floor still floats.** `zensical>=0.0.53` in `pyproject.toml` records
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
- **`prodockit pins` needs network** for `--latest` and the suggested
  default. Use `--offline` to report what the files declare without asking
  PyPI.
