---
icon: lucide/package-plus
---

{{ heading_counter_reset(page) }}

# Add prodockit to an existing document

`prodockit adopt` is for an existing Zensical document whose normal working
environment is already established. It adds prodockit's authoring
extensions and their website styles without turning the project into a copy
of prodockit-template.

Use [machine bootstrap](devcons/bootstrap.md) for a new computer or a new
repository. Adoption assumes that Git, SSH and the editor you prefer already
work. It does not configure or change any of them.

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

- A `prodockit>=...` floor to the site's existing requirements file. It uses
    `requirements.txt`, `requirements/docs.txt` or `docs/requirements.txt`, in
    that order, and creates `requirements.txt` when none exists.
- The standard prodockit Markdown extensions to the existing
    `zensical.toml`, `zensical.yml` or `zensical.yaml`.
- `docs/stylesheets/pdk.css`, loaded before any project stylesheet so
    the project's own rules can override it.
- `.prodockit-components.toml`, recording whether this project selected
    Mermaid diagrams or mathematical notation.

Mermaid and mathematics are independent options and are off by default. A
document using neither does not need Node.js, MathJax, Mermaid CLI or a browser
renderer.

When either option is selected, adoption writes the component's `package.json`
and `package-lock.json` before installing it. The lockfile records the tested
dependency set, while npm's download cache makes later reinstalls quicker. If
the project already has an author-maintained Node manifest, adoption leaves it
unchanged and uses its existing lockfile when one is present.

The command never commits, pushes, changes a remote, or writes editor settings.

Adoption is not a whole-machine PDF installer. Selecting Mermaid or
mathematics installs those project-local Node renderers, but Pandoc,
WeasyPrint, its native Pango libraries, and document fonts remain part of the
existing working environment. Follow the adoption row under
[Prepare the PDF tools](pdf.md#pdf-requirements) before building a PDF.

## Review the existing project

Start with a read-only assessment from the project's own virtual environment.
The following steps establish that context before asking prodockit what it
would change.

/// steps

//// step | Change to the repository directory

Use the directory containing the project's `zensical.toml` or Zensical YAML
file (`zensical.yml` or `zensical.yaml`):

```bash
cd /path/to/your-document
```

////

//// step | Activate the project's virtual environment

=== "macOS and Ubuntu"

    ```bash
    source .venv/bin/activate
    ```

=== "Windows PowerShell"

    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

This is deliberately a separate step from changing directory. Seeing the
environment name at the start of the prompt confirms which Python installation
will receive the package and run the build.

////

//// step | Install or update prodockit

=== "macOS"

    ```bash
    pip3 install --upgrade prodockit
    ```

=== "Ubuntu"

    ```bash
    python -m pip install --upgrade prodockit
    ```

=== "Windows PowerShell"

    ```powershell
    python -m pip install --upgrade prodockit
    ```

Confirm that the command comes from the active project environment:

```bash
prodockit --version
```

Adoption later records a `prodockit>=...` floor in the project's requirements
file. This installation step makes the command available for the first run.

////

//// step | Ask for an assessment

```bash
prodockit adopt
```

The report is read-only. It groups the work into phases and gives every change
its own stage, using the same presentation as `prodockit bootstrap`. It also says explicitly
that Git, SSH, remotes and editors are outside its scope.

////

///

## Choose optional renderers

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

## Preview and apply

Preview the complete plan before allowing any file or package change, then
build the result yourself so the review remains under your control.

/// steps

//// step | Preview every selected stage

```bash
prodockit adopt --dry-run
```

No files or packages are changed. Add `--verbose` to see the files and commands
behind the concise descriptions.

////

//// step | Apply the reviewed stages

```bash
prodockit adopt --apply
```

The command asks before each stage that writes files or installs an optional
renderer. Routine npm output is captured; a failure is reported with its own
error rather than leaving an apparently successful stage. After npm completes,
Adoption runs `mmdc --version`; an incomplete Mermaid extraction therefore
keeps both the renderer stage and Ready stage incomplete.

If Mermaid or mathematics is selected, its Node packages are installed below
`tools/`. These are project-local dependencies, not global software shared
with unrelated documents.

////

//// step | Build the website

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

## Run it again safely

The stages are idempotent: a satisfied stage is reported as `ok` and left
alone. If an installation is interrupted, run the same command again:

```bash
prodockit adopt --apply
```

It reassesses the files and continues with stages that still need work. It does
not overwrite an existing project stylesheet or remove existing Zensical
configuration.
