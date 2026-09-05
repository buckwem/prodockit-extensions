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
deployment, and checks on the published result. For a new project, first choose
[an installation path](choosing-installation.md).
Maintainers changing
the prodockit package itself should use
[Maintain prodockit](project-maintenance.md).

Start here after [building your first site](getting-started.md). This section
uses one repeatable \index{publishing workflow}: prepare the project, build both outputs, test what
was built, push the source, and verify what the hosting service actually
serves.

## Choose your starting point

\ref{tab-publishing-choose-your-starting-point} directs each project state to
the appropriate publishing guide.

| Starting point | First guide |
|---|---|
| You want a ready-made report project | [Start with prodockit-template](prodockit-template.md) explains what it provides and which files become yours |
| A new computer or an incomplete template-based checkout | [Bootstrap](devcons/bootstrap.md) checks and prepares Python, Git, Node, Pandoc, fonts, and the project environment |
| An established documentation project that should keep its existing design and workflow | [Adoption](adopt.md) integrates selected prodockit components without replacing those choices |
| A project whose dependencies are managed directly | [Manual installation](installation.md) covers preparation and package configuration; [Requirements and dependencies](requirements-dependencies.md) records the supported toolchain |
| An existing template-derived project | [Staying in step with the template](devcons/template-sync.md) brings shared workflows and publishing files up to date without replacing your writing |
| A working project that already previews with `zensical serve` | Continue with the publishing path below |
| A prodockit package release rather than a documentation project | Use the maintainer [Build and release](devcons/releasing.md) runbook instead |
/// table-caption | <
    attrs: {id: tab-publishing-choose-your-starting-point}

Choose your starting point
///

The template is a starting copy, not a live dependency. Your Markdown remains
project-owned; later template fixes arrive only when you review and apply a
template sync.

## Follow the publishing path

Build and inspect the complete outputs locally before asking the hosting service
to publish the same commit.

/// steps

//// step | Prepare the checkout

From the project root, confirm that Git sees only the work you intend to
publish:

```bash
git status --short
```

For a project prepared through bootstrap, run its report-only setup check:

```bash
prodockit bootstrap
```

For an adopted or manually installed project, activate its environment and
verify the dependencies described by its chosen route instead. A first build
on a machine does not, by itself, mean that bootstrap should be run.

For a template-derived project, also preview upstream publishing changes:

```bash
prodockit template-sync
```

Neither ordinary command applies changes. Follow its detailed guide if it
reports work to do.

////

//// step | Build the website strictly

```bash
zensical build --clean --strict
```

`--strict` turns validation warnings such as
broken internal links into failures. The result is written to `site/` unless
the project configures another `site_dir`.

////

//// step | Build the PDF from the completed website

```bash
prodockit pdf
```

The PDF uses the rendered website pages and the order in `zensical.toml`.
The command does not invoke Zensical, so build the website first. Skip this
step only when the project deliberately publishes no PDF.

See [Generate a PDF](pdf.md) for the three preparation routes, required system
tools, and optional page, cover, diagram, maths, and index settings.

////

//// step | Add optional page dates

If the website should display page update dates, run:

```bash
prodockit update-dates
```

It adds each page's date to the completed HTML; the source Markdown and
configuration remain unchanged. Omit it when dates are not required.

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

Use \ref{tab-publishing-know-which-output-you-are-checking} to distinguish
local intermediates from the website and PDF readers finally receive.

| Output | Built by | Typical location | Final check |
|---|---|---|---|
| Local preview | `zensical serve` | Address printed in the terminal | Edit a page and see it refresh |
| Static website | `zensical build --clean --strict`; optionally `prodockit update-dates` | `site/` | Open pages, optional revision dates, navigation, links, search, and downloadable files |
| Complete PDF | `prodockit pdf` | `docs/site_documentation.pdf` by default | Inspect cover, contents, page breaks, diagrams, fonts, and index |
| Hosted website | GitHub Pages or GitLab Pages workflow | Project Pages URL | Confirm the public page contains the reviewed change |
/// table-caption | <
    attrs: {id: tab-publishing-know-which-output-you-are-checking}

Know which output you are checking
///

## Build with revision dates {: #build-with-revision-dates }

The optional \index{commands!`prodockit update-dates`} command gives the final
site an “Updated” fact without putting generated fields into tracked Markdown.
Run it only when the published website should display page dates. Without it,
the Zensical build and publication workflow remain complete and valid.

See [Page update dates](update-dates.md) for where the date is
inserted and how an author can override it for one page. The rest of this
section covers building and publication.

### Use the command without adoption

`prodockit update-dates` is a standalone command. It needs a website already
built from an existing Zensical project, but it does **not** require that
project to adopt Prodockit's extensions, stylesheets, macros, template, or
publishing workflows.

1. Change to the directory containing `zensical.toml`:

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
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
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

4. Build the site with its usual command, then add the dates:

    ```bash
    zensical build --clean --strict
    prodockit update-dates
    ```

The second command changes only the configured website output, normally
`site/`. It does not call Zensical and does not edit the source Markdown or
configuration. You do not need to run `prodockit adopt` before or after these
steps.

### Use the command without Git

Git is optional. When the project is not inside a Git repository,
`prodockit update-dates` uses each Markdown file's modification timestamp as its
update date. It converts the timestamp to a calendar date in UTC and reports
that fallback while building. Saving a file changes its modification time, so
the next build updates that page's date.

Run the same two-command sequence:

```bash
zensical build --clean --strict
prodockit update-dates
```

You do not need an option to enable this fallback. A manually supplied
`revision_date`, as shown above, takes priority in both Git and non-Git
projects.

### Understand dates in a Git project

For a tracked page, the newest Git **author date** is used. A new or untracked
page that has no Git history yet uses the source file's modification
timestamp. Prodockit converts either automatic timestamp to UTC before taking
its calendar date, so authors and CI runners in different time zones get the
same result. The command names a modification-time fallback in its output. A
manually written `revision_date` or
`git_revision_date_localized` in page front matter always wins.

If the project is in Git but you deliberately want filesystem dates rather
than Git author dates, select them explicitly:

```bash
prodockit update-dates --modification-dates
```

This applies modification dates to tracked and untracked Markdown files alike.
Prodockit does not calculate or inject creation dates.

The command refuses a shallow repository because Git can return its oldest
available boundary commit as a believable but incorrect page date. In GitHub
Actions use `fetch-depth: 0`; in GitLab CI use `GIT_DEPTH: "0"`. A repository
that exists but cannot be read also fails instead of silently substituting a
different date.

Prodockit inserts the facts into the generated HTML only. It deliberately does
not invoke a site builder, so this post-processing step composes with other
tools that run before or after Zensical. Run it again after every clean site
build because that build replaces the generated HTML.

A normal `zensical serve` preview rebuilds pages continuously and therefore
does not retain automatically generated dates. Pages that declare a date in
front matter can still show it in the preview; use the completed static build
to inspect automatic Git or modification dates.

## Use the detailed guides when needed

Open the detailed guide for the part of the workflow that needs attention:

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
