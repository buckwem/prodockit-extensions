# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Shared bounded resilience policy for live-provider observations.

Provider mutations are deliberately outside this module.  A lost response to
an API write is ambiguous and must be reconciled against provider state rather
than repeated.  These helpers are for read-only observations and completed,
idempotent commands only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

READ_RETRY_DELAYS = (2.0, 5.0, 10.0, 20.0)
TRANSIENT_HTTP_STATUS = frozenset({429, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 60.0

_TRANSIENT_COMMAND_MARKERS = (
    "bad gateway",
    "connection closed by remote host",
    "connection refused",
    "connection reset",
    "could not resolve host",
    "could not resolve hostname",
    "end of central directory record signature not found",
    "connection timed out",
    "gateway timeout",
    "http 429",
    "http 502",
    "http 503",
    "http 504",
    "network is unreachable",
    "operation timed out",
    "remote end hung up unexpectedly",
    "remote hung up unexpectedly",
    "service unavailable",
    "temporary failure",
    "temporarily unavailable",
    "the remote end hung up unexpectedly",
    "tls handshake timeout",
    "unexpected eof",
    "unexpected end of file",
)


def safe_failure_detail(value: object, *, limit: int = 500) -> str:
    """Return bounded, single-line retry evidence suitable for an error."""

    detail = " ".join(str(value).split())
    return detail[-limit:] if detail else type(value).__name__


def failure_with_history(final: str, failures: Sequence[str]) -> str:
    """Add bounded earlier-attempt evidence to the final actionable error."""

    if not failures:
        return final
    history = " | ".join(safe_failure_detail(value) for value in failures)
    return f"{final}; earlier transient observations: {history}"


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.casefold() == name.casefold():
            return str(value).strip()
    return ""


def retry_after_seconds(
    headers: Mapping[str, str],
    *,
    now: datetime | None = None,
) -> float | None:
    """Parse an HTTP ``Retry-After`` delay without allowing an unbounded wait."""

    value = _header(headers, "Retry-After")
    if not value:
        return None
    if value.isdecimal():
        return min(float(value), MAX_RETRY_AFTER_SECONDS)
    try:
        target = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return min(max(0.0, (target - current).total_seconds()), MAX_RETRY_AFTER_SECONDS)


def retry_delay(default: float, headers: Mapping[str, str]) -> float:
    """Respect a provider back-off hint while retaining a finite retry budget."""

    requested = retry_after_seconds(headers)
    return max(float(default), requested or 0.0)


def transient_http_read(
    status: int,
    headers: Mapping[str, str],
    detail: str = "",
    *,
    retry_forbidden: bool = False,
) -> bool:
    """Classify a failed provider read without treating authentication as transient."""

    if status in TRANSIENT_HTTP_STATUS:
        return True
    if status != 403:
        return False
    if retry_forbidden:
        return True
    lowered = detail.casefold()
    return (
        bool(_header(headers, "Retry-After"))
        or _header(headers, "X-RateLimit-Remaining") == "0"
        or "rate limit" in lowered
        or "abuse detection" in lowered
    )


def transient_external_failure(detail: str) -> bool:
    """Classify a completed external operation that is safe to repeat."""

    lowered = detail.casefold()
    return any(marker in lowered for marker in _TRANSIENT_COMMAND_MARKERS)


def transient_command_read(detail: str) -> bool:
    """Classify provider transport output that is safe to observe again."""

    return transient_external_failure(detail)


__all__ = [
    "READ_RETRY_DELAYS",
    "TRANSIENT_HTTP_STATUS",
    "failure_with_history",
    "retry_after_seconds",
    "retry_delay",
    "safe_failure_detail",
    "transient_command_read",
    "transient_external_failure",
    "transient_http_read",
]
