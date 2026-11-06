# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Guard imports of standard modules newer than the declared Python floor.

Read the source rather than relying on the running interpreter: a newer
developer Python could otherwise hide a missing import on the oldest CI leg.
"""

from __future__ import annotations

import ast
import pathlib

from prodockit.template_sync import read_config

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Standard modules whose introduction version matters to the supported floor.
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
                if name in TOO_NEW and TOO_NEW[name] > _requires_python_floor():
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} ({name})")
    return offenders


def test_the_version_floor_is_the_one_these_gates_are_written_for() -> None:
    """The support floor is explicit so a future change revisits the gate."""
    assert _requires_python_floor() == (3, 11)


def test_no_module_newer_than_requires_python_is_imported_ungated() -> None:
    offenders = _ungated_imports()

    assert not offenders, (
        "These import a stdlib module newer than the oldest supported "
        "interpreter, so they raise ModuleNotFoundError on that leg of CI "
        "and nowhere else. Import it behind `if sys.version_info >= (...)` "
        f"with the backport in the else branch, or call the existing shim: {offenders}"
    )
