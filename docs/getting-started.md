---
icon: lucide/rocket
---

{{ heading_counter_reset(page) }}

# Build your first site

Use this route when you do not yet have a Zensical site and want to create one
cleanly before adding Prodockit. It is independent of section 6's template-site
route: Bootstrap creates a repository from `prodockit-template`, whereas this
walkthrough starts with an empty directory, proves that Zensical works on its
own, and then uses Adopt to integrate Prodockit without manual configuration.

## Build and verify the site

Five stages take the site from an empty project directory to a verified
website with downloadable PDF and source outputs.
An optional sixth stage saves the source to GitHub and publishes the website.

### Stage 1 — Prepare the project environment

Create the empty project directory and verify that it uses its own Python 3.14
environment rather than the shared setup environment.

/// steps

//// step | Prepare Python and the setup environment

Complete section 3.1 in the parent directory that holds your repositories:

[Open section 3.1 to prepare your environment](installation.md#installation-preparation){ .md-button .md-button--primary target="_blank" rel="noopener" }

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
`~/repos/.venv` is the Bootstrap setup environment and is not this site's
environment. Correct the directory and repeat section 3.1 before installing
Zensical.

////

///

### Stage 2 — Install and prove Zensical

Install Zensical, create its starter site, and prove that the unmodified site
builds and previews successfully before Prodockit is introduced.

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

This creates the [clean Zensical project structure shown in section
3.2](installation.md#installation-project-structure). Review that tree before
continuing so you can distinguish Zensical's files from the files Prodockit
adds later.

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

\index{`zensical serve`}

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

///

### Stage 3 — Add and configure Prodockit

Install Prodockit, choose its optional renderers, prepare Node.js only when a
selected renderer needs it, apply the integration stages, configure the shared
website and PDF settings, and diagnose the resulting project.

/// steps

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

//// step | Choose optional renderers and prepare Node.js when required

Save this project's choices before previewing Adopt:

```bash
pdk adopt --configure
```

Mermaid diagrams and mathematical notation are separate, optional choices and
both default to **No**. A project created from `prodockit-template` already has
a committed `.prodockit-components.toml` with both enabled; a plain Zensical
site does not inherit choices merely because its starter configuration can
support those features.

If you answer **No** to both questions, continue to the next step. Node.js and
npm are not required.

If you answer **Yes** to Mermaid or mathematical notation, install Node.js and
npm for your platform:

=== ":material-apple: macOS"

    ```bash
    brew install node
    ```

=== ":fontawesome-brands-windows: Windows"

    In PowerShell:

    ```powershell
    winget install --id OpenJS.NodeJS.LTS
    ```

    Fully close and reopen PowerShell after installation, return to the project
    directory, and reactivate `.venv` before continuing.

=== ":material-linux: Linux (Ubuntu)"

    ```bash
    sudo apt install -y curl
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt install -y nodejs
    ```

Confirm that both commands are available:

```bash
node --version
npm --version
```

These commands show whether Node.js and npm are already available. If either
is missing, Adopt can install the required runtime when you apply the selected
renderer activities. On macOS, Homebrew must already be installed and usable.

////

//// step | Adopt the Zensical site

Preview the integration stages before allowing Adopt to install the supported
project toolchain and configure the standard authoring components and shared
website styles:

```bash
pdk adopt --dry-run
```

Review the preview, then apply the changes:

```bash
pdk adopt --apply
```

Read each stage before accepting it. Adopt now uses the component choices you
saved in the previous step. Its final phase asks for missing site details and
offers optional Git and remote repository setup, with separate confirmation.
It never commits or pushes files, and does not configure SSH, editors or publishing.

Answer the site-title, repository-host, account or group, and repository-name
questions. Adopt proposes a website address where the host's layout is known;
confirm that address or supply your custom address. For GitLab, use the exact
Pages address from the hosting service if no reliable suggestion is available.
Unknown details can be deferred without preventing local testing.

Repository setup is optional. Adopt asks before initialising Git locally,
connecting an origin remote, or creating an empty hosted repository. Creation
uses `gh` for GitHub or `glab` for GitLab. Adopt offers to install missing Git
and hosting tools, then guides sign-in through the selected tool. Homebrew is
the manual macOS prerequisite. Repository creation asks for visibility (private
by default). Existing remotes are never replaced.
No files are committed or pushed automatically. You can decline and complete
these steps in Stage 6 instead.

At the end, accept the diagnostic check to see anything still outstanding.
Correction commands are followed by numbered lists of the problems they address.

After Adopt, the project retains the Zensical files and adds the [Prodockit
project files shown in section
3.2](installation.md#installation-project-structure). Adopt also updates
`zensical.toml` to enable the standard components and load the shared
stylesheet.

////

//// step | Refresh the project environment

After Adopt completes, refresh the environment **before running diagnostics,
building the site or generating a PDF**. Adopt may have added paths needed by
the installed tools and PDF libraries. Follow its highlighted instructions.

=== ":material-apple: macOS"

    In the same terminal and project directory, run:

    ```bash
    source .venv/bin/activate
    ```

    This reloads the PDF library settings. You do not need to recreate `.venv`.

=== ":fontawesome-brands-windows: Windows"

    If Adopt displays its restart banner, fully close Windows Terminal or
    VS Code and reopen it. Open PowerShell in your project directory, then run:

    ```powershell
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    Keep the project environment active. If you reopened the terminal, return
    to the project directory and reactivate it:

    ```bash
    source .venv/bin/activate
    ```

Use the activation path printed by Adopt if your environment has another name.

////

//// step | Check the generated configuration

`zensical.toml` is the single project configuration used by the website and
Prodockit's PDF commands. Adopt keeps Zensical's existing `[project]` settings,
adds the standard `project.markdown_extensions` tables, and adds
`"stylesheets/pdk.css"` to `project.extra_css`.

You do not need to open an editor or complete the publishing details at this
step. The generated defaults are enough to build and test your site locally.

!!! note "Site details are collected by Adopt"

    Adopt's final phase asks for missing `site_name`, `site_url`, `repo_url`
    and `repo_name` and updates `zensical.toml` after confirmation. Existing
    values are preserved. If you deferred these questions, run `pdk adopt --apply`
    again when the details are known. Stage 6 covers publishing and any repository
    setup you chose not to do in Adopt.

The existing `nav` setting controls website navigation and PDF page order.
The default PDF outputs are `docs/site_documentation.pdf` and
`docs/source_bundle.pdf`; you do not need to add these settings manually.

Check that the generated configuration is valid before continuing:

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

Resolve every `FAIL` before continuing. If you declined optional repository
setup, a warning that Git or repository metadata is absent is expected until
you choose to initialise or clone a repository. The Python,
configuration, dependency, managed-file, and selected-renderer checks should
pass.

Publishing warnings do not mean that installation failed. Follow the correction
route shown by each check in \ref{tab-first-site-diagnostic-corrections}:

| Diagnostic finding | Where to correct it |
| --- | --- |
| Starter site title, example website address, or missing repository link | Run `pdk adopt --apply` and answer the final questions. If an existing remote has changed, use `pdk sync-repo --create-readme`. |
| Missing PDF libraries, fonts, or renderer prerequisites | Run `pdk adopt --dry-run`, review the proposed repair, then run `pdk adopt --apply`. Refresh the environment before rerunning diagnostics. |
| Missing ignore rules for local or generated files | Run `pdk adopt --apply` for the baseline rules. Custom output paths need matching ignore rules. |
| Generated files already tracked by Git | Review them before removing them from Git tracking, retaining local copies. Ignore rules alone do not fix this; diagnostics never deletes files. |
| A stock workflow installs only Zensical | Run `pdk adopt --apply` to review its repair. |
| A workflow refers to a missing dependency file | Restore the file or review the workflow using [Build and publish](devcons/continuous-integration.md). |

/// table-caption | <
attrs: {id: tab-first-site-diagnostic-corrections}
Where to correct diagnostic findings during first-site setup.
///

The workflow check is a basic local check, not a substitute for a successful
pipeline. A configured website address does not prove publication: verify the
pipeline and hosting settings in Stage 6. Normal `pdk diag` does not change files,
repository settings or hosting settings.

////

///

### Stage 4 — Verify the adopted website

Add a small example using Prodockit's authoring features, then build and
preview it to confirm that the integration works.

/// steps

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

///

### Stage 5 — Add downloadable outputs

Generate the rendered document and source bundle, link both from the website,
and verify the finished downloads locally.

/// steps

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

### Stage 6 — Save and publish (optional)

You now have a working local site. This optional stage puts a copy of its
source on your chosen GitHub or GitLab host. Stay in your project directory.
The commands below do not require a text editor.

!!! warning "Check what you are sharing"

    A public repository exposes its committed files. A public Pages site exposes
    the generated website, even when its source repository is private.
    Do not upload passwords, tokens, personal data or confidential documents.
    Private-repository Pages availability depends on your GitHub plan. Do not
    make a repository public merely to work around an error.

/// steps

//// step | Complete any deferred repository setup

Skip this step if you completed Adopt's optional repository setup. Otherwise run:

```bash
pdk adopt --apply
```

Answer **Yes** to “Would you like to set up a GitHub or GitLab repository for
this site?” Adopt offers to install missing Git and hosting tools, guides
sign-in, asks for missing commit identity, and confirms repository creation
or connection separately. Existing settings are reused. It does not push files.

If you need to sign in again manually, use your host's tab:

=== "GitHub"

    ```bash
    gh auth login --hostname github.com
    ```

=== "GitLab"

    ```bash
    glab auth login --hostname gitlab.com
    ```

    For Surrey, replace `gitlab.com` with `gitlab.surrey.ac.uk`.

////

//// step | Prepare the files and your commit identity

Run Adopt again to add the local-output ignore rules and repair the standard
Zensical GitHub workflow. The repaired workflow installs `requirements.txt`
instead of Zensical alone, and restores MathJax website files when selected.
Custom workflows are left unchanged.

```bash
pdk diag
```

Adopt asks for missing commit identity and saves it only for this project.
Existing identity settings are preserved. Check the files before staging:

```bash
git status --short --untracked-files=all
```

The list should contain your documentation, configuration, shared styles/scripts,
renderer manifests and lockfiles. Keep the three `.prodockit-*.toml` files.
It should not contain `.venv`, `node_modules`, generated PDFs, website output,
backups or `docs/.prodockit-pdf-mermaid`. Stop if anything private appears.

////

//// step | Create the first commit

Review the staged files before committing:

```bash
git add .
git diff --cached --stat
git diff --cached
git commit -m "Create documentation site with Prodockit"
```

Press `q` to leave Git's diff viewer. Adopt's optional setup has already created
or connected your repository. Do not create it again. Check the connection:

```bash
git remote -v
```

If `origin` is missing, rerun `pdk adopt --apply` and complete repository setup.

////

//// step | Set the website and repository details

```bash
pdk sync-repo --create-readme
```

The command derives repository details from `origin`, retains the site title
and address confirmed during Adopt, and asks only for missing details. It adds
missing TOML settings in the right
tables and creates a README only if absent. It preserves existing custom values.
The suggested address is not evidence of a published site.

If a title or address needs changing later, no editor is necessary:

```bash
pdk sync-repo --site-name "My report" --site-url "https://your-account.github.io/your-repository/"
```

Replace the examples before running. Then verify and commit:

```bash
pdk config --check
zensical build --clean --strict
git add zensical.toml README.md .github/workflows/docs.yml .gitignore
git diff --cached --stat
git commit -m "Configure repository and website publishing"
```

////

//// step | Prepare publishing and push

Repository setup does not enable website publishing. Only continue when you
are ready to publish and have reviewed the workflow for your chosen host.

=== "GitHub"

    Check whether Pages is already configured:

    ```bash
    gh api "repos/{owner}/{repo}/pages" --jq .build_type
    ```

    Keep `{owner}` and `{repo}` as shown; GitHub CLI derives them from `origin`.
    If Pages does not exist, enable it when ready:

    ```bash
    gh api --method POST "repos/{owner}/{repo}/pages" -f build_type=workflow
    ```

    For an existing site using another source, change it only after review:

    ```bash
    gh api --method PUT "repos/{owner}/{repo}/pages" -f build_type=workflow
    ```

    Resolve permission or plan restrictions rather than making the repository
    public to bypass an error. See [GitHub Pages configuration](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

=== "GitLab"

    Ensure the project has a GitLab Pages workflow in `.gitlab-ci.yml`.
    Adopt's repository setup does not create a Pages workflow or configure its
    visibility. Follow [Build and publish](devcons/continuous-integration.md)
    before pushing if that workflow is missing.

    Open the selected project to review its pipeline and Pages settings:

    ```bash
    glab repo view --web
    ```

    Confirm the actual website address under Deploy > Pages. Do not infer it
    from the GitLab repository address; custom domains and instance settings differ.

For either host, push only after checking the files and publishing configuration:

```bash
git push -u origin main
```

////

//// step | Check the published website

=== "GitHub"

    ```bash
    gh run list --limit 5
    gh run watch
    gh api "repos/{owner}/{repo}/pages" --jq .html_url
    ```

    Inspect a failed run with `gh run view --log-failed`.

=== "GitLab"

    ```bash
    glab ci status
    glab repo view --web
    ```

    Inspect the pipeline and open the address shown under Deploy > Pages.

Open the returned address and check the pages, navigation and maths. A successful
push is not the same as a successful deployment. Inspect a failed pipeline
before retrying. If the actual website address differs from the configured one,
update it with `pdk sync-repo --site-url "https://your-actual-site-address/"`.

The stock workflow publishes the website; it does not generate the downloadable
PDFs from Stage 5. Follow [Publish a document](publishing.md) to configure the
full PDF and source-bundle publishing workflow before sharing those download links.

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

Adoption does not pair this clean site with `prodockit-template`, so
`pdk template-sync` does not apply unless a template relationship is
deliberately established later.

### Keep the project current {: #first-site-maintenance }

Follow this sequence inside the active project environment:

1. Use the platform-specific command earlier in this section to upgrade
   Prodockit.
2. Ask Adopt to compare the project with the newly supported combination:

   ```bash
   pdk adopt --dry-run
   ```

   Review the reported files. If Adopt selects any activities, apply them:

   ```bash
   pdk adopt --apply
   ```

3. Run Diagnostics as the final integration check:

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
