# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Node/npm provisioning shared with Bootstrap, without its repository activities."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from prodockit.bootstrap import UnsupportedHostError, current_platform
from prodockit.bootstrap.config import BootstrapConfig
from prodockit.bootstrap.model import (
    GITHUB_COM,
    MACOS,
    UBUNTU,
    WINDOWS,
    Context,
    SubprocessRunner,
    refresh_windows_path,
)
from prodockit.bootstrap.stages import node_runtime_install_plan
from prodockit.renderer_resilience import RetryReporter
from prodockit.toolchain import ToolchainError, run_install_command


@dataclass(frozen=True)
class NodePlan:
    commands: tuple[tuple[str, ...], ...] = ()
    blocked: str = ""

    @property
    def needs_work(self) -> bool:
        return bool(self.commands or self.blocked)


def plan(*, offline: bool = False) -> NodePlan:
    try:
        platform = current_platform()
    except UnsupportedHostError as error:
        return NodePlan(blocked=str(error))
    if platform not in {MACOS, UBUNTU, WINDOWS}:
        return NodePlan(blocked="Automatic Node installation supports macOS, Ubuntu and Windows 11")
    context = Context(
        config=BootstrapConfig(),
        host=GITHUB_COM,
        platform=platform,
        runner=SubprocessRunner(),
        home=Path.home(),
        guided=True,
    )
    # The shared routine only probes Node/npm and plans package-manager commands.
    # It does not read Bootstrap's saved answers or invoke Git, SSH or an editor.
    commands, _upgrade, _repair, _parts = node_runtime_install_plan(context)
    if not commands:
        return NodePlan()
    if offline:
        return NodePlan(blocked="Node.js/npm needs installation or repair, but Adopt is offline")
    if platform == MACOS and not shutil.which("brew"):
        return NodePlan(
            blocked="Homebrew is required for automatic Node.js installation; "
            "complete environment preparation first"
        )
    if platform == WINDOWS and not shutil.which("winget"):
        return NodePlan(
            blocked="Windows App Installer (winget) is required for automatic Node.js installation"
        )
    if platform == UBUNTU and not shutil.which("apt"):
        return NodePlan(blocked="Automatic Linux runtime installation requires Ubuntu with apt")
    return NodePlan(tuple(tuple(command) for command in commands))


def _refresh() -> None:
    if sys.platform == "win32":
        refresh_windows_path()
    elif sys.platform == "darwin":
        for directory in ("/usr/local/bin", "/opt/homebrew/bin"):
            if (Path(directory) / "node").is_file() and directory not in os.get_exec_path():
                os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")


def apply(root: Path, *, offline: bool = False, reporter: RetryReporter | None = None) -> None:
    _refresh()
    pending = plan(offline=offline)
    if pending.blocked:
        raise ToolchainError(pending.blocked)
    if not pending.commands:
        return
    root_user = hasattr(os, "geteuid") and os.geteuid() == 0
    if not root_user and any(command[0] == "sudo" for command in pending.commands):
        # Authenticate visibly once; captured installers must never wait for a password.
        authenticated = (
            subprocess.run(["sudo", "-n", "-v"], check=False, timeout=30).returncode == 0
        )
        if not authenticated:
            if not sys.stdin.isatty():
                raise ToolchainError(
                    "Administrator approval is required. "
                    "Run pdk adopt --apply in an interactive terminal."
                )
            if subprocess.run(["sudo", "-v"], check=False, timeout=300).returncode:
                raise ToolchainError(
                    "Administrator approval was declined; Node.js was not installed"
                )
    # Never reuse Bootstrap's fixed download pathname for a privileged script.
    with tempfile.TemporaryDirectory(prefix="prodockit-node-") as temporary:
        for command in pending.commands:
            arguments = [
                str(Path(temporary) / "nodesource-setup.sh")
                if part == "/tmp/nodesource-setup.sh"
                else part
                for part in command
            ]
            if arguments[0] == "sudo":
                if root_user:
                    arguments = [value for value in arguments[1:] if value != "-E"]
                else:
                    arguments.insert(1, "-n")
            try:
                run_install_command(arguments, root=root, reporter=reporter, offline=offline)
            except subprocess.TimeoutExpired as error:
                raise ToolchainError(
                    "Node installer timed out. Check that it and its child processes have "
                    "stopped before rerunning Adopt; no automatic retry was started."
                ) from error
            _refresh()
    remaining = plan(offline=offline)
    if remaining.needs_work:
        activation = (
            r".\.venv\Scripts\Activate.ps1"
            if sys.platform == "win32"
            else "source .venv/bin/activate"
        )
        raise ToolchainError(
            "\n" + "=" * 78 + "\nRESTART YOUR TERMINAL — NODE.JS/NPM IS NOT READY\n"
            "Fully close and reopen your terminal application in this project, then run:\n"
            f"{activation}\npdk adopt --apply\n" + "=" * 78
        )
