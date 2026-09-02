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
    about = next(item["About"] for item in config["project"]["nav"] if "About" in item)

    assert about == [
        {"38. About prodockit": "about/index.md"},
        {"39. Support and compatibility": "about/support.md"},
        {"40. Known limitations": "about/limitations.md"},
        {"41. Release notes": "about/changelog.md"},
        {"42. Licence": "about/license.md"},
    ]


def test_support_page_centralises_public_compatibility_information() -> None:
    support = _text("docs/about/support.md")
    prose = " ".join(support.split())

    for phrase in (
        "Alpha",
        "Python 3.10",
        "Python 3.14",
        "Zensical 0.0.57",
        "pymdown-extensions 11.0.2",
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


def test_macro_docs_explain_repo_and_release_compatibility_policy() -> None:
    macros = " ".join(_text("docs/macros.md").split())

    for phrase in (
        "Why `repo_url` and `applied_release` remain Prodockit variables",
        "active `origin`",
        "removes embedded CI credentials",
        "prevents a token-bearing clone URL",
        "most recently applied successfully",
        "native `git.short_tag`",
        "cannot describe its template state",
        "stable author-facing interfaces",
        "compatibility alias",
        "Authors will not need to rewrite",
    ):
        assert phrase in macros


def test_release_notes_are_a_website_only_capability_record() -> None:
    changelog = _text("docs/about/changelog.md")
    prose = " ".join(changelog.split())

    for phrase in (
        "pdf_include: false",
        "complete historical record",
        "Implemented functionality",
        "Authoring",
        "Website integration",
        "PDF output",
        "Project setup",
        "Project maintenance",
        "Publishing",
    ):
        assert phrase in prose

    assert "zendoc" not in changelog.lower()


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
