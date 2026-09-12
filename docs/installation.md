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

## Understand the project structure {: #installation-project-structure }

The installation route changes what is stored in a site's project directory.
It helps to recognise the starting structure before choosing a route or
reviewing changes made by Prodockit.

### A clean Zensical site

Running `zensical new .` in an empty project directory creates a small,
working site. Its Markdown pages live under `docs/`, `zensical.toml` controls
the site, and the supplied GitHub workflow can publish it. The project's
virtual environment, `.venv`, is local working state and is not committed to
Git, so it is not shown in the tree.

/// tree
.github/ - GitHub repository configuration
  workflows/ - automated workflows
    docs.yml - Zensical's GitHub Pages workflow
docs/ - Markdown source pages
  index.md - starter home page
  markdown.md - starter Markdown example
zensical.toml - Zensical project configuration
///

This is a complete Zensical starting point. Build and preview it successfully
before adding Prodockit so that any earlier environment or Zensical problem is
kept separate from the adoption work.

### The site after adding Prodockit {: #installation-adopted-structure }

`pdk adopt --apply` retains the Zensical pages and workflow, then adds the
selected Prodockit components and records their supported toolchain. It also
updates `zensical.toml` to enable the standard authoring extensions and load
the website and PDF stylesheets in their intended override order.

/// tree
.github/ - original GitHub repository configuration
  workflows/
    docs.yml - original Zensical workflow
docs/ - original Markdown source pages and Prodockit assets
  javascripts/ - Prodockit and project website behaviour
    pdk.js - managed Prodockit website behaviour
    mathjax.js - generated Prodockit configuration when maths is selected
    vendor/
      mathjax/
        tex-svg-full.js - vendor MathJax browser bundle
        LICENSE - vendor licence supplied with MathJax
    extra.js - USER-MANAGED website behaviour
  stylesheets/
    pdk.css - managed Prodockit website and component styles
    extra.css - USER-MANAGED website overrides
    pdk-pdf.css - managed Prodockit PDF styles
    print.css - USER-MANAGED PDF-only overrides
  index.md - original starter home page
  markdown.md - original starter Markdown example
.prodockit-components.toml - optional component choices added by Adopt
.prodockit-toolchain.toml - supported tool versions added by Adopt
.python-version - supported Python release added by Adopt
requirements.txt - supported Python packages added by Adopt
zensical.toml - original configuration updated by Adopt
///

For the website, `zensical.toml` loads `pdk.css` first and `extra.css` last, so
your rules can override the managed defaults. PDF generation continues the
cascade with `pdk-pdf.css` followed by `print.css`. Adopt creates a missing
user-managed stylesheet, but never replaces one you have edited.

Adopt installs managed `pdk.js` before the empty user-managed `extra.js`.
When mathematical notation is selected, its generated configuration and vendor
bundle are loaded between those two files. The MathJax licence is retained
beside the vendored bundle.

These are the principal files in the clean-site route, not an exhaustive list
of everything a mature project may contain. Adopt preserves existing content
and project-owned configuration.

### A site created from prodockit-template {: #installation-template-structure }

The maintained template starts with Prodockit's publishing, authoring, and
rendering structure already connected. It contains more files than a clean
Zensical site because Bootstrap is preparing a complete working project rather
than adding selected components to an existing one.

/// tree
docs/ - content and appearance
  index.md - report cover
  1-originality.md - originality and AI-use statement
  2-executive-summary.md - starter executive summary
  3-requirements.md - requirements section
  4-solution-architecture.md - solution architecture section
  5-goverance.md - governance section
  6-operations.md - operations section
  7-examples.md - extension examples
  acronyms.md - acronym list
  glossary.md - glossary
  bibliography.md - generated bibliography page
  references.md - formatted reference list
  assets/ - cover, branding, and report images
  javascripts/ - Prodockit and project website behaviour
    pdk.js - managed Prodockit website behaviour
    mathjax.js - generated Prodockit MathJax configuration
    vendor/
      mathjax/
        tex-svg-full.js - vendor MathJax browser bundle
        LICENSE - vendor licence supplied with MathJax
    extra.js - USER-MANAGED website behaviour
  stylesheets/ - website and PDF presentation
    pdk.css - managed Prodockit website and component styles
    template.css - template-specific website presentation
    extra.css - USER-MANAGED website overrides
    pdk-pdf.css - managed Prodockit PDF styles
    print.css - USER-MANAGED PDF-only overrides
zensical.toml - site, navigation, extensions, and PDF settings
requirements.txt - Python build dependencies
.python-version - supported project Python
.prodockit-shared-files.toml - managed shared-file checksums
.gitignore - generated and local files excluded from Git
README.md - project summary and publishing badges
bibliography.bib - example bibliography source
references.bib - example hand-written reference source
tools/ - pinned Mermaid and MathJax Node tooling
overrides/ - Zensical theme customisations
macros.py - shared template macros
.github/ - GitHub repository configuration
  workflows/ - GitHub Actions workflows
    docs.yml - GitHub Pages build and deployment
    release-redeploy.yml - rebuild after a template release
.gitlab-ci.yml - GitLab Pages build and deployment
///

This is the useful project-facing structure rather than every file in the
template repository. The template manifest is the authoritative record of
which files Template Sync manages, shares with the project, leaves to the
author, or excludes.

In a template site, `template.css` sits between `pdk.css` and `extra.css` in
the website cascade. PDF generation then adds `pdk-pdf.css` and finally the
user-managed `print.css`.

## Continue with an installation route

The shared preparation is complete. Choose the card that matches what you are
starting with; each route takes over from the parent repositories directory
and explains when to enter or create the project itself.

<div class="grid cards installation-route-grid" markdown>

-   :lucide-rocket:{ .lg .middle } __Adopt prodockit__

    ---

    Start with an empty directory, create and test a Zensical site, then use
    Adoption to add the Prodockit features you select.

    [:octicons-arrow-right-24: Open section 4](getting-started.md){ .md-button .md-button--primary .installation-route-button }

-   :lucide-rocket:{ .lg .middle } __Build a template site__

    ---

    Let Bootstrap prepare the machine, repository, build tools, and maintained
    `prodockit-template` as one recoverable process.

    [:octicons-arrow-right-24: Open section 5](devcons/bootstrap.md){ .md-button .md-button--primary .installation-route-button }

-   :lucide-book-open:{ .lg .middle } __Build site manually__

    ---

    Perform and verify the machine, repository, editor, renderer, and project
    setup yourself instead of asking Bootstrap or Adoption to orchestrate it.

    [:octicons-arrow-right-24: Open section 6](manual-install.md){ .md-button .md-button--primary .installation-route-button }

</div>
