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

Section 3.1 is the shared preparation for those routes. Each route then owns
its project directory, project-local environment, Prodockit installation, and
verification rather than repeating that work here.

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
