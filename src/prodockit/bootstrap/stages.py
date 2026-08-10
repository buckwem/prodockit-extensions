# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The eleven stages of a full install, as check/plan pairs.

Every stage answers two questions and performs neither: `check` decides
whether it is already done, `plan` says what would make it done. Nothing
here runs an installer - see `prodockit.bootstrap.model` for why that
split is the whole testing strategy.

Five of the eleven are platform-independent (SSH keys, cloning,
repointing the remote, the project's commit identity, VS Code
extensions), which is nearly half the work written once. That is the
argument for a stage abstraction over three separate per-platform
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

from pathlib import Path

from prodockit.bootstrap.model import (
    MACOS,
    SSH_NO_PROMPT_OPTIONS,
    UBUNTU,
    WINDOWS,
    CheckResult,
    Context,
    Plan,
    Stage,
    Status,
)

#: The VS Code extensions the User Guide installs. Kept here rather than
#: in the template so bootstrap can check them without a project.
VSCODE_EXTENSIONS = (
    "ms-python.python",
    "zensical.zensical-studio",
    "streetsidesoftware.code-spell-checker",
)

#: Minimum Node major version - what the automated builds use.
NODE_MAJOR = 22

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

#: How to add the `code` command once the application is installed.
_VSCODE_SHELL_COMMAND_HELP = (
    "In VS Code, open the Command Palette (Cmd+Shift+P / Ctrl+Shift+P) and run "
    "'Shell Command: Install \'code\' command in PATH'."
)


def _vscode_app_installed(context: Context) -> bool:
    for raw in _VSCODE_APP_PATHS.get(context.platform, ()):
        path = Path(raw.replace("~", str(context.home), 1)) if raw.startswith("~") else Path(raw)
        if context.exists(path):
            return True
    return False


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
    if _installed(context, "code"):
        return _ok()
    if _vscode_app_installed(context):
        return _wrong("VS Code is installed, but the `code` command is not on PATH")
    return _missing("VS Code is not installed")


def _plan_vscode(context: Context) -> Plan:
    # Installed already: the only thing missing is the shell command, and
    # reinstalling the application would fail rather than supply it.
    if _vscode_app_installed(context):
        return Plan(instructions=[_VSCODE_SHELL_COMMAND_HELP])
    if context.platform == MACOS:
        return Plan(
            commands=[["brew", "install", "--cask", "visual-studio-code"]],
            # After the install: the Command Palette being asked for is
            # the one in the application brew has just put there (#230).
            follow_up=[_VSCODE_SHELL_COMMAND_HELP],
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
        return Plan(
            commands=[
                ["sudo", "apt", "install", "-y", "curl"],
                [
                    "bash",
                    "-c",
                    'arch="$(dpkg --print-architecture)"; '
                    'case "$arch" in amd64) arch=x64 ;; esac; '
                    "curl -fsSL -o /tmp/code.deb "
                    '"https://update.code.visualstudio.com/latest/linux-deb-$arch/stable" '
                    "&& sudo apt install -y /tmp/code.deb",
                ],
            ]
        )
    return Plan(commands=[["winget", "install", "--id", "Microsoft.VisualStudioCode"]])


# ---------------------------------------------------------------------------
# 2. Git, installed *and* configured
# ---------------------------------------------------------------------------


def _check_git(context: Context) -> CheckResult:
    if not _installed(context, "git"):
        return _missing("git is not installed")
    name = context.runner.run(["git", "config", "--global", "user.name"])
    email = context.runner.run(["git", "config", "--global", "user.email"])
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
    return _ok(f"{name.stdout.strip()} <{email.stdout.strip()}>")


def _plan_git(context: Context) -> Plan:
    install = {
        MACOS: [["brew", "install", "git"]],
        UBUNTU: [["sudo", "apt", "update"], ["sudo", "apt", "install", "-y", "git"]],
        WINDOWS: [["winget", "install", "Git.Git"]],
    }[context.platform]
    configure = [
        ["git", "config", "--global", "user.name", context.config.full_name],
        ["git", "config", "--global", "user.email", context.config.email],
    ]
    # Only install if it is actually absent - a rerun repairing unset
    # identity should not reinstall git underneath a working one.
    if _installed(context, "git"):
        return Plan(commands=configure)
    return Plan(commands=[*install, *configure])


# ---------------------------------------------------------------------------
# 3. SSH keypair (platform-independent)
# ---------------------------------------------------------------------------


def _check_ssh_key(context: Context) -> CheckResult:
    private = _key_path(context)
    public = private.with_suffix(".pub")
    if private.exists() and public.exists():
        return _ok(str(private))
    if private.exists() or public.exists():
        return _wrong(f"only half the keypair exists at {private}")
    return _missing(f"no keypair at {private}")


def _plan_ssh_key(context: Context) -> Plan:
    private = _key_path(context)
    return Plan(
        commands=[
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-C",
                context.config.email,
                "-f",
                str(private),
            ]
        ],
        instructions=[
            "ssh-keygen will ask for a passphrase - choose a strong one and "
            "remember it; it protects the key if your machine is lost.",
        ],
    )


# ---------------------------------------------------------------------------
# 4. Public key on the host - guide and verify
# ---------------------------------------------------------------------------


def _ssh_probe(context: Context) -> list[str]:
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
    return [ssh, "-T", *options, context.host.ssh_target]


def _check_ssh_authenticates(context: Context) -> CheckResult:
    """Whether the key actually authenticates.

    `ssh -T` against a git host exits non-zero even on success (there is
    no shell to give you), so the exit code says nothing - the greeting
    string is the only reliable signal, which is why every `Host` carries
    its own.
    """
    result = context.runner.run(_ssh_probe(context))
    combined = f"{result.stdout}\n{result.stderr}"
    if context.host.ssh_success in combined:
        return _ok(f"authenticated to {context.host.hostname}")
    if "Host key verification failed" in combined or "authenticity of host" in combined:
        return _wrong(
            f"{context.host.hostname} is not a known host yet - run "
            f"`ssh -T {context.host.ssh_target}` once and accept the fingerprint"
        )
    if "Permission denied" in combined:
        return _missing(f"{context.host.hostname} rejected the key")
    return _wrong(f"could not confirm authentication to {context.host.hostname}")


def _plan_ssh_upload(context: Context) -> Plan:
    public = _key_path(context).with_suffix(".pub")
    instructions = [
        f"Open {context.host.ssh_keys_url}",
    ]
    if context.host.login_note:
        instructions.append(context.host.login_note)
    instructions += [
        f"Paste the contents of {public} - the .pub file, never the one without it.",
        "Give it any title you like, then save.",
        f"If this machine has never connected to {context.host.hostname} before, "
        f"run `ssh -T {context.host.ssh_target}` in a terminal once and answer "
        "`yes` to the fingerprint question. Trusting a host key is a decision "
        "bootstrap leaves to you rather than making silently on your behalf.",
    ]
    # Instructions only, deliberately. `ssh -T` is the *check*, and it
    # cannot also be a plan command: against a git host it exits non-zero
    # even on success (there is no shell to give you), so a runner that
    # judges commands by their exit code sees every probe as a failure and
    # stops the run - which is what it did, on a machine whose key simply
    # had not been uploaded yet (#234).
    #
    # Nothing is lost by dropping it: applying a stage always re-runs its
    # check, and that check reads the greeting rather than the exit code.
    return Plan(instructions=instructions)


# ---------------------------------------------------------------------------
# 5. Template cloned (platform-independent)
# ---------------------------------------------------------------------------

def _check_clone(context: Context) -> CheckResult:
    if (unknown := _needs_config(context, "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not project.exists():
        return _missing(f"{project} does not exist")
    if not (project / ".git").exists():
        return _wrong(f"{project} exists but is not a git repository")
    return _ok(str(project))


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
    source = context.config.source_url or context.host.template_remote
    return Plan(commands=[["git", "clone", source, str(project)]])


# ---------------------------------------------------------------------------
# 6. The reader's own project exists on the host - guide and verify
# ---------------------------------------------------------------------------


def _check_own_project(context: Context) -> CheckResult:
    if (unknown := _needs_config(context, "namespace", "project_name")) is not None:
        return unknown
    url = context.host.remote_url(context.config.namespace, context.config.project_name)
    result = context.runner.run(["git", "ls-remote", url])
    if result.ok:
        return _ok(url)
    return _missing(f"{url} is not reachable")


def _plan_own_project(context: Context) -> Plan:
    host = context.host
    return Plan(
        instructions=[
            f"Open {host.new_project_url}",
            f"Create a blank {host.project_word} named {context.config.project_name!r} "
            f"in the {host.group_word} {context.config.namespace!r}.",
            "Set visibility to Private.",
            "Untick every 'initialize with' option - the clone you already have "
            "provides the contents, and an initialised remote would conflict with it.",
        ],
        # Instructions only, for the same reason as the SSH upload above:
        # `git ls-remote` is this stage's check, and a check run as a plan
        # command turns "you have not finished in the browser yet" - the
        # normal case - into a failed command that ends the run. Re-checking
        # after apply asks the same question, and asks it again.
    )


# ---------------------------------------------------------------------------
# 7. Remote repointed at it (platform-independent)
# ---------------------------------------------------------------------------


def _check_remote(context: Context) -> CheckResult:
    if (unknown := _needs_config(context, "namespace", "project_name")) is not None:
        return unknown
    project = context.config.resolved_project_dir(context.home)
    if not (project / ".git").exists():
        return _missing("no clone to repoint yet")
    wanted = context.host.remote_url(context.config.namespace, context.config.project_name)
    result = context.runner.run(["git", "-C", str(project), "remote", "get-url", "origin"])
    if not result.ok:
        return _missing("no `origin` remote is set")
    actual = result.stdout.strip()
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
    synced = context.runner.run(["prodockit", "sync-repo", "--check"], cwd=str(project))
    if not synced.ok:
        return _wrong("origin is right, but the project config still needs syncing")
    return _ok(wanted)


def _plan_remote(context: Context) -> Plan:
    project = context.config.resolved_project_dir(context.home)
    wanted = context.host.remote_url(context.config.namespace, context.config.project_name)
    # Both run *in* the project. `git -C` could carry the path itself, but
    # `prodockit sync-repo` reads zensical.toml from the working directory
    # and has no equivalent flag, so the plan sets one for both rather
    # than half the commands knowing where they are.
    return Plan(
        cwd=str(project),
        commands=[
            ["git", "remote", "set-url", "origin", wanted],
            # sync-repo rewrites repo_url/repo_name/edit_uri/site_url and the
            # README badges to match the new remote. Without it the clone
            # keeps advertising the template's own repository.
            ["prodockit", "sync-repo"],
        ],
    )


# ---------------------------------------------------------------------------
# 8. Commit identity, in the project (platform-independent)
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
        return _missing("no clone to set an identity in yet")

    unset: list[str] = []
    mismatched: list[str] = []
    for key, wanted in _identity_wanted(context).items():
        result = context.runner.run(["git", "-C", str(project), "config", "--local", key])
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
            ["git", "config", "--local", key, value]
            for key, value in _identity_wanted(context).items()
        ],
    )


# ---------------------------------------------------------------------------
# 9. Pandoc and WeasyPrint's native stack
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
    result = context.runner.run(["pandoc", "--version"])
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
    return _ok(f"pandoc {version}")


def _plan_pandoc(context: Context) -> Plan:
    if context.platform == MACOS:
        return Plan(commands=[["brew", "install", "pandoc", "pango"]])
    if context.platform == UBUNTU:
        # Ubuntu's own pandoc package is several major versions behind -
        # far enough to change how the PDF renders (#207, #209). The CI
        # workflows and the User Guide both download the pinned release
        # directly, using dpkg to pick the right architecture so the same
        # command works on amd64, arm64 and under Rosetta.
        v = PANDOC_VERSION
        deb_url = (
            f"https://github.com/jgm/pandoc/releases/download/{v}/"
            f'pandoc-{v}-1-$(dpkg --print-architecture).deb'
        )
        return Plan(
            commands=[
                ["sudo", "apt", "install", "-y", "curl"],
                [
                    "bash",
                    "-c",
                    f'curl -fsSL -o /tmp/pandoc.deb "{deb_url}" '
                    "&& sudo apt install -y /tmp/pandoc.deb",
                ],
                [
                    "sudo",
                    "apt",
                    "install",
                    "-y",
                    "libpango-1.0-0",
                    "libpangoft2-1.0-0",
                    "libharfbuzz-subset0",
                ],
            ]
        )
    return Plan(
        commands=[["winget", "install", "--id", "JohnMacFarlane.Pandoc"]],
        # Independent of the winget install, so either order works - after
        # it, so the automated half is not held up behind a manual one.
        follow_up=[
            "WeasyPrint's graphics libraries come from MSYS2 on Windows: install "
            "MSYS2, run `pacman -S mingw-w64-x86_64-pango` in the MINGW64 shell, "
            "then add C:\\msys64\\mingw64\\bin to your user PATH.",
        ],
    )


# ---------------------------------------------------------------------------
# 10. Node and the two toolchains
# ---------------------------------------------------------------------------


def _check_node(context: Context) -> CheckResult:
    result = context.runner.run(["node", "--version"])
    if not result.ok:
        return _missing("node is not installed")
    raw = result.stdout.strip().lstrip("v")
    major = raw.split(".")[0] if raw else ""
    if not major.isdigit():
        return _wrong(f"could not read a version from {result.stdout.strip()!r}")
    if int(major) < NODE_MAJOR:
        return _wrong(f"node {raw} is older than the {NODE_MAJOR}.x the builds use")
    if not context.runner.run(["npm", "--version"]).ok:
        # The signature of Ubuntu's own nodejs package, or a NodeSource
        # install whose `curl` line failed - node without npm.
        return _wrong("node is installed but npm is not")
    return _ok(f"node {raw}")


def _plan_node(context: Context) -> Plan:
    project = context.config.resolved_project_dir(context.home)
    install = {
        MACOS: [["brew", "install", "node"]],
        UBUNTU: [
            ["sudo", "apt", "install", "-y", "curl"],
            ["bash", "-c", "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -"],
            ["sudo", "apt", "install", "-y", "nodejs"],
        ],
        WINDOWS: [["winget", "install", "OpenJS.NodeJS.LTS"]],
    }[context.platform]
    return Plan(
        commands=[
            *install,
            ["npm", "ci", "--prefix", str(project / "tools" / "mermaid")],
            ["npm", "ci", "--prefix", str(project / "tools" / "mathjax")],
        ]
    )


# ---------------------------------------------------------------------------
# 11. VS Code extensions (platform-independent)
# ---------------------------------------------------------------------------


def _absent_extensions(context: Context) -> list[str] | None:
    """Which wanted extensions are not installed, or None if unaskable."""
    result = context.runner.run(["code", "--list-extensions"])
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
        return _wrong(
            f"{present} of {len(VSCODE_EXTENSIONS)} installed; missing: {', '.join(absent)}"
        )
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
    return Plan(commands=[["code", "--install-extension", name] for name in wanted])


#: Every stage, in the order they have to happen. Ordering is a real
#: dependency, not a preference: nothing can be cloned before SSH
#: authenticates, and the Node toolchains install *into* the clone.
STAGES: tuple[Stage, ...] = (
    Stage("vscode", "Visual Studio Code", _check_vscode, _plan_vscode),
    Stage("git", "Git, installed and configured", _check_git, _plan_git),
    Stage("ssh-key", "SSH keypair", _check_ssh_key, _plan_ssh_key),
    Stage("ssh-upload", "SSH key on the host", _check_ssh_authenticates, _plan_ssh_upload),
    Stage("clone", "Template cloned", _check_clone, _plan_clone),
    Stage("own-project", "Your own project on the host", _check_own_project, _plan_own_project),
    Stage("remote", "Clone pointed at your project", _check_remote, _plan_remote),
    Stage(
        "identity",
        "Commit identity in the project",
        _check_project_identity,
        _plan_project_identity,
    ),
    Stage("pandoc", "Pandoc and WeasyPrint's libraries", _check_pandoc, _plan_pandoc),
    Stage("node", "Node.js and the render toolchains", _check_node, _plan_node),
    Stage("extensions", "VS Code extensions", _check_extensions, _plan_extensions),
)
