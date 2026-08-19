# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Modules newer than `requires-python` are imported behind a gate, or not at all.

`tomllib` arrived in 3.11 and this package supports 3.10, so a bare
`import tomllib` is a `ModuleNotFoundError` on the oldest interpreter the
project claims to run on - and on no other. Nothing local catches it: the
developer's interpreter is newer, the four other CI legs are newer, and the
single 3.10 leg is the only place it shows up. It has cost a red CI run
once already, from two test modules that reached for `tomllib` directly
instead of going through the shim `prodockit.template_sync` already had.

Checked by reading the source rather than by importing on 3.10, because on
every interpreter this suite normally runs on the bad import succeeds. The
property is asserted directly, on every platform, and covers imports added
in future rather than only the two that were wrong.

The gate itself is fine - `if sys.version_info >= (3, 11): import tomllib`
- and so is importing the backport. What this refuses is the ungated form.

This module reads `pyproject.toml` through `prodockit.template_sync`'s
shim for exactly that reason: the first draft imported `tomllib` at the
top and would have failed on the one interpreter it exists to protect.
"""

from __future__ import annotations

import ast
import pathlib

from prodockit.template_sync import read_config

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Stdlib modules newer than the floor in `requires-python`, and the
#: version each arrived in. `tomllib` is the only one in use so far.
TOO_NEW = {"tomllib": (3, 11)}


def _requires_python_floor() -> tuple[int, int]:
    """The oldest interpreter `pyproject.toml` claims to support."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = read_config(text)["project"]["requires-python"]
    digits = declared.lstrip(">=~^ ")
    major, minor = digits.split(".")[:2]
    return int(major), int(minor)


def _ungated_imports() -> list[str]:
    """Every `import <too-new>` not guarded by a `sys.version_info` test."""
    offenders = []
    for path in sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "tests").rglob("*.py")):
        if path.name == pathlib.Path(__file__).name:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        gated = {
            node
            for check in ast.walk(tree)
            if isinstance(check, ast.If) and "version_info" in ast.dump(check.test)
            for node in ast.walk(check)
        }
        for node in ast.walk(tree):
            if node in gated:
                continue
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in TOO_NEW:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} ({name})")
    return offenders


def test_the_version_floor_is_the_one_these_gates_are_written_for() -> None:
    """If the floor rises to 3.11, `tomllib` stops needing a gate at all.

    Asserted so this module is corrected rather than quietly enforcing a
    rule that no longer applies.
    """
    assert _requires_python_floor() == (3, 10), (
        "requires-python has moved - revisit TOO_NEW, and drop any entry the "
        "new floor already provides"
    )


def test_no_module_newer_than_requires_python_is_imported_ungated() -> None:
    offenders = _ungated_imports()

    assert not offenders, (
        "These import a stdlib module newer than the oldest supported "
        "interpreter, so they raise ModuleNotFoundError on that leg of CI "
        "and nowhere else. Import it behind `if sys.version_info >= (...)` "
        f"with the backport in the else branch, or call the existing shim: {offenders}"
    )
