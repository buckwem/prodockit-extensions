# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Bounded retry policy for external renderer operations."""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

DEFAULT_RETRY_DELAYS = (2.0, 5.0)

_TRANSIENT_MARKERS = (
    "eai_again",
    "econnrefused",
    "econnreset",
    "etimedout",
    "bad gateway",
    "connection refused",
    "connection reset",
    "gateway timeout",
    "name or service not known",
    "network is unreachable",
    "request timeout",
    "service unavailable",
    "socket hang up",
    "temporary failure",
    "temporarily unavailable",
    "timed out",
    "tls handshake timeout",
    "unexpected eof",
    # Chromium snaps can be launched before their automatically connected
    # graphics content snap is mounted on a newly provisioned Ubuntu host.
    "content snap gpu wrapper",
    "ensure slot is connected",
)


@dataclass(frozen=True)
class RetryNotice:
    """One transient operation that will be repeated after a delay."""

    operation: str
    attempt: int
    maximum_attempts: int
    delay: float
    detail: str


RetryReporter = Callable[[RetryNotice], None]
T = TypeVar("T")


@dataclass(frozen=True)
class RetryResult(Generic[T]):
    """One returned operation result and its bounded retry evidence."""

    value: T
    attempts: int
    transient_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class NpmResult:
    """A completed npm operation and its bounded retry evidence."""

    completed: subprocess.CompletedProcess[str]
    attempts: int
    transient_failures: tuple[str, ...] = ()

    @property
    def failure_detail(self) -> str:
        """Return the final npm error with bounded prior-attempt evidence."""

        return failure_with_history(
            _detail(self.completed), self.attempts, self.transient_failures
        )


def transient_renderer_failure(detail: str | None) -> bool:
    """Return whether renderer output names a recognized external failure."""

    lowered = (detail or "").casefold()
    return any(marker in lowered for marker in _TRANSIENT_MARKERS)


def _detail(completed: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    )


def _remove_partial_modules(path: Path) -> None:
    """Remove an incomplete install without following a directory symlink."""

    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def failure_with_history(
    final: str,
    attempts: int,
    transient_failures: Sequence[str],
) -> str:
    """Append bounded prior-attempt evidence to the actionable final error."""

    if attempts <= 1 or not transient_failures:
        return final
    history = " | ".join(value[-500:] for value in transient_failures)
    return (
        f"{final}\nFailed after {attempts} attempts. "
        f"Earlier transient failures: {history}"
    )


def run_with_retries(
    operation: str,
    action: Callable[[], T],
    *,
    succeeded: Callable[[T], bool],
    failure_detail: Callable[[T], str],
    retry_delays: Sequence[float] = DEFAULT_RETRY_DELAYS,
    reporter: RetryReporter | None = None,
    before_retry: Callable[[], None] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> RetryResult[T]:
    """Repeat a returned transient failure according to the shared policy."""

    failures: list[str] = []
    maximum_attempts = len(retry_delays) + 1
    for attempt in range(1, maximum_attempts + 1):
        result = action()
        if succeeded(result):
            return RetryResult(result, attempt, tuple(failures))
        detail = failure_detail(result)
        if attempt == maximum_attempts or not transient_renderer_failure(detail):
            return RetryResult(result, attempt, tuple(failures))
        failures.append(detail)
        delay = float(retry_delays[attempt - 1])
        if before_retry is not None:
            before_retry()
        if reporter is not None:
            reporter(
                RetryNotice(
                    operation,
                    attempt,
                    maximum_attempts,
                    delay,
                    detail,
                )
            )
        sleeper(delay)
    raise AssertionError("unreachable")


def run_npm_with_retries(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
    timeout: float = 600,
    retry_delays: Sequence[float] = DEFAULT_RETRY_DELAYS,
    reporter: RetryReporter | None = None,
) -> NpmResult:
    """Run an idempotent npm install, retrying completed transient failures.

    A ``TimeoutExpired`` is deliberately not caught. Killing npm does not
    prove that all descendants have stopped, so automatically starting a new
    installer could race a surviving process. A returned process is finished;
    its partial ``node_modules`` can therefore be removed before a safe retry.
    """

    modules = cwd / "node_modules"

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=dict(environment) if environment is not None else None,
        )

    result = run_with_retries(
        "npm renderer installation",
        run,
        succeeded=lambda completed: completed.returncode == 0,
        failure_detail=_detail,
        retry_delays=retry_delays,
        reporter=reporter,
        before_retry=lambda: _remove_partial_modules(modules),
        sleeper=time.sleep,
    )
    return NpmResult(result.value, result.attempts, result.transient_failures)


__all__ = [
    "DEFAULT_RETRY_DELAYS",
    "NpmResult",
    "RetryNotice",
    "RetryReporter",
    "RetryResult",
    "failure_with_history",
    "run_npm_with_retries",
    "run_with_retries",
    "transient_renderer_failure",
]
