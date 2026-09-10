# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from types import SimpleNamespace

import click
import pytest

from prodockit import adopt_repo_tools, adopt_repository
from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS


@pytest.mark.parametrize("platform", [MACOS, UBUNTU, WINDOWS])
@pytest.mark.parametrize("client", ["gh", "glab"])
def test_install_plan_is_host_specific(platform, client):
    commands = adopt_repo_tools.install_commands(platform, ["git", client])
    text = str(commands)
    assert (
        ("GitHub.cli" if client == "gh" else "GLab.GLab") in text
        if platform == WINDOWS
        else client in text
    )
    assert not any("push" in command for command in commands)


def test_offline_never_installs(tmp_path, monkeypatch):
    monkeypatch.setattr(adopt_repo_tools.shutil, "which", lambda name: None)
    monkeypatch.setattr(adopt_repo_tools, "run_commands", lambda *a, **kw: pytest.fail("install"))
    assert not adopt_repo_tools.ensure(tmp_path, "gh", offline=True)


def test_declined_install_never_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(adopt_repo_tools.shutil, "which", lambda name: None)
    monkeypatch.setattr(click, "confirm", lambda *a, **kw: False)
    monkeypatch.setattr(adopt_repo_tools, "run_commands", lambda *a, **kw: pytest.fail("install"))
    assert not adopt_repo_tools.ensure(tmp_path, "glab", offline=False)


def test_installs_only_missing_tool_and_rechecks(tmp_path, monkeypatch):
    available = {"git"}
    monkeypatch.setattr(
        adopt_repo_tools.shutil, "which", lambda name: name if name in available else None
    )
    monkeypatch.setattr(click, "confirm", lambda *a, **kw: True)
    monkeypatch.setattr(adopt_repo_tools, "current_platform", lambda: MACOS)
    monkeypatch.setattr(
        adopt_repo_tools.adopt_package_manager,
        "plan",
        lambda platform: SimpleNamespace(blocked="", commands=()),
    )

    def install(root, commands, **kwargs):
        assert commands == [["brew", "install", "gh"]]
        available.add("gh")

    monkeypatch.setattr(adopt_repo_tools, "run_commands", install)
    assert adopt_repo_tools.ensure(tmp_path, "gh", offline=False)


def test_commit_identity_is_local_and_preserves_existing(tmp_path, monkeypatch):
    calls = []

    def run(command, root):
        calls.append(command)
        return SimpleNamespace(
            returncode=0, stdout="Existing Name" if command[-1] == "user.name" else ""
        )

    monkeypatch.setattr(adopt_repository, "_run", run)
    monkeypatch.setattr(click, "confirm", lambda *a, **kw: True)
    monkeypatch.setattr(click, "prompt", lambda *a, **kw: "author@example.net")
    adopt_repository._commit_identity(tmp_path)
    writes = [command for command in calls if "--local" in command]
    assert writes == [["git", "config", "--local", "user.email", "author@example.net"]]


def test_declined_auth_does_not_launch_login(tmp_path, monkeypatch):
    monkeypatch.setattr(adopt_repository, "_run", lambda *a: SimpleNamespace(returncode=1))
    monkeypatch.setattr(click, "confirm", lambda *a, **kw: False)
    monkeypatch.setattr(adopt_repository.subprocess, "run", lambda *a, **kw: pytest.fail("login"))
    assert not adopt_repository._authenticate(tmp_path, "gh", "github.com")
