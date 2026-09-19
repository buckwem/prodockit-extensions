# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from prodockit.renderer_health import probe_mathjax


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
