# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from prodockit.adopt import Step
from prodockit.cli import _adopt_blocker_summary, _adopt_change_summary


def render(step, verbose=False, color=False):
    @click.command()
    def command():
        _adopt_change_summary(step, verbose=verbose)

    return CliRunner().invoke(command, color=color).output


@pytest.mark.parametrize(
    "activity", ["core", "choices", "pdf-runtime", "node", "mermaid", "maths", "csl"]
)
def test_changes_explain_purpose_and_hide_only_technical_evidence(activity):
    step = Step(
        activity,
        "Integrate",
        "Test",
        "missing",
        "technical probe evidence",
        commands=(("installer", "--internal-option"),),
        files=(Path("internal/file"),),
    )
    normal = render(step)
    verbose = render(step, verbose=True)
    assert "Why:" in normal and "Change:" in normal
    assert "Command:" not in normal and "File:" not in normal
    assert "Command:  installer --internal-option" in verbose
    assert "File:     internal/file" in verbose
    assert "technical probe evidence" in verbose
    assert "\x1b[" not in normal
    assert "\x1b[" in render(step, color=True)


def test_dependency_versions_and_downgrade_warning_stay_visible():
    step = Step(
        "dependency",
        "Integrate",
        "Software",
        "missing",
        "Pandoc 3.10.2 -> 3.10.1",
        commands=(("installer",),),
    )
    output = render(step)
    assert "Pandoc 3.10.2 -> 3.10.1" in output
    assert "upgraded or downgraded" in output


def test_declaration_only_change_does_not_claim_software_install():
    step = Step("dependency", "Integrate", "Software", "missing", "align requirements.txt")
    assert "no software installation is needed" in render(step)


def test_browser_blocker_does_not_recommend_node_installation():
    @click.command()
    def command():
        _adopt_blocker_summary(
            [
                Step(
                    "mermaid",
                    "Optional renderers",
                    "Diagrams",
                    "wrong",
                    "Browser path is missing; correct that path before retrying",
                )
            ]
        )

    result = CliRunner().invoke(command)
    assert "Browser path is missing" in result.output
    assert "rerun `pdk adopt`" in result.output
    assert "brew install node" not in result.output
    assert "winget install" not in result.output


def test_wrong_state_never_promises_to_apply_a_change():
    step = Step("core", "Integrate", "Config", "wrong", "Invalid configuration; fix line 3")
    output = render(step)
    assert "Problem:" in output and "Next:" in output
    assert "fix line 3" in output
    assert "Change:" not in output
