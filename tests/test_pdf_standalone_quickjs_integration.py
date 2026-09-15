# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.metadata
import os

import pytest

from prodockit.pdf._standalone_quickjs import (
    QuickJSMermaidLimits,
    StandaloneQuickJSMermaidEngine,
)

if os.environ.get("PRODOCKIT_RUN_QUICKJS_SPIKE") != "1":
    pytest.skip("set PRODOCKIT_RUN_QUICKJS_SPIKE=1 for the audited-wheel spike", allow_module_level=True)

quickjs = pytest.importorskip("quickjs")
pytest.importorskip("mermaidx")

if importlib.metadata.version("quickjs-ng") != "0.16.2.1":
    pytest.skip("requires the audited quickjs-ng==0.16.2.1", allow_module_level=True)
if importlib.metadata.version("mermaidx") != "0.9.5":
    pytest.skip("requires the audited mermaidx==0.9.5", allow_module_level=True)


def test_quickjs_interrupt_limit_stops_an_infinite_loop() -> None:
    context = quickjs.Context()
    context.set_memory_limit(64 * 1024 * 1024)
    context.set_max_stack_size(128 * 1024)
    context.set_time_limit(0.02)

    with pytest.raises(quickjs.JSException, match="interrupted"):
        context.eval("while (true) {}")

    context.set_time_limit(1.0)
    assert context.eval("40 + 2") == 42


def test_quickjs_stack_limit_stops_deep_recursion() -> None:
    context = quickjs.Context()
    context.set_memory_limit(64 * 1024 * 1024)
    context.set_max_stack_size(64 * 1024)
    context.set_time_limit(1.0)

    with pytest.raises(quickjs.StackOverflow, match="call stack"):
        context.eval("function recurse() { return recurse(); } recurse();")


def test_quickjs_memory_limit_stops_excessive_allocation() -> None:
    context = quickjs.Context()
    context.set_memory_limit(2 * 1024 * 1024)
    context.set_max_stack_size(128 * 1024)
    context.set_time_limit(1.0)

    with pytest.raises(quickjs.JSException, match="out of memory"):
        context.eval("let a=[]; while(true) { a.push(new ArrayBuffer(65536)); }")


def test_callback_free_engine_renders_representative_mermaid() -> None:
    engine = StandaloneQuickJSMermaidEngine(
        QuickJSMermaidLimits(execution_time_seconds=10.0)
    )
    engine.start()
    try:
        svg = engine.render_svg("graph LR; A[Start] --> B[Done]")
    finally:
        engine.close()

    assert svg.startswith("<svg")
    assert "Start" in svg
    assert "Done" in svg
    assert "foreignObject" not in svg
