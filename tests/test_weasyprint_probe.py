# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import subprocess
from pathlib import Path

from prodockit import weasyprint_probe as probe


def _clock(values: list[float]):
    iterator = iter(values)
    return lambda: next(iterator)


def test_timeout_uses_the_weasyprint_command_as_an_alternative(
    tmp_path: Path, monkeypatch
) -> None:
    command = tmp_path / "weasyprint.exe"
    command.write_text("launcher", encoding="utf-8")
    calls: list[list[str]] = []
    notices = []
    delays = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(arguments, kwargs["timeout"])
        return subprocess.CompletedProcess(arguments, 0, "WeasyPrint version 69.0\n", "")

    monkeypatch.setattr(probe, "_weasyprint_command", lambda: command)
    result = probe.run_probe(
        runner=run,
        reporter=notices.append,
        retry_delays=(2.0,),
        sleeper=delays.append,
        clock=_clock([0.0, 60.0, 62.0, 62.25]),
    )

    assert result.returncode == 0
    assert result.version == "69.0"
    assert [attempt.method for attempt in result.attempts] == [
        "Python import",
        "WeasyPrint command",
    ]
    assert calls[0][0] != calls[1][0]
    assert calls[1] == [str(command), "--version"]
    assert delays == [2.0]
    assert notices[0].maximum_attempts == 2
    assert notices[0].detail == "timed out after 60s"


def test_persistent_timeout_is_bounded_and_actionable(monkeypatch) -> None:
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        raise subprocess.TimeoutExpired(arguments, kwargs["timeout"])

    monkeypatch.setattr(probe, "_weasyprint_command", lambda: None)
    result = probe.run_probe(
        runner=run,
        retry_delays=(0.0, 0.0),
        sleeper=lambda _delay: None,
        clock=_clock([0.0, 60.0, 60.0, 120.0, 120.0, 180.0]),
    )

    assert result.returncode == 124
    assert len(calls) == 3
    assert all(command[0] == probe.sys.executable for command in calls)
    assert "timed out after 3 bounded attempts" in result.error
    assert "Each subprocess was stopped and waited for" in result.error
    assert "check the native PDF libraries" in result.error
    assert len(result.evidence()["attempts"]) == 3


def test_non_timeout_failure_is_not_retried(monkeypatch) -> None:
    calls = []

    def run(arguments, **_kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 1, "", "Pango is unavailable")

    monkeypatch.setattr(probe, "_weasyprint_command", lambda: None)
    result = probe.run_probe(
        runner=run,
        retry_delays=(0.0,),
        clock=_clock([0.0, 0.1]),
    )

    assert result.returncode == 1
    assert result.stderr == "Pango is unavailable"
    assert len(calls) == 1


def test_recent_success_is_reused_for_a_second_non_render_check(monkeypatch) -> None:
    calls = []

    def run(arguments, **_kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, "69.0\n", "")

    probe.clear_probe_cache()
    monkeypatch.setattr(probe.subprocess, "run", run)
    first = probe.run_probe(environment={"PATH": "test"})
    second = probe.run_probe(environment={"PATH": "test"})
    probe.clear_probe_cache()

    assert first is second
    assert len(calls) == 1


def test_cache_key_retains_the_runner_to_prevent_identity_reuse() -> None:
    def run(arguments, **_kwargs):
        return subprocess.CompletedProcess(arguments, 0, "", "")

    key = probe._cache_key({"PATH": "test"}, run)

    assert key[-1] is run


def test_render_retry_requires_the_alternative_command_to_create_a_pdf(
    tmp_path: Path, monkeypatch
) -> None:
    command = tmp_path / "weasyprint"
    command.write_text("launcher", encoding="utf-8")
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(arguments, kwargs["timeout"])
        Path(arguments[2]).write_bytes(b"%PDF-1.7\n")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(probe, "_weasyprint_command", lambda: command)
    result = probe.run_probe(
        render=True,
        runner=run,
        retry_delays=(0.0,),
        sleeper=lambda _delay: None,
        clock=_clock([0.0, 60.0, 60.0, 60.2]),
    )

    assert result.returncode == 0
    assert calls[1][0] == str(command)
    assert calls[1][1].endswith("probe.html")
    assert calls[1][2].endswith("probe.pdf")


def test_render_retry_rejects_an_empty_alternative_output(tmp_path: Path, monkeypatch) -> None:
    command = tmp_path / "weasyprint"
    command.write_text("launcher", encoding="utf-8")
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(arguments, kwargs["timeout"])
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(probe, "_weasyprint_command", lambda: command)
    result = probe.run_probe(
        render=True,
        runner=run,
        retry_delays=(0.0,),
        sleeper=lambda _delay: None,
        clock=_clock([0.0, 60.0, 60.0, 60.2]),
    )

    assert result.returncode == 1
    assert "did not produce a PDF" in result.stderr
