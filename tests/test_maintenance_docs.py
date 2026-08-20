# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The maintenance guide covers the repository's real operating workflow."""

from __future__ import annotations

from pathlib import Path

from prodockit.template_sync import read_config

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "zensical.toml"


def _nav_group(title: str) -> list[dict[str, str]]:
    config = read_config(CONFIG.read_text(encoding="utf-8"))
    nav = config["project"]["nav"]
    return next(item[title] for item in nav if title in item)


def test_bootstrap_is_publishing_and_maintenance_has_an_end_to_end_path() -> None:
    publishing = _nav_group("Publishing")
    maintenance = _nav_group("Project maintenance")

    assert {"Set up a machine": "devcons/bootstrap.md"} in publishing
    assert maintenance == [
        {"Maintenance overview": "project-maintenance.md"},
        {"Command-line tools": "command-line.md"},
        {"Repository metadata": "devcons/repo-metadata.md"},
        {"Version pinning and drift": "devcons/pinning-drift.md"},
        {"Staying in step with the template": "devcons/template-sync.md"},
        {"Build and release": "devcons/releasing.md"},
    ]


def test_release_guide_covers_every_github_actions_workflow() -> None:
    guide = (ROOT / "docs" / "devcons" / "releasing.md").read_text(encoding="utf-8")
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

    missing = [workflow.name for workflow in workflows if workflow.name not in guide]
    assert not missing, f"GitHub Actions workflows absent from the release guide: {missing}"


def test_release_guide_covers_the_version_sources_and_release_gates() -> None:
    guide = (ROOT / "docs" / "devcons" / "releasing.md").read_text(encoding="utf-8")
    required = (
        "pyproject.toml",
        "src/prodockit/__init__.py",
        "docs/about/changelog.md",
        "prodockit pins --check --offline",
        "pytest",
        "ruff check .",
        "mypy src",
        "zensical build --clean --strict",
        "GitHub release",
        "PyPI",
        "Trusted Publishing",
    )

    missing = [item for item in required if item not in guide]
    assert not missing, f"release steps or gates absent from the guide: {missing}"


def test_command_map_lists_every_public_command() -> None:
    guide = (ROOT / "docs" / "command-line.md").read_text(encoding="utf-8")
    commands = (
        "bootstrap",
        "init-mathjax",
        "init-tools",
        "pdf",
        "pins",
        "source-bundle",
        "sync-repo",
        "template-sync",
    )

    missing = [command for command in commands if f"`prodockit {command}" not in guide]
    assert not missing, f"public CLI commands absent from the command map: {missing}"
