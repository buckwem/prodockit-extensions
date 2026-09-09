# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import pytest

from prodockit import adopt_package_manager as manager
from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS


@pytest.mark.parametrize("platform", [MACOS, UBUNTU, WINDOWS])
def test_existing_manager_needs_no_provisioning_even_offline(monkeypatch, platform):
    monkeypatch.setattr(manager.shutil, "which", lambda name: name)
    assert manager.plan(platform, offline=True) == manager.ManagerPlan()


def test_windows_provisions_stable_current_user_manager(monkeypatch):
    monkeypatch.setattr(
        manager.shutil, "which", lambda name: name if name == "powershell" else None
    )
    planned = manager.plan(WINDOWS)
    assert not planned.blocked
    script = planned.commands[0][-1]
    assert "Add-AppxPackage -RegisterByFamilyName" in script
    assert "Microsoft.WinGet.Client -Scope CurrentUser -Repository PSGallery" in script
    assert "Repair-WinGetPackageManager -Latest" in script
    assert "winget --version" in script
    assert "IncludePreRelease" not in script
    assert "-AllUsers" not in script
    assert "Set-ExecutionPolicy" not in script


def test_missing_manager_is_blocked_offline_without_commands(monkeypatch):
    monkeypatch.setattr(manager.shutil, "which", lambda name: None)
    planned = manager.plan(WINDOWS, offline=True)
    assert not planned.commands
    assert "online" in planned.blocked


def test_macos_does_not_silently_install_development_tools(monkeypatch):
    monkeypatch.setattr(manager.shutil, "which", lambda name: None)
    planned = manager.plan(MACOS)
    assert not planned.commands
    assert "outside Adopt's runtime-only scope" in planned.blocked


def test_missing_powershell_blocks_automatic_windows_install(monkeypatch):
    monkeypatch.setattr(manager.shutil, "which", lambda name: None)
    assert "PowerShell" in manager.plan(WINDOWS).blocked


def test_node_plan_provisions_manager_before_runtime(monkeypatch):
    from prodockit import adopt_node

    monkeypatch.setattr(adopt_node, "current_platform", lambda: WINDOWS)
    monkeypatch.setattr(
        adopt_node,
        "node_runtime_install_plan",
        lambda context: ([["winget", "install", "OpenJS.NodeJS.LTS"]], False, False, []),
    )
    monkeypatch.setattr(
        manager.shutil, "which", lambda name: name if name == "powershell" else None
    )
    planned = adopt_node.plan()
    assert not planned.blocked
    assert planned.commands[0][0] == "powershell"
    assert planned.commands[1][0] == "winget"


def test_native_pdf_plan_provisions_manager_before_runtime(monkeypatch):
    from types import SimpleNamespace

    from prodockit import adopt_pdf_runtime

    monkeypatch.setattr(adopt_pdf_runtime, "_context", lambda: SimpleNamespace(platform=WINDOWS))
    monkeypatch.setattr(adopt_pdf_runtime, "_probe", lambda context: "Pango unavailable")
    monkeypatch.setattr(
        adopt_pdf_runtime,
        "_plan_pandoc",
        lambda *args, **kwargs: SimpleNamespace(commands=[["winget", "install", "MSYS2.MSYS2"]]),
    )
    monkeypatch.setattr(
        manager.shutil, "which", lambda name: name if name == "powershell" else None
    )
    planned = adopt_pdf_runtime.plan()
    assert not planned.blocked
    assert planned.commands[0][0] == "powershell"
    assert planned.commands[1][0] == "winget"
