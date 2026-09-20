# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Bounded fresh-process WeasyPrint health checks shared by user commands.

Loading WeasyPrint also loads platform-native PDF and font libraries. On the
hosted Windows ARM64 runners that loader has occasionally exceeded a deadline
even though an identical retry and the preceding release passed with the same
versions. A timeout is therefore inconclusive rather than evidence that the
installation is missing. The shared policy tries the active Python first and,
after a timeout, the active environment's WeasyPrint command when available.
Only a recent successful non-render result is reused, preventing Diagnostics
and its Adopt-readiness check from independently reaching opposite conclusions.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from prodockit.renderer_resilience import RetryNotice, RetryReporter

WEASYPRINT_PROBE_TIMEOUT = 60.0
WEASYPRINT_PROBE_RETRY_DELAYS = (2.0,)
_PENDING = "PDK_PYTHON_PACKAGE_PENDING"
_SUCCESS_CACHE_SECONDS = 120.0
_SUCCESS_CACHE: dict[
    tuple[str, str, str, Callable[..., subprocess.CompletedProcess[str]]],
    tuple[float, ProbeResult],
] = {}


def pango_install_guidance(*, selected_platform: str | None = None) -> str:
    """Return the exact supported host command for WeasyPrint's native libraries."""

    selected = sys.platform if selected_platform is None else selected_platform
    if selected == "darwin":
        return (
            "Install Pango with `brew install pango`, then run "
            '`export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib"` in this terminal.'
        )
    if selected.startswith("linux"):
        return (
            "Install Pango with `sudo apt update && sudo apt install -y "
            "libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`."
        )
    return "Install WeasyPrint's native libraries for this operating system."


@dataclass(frozen=True)
class ProbeAttempt:
    """Non-sensitive evidence from one fresh subprocess."""

    method: str
    duration_seconds: float
    timeout_seconds: float
    returncode: int | None
    timed_out: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "duration_seconds": self.duration_seconds,
            "timeout_seconds": self.timeout_seconds,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
        }


@dataclass(frozen=True)
class ProbeResult:
    """The final result and bounded attempt evidence."""

    completed: subprocess.CompletedProcess[str] | None
    attempts: tuple[ProbeAttempt, ...]
    error: str = ""

    @property
    def returncode(self) -> int:
        return self.completed.returncode if self.completed is not None else 124

    @property
    def stdout(self) -> str:
        return self.completed.stdout if self.completed is not None else ""

    @property
    def stderr(self) -> str:
        if self.error:
            return self.error
        return self.completed.stderr if self.completed is not None else ""

    @property
    def pending(self) -> bool:
        return _PENDING in self.stdout

    @property
    def version(self) -> str | None:
        match = re.search(r"\b(\d+(?:\.\d+)+)\b", self.stdout)
        return match.group(1) if match else None

    def evidence(self) -> dict[str, object]:
        return {
            "platform": sys.platform,
            "architecture": platform.machine(),
            "attempts": [attempt.as_dict() for attempt in self.attempts],
        }


def _python_command(*, render: bool) -> list[str]:
    code = (
        "import importlib.util, sys; "
        "missing = importlib.util.find_spec('weasyprint') is None; "
        f"print('{_PENDING}' if missing else ''); "
        "sys.exit(0) if missing else None; import weasyprint; "
        "print(weasyprint.__version__)"
    )
    if render:
        code += (
            "; data=weasyprint.HTML(string='<p>PDF runtime test</p>').write_pdf(); "
            "assert data.startswith(b'%PDF')"
        )
    return [sys.executable, "-c", code]


def _weasyprint_command() -> Path | None:
    name = "weasyprint.exe" if sys.platform == "win32" else "weasyprint"
    sibling = Path(sys.executable).with_name(name)
    return sibling if sibling.is_file() else None


def _cache_key(
    environment: Mapping[str, str], run: Callable[..., subprocess.CompletedProcess[str]]
) -> tuple[str, str, str, Callable[..., subprocess.CompletedProcess[str]]]:
    try:
        installed = version("weasyprint")
    except PackageNotFoundError:
        installed = "missing"
    loader_paths = "\0".join(
        environment.get(name, "")
        for name in ("PATH", "WEASYPRINT_DLL_DIRECTORIES", "DYLD_FALLBACK_LIBRARY_PATH")
    )
    # Retain the callable itself. An integer id can be reused after a
    # short-lived runner is collected, allowing stale success evidence to
    # leak into a later probe that happens to receive the same id.
    return sys.executable, installed, loader_paths, run


def clear_probe_cache() -> None:
    """Discard successful health evidence after an installation changes."""

    _SUCCESS_CACHE.clear()


def _timeout_error(attempts: Sequence[ProbeAttempt]) -> str:
    history = "; ".join(
        f"{attempt.method} timed out after {attempt.timeout_seconds:g}s" for attempt in attempts
    )
    return (
        f"WeasyPrint health check timed out after {len(attempts)} bounded attempts on "
        f"{platform.system() or sys.platform} {platform.machine() or 'unknown architecture'}: "
        f"{history}. Each subprocess was stopped and waited for. Retry the command; "
        "if it persists, close other applications and check the native PDF libraries."
    )


def run_probe(
    *,
    environment: Mapping[str, str] | None = None,
    render: bool = False,
    reporter: RetryReporter | None = None,
    timeout: float = WEASYPRINT_PROBE_TIMEOUT,
    retry_delays: Sequence[float] = WEASYPRINT_PROBE_RETRY_DELAYS,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleeper: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> ProbeResult:
    """Probe once through Python, then use the CLI after a timeout when available."""

    env = dict(os.environ if environment is None else environment)
    run = runner or subprocess.run
    sleep = sleeper or time.sleep
    now = clock or time.monotonic
    use_cache = runner is None and clock is None and not render
    cache_key = _cache_key(env, run)
    if use_cache and (cached := _SUCCESS_CACHE.get(cache_key)) is not None:
        cached_at, result = cached
        if now() - cached_at <= _SUCCESS_CACHE_SECONDS:
            return result
        _SUCCESS_CACHE.pop(cache_key, None)
    attempts: list[ProbeAttempt] = []
    maximum_attempts = len(retry_delays) + 1
    alternative = _weasyprint_command()
    with tempfile.TemporaryDirectory(prefix="prodockit-weasyprint-probe-") as temporary:
        work = Path(temporary)
        source = work / "probe.html"
        output = work / "probe.pdf"
        source.write_text("<p>PDF runtime test</p>", encoding="utf-8")
        for attempt_number in range(1, maximum_attempts + 1):
            use_cli = attempt_number > 1 and alternative is not None
            method = "WeasyPrint command" if use_cli else "Python import"
            command = (
                [str(alternative), str(source), str(output)]
                if use_cli and render
                else [str(alternative), "--version"]
                if use_cli
                else _python_command(render=render)
            )
            started = now()
            try:
                completed = run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    check=False,
                    env=env,
                )
            except subprocess.TimeoutExpired:
                duration = round(now() - started, 3)
                attempts.append(ProbeAttempt(method, duration, timeout, None, True))
                if attempt_number == maximum_attempts:
                    return ProbeResult(None, tuple(attempts), _timeout_error(attempts))
                delay = float(retry_delays[attempt_number - 1])
                if reporter is not None:
                    reporter(
                        RetryNotice(
                            f"WeasyPrint health check ({method})",
                            attempt_number,
                            maximum_attempts,
                            delay,
                            f"timed out after {timeout:g}s",
                        )
                    )
                sleep(delay)
                continue

            duration = round(now() - started, 3)
            attempts.append(
                ProbeAttempt(method, duration, timeout, completed.returncode, False)
            )
            if completed.returncode == 0 and use_cli and render:
                try:
                    rendered = output.read_bytes().startswith(b"%PDF")
                except OSError:
                    rendered = False
                if not rendered:
                    completed = subprocess.CompletedProcess(
                        command,
                        1,
                        completed.stdout,
                        "WeasyPrint command did not produce a PDF",
                    )
            result = ProbeResult(completed, tuple(attempts))
            if use_cache and result.returncode == 0 and not result.pending:
                _SUCCESS_CACHE[cache_key] = (now(), result)
            return result
    raise AssertionError("unreachable")


__all__ = [
    "WEASYPRINT_PROBE_RETRY_DELAYS",
    "WEASYPRINT_PROBE_TIMEOUT",
    "ProbeAttempt",
    "ProbeResult",
    "clear_probe_cache",
    "run_probe",
]
