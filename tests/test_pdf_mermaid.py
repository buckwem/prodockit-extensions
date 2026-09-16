# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import stat
from pathlib import Path

import pytest

import prodockit.pdf.mermaid as mermaid_module
from prodockit.pdf._standalone_quickjs import (
    StandaloneBackendUnavailableError as StandaloneRuntimeUnavailableError,
)
from prodockit.pdf._standalone_quickjs import StandaloneRenderError
from prodockit.pdf._standalone_worker import StandaloneWorkerTimeoutError
from prodockit.pdf.mermaid import (
    MermaidBackend,
    MermaidBackendUnavailableError,
    MmdcMermaidRenderer,
    StandaloneMermaidRenderer,
    create_mermaid_renderer,
    render_mermaid_diagram,
)


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


def test_mmdc_renderer_assigns_monotonic_indexes_and_forwards_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str, str, int, int]] = []
    output_dir = str(tmp_path / "diagrams")

    def fake_render(
        source: str, mmdc_bin: str, rendered_dir: str, index: int, timeout: int = 60
    ) -> str:
        calls.append((source, mmdc_bin, rendered_dir, index, timeout))
        return os.path.join(rendered_dir, f"diagram_{index}.svg")

    monkeypatch.setattr(mermaid_module, "render_mermaid_diagram", fake_render)
    renderer = MmdcMermaidRenderer("mmdc", output_dir, timeout=45)

    assert renderer.render_source("one") == os.path.join(output_dir, "diagram_1.svg")
    assert renderer.render_source("two") == os.path.join(output_dir, "diagram_2.svg")
    assert calls == [
        ("one", "mmdc", output_dir, 1, 45),
        ("two", "mmdc", output_dir, 2, 45),
    ]


def test_mmdc_renderer_close_is_idempotent() -> None:
    renderer = MmdcMermaidRenderer("mmdc", "diagrams")

    renderer.close()
    renderer.close()


def test_factory_constructs_the_current_adapter_for_a_resolved_mmdc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = []

    class RecordingRenderer:
        def __init__(self, mmdc_bin: str, output_dir: str) -> None:
            created.append((mmdc_bin, output_dir))

        def render_source(self, source: str) -> str | None:
            return source

        def close(self) -> None:
            pass

    monkeypatch.setattr(mermaid_module, "MmdcMermaidRenderer", RecordingRenderer)
    output_dir = tmp_path / "diagrams"

    renderer = create_mermaid_renderer(
        MermaidBackend.MMDC,
        mmdc_bin="resolved-mmdc",
        output_dir=str(output_dir),
    )

    assert isinstance(renderer, RecordingRenderer)
    assert created == [("resolved-mmdc", str(output_dir))]


def test_factory_returns_none_when_mmdc_is_missing(tmp_path: Path) -> None:
    output_dir = tmp_path / "diagrams"

    renderer = create_mermaid_renderer(
        MermaidBackend.MMDC,
        mmdc_bin=None,
        output_dir=str(output_dir),
    )

    assert renderer is None
    assert not output_dir.exists()


class _FakeStandaloneWorker:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self.closed = False

    def render_svg(
        self,
        source: str,
        *,
        theme: str = "default",
        config: dict[str, object] | None = None,
        css: str | None = None,
    ) -> str:
        del theme, css
        self.calls.append((source, config))
        if self.error is not None:
            raise self.error
        return f'<svg xmlns="http://www.w3.org/2000/svg"><text>{source}</text></svg>'

    def close(self) -> None:
        self.closed = True


def test_standalone_renderer_writes_monotonic_svg_files(tmp_path: Path) -> None:
    worker = _FakeStandaloneWorker()
    output_dir = tmp_path / "diagrams"
    renderer = StandaloneMermaidRenderer(str(output_dir), worker=worker)

    first = renderer.render_source("one")
    second = renderer.render_source("two")
    renderer.close()

    assert first == str((output_dir / "diagram_1.svg").resolve())
    assert second == str((output_dir / "diagram_2.svg").resolve())
    assert Path(first).read_text(encoding="utf-8").endswith("<text>one</text></svg>")
    assert Path(second).read_text(encoding="utf-8").endswith("<text>two</text></svg>")
    assert worker.calls == [
        ("one", mermaid_module._MERMAID_CONFIG),
        ("two", mermaid_module._MERMAID_CONFIG),
    ]
    assert worker.closed is True


@pytest.mark.parametrize(
    "error",
    [StandaloneRenderError("invalid"), StandaloneWorkerTimeoutError("timed out")],
)
def test_standalone_renderer_warns_and_preserves_fallback_on_diagram_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    renderer = StandaloneMermaidRenderer(
        str(tmp_path / "diagrams"), worker=_FakeStandaloneWorker(error)
    )

    assert renderer.render_source("broken") is None
    assert "Mermaid render failed for diagram 1" in capsys.readouterr().out
    assert not (tmp_path / "diagrams").exists()


def test_standalone_runtime_failure_is_not_silently_treated_as_a_bad_diagram(
    tmp_path: Path,
) -> None:
    renderer = StandaloneMermaidRenderer(
        str(tmp_path / "diagrams"),
        worker=_FakeStandaloneWorker(StandaloneRuntimeUnavailableError("runtime unavailable")),
    )

    with pytest.raises(MermaidBackendUnavailableError, match="runtime unavailable"):
        renderer.render_source("diagram")


def test_factory_constructs_standalone_only_after_full_runtime_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, str | None]] = []

    class RecordingRenderer:
        def __init__(self, output_dir: str) -> None:
            events.append(("renderer", output_dir))

        def render_source(self, source: str) -> str | None:
            return source

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        mermaid_module,
        "require_standalone_runtime",
        lambda: events.append(("preflight", None)),
    )
    monkeypatch.setattr(mermaid_module, "StandaloneMermaidRenderer", RecordingRenderer)
    output_dir = tmp_path / "diagrams"

    renderer = create_mermaid_renderer(
        MermaidBackend.STANDALONE,
        mmdc_bin="must-not-be-used",
        output_dir=str(output_dir),
    )

    assert isinstance(renderer, RecordingRenderer)
    assert events == [("preflight", None), ("renderer", str(output_dir))]
    assert not output_dir.exists()


def test_factory_reports_failed_standalone_preflight_without_creating_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> None:
        raise StandaloneRuntimeUnavailableError("requires mermaidx==0.9.5")

    monkeypatch.setattr(mermaid_module, "require_standalone_runtime", unavailable)
    output_dir = tmp_path / "diagrams"

    with pytest.raises(MermaidBackendUnavailableError, match=r"mermaidx==0\.9\.5"):
        create_mermaid_renderer(
            MermaidBackend.STANDALONE,
            mmdc_bin=None,
            output_dir=str(output_dir),
        )

    assert not output_dir.exists()
