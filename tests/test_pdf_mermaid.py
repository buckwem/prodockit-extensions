# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

import prodockit.pdf.mermaid as mermaid_module
from prodockit.pdf._standalone_quickjs import (
    StandaloneBackendUnavailableError as StandaloneRuntimeUnavailableError,
)
from prodockit.pdf._standalone_quickjs import (
    StandaloneRenderError,
    StandaloneResourceLimitError,
)
from prodockit.pdf._standalone_worker import (
    StandaloneWorkerCrashError,
    StandaloneWorkerProtocolError,
    StandaloneWorkerTimeoutError,
)
from prodockit.pdf.mermaid import (
    MermaidBackendUnavailableError,
    MermaidOutputError,
    MermaidRenderError,
    StandaloneMermaidRenderer,
    create_mermaid_renderer,
)


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


def test_standalone_renderer_rejects_symlink_output_without_changing_target(
    tmp_path: Path,
) -> None:
    worker = _FakeStandaloneWorker()
    output_dir = tmp_path / "project" / "docs" / ".prodockit-pdf-mermaid"
    output_dir.mkdir(parents=True)
    external = tmp_path / "external-canary"
    external.write_text("TRULY_OUTSIDE_PROJECT_CANARY\n", encoding="utf-8")
    output = output_dir / "diagram_1.svg"
    try:
        output.symlink_to(external)
    except OSError:
        pytest.skip("creating symlinks is not permitted on this platform")
    renderer = StandaloneMermaidRenderer(str(output_dir), worker=worker)

    with pytest.raises(MermaidOutputError, match="output is a symbolic link"):
        renderer.render_source("one")

    assert output.is_symlink()
    assert external.read_text(encoding="utf-8") == "TRULY_OUTSIDE_PROJECT_CANARY\n"
    assert worker.calls == []


def test_standalone_renderer_rejects_symlinked_output_directory(tmp_path: Path) -> None:
    worker = _FakeStandaloneWorker()
    external = tmp_path / "external"
    external.mkdir()
    output_dir = tmp_path / "project" / "docs" / ".prodockit-pdf-mermaid"
    output_dir.parent.mkdir(parents=True)
    try:
        output_dir.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks is not permitted on this platform")
    renderer = StandaloneMermaidRenderer(str(output_dir), worker=worker)

    with pytest.raises(MermaidOutputError, match="directory contains a symbolic link"):
        renderer.render_source("one")

    assert list(external.iterdir()) == []
    assert worker.calls == []


@pytest.mark.parametrize(
    ("error", "diagnostic"),
    [
        (StandaloneRenderError("untrusted diagram source"), "rejected the diagram"),
        (StandaloneResourceLimitError("untrusted diagram source"), "resource limit"),
        (StandaloneWorkerTimeoutError("untrusted diagram source"), "time limit"),
        (StandaloneWorkerCrashError("untrusted diagram source"), "exited unexpectedly"),
        (StandaloneWorkerProtocolError("untrusted diagram source"), "invalid data"),
        (OSError("untrusted diagram source"), "could not be written"),
    ],
)
def test_standalone_renderer_raises_safe_typed_diagram_failure(
    tmp_path: Path,
    error: Exception,
    diagnostic: str,
) -> None:
    renderer = StandaloneMermaidRenderer(
        str(tmp_path / "diagrams"), worker=_FakeStandaloneWorker(error)
    )

    with pytest.raises(MermaidRenderError) as caught:
        renderer.render_source("untrusted diagram source")

    message = str(caught.value)
    assert "Mermaid diagram 1 could not be rendered" in message
    assert diagnostic in message
    assert "untrusted diagram source" not in message
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

        def render_source(self, source: str) -> str:
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

    renderer = create_mermaid_renderer(output_dir=str(output_dir))

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
            output_dir=str(output_dir),
        )

    assert not output_dir.exists()
