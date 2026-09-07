---
icon: lucide/rocket
---

{{ heading_counter_reset(page) }}

# Build your first site

Use this route when you do not yet have a Zensical site and want to create one
cleanly before adding Prodockit. It is independent of section 5's template-site
route: Bootstrap creates a repository from `prodockit-template`, whereas this
walkthrough starts with an empty directory, proves that Zensical works on its
own, and then uses Adopt to integrate Prodockit without manual configuration.

/// steps

//// step | Prepare Python and the setup environment

Complete section 3.1 in the parent directory that holds your repositories:

[Open section 3.1: Prepare Python and its environment](installation.md#installation-preparation){ .md-button .md-button--primary target="_blank" rel="noopener" }

Return here with that setup environment active. The next step enters the new
site directory and creates a separate `.venv` for the site before Zensical is
installed.

////

<span id="prepare-the-empty-project-directory"></span>

//// step | Prepare the empty project directory

Leave the parent setup environment, create and enter the site directory, then
create its project-local virtual environment. Use the same repositories path
you selected in section 3.1. The examples call the site `prodockit-project`;
replace that name if required.

=== ":material-apple: macOS"

    ```bash
    deactivate
    cd /path/to/your-repositories
    mkdir -p prodockit-project
    cd prodockit-project
    "$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    deactivate
    Set-Location C:\path\to\your-repositories
    New-Item -ItemType Directory -Force .\prodockit-project | Out-Null
    Set-Location .\prodockit-project
    py -3.14 -m venv .venv
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    deactivate
    cd /path/to/your-repositories
    mkdir -p prodockit-project
    cd prodockit-project
    python3.14 -m venv .venv
    source .venv/bin/activate
    ```

This is the handoff from the shared setup environment to the new site's own
environment. Verify it before installing Zensical:

=== ":material-apple: macOS"

    ```bash
    pwd
    python --version
    python -c 'import sys; print(sys.prefix)'
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    Get-Location
    python --version
    python -c "import sys; print(sys.prefix)"
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    pwd
    python --version
    python -c 'import sys; print(sys.prefix)'
    ```

The first path must be the new project directory, Python must be 3.14, and the
last path must end in `prodockit-project/.venv`. A parent path such as
`~/Repos/.venv` is the Bootstrap setup environment and is not this site's
environment. Correct the directory and repeat section 3.1 before installing
Zensical.

////

//// step | Install Zensical

Follow Zensical's official [installation
guide](https://zensical.org/docs/get-started/) and install it into the active
project environment.

=== ":material-apple: macOS"

    ```bash
    pip3 install --upgrade zensical
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    pip install --upgrade zensical
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    pip install --upgrade zensical
    ```

!!! note "If pip or pip3 does not work"

    If `pip` does not work, try `pip3`; if `pip3` does not work, try `pip`.
    Keep the intended virtual environment active and check that the alternative
    command belongs to it before installing packages.

Confirm that Zensical is available before creating any files:

```bash
zensical --version
```

////

//// step | Create the Zensical site

Follow Zensical's official [Create your site
guide](https://zensical.org/docs/create-your-site/) from the empty project
directory:

```bash
zensical new .
```

This creates the plain Zensical structure shown below:

/// tree
.github/
  workflows/
    docs.yml - Zensical's GitHub Pages workflow
docs/
  index.md - starter home page
  markdown.md - starter Markdown example
zensical.toml - Zensical project configuration
///

////

//// step | Build the plain Zensical site

Build the complete static site from `zensical.toml` and the Markdown files in
`docs/`:

```bash
zensical build --clean --strict
```

`--clean` removes output left by an earlier build. `--strict` makes a warning
fail the command instead of allowing an uncertain result to continue. A
successful build proves that Zensical can read the configuration and source
and produce the deployable site files; it does not start a web server.

////

//// step | Preview the plain Zensical site

Start Zensical's local development server:

```bash
zensical serve
```

Open the local address printed in the terminal and confirm that the starter
site appears. While the server is running, Zensical watches the source and
rebuilds the preview after a change. Stop it with `Ctrl+C`.

Do not continue until both checks succeed. Any problem at this point belongs
to the Python environment or the plain Zensical site, not Prodockit.

////

//// step | Install Prodockit

Install Prodockit into the same active project environment. This makes the
`pdk` command available; it does not yet change the Zensical project.

=== ":material-apple: macOS"

    ```bash
    pip3 install --upgrade prodockit
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    pip install --upgrade prodockit
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    pip install --upgrade prodockit
    ```

!!! note "If pip or pip3 does not work"

    If `pip` does not work, try `pip3`; if `pip3` does not work, try `pip`.
    Keep the intended virtual environment active and check that the alternative
    command belongs to it before installing packages.

Confirm that the command is available from the active environment:

```bash
pdk --version
```

////

//// step | Adopt the Zensical site

Preview the integration stages before allowing Adopt to install the supported
project toolchain and configure the standard authoring components and shared
website styles:

```bash
pdk adopt --dry-run
pdk adopt --apply
```

Read each stage before accepting it. For this first site, leave Mermaid and
maths off unless you intend to use them. Adopt does not configure Git, SSH,
remotes, editors, commits, or publishing.

After Adopt, the project retains the Zensical files and adds the Prodockit
project files shown below. The descriptions identify the additions; Adopt also
updates `zensical.toml` to enable the standard components and load the shared
stylesheet.

/// tree
.github/
  workflows/
    docs.yml - original Zensical workflow
docs/
  stylesheets/
    pdk.css - shared Prodockit website styles added by Adopt
  index.md - original starter home page
  markdown.md - original starter Markdown example
.prodockit-components.toml - optional component choices added by Adopt
.prodockit-toolchain.toml - supported tool versions added by Adopt
.python-version - supported Python release added by Adopt
requirements.txt - supported Python packages added by Adopt
zensical.toml - original configuration updated by Adopt
///

////

//// step | Review and configure `zensical.toml`

`zensical.toml` is the single project configuration used by the website and
Prodockit's PDF commands. Adopt keeps Zensical's existing `[project]` settings,
adds the standard `project.markdown_extensions` tables, and adds
`"stylesheets/pdk.css"` to `project.extra_css`.

In the existing `[project]` table, give the site its real name and make the
page order explicit. Do not add a second `[project]` table, and retain the
extension and stylesheet settings written by Adopt:

```toml
[project]
site_name = "My first document"
nav = [
  {"Home" = "index.md"},
]
```

The `nav` order controls both the website navigation and the page order in the
rendered PDF. Add or extend `[project.extra]` to make the two generated artifact
paths explicit:

```toml
[project.extra]
pdf_output = "docs/site_documentation.pdf"
pdf_source_bundle_output = "docs/source_bundle.pdf"
```

These are the default locations, but recording them here makes the download
filenames visible to the next steps. Check the edited configuration before
continuing:

```bash
pdk config --check
```

Use [PDF configuration](pdf.md#pdf-quick-start) when you later need a different
page size, margins, output path, or PDF-only stylesheet.

////

//// step | Diagnose the adopted site

Check the active environment and every required project capability before
writing with the newly enabled components:

```bash
pdk diag
```

Resolve every `FAIL` before continuing. Because this clean-site route does not
create a Git repository, a warning that Git or repository metadata is absent
is expected until you choose to initialise or clone a repository. The Python,
configuration, dependency, managed-file, and selected-renderer checks should
pass.

////

//// step | Add and verify Prodockit content

Replace `docs/index.md` with content that uses two of the extensions enabled by
Adopt:

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

//// step | Build and preview the adopted website

Build and preview the adopted site:

```bash
zensical build --clean --strict
zensical serve
```

Open the local address again and confirm that the headings are numbered and the
reference is linked. Zensical rebuilds the preview when a source file changes;
stop it with `Ctrl+C`.

////

//// step | Generate the rendered PDF

The PDF command consumes the completed Zensical build and follows the pages in
`project.nav`. If `pdk diag` reported missing WeasyPrint native libraries or
fonts, complete the adoption row under [Prepare the PDF
tools](pdf.md#pdf-requirements) first.

Rebuild the website after any source or configuration change, then generate
the rendered document:

```bash
zensical build --clean --strict
pdk pdf
```

The configured first-site output is `docs/site_documentation.pdf`. Open it and
check its headings, contents, links, page breaks, and final page. See [Build
your first PDF](pdf.md#build-your-first-pdf) for the complete review sequence.

////

//// step | Generate the source bundle

Create a separate PDF containing the authored Markdown and project
configuration:

```bash
pdk source-bundle
```

The configured output is `docs/source_bundle.pdf`. It is separate from the
rendered document: use it when a submission, review, or archive needs the
underlying source. The [`pdk source-bundle` command
reference](commands/source-bundle.md) describes its inputs and options.

////

//// step | Add both downloads to the site

Add links to the generated files in `docs/index.md`:

```md
[Download the rendered document](site_documentation.pdf)

[Download the source bundle](source_bundle.pdf)
```

Both outputs are under `docs/`, so Zensical publishes them as site files.
Build once more to validate the links and copy the current artifacts, then
preview the finished site:

```bash
zensical build --clean --strict
zensical serve
```

Open both links in the browser before publishing the site. Regenerate the PDFs
whenever their Markdown or configuration changes, then rebuild the website so
the published downloads stay current.

////

///

## Where to go next

Continue with the part of the document workflow you need next:

- Browse the [authoring reference](extensions/headings.md) when you need
  another document feature.
- Read [Generate a PDF](pdf.md#pdf-quick-start) when the website is ready to
  print or submit.
- Follow the [project maintenance cycle](project-maintenance.md) when the
  first site becomes a maintained project, then use the
  [command-line map](command-line.md) to choose a command safely.

!!! note "Previewing these documentation changes"
    From this repository's root, run \index{`zensical serve`} and open the address it
    prints. This page already has `prodockit.steps` enabled and styled.
