# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Keep Surrey installation tabs free of generic hosting choices."""

from pathlib import Path

from jinja2 import Environment

GETTING_STARTED = Path(__file__).resolve().parent.parent / "docs/getting-started.md"
MANUAL_INSTALL = GETTING_STARTED.with_name("manual-install.md")
CHOOSING_INSTALLATION = GETTING_STARTED.with_name("choosing-installation.md")


def _render(source: Path, *, is_surrey: bool) -> str:
    text = source.read_text(encoding="utf-8")
    text = text.replace("{{ heading_counter_reset(page) }}", "")
    return Environment(autoescape=False).from_string(text).render(is_surrey=is_surrey)


def _publishing_stage(*, is_surrey: bool) -> str:
    rendered = _render(GETTING_STARTED, is_surrey=is_surrey)
    return rendered.split("### Stage 7a —", 1)[1].split("### Stage 7b —", 1)[0]


def test_surrey_publishing_stage_has_only_surrey_gitlab_tabs() -> None:
    stage = _publishing_stage(is_surrey=True)
    assert stage.count('=== ":fontawesome-brands-gitlab: Surrey GitLab"') == 2
    assert '=== "GitHub"' not in stage
    assert '=== "GitLab"' not in stage
    assert "Surrey Login" in stage
    assert "gitlab.surrey.ac.uk" in stage


def test_public_publishing_stage_keeps_both_host_choices() -> None:
    stage = _publishing_stage(is_surrey=False)
    assert stage.count('=== "GitHub"') == 2
    assert stage.count('=== "GitLab"') == 2
    assert '=== ":fontawesome-brands-gitlab: Surrey GitLab"' not in stage
    assert "Surrey Login" not in stage


def test_route_overview_names_the_rendered_host() -> None:
    surrey = _render(GETTING_STARTED, is_surrey=True)
    public = _render(GETTING_STARTED, is_surrey=False)
    assert "files and publish through Surrey GitLab Pages." in surrey
    assert "files and publish through GitHub or GitLab Pages." not in surrey
    assert "files and publish through GitHub or GitLab Pages." in public


def test_surrey_review_and_manual_install_have_one_host_tab_per_group() -> None:
    review = _render(GETTING_STARTED, is_surrey=True).split("### Stage 7b —", 1)[1]
    manual = _render(MANUAL_INSTALL, is_surrey=True)
    assert review.count('=== ":fontawesome-brands-gitlab: Surrey GitLab"') == 1
    assert manual.count('=== ":fontawesome-brands-gitlab: Surrey GitLab"') == 4
    for content in (review, manual):
        assert '=== "GitHub"' not in content
        assert '=== "GitLab"' not in content
        assert '=== "GitLab.com"' not in content
    assert '=== ":fontawesome-brands-github: GitHub"' not in review


def test_public_review_and_manual_install_keep_host_choices() -> None:
    review = _render(GETTING_STARTED, is_surrey=False).split("### Stage 7b —", 1)[1]
    manual = _render(MANUAL_INSTALL, is_surrey=False)
    assert '=== ":fontawesome-brands-github: GitHub"' in review
    assert '=== ":fontawesome-brands-gitlab: GitLab"' in review
    assert manual.count('=== "GitHub"') == 4
    assert manual.count('=== "GitLab"') == 2
    assert manual.count('=== "GitLab.com"') == 2
    assert '=== ":fontawesome-brands-gitlab: Surrey GitLab"' not in manual


def test_prepared_coursework_repo_guidance_is_surrey_only() -> None:
    link = "[section 5 — Build a template site](devcons/bootstrap.md)"
    assert link in _render(CHOOSING_INSTALLATION, is_surrey=True)
    assert link not in _render(CHOOSING_INSTALLATION, is_surrey=False)
