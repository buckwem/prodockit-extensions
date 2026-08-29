# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest
from bootstrap_cli_harness import BootstrapCliHarness


@pytest.fixture()
def bootstrap_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BootstrapCliHarness:
    """The reusable, network-free harness for prodockit bootstrap's command boundary."""
    return BootstrapCliHarness(tmp_path, monkeypatch)


@pytest.fixture()
def cli_bootstrap(bootstrap_cli: BootstrapCliHarness):
    """Compatibility callable retained in the forked stage-model tests."""
    return bootstrap_cli.invoke
