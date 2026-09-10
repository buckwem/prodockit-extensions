# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Explicitly confirmed repository setup; never commit or push author files."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import click

from prodockit.project_config import load_project_config
from prodockit.sync_repo import SyncRepoError, parse_remote


def _run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=60,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1"},
    )


def setup(config_file: Path, *, offline: bool) -> None:
    from prodockit.adopt_repo_tools import ensure

    config = load_project_config(config_file)
    root = config.root
    repository = str(config.project.get("repo_url") or "")
    try:
        host, _, _ = parse_remote(repository)
    except (ValueError, SyncRepoError):
        click.secho(
            "Repository setup deferred until its address is known. Rerun Adopt when ready.",
            fg="yellow",
        )
        return
    client = "gh" if host == "github.com" else "glab"
    if not ensure(root, client, offline=offline):
        return
    top = _run(["git", "rev-parse", "--show-toplevel"], root)
    if top.returncode == 0 and Path(top.stdout.strip()).resolve() != root.resolve():
        click.secho(
            "This directory is inside another Git repository. "
            "Its repository settings are left unchanged.",
            fg="yellow",
        )
        return
    if top.returncode:
        if not click.confirm(
            "Initialise a local Git repository in this project? No files will be committed.",
            default=False,
        ):
            return
        if _run(["git", "init", "-b", "main"], root).returncode:
            click.secho(
                "Local Git initialisation failed. Rerun Adopt after checking Git "
                "and directory permissions.",
                fg="yellow",
            )
            return
    _commit_identity(root)
    if not offline and not _authenticate(root, client, host):
        return
    remote = _run(["git", "remote", "get-url", "origin"], root)
    if remote.returncode == 0:
        click.echo("An origin remote already exists; it is left unchanged.")
        return
    repository = str(config.project.get("repo_url") or "")
    try:
        host, owner, name = parse_remote(repository)
        if not all(
            re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part) for part in [*owner.split("/"), name]
        ):
            raise ValueError("invalid repository path")
    except (ValueError, SyncRepoError):
        click.secho(
            "Set the repository details with Adopt before connecting an origin remote.", fg="yellow"
        )
        return
    if not click.confirm(
        f"Set up the connection to {repository}? No files will be pushed.", default=False
    ):
        return
    existing = click.confirm(
        "Does this repository already exist on the hosting service?", default=True
    )
    if not existing:
        if offline:
            click.secho(
                "Remote creation is deferred in offline mode. Rerun Adopt online.", fg="yellow"
            )
            return
        if host == "github.com":
            client = "gh"
        elif host == "gitlab.com" or "gitlab" in host:
            client = "glab"
        else:
            click.secho(
                "Create the repository on your hosting service, then rerun Adopt to connect it.",
                fg="yellow",
            )
            return
        visibility = click.prompt(
            "Repository visibility", type=click.Choice(["private", "public"]), default="private"
        )
        if not click.confirm(
            f"Create an empty {visibility} repository at {repository}?", default=False
        ):
            return
        command = (
            ["gh", "repo", "create", f"{owner}/{name}", f"--{visibility}"]
            if client == "gh"
            else ["glab", "repo", "create", repository, f"--{visibility}", "--skipGitInit"]
        )
        if _run(command, root).returncode:
            click.secho(
                "Remote creation did not complete successfully. Check the host before retrying; "
                "it may already exist. No automatic retry or push was attempted.",
                fg="yellow",
            )
            return
    if _run(["git", "remote", "add", "origin", repository], root).returncode:
        click.secho(
            "Could not add origin. Check the repository before retrying; "
            "an existing remote is never replaced.",
            fg="yellow",
        )
        return
    click.secho(
        "Origin configured. No files were committed or pushed; the website is not published.",
        fg="green",
    )


def _commit_identity(root: Path) -> None:
    missing = [
        key
        for key in ("user.name", "user.email")
        if not _run(["git", "config", "--get", key], root).stdout.strip()
    ]
    if not missing or not click.confirm(
        "Set the missing Git commit name/email for this project?", default=True
    ):
        return
    click.echo("Use your preferred commit email or host-provided no-reply address, not a password.")
    answers = {}
    for key in missing:
        value = click.prompt(
            "Your name" if key == "user.name" else "Your commit email", default=""
        ).strip()
        if value:
            answers[key] = value
    if answers and click.confirm(
        "Save this commit identity for this repository only?", default=True
    ):
        for key, value in answers.items():
            if _run(["git", "config", "--local", key, value], root).returncode:
                click.secho(
                    "Git could not save the commit identity. Rerun Adopt to retry.", fg="yellow"
                )


def _authenticate(root: Path, client: str, host: str) -> bool:
    if _run([client, "auth", "status", "--hostname", host], root).returncode == 0:
        return True
    if not click.confirm(f"Sign in to {host} using {client} now?", default=True):
        return False
    click.echo(
        "Follow the hosting tool's sign-in prompts. Adopt does not read or store credentials."
    )
    command = [client, "auth", "login", "--hostname", host]
    if client == "gh":
        command.append("--web")
    # Authentication deliberately owns the terminal; never capture credentials.
    result = subprocess.run(command, cwd=root, timeout=600, check=False)
    if result.returncode or _run([client, "auth", "status", "--hostname", host], root).returncode:
        click.secho(
            f"Sign-in is incomplete. Run `{client} auth login --hostname {host}` and resume Adopt.",
            fg="yellow",
        )
        return False
    return True
