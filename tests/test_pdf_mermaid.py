# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import stat
from pathlib import Path

from prodockit.pdf.mermaid import render_mermaid_diagram


def test_returns_none_when_mmdc_binary_does_not_exist(tmp_path: Path) -> None:
    missing_bin = tmp_path / "no-such-mmdc"
    result = render_mermaid_diagram("graph TD; A-->B;", str(missing_bin), str(tmp_path / "out"), 1)
    assert result is None


def _fake_mmdc(tmp_path: Path, script: str) -> str:
    """Writes a fake `mmdc` executable (a shell script) so a test can
    exercise render_mermaid_diagram() without a real mermaid-cli/Chromium
    install - script receives the same "-i in -o out -b transparent
    -c mmdc_config -p puppeteer_config" arguments the real mmdc would."""
    bin_path = tmp_path / "mmdc"
    bin_path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    bin_path.chmod(bin_path.stat().st_mode | stat.S_IEXEC)
    return str(bin_path)


def test_writes_diagram_source_and_configs_then_produces_the_svg(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    mmdc_bin = _fake_mmdc(tmp_path, 'echo "<svg></svg>" > "$4"')
    # $1=-i $2=<mmd> $3=-o $4=<svg> ...
    svg_path = render_mermaid_diagram("graph TD; A-->B;", mmdc_bin, str(output_dir), 1)
    assert svg_path is not None
    assert os.path.exists(svg_path)
    assert (output_dir / "diagram_1.mmd").read_text(encoding="utf-8") == "graph TD; A-->B;"


def test_returns_none_when_mmdc_exits_nonzero(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    mmdc_bin = _fake_mmdc(tmp_path, "exit 1")
    result = render_mermaid_diagram("graph TD; A-->B;", mmdc_bin, str(output_dir), 1)
    assert result is None


def test_returns_none_when_mmdc_binary_is_not_executable(tmp_path: Path) -> None:
    """Regression test: mmdc_bin existing but not being executable (e.g.
    permission bits, or a directory mistakenly configured as the binary
    path) makes subprocess.run raise PermissionError/OSError directly,
    not CalledProcessError - previously uncaught, contradicting this
    module's own "one bad diagram can't fail an entire build" promise."""
    output_dir = tmp_path / "out"
    non_executable_bin = tmp_path / "mmdc"
    non_executable_bin.write_text("#!/bin/sh\necho not executable\n", encoding="utf-8")
    non_executable_bin.chmod(0o644)
    result = render_mermaid_diagram("graph TD; A-->B;", str(non_executable_bin), str(output_dir), 1)
    assert result is None


def test_returns_none_on_timeout(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    mmdc_bin = _fake_mmdc(tmp_path, "sleep 2")
    result = render_mermaid_diagram("graph TD; A-->B;", mmdc_bin, str(output_dir), 1, timeout=1)
    assert result is None


def test_disables_html_labels_in_the_generated_mermaid_config(tmp_path: Path) -> None:
    # Args are: -i <mmd> -o <svg> -b transparent -c <mmdc_config> -p <puppeteer_config>
    # ($1..$9, then ${10}) - $8 is the mmdc_config path.
    output_dir = tmp_path / "out"
    mmdc_bin = _fake_mmdc(tmp_path, 'echo "<svg></svg>" > "$4"')
    render_mermaid_diagram("graph TD; A-->B;", mmdc_bin, str(output_dir), 1)
    config_path = output_dir / "diagram_1_mermaid_config.json"
    assert '"htmlLabels": false' in config_path.read_text(encoding="utf-8")
