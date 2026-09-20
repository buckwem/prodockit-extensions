---
icon: lucide/package-plus
---

{{ heading_counter_reset(page) }}

# Upgrade existing site

`prodockit adopt` is for an existing Zensical document, whether or not its
Python working environment has already been established. It prepares that
environment with the exact software combination supported by the installed
Prodockit release, then adds Prodockit's authoring extensions and website
styles without turning the project into a copy of prodockit-template. Adoption
assumes that Git, SSH and the editor you prefer already work. It does not
configure or change any of them.

\ref{fig-adoption-workflow} shows the existing project entering the outlined
adoption process. Inside that boundary, prodockit assesses the project, adds
the standard components, and either installs or skips each optional renderer.
The author then builds and reviews the local changes before accepting the
updated project.

![Adoption assesses an existing site, adds standard components, installs only the selected renderers, then leaves the author to build and review](assets/diagrams/3.1-adoption-workflow.png){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-adoption-workflow}

Adopting Prodockit into an existing document
///

## What the command changes

The standard installation adds:

- Exact declarations for Zensical, WeasyPrint, Prodockit, Markdown and PyMdown
    Extensions to the site's existing requirements file. It uses
    `requirements.txt`, `requirements/docs.txt` or `docs/requirements.txt`, in
    that order, and creates `requirements.txt` when none exists. An existing
    operator and extras, such as `prodockit[index]>=...`, are preserved while
    its version is aligned; a missing declaration is added with `==`.
- `.python-version` and `.prodockit-toolchain.toml`. The latter records every
    managed version, including Python and Pandoc, from the same tested-version
    manifest used by `prodockit pins` and `pdk diag`.
- The standard prodockit Markdown extensions to the existing
    `zensical.toml`, `zensical.yml` or `zensical.yaml`.
- Four standard stylesheets: `zensical.toml` records managed `pdk.css`
    followed by user-managed `extra.css` for the website; `pdk-pdf.toml`
    records managed `pdk-pdf.css` followed by user-managed `print.css` for
    the PDF. Existing `project.extra.pdf_*` settings are migrated into that
    PDF policy file.
- Managed `pdk.js` followed by user-managed `extra.js`. When website
    mathematics is selected, the generated MathJax configuration and the
    Zensical-documented browser runtime sit between those two files. Missing
    user-managed files are created, but their existing contents are never
    replaced.
- `.prodockit-components.toml`, recording whether this project selected
    Mermaid diagrams or mathematical notation.
- The configured `harvard-cite-them-right.csl` citation style when it is
    missing. The download is checked as CSL/XML and cached before it is placed
    in the project. Existing and custom style files remain author-owned.

!!! warning "Existing custom styles can override Prodockit"

    The Zensical theme loads first. Adoption adds Prodockit's managed
    `pdk.css` after it so Prodockit can supply its component features and
    presentation. A template site's `template.css` remains next when it is
    already configured. User-managed `extra.css` then has the final website
    override. For PDF output, `pdk-pdf.css` follows the website styles and
    user-managed `print.css` has the final PDF override.

    If an adopted feature does not look or behave as expected, you may need
    to remove or revise a conflicting custom rule. Read [which stylesheets
    Prodockit manages](stylesheets.md#keep-managed-and-author-styles-separate)
    and [the stylesheet cascade order](stylesheets.md#load-the-cascade-in-order)
    before deciding what to change.

Mermaid and mathematics are independent options and are off by default. A
document using neither does not need Node.js, MathJax, Mermaid CLI or a browser
renderer. Without `.prodockit-components.toml`, existing renderer configuration
is used to infer the component choices. Zensical's starter configuration alone
does not select a renderer. Run `pdk adopt --configure` or
use explicit command-line flags to select either renderer. Template projects
ship the component file with both enabled.

When either option is selected, Adoption records that choice and configures the
project without installing its renderer. `pdk pdf` transparently prepares and
verifies the selected project-local runtime on first use. Mermaid is Python-only;
PDF mathematics requires Node.js on `PATH`, installed separately with the
operating-system package manager, but does not require npm.

The command never commits, pushes, changes a remote, or writes editor settings.

For TOML projects, Adoption also reviews new template settings. Unknown options
arrive as commented examples rather than becoming active automatically; branding
and `template.css` are left out. `.prodockit-adopt.toml` records which setting
paths have been reviewed. Delete that file to start a fresh review without
overwriting your existing values. Software and health checks still run normally.
See [Template settings and the review ledger](commands/adopt.md#template-settings-and-the-review-ledger)
for the source, cache, exceptions and reset behaviour.

Adoption installs, upgrades or downgrades the managed Python packages in the
active virtual environment. Pandoc and PDF fonts are prepared separately in
the project cache by `pdk pdf`. Adoption does not replace the Python interpreter that is running
it: a different Python minor release blocks the whole stage before packages or
project files are changed, and the report gives the exact Bootstrap or virtual
environment remediation.

Adoption is not a whole-machine native-library installer. On macOS and Ubuntu,
WeasyPrint's Pango, GLib, HarfBuzz and fontconfig libraries remain part of the
existing machine setup. Windows x64 instead uses the standalone project cache
owned by `pdk pdf`; Pandoc and document fonts are project-local on every supported host. Follow the
adoption row under [Prepare the PDF tools](pdf.md#pdf-requirements).

## Adoption stages

Three stages assess the existing project, apply the reviewed integration, and
verify the resulting website and local changes.

### Stage 1 — Review the existing project

Start with the shared Python preparation, then move into the existing project
and assess it before making any changes.

/// steps

//// step | Prepare Python and the setup environment

Complete section 3.1 in the parent directory that holds your repositories:

[Open section 3.1 to prepare your environment](installation.md#installation-preparation){ .md-button .md-button--primary target="_blank" rel="noopener" }

Return here with that setup environment active. The next step enters the
existing project and establishes its separate project environment.

////

//// step | Enter the project and prepare its environment

Change into the directory containing the existing project's `zensical.toml`,
`zensical.yml` or `zensical.yaml`. If the prompt already shows `(.venv)`, run
`deactivate` first so that the parent setup environment is not mistaken for
the project environment.

If this project already has a `.venv`, activate it and run `python --version`.
Keep it when it reports Python 3.14. If `.venv` is missing, uses another Python
release, or is damaged, deactivate it if necessary and recreate it with the
command for your platform:

=== ":material-apple: macOS"

    ```bash
    cd /path/to/your-project
    ```

    ```bash
    "$(brew --prefix python@3.14)/bin/python3.14" -m venv --clear .venv
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    Set-Location C:\path\to\your-project
    ```

    ```powershell
    py -3.14 -m venv --clear .venv
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    cd /path/to/your-project
    ```

    ```bash
    python3.14 -m venv --clear .venv
    source .venv/bin/activate
    ```

Verify that `python --version` reports Python 3.14 and that the command path is
inside this project's `.venv` before installing anything.

////

//// step | Install or update prodockit

=== ":material-apple: macOS"

    ```bash
    pip3 install --upgrade pip
    pip3 install --upgrade prodockit
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    pip install --upgrade pip
    pip install --upgrade prodockit
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    pip install --upgrade pip
    pip install --upgrade prodockit
    ```

!!! note "If pip or pip3 does not work"

    If `pip` does not work, try `pip3`; if `pip3` does not work, try `pip`.
    Keep the intended virtual environment active and check that the alternative
    command belongs to it before installing packages.

Confirm that the command comes from the active project environment:

```bash
prodockit --version
```

Adoption later aligns Prodockit and the other managed versions with the
combination supported by this installed command. This installation step makes
the command available for the first run.

////

//// step | Choose optional renderers

Keep working in the project directory with its `.venv` active and with
`python --version` reporting Python 3.14.

Choose Mermaid and mathematics only when the existing document uses them. Run:

```bash
prodockit adopt --configure
```

The command asks two separate questions:

```text
Does this document contain Mermaid diagrams? [y/N]:
Does this document contain mathematical notation? [y/N]:
```

Choose Mermaid only when the source contains `mermaid` fenced blocks. Choose
mathematics only when the document uses TeX notation that MathJax must render.
Selecting one does not select the other.

The answers are saved in `.prodockit-components.toml`, which should be
committed with the document so another contributor gets the same components.

Command-line flags can select them explicitly for a run:

```bash
prodockit adopt --mermaid --no-maths --dry-run
prodockit adopt --no-mermaid --maths --dry-run
```

////

///

### Stage 2 — Preview and apply

Preview the complete plan before allowing any file or package change. Keep the
project's `.venv` active throughout these steps.

/// steps

//// step | Preview every selected stage

```bash
prodockit adopt --dry-run
```

No files or packages are changed. The supported-toolchain stage always lists
its affected files and exact commands. Add `--verbose` to expose the equivalent
detail for the other stages.

////

//// step | Apply the reviewed stages

\ref{fig-adopt-assessment-output} explains the coloured messages to look for
when reviewing each proposed change. Read [the command-output guide](commands/output.md#command-output-structure)
for more about phases, activities, colours, and default-No decisions.

![A terminal report with callouts identifying phases, activities, proposed changes, and warnings](assets/diagrams/command-output-anatomy.svg){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-adopt-assessment-output}

Reading an Adopt assessment
///

```bash
prodockit adopt --apply
```

The command asks before each stage that writes files or installs software. The
toolchain stage says which Python packages will be installed, upgraded or
downgraded, then verifies their versions before writing matching declarations.
A failed installation therefore cannot leave the project claiming a
combination that was not reached.

Pip uses its normal wheel cache, five request retries and bounded request
timeouts. Set `PDK_PYPI_MIRROR` to add an institutional Python package mirror.
The supported Cite Them Right Harvard style follows a cache-first rule and is
written only after its XML and CSL structure have been validated. In offline
mode, the report names the exact cache path and canonical URL when no validated
copy is available.

Adoption records selected PDF components without installing them. Its final
diagnostics report a clean missing project cache as deferred until first use.
`pdk pdf` then downloads, verifies and activates only the runtimes the document
needs; `pdk pdf --prepare COMPONENT` remains available when preparation must be
forced before a build. Missing Node or macOS/Linux WeasyPrint libraries remain
separate, actionable host prerequisites.

////

//// step | Refresh the project environment

After Apply completes, follow the highlighted environment instructions
**before running diagnostics or building**. This loads any new tool and PDF
library paths; it does not recreate the environment.

=== ":material-apple: macOS"

    In the same terminal, from the project directory:

    ```bash
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    If Adopt displays its restart banner, fully close Windows Terminal or
    VS Code, then reopen it. Open PowerShell in the project directory and run:

    ```powershell
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    Keep the project environment active. After opening a new terminal, return
    to the project directory and run:

    ```bash
    source .venv/bin/activate
    ```

Use the activation path printed by Adopt if you use a differently named
environment. Then verify the project:

```bash
pdk diag
```

Resolve any failures before proceeding to the build stage.

////

//// step | Resume an interrupted installation

!!! info "Skip this step when Apply completed successfully"

    Use this step only if installation was interrupted or you are continuing
    in a new terminal.

Change to the project directory and reactivate its environment:

=== ":material-apple: macOS"

    ```bash
    cd /path/to/your-document
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    cd C:\path\to\your-document
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    cd /path/to/your-document
    source .venv/bin/activate
    ```

Confirm that `python --version` still reports Python 3.14, then run the same
command again:

```bash
python --version
prodockit adopt --apply
```

The stages are idempotent: a satisfied stage is reported as `ok` and left
alone. Adoption reassesses installed versions and files, reuses valid caches,
and continues with stages that still need work. It does not remove unrelated
requirements or existing Zensical configuration.

////

//// step | Work from prepared caches when offline

Use offline mode only after putting the exact Python wheels in a directory and
retaining any validated template snapshot or citation style the project needs.
Run the command from the active project environment:

```bash
PDK_WHEELHOUSE=/path/to/wheels prodockit adopt --apply --offline
```

Offline mode passes `--no-index` to pip and does not silently contact PyPI.
PDF runtime acquisition belongs to `pdk pdf`, not Adopt; a later PDF build
reports its own acquisition failure without changing the completed adoption.

////

///

### Stage 3 — Build and review

Build the actual document, then inspect the resulting project changes before
accepting them into the repository.

/// steps

//// step | Build the website

Keep the project's `.venv` active so the build uses the supported Zensical and
Prodockit versions installed by adoption.

=== "zensical.toml"

    ```bash
    zensical build --clean --strict
    ```

=== "zensical.yml"

    ```bash
    zensical build -f zensical.yml --clean --strict
    ```

=== "zensical.yaml"

    ```bash
    zensical build -f zensical.yaml --clean --strict
    ```

This uses the document's actual pages and configuration, so it remains the
final proof that the adopted components work with the existing project. The
YAML filenames are supported inputs, but Zensical requires them to be supplied
explicitly with `-f`; only `zensical.toml` is discovered automatically.

////

//// step | Review the local changes

```bash
git diff
git status --short
```

Commit and publish them through the repository's normal professional workflow.
Adoption deliberately stops before either action.

////

///

## Understand the completed project {: #adopt-completed-project }

This section separates the established project choices retained by Adoption
from the files and versions Prodockit can maintain later.

### Know what becomes yours {: #adopt-project-ownership }

Adoption integrates Prodockit into the existing site without replacing its
identity. The [adopted project
tree](installation.md#installation-adopted-structure) identifies the
principal files the route adds, but an established project may contain many
more author-owned pages, assets, extensions, and workflow files.

Prodockit maintains its standard stylesheets, JavaScript, supported-toolchain
record, and selected renderer configuration. Existing content, Git history,
remotes, publishing workflow, custom styles, and custom JavaScript remain
under author control, as shown in the reviewed diff.

Adoption neither creates nor removes a template relationship. If the existing
project already has valid Template Sync metadata, continue maintaining that
relationship separately; otherwise `pdk template-sync` does not apply.

### Keep the project current {: #adopt-project-maintenance }

Follow this sequence inside the active project environment:

1. Use the platform-specific command earlier in this section to upgrade
   Prodockit.
2. Ask Adopt to compare the existing project with the newly supported
   combination:

   ```bash
   pdk adopt --dry-run
   ```

   Review the proposed files and activities. If work is selected, apply it:

   ```bash
   pdk adopt --apply
   ```

3. Run Diagnostics as the final integration check:

   ```bash
   pdk diag
   ```

Continue only when the required checks pass. Then rebuild the site and PDF.
Use `git diff` and `git status --short` before committing because an existing
project can contain deliberate configuration and design choices that automated
checks cannot judge.

## Where to go next {: #adopt-where-to-go-next }

Choose the route that matches the result:

- If setup has not completed or any check fails, use
  [Troubleshooting](troubleshooting-installs.md).
- If setup has completed and `pdk diag` passes, continue with
  [Publish a document](publishing.md).
