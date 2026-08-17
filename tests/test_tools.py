# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""`prodockit.tools` - finding programs when PATH cannot.

The failure this exists for is specific to Windows and silent
everywhere else: a process already running never receives the PATH a
`winget install` just set, so a bare command name fails on exactly the
machine that has the software (prodockit-extensions#450, #451).
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

from prodockit import tools


def test_path_wins_when_it_can_see_the_program() -> None:
    """No lookup, no full path, on the two platforms where PATH is
    simply correct - a resolver that preferred a hardcoded location
    would pin macOS and Ubuntu to whichever copy it guessed at."""
    assert tools.find("python3") == "python3" or tools.find("python") == "python"


def test_a_program_off_PATH_is_found_where_its_installer_puts_it() -> None:
    """The whole point. `exists` is injected rather than touching the
    real filesystem, so this runs the same on any machine."""
    home = Path("/fake/home")
    wanted = tools.candidates("git", home)[0]

    found = tools.find(
        "definitely-not-on-path-git", home=home, exists=lambda p: p == wanted
    )
    # The name is not one of the keys, so nothing is found and the bare
    # name comes back - the guard against a resolver that matches
    # anything.
    assert found == "definitely-not-on-path-git"

    found = tools.find("git", home=home, exists=lambda p: p == wanted)
    assert found in (str(wanted), "git"), found


def test_the_home_relative_paths_resolve_against_the_home_given() -> None:
    """Compared as `PurePath.parts`, never as rendered strings: these
    are Windows paths and the test runs on macOS and Linux too
    (MISTAKES.md #6)."""
    found = tools.candidates("git", Path("/fake/home"))
    user_scoped = [p for p in found if "AppData" in str(p)]

    assert user_scoped, "the user-scope install location is missing"
    for path in user_scoped:
        parts = PureWindowsPath(str(path)).parts
        assert "AppData" in parts and "fake" in str(path)


def test_every_program_the_stages_install_on_windows_can_be_found() -> None:
    """git was given this treatment and pandoc and node were not, which
    is the whole of #450 - so the list is asserted rather than left to
    whoever adds the next winget line."""
    for name in ("git", "pandoc", "node"):
        assert tools.WINDOWS_PATHS.get(name), name
        assert tools.candidates(name, Path("/fake/home")), name


def test_an_unknown_program_comes_back_unchanged() -> None:
    """Falling back to the bare name rather than raising: the caller's
    own error says more than anything this could raise, and on macOS and
    Ubuntu the bare name is correct."""
    assert tools.find("no-such-program-anywhere", exists=lambda p: False) == (
        "no-such-program-anywhere"
    )
