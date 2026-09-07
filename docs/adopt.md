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
- `docs/stylesheets/pdk.css`, loaded before any project stylesheet so
    the project's own rules can override it.
- `.prodockit-components.toml`, recording whether this project selected
    Mermaid diagrams or mathematical notation.

!!! warning "Existing custom styles can override Prodockit"

    The Zensical theme loads first. Adoption adds Prodockit's managed
    `pdk.css` after it so Prodockit can supply its component features and
    presentation. Your existing `docs/stylesheets/extra.css` is left
    unchanged and loads after `pdk.css`, so its custom rules can override
    Prodockit's rules.

    If an adopted feature does not look or behave as expected, you may need
    to remove or revise a conflicting custom rule. Read [which stylesheets
    Prodockit manages](stylesheets.md#keep-managed-and-author-styles-separate)
    and [the stylesheet cascade order](stylesheets.md#load-the-cascade-in-order)
    before deciding what to change.

Mermaid and mathematics are independent options and are off by default. A
document using neither does not need Node.js, MathJax, Mermaid CLI or a browser
renderer.

When either option is selected, adoption writes the component's `package.json`
and `package-lock.json` before installing it. The lockfile records the tested
dependency set, while npm's download cache makes later reinstalls quicker. If
the project already has an author-maintained Node manifest, adoption leaves it
unchanged and uses its existing lockfile when one is present.

The command never commits, pushes, changes a remote, or writes editor settings.

Adoption installs, upgrades or downgrades the managed Python packages in the
active virtual environment and installs the supported Pandoc executable into
that environment. It does not replace the Python interpreter that is running
it: a different Python minor release blocks the whole stage before packages or
project files are changed, and the report gives the exact Bootstrap or virtual
environment remediation.

Adoption is not a whole-machine native-library installer. WeasyPrint's Pango,
GLib, HarfBuzz and fontconfig libraries, and the document fonts, remain part of
the existing machine setup. Follow the adoption row under [Prepare the PDF
tools](pdf.md#pdf-requirements) before building a PDF.

## Adoption stages

### Phase 1 — Review the existing project

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
    "$(brew --prefix python@3.14)/bin/python3.14" -m venv --clear .venv
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    Set-Location C:\path\to\your-project
    py -3.14 -m venv --clear .venv
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    cd /path/to/your-project
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

//// step | Ask for an assessment

```bash
prodockit adopt
```

The report is read-only. It groups the work into phases and gives every change
its own stage, using the same presentation as `prodockit bootstrap`. It also says explicitly
that Git, SSH, remotes and editors are outside its scope.

\ref{fig-adopt-assessment-output} is a short visual guide to the assessment.
Use [section 28.1, Scan phases and
stages](commands/output.md#command-output-structure) for the complete
explanation of its phases, stages, colours, and default-No decisions:

![A left-aligned terminal report with separate callouts identifying a phase, stage, review-first changes, and warning](assets/diagrams/command-output-anatomy.svg){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-adopt-assessment-output}

Reading an Adopt assessment
///

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

### Phase 2 — Preview and apply

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

```bash
prodockit adopt --apply
```

The command asks before each stage that writes files or installs software. The
toolchain stage says which tools will be installed, upgraded or downgraded,
then verifies their versions before writing the matching declarations. A
failed installation therefore cannot leave the project claiming a combination
that was not reached.

Pip uses its normal wheel cache, five request retries and bounded request
timeouts. Set `PDK_PYPI_MIRROR` to add an institutional Python package mirror.
Pandoc downloads are validated as archives, retained in Prodockit's native
download cache and retried before moving from a configured
`PDK_PANDOC_MIRROR` to the official release source. A rerun reuses any valid
cached download rather than fetching it again.

Routine npm output is captured; a failure is reported with its own error rather
than leaving an apparently successful stage. After npm completes, Adoption
renders a minimal Mermaid diagram through its browser and converts a minimal
expression through MathJax. An incomplete npm extraction or unusable browser
therefore keeps both the renderer stage and Ready stage incomplete.

If Mermaid or mathematics is selected, its Node packages are installed below
`tools/`. These are project-local dependencies, not global software shared
with unrelated documents.

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
retaining a validated Pandoc archive in Prodockit's native download cache. Run
the command from the active project environment:

```bash
PDK_WHEELHOUSE=/path/to/wheels prodockit adopt --apply --offline
```

Offline mode passes `--no-index` to pip and does not silently contact PyPI or a
Pandoc source. If either cache is incomplete, the stage fails clearly and does
not update the declarations.

////

///

### Phase 3 — Build and review

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

## Where to go next {: #adopt-where-to-go-next }

Choose the route that matches the result:

- If setup has not completed or any check fails, use
  [Troubleshooting](troubleshooting-installs.md).
- If setup has completed and `pdk diag` passes, continue with
  [Publish a document](publishing.md).
