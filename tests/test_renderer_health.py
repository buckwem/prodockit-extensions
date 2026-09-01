# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from prodockit.renderer_health import probe_mermaid


def test_mermaid_probe_requires_a_successful_version_command(
    tmp_path: Path, monkeypatch
) -> None:
    binary = tmp_path / "mmdc"
    binary.write_text("shim", encoding="utf-8")
    monkeypatch.setattr(
        "prodockit.renderer_health.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(
            args=command,
            returncode=1,
            stdout="",
            stderr="ERR_MODULE_NOT_FOUND",
        ),
    )

    result = probe_mermaid(binary)

    assert result.ok is False
    assert result.version is None
    assert result.error == "ERR_MODULE_NOT_FOUND"


def test_mermaid_probe_records_the_reported_version(tmp_path: Path, monkeypatch) -> None:
    binary = tmp_path / "mmdc"
    binary.write_text("shim", encoding="utf-8")
    monkeypatch.setattr(
        "prodockit.renderer_health.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(
            args=command,
            returncode=0,
            stdout="11.12.0\n",
            stderr="",
        ),
    )

    result = probe_mermaid(binary)

    assert result.ok is True
    assert result.version == "11.12.0"
    assert result.error is None
