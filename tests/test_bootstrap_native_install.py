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


def test_missing_winget_installs_microsofts_signed_release(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "winget.exe"
    executable.touch()
    commands: list[list[str]] = []

    def record(command, *, check=True):  # type: ignore[no-untyped-def]
        del check
        commands.append(list(command))
        stdout = str(executable) if "Get-Command winget.exe" in command[-1] else ""
        return _completed(stdout=stdout)

    monkeypatch.setattr(
        _MODULE.shutil,
        "which",
        lambda name: "/usr/bin/powershell" if name == "powershell" else None,
    )
    monkeypatch.setattr(_MODULE, "_run", record)
    _MODULE._ensure_windows_winget()
    rendered = "\n".join(" ".join(command) for command in commands)

    assert "api.github.com/repos/microsoft/winget-cli/releases/latest" in rendered
    assert 'Authorization = "Bearer $env:GITHUB_TOKEN"' in rendered
    assert "-Headers $headers" in rendered
    assert "Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle" in rendered
    assert "DesktopAppInstaller_Dependencies.zip" in rendered
    assert "PROCESSOR_ARCHITECTURE" in rendered
    assert "Add-AppxPackage -Path $bundle -DependencyPath $dependencyPath" in rendered
    assert "-ForceApplicationShutdown" in rendered
    assert "-ForceTargetApplicationShutdown" not in rendered
    assert commands[0][0] == "/usr/bin/powershell"
    assert str(executable.parent) in _MODULE.os.environ["PATH"]


@pytest.mark.parametrize(
    ("recipe", "expected"),
    (
        (_MODULE.MACOS, ("visual-studio-code", "git", "pandoc", "pango", "node")),
        (
            _MODULE.UBUNTU,
            (
                "code",
                "git",
                "git-man",
                "pandoc",
                "nodejs",
                "chromium-browser",
            ),
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
    monkeypatch.setattr(_MODULE.shutil, "which", lambda _name: "winget")
    _MODULE.cleanup_ephemeral_runner(recipe, tmp_path)
    rendered = "\n".join(" ".join(command) for command in commands)

    for value in expected:
        assert value in rendered


def test_ubuntu_cleanup_preserves_operating_system_shared_libraries(
    monkeypatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def record(command, *, check=True):  # type: ignore[no-untyped-def]
        del check
        commands.append(list(command))
        return _completed(returncode=1)

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(_MODULE, "_run", record)

    _MODULE.cleanup_ephemeral_runner(_MODULE.UBUNTU, tmp_path)

    rendered = "\n".join(" ".join(command) for command in commands)
    assert "libpango-1.0-0" not in rendered
    assert "libpangoft2-1.0-0" not in rendered
    assert "libharfbuzz-subset0" not in rendered


def test_absent_planning_runner_preserves_cpu_architecture() -> None:
    runner = _MODULE.AbsentPlanningRunner(_MODULE.WINDOWS)

    result = runner.run([sys.executable, "-c", "int.from_bytes"])

    assert result.ok
    assert result.stdout.strip() in {"0x8664", "0xaa64"}


def test_windows_msys_roots_are_drive_absolute(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEMDRIVE", "C:")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Ada\AppData\Local")
    monkeypatch.setenv("PROGRAMFILES", r"C:\Program Files")

    assert tuple(map(str, _MODULE._windows_msys_roots())) == (
        r"C:\msys64",
        r"C:\Users\Ada\AppData\Local\Programs\msys64",
        r"C:\Program Files\msys64",
    )


def test_windows_inter_route_cleanup_keeps_msys2_but_removes_pango(
    monkeypatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def record(command, *, check=True):  # type: ignore[no-untyped-def]
        del check
        commands.append(list(command))
        return _completed(returncode=1)

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(_MODULE, "_run", record)
    monkeypatch.setattr(_MODULE.shutil, "which", lambda _name: "winget")
    root = tmp_path / "msys64"
    bash = root / "usr" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    monkeypatch.setattr(_MODULE, "_windows_msys_roots", lambda: (root,))

    _MODULE.cleanup_ephemeral_runner(
        _MODULE.WINDOWS,
        tmp_path,
        preserve_msys2=True,
    )

    rendered = "\n".join(" ".join(command) for command in commands)
    assert "mingw-w64-ucrt-x86_64-pango" in rendered
    assert "mingw-w64-clang-aarch64-pango" in rendered
    assert "winget uninstall --id MSYS2.MSYS2" not in rendered


def test_wheel_resolution_requires_exactly_one_candidate(tmp_path: Path) -> None:
    with pytest.raises(_MODULE.NativeInstallError, match="expected one"):
        _MODULE._resolve_wheel(tmp_path)

    wheel = tmp_path / "prodockit-1-py3-none-any.whl"
    wheel.touch()
    assert _MODULE._resolve_wheel(tmp_path) == wheel.resolve()
