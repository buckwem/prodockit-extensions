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

import os
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
    #: How to reach the SSH keys page through this host's own menus,
    #: taken from the User Guide's wording. A pasted URL is the faster
    #: route for someone who already knows where they are going, and the
    #: worse one for someone who does not: it gives no way to check you
    #: have landed in the right place, and no way back if you have not.
    #: Both are offered, menus first (prodockit-extensions#238).
    ssh_keys_steps: tuple[str, ...] = ()
    #: What this host's key form asks for beyond a title and the key
    #: itself. GitLab requires an expiry date and fills it in a year
    #: ahead; GitHub has no such field, so the difference is a value
    #: rather than a branch in the stage.
    ssh_key_form_extra: tuple[str, ...] = ()
    #: The button that opens the key form - "Add new key" on GitLab,
    #: "New SSH key" on GitHub.
    ssh_key_new_label: str = "Add new key"
    #: The button that saves the key - "Add key" on GitLab, "Add SSH key"
    #: on GitHub.
    ssh_key_save_label: str = "Add key"
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
    ssh_keys_steps=(
        "In the top-right corner, click your profile avatar and select 'Edit profile'.",
        "On the left-hand sidebar, select 'Access > SSH Keys'.",
    ),
    ssh_key_form_extra=(
        "Expiration date: GitLab fills this in a year ahead and will not let you "
        "clear it. Set it well past the end of your course or project - an expired "
        "key stops `git push` with a permission error that reads like a "
        "misconfigured key rather than an expired one, months after you set it up.",
    ),
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
    ssh_keys_steps=(
        "In the top-right corner, click your profile avatar and select 'Edit profile'.",
        "On the left-hand sidebar, select 'Access > SSH Keys'.",
    ),
    ssh_key_form_extra=(
        "Expiration date: GitLab fills this in a year ahead and will not let you "
        "clear it. Set it well past the end of your course or project - an expired "
        "key stops `git push` with a permission error that reads like a "
        "misconfigured key rather than an expired one, months after you set it up.",
    ),
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
    ssh_keys_steps=(
        "In the top-right corner, click your profile avatar and select 'Settings'.",
        "On the left-hand sidebar, select 'SSH and GPG keys'.",
    ),
    # No expiry field at all here - a GitHub key stays valid until it is
    # deleted, so there is nothing to warn about.
    ssh_key_new_label="New SSH key",
    ssh_key_save_label="Add SSH key",
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

    def run(self, command: Sequence[str], cwd: str | None = None) -> CommandResult: ...


#: The ssh invocation prefix that cannot stop for a human, shared by
#: `_no_prompt_env` and by the `ssh -T` probe in `stages.py` so the two
#: cannot drift apart.
SSH_NO_PROMPT_OPTIONS: tuple[str, ...] = (
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
)


def _no_prompt_env() -> dict[str, str]:
    """The environment every bootstrap command runs in: one that cannot ask.

    Bootstrap runs commands both to *check* and to *apply*, and neither
    can afford a child process that stops for input. A check must be
    read-only and fast; an apply reports its own progress and would be
    talked over. But the two tools bootstrap leans on hardest each have
    their own way of asking anyway:

    - **ssh** reads passwords and passphrases straight from `/dev/tty`,
      not stdin, so `stdin=DEVNULL` does nothing to stop it.
      `BatchMode=yes` makes it fail instead of ask. `ConnectTimeout`
      bounds the other kind of hang - an unreachable host, which for a
      university VPN is an ordinary Tuesday.
    - **git** prompts for credentials over HTTPS, and runs ssh for
      everything else - so `git ls-remote` and `git clone` inherit
      exactly the same problem the `ssh -T` check had.

    `GIT_SSH_COMMAND` is left alone if it is already set: someone who has
    configured their own ssh wrapper has a reason, and silently replacing
    it would break a working setup to fix a hypothetical one.

    Failing fast is the point. "Could not authenticate" is a finding
    bootstrap can report and act on; a blinking cursor is not.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", " ".join(SSH_NO_PROMPT_OPTIONS))
    return env


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

    `stdin=DEVNULL` is necessary but *not sufficient*, which cost a
    testing session to learn. ssh reads passwords and passphrases from
    `/dev/tty` directly, deliberately bypassing whatever stdin happens to
    be, so a check on a machine whose key was not yet uploaded fell back
    to password authentication and sat at a prompt forever
    (prodockit-extensions#225). Redirecting stdin cannot prevent that;
    only telling the tools not to ask can, which is what `_no_prompt_env`
    does.

    A stage whose command genuinely needs a terminal - `ssh-keygen`
    asking for a passphrase - cannot use this runner and will need one
    that hands over the terminal deliberately. That is a later phase's
    problem, but the default has to be the safe one.
    """

    def run(self, command: Sequence[str], cwd: str | None = None) -> CommandResult:
        try:
            completed = subprocess.run(
                list(command),
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                stdin=subprocess.DEVNULL,
                env=_no_prompt_env(),
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

    `commands` is what would be run; the other two are what a human has to
    do themselves, and *when* they do it relative to the commands:

    - `instructions` come **before** the commands, because the commands
      depend on them. "Download the .deb" has to happen before
      `apt install ./code.deb` can find it.
    - `follow_up` comes **after**, because it only makes sense once the
      commands have run. VS Code's "open the Command Palette" step needs
      the application that `brew install --cask` puts there.

    Getting this backwards is not cosmetic - it is a run that cannot
    succeed. Both orderings have shipped broken (#234, #230),
    which is why they are now two fields
    rather than one field and a convention.
    """

    commands: list[list[str]] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    follow_up: list[str] = field(default_factory=list)
    #: Where the commands run. Needed because not every tool takes a
    #: path: `git` has `-C` and `npm` has `--prefix`, but `prodockit
    #: sync-repo` reads its config from the working directory, so running
    #: it from wherever bootstrap happened to be started found no `origin`
    #: remote and failed with a message about a repository it was never
    #: looking at.
    cwd: str | None = None

    @property
    def is_manual(self) -> bool:
        return bool(self.instructions or self.follow_up) and not self.commands


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
    #: How a stage asks whether a path exists.
    #:
    #: Every other question a stage asks goes through `runner`, and every
    #: other path it looks at hangs off `home`, so a test can describe a
    #: machine it is not running on. Absolute system paths - `/Applications`,
    #: `C:\Program Files` - had neither, and read the real filesystem
    #: instead: two tests silently started depending on whether the machine
    #: running them happened to have VS Code installed. This closes that,
    #: so "tests describe a machine, never read one" is true of all of it.
    exists: Callable[[Path], bool] = Path.exists


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
