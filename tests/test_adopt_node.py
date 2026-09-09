# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import subprocess
from types import SimpleNamespace

import pytest

from prodockit import adopt
from prodockit import adopt_node as node
from prodockit.bootstrap import stages
from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS


@pytest.mark.parametrize(
    "platform,manager", [(MACOS, "brew"), (UBUNTU, "apt"), (WINDOWS, "winget")]
)
@pytest.mark.parametrize(
    "state", [(None, None, False), ("18.0.0", "8.0.0", True), ("24.0.0", None, False)]
)
def test_platform_plan_installs_upgrades_or_repairs_only_node(
    monkeypatch, platform, manager, state
):
    monkeypatch.setattr(node, "current_platform", lambda: platform)
    monkeypatch.setattr(node.adopt_package_manager.shutil, "which", lambda command: command)
    monkeypatch.setattr(stages, "_node_runtime_state", lambda context: state)
    monkeypatch.setattr(stages, "_windows_node_needs_architecture_handover", lambda context: False)
    planned = node.plan()
    assert planned.commands
    assert manager in str(planned.commands)
    assert not planned.blocked
    for forbidden in ("git clone", "ssh", "code --", "npm ci", "chromium"):
        assert forbidden not in str(planned.commands)


def test_supported_runtime_does_not_need_a_package_manager_or_network(monkeypatch):
    monkeypatch.setattr(node, "current_platform", lambda: MACOS)
    monkeypatch.setattr(node.adopt_package_manager.shutil, "which", lambda command: None)
    monkeypatch.setattr(stages, "_node_runtime_state", lambda context: ("24.0.0", "11.0.0", True))
    assert not node.plan(offline=True).needs_work


def test_offline_missing_runtime_is_blocked_before_install(monkeypatch):
    monkeypatch.setattr(node, "current_platform", lambda: UBUNTU)
    monkeypatch.setattr(stages, "_node_runtime_state", lambda context: (None, None, False))
    assert "offline" in node.plan(offline=True).blocked


def test_apply_rechecks_and_uses_unique_download_path(tmp_path, monkeypatch):
    commands = []
    states = iter(
        [
            node.NodePlan(
                (
                    (
                        "curl",
                        "-o",
                        "/tmp/nodesource-setup.sh",
                        "https://deb.nodesource.com/setup_22.x",
                    ),
                    ("sudo", "-E", "bash", "/tmp/nodesource-setup.sh"),
                )
            ),
            node.NodePlan(),
        ]
    )
    monkeypatch.setattr(node, "plan", lambda **kwargs: next(states))
    monkeypatch.setattr(node, "_refresh", lambda: None)
    monkeypatch.setattr(node.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(node, "run_install_command", lambda args, **kwargs: commands.append(args))
    node.apply(tmp_path)
    assert commands[1][0] == "bash"
    assert commands[0][2] == commands[1][1]
    assert commands[0][2] != "/tmp/nodesource-setup.sh"


def test_noninteractive_administrator_approval_failure_does_not_install(tmp_path, monkeypatch):
    monkeypatch.setattr(
        node, "plan", lambda **kwargs: node.NodePlan((("sudo", "apt", "install", "nodejs"),))
    )
    monkeypatch.setattr(node, "_refresh", lambda: None)
    monkeypatch.setattr(node.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(
        node.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1)
    )
    monkeypatch.setattr(node.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(
        node, "run_install_command", lambda *args, **kwargs: pytest.fail("installer started")
    )
    with pytest.raises(node.ToolchainError, match="interactive terminal"):
        node.apply(tmp_path)


def test_timeout_does_not_launch_another_installer(tmp_path, monkeypatch):
    monkeypatch.setattr(
        node, "plan", lambda **kwargs: node.NodePlan((("brew", "install", "node"),))
    )
    monkeypatch.setattr(node, "_refresh", lambda: None)
    calls = []

    def timeout(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, 1800)

    monkeypatch.setattr(node, "run_install_command", timeout)
    with pytest.raises(node.ToolchainError, match="child processes have stopped"):
        node.apply(tmp_path)
    assert len(calls) == 1


def test_installer_success_without_runtime_health_requires_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(
        node, "plan", lambda **kwargs: node.NodePlan((("brew", "install", "node"),))
    )
    monkeypatch.setattr(node, "_refresh", lambda: None)
    monkeypatch.setattr(node, "run_install_command", lambda *args, **kwargs: None)
    with pytest.raises(node.ToolchainError, match="RESTART YOUR TERMINAL"):
        node.apply(tmp_path)


def test_declined_node_activity_cannot_start_renderer_or_edit_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        node, "plan", lambda **kwargs: node.NodePlan((("brew", "install", "node"),))
    )
    with pytest.raises(adopt.AdoptError, match=r"Complete the Node\.js"):
        adopt.apply_step(tmp_path, adopt.AdoptOptions(mermaid=True), "mermaid")
    assert list(tmp_path.iterdir()) == []


def test_unselected_renderers_do_not_probe_or_install_node(tmp_path, monkeypatch):
    (tmp_path / "zensical.toml").write_text('[project]\nsite_name="Test"\n')
    monkeypatch.setattr(node, "plan", lambda **kwargs: pytest.fail("Node was probed"))
    monkeypatch.setattr(
        adopt.supported_toolchain,
        "plan",
        lambda *args, **kwargs: SimpleNamespace(
            blocked="", needs_work=False, detail="aligned", commands=(), files=()
        ),
    )
    steps = adopt.assess(tmp_path, adopt.AdoptOptions(mermaid=False, maths=False))
    assert not next(step for step in steps if step.id == "node").selected
