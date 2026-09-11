---
icon: lucide/wrench
---

{{ heading_counter_reset(page) }}

<!--
Copyright (c) 2025-2026 Mark Buckwell and contributors
SPDX-License-Identifier: MIT
-->

# Troubleshooting

Find the message or behaviour you can see in the first column below. More than
one check may apply: the same message can have several causes, and one early
problem can produce several later failures. Work through the suggested checks
from left to right, stopping when the problem is resolved.

Start with `pdk diag` whenever it will run. Read the first red `FAIL` before
the later results: one early problem can cause several confusing messages
below it. For example, using the wrong project environment can make correctly
installed packages appear to be missing.

Use Table \ref{tab-install-troubleshooting-symptoms} to match what you see to
the checks most likely to help.

| What you see | Checks that may help |
| --- | --- |
| Prodockit does not start, or it reports an unexpected project or version | • [Open the correct project folder](#directory-holds-projects)<br>• [Activate this project's environment](#wrong-virtual-environment)<br>• [Make the command available](#installtooling-command-not-recognised) |
| `pdk diag` reports the wrong Python or says installed packages are missing | • [Activate this project's environment](#wrong-virtual-environment)<br>• [Recreate it with the correct Python](#wrong-python)<br>• Rerun diagnostics before installing anything |
| An installation appears stuck, times out, or stops part-way through | • [Recover the interrupted installation](#installtooling-download-fails)<br>• [Check the connection](#git-host-unreachable)<br>• Repeat only the failed command or stage |
| Diagram, mathematics, or PDF setup fails | • [Repair Node.js](#installtooling-npm-missing)<br>• [Repair WeasyPrint](#installtooling-weasyprint-libraries)<br>• [Bring project versions into step](#toolchain-not-aligned) |
| Template Sync remains on `Checking this project...`, or Git cannot clone, pull, or push | • [Check the connection to GitLab or GitHub](#git-host-unreachable)<br>• [Check the SSH key](#installtooling-git-permission-denied)<br>• [Check an existing project folder](#installtooling-directory-exists) |
| `pdk diag` reports warnings after Prodockit was upgraded | • [Activate this project's environment](#wrong-virtual-environment)<br>• [Bring project versions into step](#toolchain-not-aligned)<br>• Rerun `pdk diag` |

/// table-caption | <
    attrs: {id: tab-install-troubleshooting-symptoms}

Use the visible behaviour to choose one or more recovery checks
///

## Sudo requires a terminal after authentication {: #sudo-authentication }

If Bootstrap reports `sudo: A terminal is required to authenticate` or
`sudo: interactive authentication is required`, run `sudo -v` in the same
terminal, then resume `pdk boot --apply`. Keep that terminal open throughout
setup. Captured installers retain its authentication context while using
separate process groups for timeout cleanup.

If authentication is still refused, check that the account has sudo access.
Changing sudo's authentication policy or installing another package manager
is not a remedy for this error.

## Open the correct project folder {: #directory-holds-projects }

`pdk diag`, `pdk adopt`, and `pdk template-sync` operate on one project. Run
them from the project directory containing `zensical.toml`, not from the
parent directory that contains several repositories. The refusal looks like:

``` text
Error: /path/to/repos holds projects rather than being one (your-project).
Open a terminal in the project you want brought into step, or cd into it.
```

Enter the named project, activate its environment, and try again:

=== ":material-apple: macOS"

    ``` bash
    cd ~/repos/your-project
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ``` powershell
    Set-Location ~\repos\your-project
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ``` bash
    cd ~/repos/your-project
    source .venv/bin/activate
    ```

## Activate this project's environment {: #wrong-virtual-environment }

This commonly happens after Bootstrap creates a project while the parent
folder's setup environment is still active. A `.venv` is a private Python
installation used by one folder. Diagnostics reports:

``` text
FAIL Active Python is not the project's .venv
```

Deactivate the current environment if necessary, then activate the `.venv`
in the current project:

=== ":material-apple: macOS"

    ``` bash
    deactivate
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ``` powershell
    deactivate
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ``` bash
    deactivate
    source .venv/bin/activate
    ```

If `deactivate` is not recognised, no standard Python environment is active;
run only the activation command. Confirm the result before doing anything
that installs packages:

``` bash
python -c "import sys; print(sys.executable); print(sys.prefix)"
pdk diag
```

Both paths must identify the current project's `.venv`. Do not respond to a
missing-package failure by installing into the parent environment.

## Recreate the environment with the correct Python {: #wrong-python }

Creating an environment inside an existing `.venv` can leave old command
files behind. If the prompt shows `(.venv)` but
`python --version` reports the wrong release, preserve the old directory and
recreate it with the intended interpreter.

=== ":material-apple: macOS"

    ``` bash
    deactivate
    mv .venv .venv-python-backup
    "$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ``` powershell
    deactivate
    Rename-Item .venv .venv-python-backup
    py -3.14 -m venv .venv
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ``` bash
    deactivate
    mv .venv .venv-python-backup
    python3.14 -m venv .venv
    source .venv/bin/activate
    ```

Then check `python --version`, reinstall from `requirements.txt`, and run
`pdk diag`. Keep the backup until the replacement environment has passed.

## Make the command available {: #installtooling-command-not-recognised }

First confirm that you are in the project directory and that its `.venv` is
active. Every new Terminal or PowerShell window needs the environment to be
activated again.

=== ":material-apple: macOS"

    ``` bash
    cd /path/to/your-project
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ``` powershell
    cd C:\path\to\your-project
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ``` bash
    cd /path/to/your-project
    source .venv/bin/activate
    ```

If an operating-system installer has just added Git, Node.js, or Visual Studio
Code, close the terminal, open a new one, return to the project, and activate
`.venv` again. Windows in particular does not add a newly installed command to
terminals that are already open.

On Windows, follow a Bootstrap message headed
`RESTART YOUR TERMINAL — WINDOWS SETTINGS HAVE CHANGED` literally: fully close
Windows Terminal or VS Code, reopen it in the project, and activate the
project's `.venv` again. Opening another tab in the same application may retain
the old environment.

If `pdk --version` still shows an older installation after activating the
correct environment, list every copy the computer can find:

=== ":material-apple: macOS"

    ``` bash
    which -a python pdk prodockit zensical
    rehash
    ```

=== ":fontawesome-brands-windows: Windows"

    ``` powershell
    where.exe python
    where.exe pdk
    where.exe prodockit
    where.exe zensical
    ```

=== ":material-linux: Linux (Ubuntu)"

    ``` bash
    which -a python pdk prodockit zensical
    hash -r
    ```

Inside an active virtual environment, install packages with
`python -m pip ...`; this binds pip to the Python you just checked. During the
initial machine preparation, use `pip` on Windows and Ubuntu and `pip3` on
macOS. If that command is unavailable, try the other spelling.

## Check the connection to GitLab or GitHub {: #git-host-unreachable }

If Template Sync remains at `Checking this project for template updates...`,
interrupt it with ++ctrl+c++ rather than waiting indefinitely. Read the end of
its log:

=== ":material-apple: macOS"

    ``` bash
    tail -80 .prodockit-template.log
    ```

=== ":fontawesome-brands-windows: Windows"

    ``` powershell
    Get-Content .prodockit-template.log -Tail 80
    ```

=== ":material-linux: Linux (Ubuntu)"

    ``` bash
    tail -80 .prodockit-template.log
    ```

If the last entry is a template source with no later Git output, test the exact
host outside Prodockit. Replace the hostname when the log names GitHub.com or
GitLab.com:

``` bash
ssh -T -o BatchMode=yes -o ConnectTimeout=15 git@gitlab.surrey.ac.uk
```

`Could not resolve hostname` means the computer could not turn the site name
into a network address. This is usually called a DNS problem. It happens
before the computer checks an SSH key, so generating another key cannot fix
it. Check that the same site opens in a browser, connect any required
university VPN, and look for an operating-system firewall or network-permission
prompt. Retry the SSH test first; rerun Template Sync only after it works.

An authenticity question on the first successful connection is normal. Check
the displayed host and fingerprint before accepting it. A welcome message
proves that DNS, the network route, and the SSH key now work.

## Check the SSH key {: #installtooling-git-permission-denied }

Test the SSH connection independently:

``` bash
ssh -T git@your-git-host
```

If the host rejects the key, confirm that the private key is loaded into the
SSH agent and that its matching public key is registered with the correct
GitLab or GitHub account. Also check that `git remote -v` contains the expected
host, namespace, and repository name. Do not create another repository merely
because SSH cannot currently see the intended one.

A GitLab.com project may still fetch a public template from GitHub.com. Test
the hostname shown by `.prodockit-template.log`, not only the project's
`origin`. Modern Template Sync releases use the public template transport when
available, but a custom template source can still require its own SSH access.

## Check an existing project folder {: #installtooling-directory-exists }

Do not clone over an existing directory or delete it without reviewing its
contents. Run `git status --short`, `git remote -v`, and
`git log -1 --oneline` inside it. If it is the intended existing project,
continue with [Path 2](manual-install.md#manual-install-path-2). If it is
unrelated, choose a different clone directory or move it to a clearly named
backup first.

## Repair WeasyPrint and its graphics libraries {: #installtooling-weasyprint-libraries }

Activate the project environment and repeat the direct import check:

``` bash
python -c "import weasyprint; print(weasyprint.__version__)"
```

An error ending in `cannot load library` means the platform-specific Pango
libraries are missing or cannot be found. Return to [Stage 4 — Create the
project environment](manual-install.md#stage-4-create-the-project-environment)
and repeat the graphics-library instructions for the operating system.
Installing the Python package again does not install those external libraries.

On Windows, preview Prodockit's guarded repair first:

``` powershell
pdk diag --dry-run --apply-check renderer.weasyprint
```

If the proposed Pango directory and architecture are correct, apply only that
repair:

``` powershell
pdk diag --apply --apply-check renderer.weasyprint
```

Windows native setup uses the same bounded MSYS2 recovery in Adopt, guided
Bootstrap and this repair. It performs a full MSYS2 upgrade before installing
Pango, so close other MSYS2 terminals and package managers first. Signature
errors trigger a refresh of existing signing keys, then a signed keyring update
and full upgrade if the error persists. Signature checks stay enabled.

If recovery stops, review `%LOCALAPPDATA%\prodockit\logs\msys2-setup.log`
for the selected architecture, MSYS2 directory, failed phase and exit status.
Check the system clock and [MSYS2's update guidance](https://www.msys2.org/docs/updating/).
A lock or unverified process shutdown stops automatic retries; wait for other
installers to finish. Do not delete lock files, disable signature checks or
remove the MSYS2 installation to work around the error.

The DLL architecture must match `python.exe`, not necessarily the computer.
An x64 Python requires `C:\msys64\ucrt64\bin`; an ARM64 Python requires the
CLANGARM64 libraries. Mixing them commonly produces Windows error `0xc1`.

If setting the value manually in PowerShell, the variable name requires the
`$env:` prefix:

``` powershell
$env:WEASYPRINT_DLL_DIRECTORIES = 'C:\msys64\ucrt64\bin'
[Environment]::SetEnvironmentVariable('WEASYPRINT_DLL_DIRECTORIES', 'C:\msys64\ucrt64\bin', 'User')
```

Typing `WEASYPRINT_DLL_DIRECTORIES = ...` without `$env:` attempts to run a
command with that name. Check the import with Python; do not type
`WeasyPrint = 69.0`, which invokes the WeasyPrint command with `=` as an input
filename:

``` powershell
python -c "import weasyprint; print(weasyprint.__version__)"
```

If the value was persisted but not active in the current PowerShell, close the
terminal completely, reopen it, activate `.venv`, and rerun `pdk diag`.

## Repair the Node.js installation {: #installtooling-npm-missing }

Open a new terminal first, then check both commands:

``` bash
node --version
npm --version
```

If only `npm` is missing, return to [Install
Node.js](manual-install.md#install-nodejs) and use the supported installer for
the operating system rather than combining Node.js from one source with npm
from another.

If Adopt stops with `mermaid was selected but npm is not available`, no
project rollback is needed. Install or repair Node.js, open a new terminal,
activate the project environment, confirm both version commands above, and
rerun `pdk adopt --apply`. Completed Adopt stages are detected and are not
needlessly repeated.

## Recover a failed or interrupted installation {: #installtooling-download-fails }

A timeout, connection reset, or temporary `503` normally does not require the
project or `.venv` to be removed. Check the network or university VPN, wait
briefly, and repeat only the failed installation command. Package managers
usually recognise components that finished successfully and continue with the
missing work.

Bootstrap hides routine installer output and shows how long the current
command has been running. If a Homebrew, pip, npm, apt, winget, or font command
has made no progress for an unusually long time, interrupt it once with
++ctrl+c++. Do not interrupt while the package manager says it is writing,
linking, or configuring files.

Run the failed command again. This recovered the Homebrew font installation
during testing:

``` bash
brew install --cask font-inter font-jetbrains-mono
```

Before repeating a larger stage, check what completed. Useful examples are:

``` bash
brew list --formula pandoc pango
brew list --cask font-inter font-jetbrains-mono
python -m pip check
npm --version
```

Bootstrap and Adopt are designed to resume: rerunning them rechecks completed
work and continues from the missing stage. Preserve `.venv` and the repository
unless diagnostics specifically identifies the environment itself as corrupt.

## Bring the project versions into step {: #toolchain-not-aligned }

After upgrading Prodockit, diagnostics may report both a declared pin outside
the supported combination and an Adopt integration stage. These are warnings,
not evidence that the installation failed. Follow the named tools in order:

``` bash
pdk pins
pdk adopt --dry-run
pdk adopt --apply
pdk diag
```

Review and accept the tested defaults in Pins, review Adopt's exact files
before applying them, and rerun diagnostics. A template project can instead
start with `pdk template-sync`; its preview shows the compatible Prodockit
release and the Adopt stages it will offer to apply before the template update.

Do not upgrade Pandoc or another renderer simply because a newer release
exists. Keep the version declared by the installed Prodockit combination—for
the current release, Pandoc 3.10.1—until Pins or diagnostics reports a changed
tested default.

## Check PDF fonts {: #installtooling-fonts }

If the PDF uses an unexpected font, or Bootstrap says that fonts could not be
verified, distinguish these two cases:

- **Missing:** the PDF font resolver selected a substitute instead of Inter or
  JetBrains Mono. Run `pdk adopt --apply` and approve the PDF runtime repair.
- **Unverified:** the inspection command could not run or returned no usable
  evidence. This does not prove the fonts are absent; do not repeatedly reinstall
  fonts just because their per-user directory is empty.

Check the actual family selected for each font:

```bash
fc-match -f "%{family}" Inter
fc-match -f "%{family}" "JetBrains Mono"
```

The results should name the requested families, not substitutes such as DejaVu
Sans. The font resolver includes configured system and per-user locations.
If `fc-match` is not found, macOS users can run `brew install fontconfig`;
Ubuntu users can run `sudo apt install fontconfig`. On Windows, run
`pdk adopt --apply` to repair the selected Pango runtime and follow its
environment-refresh instructions. Then rerun Bootstrap or Adopt to verify.

## Correct diagnostic findings {: #diagnostic-corrections }

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
pipeline and hosting settings in [the publishing stage](getting-started.md#stage-6-save-and-publish-optional).
Normal `pdk diag` does not change files, repository settings or hosting settings.

## Publish a document {: #troubleshooting-installs-next }

After correcting the problem, repeat the command that stopped and run
`pdk diag` again. When diagnostics passes and the website and PDF build
successfully, continue with [Publish a document](publishing.md).
