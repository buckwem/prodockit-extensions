# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.metadata
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import pytest

from prodockit.pdf._standalone_quickjs import (
    QuickJSMermaidLimits,
    StandaloneRenderError,
    StandaloneResourceLimitError,
)
from prodockit.pdf._standalone_worker import StandaloneMermaidWorker
from prodockit.pdf.mermaid import StandaloneMermaidRenderer, render_mermaid_diagram

ROOT = Path(__file__).parents[1]
CORPUS_PATH = Path(__file__).parent / "fixtures" / "mermaid_standalone_corpus.json"


@dataclass(frozen=True)
class CorpusCase:
    identifier: str
    source: str
    expected_text: tuple[str, ...]


@dataclass(frozen=True)
class SvgSemantics:
    text: str
    graphic_elements: int


def _load_corpus() -> tuple[CorpusCase, ...]:
    raw = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    cases = tuple(
        CorpusCase(
            identifier=item["id"],
            source=item["source"],
            expected_text=tuple(item["expected_text"]),
        )
        for item in raw
    )
    assert len(cases) >= 12
    assert len({case.identifier for case in cases}) == len(cases)
    return cases


CORPUS = _load_corpus()


def test_corpus_manifest_covers_representative_diagram_families() -> None:
    identifiers = {case.identifier for case in CORPUS}
    assert {
        "flowchart-basic",
        "sequence",
        "class",
        "state",
        "entity-relationship",
        "gantt",
        "journey",
        "pie",
        "mindmap",
        "timeline",
        "requirement",
        "git-graph",
        "quadrant",
        "xy-chart",
        "packet",
    } <= identifiers


def _runtime_available() -> bool:
    try:
        return (
            importlib.metadata.version("quickjs-ng") == "0.16.2.1"
            and importlib.metadata.version("mermaidx") == "0.9.5"
        )
    except importlib.metadata.PackageNotFoundError:
        return False


@pytest.fixture(scope="module")
def worker() -> Iterator[StandaloneMermaidWorker]:
    if not _runtime_available():
        pytest.skip("requires the audited standalone Mermaid wheels")
    renderer = StandaloneMermaidWorker(
        QuickJSMermaidLimits(execution_time_seconds=10.0),
        hard_timeout_seconds=20.0,
    )
    yield renderer
    renderer.close()


def _semantics(svg: str, *, allow_foreign_object: bool = False) -> SvgSemantics:
    lowered = svg.lower()
    assert "<script" not in lowered
    assert "javascript:" not in lowered
    if not allow_foreign_object:
        assert "<foreignobject" not in lowered
    root = ElementTree.fromstring(svg)
    assert root.tag.rsplit("}", 1)[-1] == "svg"
    assert root.get("viewBox") or (root.get("width") and root.get("height"))
    assert all(
        not attribute.rsplit("}", 1)[-1].lower().startswith("on")
        for element in root.iter()
        for attribute in element.attrib
    )
    text = " ".join(" ".join(root.itertext()).split())
    graphic_elements = sum(
        element.tag.rsplit("}", 1)[-1] in {"circle", "ellipse", "line", "path", "polygon", "rect"}
        for element in root.iter()
    )
    assert graphic_elements > 0
    return SvgSemantics(text=text, graphic_elements=graphic_elements)


@pytest.mark.parametrize("case", CORPUS, ids=lambda case: case.identifier)
def test_standalone_worker_renders_representative_corpus(
    case: CorpusCase,
    worker: StandaloneMermaidWorker,
    tmp_path: Path,
) -> None:
    standalone = _semantics(worker.render_svg(case.source))
    for expected in case.expected_text:
        assert expected in standalone.text

    if os.environ.get("PRODOCKIT_RUN_MMDC_PARITY") != "1":
        return
    mmdc = Path(
        os.environ.get(
            "PRODOCKIT_MMDC_BIN",
            str(ROOT / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"),
        )
    )
    if not mmdc.is_file():
        pytest.skip("mmdc is required for the explicit parity run")
    rendered = render_mermaid_diagram(case.source, str(mmdc), str(tmp_path), 1, timeout=30)
    assert rendered is not None
    baseline = _semantics(
        Path(rendered).read_text(encoding="utf-8"),
        allow_foreign_object=True,
    )
    for expected in case.expected_text:
        assert expected in baseline.text
    assert standalone.graphic_elements > 0
    assert baseline.graphic_elements > 0


@pytest.mark.parametrize(
    "source",
    [
        "flowchart LR\n  A[Safe] --> B[Done]\n  click A \"javascript:alert(1)\"",
        "flowchart LR\n  A[\"</style><script>alert(1)</script>\"] --> B[Done]",
        "%%{init: {\"securityLevel\": \"loose\", \"flowchart\": {\"htmlLabels\": true}}}%%\n"
        "flowchart LR\n  A[\"<b onmouseover='alert(1)'>Unsafe</b>\"] --> B[Done]",
    ],
    ids=["javascript-link", "script-label", "loose-directive"],
)
def test_hostile_markup_cannot_escape_strict_svg(
    source: str,
    worker: StandaloneMermaidWorker,
) -> None:
    try:
        svg = worker.render_svg(source)
    except StandaloneRenderError:
        return
    _semantics(svg)


def test_malformed_render_does_not_poison_the_next_process(
    worker: StandaloneMermaidWorker,
) -> None:
    with pytest.raises(StandaloneRenderError):
        worker.render_svg("flowchart LR\n  A -->")

    semantics = _semantics(worker.render_svg("flowchart LR\n  A[Recovered] --> B[Safe]"))
    assert "Recovered" in semantics.text
    assert "Safe" in semantics.text


def test_child_output_limit_fails_closed_without_poisoning_worker() -> None:
    if not _runtime_available():
        pytest.skip("requires the audited standalone Mermaid wheels")
    worker = StandaloneMermaidWorker(
        QuickJSMermaidLimits(output_bytes=1024, execution_time_seconds=10.0),
        hard_timeout_seconds=20.0,
    )
    try:
        with pytest.raises(StandaloneResourceLimitError):
            worker.render_svg("flowchart LR\n  A[Large output] --> B[Rejected]")
    finally:
        worker.close()


def test_custom_css_is_data_not_executable_markup(
    worker: StandaloneMermaidWorker,
) -> None:
    svg = worker.render_svg(
        "flowchart LR\n  A[Styled] --> B[Safe]",
        css='</style><script>alert("css")</script><style>',
    )

    semantics = _semantics(svg)
    assert "Styled" in semantics.text
    assert "Safe" in semantics.text


def test_renderer_adapter_writes_svg_without_node_or_npm_on_path(
    worker: StandaloneMermaidWorker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")
    renderer = StandaloneMermaidRenderer(str(tmp_path / "diagrams"), worker=worker)

    rendered = renderer.render_source("flowchart LR\n  Python --> SVG")

    assert rendered is not None
    semantics = _semantics(Path(rendered).read_text(encoding="utf-8"))
    assert "Python" in semantics.text
    assert "SVG" in semantics.text
