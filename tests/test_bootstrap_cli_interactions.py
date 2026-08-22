# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Interactive branches in the ``pdk boot --apply`` command loop."""

from pathlib import Path

import pytest
from bootstrap_cli_harness import CliFakeRunner, unreachable
from click.testing import CliRunner

from prodockit.bootstrap import (
    ApplyResult,
    BootstrapConfig,
    CheckResult,
    CommandResult,
    Plan,
    Stage,
    StageReport,
    Status,
    build_context,
    load,
)
from prodockit.bootstrap.model import MACOS
from prodockit.cli import _report_contacts, _verify_until_done, _work_through


def _config() -> BootstrapConfig:
    return BootstrapConfig(
        full_name="Ada Lovelace",
        email="al01234@surrey.ac.uk",
        username="al01234",
        host="gitlab.surrey.ac.uk",
        namespace="comm058-2026",
        project_name="report-al01234",
        project_dir="~/GitLab/report-al01234",
    )


def _context(tmp_path: Path):
    return build_context(
        _config(),
        runner=CliFakeRunner(),
        platform=MACOS,
        home=tmp_path,
        fetch=unreachable,
    )


def _stage(check, plan) -> Stage:  # type: ignore[no-untyped-def]
    return Stage(id="edge", summary="Edge stage", check=check, plan=plan)


def _isolated(call, *, input: str):  # type: ignore[no-untyped-def]
    runner = CliRunner()
    with runner.isolation(input=input) as (out, err, _):
        result = call()
        return result, out.getvalue().decode(), err.getvalue().decode()


def test_choice_path_records_the_answer_to_the_requested_config_file(tmp_path: Path) -> None:
    context = _context(tmp_path)
    path = tmp_path / "chosen.toml"
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "choice needed"),
        lambda context: Plan(
            instructions=["Choose where the starter content comes from."],
            choices=["Keep history", "Reset history", "Use template"],
            confirm="Select 1, 2 or 3",
        ),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))

    _isolated(lambda: _work_through(context, [report], path), input="1\n")

    saved = load(path)
    assert saved.source_url == "comm058-2026/report-al01234"
    assert saved.history == "keep"


def test_declining_an_instruction_only_stage_marks_it_skipped(tmp_path: Path) -> None:
    context = _context(tmp_path)
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "not done"),
        lambda context: Plan(instructions=["Do the browser step."], confirm="Finished?"),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))

    result, output, _ = _isolated(lambda: _work_through(context, [report], None), input="no\n")

    assert result is None
    assert "skipped" in output


def test_instruction_only_stage_can_confirm_without_being_marked_skipped(tmp_path: Path) -> None:
    context = _context(tmp_path)
    checks = iter([CheckResult(Status.MISSING), CheckResult(Status.OK)])
    stage = _stage(
        lambda context: next(checks),
        lambda context: Plan(instructions=["Do the browser step."], confirm="Finished?"),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))

    _, output, _ = _isolated(lambda: _work_through(context, [report], None), input="yes\n")

    assert "confirmed" in output
    assert "skipped" not in output


def test_unverifiable_manual_step_is_taken_on_trust(tmp_path: Path) -> None:
    context = _context(tmp_path)
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "private host", verifiable=False),
        lambda context: Plan(),
    )
    plan = Plan(confirm="Published?")

    result, output, _ = _isolated(lambda: _verify_until_done(context, stage, plan), input="yes\n")

    assert result is True
    assert "taken on trust - private host" in output


def test_manual_step_that_becomes_blocked_does_not_retry_forever(tmp_path: Path) -> None:
    context = _context(tmp_path)
    stage = _stage(
        lambda context: CheckResult(Status.BLOCKED, "waiting for clone"),
        lambda context: Plan(),
    )

    result, output, _ = _isolated(
        lambda: _verify_until_done(context, stage, Plan(confirm="Finished?")),
        input="yes\n",
    )

    assert result is False
    assert "waiting - waiting for clone" in output
    assert "Try again?" not in output


def test_reader_can_decline_a_retry_after_failed_verification(tmp_path: Path) -> None:
    context = _context(tmp_path)
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "still absent"),
        lambda context: Plan(),
    )

    result, output, _ = _isolated(
        lambda: _verify_until_done(context, stage, Plan(confirm="Finished?")),
        input="yes\nn\n",
    )

    assert result is False
    assert "not there yet - still absent" in output


def test_retry_can_later_confirm_the_manual_step(tmp_path: Path) -> None:
    context = _context(tmp_path)
    checks = iter(
        [
            CheckResult(Status.MISSING, "not propagated"),
            CheckResult(Status.OK, "visible"),
        ]
    )
    stage = _stage(lambda context: next(checks), lambda context: Plan())

    result, output, _ = _isolated(
        lambda: _verify_until_done(context, stage, Plan(confirm="Finished?")),
        input="yes\ny\nyes\n",
    )

    assert result is True
    assert "not there yet - not propagated" in output
    assert "confirmed" in output


def test_successful_command_path_reports_done_even_if_sudo_authentication_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "needs command"),
        lambda context: Plan(commands=[["sudo", "true"]], confirm="Run it?"),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.authenticate_sudo", lambda: False)
    monkeypatch.setattr(
        "prodockit.cli.apply_stage",
        lambda context, stage: ApplyResult(
            stage=stage,
            ran=[["sudo", "true"]],
            verified=CheckResult(Status.OK),
        ),
    )

    _, output, error = _isolated(lambda: _work_through(context, [report], None), input="y\n")

    assert "sudo was not accepted" in error
    assert "done" in output


def test_declining_follow_up_after_commands_marks_the_stage_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "follow-up absent"),
        lambda context: Plan(
            commands=[["installer"]],
            follow_up=["Enable the installed integration."],
            confirm="Finished?",
        ),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: False)
    monkeypatch.setattr(
        "prodockit.cli.apply_stage",
        lambda context, stage: ApplyResult(
            stage=stage,
            ran=[["installer"]],
            verified=CheckResult(Status.MISSING, "follow-up absent"),
        ),
    )

    _, output, _ = _isolated(lambda: _work_through(context, [report], None), input="y\nno\n")

    assert "commands ran — one more step" in output
    assert "skipped" in output


def test_follow_up_after_commands_can_confirm_without_being_marked_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    checks = iter([CheckResult(Status.MISSING), CheckResult(Status.OK)])
    stage = _stage(
        lambda context: next(checks),
        lambda context: Plan(
            commands=[["installer"]],
            follow_up=["Enable the installed integration."],
            confirm="Finished?",
        ),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: False)
    monkeypatch.setattr(
        "prodockit.cli.apply_stage",
        lambda context, stage: ApplyResult(
            stage=stage,
            ran=[["installer"]],
            verified=CheckResult(Status.MISSING, "follow-up absent"),
        ),
    )

    _, output, _ = _isolated(lambda: _work_through(context, [report], None), input="y\nyes\n")

    assert "confirmed" in output
    assert "skipped" not in output


def test_contact_report_is_silent_before_any_host_question(tmp_path: Path) -> None:
    context = _context(tmp_path)

    _, output, _ = _isolated(lambda: _report_contacts(context), input="")

    assert output == ""


def test_contact_report_includes_made_and_reused_counts(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assert context.contacts is not None
    context.contacts.made = 2
    context.contacts.reused = 3

    _, output, _ = _isolated(lambda: _report_contacts(context), input="")

    assert "2 connection(s) to gitlab.surrey.ac.uk, 3 reused." in output


def test_cli_fake_runner_handles_an_empty_command_without_crashing() -> None:
    runner = CliFakeRunner()

    result = runner.run([])

    assert result == CommandResult(returncode=127, stderr="not found")
