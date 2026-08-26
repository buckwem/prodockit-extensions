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


def test_getting_started_holds_installation_routes() -> None:
    getting_started = _nav_group("Getting started")
    publishing = _nav_group("Publish a document")
    maintenance = _nav_group("Maintain prodockit")

    assert {"3. Add prodockit to an existing document": "adopt.md"} in getting_started
    assert {"4. Set up a template project": "devcons/bootstrap.md"} in getting_started
    assert {"5. Start with prodockit-template": "prodockit-template.md"} in getting_started
    assert {
        "22. Staying in step with the template": "devcons/template-sync.md"
    } in publishing
    assert maintenance == [
        {"25. Maintenance overview": "project-maintenance.md"},
        {"26. Repository metadata": "devcons/repo-metadata.md"},
        {"27. Version pinning and drift": "devcons/pinning-drift.md"},
        {"28. Build and release": "devcons/releasing.md"},
    ]


def test_release_guide_covers_every_github_actions_workflow() -> None:
    guide = (ROOT / "docs" / "devcons" / "releasing.md").read_text(encoding="utf-8")
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

    missing = [workflow.name for workflow in workflows if workflow.name not in guide]
    assert not missing, f"GitHub Actions workflows absent from the release guide: {missing}"


def test_release_diagram_distinguishes_entry_points_from_steps() -> None:
    guide = (ROOT / "docs" / "devcons" / "releasing.md").read_text(encoding="utf-8")

    assert "START<br>Release branch" in guide
    assert "SCHEDULED TRIGGER<br>Every Monday" in guide
    assert "classDef entry" in guide


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
        "shared-files",
        "source-bundle",
        "sync-repo",
        "template-sync",
    )

    missing = [command for command in commands if f"`prodockit {command}" not in guide]
    assert not missing, f"public CLI commands absent from the command map: {missing}"


def test_template_sync_guide_covers_package_only_updates() -> None:
    guide = (ROOT / "docs" / "devcons" / "template-sync.md").read_text(encoding="utf-8")

    assert "version of prodockit installed" in guide
    assert "python -m pip install" in guide
    assert "When only prodockit needs upgrading" in guide
    assert "Pages" in guide and "documentation" in guide
    assert "manual rebuild is still necessary" in guide


def test_template_sync_links_managed_stylesheet_warnings_to_the_style_guide() -> None:
    guide = (ROOT / "docs" / "devcons" / "template-sync.md").read_text(encoding="utf-8")

    assert "Warning - managed stylesheet changes found" in guide
    assert "[Stylesheets](../stylesheets.md)" in guide
