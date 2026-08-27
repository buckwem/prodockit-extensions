---
icon: lucide/cloud-upload
---

{{ heading_counter_reset(page) }}

# Publishing overview

Publishing turns the site you previewed locally into outputs other people can
open: a website on GitHub Pages or GitLab Pages and, when the project needs
one, a downloadable PDF.

This section is for a document author with a working local project. It covers
template updates, \index{continuous integration} (CI), automated Pages
deployment, and checks on the published result. For a new project, first
choose [adoption or template bootstrap](introduction.md). Maintainers changing
the prodockit package itself should use
[Maintain prodockit](project-maintenance.md).

Start here after [building your first site](getting-started.md). This section
uses one repeatable \index{publishing workflow}: prepare the project, build both outputs, test what
was built, push the source, and verify what the hosting service actually
serves.

## Choose your starting point

| Starting point | First guide |
|---|---|
| You want a ready-made report project | [Start with prodockit-template](prodockit-template.md) explains what it provides and which files become yours |
| A new computer or an incomplete checkout | [Set up a machine](devcons/bootstrap.md) checks and prepares Python, Git, Node, Pandoc, fonts, and the project environment |
| An existing template-derived project | [Staying in step with the template](devcons/template-sync.md) brings shared workflows and publishing files up to date without replacing your writing |
| A working project that already previews with `zensical serve` | Continue with the publishing path below |
| A prodockit package release rather than a documentation project | Use the maintainer [Build and release](devcons/releasing.md) runbook instead |

The template is a starting copy, not a live dependency. Your Markdown remains
project-owned; later template fixes arrive only when you review and apply a
template sync.

## Follow the publishing path

/// steps

//// step | Prepare the checkout

From the project root, confirm that Git sees only the work you intend to
publish:

```bash
git status --short
```

If this machine has not built the project before, run the report-only setup
check:

```bash
prodockit bootstrap
```

For a template-derived project, also preview upstream publishing changes:

```bash
prodockit template-sync
```

Neither ordinary command applies changes. Follow its detailed guide if it
reports work to do.

////

//// step | Build the PDF first

```bash
prodockit pdf
```

The PDF uses the pages and order in `zensical.toml`. Build it before the
website because Zensical copies the finished PDF into the site output. Skip
this step only when the project deliberately publishes no PDF.

See [Generate a PDF](pdf.md) for the required system tools and optional page,
cover, diagram, maths, and index settings.

////

//// step | Build the website strictly

```bash
prodockit build --strict
```

Prodockit adds each page's revision date to a temporary source copy, then runs
`zensical build --clean`. `--strict` turns validation warnings such as broken
internal links into failures. The result is written to `site/` unless the
project configures another `site_dir`; the source Markdown and configuration
remain unchanged.

////

//// step | Test the files that were built

```bash
python -m pytest
```

Source tests and output tests answer different questions. Output tests can
open the generated HTML and PDF, confirm expected pages and fonts, and detect
raw Mermaid or TeX source left behind by a missing renderer. See
[Test the built output](devcons/testing.md).

////

//// step | Push through the publishing workflow

Commit only reviewed source files, then push the branch and use the
repository's normal pull-request or merge-request gate:

```bash
git push -u origin HEAD
```

After the change reaches the default branch, the supplied workflow rebuilds
the PDF and site and runs its output checks on a clean Linux runner before it
deploys. [Publish automatically](devcons/continuous-integration.md) explains
the GitHub and GitLab recipes, which checks are gates, and every external tool
they install.

////

//// step | Verify the public result

Do not stop at a green deployment job. Open the public website, follow its PDF
download, and check a page changed by this publication.

=== "GitHub Pages"

    Open the repository's **Actions** page, select the documentation workflow,
    and confirm both its deploy and live-verification jobs passed.

=== "GitLab Pages"

    Open **Build > Pipelines**, inspect the `pages` job, then use
    **Deploy > Pages** to open the published address.

The workflow proves that the artifact was accepted; the final browser check
proves that a reader can retrieve the intended version.

////

///

## Know which output you are checking

| Output | Built by | Typical location | Final check |
|---|---|---|---|
| Local preview | `zensical serve` | Address printed in the terminal | Edit a page and see it refresh |
| Static website | `prodockit build --strict` | `site/` | Open pages, revision dates, navigation, links, search, and downloadable files |
| Complete PDF | `prodockit pdf` | `docs/site_documentation.pdf` by default | Inspect cover, contents, page breaks, diagrams, fonts, and index |
| Hosted website | GitHub Pages or GitLab Pages workflow | Project Pages URL | Confirm the public page contains the reviewed change |

## Build with revision dates {: #build-with-revision-dates }

The \index{commands!`prodockit build`} command gives the final site a “Last
update” fact without putting generated fields into tracked Markdown:

### Use the command without adoption

`prodockit build` is a standalone command. It needs an existing Zensical or
MkDocs project, but it does **not** require that project to adopt Prodockit's
extensions, stylesheets, macros, template, or publishing workflows.

1. Change to the directory containing `zensical.toml`, `mkdocs.yml`, or
    `mkdocs.yaml`:

    ```bash
    cd /path/to/your-document
    ```

2. Activate the Python environment that normally builds the document:

    === "macOS"

        ```bash
        source .venv/bin/activate
        ```

    === "Windows PowerShell"

        ```powershell
        .\.venv\Scripts\Activate.ps1
        ```

    === "Ubuntu"

        ```bash
        source .venv/bin/activate
        ```

3. Install the latest Prodockit package into that environment:

    ```bash
    python -m pip install --upgrade prodockit
    ```

4. Build the site:

    ```bash
    prodockit build --strict
    ```

The command writes the configured website output, normally `site/`. It does
not edit the source Markdown or configuration. You do not need to run
`prodockit adopt` before or after these steps.

### Use the command without Git

Git is optional. When the project is not inside a Git repository,
`prodockit build` uses each Markdown file's modification timestamp as its
update date. It converts the timestamp to a calendar date in UTC and reports
that fallback while building. Saving a file changes its modification time, so
the next build updates that page's date.

Run exactly the same command:

```bash
prodockit build --strict
```

The optional `--creation-dates` switch is not useful outside Git because a
file modification timestamp does not establish when the page was created.
If a page needs a fixed, reviewed date instead, put it in that page's front
matter:

```yaml
---
revision_date: 2026-08-27
---
```

This manually supplied value takes priority in both Git and non-Git projects.

### Understand dates in a Git project

For a tracked page, the newest Git **author date** is used. A new or untracked
page that has no Git history yet uses the source file's modification
timestamp, converted to a calendar date in UTC, and names that fallback in
the command output. A manually written `revision_date` or
`git_revision_date_localized` in page front matter always wins.

Creation dates are deliberately optional because they require the complete
rename history of every page:

```bash
prodockit build --strict --creation-dates
```

This adds the oldest Git author date for tracked pages. File modification
times are never described as creation dates.

The command refuses a shallow repository because Git can return its oldest
available boundary commit as a believable but incorrect page date. In GitHub
Actions use `fetch-depth: 0`; in GitLab CI use `GIT_DEPTH: "0"`. A repository
that exists but cannot be read also fails instead of silently substituting a
different date.

Revision metadata exists only in a temporary copy below the project root.
Prodockit points a temporary configuration at that copy, invokes the public
Zensical CLI, then removes both temporary paths on success or failure. A
normal `zensical serve` preview therefore does not show generated dates unless
the page already declares one manually.

## Use the detailed guides when needed

- [Set up a machine](devcons/bootstrap.md) prepares a computer and checkout.
- [Start with prodockit-template](prodockit-template.md) introduces the starter
  project, its two outputs, and the boundary between your work and shared
  publishing infrastructure.
- [Staying in step with the template](devcons/template-sync.md) updates shared
  publishing infrastructure without taking ownership of project content.
- [Generate a PDF](pdf.md) covers local PDF requirements and configuration.
- [Publish automatically](devcons/continuous-integration.md) provides GitHub
  Actions and GitLab CI workflows.
- [Test the built output](devcons/testing.md) adds reusable pytest checks.
- [Website macros](macros.md) is the advanced reference for values and layout
  helpers evaluated while the site and PDF are rendered.
