# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Durable recovery records for the standalone ``pdkboot`` command."""

from __future__ import annotations

import json
from pathlib import Path

from prodockit.bootstrap.recovery import PdkbootRunJournal, pdkboot_report_path


def _journal(tmp_path: Path) -> PdkbootRunJournal:
    config = tmp_path / ".pdkboot.toml"
    return PdkbootRunJournal(
        pdkboot_report_path(config),
        version="0.test",
        config_path=config,
        resume=["pdkboot", "--config", str(config), "--apply"],
        stages=[
            {
                "id": "git",
                "summary": "Git",
                "status": "planned",
                "detail": "missing",
                "action": "INSTALL",
            }
        ],
    )


def test_default_report_name_is_distinct_from_config(tmp_path: Path) -> None:
    config = tmp_path / ".pdkboot.toml"

    assert pdkboot_report_path(config) == tmp_path / ".pdkboot.last-run.json"


def test_journal_records_a_resumable_failed_stage_atomically(tmp_path: Path) -> None:
    journal = _journal(tmp_path)

    journal.stage("git", "running", detail="installing", action="INSTALL")
    journal.stage("git", "failed", detail="package failed", action="INSTALL")
    journal.finish(
        "failed",
        failure={"stage": "git", "returncode": 1, "message": "package failed"},
    )

    saved = json.loads(journal.path.read_text(encoding="utf-8"))
    assert saved["schema"] == 1
    assert saved["status"] == "failed"
    assert saved["current_stage"] == "git"
    assert saved["failure"] == {
        "stage": "git",
        "returncode": 1,
        "message": "package failed",
    }
    assert saved["resume"][-1] == "--apply"
    assert saved["stages"][0]["status"] == "failed"
    assert not list(tmp_path.glob("..pdkboot.last-run.json.*.tmp"))


def test_completed_journal_clears_the_current_stage(tmp_path: Path) -> None:
    journal = _journal(tmp_path)

    journal.stage("git", "running")
    journal.stage("git", "completed")
    journal.finish("completed")

    saved = json.loads(journal.path.read_text(encoding="utf-8"))
    assert saved["status"] == "completed"
    assert saved["current_stage"] is None
    assert saved["stages"][0]["status"] == "completed"


def test_normal_run_with_a_skipped_stage_remains_incomplete(tmp_path: Path) -> None:
    journal = _journal(tmp_path)

    journal.stage("git", "running")
    journal.stage("git", "skipped")

    assert journal.settle() == "incomplete"
    saved = json.loads(journal.path.read_text(encoding="utf-8"))
    assert saved["status"] == "incomplete"
    assert saved["current_stage"] is None


def test_journal_failure_is_reported_without_raising(tmp_path: Path) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("occupied", encoding="utf-8")

    journal = PdkbootRunJournal(
        blocked / "report.json",
        version="0.test",
        config_path=tmp_path / ".pdkboot.toml",
        resume=["pdkboot", "--apply"],
        stages=[],
    )

    assert journal.error is not None
    assert "could not update" in journal.error
