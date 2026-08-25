# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The About section gives evaluators one public source of support information."""

from __future__ import annotations

from pathlib import Path

from prodockit.template_sync import read_config

ROOT = Path(__file__).resolve().parent.parent


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_about_navigation_is_evaluator_first() -> None:
    config = read_config(_text("zensical.toml"))
    about = next(
        item["35. About"] for item in config["project"]["nav"] if "35. About" in item
    )

    assert about == [
        {"35. About prodockit": "about/index.md"},
        {"36. Support and compatibility": "about/support.md"},
        {"37. Known limitations": "about/limitations.md"},
        {"38. Release notes": "about/changelog.md"},
        {"39. Licence": "about/license.md"},
    ]


def test_support_page_centralises_public_compatibility_information() -> None:
    support = _text("docs/about/support.md")
    prose = " ".join(support.split())

    for phrase in (
        "Alpha",
        "Python 3.10",
        "Python 3.14",
        "Zensical 0.0.57",
        "pymdown-extensions 11.0.1",
        "PyMdown Blocks",
        "Linux",
        "macOS",
        "Windows",
    ):
        assert phrase in prose

    assert "## Platforms" not in _text("docs/devcons/limitations.md")


def test_public_limitations_focus_on_symptoms_and_workarounds() -> None:
    limitations = _text("docs/about/limitations.md")

    for phrase in (
        "# Known limitations",
        "What you see",
        "What to do",
        "Contributor internals",
    ):
        assert phrase in limitations

    support = _text("docs/about/support.md")
    assert "about/limitations.md" not in support
    assert "limitations.md" in support


def test_repeated_status_sections_link_to_the_central_page() -> None:
    pages = (
        "docs/extensions/bibliography.md",
        "docs/macros.md",
        "docs/pdf.md",
    )

    for relative_path in pages:
        text = _text(relative_path)
        assert "## Status" not in text
        assert "about/support.md" in text or "support.md" in text


def test_pymdown_blocks_dependency_is_visible_to_evaluators_and_authors() -> None:
    for relative_path in (
        "docs/about/index.md",
        "docs/about/support.md",
        "docs/authoring.md",
    ):
        text = _text(relative_path)
        assert "PyMdown Blocks" in text
        assert "prodockit.steps" in text
        assert "prodockit.tree" in text


def test_release_notes_explain_the_legacy_version_sequence() -> None:
    changelog = _text("docs/about/changelog.md")

    assert "zendoc" in changelog[:1500]
    assert "newest first" in changelog[:1500]


def test_041_notes_cover_the_public_changes_since_040() -> None:
    changelog = _text("docs/about/changelog.md")
    notes = changelog.split("\n## 0.41.0 ", 1)[1].split("\n## ", 1)[0]

    for phrase in (
        'project.markdown_extensions."prodockit.index"',
        "pdf_include_index",
        "PyMdown Blocks",
        ".pdk-bootstrap.toml",
        "nested `index.md`",
        "11pt",
        "pdf-keep-tab-pages",
        "information architecture",
    ):
        assert phrase in notes


def test_042_notes_cover_the_public_changes_since_041() -> None:
    changelog = _text("docs/about/changelog.md")
    notes = changelog.split("\n## 0.42.0 ", 1)[1].split("\n## ", 1)[0]
    prose = " ".join(notes.split())

    for phrase in (
        'shade="off"',
        "numbered menu",
        "forward cross-page references",
        "permalink",
        "pipe table",
        "project.extra.pdf_*",
        "PDF source bundle",
        "prodockit.org",
        "LICENSE.md",
    ):
        assert phrase in prose


def test_licence_page_explains_but_does_not_replace_the_legal_text() -> None:
    licence = _text("docs/about/license.md")

    assert "icon:" in licence
    assert "# Licence" in licence
    assert "plain-language summary" in licence
    assert '--8<-- "LICENSE.md"' in licence


def test_bootstrap_maturity_distinguishes_manual_and_automated_coverage() -> None:
    support = _text("docs/about/support.md")
    bootstrap = _text("docs/devcons/bootstrap.md")
    combined = " ".join((support + bootstrap).split())

    for phrase in (
        "manual end-to-end",
        "Ubuntu",
        "Windows",
        "macOS",
        "gitlab.surrey.ac.uk",
        "github.com",
        "new document repository",
        "existing online repository",
        "not an automated cross-platform regression matrix",
        "full test suite is also run locally on macOS",
    ):
        assert phrase in combined

    assert "none of it has been run on a Windows machine" not in bootstrap
    assert "Only the University of Surrey's GitLab" not in bootstrap
