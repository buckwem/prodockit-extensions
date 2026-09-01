---
icon: lucide/activity
---

{{ heading_counter_reset(page) }}

# Diagnose a project

Use \index{commands!`prodockit diag`} when a project does not build as expected,
or before changing an installation in response to an error. The command is
read-only: it does not install packages, repair files, run a build, or change
the repository.

Run it from the project root:

```bash
pdk diag
```

Each line starts with `PASS`, `WARN`, or `FAIL`. A failure is an actionable
condition and makes the command exit non-zero. A warning records an optional
capability, an available update, or a check that could not be completed; warnings
alone leave the exit status at zero. Use `--verbose` to show the evidence behind
passing checks.

The tables below use the stable check ID included by `pdk diag --json`. Find the
ID in the report, apply its remediation, then run `pdk diag` again. When the
configuration section fails, `pdk config --check` provides the individual
`zensical.toml` paths and complete source-project report.

## Environment and installation

\ref{tab-diagnostics-environment-and-installation} explains every environment
and Python-installation result.

| Check ID | Failure or warning means | Author remediation |
|---|---|---|
| `environment.python` | Normally informational. An `environment.inspection` failure instead means Python's executable or prefix could not be inspected. | Run `python --version` and `python -c "import sys; print(sys.executable, sys.prefix)"`. Repair or reselect Python if either command fails, then reopen the terminal. |
| `environment.virtual-env` | `VIRTUAL_ENV` names a different environment from the Python running Prodockit. This commonly follows activating one environment while an older command remains on `PATH`. | Deactivate the stale environment, activate the project's intended environment, and reopen the shell or select that interpreter in the editor. Confirm with `python -c "import sys; print(sys.prefix)"`, then rerun diagnostics. Do not create a `.venv` merely to remove the message: matching pipx, Conda, system-Python, and CI installations are valid. |
| `installation.commands` | `pdk`, `prodockit`, or `zensical` is missing, reports a different version from the distribution loaded by Python, or resolves outside the active Python environment. | Activate the intended environment. Compare `python -m pip show prodockit zensical` with `pdk --version`, `prodockit --version`, and `zensical --version`; use `which` on macOS/Linux or `where` on Windows to find stale commands. Remove the stale installation or put the active environment's scripts directory first on `PATH`, then reinstall with `python -m pip install --upgrade prodockit` if required. |
| `installation.dependencies` | `python -m pip check` found a missing or incompatible installed dependency, or could not run. | Read the named package constraint in the detail. Use `python -m pip check` to reproduce it, then install a compatible set in the active environment. Prefer the versions pinned by the project; do not blindly upgrade one package when another explicitly constrains it. |
| `installation.metadata` | Installed distribution metadata is invalid or the same normalized package name appears in more than one location. This is a warning because unrelated duplicate metadata need not prevent a build. | Run `python -m pip show PACKAGE` for each name shown. Remove obsolete editable installs or duplicate package directories from the active environment. If the duplicate is unrelated and the project builds, record it when requesting support rather than deleting it speculatively. |
| `environment.inspection` / `installation.inspection` | An operating-system or metadata error prevented that whole diagnostic area from being read. Other sections still run. | Use the error detail to correct permissions or the damaged installation. Rerun with `--verbose`; if it persists, attach the JSON report and the output of `python -m pip check` to a support request. |
/// table-caption | <
    attrs: {id: tab-diagnostics-environment-and-installation}

Environment and installation diagnostics
///

## Project configuration and inputs

`project.configuration` loads the same project model used by Prodockit's PDF
pipeline and reuses the complete `pdk config --check` integrity inspection. It
does not replace Zensical's own strict build.

\ref{tab-diagnostics-project-configuration} maps its possible problems to an
author action.

| Problem reported for `project.configuration` | Author remediation |
|---|---|
| The configuration cannot be loaded | Confirm the file exists and is valid TOML or YAML. Pass a non-standard location with `pdk diag -f PATH`. Correct the first parser error before investigating later settings. |
| An obsolete Prodockit setting | Replace it with the setting named by `pdk config --check`; do not keep both old and new names. |
| An unknown or misspelled Prodockit setting or extension | Use the suggested spelling. If the setting belongs to another Zensical extension, keep it in that extension's own table rather than a `prodockit.*` table. |
| A setting has the wrong type or an invalid value | Change it to the boolean, string, list, or non-empty value described by `pdk config --check`. |
| A stylesheet, JavaScript file, navigation page, Markdown image, or configured CSL file is missing | Restore the referenced file or correct its path relative to `zensical.toml`. Generated MathJax assets should be restored with `pdk init-mathjax`; do not commit third-party generated files when the project intentionally ignores them. |
| A configured Mermaid, MathJax, Pandoc, browser, or other renderer is unavailable | Install the project's pinned toolchain with `pdk init-tools`, or correct the configured executable/script path. The rendering-tool section identifies the missing component separately. |
| Back-of-book index generation is enabled without its optional package | Install the project with the index extra: `python -m pip install "prodockit[index]"`. |
| Prodockit syntax is present while its extension is disabled | Enable the named `prodockit.*` extension in `zensical.toml`, or remove syntax the project no longer uses. |
/// table-caption | <
    attrs: {id: tab-diagnostics-project-configuration}

Project configuration and input diagnostics
///

After correcting the source problem, run both checks:

```bash
pdk config --check
pdk diag
```

The first gives the complete configuration report; the second confirms the
configuration alongside the environment and external tools.

## Dependencies and managed files

\ref{tab-diagnostics-dependencies} covers declarations recorded in the project,
rather than packages currently imported by Python.

| Check ID | Failure or warning means | Author remediation |
|---|---|---|
| `dependencies.pins` | A failure means two or more discovered declarations name different versions. With `--online`, a warning means a newer release exists or the package index could not be queried. | For disagreement, run `pdk pins --check --offline`, review every reported declaration, then use `pdk pins --set PACKAGE=VERSION` to move them together. For an available update, rebuild and review output before adopting it. For a lookup warning, retry later or use the deterministic offline form. |
| `dependencies.shared-files` | A file declared in `.prodockit-shared-files.toml` is missing or differs from the installed Prodockit release, or the shared-file manifest is invalid. | Run `pdk shared-files --check --verbose`. Review local changes first; use `pdk shared-files --apply` only when the installed release is the intended source. Move project-specific CSS into the documented project-owned stylesheet before replacing a managed file. |
| `dependencies.inspection` | Files containing version pins or shared-file metadata could not be read. | Correct the path, encoding, manifest syntax, or file permissions named in the detail, then run the narrower `pdk pins --check --offline` and `pdk shared-files --check` commands. |
/// table-caption | <
    attrs: {id: tab-diagnostics-dependencies}

Dependency and managed-file diagnostics
///

## Rendering toolchain

A renderer is a failure only when the current configuration requires it.
Missing unused tools are warnings, so a website-only project does not have to
install the PDF toolchain merely to make diagnostics pass.
\ref{tab-diagnostics-rendering-toolchain} gives the repair for each component.

| Check ID | Failure or warning means | Author remediation |
|---|---|---|
| `renderer.pandoc` | Pandoc is not on `PATH`, does not run, or reports no version. | Install the version pinned by the project and reopen the terminal. Confirm with `pandoc --version`. Bootstrap-managed projects can use `pdk bootstrap --apply`. |
| `renderer.weasyprint` | Importing WeasyPrint failed, including a missing Pango/Cairo native library. | Run `python -c "import weasyprint; print(weasyprint.__version__)"` in the active environment. Install WeasyPrint and the platform native libraries described in the installation guide; ensure the Python package and native architecture match. |
| `renderer.node` | Node is missing or cannot report its version. | Install the project's supported Node version, reopen the terminal, and confirm with `node --version`. |
| `renderer.npm` | npm is missing or cannot report its version, even if Node itself exists. | Repair or reinstall the Node distribution so `npm --version` works. Avoid mixing Node and npm from different installations on `PATH`. |
| `renderer.mermaid` | Authored Markdown uses a Mermaid fence but neither the project-local `mmdc` nor a usable command on `PATH` exists, or `mmdc --version` fails because an npm installation is incomplete. Preserving Zensical's unused Mermaid default does not make the renderer required. | Remove the incomplete `tools/mermaid/node_modules` directory and rerun `prodockit adopt --apply --mermaid`, or run `pdk init-tools` and reinstall its declared Node packages. If `pdf_mmdc_bin` is explicit, correct it to a working executable. Confirm with `mmdc --version`. |
| `renderer.browser` | No explicit Chrome or Chromium executable was found. This remains a warning because Mermaid CLI may use its own downloaded browser. | If Mermaid renders successfully, no action is required. Otherwise install Chrome/Chromium or set `PUPPETEER_EXECUTABLE_PATH` to its executable, then rerun the Mermaid/PDF build. |
| `renderer.mathjax` | Authored Markdown uses mathematical notation but `tools/mathjax/tex2svg.js` or the installed `mathjax-full` inputs are missing. Preserving Zensical's unused Arithmatex default does not make the renderer required. | Run `pdk init-tools` to install the pinned Node inputs. If only website JavaScript is absent, run `pdk init-mathjax` after the install. Do not hand-edit generated vendor files. |
| `renderer.inspection` | An operating-system error prevented the rendering tools from being inspected. | Correct the path or permissions named in the detail. Run each shown executable with `--version`, then rerun `pdk diag --verbose`. |
/// table-caption | <
    attrs: {id: tab-diagnostics-rendering-toolchain}

Rendering-toolchain diagnostics
///

## Repository and template maintenance

Repository checks are read-only. The default form examines local Git and
template metadata only; `--online` adds the remote template comparison.
\ref{tab-diagnostics-repository-and-template} explains each repository result.

| Check ID | Failure or warning means | Author remediation |
|---|---|---|
| `repository.git` | Git is unavailable, the project is not inside a repository, the repository cannot be inspected, or it has no configured remotes. Most of these are warnings because a local document can still render. | Run diagnostics from the project root. Install Git if the project uses repository macros or publishing automation. Use `git remote -v` and the repository host's clone instructions to restore the intended remote; do not invent a remote for an intentionally local project. |
| `repository.template-metadata` | `.prodockit-template.toml` is invalid, `.prodockit-template` is empty or unreadable, or ownership metadata cannot be parsed. Absence of both files is valid for a project that was not created from the template. | Restore the files from version control or repair the exact manifest/stamp error. Do not guess a template commit. For a template-derived project, use the recorded history or ask its maintainer which template revision was applied. |
| `repository.template-update` | With `--online`, a warning means the recorded template revision differs from the template host's current HEAD, or the comparison could not be completed. It is never an automatic failure. | If an update exists, run `pdk template-sync` to preview it, then follow its reviewed `--apply` workflow. If the lookup failed, check network/SSH access and retry; the offline diagnostic remains deterministic and valid. |
| `repository.inspection` | Git or template files raised an operating-system error after the project was found. | Correct the path or permissions named in the detail. Confirm `git status` and `git remote -v` work from the project root, then rerun diagnostics. |
/// table-caption | <
    attrs: {id: tab-diagnostics-repository-and-template}

Repository and template diagnostics
///

## Attach a report to a support request

Generate structured evidence without copying terminal colour or screenshots:

```bash
pdk diag --json > prodockit-diagnostics.json
```

The report shortens project and home-directory paths and removes credentials
embedded in HTTPS remote URLs. Review it before attaching it, as you would any
diagnostic file. Include the command you ran, the build error, operating system,
and whether the failure is local, in CI, or both. Use `--online` only when the
support question concerns published versions or template drift.

Do not attach generated documentation, private source files, credentials, or
repository secrets unless the support channel explicitly requires them and is
approved to receive them.
