# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Durable recovery records for the standalone ``pdkboot`` command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prodockit.bootstrap import CommandResult
from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS
from prodockit.bootstrap.recovery import (
    PdkbootRunJournal,
    pdkboot_report_path,
    recovery_advice,
)


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


@pytest.mark.parametrize(
    ("stage", "platform", "command", "outcome", "category", "expected"),
    [
        (
            "git",
            WINDOWS,
            ["winget", "install", "--id", "Git.Git"],
            CommandResult(127, stderr="winget: not found"),
            "package-manager-missing",
            "App Installer",
        ),
        (
            "git",
            WINDOWS,
            ["winget", "install", "--id", "Git.Git"],
            CommandResult(1, stderr="Failed when opening source; 0x8A15000F"),
            "winget-source",
            "source reset --force",
        ),
        (
            "clone",
            UBUNTU,
            ["git", "clone"],
            CommandResult(1, stderr="Could not resolve host"),
            "network",
            "DNS",
        ),
        (
            "project-env",
            MACOS,
            ["python", "-m", "venv"],
            CommandResult(1, stderr="Permission denied"),
            "permissions",
            "do not change ownership recursively",
        ),
        (
            "node",
            UBUNTU,
            ["npm", "ci"],
            CommandResult(1, stderr="ENOSPC: no space left on device"),
            "disk-space",
            "Free disk space",
        ),
        (
            "pandoc",
            UBUNTU,
            ["apt", "install"],
            CommandResult(100, stderr="Could not get lock /var/lib/dpkg/lock"),
            "installer-busy",
            "do not delete",
        ),
        (
            "clone",
            MACOS,
            ["git", "clone"],
            CommandResult(1, stderr="remote ended unexpectedly"),
            "partial-clone",
            "move the partial directory aside",
        ),
        (
            "node",
            WINDOWS,
            ["winget", "install", "--id", "OpenJS.NodeJS.LTS"],
            CommandResult(1, stderr="installer returned an unknown error"),
            "alternative-installer",
            "official installer for the current Node.js LTS",
        ),
        (
            "git",
            MACOS,
            ["brew", "install", "git"],
            CommandResult(1, stderr="formula installation failed"),
            "alternative-installer",
            "xcode-select --install",
        ),
        (
            "project-env",
            MACOS,
            ["python", "-m", "pip", "install"],
            CommandResult(1, stderr="build backend failed"),
            "partial-environment",
            "move the project's `.venv` aside",
        ),
        (
            "node",
            MACOS,
            ["npm", "ci"],
            CommandResult(1, stderr="dependency install failed"),
            "node-toolchain",
            "npm cache verify",
        ),
        (
            "pandoc",
            WINDOWS,
            ["powershell", "-Command", "install pango"],
            CommandResult(1, stderr="MSYS2 failed"),
            "windows-pdf-toolchain",
            "winget list --id JohnMacFarlane.Pandoc",
        ),
        (
            "git",
            MACOS,
            ["git", "config"],
            CommandResult(1, stderr="unexpected failure"),
            "unclassified",
            "Review the command output",
        ),
    ],
)
def test_failure_is_classified_with_safe_recovery_steps(
    stage: str,
    platform: str,
    command: list[str],
    outcome: CommandResult,
    category: str,
    expected: str,
) -> None:
    advice = recovery_advice(stage, platform, command, outcome)

    assert advice.category == category
    assert expected in " ".join(advice.steps)
