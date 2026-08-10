# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The answers `prodockit bootstrap` remembers between runs.

Stored per *user*, not per project, because it is needed before a project
exists - the first thing bootstrap does with it is decide what to clone
and where (prodockit-extensions#217).

**Never secrets.** There is no field here for a password, token or
passphrase, and that is a design constraint rather than an omission: the
guide-and-verify approach means bootstrap never needs one, and a plain
file in a synced home directory is the wrong place to keep one if it ever
did. If a later phase wants API access, the token belongs in the OS
keychain and this file holds at most a reference to it.

The file format is deliberately a flat ``key = "value"`` subset of TOML,
parsed here rather than with ``tomllib``. Two reasons: ``tomllib`` is
3.11+ while this package supports 3.10, and adding ``tomli`` as a runtime
dependency for one small file this tool writes itself is a poor trade. A
line that doesn't parse is an error naming the file and line number, not
a silently ignored setting - a mistyped config that quietly reverts to
defaults is exactly the kind of silent failure this project keeps
finding.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

#: One `key = "value"` line. Quotes are required, so a value containing
#: `#` or spaces needs no special handling, and an unquoted line is a
#: clear error rather than an ambiguous parse.
_LINE_RE = re.compile(r'^\s*([a-z_][a-z0-9_]*)\s*=\s*"([^"]*)"\s*$')


class BootstrapConfigError(Exception):
    """Raised when the config file exists but cannot be read."""


@dataclass
class BootstrapConfig:
    """What bootstrap asks for, and remembers.

    Every field is a string with a safe default, so a fresh run has
    something to offer as the default answer to every prompt rather than
    an empty one.
    """

    full_name: str = ""
    email: str = ""
    username: str = ""
    host: str = "surrey"
    namespace: str = ""
    project_name: str = ""
    project_dir: str = ""
    #: A repository to clone *instead of* the template - for a reader who
    #: has already been given one (a taught module usually issues one per
    #: student). Blank means "use the template", which is the common case
    #: and the default. An explicit URL rather than a detected one: the
    #: reader knows whether they were given a repository, and asking the
    #: host would put a network call inside plan-building.
    source_url: str = ""

    @property
    def is_complete(self) -> bool:
        """Whether every field bootstrap actually needs has an answer.

        `host` always has one, so it isn't listed - a config with the
        rest blank is a first run, not a broken file.
        """
        return all(
            getattr(self, name)
            for name in ("full_name", "email", "username", "namespace", "project_name")
        )

    def resolved_project_dir(self, home: Path, cwd: Path | None = None) -> Path:
        """`project_dir` as an absolute path.

        A leading `~` expands to `home`. A relative path resolves against
        `cwd` - the directory the command was run from - rather than being
        left relative and landing wherever the process happened to start.
        """
        base = cwd if cwd is not None else Path.cwd()
        raw = self.project_dir or self.project_name or "project"
        if raw.startswith("~"):
            return home / raw[1:].lstrip("/\\")
        path = Path(raw)
        return path if path.is_absolute() else base / path


def config_path(home: Path | None = None) -> Path:
    """Where the config file lives for this user.

    `%APPDATA%` on Windows, XDG's `~/.config` elsewhere - each platform's
    own convention rather than a dotfile in the home directory on all
    three, since a Windows user finding a `.config` directory has learnt
    nothing about their own system.
    """
    base = Path(home) if home is not None else Path.home()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else base / "AppData" / "Roaming"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        root = Path(xdg) if xdg else base / ".config"
    return root / "prodockit" / "bootstrap.toml"


def load(path: Path) -> BootstrapConfig:
    """Reads `path`, or returns defaults if it doesn't exist.

    An unreadable or malformed file raises rather than falling back to
    defaults: silently discarding a config someone hand-edited would
    re-prompt for everything with no explanation of why.
    """
    if not path.exists():
        return BootstrapConfig()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise BootstrapConfigError(f"could not read {path}: {error}") from error

    known = {f.name for f in fields(BootstrapConfig)}
    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if match is None:
            raise BootstrapConfigError(
                f'{path}:{number}: expected `key = "value"`, got {stripped!r}'
            )
        key, value = match.group(1), match.group(2)
        if key not in known:
            # Not an error: a config written by a newer prodockit, read by
            # an older one, should still start rather than refuse outright.
            continue
        values[key] = value
    return BootstrapConfig(**values)


def save(path: Path, config: BootstrapConfig) -> None:
    """Writes `config` to `path`, creating parent directories."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Written by `prodockit bootstrap`. Safe to edit by hand.",
            "# Never put a password, token or passphrase in this file -",
            "# nothing here reads one, and this is not a safe place for it.",
            "",
        ]
        lines += [f'{key} = "{value}"' for key, value in asdict(config).items()]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as error:
        raise BootstrapConfigError(f"could not write {path}: {error}") from error


#: Prompt text for each field, in the order bootstrap asks. Ordered so
#: later answers can be defaulted from earlier ones (a project directory
#: from a project name), which is why this is a list rather than the
#: dataclass field order.
PROMPTS: tuple[tuple[str, str], ...] = (
    ("full_name", "Your full name, as it should appear on commits"),
    ("email", "Your university email address"),
    ("username", "Your GitLab username"),
    ("namespace", "The group or namespace your project lives in (e.g. comm058-2026)"),
    ("project_name", "Your project name (e.g. report-az1234)"),
    ("project_dir", "Where to put the project on this machine"),
    (
        "source_url",
        "Existing repository to clone instead of the template "
        "(leave blank to use the template)",
    ),
)


def missing_keys(config: BootstrapConfig) -> list[str]:
    """Which prompted fields have no answer yet, in prompt order.

    `source_url` is deliberately absent: blank is a valid, common answer
    meaning "use the template", so treating it as missing would ask
    everyone a question most people should skip.
    """
    optional = {"source_url"}
    return [
        key for key, _ in PROMPTS if key not in optional and not getattr(config, key, "")
    ]


def default_for(config: BootstrapConfig, key: str) -> str:
    """The value to offer as a prompt's default.

    A stored answer always wins. Otherwise a couple of fields can be
    guessed from ones already answered, so a first run still has
    something sensible to press Enter on.
    """
    if key == "project_dir":
        # Always offered as `./<name>`, even when a value is stored -
        # unlike every other field, where the stored answer wins.
        #
        # Two reasons. The User Guide's flow is "navigate to your GitLab
        # folder, then clone", so here is nearly always the right answer;
        # and a stored value that was wrong is the one thing a reader
        # cannot correct by pressing Enter, which is how the same clone
        # landed in a home directory twice. Showing `./` makes where it
        # will go legible at a glance, in a way an absolute path buried
        # in brackets is not.
        return f"./{config.project_name}" if config.project_name else "."
    current = getattr(config, key, "")
    return str(current) if current else ""
