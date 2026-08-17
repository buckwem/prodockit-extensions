# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Finding the programs prodockit runs, when PATH cannot.

A Windows machine where something was installed a moment ago has it on
the *machine's* PATH and not on this process's - a running process does
not get PATH updates. So a bare `git` fails on precisely the machine
that has just installed git, and the honest-looking conclusion, "git is
not installed", is wrong (prodockit-extensions#390).

The bootstrap stages solved this for `git` and `code` by looking where
the installer puts the executable. `prodockit sync-repo` did not, and
failed on the same machines:

    Error: could not run git: [WinError 2] The system cannot find the
    file specified

That failure then reached the reader as *"the project config still needs
syncing"* - a cause nobody had established (#451).

This module is the one list of places to look, so the stages and the
commands cannot drift into two answers about the same machine. The
stages wrap it in their own `Context` (which fakes the filesystem for
tests); everything else calls `find` directly.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

#: Where Windows installers put the executables prodockit runs. Only
#: Windows: macOS and Ubuntu put these on PATH and keep them there, and
#: a list of guesses that never fire is a list nobody maintains.
#:
#: Taken from what the bootstrap stages themselves install - the winget
#: package in the stage's own plan decides what belongs here.
WINDOWS_PATHS: dict[str, tuple[str, ...]] = {
    "git": (
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        r"~\AppData\Local\Programs\Git\cmd\git.exe",
    ),
    # winget `JohnMacFarlane.Pandoc`, machine scope and user scope.
    "pandoc": (
        r"C:\Program Files\Pandoc\pandoc.exe",
        r"~\AppData\Local\Pandoc\pandoc.exe",
    ),
    # winget `OpenJS.NodeJS.LTS`.
    "node": (
        r"C:\Program Files\nodejs\node.exe",
        r"~\AppData\Local\Programs\nodejs\node.exe",
    ),
}


def candidates(name: str, home: Path | None = None) -> tuple[Path, ...]:
    """Every place `name` might be, with `~` resolved against `home`.

    Returned rather than tested here so a caller with its own idea of
    what exists - the bootstrap `Context`, which fakes the filesystem for
    tests - can ask the question its own way.
    """
    root = home or Path.home()
    return tuple(
        Path(str(root) + raw[1:]) if raw.startswith("~") else Path(raw)
        for raw in WINDOWS_PATHS.get(name, ())
    )


def find(
    name: str,
    *,
    home: Path | None = None,
    exists: Callable[[Path], bool] | None = None,
) -> str:
    """`name` if PATH can see it, else its full path, else `name` again.

    Falling back to the bare name rather than raising is deliberate: the
    caller's own error - "could not run git" - says more than anything
    this could raise, and on macOS and Ubuntu the bare name is simply
    correct.
    """
    if shutil.which(name):
        return name
    there = exists if exists is not None else Path.exists
    for path in candidates(name, home):
        if there(path):
            return str(path)
    return name
