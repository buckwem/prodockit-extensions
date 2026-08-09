# Continuous integration {: #ci-continuous-integration }

Building a prodockit site in \index{continuous integration!CI} needs more than `pip install`. The PDF
pipeline shells out to external binaries, and several of the ways it goes
wrong are silent - the build succeeds and publishes something subtly wrong.

The recipe, and the reasoning behind each part of it.

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

No `release:` trigger, deliberately - see [Release numbering](#ci-release-numbering)
below for why deploying straight from one looks like the obvious fix and
is actually a trap that fails silently. The cover page's release line
still needs a rebuild once a tag exists; that comes from a small separate
workflow instead.

```yaml
name: Documentation
on:
  push:
    branches: [main]
  workflow_dispatch:

# Publishing a release just after merging its version bump starts two
# deploys at once - one for the push, one for the release - and without
# this they race. See "Release numbering" below.
concurrency:
  group: pages
  cancel-in-progress: false

env:
  PANDOC_VERSION: "3.10.1"

permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-24.04
    # Consumed by the verify job below.
    outputs:
      page_url: ${{ steps.deployment.outputs.page_url }}
      index_sha: ${{ steps.fingerprint.outputs.index_sha }}
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

      # WeasyPrint's Pango and your document fonts. Pandoc comes from an
      # upstream release rather than the image - see "Pandoc version drift".
      - run: sudo apt-get update && sudo apt-get install -y curl fonts-inter fonts-jetbrains-mono
      - run: |
          curl -fsSL -o /tmp/pandoc.deb "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb"
          sudo apt install -y /tmp/pandoc.deb

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

      # Fingerprint what's about to publish, for the verify job below -
      # taken from the same directory upload-pages-artifact packs,
      # immediately before it packs it.
      - id: fingerprint
        run: echo "index_sha=$(sha256sum site/index.html | cut -d' ' -f1)" >> "$GITHUB_OUTPUT"
      - uses: actions/upload-pages-artifact@v4
        with:
          path: site               # or "public", matching your site_dir
      - uses: actions/deploy-pages@v4
        id: deployment
```

A successful deploy is not proof the site serves it. GitHub Pages has,
more than once, reported `success` and quietly kept serving the previous
build - see [Watching for drift](pinning-drift.md#pinning-watching-for-drift) below for
the same idea applied to package versions, and
[Release numbering](#ci-release-numbering) for the specific way this bit
this project. A separate `verify` job closes the gap: it polls the live
page and fails the run if it never matches the build just deployed,
without ever gating the deploy itself on delivery.

```yaml
  verify:
    needs: deploy
    runs-on: ubuntu-24.04
    steps:
      - name: Verify the live site serves this build
        env:
          PAGE_URL: ${{ needs.deploy.outputs.page_url }}
          WANT: ${{ needs.deploy.outputs.index_sha }}
        run: |
          set -u
          # Pages serves cache-control: max-age=600, so ~10 minutes of
          # staleness is normal rather than a fault. 15 minutes of polling
          # clears that window with room to spare.
          for attempt in $(seq 1 30); do
            # Download to a file rather than piping into sha256sum or
            # capturing with $(...) - a failed fetch would otherwise
            # silently hash empty input, or the captured body would lose
            # its trailing newline and never match the file on disk.
            if curl -fsSL --max-time 30 -o live-index.html "$PAGE_URL"; then
              got=$(sha256sum live-index.html | cut -d' ' -f1)
            else
              got="fetch-failed"
            fi
            [ "$got" = "$WANT" ] && exit 0
            sleep 30
          done
          echo "::error::$PAGE_URL is not serving this build after 15 minutes."
          exit 1
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
    PANDOC_VERSION: "3.10.1"       # not the image's - see "Pandoc version drift"
  script:
    - apt-get update
    - apt-get install -y curl gnupg ca-certificates libpango-1.0-0 fonts-inter fonts-jetbrains-mono
    - curl -fsSL -o /tmp/pandoc.deb "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb"
    - apt-get install -y /tmp/pandoc.deb
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

No `verify` job here - GitLab Pages serves whatever the most recent
successful job published, with no branch-scoped source to disagree with,
so the failure mode the GitHub `verify` job guards against doesn't arise
on this host.

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
    [delivery check](pinning-drift.md#pinning-watching-for-drift) caught
    it: every deployment from `main` went live, every one from a tag ref
    did not, across nine deployments with no counterexamples.

!!! warning "And serialise your deploys, or the two runs race"
    Publishing a release right after merging its version bump starts two
    deploys at once: one for the push, one for the release. Without the
    `concurrency` group in the workflow above, they run concurrently and
    the winner is whichever finishes last, not whichever is newest.

    This project shipped 0.15.1 that way. The push run had checked out
    `main` before the tag existed, so its build saw the *previous* tag -
    and its deployment is the one that ended up live, even though the
    release run started later, finished later, and reported success. The
    site sat on the old release number until a manual redeploy.

    `cancel-in-progress: false` rather than `true`: a queued deploy should
    wait and then supersede, not be thrown away.

Trigger the rebuild against your default branch instead. A tiny separate
workflow, which builds nothing itself:

```yaml
name: Redeploy docs after a release
on:
  release:
    types: [published]
  workflow_dispatch:     # so it can be re-run by hand
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

Distribution `pandoc` packages lag well behind upstream. `ubuntu-24.04`
ships **3.1.3**; a contributor on macOS or Windows has whatever Homebrew or
winget last gave them. Install a pinned `.deb` from Pandoc's own releases,
as the recipe above does, rather than `apt-get install pandoc`.

!!! danger "This gap hides bugs rather than causing them"
    Pandoc 3.1.3 accepted `<pre><code>` containing element markup as a code
    block. Pandoc 3.10 does not. Zensical's highlighter emits exactly that
    markup, so on a current pandoc every fenced code block in the PDF lost
    its `<pre>` and reflowed as justified prose - while CI, on the image's
    older package, kept publishing perfect output.

    The published PDFs were correct and every local build was broken, for
    as long as nobody compared them. CI could not have caught it, and would
    have started producing it unannounced at the next runner-image bump,
    with no commit to blame.

    Pinning does not prevent that class of change. It makes it arrive as a
    version bump you can bisect instead of a Tuesday.

## Checks worth adding {: #ci-checks-worth-adding }

Three prodockit features exist specifically to make CI catch these:

```yaml
- run: prodockit sync-repo --check          # config drifted from the git remote?
- run: prodockit pins --check --offline     # build inputs pinned inconsistently?
- run: python -m pytest                     # with prodockit[testing]
```

`prodockit sync-repo --check` writes nothing and exits non-zero if your
repo links, icon or badges no longer match the remote - see
[Repository metadata](repo-metadata.md#sync-repo-repository-metadata) below.
`prodockit pins --check` does the same for build inputs pinned across
several files - see [Version pinning and drift](pinning-drift.md#pinning-version-pinning-and-drift)
below. Use `--offline` on a pull-request gate: without it the check also
asks PyPI what the newest version is, so an upstream release or a network
blip can fail a pull request that changed nothing. Comparing the pins
against each other needs no network, and that is the part worth gating on. [`prodockit.testing`](testing.md) provides fixtures for the built
PDF and site, plus `assert_no_unrendered_mermaid()` /
`assert_no_unrendered_tex()` - which turn the quiet-degradation case into
a failed build rather than a warning nobody read.

