# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from prodockit.renderer_health import probe_mathjax, probe_mermaid


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
    def run(command, **kwargs):
        if "-o" in command:
            Path(command[command.index("-o") + 1]).write_text("<svg/>", encoding="utf-8")
            return SimpleNamespace(args=command, returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            args=command, returncode=0, stdout="11.12.0\n", stderr=""
        )

    monkeypatch.setattr("prodockit.renderer_health.subprocess.run", run)

    result = probe_mermaid(binary)

    assert result.ok is True
    assert result.version == "11.12.0"
    assert result.error is None


def test_mermaid_probe_rejects_a_browser_render_failure(tmp_path: Path, monkeypatch) -> None:
    binary = tmp_path / "mmdc"
    binary.write_text("shim", encoding="utf-8")

    def run(command, **kwargs):
        if "--version" in command:
            return SimpleNamespace(returncode=0, stdout="11.12.0", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="Browser failed to launch")

    monkeypatch.setattr("prodockit.renderer_health.subprocess.run", run)

    result = probe_mermaid(binary)

    assert result.ok is False
    assert result.version == "11.12.0"
    assert result.error == "Browser failed to launch"


def test_mathjax_probe_requires_svg_output(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "tex2svg.js"
    script.touch()
    monkeypatch.setattr(
        "prodockit.renderer_health.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(returncode=0, stdout="not svg", stderr=""),
    )

    result = probe_mathjax("node", script)

    assert result.ok is False
    assert result.error == "render probe did not produce an SVG"


def test_mathjax_probe_accepts_a_rendered_expression(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "tex2svg.js"
    script.touch()
    seen = {}

    def run(command, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="<svg></svg>", stderr="")

    monkeypatch.setattr("prodockit.renderer_health.subprocess.run", run)

    assert probe_mathjax("node", script).ok is True
    assert seen["input"] == "x"
