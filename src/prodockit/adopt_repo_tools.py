# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Opt-in Git/hosting CLI provisioning through Adopt's resilient installer."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import click

from prodockit import adopt_package_manager
from prodockit.adopt_node import run_commands
from prodockit.bootstrap import current_platform
from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS, refresh_windows_path
from prodockit.toolchain import ToolchainError


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
