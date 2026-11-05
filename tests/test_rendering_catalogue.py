# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Source contract for the Zensical rendering review catalogue."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_ROOT = ROOT / "tests" / "rendering_catalogue"
LEDGER = CATALOGUE_ROOT / "catalogue.toml"
CONFIG = CATALOGUE_ROOT / "zensical.toml"
DOCS = CATALOGUE_ROOT / "docs"

EXPECTED_CATEGORY_COUNTS = {
    "python-markdown": 13,
    "pymdown": 30,
    "configured-extension": 4,
    "zensical-authoring": 17,
    "prodockit": 9,
}
VALID_STATUSES = {"planned", "implemented", "waived"}
VALID_NESTED_DECISIONS = {"planned", "required", "not-applicable"}
ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


def _load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _prose(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _nav_paths(items: list[Any]) -> list[str]:
    paths: list[str] = []
    for item in items:
        value = next(iter(item.values()))
        if isinstance(value, list):
            paths.extend(_nav_paths(value))
        else:
            paths.append(value)
    return paths


def test_catalogue_metadata_is_versioned_and_matches_the_supported_zensical() -> None:
    ledger = _load(LEDGER)
    metadata = ledger["catalogue"]

    assert metadata["version"] == 1
    assert date.fromisoformat(metadata["reviewed_on"]) <= date.today()
    assert metadata["route"].startswith("/") and metadata["route"].endswith("/")

    project = _load(ROOT / "pyproject.toml")["project"]
    zensical = next(
        Requirement(dependency)
        for dependency in project["dependencies"]
        if Requirement(dependency).name == "zensical"
    )
    assert str(zensical.specifier) == f">={metadata['reviewed_zensical']}"


def test_reviewed_inventory_has_the_expected_category_boundary() -> None:
    capabilities = _load(LEDGER)["capability"]

    assert len(capabilities) == 73
    assert Counter(item["category"] for item in capabilities) == EXPECTED_CATEGORY_COUNTS


def test_every_capability_has_a_unique_well_formed_coverage_decision() -> None:
    capabilities = _load(LEDGER)["capability"]
    ids = [item["id"] for item in capabilities]
    by_id = {item["id"]: item for item in capabilities}

    assert len(ids) == len(set(ids))
    assert all(ID_RE.fullmatch(capability_id) for capability_id in ids)

    for item in capabilities:
        assert item["title"].strip()
        assert item["kind"] in {"authoring", "configuration", "extension"}
        assert item["reference"].startswith("https://")
        assert item["status"] in VALID_STATUSES
        assert item["nested"] in VALID_NESTED_DECISIONS

        if item["kind"] == "configuration":
            parent = item.get("parent")
            assert parent in by_id
            assert by_id[parent]["kind"] == "extension"

        if item["nested"] == "not-applicable":
            assert item.get("nested_reason", "").strip()

        if item["nested"] == "required":
            assert item.get("nested_page", "").strip()
            assert item.get("nested_anchor", "").strip()
            assert (DOCS / item["nested_page"]).is_file()

        if item["status"] == "implemented":
            for field in ("page", "anchor", "website_expectation", "pdf_expectation"):
                assert item.get(field, "").strip(), f"{item['id']} has no {field}"
            assert item.get("visual_review") == "required"
            specimen = DOCS / item["page"]
            assert specimen.is_file()
            assert item["reference"] in specimen.read_text(encoding="utf-8")
            assert item["nested"] != "planned"

        if item["status"] == "waived":
            assert item.get("rationale", "").strip()


def test_catalogue_navigation_is_isolated_and_all_pages_exist() -> None:
    project = _load(CONFIG)["project"]
    ledger = _load(LEDGER)["catalogue"]

    assert project["docs_dir"] == "docs"
    assert project["site_dir"] == "site"
    assert project["site_url"].endswith(ledger["route"])
    assert all((DOCS / page).is_file() for page in _nav_paths(project["nav"]))

    public_nav = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    assert "tests/rendering_catalogue" not in public_nav


def test_review_index_exposes_the_inventory_and_future_review_sections() -> None:
    capabilities = _load(LEDGER)["capability"]
    status_counts = Counter(item["status"] for item in capabilities)
    index = _prose(DOCS / "index.md")
    nested = _prose(DOCS / "nested-content" / "index.md")
    page_breaks = _prose(DOCS / "page-breaks" / "index.md")

    for count in EXPECTED_CATEGORY_COUNTS.values():
        assert f"| {count} |" in index
    assert "**73**" in index
    assert f"**{status_counts['implemented']}**" in index
    assert f"**{status_counts['planned']}**" in index
    assert "Every capability must also make a nested-content decision" in index
    assert "grow whenever a new capability is brought into scope" in nested
    assert "explicitly forced page breaks" in page_breaks
    assert "same page or different" in page_breaks


def test_interactive_phase_three_capabilities_define_static_transformations() -> None:
    capabilities = {item["id"]: item for item in _load(LEDGER)["capability"]}
    interactive = {
        "pymdown.arithmatex",
        "pymdown.details",
        "pymdown.highlight",
        "pymdown.tabbed",
        "pymdown.tasklist",
    }

    for capability_id in interactive:
        assert capabilities[capability_id].get("static_transformation", "").strip()


def test_phase_three_configuration_and_supporting_inputs_are_complete() -> None:
    project = _load(CONFIG)["project"]
    extensions = project["markdown_extensions"]
    pymdown = extensions["pymdownx"]

    expected_extensions = {
        "arithmatex",
        "caret",
        "details",
        "emoji",
        "highlight",
        "inlinehilite",
        "keys",
        "mark",
        "smartsymbols",
        "snippets",
        "superfences",
        "tabbed",
        "tasklist",
        "tilde",
    }
    assert expected_extensions <= pymdown.keys()
    assert "pymdownx.blocks.caption" in extensions

    assert pymdown["arithmatex"] == {"generic": True}
    assert pymdown["emoji"] == {
        "emoji_index": "zensical.extensions.emoji.twemoji",
        "emoji_generator": "zensical.extensions.emoji.to_svg",
        "options": {"custom_icons": ["overrides/.icons"]},
    }
    assert pymdown["highlight"] == {
        "pygments_lang_class": True,
        "auto_title": True,
        "linenums": True,
        "linenums_style": "pymdownx-inline",
        "anchor_linenums": True,
        "line_spans": "__span",
    }
    assert pymdown["tabbed"] == {
        "alternate_style": True,
        "combine_header_slug": True,
        "slugify": {"object": "pymdownx.slugs.slugify", "kwds": {"case": "lower"}},
    }
    assert pymdown["tasklist"] == {"custom_checkbox": True, "clickable_checkbox": True}
    assert pymdown["superfences"]["custom_fences"] == [
        {
            "name": "catalogue",
            "class": "catalogue-fence",
            "format": "pymdownx.superfences.fence_code_format",
        }
    ]

    assert (CATALOGUE_ROOT / "docs" / "javascripts" / "mathjax.js").is_file()
    assert (CATALOGUE_ROOT / "overrides" / ".icons" / "catalogue" / "phase.svg").is_file()
    assert (CATALOGUE_ROOT / "snippets" / "phase-three.md").is_file()


def test_catalogue_builds_cleanly(tmp_path: Path) -> None:
    project = tmp_path / "rendering_catalogue"
    shutil.copytree(
        CATALOGUE_ROOT,
        project,
        ignore=shutil.ignore_patterns(".cache", ".prodockit", "build", "site", "*.pdf"),
    )

    result = subprocess.run(
        [sys.executable, "-m", "zensical", "build", "--clean", "--strict"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No issues found" in result.stdout + result.stderr
    for page in ("index.html", "nested-content/index.html", "page-breaks/index.html"):
        assert (project / "site" / page).is_file()
