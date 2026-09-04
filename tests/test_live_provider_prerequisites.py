# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for bounded live-provider prerequisite installation."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
prerequisites = importlib.import_module("bootstrap_live_provider_prerequisites")


def completed(returncode: int, detail: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["code"], returncode, "", detail)


def test_transient_completed_install_retries_and_records_evidence(tmp_path: Path) -> None:
    results = iter((completed(1, "HTTP 503 Service Unavailable"), completed(0)))
    delays: list[float] = []
    report = tmp_path / "report.json"

    value = prerequisites.install_prerequisites(
        report,
        runner=lambda *_args, **_kwargs: next(results),
        sleeper=delays.append,
        commands=(("code", "--install-extension", "example.extension"),),
    )

    assert value["passed"] is True
    assert value["operations"][0]["attempts"] == 2
    assert value["operations"][0]["transient_failures"] == [
        "HTTP 503 Service Unavailable"
    ]
    assert delays == [5.0]
    assert json.loads(report.read_text(encoding="utf-8")) == value


def test_deterministic_install_failure_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def rejected(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return completed(1, "extension identifier is invalid")

    report = tmp_path / "report.json"
    with pytest.raises(prerequisites.PrerequisiteError, match="identifier is invalid"):
        prerequisites.install_prerequisites(
            report,
            runner=rejected,
            sleeper=lambda _delay: pytest.fail("deterministic failure was retried"),
            commands=(("code", "--install-extension", "invalid"),),
        )

    assert calls == 1
    assert json.loads(report.read_text(encoding="utf-8"))["passed"] is False


def test_installer_timeout_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def timed_out(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired(["brew", "install"], 10)

    with pytest.raises(prerequisites.PrerequisiteError, match="was not retried"):
        prerequisites.install_prerequisites(
            tmp_path / "report.json",
            runner=timed_out,
            commands=(("brew", "install", "pandoc"),),
        )

    assert calls == 1
