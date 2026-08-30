# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Safety checks for the installed-wheel bootstrap acceptance harness."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
bootstrap_acceptance = importlib.import_module("tools.bootstrap_acceptance")


def test_all_host_and_repository_routes_are_declared() -> None:
    assert bootstrap_acceptance.SCENARIOS == (
        ("surrey-new", "surrey", "new"),
        ("surrey-existing", "surrey", "existing"),
        ("github-new", "github", "new"),
        ("github-existing", "github", "existing"),
    )


def test_a_wheel_file_or_single_wheel_directory_is_accepted(tmp_path: Path) -> None:
    wheel = tmp_path / "prodockit-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    assert bootstrap_acceptance.resolve_wheel(wheel) == wheel.resolve()
    assert bootstrap_acceptance.resolve_wheel(tmp_path) == wheel.resolve()


def test_an_ambiguous_wheel_directory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "prodockit-1-py3-none-any.whl").write_bytes(b"one")
    (tmp_path / "prodockit-2-py3-none-any.whl").write_bytes(b"two")

    with pytest.raises(bootstrap_acceptance.AcceptanceError, match="expected one"):
        bootstrap_acceptance.resolve_wheel(tmp_path)


def test_architecture_requirements_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        bootstrap_acceptance.parser().parse_args(
            [
                "--wheel",
                "candidate.whl",
                "--report",
                "report.json",
                "--require-x64",
                "--require-arm64",
            ]
        )


@pytest.mark.parametrize("machine", ["arm64", "aarch64"])
def test_arm64_architecture_names_are_accepted(monkeypatch, machine: str) -> None:
    monkeypatch.setattr(bootstrap_acceptance.platform, "machine", lambda: machine)

    assert bootstrap_acceptance.require_architecture(x64=False, arm64=True) == machine


def test_x64_is_rejected_when_arm64_is_required(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap_acceptance.platform, "machine", lambda: "x86_64")

    with pytest.raises(bootstrap_acceptance.AcceptanceError, match="expected ARM64"):
        bootstrap_acceptance.require_architecture(x64=False, arm64=True)


def test_driver_never_imports_the_source_bootstrap_test_harness() -> None:
    driver = (ROOT / "tools" / "_bootstrap_acceptance_driver.py").read_text(
        encoding="utf-8"
    )

    assert "tests.bootstrap_cli_harness" not in driver
    assert "git clone" not in driver, "repository commands go through argument lists"
    assert "gitlab.surrey.ac.uk" not in driver, "host addresses come from the wheel"
