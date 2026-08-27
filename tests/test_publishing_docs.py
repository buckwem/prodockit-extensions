# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The Publishing section follows the path from local project to live output."""

from __future__ import annotations

import re
from pathlib import Path

from prodockit.template_sync import read_config

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "zensical.toml"


def _publishing_nav() -> list[dict[str, str]]:
    config = read_config(CONFIG.read_text(encoding="utf-8"))
    nav = config["project"]["nav"]
    return next(item["Publish a document"] for item in nav if "Publish a document" in item)


def test_publishing_nav_follows_the_reader_workflow() -> None:
    assert _publishing_nav() == [
        {"21. Publishing overview": "publishing.md"},
        {"22. Staying in step with the template": "devcons/template-sync.md"},
        {"23. Publish automatically": "devcons/continuous-integration.md"},
        {"24. Test the built output": "devcons/testing.md"},
    ]


def test_publishing_overview_covers_the_end_to_end_commands() -> None:
    guide = (ROOT / "docs" / "publishing.md").read_text(encoding="utf-8")
    required = (
        "prodockit-template",
        "prodockit pdf",
        "prodockit build --strict",
        "python -m pytest",
        "GitHub Pages",
        "GitLab Pages",
    )

    missing = [item for item in required if item not in guide]
    assert not missing, f"publishing stages absent from the overview: {missing}"


def test_template_introduction_explains_contents_and_ownership() -> None:
    guide = (ROOT / "docs" / "prodockit-template.md").read_text(encoding="utf-8")
    required = (
        "one source, two outputs",
        "zensical.toml",
        ".github/workflows/docs.yml",
        ".gitlab-ci.yml",
        ".prodockit-template.toml",
        "Project-owned",
        "Template-owned",
        "Shared",
        "prodockit bootstrap",
        "prodockit template-sync",
        "maintained on GitHub",
        "student-facing mirror",
        "is_surrey",
        "Surrey cover",
        "Surrey logos",
    )

    missing = [item for item in required if item not in guide]
    assert not missing, f"template concepts absent from the introduction: {missing}"


def test_every_publishing_page_has_a_navigation_icon() -> None:
    for item in _publishing_nav():
        path = ROOT / "docs" / next(iter(item.values()))
        text = path.read_text(encoding="utf-8")
        assert re.match(r"^---\nicon: [^\n]+\n---\n", text), f"{path.name} has no icon"


def test_ci_page_links_to_workflows_instead_of_copying_them() -> None:
    guide = (ROOT / "docs" / "devcons" / "continuous-integration.md").read_text(
        encoding="utf-8"
    )
    required = (
        "prodockit-template/blob/main/.github/workflows/docs.yml",
        "prodockit-template/blob/main/.gitlab-ci.yml",
    )

    missing = [item for item in required if item not in guide]
    assert not missing, f"maintained automation files absent from CI guide: {missing}"
    assert "```yaml" not in guide, "CI guide embeds workflow YAML that can drift"


def test_repository_site_builds_supply_revision_dates_from_full_history() -> None:
    workflows = (
        ROOT / ".github" / "workflows" / "docs.yml",
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / ".github" / "workflows" / "drift.yml",
    )
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        assert "prodockit build --strict" in text, f"{path.name} bypasses revision dates"
        assert "fetch-depth: 0" in text, f"{path.name} can publish shallow-history dates"


def test_publishing_and_maintenance_state_different_audiences() -> None:
    publishing = (ROOT / "docs" / "publishing.md").read_text(encoding="utf-8")
    maintenance = (ROOT / "docs" / "project-maintenance.md").read_text(encoding="utf-8")

    assert "document author" in publishing
    assert "maintainers of the prodockit repository" in maintenance
