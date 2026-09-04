# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

acceptance = importlib.import_module("tools.adopt_toolchain_acceptance")


def test_resolve_candidate_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "prodockit-1.0-py3-none-any.whl"
    wheel.touch()

    assert acceptance.resolve_wheel(tmp_path) == wheel.resolve()


def test_upgrade_and_downgrade_are_required_separate_scenarios(tmp_path: Path) -> None:
    base = ["--wheel", str(tmp_path), "--report", str(tmp_path / "report.json")]

    with pytest.raises(SystemExit):
        acceptance.parser().parse_args(base)
    assert acceptance.parser().parse_args([*base, "--scenario", "upgrade"]).scenario == "upgrade"
    assert (
        acceptance.parser().parse_args([*base, "--scenario", "downgrade"]).scenario == "downgrade"
    )


def test_architecture_guard_covers_x64_and_arm64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceptance.platform, "machine", lambda: "arm64")

    assert acceptance.require_architecture(x64=False, arm64=True) == "arm64"
    with pytest.raises(acceptance.AcceptanceError, match="expected x64"):
        acceptance.require_architecture(x64=True, arm64=False)


def test_positive_timeout_rejects_zero() -> None:
    with pytest.raises(acceptance.argparse.ArgumentTypeError):
        acceptance.positive_integer("0")
