# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Safety boundaries for production runtime retries."""

from __future__ import annotations

import pytest

import prodockit.renderer_resilience as resilience


@pytest.mark.parametrize(
    "detail",
    [
        "EACCES after ECONNRESET",
        "permission denied; service unavailable",
        "No matching distribution; connection reset",
        "invalid configuration; timed out",
        "no automatic retry; ECONNRESET",
        "did not finish within 1800 seconds",
    ],
)
def test_permanent_or_unverified_failure_is_never_transient(detail):
    from prodockit.bootstrap import _temporary_network_failure
    from prodockit.bootstrap.model import CommandResult

    assert not resilience.transient_runtime_failure(detail)
    assert not _temporary_network_failure(CommandResult(1, stderr=detail))
