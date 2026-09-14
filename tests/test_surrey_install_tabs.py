# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Keep Surrey installation tabs free of generic hosting choices."""

import re
from pathlib import Path

from jinja2 import Environment

GETTING_STARTED = Path(__file__).resolve().parent.parent / "docs/getting-started.md"
MANUAL_INSTALL = GETTING_STARTED.with_name("manual-install.md")
CHOOSING_INSTALLATION = GETTING_STARTED.with_name("choosing-installation.md")
BOOTSTRAP = GETTING_STARTED.parent / "devcons/bootstrap.md"
TROUBLESHOOTING = GETTING_STARTED.with_name("troubleshooting-installs.md")


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


def test_surrey_pages_setup_is_a_numbered_checklist() -> None:
    stage = _publishing_stage(is_surrey=True)
    step = stage.split("//// step | Enable repo for Pages", 1)[1].split("\n////", 1)[0]
    assert re.findall(r"^    (\d+)\. ", step, re.MULTILINE) == ["1", "2", "3", "4", "5"]
    assert "**Settings > General**" in step
    assert "**Pages** is" in step
    assert "`.gitlab-ci.yml`" in step
    assert "`.gitlab-pdk.yml`" in step
    assert "GitLab publishing workflow setup" in step


def test_public_publishing_stage_keeps_both_host_choices() -> None:
    stage = _publishing_stage(is_surrey=False)
    assert stage.count('=== ":fontawesome-brands-github: GitHub"') == 2
    assert stage.count('=== ":fontawesome-brands-gitlab: GitLab"') == 2
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


def test_surrey_manual_install_uses_only_surrey_for_repository_guidance() -> None:
    manual = _render(MANUAL_INSTALL, is_surrey=True)
    assert "GitHub" not in manual
    assert "gitlab.com" not in manual
    assert "Host gitlab.surrey.ac.uk" in manual
    assert "Open [Surrey GitLab](https://gitlab.surrey.ac.uk)" in manual


def test_troubleshooting_host_guidance_matches_the_selected_site() -> None:
    surrey = _render(TROUBLESHOOTING, is_surrey=True)
    public = _render(TROUBLESHOOTING, is_surrey=False)
    assert "GitHub" not in surrey
    assert "GitLab.com" not in surrey
    assert "Check the connection to Surrey GitLab" in surrey
    assert "Check the connection to GitLab or GitHub" in public


def test_public_review_and_manual_install_keep_host_choices() -> None:
    review = _render(GETTING_STARTED, is_surrey=False).split("### Stage 7b —", 1)[1]
    manual = _render(MANUAL_INSTALL, is_surrey=False)
    assert '=== ":fontawesome-brands-github: GitHub"' in review
    assert '=== ":fontawesome-brands-gitlab: GitLab"' in review
    assert manual.count('=== ":fontawesome-brands-github: GitHub"') == 4
    assert manual.count('=== ":fontawesome-brands-gitlab: GitLab"') == 2
    assert manual.count('=== ":fontawesome-brands-gitlab: GitLab.com"') == 2
    assert '=== ":fontawesome-brands-gitlab: Surrey GitLab"' not in manual


def test_prepared_coursework_repo_guidance_is_surrey_only() -> None:
    link = "[section 5 — Build a template site](devcons/bootstrap.md)"
    assert link in _render(CHOOSING_INSTALLATION, is_surrey=True)
    assert link not in _render(CHOOSING_INSTALLATION, is_surrey=False)


def test_bootstrap_uses_only_the_selected_host_and_surrey_links_open_new_tabs() -> None:
    surrey = _render(BOOTSTRAP, is_surrey=True)
    public = _render(BOOTSTRAP, is_surrey=False)

    assert "GitHub" not in surrey
    assert "GitLab.com" not in surrey
    assert "gitlab.surrey.ac.uk" in surrey
    assert surrey.count("Surrey GitLab") == 3
    surrey_links = re.findall(
        r'\[Surrey GitLab(?: repository)?\]\(https://gitlab\.surrey\.ac\.uk'
        r'(?:/mb0105/prodockit-template)?\)\{target="_blank" rel="noopener"\}',
        surrey,
    )
    assert len(surrey_links) == 3

    assert "Surrey" not in public
    assert "gitlab.surrey.ac.uk" not in public
    assert "GitHub.com or GitLab.com" in public
