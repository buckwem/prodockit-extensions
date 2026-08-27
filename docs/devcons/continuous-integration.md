---
icon: lucide/workflow
---

{{ heading_counter_reset(page) }}

# Publish automatically {: #ci-continuous-integration }

This page is for a document author who wants a reviewed Markdown change to
become a website and PDF automatically. \index{continuous integration} (CI) runs the
publishing commands on a clean hosted machine after a push, then hands the
static website to GitHub Pages or GitLab Pages.

You should not have to design that automation. `prodockit-template` supplies
the maintained files; this page explains how to use them, what they build, and
how to tell whether publication really succeeded.

On GitHub, \index{GitHub Actions} runs the workflow. On GitLab, the equivalent
pipeline is \index{GitLab CI}.

## Use the maintained automation files {: #ci-github-actions }

| Host | Maintained source | What runs |
|---|---|---|
| GitHub Pages | [`docs.yml`](https://github.com/buckwem/prodockit-template/blob/main/.github/workflows/docs.yml) | Builds the outputs, uploads the site, deploys Pages, and verifies the public site |
| GitLab Pages | [`.gitlab-ci.yml`](https://github.com/buckwem/prodockit-template/blob/main/.gitlab-ci.yml) | Builds the outputs and publishes the `public/` Pages artifact |

The comments in those files explain settings that must remain beside the
commands they control: pinned system tools, browser variables, fonts, build
order, Pages permissions, and artifact paths. Refer to the files for exact
YAML rather than copying a workflow from this guide.

Projects created from `prodockit-template` already contain both files. If an
older template-derived project is missing later workflow fixes, preview them
without writing:

```bash
prodockit template-sync
```

Review and apply the result using
[Staying in step with the template](template-sync.md).

## Publish the first change

/// steps

//// step | Prove the project builds locally

```bash
prodockit pdf
zensical build --clean --strict
prodockit update-dates
python -m pytest
```

Fix a local failure before pushing. CI starts from a clean machine, so it
cannot repair a missing page, broken link, or failing test that is already
reproducible in the checkout.

////

//// step | Confirm the publishing file is present

=== "GitHub Pages"

    Confirm `.github/workflows/docs.yml` exists. It should run when the
    repository's default branch changes and should allow a manual run for
    recovery.

=== "GitLab Pages"

    Confirm `.gitlab-ci.yml` contains a `pages` job. GitLab reserves the name
    `public/` for the directory that job publishes.

Use the maintained links above to compare a file that appears incomplete. Do
not replace a customised workflow until you have reviewed the difference.

////

//// step | Push through the review gate

```bash
git push -u origin HEAD
```

Open a pull request or merge request. After its checks and review are
complete, merge it into the branch the publishing workflow watches—normally
`main`.

////

//// step | Watch the publishing job

=== "GitHub Pages"

    Open **Actions**, select **Documentation**, and open the run for the merged
    commit. Check both the deployment and later live-verification result.

=== "GitLab Pages"

    Open **Build > Pipelines**, select the pipeline for the merged commit, and
    inspect its `pages` job. Then use **Deploy > Pages** to find the published
    address.

////

//// step | Verify delivery as a reader

Open the Pages address in a private browser window. Find the known change,
follow a navigation link, and download the PDF from the site.

A successful build proves an artifact was produced. A successful deployment
proves the host accepted it. Opening the public result proves a reader can
retrieve the intended version; these are three separate checks.

////

///

## Understand the build order

```mermaid
flowchart LR
    source[Markdown and zensical.toml] --> pdf[prodockit pdf]
    pdf --> site[zensical build]
    site --> dates[prodockit update-dates]
    dates --> tests[Built-output tests]
    tests --> deploy[Pages deployment]
    deploy --> verify[Public verification]
```

The PDF is built before the website because it lives under `docs/` by default.
Zensical copies it into the static site together with other downloadable
files. Reversing the commands can publish the PDF left by an earlier run.

Some projects also run `prodockit source-bundle` before the site build. That creates
a second downloadable PDF containing the Markdown and configuration rather
than the rendered report.

## Know what the hosted machine needs {: #ci-what-the-build-needs }

| Requirement | Used for | Failure when absent |
|---|---|---|
| Python requirements | Zensical, prodockit, WeasyPrint, and tests | The command normally fails |
| Pandoc | PDF conversion and `prodockit.bibliography` | The build fails |
| WeasyPrint native libraries | PDF layout | Import or PDF build fails |
| Document fonts | Correct PDF typography and pagination | A fallback font may be substituted silently |
| Node, Mermaid CLI, and Chrome | Mermaid diagrams in the PDF | The PDF can contain raw diagram source |
| Node and MathJax | TeX maths in the PDF and website bundle | The output can contain raw TeX |
| Citation style files | Bibliography formatting | A configured missing style stops rendering |
| Suitable Git history or release metadata | Version text used by a cover or macro | The field can be empty or one release behind |

The maintained workflow files install these in dependency order. A document
author normally changes the content and requirements, not the operating-system
recipe.

## Catch failures that still produce output {: #ci-the-traps }

### Render diagrams and maths {: #ci-puppeteer-variable }

WeasyPrint has no JavaScript engine. The PDF build therefore turns Mermaid and
TeX maths into static images before Pandoc sees the pages. If either renderer
is missing, the command warns but can still create a PDF.

Build-output tests make that warning enforceable:

```python
from prodockit.testing import assert_no_unrendered_mermaid, assert_no_unrendered_tex


def test_diagrams_and_maths_rendered(prodockit_pdf_page_texts):
    assert_no_unrendered_mermaid(prodockit_pdf_page_texts)
    assert_no_unrendered_tex(prodockit_pdf_page_texts)
```

The template workflow uses `PUPPETEER_SKIP_DOWNLOAD`, not the obsolete
`PUPPETEER_SKIP_CHROMIUM_DOWNLOAD`, and points Mermaid at the Chrome installed
by the job. Keep those details in the workflow where future package updates
can change them.

### Check embedded fonts {: #ci-fonts }

The website can download fonts when a browser opens it. A PDF must embed fonts
available on the build machine. WeasyPrint may silently substitute another
font, changing appearance, line wrapping, pagination, and index page numbers.

Use the template's font packages as the starting point and add an output test
when the project requires a particular typeface.

### Fetch tags only when the document uses them {: #ci-shallow-clone }

The `{% raw %}{{ release }}{% endraw %}` macro reads Git tags reachable from the checked-out
commit. GitHub's default shallow checkout has no tags, so the value becomes an
empty string without failing the build. Set a full checkout only when the
document uses tag-derived macros; the template's PDF-only `{RELEASE}` marker
uses host release metadata instead.

### Test the artifact, not only the source {: #ci-checks-worth-adding }

`prodockit.testing` opens the generated site and PDF. Start with checks that
prove the required outputs exist, then add document-specific expectations:

```python
def test_the_pdf_was_built(prodockit_pdf):
    assert prodockit_pdf.page_count > 1


def test_the_site_has_the_cover(prodockit_soup_for):
    cover = prodockit_soup_for("index.html")
    assert cover.title is not None
```

The template's own sample-output checks describe its starter document and are
advisory because real projects replace that content. A generated project
should replace them with assertions about its own required output and decide
which must gate publication. See [Test the built output](testing.md).

## Troubleshoot a publishing run

| Symptom | Start with |
|---|---|
| The same command fails locally | Fix the source or local configuration before investigating CI |
| A tool is absent only in CI | Compare the workflow with the maintained template file and its pinned requirements |
| The PDF contains raw Mermaid or TeX | Check the Node installs, Chrome path, and built-output tests |
| The PDF uses the wrong font | Check the operating-system font packages and inspect embedded fonts |
| The website builds but the PDF link is stale | Confirm the PDF command runs before Zensical and both use the same artifact directory |
| GitHub deploys but the public page is old | Inspect the workflow's live-verification job and rerun the maintained workflow against the default branch |
| GitLab succeeds but no site is visible | Open **Deploy > Pages**, then check project/instance Pages visibility and the `public/` artifact |

<span id="ci-release-numbering"></span>
<span id="ci-pandoc-version"></span>
<span id="ci-gitlab-ci"></span>

Repository release numbering, dependency drift, and workflow maintenance are
covered in [Maintain prodockit](../project-maintenance.md). Existing links to
the former sections above remain valid.
