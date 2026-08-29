# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The eighteen stages of a full install, as check/plan pairs.

Every stage answers two questions and performs neither: `check` decides
whether it is already done, `plan` says what would make it done. Nothing
here runs an installer - see `prodockit.bootstrap.model` for why that
split is the whole testing strategy.

Twelve of the eighteen are platform-independent (SSH keys, the ssh
config stanza, the agent, cloning, resetting the history, repointing the
remote, the project's commit identity and environment, VS Code
extensions and settings, the citation style, MathJax for the website),
which is most of the work written once. That
is the argument for a stage abstraction over three separate per-platform
scripts.

Two are deliberately **not automatable at all**: uploading an SSH public
key, and creating the project on the host. Both need an authenticated
human in a browser, and the alternative - a Personal Access Token typed
into a script aimed at first-time students - trades two well-signposted
clicks for a credential-handling problem. They are guide-and-verify
instead: tell the reader exactly what to do, then *check whether it
worked*, which is the half a written instruction can never do
(prodockit-extensions#217).
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from prodockit import mathjax, tools
from prodockit.bootstrap.model import (
    MACOS,
    SSH_NO_PROMPT_OPTIONS,
    UBUNTU,
    WINDOWS,
    CheckResult,
    CommandResult,
    Context,
    Plan,
    Stage,
    Status,
    windows_system_ssh,
)

#: The VS Code extensions the User Guide installs. Kept here rather than
#: in the template so bootstrap can check them without a project.
#:
#: These are the four the install guide requires, and only those. Code
#: Spell Checker used to be here in place of two of them, which was
#: wrong twice over: it comes from the *optional* tooling page, whose
#: opening line is "You don't need any of this", while Even Better TOML
#: and LTeX+ - which the guide does require - were missing entirely
#: (prodockit-extensions#248).
#:
#: Marketplace identifiers, checked rather than guessed. `valentjn.
#: vscode-ltex` is the obvious name for LTeX and returns 404 - the
#: maintained fork is LTeX+, published under `ltex-plus`.
VSCODE_EXTENSIONS = (
    "ms-python.python",
    "zensical.zensical-studio",
    "tamasfe.even-better-toml",
    "ltex-plus.vscode-ltex-plus",
)

#: Minimum Node major version - what the automated builds use.
NODE_MAJOR = 22

#: How long apt should wait for the dpkg lock rather than giving up.
#:
#: apt's default is to fail immediately if another process holds it, and
#: on a freshly installed Ubuntu that other process is very often
#: `unattended-upgrades`, which starts on boot and can hold the lock for
#: minutes. A reader who runs bootstrap on a machine they have just
#: installed gets:
#:
#:     Error: Unable to acquire the dpkg frontend lock
#:     (/var/lib/dpkg/lock-frontend), is another process using it?
#:
#: which reads like a broken machine rather than "something else is
#: mid-update, wait a moment" (prodockit-extensions#244). Waiting is what
#: a human would do, so apt is told to do it.
APT_LOCK_WAIT_SECONDS = 600
APT_LOCK_OPTION = ("-o", f"DPkg::Lock::Timeout={APT_LOCK_WAIT_SECONDS}")


def _apt(*args: str) -> list[str]:
    """One `sudo apt` command, set to wait for the dpkg lock."""
    return ["sudo", "apt", *APT_LOCK_OPTION, *args]


#: The same, for the two places apt is run inside a shell string.
APT_SH = "sudo apt " + " ".join(APT_LOCK_OPTION)

#: The debconf answer the VS Code package stops to ask for:
#:
#:     Add Microsoft apt repository for Visual Studio Code?  <Yes> <No>
#:
#: `apt install -y` does not answer it - `-y` agrees to apt's own
#: questions, not to a package's debconf ones - so a clean Ubuntu run sat
#: waiting on a dialog nobody could see, because bootstrap captures its
#: subprocesses (prodockit-extensions#428).
#:
#: Answered `true` deliberately rather than suppressed: that repository is
#: how VS Code then updates through apt, and declining would pin a reader
#: to whichever build the `.deb` happened to be.
VSCODE_MICROSOFT_REPO = "code code/add-microsoft-repo boolean true"

#: Where the answer is written for `debconf-set-selections` to read.
VSCODE_DEBCONF_FILE = "/tmp/code.debconf"

#: Written by Python rather than by `echo ... | sudo debconf-set-selections`.
#:
#: The pipe is the problem, not the echo: it puts `sudo` inside a shell,
#: which is the arrangement #244 and #287 took apart - a sudo timestamp
#: expiring there prompts where nobody is watching, and this stage exists
#: to stop exactly that kind of invisible wait. The same one-liner shape
#: as the settings stage, so `sudo` stays the first word of its own
#: command.
_WRITE_DEBCONF = (
    "import pathlib, sys; "
    "pathlib.Path(sys.argv[1]).write_text(sys.argv[2] + chr(10), encoding='utf-8')"
)

#: Where MSYS2 puts the MinGW64 libraries WeasyPrint draws text through.
MSYS2_ROOT = r"C:\msys64"
MSYS2_BIN = MSYS2_ROOT + r"\mingw64\bin"
_MSYS2_BASH = MSYS2_ROOT + r"\usr\bin\bash.exe"

#: Where MSYS2 has been found. `C:\msys64` is its installer's default,
#: not a promise, and the arm64 installer is a separate build again.
_MSYS2_ROOTS = (
    r"$env:SystemDrive\msys64",
    r"$env:SystemDrive\msys2",
    r"$env:LOCALAPPDATA\Programs\msys64",
    r"$env:ProgramFiles\msys64",
    r"C:\tools\msys64",
)

#: Pango, per MSYS2 environment. There is no MINGW64 on an arm64 install -
#: its native environment is CLANGARM64, whose packages are named
#: differently and whose DLLs live in a different directory
#: (prodockit-extensions#393). `mingw-w64-clang-aarch64-pango` was
#: confirmed present in that repository before being named here:
#: https://packages.msys2.org/packages/?repo=clangarm64&query=pango
_MSYS2_ENVIRONMENTS = {
    "arm64": ("clangarm64", "mingw-w64-clang-aarch64-pango"),
    "other": ("mingw64", "mingw-w64-x86_64-pango"),
}

_PDKBOOT_MSYS2_ENVIRONMENTS = {
    "arm64": ("clangarm64", "mingw-w64-clang-aarch64-pango"),
    # UCRT64 is MSYS2's current x64 default. MINGW64 began deprecation in
    # 2026, and CPython itself uses the Universal C Runtime on supported
    # Windows releases, so this is also the closer match for cffi-loaded DLLs.
    "other": ("ucrt64", "mingw-w64-ucrt-x86_64-pango"),
}

_PYTHON_PE_MACHINE = (
    "from pathlib import Path; import sys; "
    "data=Path(sys.executable).read_bytes(); "
    "offset=int.from_bytes(data[60:64], 'little'); "
    "print(hex(int.from_bytes(data[offset+4:offset+6], 'little')))"
)


def _windows_python_is_arm64(context: Context) -> bool:
    """Whether the Python process that will load Pango is native ARM64.

    Windows on ARM can run x64 Python. Such a process must load x64 DLLs,
    regardless of the host's native architecture; selecting from
    PROCESSOR_ARCHITEW6432 instead installs an ARM64 Pango that cffi cannot
    load into that emulated process.
    """
    result = context.runner.run([sys.executable, "-c", _PYTHON_PE_MACHINE])
    return result.ok and result.stdout.strip().lower() == "0xaa64"


def _winget(
    package_id: str,
    version: str = "",
    *,
    resilient: bool = False,
) -> list[str]:
    """One `winget install`, wired so it cannot stop for a human.

    The two `--accept-*` flags are the point. winget asks for agreement
    to its source terms the first time it is used, and to a package's
    terms when one carries them - and it asks on the terminal, so a
    captured, timed subprocess simply waits. That is the same failure
    `sudo` produced on Ubuntu (prodockit-extensions#243), reached by a
    different route, and it would have met every Windows reader on their
    very first stage.

    `-e` matches the id exactly. Without it an ambiguous name is another
    question winget stops to ask.

    `--source winget` is just as important as the exact id. These packages
    all come from the community repository; without an explicit source,
    winget also queries `msstore`, and an unrelated Store DNS or service
    failure aborts an otherwise valid community-repository install.

    `version` pins the install where the version is one this project
    cares about rather than one it merely needs - pandoc decides how the
    PDF renders, so a machine bootstrap just set up should agree with
    what CI publishes (#454). Ubuntu has always pinned pandoc by
    downloading an exact release; this is the same commitment, and it
    fails the same way if the version is not in the repository, which is
    visible rather than silent.
    """
    return [
        "winget",
        "install",
        "--id",
        package_id,
        *(["--version", version] if version else []),
        "-e",
        "--source",
        "winget",
        "--accept-source-agreements",
        "--accept-package-agreements",
        *(["--no-upgrade", "--silent", "--disable-interactivity"] if resilient else []),
    ]


def _winget_upgrade(package_id: str, version: str = "") -> list[str]:
    """An explicit, non-interactive upgrade for an approved pdkboot plan."""
    return [
        "winget",
        "upgrade",
        "--id",
        package_id,
        *(["--version", version] if version else []),
        "-e",
        "--source",
        "winget",
        "--silent",
        "--accept-source-agreements",
        "--accept-package-agreements",
        "--disable-interactivity",
    ]


def _winget_repair(package_id: str) -> list[str]:
    """Repair an installed package without treating it as a fresh install."""
    return [
        "winget",
        "repair",
        "--id",
        package_id,
        "-e",
        "--source",
        "winget",
        "--silent",
        "--accept-source-agreements",
        "--accept-package-agreements",
        "--disable-interactivity",
    ]


#: The fonts this template's PDF uses by default.
#:
#: Easy to leave out and hard to notice: the website loads them from a
#: CDN when a page is viewed, but a PDF has to embed the actual files,
#: and WeasyPrint substitutes a fallback **silently** rather than failing
#: when they are absent. So the build succeeds, the PDF looks plausible,
#: and the only symptom is a test reporting `No 'Inter' font found`
#: (prodockit-userguide#101, prodockit-extensions#249).
PDF_FONT_PACKAGES = ("fonts-inter", "fonts-jetbrains-mono")
PDF_FONT_CASKS = ("font-inter", "font-jetbrains-mono")
WINDOWS_INTER_URL = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
WINDOWS_INTER_SHA256 = "9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e"
WINDOWS_JETBRAINS_MONO_URL = (
    "https://github.com/JetBrains/JetBrainsMono/releases/download/"
    "v2.304/JetBrainsMono-2.304.zip"
)
WINDOWS_JETBRAINS_MONO_SHA256 = (
    "6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf"
)

#: The pandoc version this family of repos pins. Set in one place so a
#: bump does not leave bootstrap behind - the CI workflows pin the same
#: version independently, and `prodockit pins` checks the two agree.
PANDOC_VERSION = "3.10.1"

#: The minimum pandoc major version that renders code blocks correctly.
#: Ubuntu's own package lags well behind upstream - 2.x on some LTS
#: releases - and a pandoc old enough to be a different major version
#: renders code blocks as justified prose (#207).
PANDOC_MIN_MAJOR = 3


def _ok(detail: str = "") -> CheckResult:
    return CheckResult(Status.OK, detail)


def _missing(detail: str) -> CheckResult:
    return CheckResult(Status.MISSING, detail)


def _wrong(detail: str) -> CheckResult:
    return CheckResult(Status.WRONG, detail)


def _installed(context: Context, command: str, *args: str) -> bool:
    """Whether `command` runs at all - the usual "is this on PATH?" probe."""
    return context.runner.run([command, *(args or ("--version",))]).ok


def _unknown(detail: str) -> CheckResult:
    return CheckResult(Status.UNKNOWN, detail)


def _blocked(detail: str) -> CheckResult:
    return CheckResult(Status.BLOCKED, detail)


#: Why the two stages after `fresh-history` wait for it.
#:
#: Said in full rather than as "waiting for fresh-history", because the
#: state it describes is dangerous on its own: a clone still pointing at
#: the template will push *into the template* for anyone who has write
#: access to it, and the template is public and cloned by every new
#: reader (prodockit-extensions#311).
_STILL_THE_TEMPLATE = (
    "this clone's origin is still the template. Do the 'A history of your "
    "own' stage first - it deletes the template's history and its remote, "
    "which would throw away anything done here"
)


def _origin_is_the_template(context: Context) -> bool:
    """Whether the clone has not been separated from the template yet.

    Asked by the two stages that follow the reset, so neither acts on a
    repository the reset is about to empty. A clone made from
    `source_url` never matches - its origin is the reader's own - so that
    path is untouched.
    """
    return _origin_url(context) == context.host.template_remote


def _origin_url(context: Context) -> str:
    """The clone's `origin`, or empty when that cannot be established.

    Empty means *unknown* - no clone, no remote, or a git that refused to
    answer - and never "some other repository". Callers turn a known
    origin into a decision; they must not read silence as one.
    """
    project = context.config.resolved_project_dir(context.home)
    if not (project / ".git").exists():
        return ""
    origin = context.runner.run(
        [git_command(context), "-C", str(project), "remote", "get-url", "origin"]
    )
    return origin.stdout.strip() if origin.ok else ""


def _prodockit_command() -> list[str]:
    """The prodockit that is running, addressed so PATH cannot lose it.

    Bootstrap is itself a prodockit command, and two stages run further
    prodockit commands: `sync-repo` when it repoints a clone, and
    `init-mathjax`. Naming them bare asks the machine to find prodockit a
    second time - and on Windows that failed outright, stopping a setup
    at stage 12 with `prodockit: not found` on a machine where prodockit
    was plainly installed and driving the run
    (prodockit-extensions#371). A virtual environment's scripts are
    reachable when it launches one; they are not necessarily on the
    `PATH` a child process inherits.

    `sys.executable` is that environment's own interpreter, so the module
    form runs the install already doing the work - never a different
    prodockit that happens to come earlier on PATH, and never none.
    """
    if not sys.executable:  # pragma: no cover - embedded interpreters only
        return ["prodockit"]
    return [sys.executable, "-m", "prodockit"]


def _needs_config(context: Context, *required: str) -> CheckResult | None:
    """`UNKNOWN` if any of `required` is unanswered, else None.

    Without this a stage builds a URL out of empty strings and reports it
    as missing - `git@gitlab.surrey.ac.uk:/.git is not reachable` tells a
    first-time reader nothing except that something is broken, and it is
    not: they simply have not answered the questions yet.
    """
    blank = [name for name in required if not getattr(context.config, name, "")]
    if blank:
        return _unknown(f"needs {' and '.join(blank)}")
    return None


def _key_path(context: Context) -> Path:
    """This host's own key file.

    Per-host rather than one shared key, matching the User Guide: a
    student with both a university GitLab and a personal GitHub account
    should not have one key granting access to both.
    """
    return context.home / ".ssh" / f"id_ed25519_{context.host.key_suffix}"


# ---------------------------------------------------------------------------
# 1. VS Code
# ---------------------------------------------------------------------------


#: Where each platform's installer puts the application itself. The
#: application and the `code` shell command are separate things, and on
#: macOS installing the first does not give you the second.
_VSCODE_APP_PATHS = {
    MACOS: ("/Applications/Visual Studio Code.app",),
    UBUNTU: ("/usr/share/code", "/snap/code"),
    WINDOWS: (
        r"C:\Program Files\Microsoft VS Code",
        r"~\AppData\Local\Programs\Microsoft VS Code",
    ),
}

#: What to ask once that has been shown. "Tell me when that is done"
#: does not say which of several things, and this one is easy to skip.
_VSCODE_CONFIRM = "Have you installed the code command in PATH from VS Code?"

#: How to add the `code` command once the application is installed.
_VSCODE_SHELL_COMMAND_HELP = (
    "In VS Code, open the Command Palette (Cmd+Shift+P / Ctrl+Shift+P) and run "
    "Shell Command: Install 'code' command in PATH."
)


def _vscode_app_installed(context: Context) -> bool:
    for raw in _VSCODE_APP_PATHS.get(context.platform, ()):
        path = Path(raw.replace("~", str(context.home), 1)) if raw.startswith("~") else Path(raw)
        if context.exists(path):
            return True
    return False


#: Where the Git for Windows installer puts `git.exe`. Same reasoning as
#: `_VSCODE_APP_PATHS`: the installer adds it to `PATH`, but `PATH` is
#: read when a process starts, so a shell that has not been reopened
#: since cannot see it (prodockit-extensions#390).
#: Read from `prodockit.tools`, which `sync-repo` and the macros use
#: too. Two lists would be two answers to the same question about the
#: same machine, and #451 was exactly that divergence: the stages found
#: git by full path while `sync-repo`, looking only at PATH, could not
#: run it at all.
_GIT_APP_PATHS = {WINDOWS: tools.WINDOWS_PATHS["git"]}


def git_command(context: Context) -> str:
    """How to invoke git: `git`, or its full path when PATH cannot see it.

    Twenty-odd stages run git. A Windows machine where git was installed
    a moment ago has it on the *machine's* PATH and not on this process's,
    so every one of them failed - and the git stage reported "git is not
    installed" about a machine winget then said was already up to date
    (prodockit-extensions#390).

    The same answer as `vscode_command` for the same reason (#292): find
    the executable where the installer puts it and use it by its full
    path, rather than telling the reader to open a new terminal and start
    the run again.
    """
    if _installed(context, "git"):
        return "git"
    for raw in _GIT_APP_PATHS.get(context.platform, ()):
        path = Path(raw.replace("~", str(context.home), 1)) if raw.startswith("~") else Path(raw)
        if context.exists(path):
            return str(path)
    return "git"


def _git_is_available(context: Context) -> bool:
    """Whether git can be run at all, by either route."""
    return _installed(context, "git") or git_command(context) != "git"


def _found_where_installed(context: Context, name: str) -> str:
    """`name`, or its full path when this process's PATH cannot see it.

    The same answer as `git_command` and `vscode_command`, for the same
    reason and by the same list (prodockit-extensions#450). A `winget
    install` updates the machine's PATH; a process already running does
    not get it - so `pandoc --version` failed on the machine that had
    just installed pandoc, and the stage reported "pandoc is not
    installed" about software that was there.

    That is not merely a cosmetic miss. The stage then offers to install
    it, winget answers "already up to date", and the check fails again -
    so the run cannot move on at all (#390 records this happening with
    git).
    """
    if _installed(context, name):
        return name
    for path in tools.candidates(name, context.home):
        if context.exists(path):
            return str(path)
    return name


def pandoc_command(context: Context) -> str:
    """How to invoke pandoc: `pandoc`, or where winget put it."""
    return _found_where_installed(context, "pandoc")


def node_command(context: Context) -> str:
    """How to invoke node: `node`, or where winget put it.

    `npm_command` already exists for node's other Windows problem -
    `CreateProcess` never applies `PATHEXT`, so a bare `npm` cannot find
    `npm.cmd` (#371). This is the missing half of that pair.
    """
    return _found_where_installed(context, "node")


#: Where each platform's install puts the `code` CLI itself, as opposed
#: to the application. On macOS these are two different things and only
#: one of them is on `PATH`: the app is installed by dragging it to
#: Applications, and the command arrives only when somebody runs "Shell
#: Command: Install 'code' command in PATH" from inside it
#: (prodockit-extensions#424). The binary is there the whole time.
_VSCODE_CLI_PATHS: dict[str, tuple[str, ...]] = {
    MACOS: (
        "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
        "~/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
    ),
    UBUNTU: (
        "/usr/share/code/bin/code",
        "/snap/bin/code",
    ),
    WINDOWS: (
        r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
        r"~\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd",
    ),
}


def vscode_command(context: Context) -> str | None:
    """How to invoke VS Code's CLI, or None if it cannot be found.

    `code` when it is on `PATH`, which is the ordinary answer everywhere.

    There is a second answer on every platform, and it matters.

    On Windows the installer adds `code` to `PATH` itself - but `PATH` is
    read when a process starts, so the shell that just ran `winget
    install` cannot see it. The check therefore failed on a machine where
    VS Code was installed perfectly well, and offered a Command Palette
    action that does not exist there (prodockit-extensions#292).

    On macOS the application and the command are two different things.
    The app is installed by dragging it to Applications; `code` arrives
    only when somebody runs "Shell Command: Install 'code' command in
    PATH" from inside it, which is a step readers routinely have not
    taken - and the binary was sitting in the app bundle the whole time
    (#424).

    Rather than tell the reader to open a new terminal, or to go and do
    something the machine can do without them, the executable is looked
    for where the install puts it and used by its full path. The
    extensions stage then works in this session too. `None` means it
    genuinely is not there, and the Command Palette step is then the
    right advice rather than a guess.
    """
    if _installed(context, "code"):
        return "code"
    for raw in _VSCODE_CLI_PATHS.get(context.platform, ()):
        expanded = raw.replace("~", str(context.home), 1) if raw.startswith("~") else raw
        if context.exists(Path(expanded)):
            return str(Path(expanded))
    return None


#: Where Node's installer puts `npm.cmd` on Windows.
_NPM_PATHS = (
    r"C:\Program Files\nodejs",
    r"~\AppData\Roaming\npm",
)


def npm_command(context: Context) -> str:
    """How to invoke npm, falling back to its full path on Windows.

    Same trap as VS Code's CLI, and for the same reason (#292, #295).
    `npm` on Windows is `npm.cmd`, and Python's `subprocess` uses
    `CreateProcess`, which does not apply `PATHEXT` - so a bare `npm`
    is "not found" on a machine where Node is installed correctly.

    Returns `npm` unchanged when that works, or when nothing better can
    be found: a command that fails as `npm` at least fails under the
    name the reader knows.
    """
    if context.platform != WINDOWS or _installed(context, "npm"):
        return "npm"
    for raw in _NPM_PATHS:
        expanded = raw.replace("~", str(context.home), 1) if raw.startswith("~") else raw
        candidate = Path(expanded) / "npm.cmd"
        if context.exists(candidate):
            return str(candidate)
    return "npm"


def _check_vscode(context: Context) -> CheckResult:
    """Distinguishes the application from the `code` shell command.

    They are separate installs, and on macOS the cask gives you only the
    first - the second comes from a Command Palette action. Treating a
    missing `code` as a missing VS Code reported "not installed" on a
    machine with it plainly installed, and then tried to reinstall the
    app, which fails outright:

        Error: It seems there is already an App at
        '/Applications/Visual Studio Code.app'.

    That is precisely what `WRONG` is for - present, but not usable for
    what the later stages need it for.
    """
    command = vscode_command(context)
    if command == "code":
        return _ok()
    if command is not None and context.platform == WINDOWS:
        # Found where the installer puts it, just not visible to this
        # process yet - which is not a fault to report, and not something
        # to send the reader to a Command Palette over (#292).
        return _ok(f"{command} (PATH picks it up in a new terminal)")
    if command is not None:
        # Found *inside the application*, which is not on `PATH` and will
        # not be - so the Windows wording would be untrue here. Bootstrap
        # can drive VS Code perfectly well by this path, so nothing is
        # blocked; the reader is told how to get `code` in their own
        # terminal, which is a convenience rather than a prerequisite
        # (prodockit-extensions#424).
        return _ok(
            f"{command} - `code` itself is not on PATH. For your own terminal, run "
            "'Shell Command: Install 'code' command in PATH' from VS Code's "
            "Command Palette"
        )
    if _vscode_app_installed(context):
        return _wrong("VS Code is installed, but the `code` command is not on PATH")
    return _missing("VS Code is not installed")


def _deb_arch(context: Context) -> str:
    """This machine's architecture, as VS Code's download URL spells it.

    `dpkg` says `amd64` where the URL says `x64`; `arm64` agrees with
    itself, which is what an Apple-silicon VM reports. Asked of the
    machine rather than assumed, and asked at plan time so the command
    shown to the reader names the architecture they are on.

    Falls back to `x64` when dpkg cannot be asked - the commonest
    architecture, and a better guess than an empty URL.
    """
    result = context.runner.run(["dpkg", "--print-architecture"])
    reported = result.stdout.strip() if result.ok else ""
    return "x64" if reported in ("amd64", "") else reported


def _plan_vscode(context: Context) -> Plan:
    # Installed already: the only thing missing is the shell command, and
    # reinstalling the application would fail rather than supply it.
    if _vscode_app_installed(context):
        return Plan(
            instructions=[_VSCODE_SHELL_COMMAND_HELP],
            confirm=_VSCODE_CONFIRM,
        )
    if context.platform == MACOS:
        return Plan(
            commands=[["brew", "install", "--cask", "visual-studio-code"]],
            # After the install: the Command Palette being asked for is
            # the one in the application brew has just put there (#230).
            follow_up=[_VSCODE_SHELL_COMMAND_HELP],
            confirm=_VSCODE_CONFIRM,
        )
    if context.platform == UBUNTU:
        # Downloaded rather than asked for (#233). The old plan told the
        # reader to fetch a .deb from the website and then ran
        # `apt install ./code.deb` - a file that never exists under that
        # name anywhere: the download is `code_1.132.0-…_arm64.deb`, and
        # it lands in ~/Downloads rather than the working directory.
        #
        # `linux-deb-$arch/stable` is Microsoft's own permanent redirect
        # to the current release, so there is no version to pin and go
        # stale. dpkg names the architecture as `amd64`, where VS Code's
        # URL calls the same thing `x64`; arm64 agrees with itself, which
        # is what a Parallels VM on an Apple-silicon Mac reports.
        # The architecture is resolved here rather than in the shell, so
        # the command a reader is asked to approve names *their* machine.
        # It carried `case "$arch" in amd64) arch=x64 ;; esac`, which
        # reads as a hardcoded target even though it only maps dpkg's
        # name onto VS Code's - and asking somebody to approve a command
        # they must parse to trust is asking too much (#287).
        url = f"https://update.code.visualstudio.com/latest/linux-deb-{_deb_arch(context)}/stable"
        return Plan(
            commands=[
                _apt("install", "-y", "curl"),
                # Two commands rather than one shell line: the download
                # needs no privileges and the install does, so splitting
                # them keeps `sudo` at the front of a command where it
                # can be seen - and where a timestamp expiring mid-run
                # prompts visibly rather than inside a shell nobody is
                # watching (#287, #244).
                ["curl", "-fsSL", "-o", "/tmp/code.deb", url],
                # Answered before the install rather than during it, so
                # the reader approves the choice with everything else
                # instead of meeting it alone in a dialog (#428).
                [
                    sys.executable,
                    "-c",
                    _WRITE_DEBCONF,
                    VSCODE_DEBCONF_FILE,
                    VSCODE_MICROSOFT_REPO,
                ],
                ["sudo", "debconf-set-selections", VSCODE_DEBCONF_FILE],
                _apt("install", "-y", "/tmp/code.deb"),
            ]
        )
    return Plan(commands=[_winget("Microsoft.VisualStudioCode", resilient=context.pdkboot)])


# ---------------------------------------------------------------------------
# 2. Git, installed *and* configured
# ---------------------------------------------------------------------------


def _check_git(context: Context) -> CheckResult:
    if not _git_is_available(context):
        return _missing("git is not installed")
    git = git_command(context)
    name = context.runner.run([git, "config", "--global", "user.name"])
    email = context.runner.run([git, "config", "--global", "user.email"])
    unset = [
        label
        for label, result in (("user.name", name), ("user.email", email))
        if not result.ok or not result.stdout.strip()
    ]
    if unset:
        # Installed but unusable: commits would be attributed to nobody, or
        # rejected outright. That is `WRONG`, not `MISSING` - telling the
        # reader to install git they already have would send them the wrong
        # way entirely.
        return _wrong(f"git is installed but {' and '.join(unset)} are not set")
    if context.pdkboot and context.platform == WINDOWS:
        ssh_command = context.runner.run([git, "config", "--global", "core.sshCommand"])
        configured = ssh_command.stdout.strip().replace("\\", "/").lower()
        expected = windows_system_ssh().lower()
        if not ssh_command.ok or configured != expected:
            return _wrong(
                "git is installed and has an identity, but is not configured to use Windows OpenSSH"
            )
    found = "" if git == "git" else f" - {git} (PATH picks it up in a new terminal)"
    return _ok(f"{name.stdout.strip()} <{email.stdout.strip()}>{found}")


def _plan_git(context: Context) -> Plan:
    install = {
        MACOS: [["brew", "install", "git"]],
        UBUNTU: [_apt("update"), _apt("install", "-y", "git")],
        WINDOWS: [_winget("Git.Git", resilient=context.pdkboot)],
    }[context.platform]
    configure = [
        [git_command(context), "config", "--global", "user.name", context.config.full_name],
        [git_command(context), "config", "--global", "user.email", context.config.email],
    ]
    if context.pdkboot and context.platform == WINDOWS:
        configure.append(
            [
                git_command(context),
                "config",
                "--global",
                "core.sshCommand",
                windows_system_ssh(),
            ]
        )
    # Only install if it is actually absent - a rerun repairing unset
    # identity should not reinstall git underneath a working one.
    if _installed(context, "git") or (context.pdkboot and _git_is_available(context)):
        return Plan(commands=configure)
    return Plan(commands=[*install, *configure])


# ---------------------------------------------------------------------------
# 3. SSH keypair (platform-independent)
# ---------------------------------------------------------------------------


def _ssh_key_file_is_usable(context: Context, path: Path) -> bool:
    """Whether an existing key half is non-empty and readable by OpenSSH."""
    if not path.is_file() or not path.stat().st_size:
        return False
    return context.runner.run(["ssh-keygen", "-lf", str(path)]).ok


def _check_ssh_key(context: Context) -> CheckResult:
    private = _key_path(context)
    public = private.with_suffix(".pub")
    if context.pdkboot:
        private_ready = _ssh_key_file_is_usable(context, private)
        public_ready = _ssh_key_file_is_usable(context, public)
    else:
        private_ready = private.exists()
        public_ready = public.exists()
    if private_ready and public_ready:
        return _ok(str(private))
    if private.exists() or public.exists():
        return _wrong(f"only half the keypair exists at {private}")
    return _missing(f"no keypair at {private}")


def _create_ssh_dir(context: Context) -> list[list[str]]:
    """Commands that make `~/.ssh` exist, or none if it already does.

    `ssh-keygen` does not create the directory it is asked to write into,
    and fails with an error naming the *key* rather than the missing
    folder (prodockit-extensions#318):

        Saving key "C:\\Users\\you\\.ssh\\id_ed25519_github" failed:
        No such file or directory

    Windows is where this bites, because macOS and Linux tend to have
    `~/.ssh` already from some earlier ssh use - but a genuinely fresh
    machine of any kind has no such directory, so it is created on all
    three.

    Only when absent, so an existing directory's permissions are left
    alone. `700` is applied to one this created: ssh refuses to use a
    key others can read, and the same applies to the directory holding
    it. Windows restricts a user profile folder to that user already,
    which is what the User Guide says too.
    """
    directory = context.home / ".ssh"
    if context.exists(directory):
        return []
    if context.platform == WINDOWS:
        return [
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"New-Item -ItemType Directory -Force -Path '{directory}' | Out-Null",
            ]
        ]
    return [["mkdir", "-p", str(directory)], ["chmod", "700", str(directory)]]


def _plan_ssh_key(context: Context) -> Plan:
    private = _key_path(context)
    public = private.with_suffix(".pub")
    create = [
        *_create_ssh_dir(context),
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-C",
            context.config.email,
            "-f",
            str(private),
        ],
    ]
    if context.pdkboot and _ssh_key_file_is_usable(
        context, private
    ) and not _ssh_key_file_is_usable(context, public):
        # Preserve the private key and derive its public half. `ssh-keygen -y`
        # may ask for the existing key's passphrase, so the subprocess inherits
        # the terminal while only its public-key stdout is captured.
        script = (
            "from pathlib import Path; import subprocess, sys\n"
            "private, public, comment = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]\n"
            "key = subprocess.run(['ssh-keygen', '-y', '-f', str(private)], "
            "check=True, text=True, stdout=subprocess.PIPE).stdout.strip()\n"
            "public.write_text(f'{key} {comment}\\n', encoding='utf-8')\n"
        )
        return Plan(
            commands=[
                [sys.executable, "-c", script, str(private), str(public), context.config.email]
            ],
            instructions=[
                "Your private key is intact. pdkboot will recreate only its missing public "
                "half; it will not replace the private key."
            ],
            confirm="Recreate the public key from the existing private key?",
            needs_terminal=True,
            action="REPAIR",
        )
    if context.pdkboot and (private.exists() or public.exists()):
        commands: list[list[str]] = []
        backups: list[Path] = []
        for path in (private, public):
            if not path.exists():
                continue
            backup = _numbered_backup(path, "pdk-orphaned-key-backup")
            commands.append(_move_path_command(context, path, backup))
            backups.append(backup)
        commands.extend(create)
        return Plan(
            commands=commands,
            instructions=[
                "There is no usable private key to recover. The remaining key file will "
                f"be archived as {', '.join(str(path) for path in backups)} before a new "
                "keypair is created."
            ],
            confirm="Archive the incomplete key files and create a new keypair?",
            needs_terminal=True,
            action="REPAIR",
            destructive=False,
        )
    return Plan(
        commands=create,
        instructions=[
            "ssh-keygen will ask for a passphrase - choose a strong one and "
            "remember it; it protects the key if your machine is lost.",
        ],
        confirm="Ready to create the key?",
        needs_terminal=context.pdkboot,
    )


# ---------------------------------------------------------------------------
# 4. ~/.ssh/config points this host at the right key
# ---------------------------------------------------------------------------


def _ssh_config_path(context: Context) -> Path:
    return context.home / ".ssh" / "config"


def _persistence_keywords(context: Context) -> tuple[str, ...]:
    """The directives that keep the key loaded past this login session.

    `AddKeysToAgent` is ordinary OpenSSH (7.2+) and belongs everywhere.
    `UseKeychain` is Apple's alone, and is emphatically not ignored by
    other builds: an OpenSSH that does not know the keyword rejects the
    *whole config file*, taking every other host in it down as well. So
    it is written on macOS only, and the test suite asserts its absence
    elsewhere rather than merely its presence here.
    """
    if context.platform == MACOS:
        return ("AddKeysToAgent", "UseKeychain")
    return ("AddKeysToAgent",)


def _ssh_config_block(context: Context) -> str:
    """The `Host` stanza this host needs, in the User Guide's own shape.

    `~` rather than an absolute path, as the guide writes it: the file is
    read by ssh, which expands it, and a config copied between machines
    with different usernames then still works.

    `IdentityFile` names the key; it does not put it in the agent. On its
    own it produces a machine that works until the agent is next emptied
    - a reboot, a logout - and then fails in the way #246 describes,
    having reported itself set up correctly at the time
    (prodockit-extensions#303). The directives below are what make the
    setup outlast the session.
    """
    host = context.host
    key = f"~/.ssh/{_key_path(context).name}"
    directives = "".join(f"    {keyword} yes\n" for keyword in _persistence_keywords(context))
    return (
        f"# {host.hostname} - added by prodockit bootstrap\n"
        f"Host {host.hostname}\n"
        f"    HostName {host.hostname}\n"
        f"    User git\n"
        f"    IdentityFile {key}\n"
        f"{directives}"
    )


def _ssh_config_host_body(context: Context) -> str | None:
    """The lines of the `Host <hostname>` stanza already in the config.

    `None` when there is no config file or no stanza for this host.
    Parsed rather than string-matched because `Host` blocks run until the
    next `Host`/`Match` line, and "is the hostname mentioned anywhere in
    the file?" would be satisfied by a comment.
    """
    try:
        text = _ssh_config_path(context).read_text(encoding="utf-8")
    except OSError:
        return None

    wanted = context.host.hostname
    collecting = False
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        keyword = stripped.split()[0].lower() if stripped else ""
        if keyword in ("host", "match"):
            if collecting:
                break
            # `Host a b c` may list several patterns; an exact name is
            # what this stage writes and what it looks for.
            collecting = keyword == "host" and wanted in stripped.split()[1:]
            continue
        if collecting:
            body.append(stripped)
    return "\n".join(body) if collecting or body else None


def _check_ssh_config(context: Context) -> CheckResult:
    """Whether ssh knows which key belongs to this host.

    Without a stanza, ssh offers its own defaults (`id_rsa`,
    `id_ed25519`), never tries `id_ed25519_gitlab`, and falls back to
    asking for a password - which looks exactly like a key the host has
    rejected (prodockit-extensions#239).
    """
    path = _ssh_config_path(context)
    body = _ssh_config_host_body(context)
    if body is None:
        if not path.exists():
            return _missing(f"{path} does not exist")
        return _missing(f"{path} has no Host entry for {context.host.hostname}")
    key_name = _key_path(context).name
    if key_name not in body:
        return _wrong(
            f"{path} has a Host entry for {context.host.hostname} but it does "
            f"not point at {key_name}"
        )
    # A stanza naming the right key still leaves the machine breaking on
    # the next reboot, and reporting that as OK is how it goes unnoticed
    # for weeks: the key drops out of the agent, and the failure that
    # surfaces blames the key rather than the config (#303).
    lowered = body.lower()
    absent = [word for word in _persistence_keywords(context) if word.lower() not in lowered]
    if absent:
        return _wrong(
            f"{path} points at {key_name} but will not keep it loaded past "
            f"this session - {' and '.join(absent)} missing"
        )
    return _ok(f"{context.host.hostname} uses {key_name}, and keeps it loaded")


def _plan_ssh_config(context: Context) -> Plan:
    """Appends the stanza, or explains the edit when one already exists.

    Only ever *appends*. An existing stanza that points somewhere else is
    left for a human: ssh takes the first match, so a second one would be
    ignored anyway, and rewriting somebody's ssh config underneath them
    is not a thing an installer should do unasked.
    """
    path = _ssh_config_path(context)
    block = _ssh_config_block(context)
    private = _key_path(context)

    if _ssh_config_host_body(context) is not None:
        return Plan(
            instructions=[
                f"Your {path} already has a Host entry for "
                f"{context.host.hostname} pointing at a different key.\n"
                "ssh uses the first match, so adding a second would change "
                "nothing. Edit the existing one to read:\n"
                f"{block.rstrip()}"
            ]
        )

    if context.platform == WINDOWS:
        # No chmod, and PowerShell rather than a shell heredoc. Windows
        # restricts a user profile file to that user already, which is
        # what the guide says too.
        powershell = (
            f"New-Item -ItemType Directory -Force -Path '{path.parent}' | Out-Null; "
            f"Add-Content -Path '{path}' -Value @'\n{block}'@"
        )
        return Plan(
            commands=[["powershell", "-NoProfile", "-Command", powershell]],
            describe=(
                f"Add a Host entry for {context.host.hostname} to {path}, using "
                f"{private.name} and keeping the key loaded"
            ),
        )

    # `>>` so an existing config is added to rather than replaced, and a
    # leading newline so the stanza cannot land on the end of somebody
    # else's last line.
    append = f"mkdir -p {path.parent} && printf '\\n%s' '{block}' >> {path}"
    return Plan(
        describe=(
            f"Add a Host entry for {context.host.hostname} to {path}, using "
            f"{private.name}, keep the key loaded, and restrict the config and "
            "private-key permissions"
        ),
        commands=[
            ["bash", "-c", append],
            # ssh ignores a private key others can read - "Permissions
            # 0644 ... are too open. This private key will be ignored" -
            # and then falls back to a password, which is the same
            # symptom as having no config at all.
            ["chmod", "600", str(path)],
            ["chmod", "600", str(private)],
        ],
    )


# ---------------------------------------------------------------------------
# 5. The key is loaded into an ssh agent
# ---------------------------------------------------------------------------


#: `ssh-add -l` says which of three states the agent is in by its exit
#: code, and the difference matters: "no agent" is something only the
#: reader can fix, "no identities" is something bootstrap can.
_AGENT_HAS_KEYS = 0
_AGENT_IS_EMPTY = 1
_AGENT_NOT_RUNNING = 2


def _key_fingerprint(context: Context) -> str | None:
    """This key's SHA256 fingerprint, as `ssh-add -l` would print it."""
    public = _key_path(context).with_suffix(".pub")
    result = context.runner.run(["ssh-keygen", "-lf", str(public)])
    if not result.ok:
        return None
    # `256 SHA256:abc... comment (ED25519)` - the fingerprint is the one
    # field worth comparing; the comment and bit count vary.
    for field in result.stdout.split():
        if field.startswith("SHA256:"):
            return field
    return None


def _check_ssh_agent(context: Context) -> CheckResult:
    """Whether the key is loaded and therefore usable without a prompt.

    Stage 3 tells the reader to set a passphrase, and every ssh command
    bootstrap runs carries `BatchMode=yes`, which forbids prompting. Those
    two are only compatible if an agent is holding the decrypted key.

    Without one, `ssh -T` offers the public half quite happily - that
    needs no passphrase - and then cannot sign the host's challenge,
    because signing needs the private half. Authentication fails, and the
    upload stage reports it as `the host rejected the key`: the key is
    fine, uploaded, and unusable (prodockit-extensions#246).
    """
    listed = context.runner.run(["ssh-add", "-l"])
    if listed.returncode == _AGENT_NOT_RUNNING:
        return _missing("no ssh agent is running")
    fingerprint = _key_fingerprint(context)
    if fingerprint is None:
        return _missing("no key to load yet")
    if listed.returncode == _AGENT_IS_EMPTY or fingerprint not in listed.stdout:
        return _missing(f"{_key_path(context).name} is not loaded into the agent")
    return _ok(f"{_key_path(context).name} is loaded")


def _plan_ssh_agent(context: Context) -> Plan:
    """Loads the key, or explains how to start an agent to load it into.

    A Unix shell agent cannot be started for the parent process:
    `eval "$(ssh-agent -s)"` exports `SSH_AUTH_SOCK` into *the shell that
    runs it*, and a subprocess cannot export anything into its parent.
    Windows is different: its agent is a system service, so pdkboot can
    request elevation through UAC and continue once that service starts.
    """
    private = _key_path(context)
    listed = context.runner.run(["ssh-add", "-l"])

    if listed.returncode == _AGENT_NOT_RUNNING:
        if context.platform == WINDOWS:
            if context.pdkboot:
                elevated = (
                    "$process = Start-Process powershell.exe -Verb RunAs -Wait "
                    "-PassThru -ArgumentList '-NoProfile -Command "
                    '"Set-Service ssh-agent -StartupType Automatic; '
                    "Start-Service ssh-agent\"'; "
                    "exit $process.ExitCode"
                )
                return Plan(
                    commands=[
                        ["powershell", "-NoProfile", "-Command", elevated],
                        ["ssh-add", str(private)],
                    ],
                    instructions=[
                        "Windows will ask for permission to enable and start its "
                        "built-in ssh-agent service. Accept that UAC prompt. "
                        "Back in this terminal, ssh-add will then ask for the "
                        "key's passphrase."
                    ],
                    confirm="Ready to enable the Windows SSH agent and load the key?",
                    needs_terminal=True,
                    describe=(
                        "Enable and start Windows' built-in ssh-agent service, then "
                        f"load {private.name} into it"
                    ),
                    action="configure",
                )
            next_command = "pdkboot" if context.pdkboot else "bootstrap"
            return Plan(
                instructions=[
                    "The ssh-agent service is not running. In a PowerShell window "
                    "opened as Administrator:\n"
                    "Set-Service ssh-agent -StartupType Automatic\n"
                    "Start-Service ssh-agent\n"
                    f"Then run {next_command} again in your normal window.",
                ],
                confirm="Have you started the ssh-agent service?",
                # This run cannot see the service start: it is a separate
                # window, and every stage below this one needs the agent.
                # So the honest end is to say what to type next, not to
                # re-check something that cannot have changed (#397).
                needs_a_new_run=True,
            )
        next_command = "pdkboot" if context.pdkboot else "bootstrap"
        tool_name = "pdkboot" if context.pdkboot else "bootstrap"
        return Plan(
            instructions=[
                f"No ssh agent is running. Start one in this terminal - {tool_name} "
                "cannot do it for you, because the agent is found through a "
                "variable that only the shell running it can set:\n"
                'eval "$(ssh-agent -s)"\n'
                f"Then run {next_command} again in the same terminal.",
            ],
            confirm="Have you started an agent in this terminal?",
        )

    # On macOS the passphrase can be stored in the login keychain, which
    # is the difference between loading the key for this session and
    # loading it for good: without it the agent is empty again after the
    # next reboot, and bootstrap has to be run a second time to fix
    # something it already reported as done (#303). No other platform has
    # an equivalent flag - `AddKeysToAgent` in the stanza covers them.
    command = ["ssh-add", str(private)]
    if context.platform == MACOS:
        command = ["ssh-add", "--apple-use-keychain", str(private)]

    return Plan(
        # `ssh-add` asks for the key's passphrase and reads it from
        # /dev/tty, so it has to have the terminal. Run captured it would
        # wait, unanswerable, until the timeout (#243).
        needs_terminal=True,
        commands=[command],
        instructions=[
            "ssh-add will ask for the passphrase you gave the key when it was created.",
        ],
        confirm="Ready to load the key into the agent?",
    )


# ---------------------------------------------------------------------------
# 6. Public key on the host - guide and verify
# ---------------------------------------------------------------------------


def _host_is_unknown(context: Context) -> bool:
    """Whether this machine has never accepted the host's key.

    Asked separately from the stage's own check because the answer decides
    whether the plan needs the terminal, and a plan is built before its
    check result is in hand.
    """
    result = context.runner.run(_ssh_probe(context))
    combined = f"{result.stdout}\n{result.stderr}"
    return "Host key verification failed" in combined or "authenticity of host" in combined


def _ssh_probe(context: Context, *, interactive: bool = False) -> list[str]:
    """`ssh -T`, wired so it can never wait for a human.

    `BatchMode=yes` is the load-bearing option. ssh reads passphrases and
    passwords from `/dev/tty` directly, *not* from stdin, so redirecting
    stdin does not stop it prompting - a check ran on a machine whose key
    was not yet uploaded fell back to password authentication and simply
    sat there:

        git@gitlab.surrey.ac.uk's password:

    A check that can block is a broken check, whatever it reports
    (prodockit-extensions#225). BatchMode makes ssh fail instead of ask.

    The options come from `SSH_NO_PROMPT_OPTIONS`, the same ones every
    git command gets through `GIT_SSH_COMMAND`, so a probe that says
    "authenticated" and a `git clone` that hangs cannot disagree.

    Host-key acceptance is deliberately *not* automated here. Accepting an
    unknown host key is a trust decision, and a tool that makes it
    silently on a reader's behalf has taken something from them they did
    not know they had. Unknown-host is reported instead, with the command
    to run.
    """
    ssh, *options = SSH_NO_PROMPT_OPTIONS
    if interactive:
        # The one probe allowed to ask something. `BatchMode=yes` is what
        # makes a *check* safe (#225), and it is exactly what stops ssh
        # offering its fingerprint question - so accepting a host key
        # needs it dropped, deliberately, and only when the reader has
        # agreed to connect. `ConnectTimeout` stays: an unreachable host
        # should still fail rather than hang.
        return [ssh, "-T", "-o", "ConnectTimeout=10", context.host.ssh_target]
    return [ssh, "-T", *options, context.host.ssh_target]


#: What a server says when it is refusing to talk rather than refusing a
#: key. The connection is accepted and then dropped, mid-authentication,
#: without a verdict either way.
#:
#: `Permission denied` is deliberately not in this list. That is a clean
#: answer from a working server - the key really is wrong, or really is
#: not uploaded - and treating it as a refusal would tell a reader to
#: wait when the fix is in their hands.
_REFUSAL_SIGNS = (
    "Connection closed by",
    "Connection reset by",
    "kex_exchange_identification",
)


def _connection_refused(combined: str) -> bool:
    """Whether the host hung up rather than answering."""
    return any(sign in combined for sign in _REFUSAL_SIGNS)


def _refusal_detail(context: Context) -> str:
    """Says who hung up, and that the key is not the suspect.

    Worth spelling out. The reader sees an authentication step fail and
    reasonably concludes the key was rejected - which is what this stage
    used to tell them. It cost a working afternoon to establish that a
    key can be accepted and the connection still dropped
    (prodockit-extensions#304).
    """
    return (
        f"{context.host.hostname} accepted the connection and then closed it "
        "without answering. A server does that when it is refusing logins for "
        "a while, often after too many in quick succession. Your key is "
        "probably fine - wait a few minutes and try again."
    )


def _check_ssh_authenticates(context: Context) -> CheckResult:
    """Whether the key actually authenticates.

    `ssh -T` against a git host exits non-zero even on success (there is
    no shell to give you), so the exit code says nothing - the greeting
    string is the only reliable signal, which is why every `Host` carries
    its own.
    """
    if context.pdkboot:
        key = _check_ssh_key(context)
        if key.needs_work:
            return _blocked("the SSH keypair is not ready yet")
        agent = _check_ssh_agent(context)
        if agent.needs_work:
            return _blocked("the key is not available through the SSH agent yet")

    result = context.runner.run(_ssh_probe(context))
    combined = f"{result.stdout}\n{result.stderr}"
    if context.host.ssh_success in combined:
        return _ok(f"authenticated to {context.host.hostname}")
    if "Host key verification failed" in combined or "authenticity of host" in combined:
        return _wrong(f"{context.host.hostname} is not a known host on this machine yet")
    # Before `Permission denied`, and before the catch-all: a dropped
    # connection reached neither of those and was reported as "could not
    # confirm", which says nothing a reader can act on.
    if _connection_refused(combined):
        return _wrong(_refusal_detail(context))
    if "Permission denied" in combined:
        return _missing(f"{context.host.hostname} rejected the key")
    return _wrong(f"could not confirm authentication to {context.host.hostname}")


#: Delimiters around the printed public key. The key is one long line
#: that wraps in a terminal, so without them it is not obvious where it
#: starts and stops - and a key pasted with a missing character fails in
#: exactly the same way as one never uploaded.
PUBLIC_KEY_MARKER = "======= PUBLIC KEY ======="


def _public_key_text(context: Context) -> str | None:
    """The public half of the keypair, if it can be read.

    Only ever `.pub`. A public key is public by definition - that is what
    it is for - whereas the file beside it must never be printed, so this
    reads the one path and never derives another from it.

    `None` when the key is not there yet (stage 3 has not run, and
    `--dry-run` builds every plan regardless) or cannot be read.
    """
    public = _key_path(context).with_suffix(".pub")
    try:
        text = public.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _machine_name() -> str:
    """This computer's name, for use as an SSH key title.

    A key title answers "which machine is this?", and the address the
    key was made with does not - every key a reader creates carries the
    same one.
    """
    return socket.gethostname().split(".")[0] or "this machine"


def _plan_ssh_upload(context: Context) -> Plan:
    """The upload steps, in the User Guide's own words (#238).

    Navigated by menu rather than by pasted URL. The URL is the faster
    route for somebody who already knows where they are going, and the
    worse one for somebody who does not - it offers no way to tell you
    have arrived in the right place, and no way back if you have not. It
    is still given, as a shortcut, after the route that can be followed.
    """
    host = context.host
    public = _key_path(context).with_suffix(".pub")

    # Each entry is one numbered step; newlines within an entry hang under
    # it. The form is one step with its fields beneath, not four steps -
    # numbering "Title", "Key" and "Expiration date" separately reads as
    # three things to go and do rather than three boxes on one screen.
    login = f"Log in to {host.hostname} in a web browser."
    if host.login_note:
        login += f"\n{host.login_note}"
    instructions = [login]

    navigation = list(host.ssh_keys_steps)
    if navigation:
        navigation[-1] += f"\nOr go straight there: {host.ssh_keys_url}"
    else:  # pragma: no cover - every populated host describes its menus
        navigation = [f"Open {host.ssh_keys_url}"]
    instructions += navigation

    # The key is printed rather than pointed at. "Paste the contents of
    # ~/.ssh/id_ed25519_gitlab.pub" asks a first-time reader to find a
    # dotfile, open it in something, and copy the right one of two files
    # whose names differ by four characters - and picking the wrong one
    # uploads the *private* key. Showing the public half removes the
    # step and the hazard together.
    key_text = _public_key_text(context)
    if key_text is not None:
        key_field = (
            "Key: copy everything between the lines below - all of it, and "
            "nothing else - and paste it in:\n"
            f"{PUBLIC_KEY_MARKER}\n{key_text}\n{PUBLIC_KEY_MARKER}"
        )
    else:
        # Nothing to show: stage 3 has not run, or the file cannot be
        # read. Naming the path is the best available, and the warning
        # against its neighbour matters more here than anywhere.
        key_field = (
            f"Key: paste the contents of {public} - the .pub file, never the one without it."
        )

    # Key first, Title second, because that is the order the form
    # actually works in. GitLab fills the Title in from the key's own
    # comment the moment a key is pasted - so a title typed first is
    # silently replaced, and the reader is left with a list of keys all
    # called by their email address (prodockit-extensions#257).
    machine = _machine_name()
    form = "\n".join(
        [
            f"Click '{host.ssh_key_new_label}', then fill in, in this order:",
            key_field,
            "Title: filled in for you when you paste the key, from the address "
            f"the key was made with. Replace it with {machine!r} - the name of "
            "this machine - so you can tell which computer a key belongs to "
            "when there are several.",
            *host.ssh_key_form_extra,
        ]
    )

    instructions += [
        form,
        f"Click '{host.ssh_key_save_label}' to save it.",
    ]

    # First contact with a host asks whether to trust its fingerprint, and
    # that is the reader's decision - but it is not a reason to send them
    # to a second terminal to make it (prodockit-extensions#281 thread).
    # `needs_terminal` hands over the real one, as it does for `ssh-add`'s
    # passphrase, so ssh asks its own question here and the reader answers
    # it in place. Bootstrap still never answers it for them.
    if _host_is_unknown(context):
        return Plan(
            instructions=instructions,
            needs_terminal=True,
            commands=[_ssh_probe(context, interactive=True)],
            confirm=(
                f"Ready to connect to {host.hostname}? ssh will show its "
                "fingerprint and ask you to confirm it"
            ),
        )
    # Instructions only, deliberately. `ssh -T` is the *check*, and it
    # cannot also be a plan command: against a git host it exits non-zero
    # even on success (there is no shell to give you), so a runner that
    # judges commands by their exit code sees every probe as a failure and
    # stops the run - which is what it did, on a machine whose key simply
    # had not been uploaded yet (#234).
    #
    # Nothing is lost by dropping it: applying a stage always re-runs its
    # check, and that check reads the greeting rather than the exit code.
    return Plan(
        instructions=instructions,
        confirm=f"Have you added the key to your {host.hostname} account?",
    )


# ---------------------------------------------------------------------------
# 7. Template cloned (platform-independent)
# ---------------------------------------------------------------------------


def _numbered_backup(path: Path, label: str) -> Path:
    """An adjacent backup path that never overwrites an earlier recovery copy."""
    backup = path.parent / f".{path.name}.{label}"
    suffix = 2
    while backup.exists():
        backup = path.parent / f".{path.name}.{label}-{suffix}"
        suffix += 1
    return backup


def _move_path_command(context: Context, source: Path, destination: Path) -> list[str]:
    """Moves a path without putting a shell-interpreted path in the command."""
    if context.platform != WINDOWS:
        return ["mv", str(source), str(destination)]
    escaped_source = str(source).replace("'", "''")
    escaped_destination = str(destination).replace("'", "''")
    return [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Move-Item -LiteralPath '{escaped_source}' -Destination '{escaped_destination}'",
    ]


def _template_history_backups(project: Path) -> list[Path]:
    """Recovery copies left beside a project by the fresh-history stage."""
    return sorted(project.parent.glob(f".{project.name}.git.pdk-template-backup*"))


def _repository_has_a_commit(context: Context, project: Path) -> bool:
    return context.runner.run([git_command(context), "-C", str(project), "rev-parse", "HEAD"]).ok


def _check_clone(context: Context) -> CheckResult:
    if (unknown := _needs_config(context, "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not project.exists():
        if (
            context.pdkboot
            and not context.config.source_url.strip()
            and project_on_host(context) is None
        ):
            return _blocked(
                "where the project comes from cannot be decided until SSH access "
                "to the host is ready"
            )
        return _missing(f"{project} does not exist")
    backups = _template_history_backups(project) if context.pdkboot else []
    if not (project / ".git").exists():
        if backups:
            return _wrong(
                "the template history was archived, but the new repository was not "
                "initialised - the interrupted operation can be resumed"
            )
        return _wrong(f"{project} exists but is not a git repository")
    if context.pdkboot and not _repository_has_a_commit(context, project):
        # A deliberately fresh repository has no commit until stage 22. The
        # adjacent archive proves pdkboot created this state; without it, an
        # invalid HEAD is evidence of an interrupted clone.
        if backups:
            return _ok(f"{project} - your own project")
        return _wrong(f"{project} is an incomplete git clone with no readable commit")
    # Which repository this came from decides which path the rest of the
    # run takes - whether the history stage offers a reset, and whether
    # the reader's existing work is here at all. Saying only the path left
    # that invisible in the final report, where it is the one place a
    # reader can check what was decided (prodockit-extensions#332).
    if _origin_is_the_template(context):
        return _ok(f"{project} - from the template")
    return _ok(f"{project} - your own project")


def _plan_clone(context: Context) -> Plan:
    """Clone the template, or `source_url` when one is configured.

    The template is the default because it is what most readers need.
    Both paths are real in the User Guide though: a student on a taught
    module is often *given* a repository instead, and cloning the template
    over the top of that would be a detour through work the host already
    did.

    An explicit setting rather than probing the host for an existing
    repository: the reader knows which case they are in, and asking the
    host would put a network call inside plan-building - which has to stay
    cheap and side-effect-free, since `--dry-run` calls it.

    The later stages fall out correctly either way. A clone made from
    `source_url` already has the right `origin`, so the repoint stage
    reports `ok` and does nothing.
    """
    project = context.config.resolved_project_dir(context.home)
    if (
        context.pdkboot
        and project.exists()
        and not (project / ".git").exists()
        and _template_history_backups(project)
    ):
        return Plan(
            cwd=str(project),
            commands=[
                [git_command(context), "init", "-b", "main"],
                [git_command(context), "config", "core.fileMode", "false"],
            ],
            describe="Resume creating your repository after its template history was archived",
            action="REPAIR",
        )
    if context.pdkboot and project.exists() and (
        not (project / ".git").exists() or not _repository_has_a_commit(context, project)
    ):
        backup = _numbered_backup(project, "pdk-incomplete-clone-backup")
        return Plan(
            commands=[
                _move_path_command(context, project, backup),
                [git_command(context), "clone", clone_source(context), str(project)],
            ],
            instructions=[
                f"The existing directory is not a complete clone. It will be moved to {backup} "
                "before cloning again, so none of its files are lost."
            ],
            confirm="Archive the incomplete directory and clone the project again?",
            action="REPAIR",
            destructive=False,
        )
    # No prompt here. `--configure` put the choice with every path named
    # and recorded it; asking again mid-run would be the same decision in
    # worse words (#332).
    return Plan(commands=[[git_command(context), "clone", clone_source(context), str(project)]])


def _ls_remote_own_project(context: Context) -> CommandResult | None:
    """`git ls-remote` against the reader's own project, or None."""
    namespace = context.config.namespace.strip()
    project = context.config.project_name.strip()
    if not (namespace and project):
        return None
    return context.runner.run(
        [git_command(context), "ls-remote", context.host.remote_url(namespace, project)]
    )


#: What a host says when it really means "there is no such repository",
#: as opposed to "I will not tell you". GitHub and GitLab word it
#: differently, and neither is the only way `git ls-remote` can fail.
_ABSENT_SIGNS = ("repository not found", "project not found", "does not appear to be a git")


def project_on_host(context: Context) -> bool | None:
    """Whether the reader's project exists: yes, no, or *cannot tell*.

    `None` is the important one. On a machine with no SSH key yet -
    which is every machine, before stage 3 - `git ls-remote` fails on
    authentication, and reading that as "the repository does not exist"
    told a reader their project was missing when it was sitting on the
    host in front of them (prodockit-extensions#344).

    Only the host saying so counts as absent. Anything else - a refused
    key, an unreachable network, a name that will not resolve - is
    unknown, because none of them is evidence about the repository.
    """
    result = _ls_remote_own_project(context)
    if result is None:
        return None
    if result.ok:
        return True
    said = f"{result.stdout}\n{result.stderr}".lower()
    return False if any(sign in said for sign in _ABSENT_SIGNS) else None


def own_project_exists(context: Context) -> bool:
    """Whether the reader's own project is there at all, empty or not.

    Asked separately from `own_project_has_content` because an *empty*
    issued repository still matters. A taught module creates one per
    student with permissions already set - the instructor can see it, the
    other students cannot - and those permissions belong to that
    repository, not to its contents. Making a new one instead would
    quietly publish a student's work to the wrong audience
    (prodockit-extensions#332).
    """
    return project_on_host(context) is True


#: What makes a repository a *project* rather than merely non-empty.
#:
#: `zensical.toml` is what every later stage reads, and `README.md` is
#: what `prodockit sync-repo` rewrites. A repository holding a stray note
#: and neither of those is as unusable as an empty one, and "has any
#: commits" called it usable (prodockit-extensions#348).
PROJECT_FILES = ("zensical.toml", "README.md")


def _remote_holds_a_project(context: Context) -> bool:
    """Whether the default branch carries `PROJECT_FILES`.

    `git ls-remote` lists refs and says nothing about files, so this
    fetches the tree and no blobs - `--filter=blob:none --no-checkout`
    over the reader's own key, which is what makes it work against a
    private repository without a token. The clone is thrown away.

    Any failure answers "no". A probe that cannot complete must not be
    read as evidence that the repository is usable: that way round the
    reader gets the template and a working project, rather than a clone
    of something missing what every later stage needs.
    """
    namespace = context.config.namespace.strip()
    project = context.config.project_name.strip()
    url = context.host.remote_url(namespace, project)
    with tempfile.TemporaryDirectory() as into:
        clone = context.runner.run(
            [
                git_command(context),
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--no-checkout",
                url,
                into,
            ]
        )
        if not clone.ok:
            return False
        listed = context.runner.run(
            [git_command(context), "-C", into, "ls-tree", "--name-only", "HEAD"]
        )
    if not listed.ok:
        return False
    present = set(listed.stdout.split())
    return all(wanted in present for wanted in PROJECT_FILES)


#: What a repository holds when its only commit is the one the host made
#: from "initialize this repository with a README". GitLab and GitHub
#: both offer that tick-box next to the Create button, and a student who
#: ticks it has made a repository that cannot be pushed to from a history
#: that does not contain it (prodockit-extensions#423).
_JUST_A_README = frozenset({"README.md"})


def remote_is_only_its_first_readme(context: Context) -> bool:
    """Whether `origin` holds nothing but the README the host created.

    Deliberately exact. Anything else at all - a second file, a stray
    commit, somebody else's work - and this is False, because the answer
    decides whether a force push is offered and overwriting a repository
    that has something in it is not recoverable.
    """
    project = context.config.resolved_project_dir(context.home)
    with tempfile.TemporaryDirectory() as into:
        clone = context.runner.run(
            [
                git_command(context),
                "clone",
                "--depth",
                "1",
                "--no-checkout",
                _origin_url(context) or str(project),
                into,
            ]
        )
        if not clone.ok:
            return False
        listed = context.runner.run(
            [git_command(context), "-C", into, "ls-tree", "--name-only", "HEAD"]
        )
        counted = context.runner.run(
            [git_command(context), "-C", into, "rev-list", "--count", "HEAD"]
        )
    if not (listed.ok and counted.ok):
        return False
    return set(listed.stdout.split()) == _JUST_A_README and counted.stdout.strip() == "1"


def own_project_has_content(context: Context) -> bool:
    """Whether the reader's own project exists on the host *and* has commits.

    The distinction matters. A project created in the browser and never
    pushed to is the ordinary first-run case, and it needs the template -
    cloning an empty repository would leave nothing to work on. `git
    ls-remote` tells them apart on evidence rather than on a flag: an
    empty repository answers successfully and lists no refs.

    This puts a network call inside plan-building, which `_plan_clone`
    once argued against because `--dry-run` builds every plan. Two things
    changed. `_check_own_project` already asks this exact question one
    stage later, so the run was making the connection regardless; and
    since #304 the answer is remembered within a pass, so asking here
    costs nothing beyond the first time.
    """
    result = _ls_remote_own_project(context)
    if result is None or not result.ok or not result.stdout.strip():
        return False
    return _remote_holds_a_project(context)


def clone_source(context: Context) -> str:
    """What to clone: a URL, a name expanded against the host, or the template.

    The prompt asks for "an existing repository to clone instead of the
    template", so a reader answers with their repository - and a
    repository is usually called `report-az1234`, not
    `git@gitlab.surrey.ac.uk:comm058-2026/report-az1234.git`. That answer
    went to `git clone` verbatim and failed with `repository
    'report-az1234' does not exist`, which reads as though the repository
    were missing rather than the address incomplete
    (prodockit-extensions#283).

    Three forms are accepted, because all three are things a reader
    plausibly has to hand:

    - a full URL - `git@host:group/repo.git`, `https://host/group/repo` -
      used exactly as given, since somebody who pasted a URL means it;
    - `group/repo` - the host is filled in;
    - `repo` - the host and the configured namespace are filled in, which
      is the case in the report.
    """
    given = context.config.source_url.strip()
    if not given:
        # Nothing is detected here. `--configure` asks whether an existing
        # repository should be used and records the answer, so this reads
        # a decision rather than making one - which keeps plan-building
        # free of network calls, as `--dry-run` needs (#332).
        return context.host.template_remote
    if given.startswith(("git@", "ssh://", "https://", "http://")):
        return given

    path = given.strip("/").removesuffix(".git")
    if "/" not in path:
        namespace = context.config.namespace.strip()
        if not namespace:
            # Nothing to expand it with. Left as given so the failure is
            # git's own rather than a URL invented from a blank.
            return given
        path = f"{namespace}/{path}"
    return f"git@{context.host.hostname}:{path}.git"


# ---------------------------------------------------------------------------
# 8. A history of your own, not the template's
# ---------------------------------------------------------------------------


def _check_fresh_history(context: Context) -> CheckResult:
    """Whether the clone still carries the template's commit history.

    Judged by `origin`, and deliberately so. The obvious test - "does
    this repository have commits?" - would report a project the reader
    had been working in for weeks as needing its history deleted, which
    is the one mistake this stage must never make. `origin` still
    pointing at the template is the only state in which discarding the
    history is unambiguously right, and it is a state that cannot recur:
    resetting removes the remote, and repointing replaces it.

    A clone made from `source_url` already belongs to the reader, so its
    origin is not the template's and nothing here applies to it.
    """
    if (unknown := _needs_config(context, "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not (project / ".git").exists():
        # Not "missing": there is nothing here to repair yet, and a plan
        # built from it deleted a `.git` that does not exist and ran
        # `git init` in a directory that does not exist either. Waiting
        # on the clone, like the two stages after this one (#330).
        return _blocked("there is no clone yet - do the 'Project cloned' stage first")
    origin = context.runner.run(
        [git_command(context), "-C", str(project), "remote", "get-url", "origin"]
    )
    if not origin.ok:
        # No remote at all: `git init` has already been here.
        return _ok("a history of its own")
    if origin.stdout.strip() != context.host.template_remote:
        if not _file_mode_ignored(context):
            # The plan sets this alongside the reset, so the check has to
            # be able to see it (#224) - and it is per-repository, so a
            # fresh clone silently loses it again.
            return _wrong("a history of its own, but core.fileMode is not off")
        return _ok("a history of its own")
    # An explicit "keep" settles it. The reader was shown both paths at
    # configure time and chose this one, so nothing here re-derives the
    # decision from what `origin` happens to say (#332).
    if context.config.history.strip() == "keep":
        if not _file_mode_ignored(context):
            return _wrong("keeping your history, but core.fileMode is not off")
        return _ok("keeping your history")
    # WRONG rather than MISSING, for the prompt's default. `--apply`
    # offers MISSING as [Y/n] and WRONG as [y/N], and deleting a
    # repository's history is the last thing that should happen by
    # pressing Enter.
    return _wrong("still the template's history, and pointed at the template")


def _file_mode_ignored(context: Context) -> bool:
    """Whether git has been told to ignore the executable bit.

    Cloud-sync clients rewrite those bits as they sync, and git reads a
    changed bit as a changed file - so a project in a synced folder shows
    every file as modified without a byte of content having changed.
    """
    project = context.config.resolved_project_dir(context.home)
    result = context.runner.run(
        [git_command(context), "-C", str(project), "config", "core.fileMode"]
    )
    return result.ok and result.stdout.strip().lower() == "false"


def _plan_fresh_history(context: Context) -> Plan:
    """Archives the template's `.git` directory and starts again.

    `core.fileMode false` comes with it, from the guide: git treats a
    change to a file's executable bit as a change to the file, and
    cloud-sync clients rewrite those bits as they sync - so a project in
    a synced folder can show every file as modified without a byte of
    content having changed.
    """
    project = context.config.resolved_project_dir(context.home)
    # A clone that already carries its own history has nothing to reset,
    # and this stage's other concern - core.fileMode - is a one-line
    # setting. Returning the reset here offered to replace `.git` on the
    # reader's own project because a git *option* was unset: the exact
    # mistake `_check_fresh_history` says this stage must never make
    # (prodockit-extensions#332).
    chosen = context.config.history.strip()
    if chosen == "keep" or (not chosen and not _origin_is_the_template(context)):
        return Plan(
            cwd=str(project),
            commands=[[git_command(context), "config", "core.fileMode", "false"]],
            action="configure",
        )
    git_dir = project / ".git"
    if not context.pdkboot:
        remove = (
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Remove-Item -Recurse -Force '{git_dir}'",
            ]
            if context.platform == WINDOWS
            else ["rm", "-rf", str(git_dir)]
        )
        return Plan(
            cwd=str(project),
            destructive=False,
            confirm="Delete the template's history and start a new repository?",
            instructions=[
                "This deletes the template's commit history from your clone - every "
                "commit, branch and tag - and cannot be undone. Your files are not "
                "touched, only the history behind them.\n"
                f"The directory is {project}.\n"
                "Skip this if you want to keep the template's history.",
            ],
            commands=[
                remove,
                [git_command(context), "init", "-b", "main"],
                [git_command(context), "config", "core.fileMode", "false"],
            ],
        )
    # Outside the new repository: leaving the backup inside the project
    # would make `git add -A` include the entire archived object database in
    # the first commit.
    backup = _numbered_backup(project, "git.pdk-template-backup")
    archive = _move_path_command(context, git_dir, backup)
    return Plan(
        cwd=str(project),
        # The old history is moved aside, never deleted. The move itself is
        # atomic on the same filesystem and refuses to overwrite an existing
        # backup, so an interrupted reset remains recoverable.
        destructive=False,
        confirm="Archive the template's history and start a new repository?",
        instructions=[
            "This moves the template's commit history out of the active clone - "
            "every commit, branch and tag. Your files are not touched, and the "
            f"old history can be recovered from {backup}.\n"
            f"The directory is {project}.\n"
            "Skip this if you want to keep the template's history.",
        ],
        commands=[
            archive,
            [git_command(context), "init", "-b", "main"],
            [git_command(context), "config", "core.fileMode", "false"],
        ],
        action="archive",
    )


# ---------------------------------------------------------------------------
# 9. The reader's own project exists on the host - guide and verify
# ---------------------------------------------------------------------------


#: Lines git prints around the host's own message, which say nothing a
#: reader can act on.
_GIT_NOISE = (
    "fatal: could not read from remote repository",
    "please make sure you have the correct access rights",
    "and the repository exists",
    "remote:",
)


def host_said(result: CommandResult) -> str:
    """The host's own words from a failed git command, or "".

    A refusal is worth quoting rather than paraphrasing: "could not be
    found or you don't have permission to view it" and "Permission
    denied (publickey)" need different things from the reader, and a
    summary that covers both chooses neither
    (prodockit-extensions#439).
    """
    for line in f"{result.stderr}\n{result.stdout}".splitlines():
        said = line.strip().removeprefix("remote:").strip()
        if not said or set(said) <= {"=", "-"} or said.lower().startswith(_GIT_NOISE):
            continue
        return said
    return ""


def _check_own_project(context: Context) -> CheckResult:
    if (unknown := _needs_config(context, "namespace", "project_name")) is not None:
        return unknown
    # Deliberately not blocked on the history reset. The repository lives
    # on the *host*, and archiving the local `.git` is local - so nothing
    # here is thrown away by the reset, unlike the repoint in the stage below.
    #
    # Blocking it made the retry loop unescapable: the reader created the
    # repository, said yes, and was told the clone still points at the
    # template - a fact about their machine that creating a repository
    # cannot change (prodockit-extensions#336).
    url = context.host.remote_url(context.config.namespace, context.config.project_name)
    if context.pdkboot and _check_ssh_authenticates(context).needs_work:
        return _blocked(
            "SSH access to the host is not ready yet - complete the 'SSH key on the "
            "host' stage first"
        )
    result = context.runner.run([git_command(context), "ls-remote", url])
    if result.ok:
        return _ok(url)
    # "not reachable" would be read as "you have not created it yet",
    # which is this stage's normal finding and the wrong advice when the
    # host is simply refusing to talk (#304).
    if _connection_refused(f"{result.stdout}\n{result.stderr}"):
        return _wrong(_refusal_detail(context))
    # Not "does not exist", and not "is not reachable" either. github.com
    # answers `Repository not found.` for a repository that is missing
    # *and* for one your key cannot see, and GitLab covers both in a
    # single sentence - so the honest report is what was seen, and the
    # plan warns before anything is created (prodockit-extensions#377).
    said = host_said(result)
    reply = f" - {context.host.hostname} said: {said}" if said else ""
    return _missing(f"nothing visible at {url}{reply}")


def _namespace_report(context: Context) -> list[str]:
    """What to say about the address the URL was built from.

    Detection and reporting, not repair (prodockit-extensions#441). A
    group's real path cannot be read from here without credentials, so
    the honest move is to name the value being used, say where the
    reader can see the true one, and let them compare - rather than
    guess a second address and turn a visible failure into a silent
    wrong answer.

    Shown only when the project is not visible: on a run that finds it,
    the address was right and this is noise.
    """
    if not context.host.namespace_note:
        return []
    namespace = context.config.namespace
    url = context.host.remote_url(namespace, context.config.project_name)
    return [
        f"If it is there and this still cannot see it, check the address rather "
        f"than the name. This is looking for:\n"
        f"    {url}\n"
        f"so it is using {namespace!r} as the "
        f"{context.host.group_word}'s address.\n"
        f"{context.host.namespace_note}",
    ]


def _plan_own_project(context: Context) -> Plan:
    host = context.host
    return Plan(
        instructions=[
            f"Open {host.new_project_url}",
            # First, because the check cannot tell these apart and the
            # wrong answer is expensive: an issued repository carries the
            # permissions deciding who can read the work, and a second
            # one will not have them (#332).
            f"Check whether {context.config.namespace}/{context.config.project_name} is "
            "already there. Being unable to see it is not proof that it is not - if it "
            "exists, do not create another; ask for access to that one instead.",
            f"If it is not there, create a blank {host.project_word} named "
            f"{context.config.project_name!r} in the {host.group_word} "
            f"{context.config.namespace!r}.",
            host.project_visibility,
            (
                "Untick every 'initialize with' option - pdkboot will add the selected "
                "project contents after this, and an initialised remote would conflict "
                "with them."
                if context.pdkboot
                else "Untick every 'initialize with' option - the clone you already "
                "have provides the contents, and an initialised remote would conflict "
                "with it."
            ),
            # Said here because this is where a reader stands when the
            # address is wrong: they can see the project in the browser
            # and bootstrap cannot (#441).
            *_namespace_report(context),
            # Whatever else this host needs doing in the browser. Said here,
            # while the reader is already in the right place, rather than
            # left for them to discover from a failed build afterwards
            # (#324).
            *host.after_creating_steps,
        ],
        confirm=(f"Have you created the {host.project_word} on {host.hostname}?"),
        # Instructions only, for the same reason as the SSH upload above:
        # `git ls-remote` is this stage's check, and a check run as a plan
        # command turns "you have not finished in the browser yet" - the
        # normal case - into a failed command that ends the run. Re-checking
        # after apply asks the same question, and asks it again.
    )


# ---------------------------------------------------------------------------
# 10. Remote repointed at it (platform-independent)
# ---------------------------------------------------------------------------


def _check_remote(context: Context) -> CheckResult:
    if (unknown := _needs_config(context, "namespace", "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not (project / ".git").exists():
        absent = _blocked if context.pdkboot else _missing
        return absent("no clone to repoint yet")
    wanted = context.host.remote_url(context.config.namespace, context.config.project_name)
    result = context.runner.run(
        [git_command(context), "-C", str(project), "remote", "get-url", "origin"]
    )
    if not result.ok:
        return _missing("no `origin` remote is set")
    actual = result.stdout.strip()
    # Named for what it is rather than reported as "not the expected
    # URL". Repointing now would be undone by the reset that has to come
    # first, and leaving it is how a project ends up pushing into the
    # template (#311).
    if actual == context.host.template_remote:
        return _blocked(_STILL_THE_TEMPLATE)
    if actual != wanted:
        return _wrong(f"origin is {actual}, expected {wanted}")

    # The remote being right is only half of it. `prodockit sync-repo`
    # also rewrites repo_url/repo_name/edit_uri/site_url and the README
    # badges, and a stage that checked only the remote reported itself
    # done after `git remote set-url` had succeeded and sync-repo had
    # not - leaving a clone that pushed to the right place while still
    # advertising the template's repository on every page. Asking
    # sync-repo itself is the honest test, and the one that stays correct
    # as sync-repo grows.
    synced = context.runner.run([*_prodockit_command(), "sync-repo", "--check"], cwd=str(project))
    if not synced.ok:
        # Three results, not two. `--check` exits non-zero both for
        # "there is a difference" and for "I could not look", and saying
        # the same sentence to both named a cause nobody had established
        # (prodockit-extensions#451):
        #
        #   Error: could not run git: [WinError 2] The system cannot
        #   find the file specified
        #
        # reached the reader as "the project config still needs
        # syncing", which is not something running sync-repo would fix.
        if (broke := _sync_check_broke(synced)) is not None:
            return _wrong(f"could not check whether the project config is synced - {broke}")
        return _wrong("origin is right, but the project config still needs syncing")
    return _ok(wanted)


#: What `sync-repo` says when it could not carry the check out at all,
#: as opposed to carrying it out and finding a difference. Its own error
#: prefix, so this does not have to guess from an exit status.
_SYNC_CHECK_FAILED = "Error:"


def _sync_check_broke(result: CommandResult) -> str | None:
    """What stopped the check, or None if it actually ran.

    Read from what it said rather than from the exit status, because the
    status is the thing that cannot tell these apart.
    """
    for line in f"{result.stderr}\n{result.stdout}".splitlines():
        said = line.strip()
        if said.startswith(_SYNC_CHECK_FAILED):
            return said.removeprefix(_SYNC_CHECK_FAILED).strip() or None
    return None


def _plan_remote(context: Context) -> Plan:
    project = context.config.resolved_project_dir(context.home)
    wanted = context.host.remote_url(context.config.namespace, context.config.project_name)
    # Both run *in* the project. `git -C` could carry the path itself, but
    # `prodockit sync-repo` reads zensical.toml from the working directory
    # and has no equivalent flag, so the plan sets one for both rather
    # than half the commands knowing where they are.
    # `set-url` if there is an origin, `add` if there is not. Resetting
    # the history deletes `.git` and starts a new repository, which has
    # no remotes at all - so after that stage `set-url` fails with "No
    # such remote 'origin'" and the repoint never happens (#248).
    has_origin = context.runner.run(
        [git_command(context), "-C", str(project), "remote", "get-url", "origin"]
    ).ok
    repoint = (
        [git_command(context), "remote", "set-url", "origin", wanted]
        if has_origin
        else [git_command(context), "remote", "add", "origin", wanted]
    )
    return Plan(
        cwd=str(project),
        commands=[
            repoint,
            # sync-repo rewrites repo_url/repo_name/edit_uri/site_url and the
            # README badges to match the new remote. Without it the clone
            # keeps advertising the template's own repository.
            [*_prodockit_command(), "sync-repo"],
        ],
    )


# ---------------------------------------------------------------------------
# 11. Commit identity, in the project (platform-independent)
# ---------------------------------------------------------------------------


def _identity_wanted(context: Context) -> dict[str, str]:
    return {
        "user.name": context.config.full_name,
        "user.email": context.config.email,
    }


def _check_project_identity(context: Context) -> CheckResult:
    """Whether *this repository* commits under the configured identity.

    `--local` is the whole point. `git config user.email` inside a
    repository falls back to the global value, so a check written that
    way passes on any machine with any identity at all - which is exactly
    how bootstrap came to ask for an email, store it, and then never
    apply it. Every stage reported `ok` while commits went out under a
    GitHub noreply address the reader had not chosen for this work
    (prodockit-extensions#222).

    That is not cosmetic. A commit whose author address does not match a
    known account on the host is not linked to that account, so
    coursework can show as authored by an unrecognised user - and the
    reader has no reason to suspect it, because they were told the stage
    was fine.
    """
    if (unknown := _needs_config(context, "full_name", "email")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not context.exists(project / ".git"):
        absent = _blocked if context.pdkboot else _missing
        return absent("no clone to set an identity in yet")

    unset: list[str] = []
    mismatched: list[str] = []
    for key, wanted in _identity_wanted(context).items():
        result = context.runner.run(
            [git_command(context), "-C", str(project), "config", "--local", key]
        )
        actual = result.stdout.strip() if result.ok else ""
        if not actual:
            unset.append(key)
        elif actual != wanted:
            mismatched.append(f"{key} is {actual}, expected {wanted}")
    if mismatched:
        # Both values named, because "wrong" without saying what it is
        # leaves the reader to go and find out with a command they would
        # have to know already.
        return _wrong("; ".join(mismatched))
    if unset:
        return _missing(
            f"this repository has no {' or '.join(unset)} of its own - "
            "commits would use your global identity"
        )
    identity = _identity_wanted(context)
    return _ok(f"{identity['user.name']} <{identity['user.email']}> in this repository")


def _plan_project_identity(context: Context) -> Plan:
    """Sets the identity on the clone, never globally.

    A global `user.email` is a legitimate personal preference, and a tool
    that sets up one university project has no business rewriting the
    identity someone uses for everything else. Per-repository fixes
    attribution exactly where it matters and leaves the rest of their
    work alone.
    """
    return Plan(
        cwd=str(context.config.resolved_project_dir(context.home)),
        commands=[
            [git_command(context), "config", "--local", key, value]
            for key, value in _identity_wanted(context).items()
        ],
    )


# ---------------------------------------------------------------------------
# 12. Pandoc, and the libraries WeasyPrint needs
# ---------------------------------------------------------------------------


def _pandoc_version(stdout: str) -> str | None:
    """Extract the version number from `pandoc --version` output.

    The first non-blank line is normally `pandoc 3.10.1` or similar.
    """
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("pandoc"):
            parts = stripped.split()
            if len(parts) >= 2:
                return parts[1]
    return None


def _check_pandoc(context: Context) -> CheckResult:
    result = context.runner.run([pandoc_command(context), "--version"])
    if not result.ok:
        return _missing("pandoc is not installed")
    version = _pandoc_version(result.stdout)
    if version is None:
        return _wrong("pandoc is installed but its version could not be read")
    major = version.split(".")[0]
    if major.isdigit() and int(major) < PANDOC_MIN_MAJOR:
        # Ubuntu's own package lags well behind upstream - far enough to
        # change how the PDF renders. Code blocks come out as justified
        # prose on pandoc 2.x (#207).
        return _wrong(
            f"pandoc {version} is too old - {PANDOC_MIN_MAJOR}.x or later is "
            f"needed (the builds pin {PANDOC_VERSION})"
        )
    missing_fonts = _absent_pdf_fonts(context)
    if missing_fonts:
        # The plan installs these, so the check has to be able to see
        # them (#224). WeasyPrint substitutes silently when they are
        # absent, so nothing else will notice until a test does.
        return _wrong(f"pandoc {version}, but the PDF fonts are missing: {missing_fonts}")
    if version != PANDOC_VERSION:
        # Said, not failed. Pandoc decides how the PDF renders - #207 was
        # code blocks coming out as justified prose on an older major,
        # and limitations.md records 3.1.3 accepting markup 3.10 does
        # not - so a local pandoc that differs from the builds' is worth
        # knowing about: both builds succeed, and only the output
        # disagrees (#454).
        #
        # Deliberately not `_wrong`. Homebrew cannot install an old
        # pandoc, so on macOS a failing status would be one no reader
        # could ever clear - a stage stuck for good, which is the failure
        # this project keeps having to undo (#443, #451). A note they can
        # act on beats a red mark they cannot.
        return _ok(
            f"pandoc {version} - the builds pin {PANDOC_VERSION}, so a PDF built "
            "here can differ from the published one"
        )
    return _ok(f"pandoc {version}")


def _absent_pdf_fonts(context: Context) -> str:
    """Which of the PDF's fonts are not installed, as a readable list.

    Empty when they are all present *or* when the machine cannot be
    asked. "I could not tell" must not read as "they are missing": a
    false alarm here sends the reader to reinstall fonts they already
    have, which is worse than the silence this replaces.
    """
    wanted = ("Inter", "JetBrains Mono")
    if context.platform == WINDOWS:
        # Windows has no package manager for these, so the plan asks the
        # reader to install them - which is a reason to check, not a
        # reason not to. An instruction nobody verifies is how a font
        # goes missing silently, and a per-user install lands here.
        fonts = context.home / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"
        if not fonts.is_dir():
            return ""
        blob = " ".join(path.name for path in fonts.iterdir())
        blob = blob.replace("-", " ").replace("_", " ")
        absent = [name for name in wanted if name.replace(" ", "") not in blob.replace(" ", "")]
        return ", ".join(absent)
    listed = context.runner.run(["fc-list", ":", "family"])
    if not listed.ok:
        # fontconfig is not there to ask. On macOS it often is not.
        # Under `home` only. `/Library/Fonts` would answer for the
        # machine running the tests rather than the machine being
        # described - the same trap `Context.exists` was added for - and
        # a cask installs into the user's own directory anyway.
        fonts = context.home / "Library" / "Fonts"
        if not fonts.is_dir():
            return ""
        installed = [path.name for path in fonts.iterdir()]
        if not installed:
            return ""
        blob = " ".join(installed).replace("-", " ").replace("_", " ")
    else:
        blob = listed.stdout
    absent = [name for name in wanted if name.replace(" ", "") not in blob.replace(" ", "")]
    return ", ".join(absent)


def _windows_font_install_command() -> list[str]:
    """Install the PDF fonts for the current Windows user, unattended.

    There are no dependable font packages in the community winget source.
    Download the publishers' versioned archives instead, verify the exact
    bytes before extracting them, and use Windows' documented per-user font
    location and registry key. Per-user installation avoids UAC and is the
    same scope pdkboot's font check reads.
    """
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "$ProgressPreference = 'SilentlyContinue'; "
        "$work = Join-Path ([IO.Path]::GetTempPath()) "
        "('pdkboot-fonts-' + [guid]::NewGuid()); "
        "$fontDir = Join-Path $env:LOCALAPPDATA 'Microsoft\\Windows\\Fonts'; "
        "$fontKey = 'HKCU:\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts'; "
        "New-Item -ItemType Directory -Force -Path $work,$fontDir | Out-Null; "
        "New-Item -Path $fontKey -Force | Out-Null; "
        "try { "
        f"$archives = @(@{{Name='inter'; Uri='{WINDOWS_INTER_URL}'; "
        f"Sha='{WINDOWS_INTER_SHA256}'}}, "
        f"@{{Name='jetbrains'; Uri='{WINDOWS_JETBRAINS_MONO_URL}'; "
        f"Sha='{WINDOWS_JETBRAINS_MONO_SHA256}'}}); "
        "foreach ($archive in $archives) { "
        "$zip = Join-Path $work ($archive.Name + '.zip'); "
        "$out = Join-Path $work $archive.Name; "
        "Invoke-WebRequest -Uri $archive.Uri -OutFile $zip; "
        "$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant(); "
        "if ($actual -ne $archive.Sha) { "
        "throw \"Font archive checksum failed for $($archive.Name)\" }; "
        "Expand-Archive -LiteralPath $zip -DestinationPath $out -Force }; "
        "$fonts = @("
        "@{Path='inter\\Inter.ttc'; Name='Inter (TrueType)'},"
        "@{Path='inter\\InterVariable.ttf'; Name='Inter Variable (TrueType)'},"
        "@{Path='inter\\InterVariable-Italic.ttf'; Name='Inter Variable Italic (TrueType)'},"
        "@{Path='jetbrains\\fonts\\ttf\\JetBrainsMono-Regular.ttf'; "
        "Name='JetBrains Mono Regular (TrueType)'},"
        "@{Path='jetbrains\\fonts\\ttf\\JetBrainsMono-Italic.ttf'; "
        "Name='JetBrains Mono Italic (TrueType)'},"
        "@{Path='jetbrains\\fonts\\ttf\\JetBrainsMono-Bold.ttf'; "
        "Name='JetBrains Mono Bold (TrueType)'},"
        "@{Path='jetbrains\\fonts\\ttf\\JetBrainsMono-BoldItalic.ttf'; "
        "Name='JetBrains Mono Bold Italic (TrueType)'}) ; "
        "foreach ($font in $fonts) { "
        "$source = Join-Path $work $font.Path; "
        "if (-not (Test-Path -LiteralPath $source)) { "
        "throw \"Font file missing from archive: $($font.Path)\" }; "
        "$file = Split-Path -Leaf $source; "
        "Copy-Item -LiteralPath $source -Destination (Join-Path $fontDir $file) -Force; "
        "New-ItemProperty -Path $fontKey -Name $font.Name -Value $file "
        "-PropertyType String -Force | Out-Null } "
        "} finally { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }"
    )
    return ["powershell", "-NoProfile", "-Command", script]


def _plan_pandoc(context: Context) -> Plan:
    if context.platform == MACOS:
        return Plan(
            commands=[
                ["brew", "install", "pandoc", "pango"],
                # The PDF embeds these; the website loads them from a CDN
                # at view time and so never notices they are absent
                # (prodockit-userguide#101, #249).
                ["brew", "install", "--cask", *PDF_FONT_CASKS],
            ]
        )
    if context.platform == UBUNTU:
        # Ubuntu's own pandoc package is several major versions behind -
        # far enough to change how the PDF renders (#207, #209). The CI
        # workflows and the User Guide both download the pinned release
        # directly, using dpkg to pick the right architecture so the same
        # command works on amd64, arm64 and under Rosetta.
        v = PANDOC_VERSION
        deb_url = (
            f"https://github.com/jgm/pandoc/releases/download/{v}/"
            f"pandoc-{v}-1-$(dpkg --print-architecture).deb"
        )
        download_and_install = [
            [
                "bash",
                "-c",
                f'curl -fsSL -o /tmp/pandoc.deb "{deb_url}" && {APT_SH} install -y /tmp/pandoc.deb',
            ]
        ]
        if context.pdkboot:
            download_and_install = [
                ["bash", "-c", f'curl -fsSL -o /tmp/pandoc.deb "{deb_url}"'],
                _apt("install", "-y", "/tmp/pandoc.deb"),
            ]
        return Plan(
            commands=[
                _apt("install", "-y", "curl"),
                *download_and_install,
                _apt(
                    "install",
                    "-y",
                    "libpango-1.0-0",
                    "libpangoft2-1.0-0",
                    "libharfbuzz-subset0",
                    *PDF_FONT_PACKAGES,
                ),
            ]
        )
    # MSYS2 carries Pango, which is what WeasyPrint draws text through on
    # Windows. The User Guide walks the reader through a MINGW64 shell
    # and the Environment Variables dialog; all three steps run
    # unattended, so they do.
    # Both of these are facts about the installation rather than about this
    # project, and neither can be known from here: winget installs MSYS2
    # where it likes, and Pango must match the Python process that loads
    # it. Windows on ARM may run x64 tools under emulation, so neither a
    # PowerShell process nor the host architecture reliably answers that
    # question. pdkboot asks its own Python interpreter (#393).
    pandoc_upgrade = False
    pandoc_install: list[str] | None = _winget(
        "JohnMacFarlane.Pandoc",
        PANDOC_VERSION,
        resilient=context.pdkboot,
    )
    if context.pdkboot:
        installed = context.runner.run([pandoc_command(context), "--version"])
        installed_version = _pandoc_version(installed.stdout) if installed.ok else None
        installed_major = installed_version.split(".")[0] if installed_version else ""
        if installed_major.isdigit() and int(installed_major) < PANDOC_MIN_MAJOR:
            pandoc_install = _winget_upgrade("JohnMacFarlane.Pandoc", PANDOC_VERSION)
            pandoc_upgrade = True
        elif installed_version is not None:
            # A partial run may have installed Pandoc and Pango before a
            # later font download lost the network. Repeating the pinned
            # install then exits 1 with "A package version is already
            # installed. Installation cancelled" and used to prevent the
            # repair command from ever being reached.
            pandoc_install = None

    environments = _PDKBOOT_MSYS2_ENVIRONMENTS if context.pdkboot else _MSYS2_ENVIRONMENTS
    arm, other = environments["arm64"], environments["other"]
    roots = ", ".join(f'"{root}"' for root in _MSYS2_ROOTS)
    if context.pdkboot:
        selected = arm if _windows_python_is_arm64(context) else other
        select_environment = f"$msysEnv = '{selected[0]}'; $pkg = '{selected[1]}'; "
    else:
        select_environment = (
            "$nativeArch = $env:PROCESSOR_ARCHITECTURE; "
            f"$msysEnv = if ($nativeArch -eq 'ARM64') {{ '{arm[0]}' }} "
            f"else {{ '{other[0]}' }}; "
            f"$pkg = if ($msysEnv -eq '{arm[0]}') {{ '{arm[1]}' }} "
            f"else {{ '{other[1]}' }}; "
        )
    pango = (
        "$roots = @(" + roots + "); "
        '$root = $roots | Where-Object { Test-Path "$_\\usr\\bin\\bash.exe" } '
        "| Select-Object -First 1; "
        "if (-not $root) { "
        "Write-Host \"MSYS2 was not found. Looked in: $($roots -join ', ')\"; "
        'Write-Host "Install it, or run pacman for pango in its own shell yourself."; '
        "exit 1 }; " + select_environment + 'Write-Host "Using MSYS2 at $root ($msysEnv)"; '
        # `--needed` so a rerun is a no-op rather than a reinstall, and
        # `--noconfirm` because pacman asks otherwise.
        '& "$root\\usr\\bin\\bash.exe" -lc "pacman -S --noconfirm --needed $pkg"; '
        "exit $LASTEXITCODE"
    )
    # Appended only when absent: a PATH with the same entry on it four
    # times is what a tool that assumed one run looks like. The directory
    # follows the environment found above, for the same reason.
    path_entry = (
        "$roots = @(" + roots + "); "
        '$root = $roots | Where-Object { Test-Path "$_\\usr\\bin\\bash.exe" } '
        "| Select-Object -First 1; "
        "if (-not $root) { exit 1 }; "
        + select_environment
        + '$bin = Join-Path $root "$msysEnv\\bin"; '
        "$p=[Environment]::GetEnvironmentVariable('Path','User'); "
        'if ($p -notlike "*$bin*") { '
        "[Environment]::SetEnvironmentVariable('Path', $p + \";$bin\", 'User') }; "
        "[Environment]::SetEnvironmentVariable("
        "'WEASYPRINT_DLL_DIRECTORIES', $bin, 'User')"
    )
    commands = [
        *([pandoc_install] if pandoc_install is not None else []),
        _winget("MSYS2.MSYS2", resilient=context.pdkboot),
        ["powershell", "-NoProfile", "-Command", pango],
        ["powershell", "-NoProfile", "-Command", path_entry],
    ]
    if context.pdkboot:
        commands.append(_windows_font_install_command())
    return Plan(
        commands=commands,
        describe=(
            f"Upgrade Pandoc to the supported {PANDOC_VERSION} release, then "
            "prepare the Windows PDF libraries"
            if pandoc_upgrade
            else ""
        ),
        action="UPGRADE" if pandoc_upgrade else "",
        destructive=pandoc_upgrade,
        # Independent of the winget install, so either order works - after
        # it, so the automated half is not held up behind a manual one.
        follow_up=(
            []
            if context.pdkboot
            else [
                "After setup finishes, open a new PowerShell before running build "
                "commands yourself. pdkboot has refreshed its own PATH for this run, "
                "so do not close this window now.",
                "Install the fonts the PDF uses, which Windows has no package "
                "manager for: download the desktop (.ttf/.otf) files for Inter and "
                "JetBrains Mono from fonts.google.com, select them all, right-click, "
                "and choose 'Install'.",
            ]
        ),
        confirm=("" if context.pdkboot else "Have you installed the fonts?"),
    )


# ---------------------------------------------------------------------------
# 13. The project's own virtual environment, and what goes in it
# ---------------------------------------------------------------------------


def _project_venv(context: Context) -> Path:
    """The virtual environment *inside the project*.

    Not the one bootstrap is running from. That one necessarily predates
    the project - `pip install prodockit` has to happen before there is
    anything to clone - and the User Guide's is a second, separate
    environment created in the project directory afterwards. Its own
    prompts say so (`(.venv) yourname@Mac your-project %`), and the VS
    Code Python extension finds the project's `.venv` and activates it in
    every new terminal, which is the whole reason it is there
    (prodockit-extensions#248).
    """
    return context.config.resolved_project_dir(context.home) / ".venv"


def _venv_python(context: Context) -> Path:
    venv = _project_venv(context)
    if context.platform == WINDOWS:
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _venv_command(context: Context, name: str) -> Path:
    """A console script inside the project's own environment.

    The project's `zensical`, not whichever one happens to be on PATH:
    the version is pinned in the project's `requirements.txt`, and a
    different one outside it would build the site differently from CI.
    """
    venv = _project_venv(context)
    if context.platform == WINDOWS:
        return venv / "Scripts" / f"{name}.exe"
    return venv / "bin" / name


def _venv_activation(context: Context) -> Path:
    venv = _project_venv(context)
    return venv / ("Scripts/Activate.ps1" if context.platform == WINDOWS else "bin/activate")


def _project_venv_is_structurally_complete(context: Context) -> bool:
    """Whether the generated environment has Python, pip, and activation support."""
    python = _venv_python(context)
    if not python.exists() or not _venv_activation(context).exists():
        return False
    return context.runner.run([str(python), "-m", "pip", "--version"]).ok


_MACOS_DYLD_MARKER = "# Added by pdkboot for WeasyPrint"


def _homebrew_library_path(context: Context) -> str:
    """The Homebrew library directory WeasyPrint's loader needs on macOS."""
    prefix = context.runner.run(["brew", "--prefix"])
    root = prefix.stdout.strip() if prefix.ok and prefix.stdout.strip() else "/opt/homebrew"
    return str(Path(root) / "lib")


def _macos_loader_line(context: Context) -> str:
    library = _homebrew_library_path(context)
    return (
        f'export DYLD_FALLBACK_LIBRARY_PATH="{library}'
        '${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"'
    )


def _macos_loader_is_configured(context: Context) -> bool:
    activate = _project_venv(context) / "bin" / "activate"
    try:
        expected = f"{_MACOS_DYLD_MARKER}\n{_macos_loader_line(context)}"
        return expected in activate.read_text(encoding="utf-8")
    except OSError:
        return False


def _imports_from_project_venv(context: Context, module: str) -> CommandResult:
    """Runs `import <module>` using the *project's* interpreter."""
    command = [str(_venv_python(context)), "-c", f"import {module}"]
    if context.pdkboot and context.platform == MACOS:
        command = [
            "env",
            f"DYLD_FALLBACK_LIBRARY_PATH={_homebrew_library_path(context)}",
            *command,
        ]
    return context.runner.run(command)


_PYTHON_VERSION_PROBE = "import platform; print(platform.python_version())"


def _project_build_python(project: Path) -> str | None:
    """The Python release the project and its non-matrix CI builds use."""
    try:
        version = (project / ".python-version").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return version if re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", version) else None


def _project_environment_python(context: Context) -> str | None:
    """The actual interpreter version inside the generated environment."""
    result = context.runner.run(
        [str(_venv_python(context)), "-c", _PYTHON_VERSION_PROBE]
    )
    return result.stdout.strip() if result.ok and result.stdout.strip() else None


def _python_minor(version: str) -> tuple[int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)", version)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _check_project_env(context: Context) -> CheckResult:
    """Whether the project can actually build, asked of the project itself.

    Three distinct failures, and they need distinct answers - "run pip
    again" is the right advice for one of them and useless for the other
    two.

    The WeasyPrint probe is the one the User Guide singles out:

        Check that WeasyPrint can find its graphics libraries. This is
        the one part of the setup `pip` cannot verify for you.

    It is a stricter test than it looks. Importing WeasyPrint loads Pango
    and its friends through the system's dynamic linker, so a successful
    import proves both that the Python package is installed *and* that
    the native libraries the pandoc stage installed can actually be
    found. `pip` exiting zero proves neither.
    """
    if (unknown := _needs_config(context, "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not project.exists():
        project_absent = _blocked if context.pdkboot else _missing
        return project_absent("no project directory yet")
    if not _venv_python(context).exists():
        return _missing(f"no virtual environment at {_project_venv(context)}")
    if not (project / "requirements.txt").exists():
        return _wrong("the project has no requirements.txt to install")
    if context.pdkboot and not _project_venv_is_structurally_complete(context):
        return _wrong(
            f"the virtual environment at {_project_venv(context)} is incomplete - "
            "it will be archived and rebuilt"
        )
    if not _imports_from_project_venv(context, "zensical").ok:
        return _missing("the project's dependencies are not installed")
    weasyprint = _imports_from_project_venv(context, "weasyprint")
    if not weasyprint.ok:
        # Installed but unusable, which is exactly what WRONG is for -
        # and reinstalling it would not help, so the detail has to point
        # at the libraries rather than at pip.
        library_source = {
            MACOS: "Homebrew's libraries",
            WINDOWS: "the MSYS2 libraries matching this Python's architecture",
            UBUNTU: "the system Pango libraries",
        }[context.platform]
        return _wrong(
            "WeasyPrint is installed but cannot load its graphics libraries - "
            f"the pandoc stage installs {library_source}"
        )
    if context.pdkboot and context.platform == MACOS and not _macos_loader_is_configured(context):
        return _wrong(
            "WeasyPrint works in this run, but the project environment does not yet "
            "preserve Homebrew's library path for future shells"
        )
    build_python = _project_build_python(project)
    environment_python = _project_environment_python(context) if build_python else None
    if (
        build_python
        and environment_python
        and _python_minor(build_python) != _python_minor(environment_python)
    ):
        return _ok(
            f"the project's own environment, {_project_venv(context)}, is ready - "
            f"built with Python {environment_python}, while the project and CI build "
            f"with Python {build_python}"
        )
    # Says whose environment it is. There are two in a finished setup -
    # prodockit's own and this one - and a reader who has just been asked
    # about the first should not have to guess which this is (#381).
    return _ok(f"the project's own environment, {_project_venv(context)}, is ready")


#: Asked of the interpreter rather than read from this process. The two
#: are the same interpreter in a real run, but a test suite is launched
#: however its runner feels like launching it - CI uses
#: `actions/setup-python`, which is not a virtual environment - and a
#: check that reads `sys` directly answers differently there than on a
#: developer's machine, for reasons that have nothing to do with the code
#: under test (prodockit-extensions#381).
_IN_A_VENV = "import sys; print(sys.prefix != sys.base_prefix)"


def _running_in_a_venv(context: Context) -> bool:
    """Whether the interpreter running bootstrap is a virtual environment's."""
    said = context.runner.run([sys.executable, "-c", _IN_A_VENV])
    return said.ok and said.stdout.strip() == "True"


def _can_build_environments(context: Context) -> bool:
    """Whether `sys.executable` has the machinery to make a virtual environment.

    Debian and Ubuntu ship the standard library's `venv` without
    `ensurepip`, in a package of their own.
    """
    return context.runner.run([sys.executable, "-c", "import ensurepip, venv"]).ok


def _check_own_venv(context: Context) -> CheckResult:
    """Whether prodockit itself is running inside a virtual environment.

    First, because it is the prerequisite for the run rather than a step
    within it (prodockit-extensions#381).

    There are two environments in a finished setup and they are easy to
    confuse:

    1. **prodockit's own** - the one `pdk bootstrap` is running from.
       This stage.
    2. **the project's** - `<project>/.venv`, holding Zensical and
       everything else in `requirements.txt`. Built much later, with
       `sys.executable -m venv` - which is to say, built *by* the first.

    A system Python is the case that goes wrong. Debian and Ubuntu refuse
    `pip install` outside a virtual environment, and ship `venv` without
    `ensurepip` besides, so the run failed at the project environment in
    words about the project rather than about the interpreter building
    it.

    Nothing here can be repaired in place: a new environment needs a new
    process, so the answer cannot change while this one is running.
    Hence `verifiable=False` - the steps are shown, and the next run is
    what confirms them.
    """
    if not _running_in_a_venv(context):
        return CheckResult(
            Status.MISSING,
            f"running from {sys.executable}, which is not a virtual environment",
            verifiable=False,
        )
    if not _can_build_environments(context):
        # Inside one, but unable to make another - so the project's
        # environment cannot be built. Rare, and better said here than
        # discovered fifteen stages later.
        return _missing(f"{sys.executable} cannot build the project's environment")
    return _ok(sys.prefix)  # the environment it is running from


def _venv_recipe(context: Context, interpreter: str = "") -> list[str]:
    """The exact lines that put prodockit in an environment of its own.

    Written out per platform rather than described, because the reader
    who needs them is at a shell that has just refused to install
    something and a paraphrase is one more thing to get right.

    Not runnable here: the last line replaces the process that would be
    running them, so these are shown and the reader runs them.
    """
    if context.platform == WINDOWS:
        home = r"%USERPROFILE%"
        command = "pdkboot" if context.pdkboot else "pdk bootstrap"
        return [
            rf"{interpreter or 'py'} -m venv {home}\.venvs\prodockit",
            rf"{home}\.venvs\prodockit\Scripts\pip install prodockit",
            rf"{home}\.venvs\prodockit\Scripts\{command}",
        ]
    command = "pdkboot" if context.pdkboot else "pdk bootstrap"
    return [
        f"{interpreter or 'python3'} -m venv ~/.venvs/prodockit",
        "~/.venvs/prodockit/bin/pip install prodockit",
        f"~/.venvs/prodockit/bin/{command}",
    ]


def _plan_own_venv(context: Context) -> Plan:
    """Install whatever is missing, then show exactly how to run from an environment.

    The install is offered only when the machinery is genuinely absent.
    On a system Python that can already build environments there is
    nothing to install, and an `apt install` in front of the three lines
    that matter would be noise.
    """
    installers = {
        UBUNTU: _apt("install", "-y", "python3-venv"),
        MACOS: ["brew", "install", "python@3.14"],
        WINDOWS: _winget("Python.Python.3.14", resilient=context.pdkboot),
    }
    missing_machinery = not _can_build_environments(context)
    return Plan(
        commands=[installers[context.platform]] if missing_machinery else [],
        describe=(
            "Install the machinery Python needs to create virtual environments"
            if missing_machinery
            else ""
        ),
        instructions=[
            "Put prodockit in an environment of its own and run it from there. "
            "This run cannot move itself - a new environment needs a new process:",
            # Named exactly on macOS when a Python has just been installed
            # beside the broken one: Homebrew does not relink `python3` for
            # a versioned formula, so `python3` would still be the
            # interpreter this stage was working around.
            *_venv_recipe(
                context,
                "python3.14" if missing_machinery and context.platform == MACOS else "",
            ),
        ],
        confirm="Is prodockit running from its own environment now?",
    )


def _plan_project_env(context: Context) -> Plan:
    """Creates the project's venv and installs its requirements into it.

    `sys.executable` builds the environment - the interpreter bootstrap
    is itself running under, which is a real Python of a known version -
    and then the *new* environment's own pip does the installing.

    That second part is the one worth being careful about. A bare `pip
    install -r requirements.txt` would find whichever pip is on `PATH`,
    which is bootstrap's own, and install the project's dependencies into
    bootstrap's environment instead. It would exit zero, this stage would
    re-check, and the project's `.venv` would still be empty - the failure
    only surfacing at the reader's first build. Naming the interpreter
    explicitly is what makes that impossible.
    """
    project = context.config.resolved_project_dir(context.home)
    venv = _project_venv(context)
    python = _venv_python(context)
    commands: list[list[str]] = []
    rebuild = (
        context.pdkboot and venv.exists() and not _project_venv_is_structurally_complete(context)
    )
    if rebuild:
        backup = venv.parent / ".venv.pdk-incomplete-backup"
        suffix = 2
        while backup.exists():
            backup = venv.parent / f".venv.pdk-incomplete-backup-{suffix}"
            suffix += 1
        commands.append(_move_path_command(context, venv, backup))
    if not python.exists() or rebuild:
        commands.append([sys.executable, "-m", "venv", str(venv)])
    commands.append([str(python), "-m", "pip", "install", "-r", str(project / "requirements.txt")])
    if context.pdkboot and context.platform == MACOS:
        activate = venv / "bin" / "activate"
        library = _homebrew_library_path(context)
        script = (
            "from pathlib import Path; import sys\n"
            "path = Path(sys.argv[1]); marker = sys.argv[2]; library = sys.argv[3]\n"
            "text = path.read_text(encoding='utf-8')\n"
            "line = 'export DYLD_FALLBACK_LIBRARY_PATH=\"' + library + "
            "'${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}\"'\n"
            "lines = text.splitlines()\n"
            "updated_lines = []\n"
            "index = 0\n"
            "while index < len(lines):\n"
            "    if lines[index] == marker:\n"
            "        index += 1\n"
            "        if index < len(lines) and lines[index].startswith("
            "'export DYLD_FALLBACK_LIBRARY_PATH='):\n"
            "            index += 1\n"
            "        continue\n"
            "    updated_lines.append(lines[index])\n"
            "    index += 1\n"
            "updated = ('\\n'.join(updated_lines).rstrip() + '\\n\\n' + marker + "
            "'\\n' + line + '\\n')\n"
            "temporary = path.with_name(path.name + '.pdkboot.tmp')\n"
            "temporary.write_text(updated, encoding='utf-8')\n"
            "temporary.chmod(path.stat().st_mode)\n"
            "temporary.replace(path)\n"
        )
        commands.append([sys.executable, "-c", script, str(activate), _MACOS_DYLD_MARKER, library])
    return Plan(cwd=str(project), commands=commands)


# ---------------------------------------------------------------------------
# 14. Node and the two toolchains
# ---------------------------------------------------------------------------


#: Commands whose name cannot be run bare on Windows, with the resolver
#: that finds them. `CreateProcess` appends `.exe` and nothing else, so a
#: `.cmd` shim - which is what npm and VS Code's CLI are - is "not found"
#: however right `PATH` is.
_RESOLVE_BEFORE_RUNNING: dict[str, Callable[[Context], str]] = {
    "npm": npm_command,
    "pandoc": pandoc_command,
    "node": node_command,
    "code": lambda context: vscode_command(context) or "code",
}


def resolve_for_execution(context: Context, command: Sequence[str]) -> list[str]:
    """`command` with its name resolved as late as possible.

    A plan is built before any of it runs, so a command installed by an
    earlier line of the *same* plan cannot be found when the plan is
    written. The node stage is exactly that: `winget install` Node, then
    `npm ci` twice - and `npm` resolved to the bare name, which on
    Windows can never work (prodockit-extensions#405).

    Resolving here instead costs one lookup per command and is the only
    point at which the answer can be right.
    """
    if not command:
        return list(command)
    resolver = _RESOLVE_BEFORE_RUNNING.get(command[0])
    if resolver is None:
        return list(command)
    return [resolver(context), *command[1:]]


def _check_node(context: Context) -> CheckResult:
    if (unknown := _needs_config(context, "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if context.pdkboot and not project.exists():
        # This stage installs system Node *and* the render toolchains held
        # inside the clone. Running its combined plan before the clone exists
        # installs half the stage and then sends npm into a nonexistent path
        # (prodockit-extensions#610).
        return _blocked("no project directory yet")
    result = context.runner.run([node_command(context), "--version"])
    if not result.ok:
        return _missing("node is not installed")
    raw = result.stdout.strip().lstrip("v")
    major = raw.split(".")[0] if raw else ""
    if not major.isdigit():
        return _wrong(f"could not read a version from {result.stdout.strip()!r}")
    if int(major) < NODE_MAJOR:
        return _wrong(f"node {raw} is older than the {NODE_MAJOR}.x the builds use")
    if not context.runner.run([npm_command(context), "--version"]).ok:
        # The signature of Ubuntu's own nodejs package, or a NodeSource
        # install whose `curl` line failed - node without npm.
        return _wrong("node is installed but npm is not")

    # Everything above is about node itself; the rest of this stage's plan
    # installs the two toolchains and, on Ubuntu, the browser Mermaid
    # renders through. A check that stopped at `node --version` reported
    # `ok` on a machine that had node and nothing else - so a reader who
    # had installed Node themselves was told this stage was done, got no
    # toolchains, and found out at the first diagram (#224).
    if project.exists() and context.pdkboot:
        mermaid = project / "tools" / "mermaid" / "node_modules" / ".bin"
        mermaid_cli = mermaid / ("mmdc.cmd" if context.platform == WINDOWS else "mmdc")
        mathjax_bundle = project.joinpath(*mathjax.SOURCE)
        absent = []
        if not mermaid_cli.is_file():
            absent.append("mermaid")
        if not mathjax_bundle.is_file() or not mathjax_bundle.stat().st_size:
            absent.append("mathjax")
        if absent:
            return _wrong(f"node {raw}, but {' and '.join(absent)} is not installed")
    elif project.exists():
        absent = [
            name
            for name in ("mermaid", "mathjax")
            if not (project / "tools" / name / "node_modules").exists()
        ]
        if absent:
            return _wrong(f"node {raw}, but {' and '.join(absent)} is not installed")
    if context.platform == UBUNTU and not _chromium_ready(context):
        return _wrong(
            f"node {raw}, but Puppeteer has no system Chromium to use - it would "
            "download one, which on ARM64 is a build that cannot run"
        )
    return _ok(f"node {raw}")


def _node_runtime_state(context: Context) -> tuple[int | None, bool]:
    """Installed Node major and whether its npm companion is runnable."""
    result = context.runner.run([node_command(context), "--version"])
    if not result.ok:
        return None, False
    raw = result.stdout.strip().lstrip("v")
    major = raw.split(".")[0] if raw else ""
    parsed = int(major) if major.isdigit() else None
    npm_ok = context.runner.run([npm_command(context), "--version"]).ok
    return parsed, npm_ok


def _chromium_ready(context: Context) -> bool:
    """Whether Mermaid has a browser it can actually use, on Ubuntu.

    Both halves matter. A Chromium that is installed but never pointed at
    leaves Puppeteer downloading its own; the exports without a Chromium
    point at nothing.
    """
    found = context.runner.run(["bash", "-c", "which chromium-browser || which chromium"])
    if not found.ok or not found.stdout.strip():
        return False
    exports = context.runner.run(
        ["bash", "-c", f"grep -q {PUPPETEER_SKIP_VAR} {context.home / '.bashrc'}"]
    )
    return exports.ok


#: Where Puppeteer is told to find a browser, and told not to fetch one.
PUPPETEER_PATH_VAR = "PUPPETEER_EXECUTABLE_PATH"
PUPPETEER_SKIP_VAR = "PUPPETEER_SKIP_DOWNLOAD"

#: Resolves the system Chromium the way the User Guide does. Ubuntu has
#: called the package both things across releases.
_WHICH_CHROMIUM = "$(which chromium-browser || which chromium)"


def _puppeteer_exports() -> str:
    """The two exports, as a shell prefix.

    Computed by the shell at run time rather than by a plan beforehand,
    because the path does not exist yet when the plan is built - the same
    plan installs Chromium a command earlier.
    """
    return f"export {PUPPETEER_PATH_VAR}={_WHICH_CHROMIUM}; export {PUPPETEER_SKIP_VAR}=true; "


def _plan_node(context: Context) -> Plan:
    project = context.config.resolved_project_dir(context.home)
    ubuntu_node_install = [
        _apt("install", "-y", "curl"),
        ["bash", "-c", "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -"],
        _apt("install", "-y", "nodejs"),
    ]
    if context.pdkboot:
        ubuntu_node_install = [
            _apt("install", "-y", "curl"),
            [
                "curl",
                "-fsSL",
                "-o",
                "/tmp/nodesource-setup.sh",
                "https://deb.nodesource.com/setup_22.x",
            ],
            ["sudo", "-E", "bash", "/tmp/nodesource-setup.sh"],
            _apt("install", "-y", "nodejs"),
        ]
    install = {
        MACOS: [["brew", "install", "node"]],
        UBUNTU: ubuntu_node_install,
        WINDOWS: [_winget("OpenJS.NodeJS.LTS", resilient=context.pdkboot)],
    }[context.platform]

    upgrade = False
    repair = False
    if context.pdkboot:
        major, npm_ok = _node_runtime_state(context)
        if major is not None and major >= NODE_MAJOR and npm_ok:
            install = []
        elif context.platform == WINDOWS and major is not None and major < NODE_MAJOR:
            install = [_winget_upgrade("OpenJS.NodeJS.LTS")]
            upgrade = True
        elif context.platform == WINDOWS and major is not None and not npm_ok:
            install = [_winget_repair("OpenJS.NodeJS.LTS")]
            repair = True

    mermaid = str(project / "tools" / "mermaid")
    mathjax = str(project / "tools" / "mathjax")

    if context.platform != UBUNTU:
        return Plan(
            commands=[
                *install,
                [npm_command(context), "ci", "--prefix", mermaid],
                [npm_command(context), "ci", "--prefix", mathjax],
            ],
            describe=(
                f"Upgrade Node to the supported {NODE_MAJOR}.x release, then install "
                "the project toolchains"
                if upgrade
                else (
                    "Repair the existing Node installation so npm works, then install "
                    "the project toolchains"
                    if repair
                    else ""
                )
            ),
            action="UPGRADE" if upgrade else ("REPAIR" if repair else ""),
            # An upgrade or repair of an existing runtime is an explicit
            # decision. A fresh install and npm's project-local work keep the
            # established yes default.
            destructive=upgrade or repair,
        )

    # Chromium first, and the exports before `npm ci` rather than after.
    #
    # `npm ci` in tools/mermaid triggers Puppeteer's own postinstall
    # download, and that download is not guaranteed to match the CPU it
    # lands on: on ARM64 - an Apple-silicon Linux VM, Graviton, a
    # Raspberry Pi - it fetches an x86_64 Chrome that can never run.
    # Nothing fails at install time. Mermaid simply cannot render a
    # diagram later, a long way from the command that caused it
    # (prodockit-userguide#102, prodockit-extensions#249).
    exports = _puppeteer_exports()
    bashrc = context.home / ".bashrc"
    persist = (
        f"grep -q {PUPPETEER_SKIP_VAR} {bashrc} 2>/dev/null || "
        f"printf '%s\n%s\n' "
        f"'export {PUPPETEER_PATH_VAR}={_WHICH_CHROMIUM}' "
        f"'export {PUPPETEER_SKIP_VAR}=true' >> {bashrc}"
    )
    return Plan(
        commands=[
            *install,
            _apt("install", "-y", "chromium-browser"),
            # Appended once. Rerunning bootstrap should not leave a
            # profile with the same two exports in it four times over.
            ["bash", "-c", persist],
            ["bash", "-c", f"{exports}npm ci --prefix {mermaid}"],
            ["bash", "-c", f"{exports}npm ci --prefix {mathjax}"],
        ]
    )


# ---------------------------------------------------------------------------
# 15. VS Code extensions (platform-independent)
# ---------------------------------------------------------------------------


def _absent_extensions(context: Context) -> list[str] | None:
    """Which wanted extensions are not installed, or None if unaskable.

    Asked with the command the plan installs them with. A bare `code`
    cannot run on Windows at all - `CreateProcess` appends `.exe` and
    nothing else, and VS Code's CLI is `code.cmd` - so this check could
    never pass there, whatever was installed. The stage reported "is VS
    Code installed?" about the VS Code it had just driven successfully,
    four times, by full path (prodockit-extensions#410).
    """
    result = context.runner.run([vscode_command(context) or "code", "--list-extensions"])
    if not result.ok:
        return None
    installed = {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
    return [name for name in VSCODE_EXTENSIONS if name.lower() not in installed]


def _check_extensions(context: Context) -> CheckResult:
    absent = _absent_extensions(context)
    if absent is None:
        return _missing("could not list extensions - is VS Code installed?")
    if absent:
        # Name what is already there as well as what is not. "missing: x"
        # alone, next to a plan that reinstalled all three, read as though
        # nothing was installed.
        present = len(VSCODE_EXTENSIONS) - len(absent)
        detail = f"{present} of {len(VSCODE_EXTENSIONS)} installed; missing: {', '.join(absent)}"
        if not present:
            # None of them installed is MISSING, not WRONG, and the
            # difference is what the `--apply` prompt defaults to. Asking
            # `[y/N]` to install extensions on a machine that has none is
            # asking the reader to argue for the thing they ran bootstrap
            # to get (prodockit-extensions#242). WRONG defaults to no
            # because reapplying can destroy work; there is nothing here
            # to destroy.
            return _missing(detail)
        return _wrong(detail)
    return _ok(f"all {len(VSCODE_EXTENSIONS)} installed")


def _plan_extensions(context: Context) -> Plan:
    """Installs only what is absent.

    Reinstalling extensions that are already present is slow, noisy, and
    misleading to read in `--dry-run`: three `code --install-extension`
    lines under "missing: one-extension" says the tool has not understood
    its own check.
    """
    absent = _absent_extensions(context)
    wanted = VSCODE_EXTENSIONS if absent is None else absent
    # By the path it was found at, so a Windows session that has just
    # installed VS Code can still install extensions without being sent
    # away to open a new terminal (#292).
    command = vscode_command(context) or "code"
    return Plan(commands=[[command, "--install-extension", name] for name in wanted])


#: Every stage, in the order they have to happen. Ordering is a real
#: dependency, not a preference: nothing can be cloned before SSH
#: authenticates, and the Node toolchains install *into* the clone.
# ---------------------------------------------------------------------------
# 16. The editor's own settings, in the project
# ---------------------------------------------------------------------------


#: Zensical Studio needs Markdown files handed to the right language
#: mode, and LTeX+ needs to be told which language it is checking. Both
#: live in the project's own `.vscode/settings.json`, so they are one
#: stage (prodockit-extensions#248).
_MARKDOWN_ASSOCIATION = {"*.md": "python-markdown"}

#: Merges the wanted keys into whatever is already there, rather than
#: writing the file. `.vscode/settings.json` is the reader's, and may
#: hold settings this knows nothing about; and VS Code writes it itself
#: whenever a setting is changed in the UI. Run through the interpreter
#: bootstrap is already using, so it needs nothing installed and behaves
#: the same on all three platforms.
_MERGE_SETTINGS = """
import json, sys, pathlib
path, incoming = pathlib.Path(sys.argv[1]), json.loads(sys.argv[2])
path.parent.mkdir(parents=True, exist_ok=True)
try:
    current = json.loads(path.read_text(encoding="utf-8") or "{}")
except FileNotFoundError:
    current = {}
if not isinstance(current, dict):
    raise ValueError(f"{path} is not a JSON object")
raw_associations = current.get("files.associations")
associations = dict(raw_associations) if isinstance(raw_associations, dict) else {}
associations.update(incoming.pop("files.associations", {}))
if associations:
    current["files.associations"] = associations
current.update(incoming)
path.write_text(json.dumps(current, indent=2) + "\\n", encoding="utf-8")
"""

_LEGACY_MERGE_SETTINGS = """
import json, sys, pathlib
path, incoming = pathlib.Path(sys.argv[1]), json.loads(sys.argv[2])
path.parent.mkdir(parents=True, exist_ok=True)
try:
    current = json.loads(path.read_text(encoding="utf-8") or "{}")
except (OSError, ValueError):
    current = {}
if not isinstance(current, dict):
    current = {}
associations = dict(current.get("files.associations") or {})
associations.update(incoming.pop("files.associations", {}))
if associations:
    current["files.associations"] = associations
current.update(incoming)
path.write_text(json.dumps(current, indent=2) + "\\n", encoding="utf-8")
"""


def _reader_language(context: Context) -> str | None:
    """The reader's own language, as LTeX+ spells it, or None.

    Asked of the machine rather than pinned. The User Guide says `en-GB`
    because that is right for its own readers, but bootstrap runs on
    other people's computers - and a document checked against the wrong
    variety of a language is worse than one not checked at all, because
    the corrections are confident and wrong. Imposing `en-GB` on an
    `en-US` reader is the same mistake as the reverse.

    None when the machine will not say. Leaving the setting out is better
    than guessing: LTeX+ has a default of its own, and an absent value is
    at least honest about not knowing.
    """
    if context.platform == MACOS:
        # The GUI locale, which is the one the reader actually chose;
        # `LANG` is frequently unset in a macOS GUI session's shell.
        result = context.runner.run(["defaults", "read", "-g", "AppleLocale"])
    elif context.platform == WINDOWS:
        result = context.runner.run(["powershell", "-NoProfile", "-Command", "(Get-Culture).Name"])
    else:
        result = context.runner.run(["locale"])
    if not result.ok:
        return None

    raw = result.stdout.strip()
    if context.platform == UBUNTU:
        # `locale` prints a block of KEY=value lines; LANG is the one
        # naming the language rather than a category override.
        for line in raw.splitlines():
            if line.startswith("LANG="):
                raw = line.partition("=")[2].strip().strip('"')
                break
        else:
            return None
    # en_GB.UTF-8 / en_GB@euro / en-GB all mean the same thing here.
    tag = raw.split(".")[0].split("@")[0].replace("_", "-").strip()
    if not tag or tag.upper() in ("C", "POSIX"):
        return None
    return tag


def _wanted_settings(context: Context) -> dict[str, object]:
    settings: dict[str, object] = {"files.associations": dict(_MARKDOWN_ASSOCIATION)}
    language = _reader_language(context)
    if language is not None:
        settings["ltex.language"] = language
    return settings


def _settings_path(context: Context) -> Path:
    return context.config.resolved_project_dir(context.home) / ".vscode" / "settings.json"


def _check_vscode_settings(context: Context) -> CheckResult:
    if (unknown := _needs_config(context, "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not project.exists():
        project_absent = _blocked if context.pdkboot else _missing
        return project_absent("no project directory yet")
    path = _settings_path(context)
    try:
        current = json.loads(path.read_text(encoding="utf-8") or "{}")
    except FileNotFoundError:
        return _missing(f"{path} is not there yet")
    except OSError:
        return (
            _wrong(f"{path} cannot be read")
            if context.pdkboot
            else _missing(f"{path} is not there yet")
        )
    except ValueError:
        return (
            _wrong(f"{path} is not valid JSON")
            if context.pdkboot
            else _missing(f"{path} is not there yet")
        )
    if not isinstance(current, dict):
        return _wrong(f"{path} is not a JSON object")

    associations = current.get("files.associations") or {}
    missing = [
        key
        for key, value in _MARKDOWN_ASSOCIATION.items()
        if not isinstance(associations, dict) or associations.get(key) != value
    ]
    if missing:
        return _missing("Markdown is not associated with Zensical Studio's language mode")
    language = _reader_language(context)
    if language is not None and current.get("ltex.language") != language:
        return _missing(f"LTeX+ is not set to {language}")
    return _ok(str(path))


def _plan_vscode_settings(context: Context) -> Plan:
    path = _settings_path(context)
    if context.pdkboot and path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, ValueError):
            return Plan(
                instructions=[
                    f"{path} already exists but is not valid JSON. It has been left "
                    "unchanged. Remove comments or trailing commas (which VS Code "
                    "accepts but JSON tools do not), then save the file."
                ],
                confirm="Have you repaired the existing VS Code settings file?",
            )
        if not isinstance(current, dict):
            return Plan(
                instructions=[
                    f"{path} is a valid JSON value, but VS Code settings must be a "
                    "JSON object. It has been left unchanged; replace the outer "
                    "value with an object before continuing."
                ],
                confirm="Have you repaired the existing VS Code settings file?",
            )
    language = _reader_language(context)
    wanted = "Markdown opens in Zensical Studio's editor"
    if language is not None:
        wanted += f", and LTeX+ checks your writing as {language}"
    return Plan(
        describe=f"Update {_settings_path(context)} so {wanted}",
        commands=[
            [
                sys.executable,
                "-c",
                _MERGE_SETTINGS if context.pdkboot else _LEGACY_MERGE_SETTINGS,
                str(_settings_path(context)),
                json.dumps(_wanted_settings(context)),
            ]
        ],
    )


# ---------------------------------------------------------------------------
# 17. The citation style the first build needs
# ---------------------------------------------------------------------------


#: What the template points `csl_style` at, and where to get it. Fetched
#: rather than committed (prodockit-userguide#97), which would be a
#: detail except that `prodockit.bibliography` is enabled by default - so
#: `zensical serve`, `zensical build` and `prodockit pdf` all fail
#: outright until the file is there (prodockit-userguide#103, #249).
DEFAULT_CSL_STYLE = "harvard-cite-them-right.csl"
CSL_STYLE_URL = "https://www.zotero.org/styles/harvard-cite-them-right"


def _configured_csl_style(context: Context) -> str:
    """The style the project asks for, or the template's default.

    Read by scanning rather than parsing: the value is wanted before the
    project's own environment exists, so this cannot depend on anything
    installed into it.
    """
    config = context.config.resolved_project_dir(context.home) / "zensical.toml"
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_CSL_STYLE
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "csl_style" not in stripped:
            continue
        _, _, value = stripped.partition("=")
        name = value.strip().strip("\"'")
        if name:
            return name
    return DEFAULT_CSL_STYLE


def _check_csl_style(context: Context) -> CheckResult:
    if (unknown := _needs_config(context, "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not project.exists():
        project_absent = _blocked if context.pdkboot else _missing
        return project_absent("no project directory yet")
    style = _configured_csl_style(context)
    path = project / style
    if not path.exists():
        return _missing(f"{style} is not in the project")
    if not path.stat().st_size:
        # A failed download leaves an empty file behind, and an empty
        # file is not a missing one - it looks satisfied to anything
        # asking only whether the path exists.
        return _wrong(f"{style} is empty - the download did not complete")
    return _ok(str(path))


def _plan_csl_style(context: Context) -> Plan:
    project = context.config.resolved_project_dir(context.home)
    style = _configured_csl_style(context)
    if style != DEFAULT_CSL_STYLE:
        # Somebody has chosen a different style, and this only knows
        # where the default one lives.
        return Plan(
            instructions=[
                f"This project asks for {style}, which is not the style bootstrap "
                f"knows how to fetch. Download it into {project} yourself - "
                "https://www.zotero.org/styles lists them.",
            ]
        )
    if context.platform == WINDOWS:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            # `$ProgressPreference` first: on PowerShell 5.1, still the
            # Windows default, Invoke-WebRequest's progress bar makes a
            # download dramatically slower - minutes rather than seconds
            # - which reads as a hang (#244, #295).
            f"$ProgressPreference = 'SilentlyContinue'; "
            f'Invoke-WebRequest -Uri "{CSL_STYLE_URL}" -OutFile {style}',
        ]
    else:
        command = ["curl", "-fsSL", "-o", style, CSL_STYLE_URL]
    return Plan(cwd=str(project), commands=[command])


# ---------------------------------------------------------------------------
# 18. MathJax for the website, installed rather than committed
# ---------------------------------------------------------------------------


#: Where the installer puts things, borrowed rather than restated. The
#: paths, the bundle's name and the configuration all live in
#: `prodockit.mathjax` now, which is the single implementation both this
#: stage and a project's CI call (prodockit-extensions#276).
def _mathjax_paths(context: Context) -> tuple[Path, Path, Path, Path, Path]:
    project = context.config.resolved_project_dir(context.home)
    return (
        project.joinpath(*mathjax.SOURCE),
        project.joinpath(*mathjax.LICENSE_SOURCE),
        project.joinpath(*mathjax.DEST, mathjax.BUNDLE),
        project.joinpath(*mathjax.DEST, mathjax.LICENSE),
        project.joinpath(*mathjax.CONFIG),
    )


def _check_mathjax(context: Context) -> CheckResult:
    """Whether the website can typeset the maths the PDF already can.

    Both halves are needed and they fail differently. Without the config
    the bundle loads and does nothing; without the bundle the config
    configures nothing. Either way the page shows raw TeX, which is what
    was reported (prodockit-extensions#263).
    """
    if (unknown := _needs_config(context, "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not project.exists():
        project_absent = _blocked if context.pdkboot else _missing
        return project_absent("no project to install it into yet")
    if not (project / "docs").is_dir():
        return _missing("no project to install it into yet")
    source, license_source, bundle, license_path, config = _mathjax_paths(context)
    absent = [
        name for name, path in (
            ("the config", config),
            ("the bundle", bundle),
            ("the licence", license_path),
        ) if not path.exists()
    ]
    if absent:
        return _missing(f"{' and '.join(absent)} for the website is not installed")
    if context.pdkboot:
        try:
            bundle_bytes = bundle.read_bytes()
            license_bytes = license_path.read_bytes()
            config_text = config.read_text(encoding="utf-8")
        except OSError:
            return _wrong("the generated MathJax files cannot be read")
        if not bundle_bytes:
            return _wrong("the generated MathJax bundle is empty - installation was interrupted")
        if not license_bytes:
            return _wrong("the generated MathJax licence is empty - installation was interrupted")
        if source.exists():
            try:
                if bundle_bytes != source.read_bytes():
                    return _wrong(
                        "the generated MathJax bundle does not match the project's pinned copy"
                    )
            except OSError:
                return _wrong("the project's pinned MathJax bundle cannot be read")
        if license_source.exists():
            try:
                if license_bytes != license_source.read_bytes():
                    return _wrong(
                        "the generated MathJax licence does not match the project's pinned copy"
                    )
            except OSError:
                return _wrong("the project's pinned MathJax licence cannot be read")
        if config_text != mathjax.CONFIG_SOURCE:
            return _wrong("the generated MathJax configuration is incomplete or out of date")
        try:
            ignored = (project / ".gitignore").read_text(encoding="utf-8").splitlines()
        except OSError:
            ignored = []
        missing_ignores = [entry for entry in mathjax.IGNORED if entry not in ignored]
        if missing_ignores:
            return _wrong(
                "MathJax is installed, but its generated files are not all excluded from git: "
                + ", ".join(missing_ignores)
            )
    if not source.exists():
        # Installed, but the pinned copy it came from is gone - so nothing
        # can say whether the two still agree.
        return _ok(f"{bundle.name} is installed")
    return _ok(f"{bundle.name} is installed")


def _plan_mathjax(context: Context) -> Plan:
    """Runs the command that does this, rather than a copy of it.

    The configuration used to live here *and* in a template's CI, which
    never runs bootstrap - two copies of a thing whose whole failure mode
    is being subtly wrong, since both produce a valid file and the site
    simply typesets one way locally and another when published
    (prodockit-extensions#276).

    `prodockit init-mathjax` is now the single implementation, and this
    calls it - the same arrangement the repoint stage already has with
    `prodockit sync-repo`.
    """
    project = context.config.resolved_project_dir(context.home)
    return Plan(
        cwd=str(project),
        describe=(
            "Install MathJax for the website: copy the browser bundle out of "
            "tools/mathjax's pinned install, copy its licence, write the browser "
            "configuration, and keep the generated assets out of git"
        ),
        commands=[[*_prodockit_command(), "init-mathjax"]],
    )


# ---------------------------------------------------------------------------
# 19. The published site answers - the last thing, and only a test
# ---------------------------------------------------------------------------


def site_url(context: Context) -> str:
    """Where this project's site is published, or "" if unknowable."""
    template = context.host.pages_url
    namespace = context.config.namespace.strip()
    project = context.config.project_name.strip()
    if not (template and namespace and project):
        return ""
    return template.format(namespace=namespace, project=project)


def _http_probe(context: Context, url: str) -> tuple[int | None, str]:
    """What a stranger gets from `url`, or `None` if the asking failed.

    `None` is not a status and must never be read as one - a refused
    connection, a DNS failure and a timeout all mean the question was
    never put (prodockit-extensions#374).

    Asked with Python rather than by launching `curl`. That subprocess
    cost three fixes of its own - curl arriving four stages later than
    the first check that wanted it, `-o /dev/null` on a platform without
    one, and a misdiagnosis where PowerShell's `curl` alias looked like
    an absent program - none of which were really about curl (#449).

    Redirects are deliberately not followed: a `302` is how a
    login-walled site is recognised as published.
    """
    answer = context.fetch(url)
    if answer is not None:
        return int(answer.status), ""
    if not context.pdkboot:
        return None, ""
    # Python's TLS trust can differ from the operating system's on macOS.
    # curl uses the system trust store, so it is a useful second opinion.
    curl = "curl.exe" if context.platform == WINDOWS else "curl"
    result = context.runner.run(
        [
            curl,
            "-sS",
            "-o",
            os.devnull,
            "-w",
            "%{http_code}",
            "--max-redirs",
            "0",
            "--connect-timeout",
            "20",
            url,
        ]
    )
    match = re.search(r"\b([1-5]\d\d)\b", result.stdout)
    if match:
        return int(match.group(1)), ""
    combined = f"{result.stdout}\n{result.stderr}".lower()
    certificate_errors = (
        "sec_e_untrusted_root",
        "certificate chain was issued by an authority that is not trusted",
        "certificate verify failed",
        "ssl certificate problem",
    )
    if any(error in combined for error in certificate_errors):
        return None, "the certificate chain is not trusted by this machine"
    return None, ""


def _http_status(context: Context, url: str) -> int | None:
    """Compatibility wrapper for callers that need only the status."""
    return _http_probe(context, url)[0]


def _site_answers(context: Context) -> bool:
    """Whether the published site responds.

    Proof that Pages is switched on, and it needs no token: a Pages site
    is readable by anyone even when its repository is private, which is
    what makes any of this checkable from outside. A probe that could not
    run is not proof of anything, and answers False.
    """
    url = site_url(context)
    return bool(url) and _http_status(context, url) == 200


def _check_site_published(context: Context) -> CheckResult:
    """Whether the documentation site actually answers.

    Deliberately a *test* and not a step. The template's workflow enables
    Pages itself now (`configure-pages` with `enablement: true`), so
    there is nothing here for a reader to do - and an instruction telling
    them to do it anyway is one more thing to misread
    (prodockit-extensions#333).

    It is last because it can only be true after a push has built the
    site. On a first run, before anything has been pushed, "not published
    yet" is the correct and expected answer - which is why it is worded
    as waiting rather than as a fault.

    Fetched anonymously on purpose. A direct 200 proves this exact site;
    a shared authentication response does not, so pdkboot asks the reader
    to confirm that address in their signed-in browser instead.
    """
    if (unknown := _needs_config(context, "namespace", "project_name")) is not None:
        return unknown
    url = site_url(context)
    if not url:
        # A self-hosted GitLab publishes wherever its administrator
        # decided, so there is no address to try. Not a finding - leaving
        # every run permanently one stage short would be worse than the
        # gap it reports - but the detail says it was not checked, rather
        # than implying a site was found.
        return _ok(f"not checked - {context.host.hostname} publishes at no fixed address")
    # A Pages deployment cannot exist before this project's own commit is
    # present on the remote. Check that prerequisite before asking the
    # guessed Pages URL: some installations send *every* path, including a
    # nonexistent one, to the same authentication service. Its redirect is
    # evidence that the login service exists, not that this project has
    # published a site (prodockit-extensions#611).
    if _check_first_push(context).status is not Status.OK:
        return _blocked(
            "the first push has not been confirmed - complete the "
            "'First commit pushed' stage first"
        )
    status, probe_problem = _http_probe(context, url)
    if status == 200:
        # Said plainly, because it is the part readers get wrong: a Pages
        # site is readable by anyone, even when the repository behind it
        # is private. Only an Enterprise plan can restrict who sees it, so
        # on any other plan "private repository" does not mean "private
        # site" - and drafts in docs/ are published as soon as they build.
        return _ok(f"Pages is enabled - {url} (public: anyone with the link can read it)")
    if status is None:
        # Nobody said the site is missing - the question was never put.
        # curl arrives with the Pandoc stage, so a run that has not got
        # that far has no way to ask (prodockit-extensions#374).
        if probe_problem:
            detail = f"could not verify {url} because {probe_problem}"
        else:
            detail = f"could not check {url} from here - the probe did not run"
        if context.pdkboot and context.config.confirmed_site_url == url:
            return _ok(f"published at {url} - confirmed in your browser")
        if context.pdkboot:
            return CheckResult(
                Status.MISSING,
                f"{detail}; confirm it in your browser",
                verifiable=False,
            )
        return _missing(detail)
    if status in (401, 403) or 300 <= status < 400:
        # Authentication responses are deliberately inconclusive. Surrey's
        # Pages gateway returns the same redirect for a published private
        # site and for a path that has never existed, so treating it as proof
        # produced a false `All 23 stages are set up` after a failed pipeline
        # (#611). The browser remains the only project-specific check there.
        if context.pdkboot and context.config.confirmed_site_url == url:
            return _ok(f"published at {url} - confirmed in your browser")
        detail = (
            f"could not verify {url} because {context.host.hostname}'s login response "
            "does not prove that this specific site exists"
        )
        if context.pdkboot:
            return CheckResult(
                Status.MISSING,
                f"{detail}; confirm the exact address in your browser",
                verifiable=False,
            )
        return _missing(detail)
    return _missing(f"{url} is not answering yet")


def _plan_site_published(context: Context) -> Plan:
    """Set the front page's link, once there is a site to link to.

    Every sentence past the first is the host's own, not this stage's.
    They used to be written here as literals, all of them describing
    GitHub - so a GitLab reader was sent looking for a gear beside
    'About' that does not exist, and told their site was readable by
    anyone with the link when reaching it needs a university login
    (prodockit-extensions#444).

    That last one is why this is values rather than a branch: it is not
    merely wrong, it contradicts what the project stage told the same
    reader about the same project, and both cannot be true.
    """
    host = context.host
    url = site_url(context)
    readme = context.config.resolved_project_dir(context.home) / "README.md"
    try:
        readme_already_links_to_site = url in readme.read_text(encoding="utf-8")
    except OSError:
        readme_already_links_to_site = False
    return Plan(
        instructions=[
            f"Push your first commit, and the workflow will publish {url}.",
            # Said rather than done. Setting it needs an authenticated API
            # call, and asking a reader to install and sign into a command
            # line for one field was four ways to go wrong for a link they
            # can paste in ten seconds (#357).
            *(() if readme_already_links_to_site else host.site_link_steps),
            "It enables Pages itself, so there is nothing to switch on.",
            *([host.site_visibility_note] if host.site_visibility_note else []),
            *([host.site_missing_note] if host.site_missing_note else []),
        ],
        confirm="Has your first build published the site?",
    )


# ---------------------------------------------------------------------------
# 19. The first commit, pushed - what actually publishes the project
# ---------------------------------------------------------------------------


#: What a host says when it accepted the connection and then declined the
#: push. Authorisation, not authentication - the key is fine, the account
#: simply may not write here (prodockit-extensions#414).
_PUSH_REFUSED_SIGNS = (
    "not allowed to push",
    "you are not allowed",
    "protected branch",
    "insufficient permission",
    "pre-receive hook declined",
)


def _push_refused(context: Context) -> str:
    """The host's own words when it will not accept a push, else "".

    Asked with `--dry-run`, and only from the one state that cannot
    explain itself: everything committed here, and nothing on the host.
    A first run never reaches this - it has work to commit - so the
    ordinary path pays nothing for it (#304).

    The commands themselves run with the terminal attached rather than
    captured, so their output goes to the reader and not to bootstrap.
    This is how the refusal gets read back at all.
    """
    project = context.config.resolved_project_dir(context.home)
    attempt = context.runner.run(
        [git_command(context), "-C", str(project), "push", "--dry-run", "-u", "origin", "main"]
    )
    if attempt.ok:
        return ""
    said = f"{attempt.stdout}\n{attempt.stderr}".lower()
    return next((sign for sign in _PUSH_REFUSED_SIGNS if sign in said), "")


def _uncommitted_work(context: Context) -> list[str]:
    """The exact porcelain-status lines a first commit would include."""
    project = context.config.resolved_project_dir(context.home)
    pending = context.runner.run(
        [git_command(context), "-C", str(project), "status", "--porcelain"]
    )
    if not pending.ok:
        return []
    return [line for line in pending.stdout.splitlines() if line.strip()]


def _has_uncommitted_work(context: Context) -> bool:
    """Whether the project has changes that are not in a commit yet."""
    return bool(_uncommitted_work(context))


def _check_first_push(context: Context) -> CheckResult:
    """Whether the project has been committed and pushed to its remote.

    Everything before this leaves a working project on one machine and an
    empty repository on the host. The push is what makes it real: it is
    what builds the site, and what the next machine clones
    (prodockit-extensions#339).

    Placed after the local setup stages deliberately, so the first commit
    carries the CSL style, the MathJax bundle and the VS Code settings
    rather than needing a second commit for them.
    """
    if (unknown := _needs_config(context, "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not (project / ".git").exists():
        return _blocked("there is no clone yet - do the 'Project cloned' stage first")
    origin = context.runner.run(
        [git_command(context), "-C", str(project), "remote", "get-url", "origin"]
    )
    if not origin.ok:
        return _blocked("no origin yet - do the 'Clone pointed at your project' stage first")
    if _has_uncommitted_work(context):
        return _missing("there is work here that has never been committed")
    remote = context.runner.run(
        [git_command(context), "-C", str(project), "ls-remote", "origin", "HEAD"]
    )
    if not remote.ok:
        return _wrong("could not reach origin to see what is there")
    if not remote.stdout.strip():
        # Committed here, empty there. Either the push has not been run
        # yet, or it was run and the host declined it - and those need
        # different things from the reader (#414).
        if _push_refused(context):
            return _wrong(
                f"{context.host.hostname} will not accept a push to "
                f"{context.config.namespace.strip()}/{project.name} - the key is fine, "
                "the account is not allowed to write here. Check whether the repository "
                "was issued to somebody else, whether your role on it is more than "
                "Reporter, and whether `main` is a protected branch"
            )
        return _missing(f"{project.name} is still empty on {context.host.hostname}")

    # Something is there - but "something" was read as "your work", so a
    # repository created with the host's own README reported this stage
    # `ok` and the project was never pushed at all
    # (prodockit-extensions#423). The site stage then found nothing
    # published and nobody could see why.
    here = context.runner.run([git_command(context), "-C", str(project), "rev-parse", "HEAD"])
    if not here.ok:
        return _missing("nothing committed here yet")
    if remote.stdout.split()[0] == here.stdout.strip():
        return _ok(f"pushed to {context.host.hostname}")
    if remote_is_only_its_first_readme(context):
        return _missing(
            f"{context.host.hostname} has only the README it made when the "
            "repository was created - your project is not pushed yet"
        )
    # Not a README, and not this project's history either. Somebody's
    # work, and not something to push over on a guess.
    return _wrong(
        f"{context.host.hostname} has commits this project does not - nothing here "
        "will push over them. Look at the repository before going further"
    )


#: The merge that takes the project's tree over the README's, written
#: where a reader will read it: `git log` shows this line and nothing
#: else about how the two histories met.
_ADOPT_MESSAGE = "Add the project to the repository created for it"


def _adopt_commands(context: Context) -> list[list[str]]:
    """Take the host's first commit into this history, or nothing.

    A repository created with "initialize with a README" has a commit
    this project's history does not contain, so an ordinary push is
    rejected as non-fast-forward - and the reader is left with a rejected
    push and a stage that had told them everything was fine (#423).

    That used to be answered with `--force-with-lease`, which a protected
    branch refuses outright: GitLab protects the default branch on
    creation and declines *any* force push to it, lease or no lease, so
    the one case this exists for was also the case most likely to be
    blocked (#442). On an assessed repository the protection is the
    point, and it is usually not the student's to switch off.

    Merging reaches the same end without forcing anything. `-s ours`
    takes this project's tree entire and discards the README's - the
    same outcome the force push had - while keeping the host's commit in
    the history, which is what makes the push a fast-forward.

    Nothing local is rewritten, so a run that already made the commit
    before a push was refused can merge and push on the retry rather
    than needing the commit remade (#414).
    """
    if not remote_is_only_its_first_readme(context):
        return []
    return [
        [git_command(context), "fetch", "origin", "main"],
        [
            git_command(context),
            "merge",
            "--allow-unrelated-histories",
            "-s",
            "ours",
            "FETCH_HEAD",
            "-m",
            _ADOPT_MESSAGE,
        ],
    ]


def _push_command(context: Context) -> list[str]:
    """An ordinary push, always.

    Never forced. Where the remote has a commit of its own,
    `_adopt_commands` has already taken it into this history, so there
    is nothing left to force over - and a push that cannot force cannot
    destroy what it was mistaken about.
    """
    return [git_command(context), "push", "-u", "origin", "main"]


def _plan_first_push(context: Context) -> Plan:
    """Commit everything and push it.

    `git add -A` is right here and nowhere else: this runs once, on a
    project whose entire contents bootstrap has just assembled, so there
    is nothing of the reader's it could sweep up by accident. The
    `.gitignore` the template ships keeps the virtualenv, node_modules
    and the fonts out.
    """
    project = context.config.resolved_project_dir(context.home)
    pending = _uncommitted_work(context)
    return Plan(
        cwd=str(project),
        commands=[
            # Built before the commit, and with the cache cleared.
            #
            # `prodockit sync-repo` rewrites the brand icon in
            # `zensical.toml`, and a build served from `.cache/` keeps
            # showing the template's logo until something clears it -
            # which readers were doing by running `zensical serve` and
            # wondering why (prodockit-extensions#364).
            #
            # It earns its place twice over: the first push is also the
            # first time anything proves this project *builds*, and
            # finding that out here beats finding it out from a red
            # pipeline minutes later.
            [str(_venv_command(context, "zensical")), "build", "--clean"],
            [git_command(context), "add", "-A"],
            # Only when there is something to commit. A push refused by
            # the host - permissions, a protected branch - leaves the
            # commit made and the remote empty, and this stage is then
            # asked to run again. `git commit` with nothing staged exits
            # 1, so the retry failed before reaching the push: the one
            # state the stage could not make progress from was the one it
            # had just reached (prodockit-extensions#414).
            *([[git_command(context), "commit", "-m", "Initial commit"]] if pending else []),
            *_adopt_commands(context),
            _push_command(context),
        ],
        instructions=[
            "This builds the site once, commits everything in the project, "
            "and pushes it - which is what publishes it.",
            *(
                [
                    "These are the exact uncommitted changes that `git add -A` "
                    "will include:\n" + "\n".join(f"  {line}" for line in pending)
                ]
                if context.pdkboot and pending
                else []
            ),
            *(
                [
                    "The repository was created with a README, which nothing here "
                    "wrote and nothing here needs. That commit is taken into this "
                    "project's history and the project's own files replace its "
                    "contents, so nothing is forced and nothing is overwritten - "
                    "if anything else has reached the repository since, the push "
                    "is refused rather than destroying it."
                ]
                if remote_is_only_its_first_readme(context)
                else []
            ),
        ],
        confirm="Commit and push the project?",
    )


# ---------------------------------------------------------------------------
# 10. Pages switched on - asked while the reader is still in the browser
# ---------------------------------------------------------------------------


def _json_object(text: str) -> dict[str, object] | None:
    """The JSON object in `text`, or None if it is not one.

    Parsed rather than matched on substrings: `"has_pages": false` and
    `"has_pages": true` differ by four characters, and a string test for
    the wrong one would report a repository as configured when it is not.
    """
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _check_pages(context: Context) -> CheckResult:
    """Whether Pages is switched on, where that can be seen without a token.

    A **public** repository says so in its own API object - `has_pages` -
    to any anonymous caller. A **private** one answers `404` to
    everything, so nothing about it is visible from outside until a push
    has built the site; the stage that fetches the site is the honest
    test there, and needs no token either.

    This asked `gh` until 0.30.1, which meant installing a tool,
    authenticating it in a browser, from the right directory, on every
    machine - four ways to go wrong for a check another stage already
    makes for free (prodockit-extensions#357).
    """
    if (unknown := _needs_config(context, "namespace", "project_name")) is not None:
        return unknown
    host = context.host
    if not host.pages_setup_steps:
        # GitLab configures its own Pages from the CI job, so there is
        # nothing here for a reader to switch on - and printing GitHub's
        # steps to them would be an instruction to do nothing (#360).
        return _ok(f"{host.hostname} configures Pages from its CI job")
    if not host.repo_api:
        return _ok(f"not checked - {host.hostname} has no anonymous metadata to read")
    namespace = context.config.namespace.strip()
    project = context.config.project_name.strip()
    api = host.repo_api.format(namespace=namespace, project=project)
    seen = context.fetch(api)
    if seen is None:
        # The question was never put - no route, no name, no listener.
        # Saying "cannot be seen from outside a private repository" would
        # name a cause nobody established (#374).
        return _missing(f"could not check {api} from here - the probe did not run")
    described = _json_object(seen.body) if seen.status == 200 else None
    if described is not None and "has_pages" in described:
        if described["has_pages"]:
            return _ok("Pages is enabled")
        return _missing("Pages is not switched on for this repository")
    # Private, or the host does not answer anonymously. The site itself
    # is asked first: it is readable without a token even when its
    # repository is not, so a project that has already published says so
    # here rather than carrying a finding it could never clear.
    if _site_answers(context):
        return _ok(f"Pages is enabled - {site_url(context)} answers")
    # Otherwise the reader is shown the steps. Reporting `ok` here meant
    # a stage that had never been done was skipped in silence, on the one
    # host where it has to be done by hand (prodockit-extensions#374) -
    # "cannot be seen" and "is set up" are not the same sentence and were
    # being printed as one.
    #
    # Not verifiable: `404` is all this repository will ever say to an
    # anonymous caller, so asking again after the reader returns from the
    # browser cannot confirm it. The site stage at the end of the run is
    # what settles it.
    return CheckResult(
        Status.MISSING,
        "cannot be seen from outside a private repository - switch it on if you "
        "have not; the site check at the end of the run proves it",
        verifiable=False,
    )


def _plan_pages(context: Context) -> Plan:
    """The browser steps, put here rather than buried in stage 9.

    A stage of its own because it was missed twice as a trailing item on
    somebody else's list, and the cost of missing it is a red first
    build whose error names the site rather than the setting.
    """
    # The host's own words, not GitHub's. A GitLab reader has nothing to
    # switch on, and the check above reports them satisfied before this
    # is ever built (#360).
    return Plan(
        instructions=list(context.host.pages_setup_steps),
        confirm=f"Have you switched Pages on for {context.host.hostname}?",
    )


# ---------------------------------------------------------------------------
# 7. Where the project comes from - asked once the host can be reached
# ---------------------------------------------------------------------------


def _check_clone_source(context: Context) -> CheckResult:
    """Whether it is settled where the project's contents come from.

    Placed after the SSH stages and before the clone, because that is the
    first point at which the question can be *answered*. `--configure`
    runs before any of this: on a fresh machine there is no key yet, so
    `git ls-remote` cannot authenticate and the honest answer there is "I
    could not look" - which left the decision never actually offered, on
    the run where it matters most (prodockit-extensions#348).

    Nothing to decide is `ok`, not a question. A reader whose project
    does not exist yet, or exists and is empty, gets the template - the
    only workable answer - and is not asked to choose between one thing.
    """
    if (unknown := _needs_config(context, "namespace", "project_name")) is not None:
        return unknown
    # A clone already pointing at the reader's own project settles it:
    # the contents are on disk and answering cannot change where they
    # came from. Re-running a finished machine was putting three paths to
    # a reader who had already taken one (prodockit-extensions#368). A
    # clone still on the template is the case where the decision really
    # is ahead of them, so that one stays a question.
    origin = _origin_url(context)
    if origin and origin != context.host.template_remote:
        return _ok(f"already cloned from {origin}")
    if context.config.source_url.strip():
        return _ok(f"cloning {context.config.source_url.strip()}")
    if not own_project_has_content(context):
        # Which of these it is matters. "ok" with nothing after it reads
        # the same whether the host was searched and found empty or never
        # reachable at all - and that ambiguity is the fault chased
        # through #344 and #351 (prodockit-extensions#356).
        # Both answers name the address that was asked about. A reader
        # whose project plainly exists was told there was no repository,
        # with nothing to show that the question had been put to a
        # different address than the one they had in mind
        # (prodockit-extensions#377). The namespace is one field shared
        # by every host, so a run that changes host carries the previous
        # host's namespace with it, and the wrong address is the likely
        # answer rather than an exotic one.
        probed = context.host.remote_url(
            context.config.namespace.strip(), context.config.project_name.strip()
        )
        if project_on_host(context) is None:
            if context.pdkboot:
                return _blocked(
                    f"could not yet ask {context.host.hostname} about {probed} - "
                    "this stage will be rechecked after SSH is ready"
                )
            return _ok(
                f"could not reach {context.host.hostname} to ask about {probed} - "
                "the template will be cloned"
            )
        # "Not found" is never only that. Both hosts answer a private
        # repository the key cannot see with the words they use for one
        # that does not exist - github.com says `Repository not found.`
        # either way - so absence is not something this can report.
        if context.pdkboot and project_on_host(context):
            return _ok(f"{probed} exists and is empty - the template will be cloned")
        return _ok(f"nothing visible at {probed} - the template will be cloned")
    name = f"{context.config.namespace.strip()}/{context.config.project_name.strip()}"
    if context.pdkboot:
        # The standalone preview deliberately exposes only the proven-safe
        # path for now. Keep the decision in this run's config object so the
        # clone plan remains a pure reader and `--dry-run` does not make a
        # second network call while building it. It need not be written to
        # disk: once cloned, origin settles this stage permanently.
        context.config.source_url = name
        context.config.history = "keep"
        return _ok(
            f"Option 1 selected automatically: {name} has work on the host, so pdkboot "
            "will clone the full repository and keep its existing commit history and origin"
        )
    return _missing(f"{name} has work on the host - choose what to do with it")


def _plan_clone_source(context: Context) -> Plan:
    """The three paths, as a numbered choice with no default.

    Not three yes/no questions in a row: that invites pressing Enter
    through them, and one of these answers deletes commits that cannot be
    recovered.
    """
    name = f"{context.config.namespace.strip()}/{context.config.project_name.strip()}"
    return Plan(
        instructions=[
            f"{name} already exists on {context.host.hostname} and has content in it.",
            f"Open https://{context.host.hostname}/{name} and confirm this exact active "
            "project opens without redirecting to an archived or deletion-scheduled name "
            "before choosing. Git can still follow a renamed project's old address.",
        ],
        choices=(
            f"clone the full repo {name!r}, then leave the existing git records and "
            "sync origin unchanged",
            f"clone the full repo {name!r}, then delete the existing git records and "
            "set up a new remote repo",
            "start from the template in a new repository of your own. Choose this only "
            f"if {name} is not the repository your work belongs in - a repository "
            "issued to you carries the permissions that decide who can read it, and a "
            "new one will not have them.",
        ),
        confirm="Select 1, 2 or 3",
    )


STAGES: tuple[Stage, ...] = (
    # First of all, because it is the prerequisite for the run rather
    # than a step within it: everything below is installed or built by
    # the interpreter this asks about (#381).
    Stage(
        "own-venv",
        "prodockit runs in an environment of its own",
        _check_own_venv,
        _plan_own_venv,
    ),
    Stage("vscode", "Visual Studio Code", _check_vscode, _plan_vscode),
    Stage("git", "Git, installed and configured", _check_git, _plan_git),
    Stage("ssh-key", "SSH keypair", _check_ssh_key, _plan_ssh_key),
    # Before the upload, not after: `ssh -T` is how the upload stage
    # checks itself, and without this stanza ssh never offers the key at
    # all (prodockit-extensions#239).
    Stage("ssh-config", "SSH config points at the key", _check_ssh_config, _plan_ssh_config),
    # Also before the upload: a passphrase-protected key cannot sign
    # the host's challenge unless an agent is holding it (#246).
    Stage("ssh-agent", "Key loaded into the ssh agent", _check_ssh_agent, _plan_ssh_agent),
    Stage("ssh-upload", "SSH key on the host", _check_ssh_authenticates, _plan_ssh_upload),
    # Between the SSH stages and the clone: the first point at which the
    # host can be reached, and the last at which the answer still
    # matters (#348).
    Stage(
        "clone-source",
        "Where the project comes from",
        _check_clone_source,
        _plan_clone_source,
    ),
    Stage("clone", "Project cloned", _check_clone, _plan_clone),
    # Before the remote is set: resetting deletes .git, remotes and all,
    # so doing it afterwards would throw away the repoint (#248).
    Stage("fresh-history", "A history of your own", _check_fresh_history, _plan_fresh_history),
    Stage("own-project", "Your own project on the host", _check_own_project, _plan_own_project),
    # Straight after creating the project, while the reader is still in
    # the browser - it was missed twice as a trailing item on stage 9's
    # list (#341).
    Stage("pages", "Pages switched on", _check_pages, _plan_pages),
    Stage("remote", "Clone pointed at your project", _check_remote, _plan_remote),
    Stage(
        "identity",
        "Commit identity in the project",
        _check_project_identity,
        _plan_project_identity,
    ),
    # Named for what it checks. It installs the libraries WeasyPrint
    # needs, but cannot verify them - importing WeasyPrint is what does
    # that, and WeasyPrint is not installed until the project's own
    # environment exists, one stage below (#248).
    Stage("pandoc", "Pandoc, and the libraries WeasyPrint needs", _check_pandoc, _plan_pandoc),
    Stage(
        "project-env",
        "Project environment and its dependencies",
        _check_project_env,
        _plan_project_env,
    ),
    Stage("node", "Node.js and the render toolchains", _check_node, _plan_node),
    Stage("extensions", "VS Code extensions", _check_extensions, _plan_extensions),
    # Last, so that the state bootstrap leaves behind is one where
    # opening the project in VS Code is enough to start writing.
    Stage(
        "vscode-settings",
        "VS Code settings for the project",
        _check_vscode_settings,
        _plan_vscode_settings,
    ),
    # `prodockit.bibliography` is on by default and this file is not in
    # the clone, so without it the very first build fails outright.
    Stage("csl-style", "Citation style for the first build", _check_csl_style, _plan_csl_style),
    # After node, because the bundle is copied out of what `npm ci` put
    # in tools/mathjax (#263).
    Stage("mathjax", "MathJax for the website", _check_mathjax, _plan_mathjax),
    # Last of all, because it can only be true once a push has built the
    # site - and it is a test rather than a step: the workflow enables
    # Pages itself (#333).
    # Before the site check, because the push is what builds the site.
    Stage("first-push", "First commit pushed", _check_first_push, _plan_first_push),
    Stage(
        "site",
        "Documentation site published",
        _check_site_published,
        _plan_site_published,
    ),
)
