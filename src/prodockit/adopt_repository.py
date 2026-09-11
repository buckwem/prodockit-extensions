# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Explicitly confirmed repository setup; never commit or push author files."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

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


def activity_heading(title: str, explanation: str) -> None:
    """Separate final-phase activities using Adopt's existing heading colour."""
    click.echo()
    click.secho("─" * 78, fg="blue")
    click.secho(f"Activity — {title}", fg="blue", bold=True)
    click.echo(explanation)
    click.echo()


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
    activity_heading(
        "Git and hosting tools",
        f"Check Git and {'GitHub CLI (gh)' if client == 'gh' else 'GitLab CLI (glab)'}. "
        "Missing tools are installed only with your approval.",
    )
    if not ensure(root, client, offline=offline):
        return
    activity_heading(
        "Local repository",
        "Check whether this project already uses Git. Initialising Git does not save a commit.",
    )
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
    click.secho("READY: This project has a local Git repository.", fg="green")
    activity_heading(
        "Commit name and email",
        "Check the identity used for future commits. This is separate from signing in.",
    )
    _commit_identity(root)
    activity_heading(
        "Sign in to the hosting service",
        f"Check your sign-in to {host}. The hosting tool handles authentication, not Adopt.",
    )
    if offline:
        click.secho("Sign-in skipped in offline mode.", fg=(230, 159, 0))
    if not offline and not _authenticate(root, client, host):
        return
    activity_heading(
        "Connect the hosted repository",
        "Keep an existing connection, or confirm a new one. No files will be uploaded.",
    )
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
        activity_heading(
            "Create the hosted repository",
            "Create an empty repository on the hosting service. Check its address and visibility.",
        )
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
        try:
            created = _run(command, root).returncode == 0
        except (OSError, subprocess.SubprocessError):
            created = False
        if not created:
            click.secho(
                "The hosting tool did not confirm creation. Checking whether the exact "
                "repository exists; creation will not be retried.",
                fg="yellow",
            )
            if not _verify_created_repository(root, client, repository, visibility):
                click.secho(
                    "Could not verify the repository and its requested visibility. "
                    "Check it on the hosting service before retrying. "
                    "Run `pdk adopt --apply` and answer Yes to the existing-repository "
                    "question if it is already there. No connection or push was attempted.",
                    fg="yellow",
                )
                return
            click.secho(f"The {visibility} repository exists at {repository}.", fg="green")
            if not click.confirm(
                "Finish connecting this project to that repository? No files will be pushed.",
                default=False,
            ):
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


def _verify_created_repository(root: Path, client: str, repository: str, visibility: str) -> bool:
    """Resolve an ambiguous create once, without retrying any remote mutation."""
    host, owner, name = parse_remote(repository)
    command = (
        ["gh", "repo", "view", repository, "--json", "url,isPrivate"]
        if client == "gh"
        else [
            "glab",
            "api",
            f"projects/{quote(f'{owner}/{name}', safe='')}",
            "--hostname",
            host,
        ]
    )
    try:
        result = _run(command, root)
        if result.returncode:
            return False
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            return False
        url = data.get("url" if client == "gh" else "web_url")
        if not isinstance(url, str) or parse_remote(url) != (host, owner, name):
            return False
        if client == "gh":
            return data.get("isPrivate") is (visibility == "private")
        return data.get("visibility") == visibility
    except (OSError, subprocess.SubprocessError, ValueError, SyncRepoError):
        return False


def _commit_identity(root: Path) -> None:
    missing = [
        key
        for key in ("user.name", "user.email")
        if not _run(["git", "config", "--get", key], root).stdout.strip()
    ]
    if not missing:
        click.secho("READY: Git commit name and email are already set.", fg="green")
        return
    if not click.confirm("Set the missing Git commit name/email for this project?", default=True):
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
        click.secho(f"READY: Already signed in to {host}.", fg="green")
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
    try:
        result = subprocess.run(command, cwd=root, timeout=600, check=False)
    except subprocess.TimeoutExpired:
        click.secho(
            "Sign-in timed out before completion. Earlier installation work is retained. "
            f"Run `{client} auth login --hostname {host}` for a fresh sign-in, complete "
            "it promptly, then run `pdk adopt --apply` to finish repository setup.",
            fg="yellow",
        )
        return False
    if result.returncode or _run([client, "auth", "status", "--hostname", host], root).returncode:
        click.secho(
            f"Sign-in is incomplete. Run `{client} auth login --hostname {host}` and resume Adopt.",
            fg="yellow",
        )
        return False
    return True
