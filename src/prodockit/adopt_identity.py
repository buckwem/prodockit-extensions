# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Guided, optional site identity setup without creating repositories or remotes."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import click
import tomlkit

from prodockit.project_config import load_project_config
from prodockit.sync_repo import SyncRepoError, icon_for_host, parse_remote, site_url_for


def missing_fields(project: dict[str, Any]) -> list[str]:
    missing = []
    for key in ("site_name", "site_url", "repo_url", "repo_name"):
        value = str(project.get(key) or "").strip()
        placeholder = not value
        if key == "site_name":
            placeholder |= value.casefold() in {
                "documentation",
                "my docs",
                "my site",
                "your site",
                "your site name",
            }
        if key.endswith("url"):
            parsed = urlparse(value)
            placeholder |= parsed.hostname in {
                "example.com",
                "www.example.com",
                "example.org",
                "www.example.org",
            }
            if key == "repo_url":
                placeholder |= parsed.path.strip("/") in {
                    "user/repo",
                    "your-account/your-repository",
                }
        if key == "repo_name":
            placeholder |= value in {"user/repo", "your-account/your-repository"}
        if placeholder:
            missing.append(key)
    return missing


def _url(question: str, default: str = "") -> str:
    while True:
        answer = click.prompt(question, default=default, show_default=bool(default)).strip()
        if not answer:
            return ""
        parsed = urlparse(answer)
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
            return answer
        click.secho(
            "Enter a full http:// or https:// address, without login credentials.", fg="yellow"
        )


def _deferred(missing: list[str]) -> None:
    click.secho("Run 'pdk adopt --apply' to correct:", fg="yellow", bold=True)
    labels = {
        "site_name": "Site title (site_name)",
        "site_url": "Website address (site_url)",
        "repo_url": "Repository address (repo_url)",
        "repo_name": "Repository display name (repo_name)",
    }
    for number, key in enumerate(missing, 1):
        click.echo(f"{number}. {labels[key]} has not been set.")


def configure(
    config_file: Path, *, apply: bool, interactive: bool, repository_setup: bool = True
) -> bool:
    config = load_project_config(config_file)
    missing = missing_fields(config.project)
    if not repository_setup:
        missing = [key for key in missing if key in {"site_name", "site_url"}]
    if not missing:
        click.secho("Selected site details are already configured; no change needed.", fg="green")
        return False
    click.secho("Site details still to complete: " + ", ".join(missing), fg="yellow", bold=True)
    if not apply or not interactive:
        _deferred(missing)
        click.echo("Answer the questions in a terminal. Local testing can continue.")
        return False
    if config.path.suffix != ".toml":
        click.secho(
            "Guided identity editing currently requires zensical.toml; "
            "existing YAML is left unchanged.",
            fg="yellow",
        )
        return False
    if not click.confirm("Would you like to complete these details now?", default=True):
        _deferred(missing)
        return False
    click.echo(
        "These answers only update this site's configuration. No repository or website is created."
    )
    click.echo("Leave an answer blank if it is not known yet.")
    updates = {}
    if "site_name" in missing:
        name = click.prompt("What title should appear on your site?", default="").strip()
        if name:
            updates["site_name"] = name

    repository = str(config.project.get("repo_url") or "") if "repo_url" not in missing else ""
    if "repo_url" in missing and shutil.which("git"):
        try:
            result = subprocess.run(
                ["git", "-C", str(config.root), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                host, owner, name = parse_remote(result.stdout.strip())
                suggested = f"https://{host}/{owner}/{name}"
                if click.confirm(f"Use the existing repository {suggested}?", default=True):
                    repository = suggested
        except (OSError, subprocess.SubprocessError, ValueError, SyncRepoError):
            pass
    if (
        "repo_url" in missing
        and not repository
        and click.confirm("Do you know where your repository will be hosted?", default=True)
    ):
        host = click.prompt(
            "Repository host (github.com, gitlab.com, or your organisation's Git host)", default=""
        ).strip()
        if host:
            host = host.removeprefix("https://").removeprefix("http://").rstrip("/").lower()
            if not all(character.isalnum() or character in ".-:" for character in host):
                raise click.ClickException(
                    "Use a hostname only, not an account or repository path. "
                    "Rerun Adopt to try again."
                )
            personal = click.confirm(
                "Will the repository be under your personal account?", default=True
            )
            owner = (
                click.prompt(
                    "What is your account name?"
                    if personal
                    else "What is the organisation or group path (include subgroups)?",
                    default="",
                )
                .strip()
                .strip("/")
            )
            name = click.prompt("What is the repository name?", default="").strip()
            if owner and name:
                if not all(
                    re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part)
                    for part in [*owner.split("/"), name]
                ):
                    raise click.ClickException(
                        "Use account/group and repository names, not URLs. "
                        "Rerun Adopt to try again."
                    )
                repository = f"https://{host}/{owner}/{name}"
    if repository:
        if "repo_url" in missing:
            updates["repo_url"] = repository
        if "repo_name" in missing:
            try:
                _, owner, name = parse_remote(repository)
                updates["repo_name"] = f"{owner}/{name}"
            except (ValueError, SyncRepoError):
                display = click.prompt("Repository display name", default="").strip()
                if display:
                    updates["repo_name"] = display
    if "site_url" in missing:
        suggested = ""
        if repository:
            try:
                host, owner, name = parse_remote(repository)
                kind, _, _ = icon_for_host(host)
                suggested = site_url_for(kind, owner, name, None, host) or ""
            except (ValueError, SyncRepoError):
                pass
        if suggested:
            click.echo("This is a suggested Pages address, not proof that the site is published.")
        else:
            click.echo(
                "For GitLab or custom hosting, use the exact address shown by your "
                "hosting service; do not guess."
            )
        if click.confirm(
            "Do you know the website address, or want to use a suggested Pages address?",
            default=bool(suggested),
        ):
            address = _url("Website address (site_url)", suggested)
            if address:
                updates["site_url"] = address
    if not updates:
        _deferred(missing)
        return False
    for key, value in updates.items():
        click.echo(f"  {key}: {value}")
    if not click.confirm("Save these details in zensical.toml?", default=True):
        return False
    from prodockit.adopt import _atomic_write

    document = tomlkit.parse(config.path.read_text(encoding="utf-8"))
    for key, value in updates.items():
        project: Any = document["project"]
        project[key] = value
    rendered = tomlkit.dumps(document)
    tomlkit.parse(rendered)
    _atomic_write(config.path, rendered.encode("utf-8"))
    click.secho(
        "Site details saved. No Git remotes, repositories or hosting settings were changed.",
        fg="green",
    )
    remaining = [key for key in missing if key not in updates]
    if remaining:
        _deferred(remaining)
    return True
