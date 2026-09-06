---
icon: lucide/rocket
---

{{ heading_counter_reset(page) }}

# Build your first site

Use this route when you do not yet have a Zensical site and want to create one
cleanly before adding Prodockit. It is independent of section 5's Bootstrap
route: Bootstrap creates a repository from `prodockit-template`, whereas this
walkthrough starts with an empty directory, proves that Zensical works on its
own, and then uses Adopt to integrate Prodockit without manual configuration.

First complete [section 3.1, Prepare Python and its
environment](installation.md#installation-preparation). When it asks you to
choose a project directory, use the empty directory for this new site. Return
here with that directory's `.venv` active. Python installation, environment
creation, activation, and verification remain in section 3.1 so they are not
duplicated here.

/// steps

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

Build and preview the adopted site:

```bash
zensical build --clean --strict
zensical serve
```

Open the local address again and confirm that the headings are numbered and the
reference is linked. Zensical rebuilds the preview when a source file changes;
stop it with `Ctrl+C`.

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
