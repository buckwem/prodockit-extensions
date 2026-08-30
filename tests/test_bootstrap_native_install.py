# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "bootstrap_native_install",
    Path(__file__).parents[1] / "tools" / "bootstrap_native_install.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_cleanup_refuses_to_modify_a_developer_machine(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    with pytest.raises(_MODULE.NativeInstallError, match="disposable GitHub Actions"):
        _MODULE.cleanup_ephemeral_runner(_MODULE.UBUNTU, tmp_path)


@pytest.mark.parametrize(
    ("recipe", "expected"),
    (
        (_MODULE.MACOS, ("visual-studio-code", "git", "pandoc", "pango", "node")),
        (
            _MODULE.UBUNTU,
            ("code", "git", "pandoc", "libpango-1.0-0", "nodejs", "chromium-browser"),
        ),
        (
            _MODULE.WINDOWS,
            (
                "Microsoft.VisualStudioCode",
                "Git.Git",
                "JohnMacFarlane.Pandoc",
                "MSYS2.MSYS2",
                "OpenJS.NodeJS.LTS",
            ),
        ),
    ),
)
def test_cleanup_covers_every_bootstrap_runtime(
    monkeypatch, tmp_path: Path, recipe: str, expected: tuple[str, ...]
) -> None:
    commands: list[list[str]] = []

    def record(command, *, check=True):  # type: ignore[no-untyped-def]
        del check
        commands.append(list(command))
        return _completed(returncode=1)

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(_MODULE, "_run", record)
    _MODULE.cleanup_ephemeral_runner(recipe, tmp_path)
    rendered = "\n".join(" ".join(command) for command in commands)

    for value in expected:
        assert value in rendered


def test_absent_planning_runner_preserves_cpu_architecture() -> None:
    runner = _MODULE.AbsentPlanningRunner(_MODULE.WINDOWS)

    result = runner.run([sys.executable, "-c", "int.from_bytes"])

    assert result.ok
    assert result.stdout.strip() in {"0x8664", "0xaa64"}


def test_wheel_resolution_requires_exactly_one_candidate(tmp_path: Path) -> None:
    with pytest.raises(_MODULE.NativeInstallError, match="expected one"):
        _MODULE._resolve_wheel(tmp_path)

    wheel = tmp_path / "prodockit-1-py3-none-any.whl"
    wheel.touch()
    assert _MODULE._resolve_wheel(tmp_path) == wheel.resolve()
