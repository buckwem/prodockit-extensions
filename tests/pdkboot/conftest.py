# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from .harness import PdkbootCliHarness


@pytest.fixture()
def bootstrap_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PdkbootCliHarness:
    """The reusable, network-free harness for pdkboot's command boundary."""
    return PdkbootCliHarness(tmp_path, monkeypatch)


@pytest.fixture()
def cli_bootstrap(bootstrap_cli: PdkbootCliHarness):
    """Compatibility callable retained in the forked stage-model tests."""
    return bootstrap_cli.invoke
