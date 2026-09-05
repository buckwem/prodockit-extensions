---
icon: lucide/package-plus
---

{{ heading_counter_reset(page) }}

# Installation preparation

Every installation route needs the same supported Python release and an active
virtual environment.\index{virtual environment} Prepare those once in section
3.1, then continue with the
route that matches the work: [adoption](adopt.md) for an established document,
[bootstrap](devcons/bootstrap.md) for a new machine and template project,
[prodockit-template](prodockit-template.md) for the supplied project structure,
or the [first-site walkthrough](getting-started.md) for an empty directory.

The remainder of this chapter is the manual setup route. Use it when you want
to choose and install the package, external tools, and enabled extensions
directly. Bootstrap is not a general installer for an unrelated Zensical
project.

## Prepare Python and its environment {: #installation-preparation }

Python must exist before it can create the environment that runs Prodockit.
The environment keeps the documentation toolchain separate from system Python
and avoids the `externally-managed-environment` error produced by package-
managed Python installations under PEP 668.

Choose the directory appropriate to the route you will follow: the existing
repository for adoption, a parent working directory for bootstrap, the
template repository for direct template use, or the empty project directory
for the first-site walkthrough. The examples call it `your-project`; substitute
the real path throughout.

/// steps

//// step | Install Python 3.14

Install and verify the supported interpreter before creating an environment.

=== ":material-apple: macOS"

    Install [Homebrew](https://brew.sh) if needed, then run:

    ```bash
    brew install python@3.14
    "$(brew --prefix python@3.14)/bin/python3.14" --version
    ```

=== ":fontawesome-brands-windows: Windows"

    Install the 64-bit Python 3.14 release from
    [python.org](https://www.python.org/downloads/). Select **Add python.exe to
    PATH** and **Disable path length limit** in the installer, then open a new
    PowerShell window and run:

    ```powershell
    py -3.14 --version
    ```

    If `python` opens the Microsoft Store, disable its `python.exe` and
    `python3.exe` App Installer aliases.

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    sudo apt update
    sudo apt install python3.14 python3.14-venv python3-pip
    python3.14 --version
    ```

Every check must report Python 3.14 before you continue.

////

//// step | Create the virtual environment

Change to the directory selected for your route and create `.venv` there.

=== ":material-apple: macOS"

    ```bash
    cd /path/to/your-project
    "$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    cd C:\path\to\your-project
    py -3.14 -m venv .venv
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    cd /path/to/your-project
    python3.14 -m venv .venv
    ```

Creating the environment does not activate it or change system Python.

////

//// step | Activate the environment

<span id="installation-reactivate"></span>

Activate `.venv` in every new terminal before installing or running the
documentation tools.

=== ":material-apple: macOS"

    ```bash
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

    The policy applies to the current account and may ask for confirmation.
    To leave it unchanged, use classic **CMD** and run
    `.\.venv\Scripts\activate.bat` instead.

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    source .venv/bin/activate
    ```

The shell prompt normally gains a `(.venv)` prefix.

////

//// step | Verify the active environment

Verify both the version and the interpreter selected by the shell.

=== ":material-apple: macOS"

    ```bash
    python --version
    command -v python
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    python --version
    Get-Command python
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    python --version
    command -v python
    ```

The version must report Python 3.14 and the executable path must be inside the
`.venv` directory. If either check points elsewhere, repeat the activation
step before continuing with chapters 4, 5, 6 or 7.

////

///

## From PyPI

Install the current prodockit package into the active project environment:

```bash
pip install prodockit
```

If an installed command appears to use the wrong Python or version, run this
from the project root before reinstalling anything:

```bash
pdk diag
```

The report distinguishes a stale command on `PATH` from a valid virtual
environment, pipx, Conda, system-Python, or CI installation. It also runs the
active interpreter's dependency check and verifies only the renderers required
by the project's configuration. Use `pdk diag --verbose` for paths and version
evidence, or attach `pdk diag --json` when requesting support.

For a minimal project that needs no PDF toolchain, continue with
[Build your first site](getting-started.md). The
[requirements and dependencies](requirements-dependencies.md) chapter records
the external tools that can be added later when the document needs them.

## Enabling an extension

Each prodockit extension is registered as a standard Python-Markdown extension
under the `markdown.extensions` entry point group, so it can be enabled by
name, the same way you'd enable a built-in extension like `toc` or a
`pymdownx` one:

```python
import markdown

html = markdown.markdown(
    text,
    extensions=["prodockit.headings", "prodockit.refs", "prodockit.tables"],
)
```

Or, for a [Zensical](https://zensical.org/) project, in `zensical.toml`
alongside the built-in and `pymdownx` extensions. Unlike `pymdownx`'s and
Zensical's own namespaces, Zensical doesn't hoist a nested
`prodockit.headings` table into that dotted extension name, so each one needs
a quoted key instead:

```toml
[project.markdown_extensions."prodockit.headings"]
[project.markdown_extensions."prodockit.refs"]
[project.markdown_extensions."prodockit.citations"]
[project.markdown_extensions."prodockit.glossary"]
[project.markdown_extensions."prodockit.tables"]
[project.markdown_extensions."prodockit.tree"]
[project.markdown_extensions."prodockit.steps"]
[project.markdown_extensions."prodockit.bibliography"]
[project.markdown_extensions."prodockit.index"]
```

Enable only the ones you use - each is independent, and none of them
requires another.

### The nine extensions {: #installation-the-extensions }

See each extension's own page for its syntax, examples, and configuration:

\ref{tab-installation-the-nine-extensions} maps each Markdown extension to the authoring feature it provides.

| Extension {: width="40%" } | What it adds |
| --- | --- |
| [`prodockit.headings`](extensions/headings.md) | Numbered headings, and a number a cross-reference can point at |
| [`prodockit.refs`](extensions/refs.md) | Cross-references that resolve to a number *and* a name |
| [`prodockit.citations`](extensions/citations.md) | Citation handling |
| [`prodockit.glossary`](extensions/glossary.md) | Acronyms and a glossary |
| [`prodockit.tables`](extensions/tables.md) | Column widths, dense tables, multi-row headers, merged cells, rotated headings |
| [`prodockit.tree`](extensions/tree.md) | A directory listing that looks like one |
| [`prodockit.steps`](extensions/steps.md) | Numbered steps a reader works through in order |
| [`prodockit.bibliography`](extensions/bibliography.md) | A bibliography built from your `.bib` files |
| [`prodockit.index`](extensions/index-terms.md) | A back-of-book index (PDF only) |
/// table-caption | <
    attrs: {id: tab-installation-the-nine-extensions}

The nine extensions
///

### What is *not* an extension {: #installation-not-extensions }

Several parts of prodockit have no `markdown.extensions` entry point and
nothing to add to `zensical.toml`, because they are not Markdown syntax:

\ref{tab-installation-what-is-not-an-extension} distinguishes the standalone commands and integrations from Markdown extensions.

| | |
| --- | --- |
| [`prodockit pdf`](pdf.md) | A separate PDF-generation build step |
| [`prodockit source-bundle`](pdf.md#bundling-source-into-a-pdf) | Packages documentation source as a separate PDF |
| [`prodockit.zensical_macros`](macros.md) | A `define_env()` module for Zensical's macros plugin, named under its `modules` config rather than as an extension |
| [`prodockit.testing`](devcons/testing.md) | pytest fixtures and checks for an already-built site and PDF |
| [`prodockit bootstrap`](devcons/bootstrap.md) | Sets up a machine and a project based on `prodockit-template` |
| [`prodockit sync-repo`](devcons/repo-metadata.md) | Keeps repository metadata and README badges matching the git remote |
| [`prodockit pins`](devcons/pinning-drift.md) | Moves build-input version pins together |
| [`prodockit template-sync`](devcons/template-sync.md) | Brings a project back into step with the template it came from |
| [`prodockit init-tools` / `init-mathjax`](command-line.md#publish-and-verify) | Sets up optional Mermaid and maths rendering tools |
/// table-caption | <
    attrs: {id: tab-installation-what-is-not-an-extension}

What is not an extension
///

Contributors changing the package itself should use the editable installation
and repository checks in
[Development and code map](devcons/development.md#create-a-development-environment).
