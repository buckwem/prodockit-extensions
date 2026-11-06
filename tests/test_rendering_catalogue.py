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

from tools import rendering_catalogue as review_bundle

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
    assert project["plugins"] == [{"search": {"enabled": False}}]
    assert project["theme"]["custom_dir"] == "overrides"
    assert project["site_url"].endswith(ledger["route"])
    assert all((DOCS / page).is_file() for page in _nav_paths(project["nav"]))

    public_nav = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    assert "tests/rendering_catalogue" not in public_nav


def test_phase_seven_test_layers_classify_every_catalogue_assertion_once() -> None:
    layers = review_bundle.test_layers()
    assert sum(len(layer["tests"]) for layer in layers) == len(
        review_bundle.catalogue_test_functions()
    )
    assert all(layer["tests"] for layer in layers)


def test_phase_seven_ci_and_release_qualification_contract() -> None:
    workflow = (ROOT / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")
    release_gate = (ROOT / "tools" / "release_gate_provider_status.py").read_text(
        encoding="utf-8"
    )
    project = _load(CONFIG)["project"]

    assert "pull_request:" in workflow
    assert 'tests/rendering_catalogue/**' in workflow
    assert "python tools/rendering_catalogue.py build" in workflow
    assert "if: always()" in workflow
    assert "github.event_name != 'pull_request'" in workflow
    build_job = workflow.split("\n  build:\n", 1)[1].split("\n  deploy:\n", 1)[0]
    deploy_job = workflow.split("\n  deploy:\n", 1)[1].split("\n  verify:\n", 1)[0]
    assert "environment:" not in build_job
    assert "actions/deploy-pages@v4" not in build_job
    assert "if: github.event_name != 'pull_request'" in deploy_job
    assert "environment:\n      name: github-pages" in deploy_job
    assert "actions/deploy-pages@v4" in deploy_job
    assert "needs: [build, deploy]" in workflow
    assert '".github/workflows/docs.yml"' in release_gate
    assert project["extra_css"] == ["stylesheets/pdk.css", "stylesheets/page-breaks.css"]
    assert project["extra_javascript"] == [
        "javascripts/mathjax.js",
        "https://unpkg.com/mathjax@3/es5/tex-mml-chtml.js",
    ]


def test_phase_six_review_bundle_and_crawler_controls_are_declared() -> None:
    sources = _nav_paths(_load(CONFIG)["project"]["nav"])
    assert review_bundle.catalogue_sources() == sources
    assert review_bundle.page_url("index.md") == ""
    assert review_bundle.page_url("pymdown/index.md") == "pymdown/"
    assert review_bundle.page_url("pymdown/tabs.md") == "pymdown/tabs/"
    assert review_bundle.page_pdf("nested-content/index.md").as_posix() == (
        "page-pdfs/nested-content/index.pdf"
    )

    override = (CATALOGUE_ROOT / "overrides" / "main.html").read_text(encoding="utf-8")
    for directive in ("noindex", "nofollow", "noarchive", "nosnippet", "noimageindex"):
        assert directive in override

    robots = (ROOT / "docs" / "robots.txt").read_text(encoding="utf-8")
    assert "User-agent: *" in robots
    assert "Disallow: /rendering-review/" in robots
    for agent in ("GPTBot", "OAI-SearchBot", "ClaudeBot", "CCBot", "PerplexityBot"):
        assert f"User-agent: {agent}" in robots

    public_markdown = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "docs").rglob("*.md")
    )
    assert "/rendering-review/" not in public_markdown

    workflow = (ROOT / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")
    for command in (
        "tools/rendering_catalogue.py build",
        "tools/rendering_catalogue.py verify",
        "tools/rendering_catalogue.py publish",
        "tools/rendering_catalogue.py verify-publication",
    ):
        assert command in workflow
    assert "rendering-review-bundle" in workflow
    assert "if: always()" in workflow

    readme = _prose(CATALOGUE_ROOT / "README.md")
    assert "X-Robots-Tag" in readme
    assert "crawler can ignore" in readme


def test_review_index_exposes_the_inventory_and_review_sections() -> None:
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
    assert "grows whenever a new capability is brought into scope" in nested
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
        },
        {
            "name": "mermaid",
            "class": "mermaid",
            "format": "pymdownx.superfences.fence_code_format",
        },
    ]

    assert (CATALOGUE_ROOT / "docs" / "javascripts" / "mathjax.js").is_file()
    assert (CATALOGUE_ROOT / "overrides" / ".icons" / "catalogue" / "phase.svg").is_file()
    assert (CATALOGUE_ROOT / "snippets" / "phase-three.md").is_file()


def test_phase_four_configuration_and_coverage_are_complete() -> None:
    ledger = _load(LEDGER)["capability"]
    project = _load(CONFIG)["project"]
    extensions = project["markdown_extensions"]

    assert Counter(item["status"] for item in ledger) == {
        "implemented": 72,
        "waived": 1,
    }
    assert not any(item["status"] == "planned" for item in ledger)

    assert {"betterem", "magiclink"} <= extensions["pymdownx"].keys()
    assert extensions["zensical"]["extensions"]["glightbox"] == {
        "auto": True,
        "auto_themed": True,
        "auto_caption": False,
    }
    assert extensions["zensical"]["extensions"]["macros"] == {
        "module_name": "catalogue_macros",
        "on_error_fail": True,
    }
    assert project["extra_css"] == [
        "stylesheets/pdk.css",
        "stylesheets/page-breaks.css",
    ]
    for name in (
        "headings",
        "refs",
        "citations",
        "glossary",
        "tables",
        "tree",
        "steps",
        "bibliography",
        "index",
    ):
        assert f"prodockit.{name}" in extensions

    directives = next(item for item in ledger if item["id"] == "zensical.authoring.directives")
    assert directives["status"] == "waived"
    assert "Zensical Spark" in directives["rationale"]
    assert "Zensical Spark" in _prose(DOCS / "zensical-authoring" / "index.md")
    assert (CATALOGUE_ROOT / "catalogue_macros.py").is_file()
    assert (CATALOGUE_ROOT / "references.bib").is_file()
    assert (DOCS / "stylesheets" / "pdk.css").read_bytes() == (
        ROOT / "docs" / "stylesheets" / "pdk.css"
    ).read_bytes()


def test_phase_five_nested_and_page_boundary_contract_is_complete() -> None:
    project = _load(CONFIG)["project"]
    nav = _nav_paths(project["nav"])
    pdf = _load(CATALOGUE_ROOT / "pdk-pdf.toml")
    document = pdf["document"]

    assert "page-breaks/forced-and-kept.md" in nav
    assert "page-breaks/flow-and-overflow.md" in nav
    assert document["page_size"] == "A4"
    assert document["extra_css"][-1] == "stylesheets/page-breaks.css"
    assert pdf["margins"] == {
        "top": "2cm",
        "right": "2cm",
        "bottom": "2.5cm",
        "left": "2cm",
    }

    matrix = _prose(DOCS / "nested-content" / "index.md")
    for case in (
        "Blockquotes",
        "Ordered, unordered, nested and task lists",
        "Admonitions",
        "Details and content tabs",
        "Grids and images",
        "Markdown in HTML",
        "Tables and cells",
        "Captions and figures",
        "Footnotes",
        "Directives",
    ):
        assert case in matrix
    assert "record why nesting has no independent meaning" in matrix
    assert "Directives" in matrix and "Waiver" in matrix

    complex_cases = _prose(DOCS / "nested-content" / "complex-combinations.md")
    for marker in (
        "List-owned call-out",
        "Content tabs containing a grid",
        "Grid containing lists and admonitions",
        "Numbered steps containing tabs and a grid",
        "Final nested result",
    ):
        assert marker in complex_cases
    assert complex_cases.count("**Markdown used**") == 4

    deep_admonitions = _prose(DOCS / "nested-content" / "deep-admonitions.md")
    for marker in (
        "Four-level warning",
        "Deep procedure card",
        "Card-owned procedure",
        "Stable sibling card",
    ):
        assert marker in deep_admonitions
    assert deep_admonitions.count("**Markdown used**") == 2

    specimens = "\n".join(
        (DOCS / "page-breaks" / name).read_text(encoding="utf-8")
        for name in ("forced-and-kept.md", "flow-and-overflow.md")
    )
    markers = set(re.findall(r"PB-[A-Z][A-Z0-9-]*", specimens))
    expected_markers = {
        "PB-FORCED-AFTER-START",
        "PB-FORCED-AFTER-END",
        "PB-FORCED-BEFORE-START",
        "PB-FORCED-BEFORE-END",
        "PB-KEEP-LEAD",
        "PB-KEEP-START",
        "PB-KEEP-END",
        "PB-HEADING-LEAD",
        "PB-HEADING-TITLE",
        "PB-HEADING-FOLLOWING-CONTENT",
        "PB-FIGURE-LEAD",
        "PB-FIGURE-CAPTION",
        "PB-CODE-FIRST",
        "PB-CODE-LAST",
        "PB-TABLE-HEADER",
        "PB-TABLE-ROW-01",
        "PB-TABLE-ROW-52",
        "PB-NATURAL-FIRST",
        "PB-NATURAL-LAST",
        "PB-ADMONITION-TITLE",
        "PB-ADMONITION-END",
        "PB-TAB-FIRST",
        "PB-TAB-SECOND",
        "PB-GRID-FIRST",
        "PB-GRID-SECOND",
        "PB-FOOTNOTE-REFERENCE",
        "PB-FOOTNOTE-CONTENT",
        "PB-MERMAID-START",
        "PB-MERMAID-END",
        "PB-MATH-VECTOR",
        "PB-LONG-TOKEN-START-CATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUE-PB-LONG-TOKEN-END",
    }
    assert expected_markers <= markers

    stylesheet = (DOCS / "stylesheets" / "page-breaks.css").read_text(encoding="utf-8")
    for rule in (
        "break-before: page",
        "break-after: page",
        "break-inside: avoid",
        "overflow-wrap: anywhere",
    ):
        assert rule in stylesheet


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
