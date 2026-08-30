# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest

native = importlib.import_module("tools.bootstrap_native_upgrade")


def _completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


def test_real_upgrade_routes_are_the_two_requested_paths() -> None:
    assert native.SCENARIOS == (
        ("surrey-existing-real-upgrade", "surrey", "existing"),
        ("github-new-real-upgrade", "github", "new"),
    )


def test_old_extension_packages_are_below_every_supported_floor() -> None:
    for identifier, version in native.OLD_EXTENSIONS.items():
        minimum = native.VSCODE_EXTENSION_MIN_VERSIONS[identifier]
        assert native._parts(version) < native._parts(minimum)


def test_marketplace_download_names_the_exact_old_package() -> None:
    assert native._marketplace_url("example.extension", "1.2.3") == (
        "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
        "example/vsextensions/extension/1.2.3/vspackage"
    )


def test_mac_path_lets_homebrew_replace_portable_old_tools(monkeypatch, tmp_path: Path) -> None:
    manager = tmp_path / "homebrew" / "bin"
    old = tmp_path / "old" / "bin"
    monkeypatch.setenv("PATH", os.pathsep.join(("/usr/bin", str(manager))))
    monkeypatch.setattr(native, "_run", lambda *_args, **_kwargs: _completed("/brew\n"))

    environment = native._scenario_environment(
        recipe=native.MACOS,
        portable_bins=[old],
        home=tmp_path / "home",
    )

    assert environment["PATH"].split(os.pathsep)[:2] == ["/brew/bin", str(old)]


def test_ubuntu_path_leaves_new_system_packages_ahead_of_old_tools(
    monkeypatch, tmp_path: Path
) -> None:
    old = tmp_path / "old" / "bin"
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")

    environment = native._scenario_environment(
        recipe=native.UBUNTU,
        portable_bins=[old],
        home=tmp_path / "home",
    )

    assert environment["PATH"].split(os.pathsep) == [
        "/usr/local/bin",
        "/usr/bin",
        str(old),
    ]


def test_native_upgrade_refuses_a_developer_machine(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    with pytest.raises(native.NativeInstallError, match="disposable GitHub Actions"):
        native.run_native_upgrades(
            tmp_path / "prodockit.whl", tmp_path / "report.json"
        )


def test_windows_seed_requests_actual_old_package_versions(monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(native, "_ensure_windows_winget", lambda: None)
    monkeypatch.setattr(native, "refresh_windows_path", lambda: None)

    def record(command, **_kwargs):  # type: ignore[no-untyped-def]
        commands.append(list(command))
        return _completed()

    monkeypatch.setattr(native, "_run", record)

    native._install_windows_old_software()

    rendered = "\n".join(" ".join(command) for command in commands)
    assert f"Microsoft.VisualStudioCode --version {native.OLD_VSCODE}" in rendered
    assert f"Git.Git --version {native.OLD_GIT}" in rendered
    assert f"JohnMacFarlane.Pandoc --version {native.OLD_PANDOC}" in rendered
    assert f"OpenJS.NodeJS.LTS --version {native.OLD_NODE}" in rendered
