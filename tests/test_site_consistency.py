# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Regression checks for beginner routing and consistent public documentation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped, unused-ignore]
from click.testing import CliRunner

from prodockit.cli import main
from prodockit.template_sync import read_config

ROOT = Path(__file__).resolve().parent.parent


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _nav() -> list[Any]:
    return read_config(_text("zensical.toml"))["project"]["nav"]


def _paths(items: list[Any]) -> list[str]:
    paths: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = next(iter(item.values()))
        if isinstance(value, list):
            paths.extend(_paths(value))
        else:
            paths.append(value)
    return paths


def _labelled_paths(items: list[Any]) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label, value = next(iter(item.items()))
        if isinstance(value, list):
            paths.extend(_labelled_paths(value))
        else:
            paths.append((label, value))
    return paths


def test_every_navigated_page_except_home_has_an_icon() -> None:
    for relative_path in _paths(_nav()):
        if relative_path == "index.md":
            continue
        text = _text(f"docs/{relative_path}")
        parts = text.split("---", 2)
        assert len(parts) == 3 and not parts[0], relative_path
        metadata = yaml.safe_load(parts[1])
        assert isinstance(metadata, dict), relative_path
        icon = metadata.get("icon")
        assert isinstance(icon, str) and icon.strip(), relative_path


def test_home_page_hero_title_is_not_numbered() -> None:
    home = _text("docs/index.md")

    assert '{: .cover-hero-title .unnumbered }' in home


def test_every_navigated_page_resets_its_heading_counter_from_nav() -> None:
    macro = "{{ heading_counter_reset(page) }}"

    for relative_path in _paths(_nav()):
        text = _text(f"docs/{relative_path}")
        body = text.split("---", 2)[2]
        assert body.startswith(f"\n\n{macro}\n\n"), relative_path
        assert re.findall(rf"^{re.escape(macro)}$", text, re.MULTILINE) == [macro], relative_path


def test_nav_page_labels_follow_continuous_heading_numbers() -> None:
    labelled_paths = _labelled_paths(_nav())
    top_level_labels = [next(iter(item)) for item in _nav() if isinstance(item, dict)]

    assert labelled_paths[0] == ("Home", "index.md")
    for number, (label, _relative_path) in enumerate(labelled_paths[1:], 1):
        assert label.startswith(f"{number}. "), label
    assert "About" in top_level_labels
    assert not any(re.match(r"^\d+\. ", label) for label in top_level_labels)


def test_reference_site_enables_website_heading_numbering() -> None:
    config = read_config(_text("zensical.toml"))["project"]

    assert config["extra"]["heading_numbering"] is True
    assert config["extra"]["website_heading_numbering"] is True
    assert config["extra_css"] == ["stylesheets/pdk.css", "stylesheets/extra.css"]
    assert config["extra"]["pdf_extra_css"] == [
        "stylesheets/pdk-pdf.css",
        "stylesheets/print.css",
    ]
    assert "config.extra.website_heading_numbering == false" in _text("overrides/main.html")


def test_reference_site_fails_when_a_macro_cannot_render() -> None:
    config = read_config(_text("zensical.toml"))["project"]
    macros = config["markdown_extensions"]["zensical"]["extensions"]["macros"]

    assert macros["on_error_fail"] is True
    guide = _text("docs/macros.md")
    assert guide.count("on_error_fail = true") == 3
    assert "allowing a broken site to be published" in guide


def test_get_started_routes_authors_to_authoring_and_publishing() -> None:
    introduction = _text("docs/introduction.md")

    assert "Start with the [maintenance cycle]" not in introduction
    assert "[Authoring reference](authoring.md)" in introduction
    assert "[Publish a document](publishing.md)" in introduction


def test_introduction_offers_an_optional_tracking_free_support_link() -> None:
    introduction = _text("docs/introduction.md")

    assert "## Support prodockit" in introduction
    assert "https://buymeacoffee.com/buckwem" in introduction
    assert "software and online services used to" in introduction
    assert "develop, test, and publish prodockit" in introduction
    assert ".md-button .md-button--primary" in introduction
    assert "<script" not in introduction
    assert "cdn.buymeacoffee.com" not in introduction


def test_public_documentation_links_use_the_custom_domain() -> None:
    for relative_path in (
        "README.md",
        "pyproject.toml",
        "zensical.toml",
        "src/prodockit/__init__.py",
        "docs/pdf.md",
        "overrides/partials/copyright.html",
    ):
        text = _text(relative_path)
        assert "https://prodockit.org/" in text, relative_path
        assert "https://buckwem.github.io/prodockit-extensions/" not in text, relative_path


def test_command_line_reference_is_for_document_authors() -> None:
    nav = _nav()
    authoring = next(item["Authoring reference"] for item in nav if "Authoring reference" in item)
    maintenance = next(item["Maintain prodockit"] for item in nav if "Maintain prodockit" in item)

    assert {"19. Command-line reference": "command-line.md"} in authoring
    assert all("command-line.md" not in item.values() for item in maintenance)
    assert "document authors" in _text("docs/command-line.md")


def test_bootstrap_documents_current_hosts_and_local_config() -> None:
    guide = _text("docs/devcons/bootstrap.md")

    assert "github.com is declared but not yet supported" not in guide
    assert "currently implements gitlab.surrey.ac.uk only" not in guide
    for phrase in ("gitlab.surrey.ac.uk", "github.com", "gitlab.com", ".pdk-bootstrap.toml", "--config"):
        assert phrase in guide


def test_bootstrap_config_help_describes_the_real_default() -> None:
    result = CliRunner().invoke(main, ["bootstrap", "--help"])

    assert result.exit_code == 0
    assert ".pdk-bootstrap.toml" in result.output
    assert "user config directory" not in result.output


def test_authoring_navigation_uses_consistent_sentence_case() -> None:
    authoring = next(item["Authoring reference"] for item in _nav() if "Authoring reference" in item)
    labels = [re.sub(r"^\d+\. ", "", next(iter(item))) for item in authoring]

    assert labels == [
        "Overview",
        "Headings",
        "Cross-references",
        "Hand-written citations and references",
        "Acronyms and glossary",
        "Tables",
        "Directory trees",
        "Numbered steps",
        "BibTeX bibliography",
        "Index (PDF only)",
        "Website macros",
        "Generate a PDF",
        "Command-line reference",
        "Stylesheets",
    ]


def test_ci_page_does_not_present_maintainer_topics_to_authors() -> None:
    guide = _text("docs/devcons/continuous-integration.md")

    assert "## Maintainer topics live under Maintain prodockit" not in guide
    for anchor in ("ci-release-numbering", "ci-pandoc-version", "ci-gitlab-ci"):
        assert f'id="{anchor}"' in guide


def test_advanced_authoring_sections_include_markdown_and_result() -> None:
    required_sections = {
        "docs/extensions/steps.md": ("Continue numbering after a break", "Add an id or other HTML attributes"),
        "docs/extensions/tree.md": ("Configure indentation and icons",),
        "docs/extensions/citations.md": ("Cite a source before its full reference", "Fix a missing citation"),
        "docs/extensions/glossary.md": ("Use a term before its definition", "Fix a missing term", "Keep acronyms and glossary terms on separate pages"),
        "docs/extensions/tables.md": ("Use more than one header row", "Merge cells", "Rotate headings"),
        "docs/extensions/headings.md": ("Number appendices", "Leave a heading unnumbered"),
    }

    for relative_path, headings in required_sections.items():
        text = _text(relative_path)
        for heading in headings:
            match = re.search(
                rf"^###? {re.escape(heading)}[^\n]*\n(?P<body>.*?)(?=^## |^### |\Z)",
                text,
                re.MULTILINE | re.DOTALL,
            )
            assert match is not None, f"{relative_path}: missing section {heading!r}"
            body = match.group("body")
            assert '"Markdown"' in body, f"{relative_path}: {heading!r} has no Markdown example"
            assert '"Result"' in body, f"{relative_path}: {heading!r} has no rendered result"
