---
icon: lucide/rocket
---

{{ heading_counter_reset(page) }}

# Build or update a site

Use this route to create a Zensical site or add and update Prodockit in an
existing site. New projects first prove that Zensical works on its own;
existing projects keep their content and skip the site-creation steps.
Adopt then aligns the software and integrates the selected components.
Unlike the template-site route, this does not replace the project with
`prodockit-template`.

## Build and verify the site

Follow the badges beside the step titles:

- **Clean**{: .install-clean}: only for a new site in an empty directory.
- **Update**{: .install-update}: only for an existing Zensical site, with or without Prodockit.
- **Optional**{: .bg-green}: skip when already completed or not needed.
- [Go to](#stage-1-prepare-the-project-environment){ .install-go }: click to jump to another section.

Steps without a path badge apply to both routes. The words identify the path
as well as the colours. Keep your existing site's content and configuration;
do not copy new-site examples over them.

Follow Stage 3a for a clean site or Stage 3b for an existing Zensical site;
both routes join at Stage 4 and lead to a verified website with downloadable outputs.
An optional seventh stage saves the source to GitHub and publishes the website.

### Stage 1 — Prepare the setup environment {: #stage-1-prepare-the-project-environment }

Python 3.14 must be installed before either a clean installation or an upgrade.
An existing Zensical site may use an older Python version; installing or
updating Prodockit does not upgrade Python itself.

If Python 3.14 is not already installed, complete section 3.1 in the parent
directory that holds your repositories. It also prepares the shared setup
environment:

[Open section 3.1 to prepare your environment](installation.md#installation-preparation){ .md-button .md-button--primary target="_blank" rel="noopener" }

Once you have Python 3.14 installed, choose the route that matches whether you are creating a new site or updating an existing one:

- For a **Clean**{: .install-clean} install, continue: [Go to Stage 2](#stage-2-prepare-the-project-environment){ .install-go }.
- For an **Upgrade**{: .install-update} install, skip ahead: [Go to Stage 3b](#stage-2b-return-to-zensical-environment){ .install-go }.

### Stage 2 — Prepare the project environment **Clean**{: .install-clean} {: #stage-2-prepare-the-project-environment }

Create the new site directory and its own Python environment. For an existing
Zensical site, skip to Stage 3b and use its existing directory and environment.

/// steps

<span id="prepare-the-empty-project-directory"></span>

//// step | Prepare the empty project directory **Clean**{: .install-clean}

Leave the setup environment, then create and enter your new site's folder.
Change `~/repos` and `prodockit-project` if you chose different names. Skip
`deactivate` if no environment is active, and `mkdir` if the intended folder
already exists and is empty.

Run each line in turn. **If `cd` fails, stop and correct the path before continuing.**

=== ":material-apple: macOS"

    ```bash
    deactivate
    cd ~/repos
    mkdir -p prodockit-project
    cd prodockit-project
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    deactivate
    cd ~/repos
    mkdir prodockit-project
    cd prodockit-project
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    deactivate
    cd ~/repos
    mkdir -p prodockit-project
    cd prodockit-project
    ```

////

//// step | Create and activate the project environment **Clean**{: .install-clean}

Create a Python 3.14 environment in `.venv`, then activate it so subsequent
commands use this site's packages rather than another project's.

=== ":material-apple: macOS"

    ```bash
    "$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    The policy command allows activation scripts for your Windows account.

    ```powershell
    py -3.14 -m venv .venv
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    python3.14 -m venv .venv
    source .venv/bin/activate
    ```

////

//// step | Verify the project environment

Check your current directory, Python version and active environment before
installing Zensical:

=== ":material-apple: macOS"

    ```bash
    pwd
    python --version
    python -c 'import sys; print(sys.prefix)'
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    pwd
    python --version
    python -c "import sys; print(sys.prefix)"
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    pwd
    python --version
    python -c 'import sys; print(sys.prefix)'
    ```

The results should show your project folder, Python 3.14 and that folder's
`.venv`—not `~/repos/.venv`. If they do not, correct the directory and activate
the project's environment before continuing.

////

///

### Stage 3a — Install and prove Zensical **Clean**{: .install-clean} {: #stage-2-install-and-prove-zensical }

If you already have a Zensical site, skip this stage and continue with Stage 3b,
even if its current build fails: Adopt may repair its software dependencies.

Install Zensical, create its starter site, and prove that the unmodified site
builds and previews successfully before Prodockit is introduced.

/// steps

//// step | Install Zensical

Install the latest Zensical into your active project environment using the
command for your platform. See the [official installation guide](https://zensical.org/docs/get-started/) for details.

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

////

//// step | Create the Zensical site

Create the starter site in your empty project directory. The dot means
“here”—do not run this in an existing site.

```bash
zensical new .
```

See the [project structure](installation.md#installation-project-structure)
or Zensical's [Create your site guide](https://zensical.org/docs/create-your-site/) for details.

////

//// step | Build the plain Zensical site

Build the website from scratch and check for errors or warnings. Continue
only when the build succeeds.

```bash
zensical build --clean --strict
```

////

//// step | Preview the plain Zensical site

Start a local preview with \index{`zensical serve`}:

```bash
zensical serve
```

Open the address printed in the terminal and check that the site appears.
Press `Ctrl+C` to stop the preview.

////

///

Now that Zensical is set up, continue with installing Prodockit:
[Go to Stage 4](#stage-4-add-and-configure-prodockit){ .install-go }

### Stage 3b — Return to Zensical environment **Upgrade**{: .install-update} {: #stage-2b-return-to-zensical-environment }

Use this route when Zensical is already installed for your existing site.
If you completed Stage 3a, skip this stage and continue with Stage 4.

/// steps

//// step | Enter the project root directory

Leave the active environment, then enter the existing site's root directory—the folder containing its Zensical
configuration. Use your own site's path if it differs from the example.
Skip `deactivate` if no environment is active. Do not create another project
folder or run `zensical new .`.

=== ":material-apple: macOS"

    ```bash
    deactivate
    cd ~/repos/prodockit-project
    ```

=== ":fontawesome-brands-windows: Windows"

    ```powershell
    deactivate
    cd ~/repos/prodockit-project
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    deactivate
    cd ~/repos/prodockit-project
    ```

**If `cd` fails, stop and correct the path before continuing.**

////

//// step | Create a virtual environment **Optional**{: .bg-green}

Skip this step if the site already has a working Python 3.14 environment.
These instructions use `.venv` as the environment folder name. If yours has
another name, use that name in the activation commands in step 3; do not
create a second environment just to match the guide.

If no environment exists, create one inside the project directory using
Python 3.14 from the preparation stage. This keeps the site's packages
separate from other projects. For a damaged or older environment, follow
[environment recovery](troubleshooting-installs.md#wrong-python) instead.

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

////

//// step | Activate the virtual environment

Activate the site's environment so the following installation commands use
its Python and packages. Replace `.venv` if your environment has another name.

=== ":material-apple: macOS"

    ```bash
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    The execution-policy command allows PowerShell to run the environment's
    activation script; otherwise Windows may block it. It affects your
    account, not other users.

    ```powershell
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    source .venv/bin/activate
    ```

////

///

Now that we have aligned the previous Zensical installation, continue with installing Prodockit:
[Go to Stage 4](#stage-4-add-and-configure-prodockit){ .install-go }

### Stage 4 — Add and configure Prodockit

Install Prodockit, choose the features you need, then check the completed setup.

!!! info "Why are we not installing and configuring by hand?"

    With Mermaid and mathematical notation selected, the setup involves around
    230 individual software packages and tools: around 30 Python packages,
    around 195 JavaScript packages, plus Python, Node.js, npm, Pandoc and a
    browser for drawing diagrams. These figures include the supporting packages
    installed automatically, not just the tools named in the commands. System
    libraries and fonts are additional, and totals vary by platform and release.
    There are also around 50 configuration entries to check or add in
    `zensical.toml`, counting extension sections and website/PDF settings.
    The exact work depends on your platform and what is already configured.

    Installing compatible versions, connecting the tools and checking all those
    settings by hand takes time. Missed commands, failed downloads and small
    configuration mistakes make it easy to end up with a partly working site.
    Adopt automates this work, checks what is already present and lets you rerun
    it after a failure instead of starting the whole process again.

/// steps

//// step | Install Prodockit

Install or update Prodockit in the active project environment. This adds the
`pdk` command; the next steps use it to configure your site.

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

////

//// step | Choose optional renderers

Choose whether to include Mermaid diagrams and mathematical notation:

```bash
pdk adopt --configure
```

Both default to **No** for a new site. Existing installations or saved choices
may already enable them; check before accepting.

If either is selected, Adopt will check Node.js and npm and offer installation
or repair. You do not need to install them manually first. On macOS, Homebrew
must already be available; administrator approval may be needed.

////

//// step | Adopt the Zensical site

Adopt checks your site, installs or updates the software it needs, and adds
Prodockit's settings and shared files while preserving your content. First
preview its plan, then apply the changes you approve. The coloured messages
help you see what is ready, what will change and what needs your attention,
as shown in \ref{fig-first-site-adopt-output}.

![A terminal report with callouts identifying phases, activities, proposed changes, and warnings](assets/diagrams/command-output-anatomy.svg){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-first-site-adopt-output}

Reading the coloured Adopt messages
///

Preview the proposed changes without installing anything:

```bash
pdk adopt --dry-run
```

Apply the plan, approving or skipping each group of changes:

```bash
pdk adopt --apply
```

Answer the final questions about your site and repository. You can defer
unknown details and optional repository setup until Stage 7a. Adopt asks before
installing Git tools, connecting or creating a repository; it never commits,
pushes or publishes your files.

Accept the final diagnostic check and follow any correction instructions.
The [project structure guide](installation.md#installation-project-structure)
explains the files added by Adopt.

If installation is interrupted, keep your files, reactivate the environment
and rerun `pdk adopt --apply`. Follow any cleanup or restart instructions first;
see [Recover a failed installation](troubleshooting-installs.md#installtooling-download-fails).

////

//// step | Refresh the project environment

Reactivate the environment **before running diagnostics or builds** to load
any paths Adopt added. Use the activation path it prints if yours has another name.

=== ":material-apple: macOS"

    ```bash
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    Adopt displays this highlighted banner, using your project's actual path:

    <pre class="terminal-banner"><code><span class="terminal-warning">==============================================================================
    RESTART YOUR TERMINAL BEFORE CHECKING THE PROJECT
    Fully close Windows Terminal or VS Code, then reopen it in this project.</span>
      Project: C:\Users\your-name\repos\prodockit-project
      &amp; 'C:\Users\your-name\repos\prodockit-project\.venv\Scripts\Activate.ps1'
    <span class="terminal-warning">==============================================================================</span></code></pre>

    Close and reopen the terminal, then return to your project directory before
    running the commands below. The policy command allows activation scripts
    for your account.

    ```powershell
    cd ~/repos/prodockit-project
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    source .venv/bin/activate
    ```

////

//// step | Diagnose the adopted site

Check the environment, installed tools and project setup without changing files.
This is also a useful tool to run whenever you have problems: it checks for
common errors and suggests how to correct them.

```bash
pdk diag
```

Resolve every `FAIL` before continuing. Warnings about deferred repository
setup can wait until Stage 7a. For help, see [Correct diagnostic findings](troubleshooting-installs.md#diagnostic-corrections).

////

///

### Stage 5 — Verify the adopted website

Build and preview a small example to check that Prodockit is working.

/// steps

//// step | Add and verify Prodockit content

For a new site, put this example in `docs/index.md`. For an existing site,
keep your content and your site will adopt the styles used on this website.

!!! warning "Custom styles can override Prodockit"

    Adopt preserves your custom styles. Your `extra.css` loads after Prodockit's
    `pdk.css`, so its rules may override the Prodockit styles and change how
    features appear. You may need to adjust or remove conflicting custom rules.
    See [stylesheet precedence](stylesheets.md#load-the-cascade-in-order) for
    the loading order and how the styles work together.

```md
# My first document

The detail is in \ref{results}.

## Method

Describe what you did here.

## Results {: #results }

Describe what you found here.
```

Prodockit should number the headings and turn `\ref{results}` into a link
to the Results section.

////

//// step | Build and preview the adopted website

Build the site, then start the preview only if the build succeeds:

```bash
zensical build --clean --strict
zensical serve
```

Open the displayed address and check the numbered headings and reference link.
For an existing site, also check its pages, styling and navigation. Press
`Ctrl+C` to stop the preview before continuing.

////

///

### Stage 6 — Add downloadable outputs

Create downloadable PDFs of your document and its source. For an existing
site, keep working download links and use the output filenames printed by the commands.

!!! note "Local downloads and published downloads are different"

    These steps test downloads locally. The stock website workflow does not
    regenerate PDFs; configure publishing to keep online downloads up to date.

/// steps

//// step | Generate the rendered PDF

Build the website, then generate its PDF. Run `pdk pdf` only if the build succeeds.

```bash
zensical build --clean --strict
pdk pdf
```

Open the output, normally `docs/site_documentation.pdf`, and check its layout and links.

See [PDF documentation](pdf.md) for more detailed guidance.

////

//// step | Generate the source bundle

Create a separate PDF containing the Markdown and configuration for review or
submission. Skip this step if you do not need to share the source.

```bash
pdk source-bundle
```

The output is normally `docs/source_bundle.pdf`.

See [Bundling source into a PDF](pdf.md#bundling-source-into-a-pdf) for more detailed guidance.

////

//// step | Add both downloads to the site

Add the template's front-page download buttons to `docs/index.md`:

```md
<div style="float: right; display: flex; gap: 15px; margin-left: 15px;" class="web-only" markdown="1">
[:material-archive: Source](source_bundle.pdf){ .md-button target="_blank" }
[:material-file-pdf-box: PDF](site_documentation.pdf){ .md-button target="_blank" }
</div>
```

Rebuild to copy the PDFs into the website, then preview it if the build succeeds:

```bash
zensical build --clean --strict
zensical serve
```

Test both buttons in the browser. After changing the content, regenerate the
PDFs and rebuild the website to keep the downloads current. Press `Ctrl+C` to stop the preview.

////

///

Choose the next stage for your site:

- For a **Clean**{: .install-clean} install: [Go to Stage 7a](#stage-6-save-and-publish-optional){ .install-go }.
- For an **Update**{: .install-update} install: [Go to Stage 7b](#stage-7-review-the-project-changes){ .install-go }.

### Stage 7a — Publish the website **Clean**{: .install-clean} {: #stage-6-save-and-publish-optional }

This stage publishes your working local site on GitHub Pages or GitLab Pages.
Stay in the project directory with its environment active. If the site is
already published, keep its existing workflow and use its normal review process.

The steps below enable Pages, check the files you will share, save and upload
your changes, and confirm that the website is published. We provide terminal
commands, but you can review the differences between files in your preferred
development environment, such as [Visual Studio Code](https://code.visualstudio.com/download).
Its Source Control view lets you inspect changes side by side before committing.
Using an editor for this review is optional; the commands below work without one.

!!! warning "Check what you are sharing"

    A public repository exposes its committed files, and a public Pages site
    exposes the generated website. Do not upload passwords, tokens or private
    material. Do not make a repository public just to work around a Pages error.

/// steps

//// step | Enable repo for Pages

Use your host's tab. Skip settings that are already correct.

=== "GitHub"

    1. Open your repository on GitHub.
    2. Open **Settings > Pages**.
    3. Under **Build and deployment**, set **Source** to **GitHub Actions**.

    Use the existing `.github/workflows/docs.yml`; do not add a duplicate.
    If it is missing or Pages settings are unavailable, follow
    [GitHub Pages setup](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

=== "GitLab"

    Keep your existing Pages job in `.gitlab-ci.yml`. If none exists, follow
    [the GitLab publishing workflow setup](devcons/continuous-integration.md)
    before continuing. Adopt does not create an active GitLab pipeline.

////

//// step | Check the site and files

Check the setup and build the site.
Run each command separately and stop if a check fails:

```bash
pdk diag
zensical build --clean --strict
```

List every changed and new file so you can check what will be included in the
commit and avoid uploading generated or private files:

```bash
git status --short --untracked-files=all
```

Include source, configuration and the publishing workflow—not `.venv`,
`node_modules`, generated website output, caches, backups or private files.

////

//// step | Save and upload the changes

Select the site's source, configuration and publishing workflow files reviewed
in step 2, then review and commit the changes, running one command at a time.
Press `q` to leave the diff viewer; stop if anything should not be shared.
If your repository requires a pull or merge request, use that process instead.

```bash
git add .
git diff --cached
git commit -m "Publish documentation site"
```

Upload the commit to start the publishing workflow. Use your publishing branch
if it is not `main`:

```bash
git push -u origin main
```

If there is nothing new to commit or push, check the latest deployment instead.

////

//// step | Open the published website

Wait for a successful deployment, then open the published site:

=== "GitHub"

    1. Open the repository's **Actions** tab.
    2. Open the documentation run for your latest commit and wait for success.
    3. Open **Settings > Pages**, then follow the published website link.

=== "GitLab"

    1. Open the project's **Build > Pipelines** page.
    2. Open the pipeline for your latest commit and check that its Pages job succeeds.
    3. Open **Deploy > Pages** and follow the website address shown there.

Check the pages, navigation and any diagrams or maths. If publishing fails,
use [Troubleshooting](troubleshooting-installs.md) before retrying.

If the published address differs from your configuration, update it using the
actual address below, then repeat steps 2 and 3:

```bash
pdk sync-repo --site-url "https://your-actual-site-address/"
```

For automated PDF and source downloads, follow [Publish a document](publishing.md).

////

///

### Stage 7b — Review the project changes **Update**{: .install-update} {: #stage-7-review-the-project-changes }

If your site already uses Git, review the changed and new files before
committing through your normal workflow. For a new repository, use Stage 7a instead.

/// steps

//// step | Review the Adopt changes

Before committing, review the files added or updated by `pdk adopt`. Check that
your existing content and custom settings have been preserved. Depending on
your choices, changes may include:

- `zensical.toml`: updated authoring, website, PDF, stylesheet and script settings,
  plus any site and repository details you confirmed. Existing settings are retained
  unless Adopt needs to change them.
- `requirements.txt` (or your existing requirements file): added packages and
  aligned versions; unrelated dependencies are retained.
- `.python-version` and `.prodockit-toolchain.toml`: rewritten with the supported
  versions. `.prodockit-components.toml` is rewritten with your component choices;
  `.prodockit-adopt.toml` records which template settings have been reviewed.
- `.gitignore`: additional rules to exclude local and generated files; existing
  rules are retained.
- `docs/stylesheets/pdk.css`, `docs/stylesheets/pdk-pdf.css` and
  `docs/javascripts/pdk.js`: managed files replaced with the release versions.
- `docs/stylesheets/extra.css`, `docs/stylesheets/print.css` and
  `docs/javascripts/extra.js`: created if missing; custom content is preserved.
  An `extra.js` containing only the recognised old stock script is cleared after
  moving that behaviour to `pdk.js`.
- `tools/mermaid/` and `tools/mathjax/`: selected renderer configuration, package
  manifests, lock files and scripts may be replaced. Previous files are backed up
  under `.prodockit-adopt-backups/renderers/`.
- Citation-style files: installed when missing; existing custom styles are retained.
- Build automation and proposed `pdk.yml` or `.gitlab-pdk.yml` files: review and
  merge these in the next step.

Adopt can also regenerate MathJax files under `docs/javascripts/`, install packages
in `.venv` and `node_modules`, and update local Git settings if approved. These
local or generated changes are not all files to commit.

Keep the configuration needed to reproduce your site, but do not commit local
environments, caches, backups or private files.

////

//// step | Merge the build instructions

The `pdk adopt` command only updates an existing build automation YAML file if its SHA-256 hash
matches a known baseline supplied by the Zensical team. Otherwise, it leaves
your file unchanged and creates a separate Prodockit version for manual merging.

=== ":fontawesome-brands-github: GitHub"

    Merge the relevant instructions from `./pdk.yml` into `./.github/workflows/docs.yml`.

    The proposal stays in the repository root, outside `.github/workflows/`,
    so GitHub cannot run it automatically before you review and merge it.

=== ":fontawesome-brands-gitlab: GitLab"

    Merge the relevant instructions from `./.gitlab-pdk.yml` into `./.gitlab-ci.yml`.

This is a manual merge, not a file replacement. Bring across the required
dependency installation and build commands while keeping your existing
triggers, permissions, secrets and publishing settings. Avoid duplicate jobs
or commands. The proposals cover the website build; PDF publishing needs
additional setup.

The separate files do not run automatically. If neither exists, skip this step.

////

//// step | Follow your project's release process

Follow your usual process to create a branch, review and commit all the project
changes made by `pdk adopt`, including any build instructions merged above,
then push the branch. Use your normal pull or merge request, testing and release
process before publishing the updated site. Keep local environments, caches
and private files out of the commit.

////

///

## Understand the completed project {: #first-site-completed-project }

This section explains which parts of the adopted site Prodockit maintains and
how to keep the completed project aligned after installation.

### Know what becomes yours {: #first-site-ownership }

This route starts with a clean Zensical site and then uses Adopt to add the
selected Prodockit components. The [adopted project
tree](installation.md#installation-adopted-structure) shows the principal
managed and user-managed files together.

Prodockit maintains its standard stylesheets, JavaScript, supported-toolchain
record, and saved component choices. Your Markdown, images, bibliography,
site identity, navigation, and the contents of `extra.css`, `print.css`, and
`extra.js` remain yours. Generated output and `.venv` stay local and can be
recreated.

Adoption does not create or remove a template relationship. For a new plain
site, `pdk template-sync` does not apply unless that relationship is established
later. For an existing template-derived site, retain its template metadata and
continue using Template Sync for template updates, followed by Adopt and diagnostics.

### Keep the project current {: #first-site-maintenance }

Follow this sequence inside the active project environment:

1. Use the platform-specific command earlier in this section to upgrade
   Prodockit.
2. Ask Adopt to compare the project with the newly supported combination:

   `pdk adopt --dry-run`
   :   Lists the proposed software and project changes without applying them.

   ```bash
   pdk adopt --dry-run
   ```

   Review the reported files. If Adopt selects any activities, apply them:

   `pdk adopt --apply`
   :   Asks you to approve or skip the proposed changes and applies those
       you accept.

   ```bash
   pdk adopt --apply
   ```

3. Run Diagnostics as the final integration check:

   `pdk diag`
   :   Checks the resulting environment and project without changing files.
       Follow its correction guidance for any failures or warnings.

   ```bash
   pdk diag
   ```

Continue only when the required checks pass. Then rebuild the website and both
downloadable outputs, inspect them, and commit only the reviewed project files.

## Where to go next {: #getting-started-where-to-go-next }

Choose the route that matches the result:

- If setup has not completed or any check fails, use
  [Troubleshooting](troubleshooting-installs.md).
- If setup has completed and `pdk diag` passes, continue with
  [Publish a document](publishing.md).
