# Build your first site

This walkthrough starts with an empty directory and ends with a local Zensical
site using numbered headings and a cross-reference. It also demonstrates
`prodockit.steps`: the procedure you are reading is rendered by that extension.

/// steps

//// step | Install Python

prodockit requires Python 3.10 or later. Install Python for your operating
system, then close and reopen the terminal so the new command is on `PATH`.

=== ":material-apple: macOS"

    Install [Homebrew](https://brew.sh/) first if you do not already have it,
    then run:

    ```bash
    brew update
    brew install python
    python3 --version
    ```

=== ":fontawesome-brands-windows: Windows"

    Open PowerShell and run:

    ```powershell
    winget install --exact --id Python.Python.3.13
    python --version
    ```

    If `python` opens the Microsoft Store, search Windows for **Manage app
    execution aliases** and turn off the App Installer aliases for
    `python.exe` and `python3.exe`.

=== ":material-linux: Linux (Ubuntu)"

    Open a terminal and run:

    ```bash
    sudo apt update
    sudo apt install python3 python3-venv python3-pip
    python3 --version
    ```

////

//// step | Create and activate a virtual environment

Create a directory for the site, then create the environment inside it:

=== ":material-apple: macOS"

    ```bash
    mkdir my-docs
    cd my-docs
    "$(brew --prefix)/bin/python3" -m venv .venv
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    In PowerShell:

    ```powershell
    mkdir my-docs
    cd my-docs
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    mkdir my-docs
    cd my-docs
    python3 -m venv .venv
    source .venv/bin/activate
    ```

The prompt normally starts with `(.venv)` after activation. The rest of the
walkthrough uses `python`, which now means the interpreter inside that virtual
environment on all three platforms.

////

//// step | Install prodockit

```bash
python -m pip install prodockit
```

Zensical is a core dependency, so this installs the `zensical` command too.
Confirm both commands are available:

```bash
prodockit --version
zensical --version
```

////

//// step | Create the Zensical project

```bash
zensical new .
```

This creates `zensical.toml` and a starter `docs/` directory without
overwriting unrelated files.

////

//// step | Enable the two extensions

Add these tables at the end of `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.headings"]
[project.markdown_extensions."prodockit.refs"]
```

The quoted table names matter: each dotted extension name must remain one TOML
key. Extensions are independent, so a project can enable only these two.

////

//// step | Add content that uses them

Replace `docs/index.md` with:

```md
# My first document

The detail is in \ref{results}.

## Method

Describe what you did here.

## Results {: #results }

Describe what you found here.
```

`prodockit.headings` numbers the sections. `prodockit.refs` turns
`\ref{results}` into a link containing the current number and title, so it
stays correct if the sections move.

////

//// step | Preview the site

```bash
zensical serve
```

Open the local address printed in the terminal. Zensical rebuilds the preview
when a source file changes; stop it with `Ctrl+C`.

////

///

## Where to go next

- Browse the [authoring reference](extensions/headings.md) when you need
  another document feature.
- Read [Generate a PDF](pdf.md#pdf-quick-start) when the website is ready to
  print or submit.
- Follow the [project maintenance cycle](project-maintenance.md) when the
  first site becomes a maintained project, then use the
  [command-line map](command-line.md) to choose a command safely.

!!! note "Previewing these documentation changes"
    From this repository's root, run `zensical serve` and open the address it
    prints. This page already has `prodockit.steps` enabled and styled.
