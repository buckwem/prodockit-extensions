# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Checks for the release-only installed Adopt upgrade driver."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
adopt_native_upgrade = importlib.import_module("adopt_native_upgrade")


def test_the_upgrade_starts_from_a_published_adopt_release() -> None:
    assert adopt_native_upgrade.OLD_PRODOCKIT_VERSION == "0.47.0"


def test_architecture_requirements_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        adopt_native_upgrade.parser().parse_args(
            ["--wheel", "candidate.whl", "--require-x64", "--require-arm64"]
        )
