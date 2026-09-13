# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Keep the first Surrey installation preview free of generic host choices."""

from pathlib import Path

from jinja2 import Environment


GETTING_STARTED = Path(__file__).resolve().parent.parent / "docs/getting-started.md"


def _publishing_stage(*, is_surrey: bool) -> str:
    source = GETTING_STARTED.read_text(encoding="utf-8")
    stage = source.split("### Stage 7a —", 1)[1].split("### Stage 7b —", 1)[0]
    return Environment(autoescape=False).from_string(stage).render(is_surrey=is_surrey)


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
