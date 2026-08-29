# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Interactive branches in the ``pdk boot --apply`` command loop."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from prodockit.bootstrap import (
    STAGES,
    ApplyResult,
    BootstrapConfig,
    CheckResult,
    CommandResult,
    Plan,
    Stage,
    StageReport,
    Status,
    apply_stage,
    build_context,
    load,
)
from prodockit.bootstrap.model import MACOS
from prodockit.cli import (
    _announce_apply,
    _apply_outstanding,
    _pdkboot_phase,
    _pdkboot_stages,
    _report_contacts,
    _verify_until_done,
    _work_through,
)

from .harness import CliFakeRunner, unreachable


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
        pdkboot=True,
    )


def _stage(check, plan) -> Stage:  # type: ignore[no-untyped-def]
    return Stage(id="edge", summary="Edge stage", check=check, plan=plan)


def test_pdkboot_profile_is_passed_while_the_command_context_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Windows SSH choice lives in the runner built with the context.

    Marking a completed context as pdkboot afterwards changes its display
    profile but cannot reconstruct its runner. That made Windows' ``ssh -T``
    authenticate while Git's repository probes used another SSH client and
    failed with ``Permission denied (publickey)``.
    """
    from prodockit.pdkboot import main

    received: list[bool] = []

    def build(config, *, pdkboot=False):  # type: ignore[no-untyped-def]
        received.append(pdkboot)
        return build_context(
            config,
            runner=CliFakeRunner(),
            platform=MACOS,
            home=tmp_path,
            fetch=unreachable,
            pdkboot=pdkboot,
        )

    monkeypatch.setattr("prodockit.cli.load_bootstrap_config", lambda path: _config())
    monkeypatch.setattr("prodockit.cli.build_bootstrap_context", build)
    monkeypatch.setattr("prodockit.cli.check_all", lambda context, stages: [])

    result = CliRunner().invoke(main, ["--check", "--config", str(tmp_path / "pdk.toml")])

    assert result.exit_code == 0, result.output
    assert received == [True]


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


def test_browser_confirmed_site_is_remembered_for_the_next_check(tmp_path: Path) -> None:
    context = _context(tmp_path)
    stage = next(stage for stage in STAGES if stage.id == "site")
    config_path = tmp_path / ".pdkboot.toml"

    result, output, _ = _isolated(
        lambda: _verify_until_done(
            context,
            stage,
            stage.plan(context),
            config_path,
        ),
        input="yes\n",
    )

    assert result is True
    assert "taken on trust" in output
    saved = load(config_path)
    assert saved.confirmed_site_url.endswith("/report-al01234/")

    checked_again = stage.check(
        build_context(
            saved,
            runner=CliFakeRunner(),
            platform=MACOS,
            home=tmp_path,
            fetch=unreachable,
            pdkboot=True,
        )
    )
    assert checked_again.status is Status.OK
    assert "confirmed in your browser" in checked_again.detail


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


def test_project_environment_becoming_blocked_is_not_offered_for_apply(
    tmp_path: Path,
) -> None:
    """The apply pass rechecks after earlier stages and must honour a missing clone (#610)."""
    context = _context(tmp_path)
    stage = next(stage for stage in STAGES if stage.id == "project-env")
    stale = StageReport(
        stage,
        CheckResult(Status.MISSING, "no project directory yet"),
        stage.plan(context),
    )

    _, output, _ = _isolated(
        lambda: _work_through(context, [stale], None),
        input="",
    )

    assert "WAIT" in output
    assert "no project directory yet" in output
    assert "Run 2 commands?" not in output
    assert "Working directory:" not in output


def test_apply_view_distinguishes_blocked_from_unknown_stages(tmp_path: Path) -> None:
    context = _context(tmp_path)
    blocked = _stage(
        lambda context: CheckResult(Status.BLOCKED, "waiting for clone"),
        lambda context: Plan(),
    )
    unknown = Stage(
        id="unknown",
        summary="Unknown stage",
        check=lambda context: CheckResult(Status.UNKNOWN, "could not inspect"),
        plan=lambda context: Plan(),
    )

    _, output, _ = _isolated(
        lambda: _work_through(
            context,
            [
                StageReport(blocked, CheckResult(Status.BLOCKED), None),
                StageReport(unknown, CheckResult(Status.UNKNOWN), None),
            ],
            None,
        ),
        input="",
    )

    assert "WAIT  Edge stage - waiting for clone" in output
    assert "?     Unknown stage - could not inspect" in output


def test_apply_groups_real_stages_into_named_phases(tmp_path: Path) -> None:
    context = _context(tmp_path)
    git = Stage(
        id="git",
        summary="Git",
        check=lambda context: CheckResult(Status.OK, "ready"),
        plan=lambda context: Plan(),
    )
    ssh = Stage(
        id="ssh-key",
        summary="SSH key",
        check=lambda context: CheckResult(Status.OK, "ready"),
        plan=lambda context: Plan(),
    )

    _, output, _ = _isolated(
        lambda: _work_through(
            context,
            [
                StageReport(git, CheckResult(Status.OK), None),
                StageReport(ssh, CheckResult(Status.OK), None),
            ],
            None,
        ),
        input="",
    )

    assert "Phase 2/7 — Core tools" in output
    assert "Phase 3/7 — Git and host" in output
    assert output.count("═" * 40) == 4, "each phase has a double-line top and bottom"


def test_every_real_stage_has_one_forward_moving_phase() -> None:
    phases = [_pdkboot_phase(stage.id) for stage in _pdkboot_stages()]

    assert all(phase is not None for phase in phases)
    numbers = [phase[0] for phase in phases if phase is not None]
    assert numbers == sorted(numbers)
    assert set(numbers) == set(range(1, 8))


def test_pdkboot_creates_the_host_project_before_choosing_and_cloning() -> None:
    """A newly created empty repository becomes usable in the same run."""
    pdkboot_ids = [stage.id for stage in _pdkboot_stages()]
    legacy_ids = [stage.id for stage in STAGES]

    assert pdkboot_ids.index("ssh-upload") < pdkboot_ids.index("own-project")
    assert pdkboot_ids.index("own-project") < pdkboot_ids.index("clone-source")
    assert pdkboot_ids.index("clone-source") < pdkboot_ids.index("clone")
    assert pdkboot_ids.index("clone") < pdkboot_ids.index("fresh-history")
    assert legacy_ids.index("clone") < legacy_ids.index("own-project"), (
        "the existing prodockit bootstrap order remains unchanged"
    )
    assert {stage.id for stage in _pdkboot_stages()} == {stage.id for stage in STAGES}


def test_active_stage_shows_action_current_state_and_goal(tmp_path: Path) -> None:
    context = _context(tmp_path)
    stage = Stage(
        id="git",
        summary="Git, installed and configured",
        check=lambda context: CheckResult(Status.WRONG, "email is not configured"),
        plan=lambda context: Plan(commands=[["git", "config", "user.email", "ada@example.test"]]),
    )
    report = StageReport(stage, CheckResult(Status.WRONG), stage.plan(context))

    _, output, _ = _isolated(
        lambda: _work_through(context, [report], None),
        input="n\n",
    )

    assert "Action:   CONFIGURE" in output
    assert "Current:  email is not configured" in output
    assert "Goal:     Git, installed and configured" in output
    assert "Stage [1/1] Git, installed and configured" in output
    assert "─" * 40 in output, "the stage has a visible boundary in plain logs"


def test_apply_announcement_summarises_kinds_of_work(tmp_path: Path) -> None:
    context = _context(tmp_path)
    stages = [
        Stage(
            id="node",
            summary="Node",
            check=lambda context: CheckResult(Status.MISSING),
            plan=lambda context: Plan(commands=[["install-node"]]),
        ),
        Stage(
            id="identity",
            summary="Identity",
            check=lambda context: CheckResult(Status.WRONG),
            plan=lambda context: Plan(commands=[["configure-git"]]),
        ),
        Stage(
            id="site",
            summary="Site",
            check=lambda context: CheckResult(Status.MISSING),
            plan=lambda context: Plan(instructions=["Publish it"]),
        ),
    ]
    reports = [
        StageReport(stage, stage.check(context), stage.plan(context)) for stage in stages
    ]

    _, output, _ = _isolated(
        lambda: _announce_apply(context, len(reports), reports),
        input="",
    )

    assert "Work:     1 install · 1 configure · 1 manual" in output


def test_pdkboot_captures_routine_output_but_retains_failure_details(tmp_path: Path) -> None:
    runner = CliFakeRunner(
        {"installer": CommandResult(1, stdout="download context", stderr="package failed")}
    )
    context = build_context(
        _config(),
        runner=runner,
        platform=MACOS,
        home=tmp_path,
        fetch=unreachable,
        pdkboot=True,
    )
    stage = _stage(
        lambda context: CheckResult(Status.MISSING),
        lambda context: Plan(commands=[["installer"]]),
    )

    outcome = apply_stage(
        context,
        stage,
        stage.plan(context),
        progress=lambda event, number, total, command: None,
    )

    assert runner.captures == [True]
    assert outcome.failed == CommandResult(
        1, stdout="download context", stderr="package failed"
    )


def test_pdkboot_prints_captured_output_when_a_command_fails(tmp_path: Path) -> None:
    runner = CliFakeRunner(
        {"installer": CommandResult(1, stdout="download context", stderr="package failed")}
    )
    context = build_context(
        _config(),
        runner=runner,
        platform=MACOS,
        home=tmp_path,
        fetch=unreachable,
        pdkboot=True,
    )
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "not installed"),
        lambda context: Plan(commands=[["installer"]]),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))

    click_runner = CliRunner()
    with click_runner.isolation(input="y\n") as (output, error, _):
        with pytest.raises(SystemExit):
            _work_through(context, [report], None)
        stdout = output.getvalue().decode()
        stderr = error.getvalue().decode()

    assert "Working on command 1/1: installer" in stdout
    assert "download context" in stderr
    assert "package failed" in stderr


def test_terminal_command_keeps_direct_terminal_access(tmp_path: Path) -> None:
    runner = CliFakeRunner({"ssh-add": CommandResult(0)})
    context = build_context(
        _config(),
        runner=runner,
        platform=MACOS,
        home=tmp_path,
        fetch=unreachable,
        pdkboot=True,
    )
    stage = _stage(
        lambda context: CheckResult(Status.OK),
        lambda context: Plan(commands=[["ssh-add"]], needs_terminal=True),
    )

    apply_stage(context, stage, stage.plan(context))

    assert runner.captures == [False]


def test_apply_records_skipped_work_and_exact_resume_command(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (tmp_path / ".git").mkdir()
    config_path = tmp_path / "manual test.toml"
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "not installed"),
        lambda context: Plan(commands=[["installer"]]),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))

    _, output, _ = _isolated(
        lambda: _apply_outstanding(context, [report], config_path),
        input="n\n",
    )

    report_path = tmp_path / "manual test.last-run.json"
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["status"] == "incomplete"
    assert saved["stages"][0]["status"] == "skipped"
    assert saved["resume"] == [
        "pdkboot",
        "--config",
        str(config_path),
        "--apply",
    ]
    assert f"Recovery report: {report_path}" in output
    ignored = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert report_path.name in ignored.splitlines()
    assert "recovery state" in ignored


def test_apply_failure_records_stage_exit_status_and_message(tmp_path: Path) -> None:
    runner = CliFakeRunner({"installer": CommandResult(23, stderr="repository unavailable")})
    context = build_context(
        _config(),
        runner=runner,
        platform=MACOS,
        home=tmp_path,
        fetch=unreachable,
        pdkboot=True,
    )
    config_path = tmp_path / ".pdkboot.toml"
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "not installed"),
        lambda context: Plan(commands=[["installer"]]),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))

    runner_cli = CliRunner()
    with runner_cli.isolation(input="y\n") as (output, error, _):
        with pytest.raises(SystemExit):
            _apply_outstanding(context, [report], config_path)
        rendered = output.getvalue().decode() + error.getvalue().decode()

    saved = json.loads(
        (tmp_path / ".pdkboot.last-run.json").read_text(encoding="utf-8")
    )
    assert saved["status"] == "failed"
    assert saved["failure"] == {
        "stage": "edge",
        "returncode": 23,
        "message": "repository unavailable",
        "category": "unclassified",
        "recovery": [
            "Review the command output above and correct the reported condition.",
            "Resume pdkboot; completed stages will be checked and skipped.",
        ],
    }
    assert saved["stages"][0]["status"] == "failed"
    assert "Recovery:" in rendered
    assert "Review the command output" in rendered


def test_interrupted_apply_records_where_to_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    config_path = tmp_path / ".pdkboot.toml"
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "not installed"),
        lambda context: Plan(commands=[["installer"]]),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))

    def interrupt(context, reports, config_path, journal):  # type: ignore[no-untyped-def]
        journal.stage("edge", "running", action="INSTALL")
        raise KeyboardInterrupt

    monkeypatch.setattr("prodockit.cli._work_through", interrupt)
    runner_cli = CliRunner()
    with runner_cli.isolation(input=""), pytest.raises(KeyboardInterrupt):
        _apply_outstanding(context, [report], config_path)

    saved = json.loads(
        (tmp_path / ".pdkboot.last-run.json").read_text(encoding="utf-8")
    )
    assert saved["status"] == "interrupted"
    assert saved["current_stage"] == "edge"
    assert saved["failure"] == {
        "stage": "edge",
        "message": "run interrupted by the user",
    }


def test_failed_installer_can_recover_when_the_stage_now_verifies(tmp_path: Path) -> None:
    runner = CliFakeRunner(
        {"installer": CommandResult(1603, stderr="installer reported a final error")}
    )
    context = build_context(
        _config(),
        runner=runner,
        platform=MACOS,
        home=tmp_path,
        fetch=unreachable,
        pdkboot=True,
    )
    checks = iter(
        [
            CheckResult(Status.MISSING, "not installed"),
            CheckResult(Status.OK, "installed despite the exit code"),
        ]
    )
    stage = _stage(
        lambda context: next(checks),
        lambda context: Plan(commands=[["installer"]]),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))
    config_path = tmp_path / ".pdkboot.toml"

    _, output, error = _isolated(
        lambda: _apply_outstanding(context, [report], config_path),
        input="y\n",
    )

    assert "recovered: command returned 1603" in output
    assert "installer reported a final error" in output
    assert error == ""
    saved = json.loads(
        (tmp_path / ".pdkboot.last-run.json").read_text(encoding="utf-8")
    )
    assert saved["status"] == "completed"
    assert saved["stages"][0]["status"] == "completed"
    assert "stage now verifies correctly" in saved["stages"][0]["detail"]


def test_failed_installer_still_stops_when_the_stage_is_partial(tmp_path: Path) -> None:
    runner = CliFakeRunner({"installer": CommandResult(1, stderr="partial install")})
    context = build_context(
        _config(),
        runner=runner,
        platform=MACOS,
        home=tmp_path,
        fetch=unreachable,
        pdkboot=True,
    )
    stage = _stage(
        lambda context: CheckResult(Status.WRONG, "only part is present"),
        lambda context: Plan(commands=[["installer"]]),
    )

    outcome = apply_stage(
        context,
        stage,
        stage.plan(context),
        progress=lambda event, number, total, command: None,
    )

    assert outcome.ok is False
    assert outcome.failed == CommandResult(1, stderr="partial install")
    assert outcome.recovered is None


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
        lambda context, stage, plan, **kwargs: ApplyResult(
            stage=stage,
            ran=[["sudo", "true"]],
            verified=CheckResult(Status.OK),
        ),
    )

    _, output, error = _isolated(lambda: _work_through(context, [report], None), input="y\n")

    assert "sudo was not accepted" in error
    assert "done" in output


def test_command_path_executes_the_exact_plan_the_reader_approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    planned: list[Plan] = []

    def make_plan(context) -> Plan:  # type: ignore[no-untyped-def]
        plan = Plan(commands=[["installer", str(len(planned) + 1)]])
        planned.append(plan)
        return plan

    stage = _stage(lambda context: CheckResult(Status.MISSING, "needs command"), make_plan)
    report = StageReport(stage, CheckResult(Status.MISSING), None)
    approved: list[Plan] = []
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: False)
    monkeypatch.setattr(
        "prodockit.cli.apply_stage",
        lambda context, stage, plan, **kwargs: approved.append(plan)
        or ApplyResult(stage=stage, verified=CheckResult(Status.OK)),
    )

    _isolated(lambda: _work_through(context, [report], None), input="y\n")

    assert len(planned) == 1
    assert approved == planned


@pytest.mark.parametrize("command_failed", [True, False])
def test_a_failed_stage_explains_how_to_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command_failed: bool,
) -> None:
    context = _context(tmp_path)
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "still missing"),
        lambda context: Plan(commands=[["installer"]]),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), None)
    failed = CommandResult(1, stderr="installer failed") if command_failed else None
    verified = None if command_failed else CheckResult(Status.MISSING, "still missing")
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: False)
    monkeypatch.setattr(
        "prodockit.cli.apply_stage",
        lambda context, stage, plan, **kwargs: ApplyResult(
            stage=stage,
            failed=failed,
            verified=verified,
        ),
    )

    runner = CliRunner()
    with runner.isolation(input="y\n") as (_, error, _):
        with pytest.raises(SystemExit):
            _work_through(context, [report], None)
        stderr = error.getvalue().decode()

    assert "pdkboot --apply" in stderr
    assert "completed stages will be rechecked and skipped" in stderr


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
        lambda context, stage, plan, **kwargs: ApplyResult(
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
        lambda context, stage, plan, **kwargs: ApplyResult(
            stage=stage,
            ran=[["installer"]],
            verified=CheckResult(Status.MISSING, "follow-up absent"),
        ),
    )

    _, output, _ = _isolated(lambda: _work_through(context, [report], None), input="y\nyes\n")

    assert "confirmed" in output
    assert "skipped" not in output


def test_successful_installer_still_shows_and_confirms_its_follow_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    monkeypatch.setattr(
        "prodockit.cli.apply_stage",
        lambda context, stage, plan, **kwargs: ApplyResult(
            stage=stage,
            ran=[["installer"]],
            verified=CheckResult(Status.OK),
        ),
    )

    _, output, _ = _isolated(
        lambda: _work_through(context, [report], None), input="y\nyes\n"
    )

    assert "commands ran — one more step" in output
    assert "Enable the installed integration." in output
    assert "confirmed" in output


def test_instructions_and_commands_have_one_approval_prompt(tmp_path: Path) -> None:
    context = _context(tmp_path)
    stage = _stage(
        lambda context: CheckResult(Status.MISSING, "not installed"),
        lambda context: Plan(
            commands=[["installer"]],
            instructions=["Choose a passphrase when asked."],
            confirm="Ready to install?",
        ),
    )
    report = StageReport(stage, CheckResult(Status.MISSING), stage.plan(context))

    _, output, _ = _isolated(
        lambda: _work_through(context, [report], None), input="n\n"
    )

    assert output.count("Ready to install?") == 1
    assert "Run 1 command?" not in output
    assert output.index("Will run:") < output.index("Ready to install?")


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
