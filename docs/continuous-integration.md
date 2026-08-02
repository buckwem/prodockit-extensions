# Continuous integration {: #ci-continuous-integration }

Building a prodockit site in \index{continuous integration!CI} needs more than `pip install`. The PDF
pipeline shells out to external binaries, and several of the ways it goes
wrong are silent - the build succeeds and publishes something subtly wrong.

This page is the recipe, the reasoning behind each part of it, and the two
further checks - keeping repository metadata in step with your git remote,
and keeping build inputs pinned and watched for drift - that close the
remaining gaps.

## What the build actually needs {: #ci-what-the-build-needs }

| Requirement | Needed for | Silent if missing? |
| --- | --- | --- |
| `pandoc` | `prodockit pdf`, and `prodockit.bibliography` even without a PDF | No - the build fails |
| `weasyprint` | `prodockit pdf` | No - the build fails |
| Your document fonts | Embedding them in the PDF | **Yes** - WeasyPrint substitutes a generic font |
| `mermaid-cli` + Chrome | Mermaid diagrams in the PDF | **Warned** since 0.12.0, but the build still succeeds |
| `mathjax-full` | TeX maths in the PDF | **Warned** since 0.12.0, but the build still succeeds |
| Full git history | The `{{ release }}` cover line | **Yes** - the line just doesn't appear |

The three marked rows are where every mistake has actually happened.

## GitHub Actions {: #ci-github-actions }

```yaml
name: Documentation
on:
  push:
    branches: [main]
  # Redeploy when a release is published, so the cover page's release
  # number isn't a release behind - see "Release numbering" below.
  release:
    types: [published]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    env:
      PUPPETEER_SKIP_DOWNLOAD: "true"
      PUPPETEER_EXECUTABLE_PATH: /usr/bin/google-chrome-stable
    steps:
      - uses: actions/configure-pages@v5
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0          # tags, for {{ release }}
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"

      # Pandoc, WeasyPrint's Pango, and your document fonts.
      - run: sudo apt-get update && sudo apt-get install -y pandoc fonts-inter fonts-jetbrains-mono

      # Chrome, for mermaid-cli. Skip this block if you have no diagrams.
      - run: curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor | sudo tee /usr/share/keyrings/google-chrome.gpg > /dev/null
      - run: echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
      - run: sudo apt-get update && sudo apt-get install -y google-chrome-stable
      - run: npm ci --prefix tools/mermaid
      - run: npm ci --prefix tools/mathjax

      - run: pip install -r requirements.txt
      - run: prodockit sync-repo --check
      - run: prodockit pdf
      - run: zensical build --clean --strict

      - uses: actions/upload-pages-artifact@v4
        with:
          path: site               # or "public", matching your site_dir
      - uses: actions/deploy-pages@v4
        id: deployment
```

## GitLab CI {: #ci-gitlab-ci }

The same steps on a slimmer base image, which needs Node and Pango
installing too:

```yaml
pages:
  image: python:latest
  variables:
    PUPPETEER_SKIP_DOWNLOAD: "true"
    PUPPETEER_EXECUTABLE_PATH: /usr/bin/google-chrome-stable
    GIT_DEPTH: "0"                 # tags, for {{ release }}
  script:
    - apt-get update
    - apt-get install -y curl gnupg ca-certificates pandoc libpango-1.0-0 fonts-inter fonts-jetbrains-mono
    - curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    - apt-get install -y nodejs
    - curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
    - echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
    - apt-get update && apt-get install -y google-chrome-stable
    - npm ci --prefix tools/mermaid
    - npm ci --prefix tools/mathjax
    - pip install -r requirements.txt
    - prodockit pdf
    - zensical build --clean --strict
    - mv site public
  artifacts:
    paths: [public]
```

## The traps {: #ci-the-traps }

### `PUPPETEER_SKIP_DOWNLOAD`, not `PUPPETEER_SKIP_CHROMIUM_DOWNLOAD` {: #ci-puppeteer-variable }

Puppeteer renamed this. `mermaid-cli` 11.x resolves to puppeteer 25.x,
which honours only the new name - under the old one the skip does nothing,
so every run downloads a full Chrome build and then discards it in favour
of `PUPPETEER_EXECUTABLE_PATH`. Usually just slow; a hard failure when
that download is blocked or times out.

Three separate projects had the old name. `prodockit init-tools` prints
the correct pair.

### Fonts must actually be installed {: #ci-fonts }

Your website loads its fonts from a CDN at view time. WeasyPrint has no
such fallback - it needs the font files present to embed them, and
**silently substitutes a generic system font** if they're missing. The PDF
builds, publishes, and looks wrong.

Install the packages matching your configured fonts (`fonts-inter` and
`fonts-jetbrains-mono` above), and consider a test asserting the expected
font is embedded.

### A shallow clone has no tags {: #ci-shallow-clone }

`actions/checkout` defaults to `fetch-depth: 1`, which fetches **no tags at
all**. `prodockit.zensical_macros`' `{{ release }}` is `git describe
--tags`, so it returns an empty string and the cover page's release line
silently disappears - while working perfectly in any local clone.

Set `fetch-depth: 0` (GitHub) or `GIT_DEPTH: "0"` (GitLab).

### Release numbering is one behind by default {: #ci-release-numbering }

`{{ release }}` can only report a tag that exists when the build runs, and
a release is normally tagged *after* the commit is pushed - which is what
triggers the deploy. So the first deploy after a release shows the
*previous* one.

So something has to rebuild once the tag exists. The obvious way - adding
`release: [published]` to the deploy workflow itself - is a trap on GitHub
Pages, and a quiet one.

!!! danger "Do not deploy directly from a release event"
    A release event runs against `refs/tags/<tag>`, so the Pages
    deployment it creates carries a **tag ref**. With Pages configured
    `source: {branch: main}`, that deployment is accepted, reports
    `success`, and is then never served - the site carries on returning
    the previous build.

    Nothing fails. The run is green, the deployment shows `success`, the
    one it superseded shows `inactive`, and the site is simply a release
    behind. This project shipped three releases that way before a
    [delivery check](#pinning-watching-for-drift) caught
    it: every deployment from `main` went live, every one from a tag ref
    did not, across nine deployments with no counterexamples.

Trigger the rebuild against your default branch instead. A tiny separate
workflow, which builds nothing itself:

```yaml
name: Redeploy docs after a release
on:
  release:
    types: [published]
permissions:
  actions: write        # lets GITHUB_TOKEN start another run
jobs:
  redeploy:
    runs-on: ubuntu-24.04
    steps:
      - env:
          GH_TOKEN: ${{ github.token }}
          GH_REPO: ${{ github.repository }}
        run: gh workflow run docs.yml --ref main
```

The deploy workflow then needs only `push` and `workflow_dispatch`, and no
tag entry in the environment's deployment branch policies - nothing
deploys from a tag any more.

On GitLab this does not arise: Pages serves whatever the most recent
successful job published, with no branch-scoped source to disagree with.

### Pandoc version drift {: #ci-pandoc-version }

Distribution `pandoc` packages lag well behind upstream - far enough that
some markdown edge cases parse differently than on a contributor's machine.
If that matters to you, install a pinned `.deb` from Pandoc's own releases
instead of `apt-get install pandoc`.

## Checks worth adding {: #ci-checks-worth-adding }

Three prodockit features exist specifically to make CI catch these:

```yaml
- run: prodockit sync-repo --check   # config drifted from the git remote?
- run: prodockit pins --check        # build inputs behind PyPI, or pinned inconsistently?
- run: python -m pytest              # with prodockit[testing]
```

`prodockit sync-repo --check` writes nothing and exits non-zero if your
repo links, icon or badges no longer match the remote - see
[Repository metadata](#sync-repo-repository-metadata) below.
`prodockit pins --check` does the same for build inputs pinned across
several files - see [Version pinning and drift](#pinning-version-pinning-and-drift)
below. [`prodockit.testing`](testing.md) provides fixtures for the built
PDF and site, plus `assert_no_unrendered_mermaid()` /
`assert_no_unrendered_tex()` - which turn the quiet-degradation case into
a failed build rather than a warning nobody read.

## Repository metadata {: #sync-repo-repository-metadata }

\index{`prodockit sync-repo`} keeps the repo-hosting-specific parts of your project
in step with the git remote the checkout actually uses, so forking or
mirroring it between GitHub, GitLab and Bitbucket doesn't leave stale links,
the wrong brand icon, or README badges pointing at somebody else's
repository.

Everything it writes is derived from one thing - `git remote get-url origin`:

- In `zensical.toml`: `repo_url`, `repo_name`, `[project.theme.icon] repo`
  and `edit_uri`.
- In `README.md`: the badge row between the `repo-badges` markers, if you
  have them.

### Quick start {: #sync-repo-quick-start }

Run it from your project root, wherever `zensical.toml` lives:

```bash
prodockit sync-repo
```

It reports only what it actually changed:

```
Detected GitHub remote (https://github.com/you/your-repo); updated: repo_url, repo_name, edit_uri
```

Run it after changing a remote, or as a build step before `zensical build`.
Running it twice does nothing the second time.

### In CI {: #sync-repo-in-ci }

`--check` writes nothing and exits non-zero if anything is out of date -
enough to fail a build when a config has drifted from the remote it's
actually served from:

```bash
prodockit sync-repo --check
```

### Options {: #sync-repo-options }

| Option | Default | What it does |
| --- | --- | --- |
| `-f`, `--config-file` | `zensical.toml` | Which Zensical config to update. |
| \index{prodockit sync-repo!`--readme`} | `README.md` | README to update the badge block in. Pass an empty value to skip it. |
| \index{prodockit sync-repo!`--remote`} | `origin` | Which git remote to read the repository URL from. |
| \index{prodockit sync-repo!`--branch`} | detected | Default branch for `edit_uri` and GitLab build-badge links. |
| \index{prodockit sync-repo!`--check`} | off | Report what would change, write nothing, exit non-zero if anything would. |

### What it does, and why {: #sync-repo-what-it-does }

#### `edit_uri` {: #sync-repo-edit-uri }

Zensical falls back to `edit/master/<docs_dir>` when `edit_uri` isn't set -
hardcoding the `master` branch name whatever your repository's default
actually is, and only for an exact `github.com`/`gitlab.com` host match, so
a self-hosted GitLab gets no default at all and its "edit this page" button
simply never appears.

`sync-repo` sets it explicitly instead, from your remote's real default
branch and matched by *kind* of host rather than exact hostname - so
`gitlab.your-institution.ac.uk` is recognised as GitLab and gets a working
edit link. A host it has no edit-URL convention for is left alone rather
than guessed at.

#### `repo_name` keeps the shape you chose {: #sync-repo-repo-name }

Zensical prints `repo_name` verbatim in the site header, and both
`owner/repo` and a bare `repo` are in legitimate use. `sync-repo` looks at
what your config already says and keeps that shape, updating only the
values - so syncing never silently restyles your header.

#### README badges {: #sync-repo-readme-badges }

If your README contains these markers, the block between them is replaced
with a badge row (build status, stars, forks) pointing at whichever host
your remote is on:

```markdown
<!-- repo-badges:start -->
<!-- repo-badges:end -->
```

GitHub and GitLab have known badge sets. Any other host is reported and
left untouched rather than given invented URLs. If you don't want managed
badges, leave the markers out - their absence is a normal state, not an
error, and `sync-repo` just says so and moves on.

### Using it from Python {: #sync-repo-from-python }

The command is a thin wrapper around
[`prodockit.sync_repo`](https://github.com/buckwem/prodockit-extensions/blob/main/src/prodockit/sync_repo.py),
whose `sync_repo_metadata()` returns what changed rather than printing it:

```python
from prodockit.sync_repo import sync_repo_metadata

result = sync_repo_metadata(check=True)
if result.changed:
    print("out of date:", ", ".join(result.changes))
```

## Version pinning and drift {: #pinning-version-pinning-and-drift }

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
    the [back-of-book index](extensions/index-terms.md) and the table of
    contents.

The answer is two halves that only work together:

1. **Pin the build inputs**, so output changes when someone decides it
   should.
2. **Watch for newer releases**, so pinning does not mean going quietly
   stale.

### Where a version gets declared {: #pinning-where-declared }

Pinning creates its own problem: the same version ends up written in
several files at once, and nothing keeps them in step.

| File | Typically declares | Why that form |
| --- | --- | --- |
| `pyproject.toml` | `zensical>=0.0.52` | A **floor**. An exact pin in a library's metadata propagates to every consumer and conflicts with any project needing a different Zensical. |
| CI docs/build job | `zensical==0.0.52` | An **exact pin**. The site and PDF are artifacts; they should change deliberately. |
| CI test job | `weasyprint==69.0` | An **exact pin**. Tests that assert on where things land in a rendered PDF treat the layout engine as an input, not an implementation detail. |
| Drift job | both, exactly | The baseline it compares the newest release against. |

Both forms are correct in their own place. What is not correct is them
disagreeing, which is easy to do by hand and invisible when it happens.

### `prodockit pins` {: #pinning-prodockit-pins }

Reads every declaration across all of those files, shows what is
currently set against what is newest on PyPI, and moves them together.

```bash
prodockit pins
```

```text
zensical
  pyproject.toml:34  zensical>=0.0.52
  .github/workflows/docs.yml:121  zensical==0.0.52
  .github/workflows/drift.yml:62  zensical==0.0.52
  newest on PyPI: 0.0.53  <- newer available

weasyprint
  .github/workflows/ci.yml:59  weasyprint==69.0
  .github/workflows/docs.yml:121  weasyprint==69.0
  newest on PyPI: 69.0

zensical: version to set [0.0.53]:
```

Press ++enter++ to take the newest release, or type a version. Each site
keeps **its own operator** - the floor stays a floor, the pins stay
pinned - so one answer updates every file correctly.

#### Options {: #pinning-options }

| Option | What it does |
| --- | --- |
| `-r`, `--root` | Project root to scan. Defaults to the current directory. |
| `-p`, `--package` | Package to manage, repeatable. Defaults to `zensical` and `weasyprint`. |
| `--set PACKAGE=VERSION` | Set a version without prompting, repeatable. |
| `--latest` | Take PyPI's newest for every package without prompting. |
| `--check` | Report and exit non-zero if anything is behind or inconsistent. Writes nothing. |
| `--offline` | Skip the PyPI lookup and only report what the files declare. |

`--check` is the one to put in CI:

```bash
prodockit pins --check
```

It fails when a package is behind PyPI **or** when the files disagree with
each other - the second being the failure that pinning across several
files invites.

#### What it scans {: #pinning-what-it-scans }

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

### Watching for drift {: #pinning-watching-for-drift }

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

#### Reporting, not failing {: #pinning-reporting-not-failing }

A newer release is information, not a broken build. A scheduled job that
goes red every week trains everyone to ignore it, so open an issue
instead - and keep **one** open at a time, updating it in place rather
than filing a fresh one every Monday until somebody acts.

#### GitHub Actions {: #pinning-github-actions }

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
          pip install -e ".[testing]" "zensical==0.0.52" "weasyprint==69.0"
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

#### GitLab CI {: #pinning-gitlab-ci }

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
    - pip install -e ".[testing]" "zensical==0.0.52" "weasyprint==69.0"
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

### The input pip cannot reach {: #pinning-runner-image }

`prodockit pins` manages Python packages. The CI runner image is the other
half, and nothing in `pyproject.toml` or a workflow's `pip install` line
touches it:

- **`pandoc`** comes from the image's own package archive. Distribution
  packages lag upstream far enough that some markdown edge cases parse
  differently - see [Pandoc version drift](#ci-pandoc-version).
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

### Taking an upgrade {: #pinning-taking-an-upgrade }

When drift reports something worth having:

```bash
prodockit pins            # accept the suggested version, or type one
prodockit pdf             # rebuild - PDF first ...
zensical build --clean    # ... then the site
```

Then diff the built output against the previous version before committing.
That is the step the whole arrangement exists to make possible: seeing what
an upgrade does to your document *before* your readers do.

### Limitations and workarounds {: #pinning-limitations }

See [Limitations and workarounds](limitations.md) for the general list.
Specific to pinning:

- **A floor still floats.** `zensical>=0.0.52` in `pyproject.toml` records
  a version; it does not control one. Only the exact pin in the build job
  does. Both exist deliberately - see the table above.
- **Only pip packages are watched.** `pandoc` and Chrome arrive from the
  runner image, so a drift job that installs both builds in one job cannot
  see them change between weeks. Pinning the image is the lever for those -
  see below.
- **`prodockit pins` needs network** for `--latest` and the suggested
  default. Use `--offline` to report what the files declare without asking
  PyPI.
