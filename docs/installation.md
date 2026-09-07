---
icon: lucide/package-plus
---

{{ heading_counter_reset(page) }}

# Prepare to install

Every installation route begins in the parent directory where you keep your
repositories and needs the same supported Python release. Prepare Python and a
setup virtual environment\index{virtual environment} there in section 3.1,
then continue with the route that matches the work:
[adoption](adopt.md) for an established document,
[bootstrap](devcons/bootstrap.md) for a new machine and template project,
[the template-project guide](devcons/bootstrap.md#bootstrap-template) for the supplied project structure,
or the [first-site walkthrough](getting-started.md) for an empty directory.

The remainder of this chapter is the manual setup route. Use it when you want
to choose and install the package, external tools, and enabled extensions
directly. Bootstrap is not a general installer for an unrelated Zensical
project.

## Prepare Python and its environment {: #installation-preparation }

Python must exist before it can create the environment that runs Prodockit.
Always complete this section in the directory that holds all your repositories,
for example `~/repos`, `~/github`, `~/gitlab`, or
`C:\Users\your-name\github`. Do not enter an individual project yet.

The setup `.venv` keeps the initial tools separate from system Python and
avoids the `externally-managed-environment` error produced by package-managed
Python installations under PEP 668. Bootstrap uses this setup environment to
create or prepare a project. Adoption and the first-site walkthrough later
enter their project directory and create or replace that project's own
`.venv`; those important transitions are shown in their own steps rather than
hidden here.

/// steps

//// step | Install Python 3.14

Install and verify the supported interpreter before creating an environment.

=== ":material-apple: macOS"

    If Homebrew is not installed, use its official installer. Follow every
    post-install instruction it prints so that `brew` is added to your shell.

    [:simple-homebrew: Install Homebrew](https://brew.sh/){ .md-button .homebrew-button target="_blank" rel="noopener" }

    **After Homebrew finishes installing, close Terminal completely and reopen
    it. The current terminal will not know about the new `brew` command.**

    In the reopened terminal, check that Homebrew is available:

    ```bash
    brew --version
    ```

    Install and verify Python 3.14:

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

First choose the parent directory that will hold your Git repositories. Keeping
projects under one parent gives Bootstrap a predictable place to create a new
project and makes it clear that this first `.venv` is a setup environment, not
the environment belonging to one particular site.

!!! tip "Create a repositories directory if this is your first one"

    If you have not worked with a Git repository before, create one top-level
    directory for all your repositories. `repos` is a neutral name; `gitlab`
    or `github` can be useful when you prefer to group projects by host. Keep
    using an existing repositories directory if you already have one, and
    replace `repos` in the examples with its name. Lowercase names are quicker
    to type. After creating the directory, type the first few characters of
    its name and press ++tab++ to let the terminal complete the rest.

Create or enter the repositories directory:

=== ":material-apple: macOS"

    ```bash
    mkdir -p ~/repos
    cd ~/repos
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    New-Item -ItemType Directory -Force ~\repos | Out-Null
    Set-Location ~\repos
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    mkdir -p ~/repos
    cd ~/repos
    ```

Next create the setup virtual environment in that directory. Python stores it
in a folder named `.venv` alongside, rather than inside, the individual
repository folders that will be created later.

=== ":material-apple: macOS"

    ```bash
    "$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    py -3.14 -m venv .venv
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
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
parent repositories directory's `.venv`. If either check points elsewhere,
repeat the activation step. The route you follow next will say when to keep
using this setup environment and when to create or activate a project-local
one.

////

///

### Restart the terminal after Windows installation {: #installation-windows-restart }

Use this Windows-only recovery step when an installer changes the terminal environment.

=== ":fontawesome-brands-windows: Windows"

    After Bootstrap or an installer changes Windows settings, fully close the
    terminal application (Windows Terminal or VS Code), then reopen PowerShell.
    A new tab or reactivating the virtual environment alone may retain old settings.
    Bootstrap displays this amber message; Template Sync displays it if its
    environment refresh cannot recover the required commands:

    <pre style="color: #E69F00; background: #181818; padding: 1em; white-space: pre-wrap;">============================================================
    RESTART YOUR TERMINAL — WINDOWS SETTINGS HAVE CHANGED
    ============================================================
    Fully close Windows Terminal or VS Code, then reopen it.
    Open PowerShell in your project directory:
    C:\path\to\your-project
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    pdk diag
    ============================================================</pre>

    The project path above is replaced with your actual path. If Template Sync
    cannot continue, the banner also says: `Template Sync cannot continue in this terminal.`

    In the reopened PowerShell, change to your project and check the environment:

    ```powershell
    cd C:\path\to\your-project
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    pdk diag
    ```

    Continue when the required checks pass. If commands are still missing, use
    the diagnostic report to investigate installation before reinstalling tools.

## From PyPI

Install the current prodockit package into the active project environment:

=== ":material-apple: macOS"

    ```bash
    pip3 install prodockit
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    pip install prodockit
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    pip install prodockit
    ```

!!! note "If pip or pip3 does not work"

    If `pip` does not work, try `pip3`; if `pip3` does not work, try `pip`.
    Keep the intended virtual environment active and check that the alternative
    command belongs to it before installing packages.

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
| [`prodockit init-tools`](commands/init-tools.md) / [`init-mathjax`](commands/init-mathjax.md) | Sets up optional Mermaid and maths rendering tools |
/// table-caption | <
    attrs: {id: tab-installation-what-is-not-an-extension}

What is not an extension
///

Contributors changing the package itself should use the editable installation
and repository checks in
[Development and code map](devcons/development.md#create-a-development-environment).
