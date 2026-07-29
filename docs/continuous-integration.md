# Continuous integration {: #ci-continuous-integration }

Building a prodockit site in \index{continuous integration!CI} needs more than `pip install`. The PDF
pipeline shells out to external binaries, and several of the ways it goes
wrong are silent - the build succeeds and publishes something subtly wrong.

This page is the recipe, and the reasoning behind each part of it.

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

The `release: [published]` trigger above fixes that by redeploying once the
tag exists. On GitHub Pages this also needs a matching tag entry in the
environment's deployment branch policies, since a release event runs
against `refs/tags/<tag>` rather than a branch - without it the run is
rejected at the environment gate instead of deploying.

### Pandoc version drift {: #ci-pandoc-version }

Distribution `pandoc` packages lag well behind upstream - far enough that
some markdown edge cases parse differently than on a contributor's machine.
If that matters to you, install a pinned `.deb` from Pandoc's own releases
instead of `apt-get install pandoc`.

## Checks worth adding {: #ci-checks-worth-adding }

Two prodockit features exist specifically to make CI catch these:

```yaml
- run: prodockit sync-repo --check   # config drifted from the git remote?
- run: python -m pytest              # with prodockit[testing]
```

`prodockit sync-repo --check` writes nothing and exits non-zero if your
repo links, icon or badges no longer match the remote.
[`prodockit.testing`](testing.md) provides fixtures for the built PDF and
site, plus `assert_no_unrendered_mermaid()` /
`assert_no_unrendered_tex()` - which turn the quiet-degradation case into
a failed build rather than a warning nobody read.
