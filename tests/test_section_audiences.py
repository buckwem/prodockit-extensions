# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Every top-level section says who it is for before presenting reference detail."""

from __future__ import annotations

from pathlib import Path

from prodockit.template_sync import read_config

ROOT = Path(__file__).resolve().parent.parent


def test_top_level_sections_open_with_an_introduction() -> None:
    config = read_config((ROOT / "zensical.toml").read_text(encoding="utf-8"))
    nav = config["project"]["nav"]

    expected_first_items = {
        "Getting started": {"Overview": "introduction.md"},
        "Authoring reference": {"Overview": "authoring.md"},
        "Publish a document": {"Publishing overview": "publishing.md"},
        "Maintain prodockit": {"Maintenance overview": "project-maintenance.md"},
        "Contributor internals": {"Overview": "devcons/devcons.md"},
        "About": {"About prodockit": "about/index.md"},
    }

    groups = {next(iter(item)): next(iter(item.values())) for item in nav if isinstance(item, dict)}
    for title, first_item in expected_first_items.items():
        assert groups[title][0] == first_item


def test_section_introductions_name_their_audience() -> None:
    audiences = {
        "docs/introduction.md": "new to prodockit",
        "docs/authoring.md": "document author",
        "docs/publishing.md": "document author",
        "docs/project-maintenance.md": "maintainers of the prodockit repository",
        "docs/devcons/devcons.md": "contributing code to prodockit",
        "docs/about/index.md": "anyone evaluating or using prodockit",
    }

    for relative_path, phrase in audiences.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert phrase in text, f"{relative_path} does not identify its audience"


def test_contributor_internals_has_focused_reference_pages() -> None:
    config = read_config((ROOT / "zensical.toml").read_text(encoding="utf-8"))
    nav = config["project"]["nav"]
    contributor = next(
        item["Contributor internals"] for item in nav if "Contributor internals" in item
    )

    assert contributor == [
        {"Overview": "devcons/devcons.md"},
        {"Development and code map": "devcons/development.md"},
        {"Extension integration": "devcons/extension-internals.md"},
        {"PDF pipeline and API": "devcons/pdf-internals.md"},
        {"Bootstrap design": "devcons/bootstrap-internals.md"},
        {"Zensical coupling": "devcons/zensical-coupling.md"},
        {"Implementation limitations": "devcons/limitations.md"},
    ]


def test_internal_sections_are_not_embedded_in_author_pages() -> None:
    forbidden = {
        "docs/installation.md": "## Development install",
        "docs/pdf.md": "### Python API",
        "docs/extensions/headings.md": "### Sharing a registry across a multi-page build",
        "docs/extensions/refs.md": "#### Under other tools: manual",
        "docs/extensions/citations.md": "#### Under other tools: manual",
        "docs/extensions/glossary.md": "#### Under other tools: manual",
        "docs/extensions/bibliography.md": "## How it works",
        "docs/extensions/steps.md": "### Why continued numbering is emitted twice",
        "docs/devcons/repo-metadata.md": "## Using it from Python",
        "docs/devcons/testing.md": "## A note on installing this everywhere",
        "docs/devcons/bootstrap.md": "### A check must be able to see what its plan does",
    }

    for relative_path, heading in forbidden.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert heading not in text, f"{relative_path} still contains {heading!r}"


def test_moved_internal_topics_are_covered_in_contributor_pages() -> None:
    required = {
        "docs/devcons/development.md": (
            "pip install -e \".[dev]\"",
            "sync_repo_metadata",
            "pytest plugin",
        ),
        "docs/devcons/extension-internals.md": (
            "IdRegistry",
            "CitationRegistry",
            "GlossaryRegistry",
            "pandoc --citeproc",
            "two PDF passes",
            "counter-reset",
        ),
        "docs/devcons/pdf-internals.md": (
            "build_pdf",
            "Page",
            "PdfBuildError",
            "prodockit.pdf.lua",
            "prodockit.pdf.index",
        ),
        "docs/devcons/bootstrap-internals.md": (
            "check",
            "plan",
            "non-interactive",
            "fresh history",
            "guide and verify",
        ),
    }

    for relative_path, phrases in required.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        missing = [phrase for phrase in phrases if phrase not in text]
        assert not missing, f"{relative_path} is missing internal topics: {missing}"
