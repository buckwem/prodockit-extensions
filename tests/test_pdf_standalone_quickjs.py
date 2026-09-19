# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Any

import pytest

import prodockit.pdf._standalone_quickjs as runtime_module
from prodockit.pdf._standalone_quickjs import (
    QuickJSMermaidLimits,
    StandaloneBackendUnavailableError,
    StandaloneQuickJSMermaidEngine,
    StandaloneRenderError,
    StandaloneResourceLimitError,
    StandaloneStackLimitError,
)


class FakeContext:
    def __init__(self, svg: str = "<svg/>", error: str | None = None) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.values: dict[str, Any] = {}
        self.svg = svg
        self.error = error

    def set_memory_limit(self, limit: int) -> None:
        self.calls.append(("memory", limit))

    def set_max_stack_size(self, limit: int) -> None:
        self.calls.append(("stack", limit))

    def set_time_limit(self, limit: float) -> None:
        self.calls.append(("time", limit))

    def set(self, name: str, value: Any) -> None:
        self.calls.append(("set", name, value))
        self.values[name] = value

    def eval(self, source: str) -> Any:
        self.calls.append(("eval", source))
        if source == "!!globalThis.__renderResult || !!globalThis.__renderError":
            return True
        if source == "globalThis.__renderError":
            return self.error
        if source == "globalThis.__renderResult":
            return self.svg
        return None

    def execute_pending_job(self) -> bool:
        self.calls.append(("job",))
        return False

    def add_callable(self, *_args: Any) -> None:
        raise AssertionError("Python callbacks are forbidden")


def _fake_runtime(context: FakeContext) -> runtime_module._Runtime:
    return runtime_module._Runtime(
        context_factory=lambda: context,
        dom_shim_js="dom shim",
        mermaid_js="mermaid bundle",
        measure_text_js="glyph tables",
        path_bbox_js="path geometry",
        patch_svg=lambda svg: svg,
    )


def test_engine_configures_all_three_quickjs_limits_before_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = FakeContext()
    limits = QuickJSMermaidLimits(
        memory_bytes=64 * 1024 * 1024,
        maximum_stack_bytes=128 * 1024,
        execution_time_seconds=2.0,
    )
    monkeypatch.setattr(runtime_module, "_load_runtime", lambda: _fake_runtime(context))
    engine = StandaloneQuickJSMermaidEngine(limits)

    engine.start()
    assert context.calls[:2] == [
        ("memory", limits.memory_bytes),
        ("stack", limits.maximum_stack_bytes),
    ]
    assert not any(call[0] == "time" for call in context.calls)

    assert engine.render_svg("graph LR; A-->B") == "<svg/>"
    assert any(call[0] == "time" for call in context.calls)


def test_engine_passes_untrusted_values_with_context_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = FakeContext()
    monkeypatch.setattr(runtime_module, "_load_runtime", lambda: _fake_runtime(context))
    engine = StandaloneQuickJSMermaidEngine()
    engine.start()

    source = 'graph LR; A["quoted"]-->B'
    css = '.node::after { content: "quoted"; }'
    engine.render_svg(source, theme="dark", config={"flowchart": {"curve": "basis"}}, css=css)

    assert context.values["__code"] == source
    assert context.values["__css"] == css
    assert context.values["__renderId"] == "pdk1"
    config = runtime_module.json.loads(context.values["__config"])
    assert config["theme"] == "dark"
    assert config["flowchart"] == {"curve": "basis", "htmlLabels": False}
    assert config["htmlLabels"] is False
    assert config["securityLevel"] == "strict"
    eval_sources = [call[1] for call in context.calls if call[0] == "eval"]
    assert all(source not in script and css not in script for script in eval_sources)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("memory_bytes", 1),
        ("maximum_stack_bytes", 1),
        ("execution_time_seconds", 0),
        ("promise_jobs", 0),
        ("source_bytes", 0),
        ("output_bytes", 0),
    ],
)
def test_limits_reject_unsafe_values(field: str, value: int) -> None:
    with pytest.raises(ValueError, match=field):
        QuickJSMermaidLimits(**{field: value})


def test_default_stack_limit_uses_the_approved_one_mebibyte_ceiling() -> None:
    assert QuickJSMermaidLimits().maximum_stack_bytes == 1024 * 1024


def test_mermaid_stack_exhaustion_is_a_resource_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = FakeContext(error="RangeError: Maximum call stack size exceeded")
    monkeypatch.setattr(runtime_module, "_load_runtime", lambda: _fake_runtime(context))
    engine = StandaloneQuickJSMermaidEngine()
    engine.start()

    with pytest.raises(StandaloneStackLimitError, match="stack limit"):
        engine.render_svg("flowchart TD\n N0 --> N1")


def test_source_and_output_limits_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    context = FakeContext(svg="<svg>too large</svg>")
    monkeypatch.setattr(runtime_module, "_load_runtime", lambda: _fake_runtime(context))
    source_limited_engine = StandaloneQuickJSMermaidEngine(
        QuickJSMermaidLimits(source_bytes=4)
    )
    source_limited_engine.start()

    with pytest.raises(ValueError, match="source"):
        source_limited_engine.render_svg("12345")

    context.svg = "x" * 1025
    output_limited_engine = StandaloneQuickJSMermaidEngine(
        QuickJSMermaidLimits(output_bytes=1024)
    )
    output_limited_engine.start()
    with pytest.raises(StandaloneResourceLimitError, match="output"):
        output_limited_engine.render_svg("1234")


@pytest.mark.parametrize(
    "svg",
    [
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><g onmouseover="alert(1)"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.test/a"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><style>.x{fill:url(https://example.test)}</style></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
        '<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>',
        "not svg",
    ],
)
def test_engine_rejects_active_or_external_svg(
    monkeypatch: pytest.MonkeyPatch,
    svg: str,
) -> None:
    context = FakeContext(svg=svg)
    monkeypatch.setattr(runtime_module, "_load_runtime", lambda: _fake_runtime(context))
    engine = StandaloneQuickJSMermaidEngine()
    engine.start()

    with pytest.raises(StandaloneRenderError):
        engine.render_svg("graph LR; A-->B")


def test_runtime_rejects_missing_or_wrong_dependency_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_name: str) -> str:
        raise runtime_module.importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(runtime_module.importlib.metadata, "version", missing)
    with pytest.raises(StandaloneBackendUnavailableError, match=r"mermaidx==0\.9\.5"):
        runtime_module._load_runtime()

    monkeypatch.setattr(runtime_module.importlib.metadata, "version", lambda _name: "999")
    with pytest.raises(StandaloneBackendUnavailableError, match="found 999"):
        runtime_module._load_runtime()


def test_promise_job_limit_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    context = FakeContext()
    limits = QuickJSMermaidLimits(promise_jobs=1)
    monkeypatch.setattr(runtime_module, "_load_runtime", lambda: _fake_runtime(context))
    engine = StandaloneQuickJSMermaidEngine(limits)
    engine.start()
    context.eval = lambda _source: False
    context.execute_pending_job = lambda: True

    with pytest.raises(StandaloneResourceLimitError, match="Promise-job"):
        engine.render_svg("graph LR; A-->B")
