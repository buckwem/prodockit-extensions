---
icon: lucide/layout-template
---

{{ heading_counter_reset(page) }}

# Start with prodockit-template

The \index{`prodockit-template`} project ([GitHub
repository](https://github.com/buckwem/prodockit-template)) is a
ready-made Zensical project for coursework, assignments, and professional
reports. Its central promise is **one source, two outputs**: write the report
as Markdown under `docs/`, then build both a browsable website and a single PDF
from the same pages and navigation.

Use the template when you want the publishing structure supplied for you. It
does not prescribe the subject or wording of the report, and it does not turn
your project into a live copy of the template.

The template is maintained on GitHub. Its Surrey GitLab repository is a
student-facing mirror of that source, not a separate edition with an
independent set of fixes. Surrey students clone the nearby mirror; other
projects normally clone GitHub.

## See what the template provides

The starter repository already connects authoring, rendering, testing, and
deployment:

/// tree
docs/ - content and appearance
  index.md - report cover
  originality.md - originality and AI-use statement
  section1.md - starter report section
  acronyms.md - acronym list
  glossary.md - glossary
  references.md - formatted reference list
  stylesheets/ - website and PDF styles
zensical.toml - site, navigation, extensions, and PDF settings
requirements.txt - Python build dependencies
tools/ - pinned Mermaid and MathJax Node tooling
overrides/ - Zensical theme customisations
macros.py - shared macros and Surrey environment detection
.github/workflows/docs.yml - GitHub Pages build and deployment
.gitlab-ci.yml - GitLab Pages build and deployment
///

The sample pages demonstrate the enabled prodockit extensions. Replace their
starter prose and headings with your report; keep the publishing files until
you have a specific reason to customise them.

## Adapt one template to its host

The project-specific `macros.py` defines an \index{`is_surrey`} value. It becomes true
when the build sees the Surrey GitLab CI host, a Surrey `origin` remote, or a
Surrey address in the Zensical environment. The template uses that value to
select the Surrey cover and Surrey logos; otherwise it renders the generic
cover and logos.

```jinja title="The choice made in the template cover"
{% if is_surrey %}
    Surrey cover and branding
{% else %}
    Generic cover and branding
{% endif %}
```

This keeps the report structure, extensions, build commands, and workflows the
same on both hosts. Branding is enabled by where the project is built rather
than by asking students to maintain a second configuration file.

## Create a project safely

The recommended route is `prodockit bootstrap`. It checks the computer, clones
the correct template for the selected host, separates the clone from the
template's Git history, points it at your own empty repository, installs the
project environment, and verifies the first push and published site.

/// steps

//// step | Install enough to run bootstrap

Install Python and prodockit first. The [machine setup guide](devcons/bootstrap.md)
provides commands for macOS, Ubuntu, and Windows and explains why bootstrap
cannot install the command that is currently running.

////

//// step | Configure the project

```bash
prodockit bootstrap --configure
```

Choose the host, namespace or organisation, project name, local directory,
and commit identity. Configuration is written beside the project so a later
check uses the same answers.

////

//// step | Review the plan

```bash
prodockit bootstrap --dry-run
```

This prints the outstanding stages and commands without applying them. One
stage deliberately replaces the template's Git history with a history of your
own; bootstrap marks that destructive stage clearly and does not accept the
default answer for it.

////

//// step | Apply and verify

```bash
prodockit bootstrap --apply
```

Bootstrap guides the two browser actions it cannot perform without holding
your credentials: uploading the SSH public key and creating an empty project.
It then verifies both rather than assuming a click succeeded.

////

///

The source template depends on the selected host:

=== "GitHub"

    Bootstrap clones
    `github.com/buckwem/prodockit-template`, then points `origin` at the empty
    repository you create in your account or organisation.

=== "GitLab.com"

    Bootstrap uses the GitHub template as its public source, then points
    `origin` at your GitLab namespace. Your finished project and Pages site
    remain on GitLab.

=== "University of Surrey GitLab"

    Bootstrap clones the synchronised Surrey student mirror at
    `gitlab.surrey.ac.uk/mb0105/prodockit-template`. A GitHub account is not
    required. The `is_surrey` macro detects that remote and enables the Surrey
    presentation automatically.

If a course or organisation has already created a repository for you, set
`source_url` during configuration. Bootstrap clones that project instead of
starting from the public template and keeps its existing history.

## Know what becomes yours

After creation, the repository is your project. The template manifest,
`.prodockit-template.toml`, classifies files so a later
`prodockit template-sync` can update shared publishing infrastructure without
guessing about ownership.

![Template files are classified as managed or shared, author-owned, or generated and local so later updates preserve the author's work](assets/diagrams/template-file-ownership.png){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-template-file-ownership}

Template file ownership
///

| Classification | Examples | Later template update |
|---|---|---|
| **Project-owned** | Markdown and assets under `docs/`, bibliography files, licence, editor and prose-lint choices | Never read for comparison and never written |
| **Template-owned** | Pages workflows, `.gitlab-ci.yml`, styles, JavaScript, `macros.py`, `overrides/`, and `tools/` | Updated when the project has not edited the file; a local edit is kept for review |
| **Shared** | `zensical.toml`, requirements files, `.gitignore`, and `README.md` | Merged by setting or delegated to the command that owns that content |
| **Excluded** | Template changelog, contributor files, issue templates, and the template's sample regression suite | Not delivered to generated projects |

For shared files, the merge is deliberately narrow. Template extension and
PDF settings can arrive in `zensical.toml`, but project content such as the
author's PDF copyright is not replaced. Dependency versions are left to
`prodockit pins`; repository badges are left to `prodockit sync-repo`.

## Keep the project current

A generated project does not change when the source template changes. Check
periodically and before a final publication:

```bash
prodockit template-sync
```

This first run is a report. If an update is useful, the
[template-sync guide](devcons/template-sync.md) explains how to apply it on a
branch, compare `.new` sidecars for files you edited, build both outputs, and
publish through the normal review gate.

The template version you started from is not a prodockit package version.
Template releases describe starter files; prodockit releases describe the
installed extensions and commands. The two can move independently.
