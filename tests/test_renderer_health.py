# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import prodockit.renderer_health as renderer_health
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


def test_mermaid_probe_uses_the_runnable_windows_shim(tmp_path: Path) -> None:
    binary = tmp_path / "mmdc"
    binary.write_text("posix shim", encoding="utf-8")
    windows_shim = tmp_path / "mmdc.cmd"
    windows_shim.write_text("windows shim", encoding="utf-8")
    assert renderer_health._command(binary, "--version", platform="nt") == [
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        str(windows_shim),
        "--version",
    ]


def test_mermaid_probe_bypasses_cmd_for_npm_cli_in_path_with_spaces(tmp_path: Path) -> None:
    binary = tmp_path / "project with spaces" / "node_modules" / ".bin" / "mmdc"
    binary.parent.mkdir(parents=True)
    binary.write_text("posix shim", encoding="utf-8")
    windows_shim = binary.with_suffix(".cmd")
    windows_shim.write_text("windows shim", encoding="utf-8")
    cli = binary.parent.parent / "@mermaid-js" / "mermaid-cli" / "src" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("// cli", encoding="utf-8")

    assert renderer_health._command(binary, "--version", platform="nt") == [
        "node",
        str(cli),
        "--version",
    ]


def test_mermaid_probe_uses_a_discovered_browser_when_downloads_are_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    binary = tmp_path / "mmdc"
    binary.write_text("shim", encoding="utf-8")
    monkeypatch.delenv("PUPPETEER_EXECUTABLE_PATH", raising=False)
    monkeypatch.setenv("PUPPETEER_SKIP_DOWNLOAD", "true")
    monkeypatch.setattr(
        "prodockit.renderer_health.shutil.which",
        lambda name: "/usr/bin/chromium" if name == "chromium" else None,
    )
    environments = []

    def run(command, **kwargs):
        environments.append(kwargs["env"])
        if "-o" in command:
            Path(command[command.index("-o") + 1]).write_text("<svg/>", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="11.12.0", stderr="")

    monkeypatch.setattr("prodockit.renderer_health.subprocess.run", run)

    assert probe_mermaid(binary).ok is True
    assert all(
        environment["PUPPETEER_EXECUTABLE_PATH"] == "/usr/bin/chromium"
        for environment in environments
    )


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
