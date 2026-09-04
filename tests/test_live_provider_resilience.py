# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for the shared live-provider observation retry policy."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
resilience = importlib.import_module("live_provider_resilience")


def test_retry_after_respects_provider_delay_with_a_finite_cap() -> None:
    assert resilience.retry_delay(2, {"Retry-After": "7"}) == 7
    assert resilience.retry_delay(20, {"Retry-After": "7"}) == 20
    assert resilience.retry_delay(2, {"Retry-After": "600"}) == 60
    assert resilience.retry_after_seconds(
        {"Retry-After": "Thu, 01 Jan 2026 00:00:09 GMT"},
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ) == 9


def test_github_forbidden_is_retryable_only_with_throttle_evidence() -> None:
    assert not resilience.transient_http_read(403, {}, "Forbidden")
    assert resilience.transient_http_read(
        403, {"X-RateLimit-Remaining": "0"}, "Forbidden"
    )
    assert resilience.transient_http_read(403, {}, "secondary rate limit")
    assert resilience.transient_http_read(403, {}, "Forbidden", retry_forbidden=True)


def test_git_read_classifier_separates_network_from_identity_errors() -> None:
    assert resilience.transient_command_read(
        "fatal: unable to access origin: Could not resolve host: github.com"
    )
    assert not resilience.transient_command_read("Permission denied (publickey)")
    assert not resilience.transient_command_read("Repository not found")
