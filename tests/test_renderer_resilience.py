# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Safety boundaries for production renderer retries."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import prodockit.renderer_health as renderer_health
import prodockit.renderer_resilience as resilience
from prodockit.renderer_health import RendererProbe


def test_mermaid_probe_recovers_from_the_ubuntu_snap_content_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "mmdc"
    outcomes = iter(
        (
            RendererProbe(binary, error="Content snap GPU wrapper is not mounted"),
            RendererProbe(binary, version="11.12.0"),
        )
    )
    notices = []
    delays = []
    monkeypatch.setattr(renderer_health, "_probe_mermaid_once", lambda *_args, **_kw: next(outcomes))
    monkeypatch.setattr(renderer_health.time, "sleep", delays.append)

    result = renderer_health.probe_mermaid(binary, reporter=notices.append)

    assert result.ok
    assert result.attempts == 2
    assert result.transient_failures == ("Content snap GPU wrapper is not mounted",)
    assert delays == [2.0]
    assert [(notice.attempt, notice.maximum_attempts) for notice in notices] == [(1, 3)]


def test_mermaid_probe_does_not_retry_a_deterministic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "mmdc"
    calls = []

    def probe(*_args, **_kwargs):
        calls.append(True)
        return RendererProbe(binary, error="Mermaid syntax is invalid")

    monkeypatch.setattr(renderer_health, "_probe_mermaid_once", probe)
    monkeypatch.setattr(
        renderer_health.time,
        "sleep",
        lambda _delay: pytest.fail("a deterministic failure was retried"),
    )

    result = renderer_health.probe_mermaid(binary)

    assert not result.ok
    assert result.attempts == 1
    assert calls == [True]


def test_mermaid_probe_exhaustion_preserves_bounded_attempt_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "mmdc"
    outcomes = iter(
        RendererProbe(binary, error=detail)
        for detail in ("EAI_AGAIN first", "ECONNRESET second", "ETIMEDOUT final")
    )
    monkeypatch.setattr(
        renderer_health,
        "_probe_mermaid_once",
        lambda *_args, **_kwargs: next(outcomes),
    )
    monkeypatch.setattr(renderer_health.time, "sleep", lambda _delay: None)

    result = renderer_health.probe_mermaid(binary)

    assert not result.ok
    assert result.attempts == 3
    assert result.error is not None
    assert "ETIMEDOUT final" in result.error
    assert "EAI_AGAIN first" in result.error
    assert "ECONNRESET second" in result.error


def test_npm_retry_removes_partial_modules_and_reports_the_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules = tmp_path / "node_modules"
    modules.mkdir()
    (modules / "partial").write_text("partial", encoding="utf-8")
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 1, "", "npm ERR! code ECONNRESET")
        return subprocess.CompletedProcess(command, 0, "installed", "")

    notices = []
    delays = []
    monkeypatch.setattr(resilience.subprocess, "run", run)
    monkeypatch.setattr(resilience.time, "sleep", delays.append)

    result = resilience.run_npm_with_retries(
        ["npm", "ci"], cwd=tmp_path, reporter=notices.append
    )

    assert result.completed.returncode == 0
    assert result.attempts == 2
    assert result.transient_failures == ("npm ERR! code ECONNRESET",)
    assert not modules.exists()
    assert delays == [2.0]
    assert notices[0].operation == "npm renderer installation"


def test_npm_does_not_retry_an_unrecognized_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "invalid package manifest")

    monkeypatch.setattr(resilience.subprocess, "run", run)
    monkeypatch.setattr(
        resilience.time,
        "sleep",
        lambda _delay: pytest.fail("an unrecognized failure was retried"),
    )

    result = resilience.run_npm_with_retries(["npm", "ci"], cwd=tmp_path)

    assert result.completed.returncode == 1
    assert result.attempts == 1
    assert len(calls) == 1


def test_npm_retry_unlinks_partial_modules_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    modules = tmp_path / "node_modules"
    modules.symlink_to(outside, target_is_directory=True)
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            1 if len(calls) == 1 else 0,
            "",
            "npm ERR! code ETIMEDOUT" if len(calls) == 1 else "",
        )

    monkeypatch.setattr(resilience.subprocess, "run", run)
    monkeypatch.setattr(resilience.time, "sleep", lambda _delay: None)

    result = resilience.run_npm_with_retries(["npm", "ci"], cwd=tmp_path)

    assert result.completed.returncode == 0
    assert not modules.exists()
    assert outside.is_dir()


def test_npm_exhaustion_preserves_bounded_attempt_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = iter(("EAI_AGAIN first", "ECONNRESET second", "ETIMEDOUT final"))
    monkeypatch.setattr(
        resilience.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 1, "", next(attempts)
        ),
    )
    monkeypatch.setattr(resilience.time, "sleep", lambda _delay: None)

    result = resilience.run_npm_with_retries(["npm", "ci"], cwd=tmp_path)

    assert result.attempts == 3
    assert "ETIMEDOUT final" in result.failure_detail
    assert "EAI_AGAIN first" in result.failure_detail
    assert "ECONNRESET second" in result.failure_detail


def test_npm_timeout_is_not_retried_while_descendant_state_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules = tmp_path / "node_modules"
    modules.mkdir()
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(resilience.subprocess, "run", run)

    with pytest.raises(subprocess.TimeoutExpired):
        resilience.run_npm_with_retries(["npm", "ci"], cwd=tmp_path)

    assert len(calls) == 1
    assert modules.is_dir()
