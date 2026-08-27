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
        {"22. Publishing overview": "publishing.md"},
        {"23. Staying in step with the template": "devcons/template-sync.md"},
        {"24. Publish automatically": "devcons/continuous-integration.md"},
        {"25. Test the built output": "devcons/testing.md"},
    ]


def test_publishing_overview_covers_the_end_to_end_commands() -> None:
    guide = (ROOT / "docs" / "publishing.md").read_text(encoding="utf-8")
    required = (
        "prodockit-template",
        "prodockit pdf",
        "zensical build --clean --strict",
        "prodockit update-dates",
        "update-dates.md",
        "python -m pytest",
        "GitHub Pages",
        "GitLab Pages",
    )

    missing = [item for item in required if item not in guide]
    assert not missing, f"publishing stages absent from the overview: {missing}"


def test_authoring_explains_page_dates_and_links_to_the_build() -> None:
    guide = (ROOT / "docs" / "update-dates.md").read_text(encoding="utf-8")
    required = (
        "<!-- prodockit-update-date -->",
        "The text before or after the marker",
        "revision_date: 2026-08-27",
        "Updated on YYYY-MM-DD",
        "publishing.md#build-with-revision-dates",
    )

    missing = [item for item in required if item not in guide]
    assert not missing, f"page-date authoring guidance is incomplete: {missing}"

    authoring = (ROOT / "docs" / "authoring.md").read_text(encoding="utf-8")
    macros = (ROOT / "docs" / "macros.md").read_text(encoding="utf-8")
    publishing = (ROOT / "docs" / "publishing.md").read_text(encoding="utf-8")

    assert "[Page update dates](update-dates.md)" in authoring
    assert "Page dates are not macros" in macros
    assert "[Page update dates](update-dates.md)" in macros
    assert "[Page update dates](update-dates.md)" in publishing


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
        assert "prodockit update-dates" in text, f"{path.name} bypasses revision dates"
        assert "fetch-depth: 0" in text, f"{path.name} can publish shallow-history dates"


def test_publishing_and_maintenance_state_different_audiences() -> None:
    publishing = (ROOT / "docs" / "publishing.md").read_text(encoding="utf-8")
    maintenance = (ROOT / "docs" / "project-maintenance.md").read_text(encoding="utf-8")

    assert "document author" in publishing
    assert "maintainers of the prodockit repository" in maintenance
