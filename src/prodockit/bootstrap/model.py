# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The pieces `prodockit bootstrap` is built from: a host, a runner, and a
stage.

Every one of them exists to keep the stages themselves *pure* - a stage
decides **what commands would achieve something** and never runs anything
itself. That is the whole testing strategy in one sentence: a test suite
cannot run ``brew install``, so the thing under test has to be the command
list rather than its effect (prodockit-extensions#217).

The same split gives ``--dry-run`` for free: printing a plan and executing
one differ only in which runner receives it.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from prodockit.bootstrap.config import BootstrapConfig

#: Platform identifiers. Deliberately not `sys.platform` values - these
#: name the *install recipe* rather than the kernel, and "ubuntu" is a
#: package-manager family (apt) rather than a distribution check.
MACOS = "macos"
UBUNTU = "ubuntu"
WINDOWS = "windows"
PLATFORMS = (MACOS, UBUNTU, WINDOWS)


@dataclass(frozen=True)
class Host:
    """A git host prodockit can set a project up against.

    Surrey's GitLab is the only one phase 1 populates, but every
    host-specific value the stages need is a *field here* rather than a
    branch in the stage code, so adding gitlab.com or github.com later is
    filling in a record rather than rewriting the stages
    (prodockit-extensions#217).

    `ssh_success` is the substring `ssh -T git@<hostname>` prints on a
    working key. It differs between GitLab ("Welcome to GitLab") and
    GitHub ("successfully authenticated"), and matching on it is how the
    guide-and-verify stages tell "the user clicked something" from
    "authentication actually works".

    `project_word`/`group_word` are display strings only. GitLab calls
    them projects in groups, GitHub calls them repositories in
    organisations, and a first-time reader following on-screen prompts
    should see their own host's vocabulary rather than ours.
    """

    key: str
    #: Where this host's copy of the template is cloned from. Surrey
    #: mirrors it onto its own GitLab, so a student never needs a GitHub
    #: account to start - cloning the GitHub original would ask them for
    #: credentials they have not got.
    template_remote: str
    #: The suffix the User Guide's own `ssh-keygen -f` line uses, so a
    #: check finds the key a reader was actually told to create. Not
    #: `key`: Surrey's instance and gitlab.com are different *hosts* but
    #: both are GitLab, and the guide names the file `id_ed25519_gitlab`
    #: for either. Getting this wrong reports a missing key and then
    #: creates a second one beside the working original.
    key_suffix: str
    hostname: str
    ssh_success: str
    ssh_keys_url: str
    new_project_url: str
    project_word: str = "project"
    group_word: str = "group"
    login_note: str = ""
    supported: bool = True

    @property
    def ssh_target(self) -> str:
        return f"git@{self.hostname}"

    def remote_url(self, namespace: str, project: str) -> str:
        return f"git@{self.hostname}:{namespace}/{project}.git"


SURREY_GITLAB = Host(
    key="surrey",
    template_remote="git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git",
    key_suffix="gitlab",
    hostname="gitlab.surrey.ac.uk",
    ssh_success="Welcome to GitLab",
    ssh_keys_url="https://gitlab.surrey.ac.uk/-/user_settings/ssh_keys",
    new_project_url="https://gitlab.surrey.ac.uk/projects/new",
    login_note="Choose the Surrey Login button and use your university credentials.",
)

#: Deliberately declared but unsupported. The shape is proven by having
#: more than one entry, and `supported=False` makes phase 1 refuse them
#: with a clear message rather than half-working against a host nothing
#: has tested (prodockit-extensions#217).
GITLAB_COM = Host(
    key="gitlab",
    template_remote="git@github.com:buckwem/prodockit-template.git",
    key_suffix="gitlab",
    hostname="gitlab.com",
    ssh_success="Welcome to GitLab",
    ssh_keys_url="https://gitlab.com/-/user_settings/ssh_keys",
    new_project_url="https://gitlab.com/projects/new",
    supported=False,
)

GITHUB_COM = Host(
    key="github",
    template_remote="git@github.com:buckwem/prodockit-template.git",
    key_suffix="github",
    hostname="github.com",
    ssh_success="successfully authenticated",
    ssh_keys_url="https://github.com/settings/keys",
    new_project_url="https://github.com/new",
    project_word="repository",
    group_word="organisation",
    supported=False,
)

HOSTS = {host.key: host for host in (SURREY_GITLAB, GITLAB_COM, GITHUB_COM)}


@dataclass(frozen=True)
class CommandResult:
    """What running one command produced."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class Runner(Protocol):
    """Runs one command and reports what happened.

    Injected rather than called directly so a test can supply canned
    output for every platform's commands from whichever single platform
    the test suite happens to be running on.
    """

    def run(self, command: Sequence[str]) -> CommandResult: ...


class SubprocessRunner:
    """The real runner.

    `encoding="utf-8"` is not optional: without it `text=True` decodes
    using the locale encoding, which is cp1252 on a UK Windows install,
    and any non-ASCII byte in a tool's output crashes the run with a
    `UnicodeDecodeError` that names nothing useful
    (prodockit-extensions#189). `tests/test_subprocess_encoding.py`
    enforces this across the package.

    `stdin=DEVNULL` is not optional either, and for a subtler reason.
    `subprocess` inherits the parent's stdin by default, so a command run
    during a check reads the *user's* keyboard input - `ssh -T` during
    stage 4 silently consumed the answers typed for bootstrap's own
    prompts, and every later prompt then aborted on end-of-input. Any
    command that decides to ask something (ssh confirming a host key, git
    asking for credentials) would do the same, and would hang instead if
    nothing was waiting on stdin.

    A stage whose command genuinely needs a terminal - `ssh-keygen`
    asking for a passphrase - cannot use this runner and will need one
    that hands over the terminal deliberately. That is a later phase's
    problem, but the default has to be the safe one.
    """

    def run(self, command: Sequence[str]) -> CommandResult:
        try:
            completed = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                stdin=subprocess.DEVNULL,
                timeout=300,
            )
        except FileNotFoundError:
            # The command isn't installed. That is a finding, not a crash -
            # "is this installed?" is exactly what most checks are asking.
            return CommandResult(returncode=127, stderr=f"{command[0]}: not found")
        except (OSError, subprocess.SubprocessError) as error:
            return CommandResult(returncode=1, stderr=str(error))
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )


class Status(Enum):
    """Whether a stage is set up.

    `WRONG` is separate from `MISSING` deliberately. Git installed but with
    no `user.email` set, or MSYS2 present without `pango`, is not the same
    as absent - it is the state a rerun exists to repair, and reporting it
    as "missing" would tell a reader to install something they already
    have.
    """

    OK = "ok"
    MISSING = "missing"
    WRONG = "wrong"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CheckResult:
    status: Status
    detail: str = ""

    @property
    def needs_work(self) -> bool:
        return self.status is not Status.OK


@dataclass(frozen=True)
class Plan:
    """How a stage would be applied.

    `commands` is what would be run; `instructions` is what a human has to
    do themselves. A stage can carry both - uploading an SSH key is a
    browser step (instruction) whose success is then confirmed by
    `ssh -T` (command).
    """

    commands: list[list[str]] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)

    @property
    def is_manual(self) -> bool:
        return bool(self.instructions) and not self.commands


@dataclass(frozen=True)
class Context:
    """Everything a stage's `check`/`plan` is allowed to depend on.

    Passed in rather than read from the environment so a test can describe
    a machine - a different platform, a different host, a project that
    does or doesn't exist - without touching the real one.
    """

    config: BootstrapConfig
    host: Host
    platform: str
    runner: Runner
    home: Path


@dataclass(frozen=True)
class Stage:
    """One step of the install.

    `check` answers "is this already done?"; `plan` answers "what would
    make it done?". Neither performs anything, which is what lets
    `--check` and `--dry-run` be the same code path as a real run with a
    different runner attached.
    """

    id: str
    summary: str
    check: Callable[[Context], CheckResult]
    plan: Callable[[Context], Plan]
