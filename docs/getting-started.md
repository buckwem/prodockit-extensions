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

Steps without a path badge apply to both routes. The words identify the path
as well as the colours. Keep your existing site's content and configuration;
do not copy new-site examples over them.

Five stages take the site from an empty project directory to a verified
website with downloadable PDF and source outputs.
An optional sixth stage saves the source to GitHub and publishes the website.

### Stage 1 — Prepare the project environment

Prepare or enter the project directory and verify that it uses its own Python
3.14 environment rather than the shared setup environment.

/// steps

//// step | Prepare Python and the setup environment

Complete section 3.1 in the parent directory that holds your repositories:

[Open section 3.1 to prepare your environment](installation.md#installation-preparation){ .md-button .md-button--primary target="_blank" rel="noopener" }

Return here with that setup environment active. The next step enters the new
site directory and creates a separate `.venv` for the site before Zensical is
installed.

////

<span id="prepare-the-empty-project-directory"></span>

//// step | Prepare the empty project directory **Clean**{: .install-clean}

Leave the parent setup environment, create and enter the site directory, then
create its project-local virtual environment. Use the same repositories path
you selected in section 3.1. The examples call the site `prodockit-project`;
replace that name if required.

!!! warning "Already have a site? Keep its files and environment"

    Enter the existing directory containing `zensical.toml`, `zensical.yml`
    or `zensical.yaml` instead of creating a new project. Do not run
    `zensical new .` there or replace its pages with the starter examples.
    Activate its existing `.venv` and check `python --version` first. If it
    reports Python 3.14, keep that environment. If it is missing or damaged,
    follow [the environment recovery instructions](troubleshooting-installs.md#wrong-python)
    before continuing. Adopt aligns packages but cannot replace the running
    Python interpreter.

The commands below perform these actions in order:

- `deactivate` leaves the currently active setup environment; it does not
  delete it. Omit this command if no environment is active.
- `cd` or PowerShell's `Set-Location` changes the directory you are working in.
  Replace the example repositories path with your own before running it.
- `mkdir -p` or `New-Item -ItemType Directory -Force` creates the project folder
  if it does not exist. `Out-Null` hides PowerShell's folder-creation listing.
- The second directory-change command enters that project folder.
- The Python command ending in `-m venv .venv` creates its isolated environment.
  On macOS, `brew --prefix python@3.14` locates Homebrew's Python 3.14;
  Windows uses `py -3.14`, and Ubuntu uses `python3.14`.
- On Windows, `Set-ExecutionPolicy ... RemoteSigned` allows locally created
  activation scripts for your user account; it does not change every user's policy.
- `source .venv/bin/activate` or the PowerShell activation script activates that
  environment so subsequent Python commands use the project's installation.

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

`pwd` (or `Get-Location`) prints your current directory. `python --version`
prints the Python version. The final `python -c ...` command prints the active
Python environment's directory; it only reads this information.

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

### Stage 2 — Install and prove Zensical **Clean**{: .install-clean} {: #stage-2-install-and-prove-zensical }

If you already have a Zensical site, skip this stage and continue with Stage 3,
even if its current build fails: Adopt may repair its software dependencies.
Do not run `zensical new .` in an existing site. If Zensical is installed but you have
not created a site yet, skip only the installation step and continue with
“Create the Zensical site” below.

Install Zensical, create its starter site, and prove that the unmodified site
builds and previews successfully before Prodockit is introduced.

/// steps

//// step | Install Zensical

Follow Zensical's official [installation
guide](https://zensical.org/docs/get-started/) and install it into the active
project environment.

`pip install --upgrade` (or `pip3 install --upgrade`) installs Zensical if it
is missing, or updates it to the newest available version in this environment.

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
directory. `zensical new .` creates the starter configuration and documentation;
the dot means the current directory:

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

Start Zensical's local development server with \index{`zensical serve`}:

```bash
zensical serve
```

Open the local address printed in the terminal and confirm that the starter
site appears. While the server is running, Zensical watches the source and
rebuilds the preview after a change. Stop it with `Ctrl+C`.

Do not continue until both checks succeed. Any problem at this point belongs
to the Python environment or the plain Zensical site, not Prodockit.

////

//// step | Reactivate the Zensical environment

You now have a working Zensical site and can stop here if you do not need
Prodockit yet. After stopping the preview server, reactivate the project
environment using the command for your platform below. This does not recreate
`.venv` or reinstall anything.

If you return in a new terminal later, first open the project directory and
run the same activation command before using Zensical or continuing to Stage 3.

=== ":material-apple: macOS"

    ```bash
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

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

### Stage 3 — Add and configure Prodockit

Install Prodockit, choose its optional renderers, prepare Node.js only when a
selected renderer needs it, apply the integration stages, configure the shared
website and PDF settings, and diagnose the resulting project.

/// steps

//// step | Install Prodockit

Install Prodockit into the same active project environment. This makes the
`pdk` command available; it does not yet change the Zensical project.

The `--upgrade` option installs the newest available Prodockit release, or
updates the copy already installed in this environment.

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

//// step | Choose optional renderers

Save this project's choices before previewing Adopt:

```bash
pdk adopt --configure
```

Mermaid diagrams and mathematical notation are separate, optional choices and
both default to **No**. A project created from `prodockit-template` already has
a committed `.prodockit-components.toml` with both enabled; a plain Zensical
site does not inherit choices merely because its starter configuration can
support those features.

Existing project-local Mermaid or MathJax installations, including incomplete
scaffolds, are inferred when no saved choices exist. Check the choices before
accepting them. Unselected renderers are left alone; selected renderer files
are backed up under `.prodockit-adopt-backups/renderers` before alignment.

If you answer **No** to both questions, continue to the next step. Node.js and
npm are not required.

If you answer **Yes** to either option, Adopt will check Node.js and npm and
offer any required installation or repair when you apply the plan. You do not
need to install them manually first. Administrator approval may be needed.
On macOS, Homebrew must already be usable from section 3.1. If this activity
fails, follow [Node.js troubleshooting](troubleshooting-installs.md#installtooling-npm-missing).

////

//// step | Adopt the Zensical site

!!! warning "Existing custom styles can override Prodockit"

    Adopt loads managed `pdk.css` after the Zensical theme and keeps any
    existing `template.css` next. Your `extra.css` has the final website
    override. For PDFs, `pdk-pdf.css` supplies the managed rules and
    `print.css` has the final override. Your custom files are retained, but
    conflicting rules can hide or change Prodockit features. Read
    [the stylesheet precedence guide](stylesheets.md#load-the-cascade-in-order)
    if the updated site does not look as expected.

\ref{fig-first-site-adopt-output} explains the coloured messages to look for
when reviewing each proposed change. See [the command-output guide](commands/output.md#command-output-structure)
for more about phases, activities, colours, and default-No decisions.

![A terminal report with callouts identifying phases, activities, proposed changes, and warnings](assets/diagrams/command-output-anatomy.svg){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-first-site-adopt-output}

Reading the coloured Adopt messages
///

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

If installation is interrupted, keep the project files, reactivate its
environment and rerun `pdk adopt --apply`. Adopt reassesses the project and
reuses completed work and validated caches. Follow any cleanup or restart
warning before retrying. See [Recover a failed installation](troubleshooting-installs.md#installtooling-download-fails).
For a deliberately disconnected machine, see [offline adoption](commands/adopt.md)
for the caches required by `--offline`; it cannot download missing software.

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

Adopt keeps existing requirements operators and extras while aligning managed
versions. It uses `requirements.txt`, `requirements/docs.txt` or
`docs/requirements.txt`, and creates the first when none exists. It also
records the supported versions in `.prodockit-toolchain.toml` and
`.python-version`. Missing user-managed styles and scripts are created, not
overwritten. A configured citation style is installed when missing; existing
custom CSL files remain yours.

For TOML sites, `.prodockit-adopt.toml` records reviewed template settings.
New options that Adopt does not recognise are added as commented examples;
branding and `template.css` are excluded. The ledger does not skip software
health checks. See [the settings review ledger](commands/adopt.md#template-settings-and-the-review-ledger)
before resetting it.

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

For help with warnings or failures, see [Correct diagnostic findings](troubleshooting-installs.md#diagnostic-corrections)
in Troubleshooting.

////

///

### Stage 4 — Verify the adopted website

Add a small example using Prodockit's authoring features, then build and
preview it to confirm that the integration works.

/// steps

//// step | Add and verify Prodockit content

For a new site, replace the starter `docs/index.md` with this small example
using two enabled extensions. For an existing site, keep its pages and add
the example to a temporary test page instead:

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

`zensical build --clean --strict` rebuilds the website from scratch and stops
on warnings. If it succeeds, `zensical serve` starts the local preview server:

```bash
zensical build --clean --strict
zensical serve
```

Open the local address again and confirm that the headings are numbered and the
reference is linked. Zensical rebuilds the preview when a source file changes;
stop it with `Ctrl+C`.

For an existing YAML configuration, add `-f zensical.yml` or
`-f zensical.yaml` to both Zensical commands to select that file; only
`zensical.toml` is discovered automatically. Check the real site's pages,
custom styling and navigation as well as the example.

If the project already uses Git, `git diff` shows the local changes and
`git status --short` lists modified and untracked files. Review these before
committing through your normal workflow; press `q` to leave the diff viewer.

////

///

### Stage 5 — Add downloadable outputs

For an existing site, retain its configured PDF filenames and existing download
links. Use the actual output paths printed by the commands instead of assuming
the default filenames below. Skip adding links that already work.

!!! note "Local downloads and published downloads are different"

    These steps generate and test downloads locally. The stock website workflow
    does not regenerate PDFs. Before sharing published download links, configure
    [PDF and source-bundle publishing](publishing.md) so later builds keep them current.

Generate the rendered document and source bundle, link both from the website,
and verify the finished downloads locally.

/// steps

//// step | Generate the rendered PDF

The PDF command consumes the completed Zensical build and follows the pages in
`project.nav`. If `pdk diag` reported missing WeasyPrint native libraries or
fonts, complete the adoption row under [Prepare the PDF
tools](pdf.md#pdf-requirements) first.

`zensical build --clean --strict` rebuilds and checks the website after any
source or configuration change. If it succeeds, `pdk pdf` uses that completed
build to generate the rendered PDF:

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

`zensical build --clean --strict` creates a fresh website containing the PDF
downloads. `zensical serve` starts the local server so you can test both links.

```bash
zensical build --clean --strict
zensical serve
```

Open both links in the browser before publishing the site. Regenerate the PDFs
whenever their Markdown or configuration changes, then rebuild the website so
the published downloads stay current.

////

///

### Stage 6 — Save and publish **Optional**{: .bg-green} {: #stage-6-save-and-publish-optional }

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

//// step | Complete any deferred repository setup **Optional**{: .bg-green}

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

    This starts GitHub's sign-in process and saves authentication for the
    GitHub command-line tool. Follow its prompts; do not paste a token into
    your documentation.

    ```bash
    gh auth login --hostname github.com
    ```

=== "GitLab"

    This signs the GitLab command-line tool into the selected GitLab host.
    Follow its prompts to authenticate your account.

    ```bash
    glab auth login --hostname gitlab.com
    ```

    For Surrey, replace `gitlab.com` with `gitlab.surrey.ac.uk`.

////

//// step | Prepare the files and your commit identity

Check that the project is ready. `pdk diag` reports problems without changing
files. Follow its correction guidance before continuing. Adopt supplies the
baseline ignore rules and repairs the standard Zensical GitHub workflow;
diagnostics checks for common omissions but does not perform those repairs.

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

//// step | Create the first commit **Clean**{: .install-clean}

**Update**{: .install-update}: skip this first-commit step. Review and commit your
changes using the existing repository's normal branch and review process;
keep its remote and publishing workflow.

Run these commands one at a time, reviewing the output before moving on:

- `git add .` selects the current directory's changes for the next commit;
  files covered by ignore rules are excluded unless already tracked.
- `git diff --cached --stat` summarises the selected files and change sizes.
- `git diff --cached` shows their actual changes. Check for private information
  or unwanted files and stop if anything is wrong. Press `q` to close the viewer.
- `git commit -m ...` saves the reviewed changes in local Git history with
  the supplied description. It does not upload anything.

```bash
git add .
git diff --cached --stat
git diff --cached
git commit -m "Create documentation site with Prodockit"
```

Press `q` to leave Git's diff viewer. Adopt's optional setup has already created
or connected your repository. Do not create it again. `git remote -v` lists
the configured download and upload addresses; check that `origin` is your
intended repository:

```bash
git remote -v
```

If `origin` is missing, rerun `pdk adopt --apply` and complete repository setup.

////

//// step | Set the website and repository details **Optional**{: .bg-green}

Skip this step if the website and repository details were already set up
during Adopt and are correct. Use it to complete missing details or update
them later.

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

Replace the examples with your real title and website address before running.
The command updates those two settings in `zensical.toml`.

Then run the following commands one at a time:

- `pdk config --check` validates the configuration and project inputs.
- `zensical build --clean --strict` rebuilds the website locally, removing old
  build output and treating warnings as errors. Stop if either check fails.
- `git add ...` selects the listed configuration and publishing files for a
  commit. Omit any path that does not exist in your project; a GitLab project
  may use `.gitlab-ci.yml` instead of the GitHub workflow.
- `git diff --cached --stat` lists the selected changes for your review.
- `git commit -m ...` records those changes locally. If Git reports nothing
  to commit, the files are already saved and you can continue.

```bash
pdk config --check
zensical build --clean --strict
git add zensical.toml README.md .github/workflows/docs.yml .gitignore
git diff --cached --stat
git commit -m "Configure repository and website publishing"
```

////

//// step | Enable repo for Pages

Repository setup does not enable website publishing. Only continue when you
are ready to publish and have reviewed the workflow for your chosen host.

=== "GitHub"

    1. Open your repository on GitHub in your browser.
    2. Select **Settings**, then **Pages** in the left-hand menu.
    3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
       If it is already selected, leave it unchanged.

    Use the project's existing documentation workflow; do not add another
    workflow from the suggested templates. If Pages or the Source setting is
    unavailable, check your repository permissions and plan. Do not make the
    repository public just to clear an error.
    See [GitHub's Pages instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

=== "GitLab"

    1. Open your project on GitLab in your browser.
    2. Check that the repository contains `.gitlab-ci.yml` with a Pages job.
       If it is missing, follow [Build and publish](devcons/continuous-integration.md)
       before continuing; Adopt's repository setup does not create it.
    3. Open **Deploy > Pages** to review the publishing information. The website
       address becomes available after the first successful Pages deployment.

    GitLab uses the Pages job to publish the site; there is no GitHub-style
    Source selector. On a university or company GitLab instance, ask its
    administrator if Pages is unavailable.
    See [GitLab's Pages instructions](https://docs.gitlab.com/user/project/pages/).

////

//// step | Check the published website

For either host, push after checking the files and enabling Pages.
For an existing repository, use its normal publishing branch and process;
do not assume it uses `main` or push directly to a protected branch.
`git push` uploads your local commits to `origin`; `main` names the branch,
and `-u` remembers that destination for future pushes. This upload can start
the publishing workflow:

```bash
git push -u origin main
```

Then check the publishing run for your host:

=== "GitHub"

    - `gh run list --limit 5` lists the five most recent workflow runs.
    - `gh run watch` lets you select a run and follow its progress until it ends.
    - `gh api ... --jq .html_url` asks GitHub for the published Pages address.
      Leave `{owner}` and `{repo}` unchanged: the tool derives them from your
      current repository.

    ```bash
    gh run list --limit 5
    gh run watch
    gh api "repos/{owner}/{repo}/pages" --jq .html_url
    ```

    Inspect a failed run with `gh run view --log-failed`.

=== "GitLab"

    - `glab ci status` reports the current branch's pipeline status.
    - `glab repo view --web` opens the project in your browser so you can
      inspect the pipeline and find the Pages address.

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

Adoption does not create or remove a template relationship. For a new plain
site, `pdk template-sync` does not apply unless that relationship is established
later. For an existing template-derived site, retain its template metadata and
continue using Template Sync for template updates, followed by Adopt and diagnostics.

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
