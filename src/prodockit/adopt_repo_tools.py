# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Opt-in Git/hosting CLI provisioning through Adopt's resilient installer."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import click

from prodockit import adopt_package_manager
from prodockit.bootstrap import current_platform
from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS, refresh_windows_path
from prodockit.renderer_resilience import RetryReporter
from prodockit.toolchain import ToolchainError, run_install_command


def run_commands(
    root: Path,
    commands: Sequence[Sequence[str]],
    *,
    offline: bool = False,
    reporter: RetryReporter | None = None,
    refresh: Callable[[], None] | None = None,
    label: str = "Repository tools",
) -> None:
    """Run approved repository-tool installers with bounded retries."""
    refresh = refresh or _refresh
    root_user = hasattr(os, "geteuid") and os.geteuid() == 0
    if not root_user and any(command[0] == "sudo" for command in commands):
        authenticated = (
            subprocess.run(["sudo", "-n", "-v"], check=False, timeout=30).returncode == 0
        )
        if not authenticated:
            if not sys.stdin.isatty():
                raise ToolchainError(
                    "Administrator approval is required. Run pdk adopt --apply "
                    "in an interactive terminal."
                )
            if subprocess.run(["sudo", "-v"], check=False, timeout=300).returncode:
                raise ToolchainError(
                    f"Administrator approval was declined; {label} were not installed"
                )
    for command in commands:
        arguments = list(command)
        if arguments[0] == "sudo":
            if root_user:
                arguments = [value for value in arguments[1:] if value != "-E"]
            else:
                arguments.insert(1, "-n")
        run_install_command(arguments, root=root, reporter=reporter, offline=offline)
        refresh()


def install_commands(platform: str, missing: list[str]) -> list[list[str]]:
    if platform == MACOS:
        return [["brew", "install", *missing]]
    if platform == UBUNTU:
        return [["sudo", "apt-get", "update"], ["sudo", "apt-get", "install", "-y", *missing]]
    if platform == WINDOWS:
        ids = {"git": "Git.Git", "gh": "GitHub.cli", "glab": "GLab.GLab"}
        return [
            [
                "winget",
                "install",
                "--id",
                ids[name],
                "--exact",
                "--source",
                "winget",
                "--accept-source-agreements",
                "--accept-package-agreements",
                "--disable-interactivity",
            ]
            for name in missing
        ]
    raise ToolchainError("Repository tool installation supports Windows 11, Ubuntu and macOS.")


def _refresh() -> None:
    if os.name == "nt":
        refresh_windows_path()
    else:
        for directory in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
            if Path(directory).is_dir() and directory not in os.get_exec_path():
                os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")


def ensure(root: Path, client: str, *, offline: bool) -> bool:
    _refresh()
    missing = [name for name in ("git", client) if not shutil.which(name)]
    if not missing:
        click.secho(f"READY: Git and {client} are already installed.", fg="green")
        return True
    if offline:
        click.secho(
            "Repository tools are missing: "
            + ", ".join(missing)
            + ". Rerun Adopt online to install them.",
            fg="yellow",
        )
        return False
    if not click.confirm(
        "Install missing repository tools: " + ", ".join(missing) + "?", default=True
    ):
        return False
    platform = current_platform()
    manager = adopt_package_manager.plan(platform)
    if manager.blocked:
        click.secho(manager.blocked, fg="yellow")
        return False
    try:
        run_commands(
            root,
            [*manager.commands, *install_commands(platform, missing)],
            label="Repository tools",
            refresh=_refresh,
        )
    except (ToolchainError, OSError, subprocess.SubprocessError) as error:
        click.secho(f"Repository tool installation is incomplete: {error}", fg="yellow")
        return False
    if any(not shutil.which(name) for name in ("git", client)):
        click.secho("=" * 78, fg="yellow", bold=True)
        click.secho("REPOSITORY TOOLS ARE NOT YET AVAILABLE", fg="yellow", bold=True)
        click.echo(
            "Fully close and reopen your terminal, return to this project "
            "and activate its environment."
        )
        click.echo("Then run 'pdk adopt --apply' to finish repository setup.")
        click.secho("=" * 78, fg="yellow", bold=True)
        return False
    return True
