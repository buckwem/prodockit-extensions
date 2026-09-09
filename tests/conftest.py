# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest
from bootstrap_cli_harness import BootstrapCliHarness


@pytest.fixture(autouse=True)
def native_pdf_runtime_is_host_independent(monkeypatch):
    """Configuration unit tests must not inspect or install the host's fonts.

    Native-runtime tests override these probes explicitly; native acceptance
    subprocesses run the real probes without these in-process test fixtures.
    """
    monkeypatch.setattr("prodockit.adopt_pdf_runtime._probe", lambda *args, **kwargs: "")
    monkeypatch.setattr("prodockit.adopt_pdf_runtime._loader_missing", lambda *args: False)


@pytest.fixture(autouse=True)
def offline_adopt_template_source(monkeypatch: pytest.MonkeyPatch):
    """CLI regression tests never depend on the live GitHub template.

    Snapshot fetching and real template-setting reviews have their own explicit
    fixtures in test_adopt_settings.py. Keep unrelated command tests offline.
    """
    from prodockit.adopt_settings import Snapshot

    monkeypatch.setattr(
        "prodockit.cli.load_adopt_settings_snapshot",
        lambda **kwargs: Snapshot("[project]\n", "test:empty-template"),
    )


@pytest.fixture()
def bootstrap_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BootstrapCliHarness:
    """The reusable, network-free harness for prodockit bootstrap's command boundary."""
    return BootstrapCliHarness(tmp_path, monkeypatch)


@pytest.fixture()
def cli_bootstrap(bootstrap_cli: BootstrapCliHarness):
    """Compatibility callable retained in the forked stage-model tests."""
    return bootstrap_cli.invoke
