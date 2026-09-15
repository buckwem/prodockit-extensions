# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.metadata
import os
from typing import Any

import pytest

import prodockit.pdf._standalone_worker as worker_module
from prodockit.pdf._standalone_quickjs import (
    QuickJSMermaidLimits,
    StandaloneBackendUnavailableError,
    StandaloneRenderError,
    StandaloneResourceLimitError,
)
from prodockit.pdf._standalone_worker import (
    StandaloneMermaidWorker,
    StandaloneWorkerCrashError,
    StandaloneWorkerProtocolError,
    StandaloneWorkerTimeoutError,
)


class FakeReceiveConnection:
    def __init__(self, response: bytes | BaseException, *, ready: bool = True) -> None:
        self.response = response
        self.ready = ready
        self.closed = False

    def poll(self, _timeout: float) -> bool:
        return self.ready

    def recv_bytes(self, _maxlength: int | None = None) -> bytes:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    def close(self) -> None:
        self.closed = True


class FakeSendConnection:
    def __init__(self) -> None:
        self.closed = False
        self.sent: list[bytes] = []

    def send_bytes(self, payload: bytes) -> None:
        self.sent.append(payload)

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(
        self,
        *,
        exitcode: int | None = 0,
        alive_after_join: bool = False,
        ignore_terminate: bool = False,
        start_error: BaseException | None = None,
    ) -> None:
        self.exitcode = exitcode
        self.alive = False
        self.alive_after_join = alive_after_join
        self.ignore_terminate = ignore_terminate
        self.start_error = start_error
        self.started = False
        self.terminate_calls = 0
        self.kill_calls = 0
        self.closed = False

    def start(self) -> None:
        if self.start_error is not None:
            raise self.start_error
        self.started = True
        self.alive = True

    def is_alive(self) -> bool:
        return self.alive

    def join(self, _timeout: float | None = None) -> None:
        self.alive = self.alive_after_join

    def terminate(self) -> None:
        self.terminate_calls += 1
        if not self.ignore_terminate:
            self.alive = False
            self.alive_after_join = False

    def kill(self) -> None:
        self.kill_calls += 1
        self.alive = False
        self.alive_after_join = False

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(
        self,
        response: bytes | BaseException,
        *,
        ready: bool = True,
        process: FakeProcess | None = None,
    ) -> None:
        self.receive = FakeReceiveConnection(response, ready=ready)
        self.send = FakeSendConnection()
        self.process = process or FakeProcess()
        self.target: Any = None
        self.args: tuple[Any, ...] = ()

    def Pipe(self, duplex: bool = True) -> tuple[Any, Any]:
        assert duplex is False
        return self.receive, self.send

    def Process(
        self,
        *,
        target: Any,
        args: tuple[Any, ...],
        daemon: bool | None = None,
    ) -> FakeProcess:
        assert daemon is False
        self.target = target
        self.args = args
        return self.process


def _response(**values: object) -> bytes:
    return worker_module._json_bytes({"version": 1, **values})


def test_worker_returns_svg_and_reaps_the_process() -> None:
    context = FakeContext(_response(status="ok", svg="<svg/>"))
    worker = StandaloneMermaidWorker(context=context)

    assert worker.render_svg("graph LR; A-->B") == "<svg/>"
    assert context.process.started
    assert context.process.closed
    assert not context.process.is_alive()
    assert context.receive.closed
    assert context.send.closed


def test_hard_timeout_terminates_the_worker_without_a_leak() -> None:
    context = FakeContext(b"", ready=False)
    worker = StandaloneMermaidWorker(context=context, hard_timeout_seconds=0.01)

    with pytest.raises(StandaloneWorkerTimeoutError, match="hard timeout"):
        worker.render_svg("graph LR; A-->B")

    assert context.process.terminate_calls == 1
    assert context.process.kill_calls == 0
    assert context.process.closed
    assert not context.process.is_alive()


def test_stubborn_worker_is_killed_after_terminate_grace() -> None:
    process = FakeProcess(alive_after_join=True, ignore_terminate=True)
    context = FakeContext(b"", ready=False, process=process)
    worker = StandaloneMermaidWorker(context=context, hard_timeout_seconds=0.01)

    with pytest.raises(StandaloneWorkerTimeoutError):
        worker.render_svg("graph LR; A-->B")

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert not process.is_alive()


def test_worker_exit_without_response_is_a_crash() -> None:
    context = FakeContext(EOFError(), process=FakeProcess(exitcode=9))
    worker = StandaloneMermaidWorker(context=context)

    with pytest.raises(StandaloneWorkerCrashError, match="without a response"):
        worker.render_svg("graph LR; A-->B")

    assert not context.process.is_alive()
    assert context.process.closed


def test_process_start_failure_closes_every_parent_resource() -> None:
    process = FakeProcess(start_error=OSError("spawn failed"))
    context = FakeContext(b"", process=process)
    worker = StandaloneMermaidWorker(context=context)

    with pytest.raises(OSError, match="spawn failed"):
        worker.render_svg("graph LR; A-->B")

    assert context.receive.closed
    assert context.send.closed
    assert process.closed
    assert not process.is_alive()


@pytest.mark.parametrize(
    "response",
    [b"not json", b"[]", _response(status="wat"), _response(status="error", kind="new")],
)
def test_malformed_response_fails_as_a_protocol_error(response: bytes) -> None:
    worker = StandaloneMermaidWorker(context=FakeContext(response))

    with pytest.raises(StandaloneWorkerProtocolError):
        worker.render_svg("graph LR; A-->B")


def test_oversized_response_fails_as_a_protocol_error() -> None:
    context = FakeContext(OSError("bad message length"))
    worker = StandaloneMermaidWorker(context=context)

    with pytest.raises(StandaloneWorkerProtocolError, match="size limit"):
        worker.render_svg("graph LR; A-->B")

    assert context.process.terminate_calls == 1
    assert not context.process.is_alive()


@pytest.mark.parametrize(
    ("kind", "error_type"),
    [
        ("unavailable", StandaloneBackendUnavailableError),
        ("resource", StandaloneResourceLimitError),
        ("render", StandaloneRenderError),
        ("worker", StandaloneWorkerCrashError),
    ],
)
def test_typed_child_errors_are_preserved(kind: str, error_type: type[Exception]) -> None:
    worker = StandaloneMermaidWorker(
        context=FakeContext(_response(status="error", kind=kind))
    )

    with pytest.raises(error_type):
        worker.render_svg("graph LR; A-->B")


def test_close_is_idempotent_and_prevents_new_processes() -> None:
    context = FakeContext(_response(status="ok", svg="<svg/>"))
    worker = StandaloneMermaidWorker(context=context)

    worker.close()
    worker.close()

    assert worker.closed
    with pytest.raises(RuntimeError, match="closed"):
        worker.render_svg("graph LR; A-->B")
    assert not context.process.started
    assert context.receive.closed
    assert context.send.closed


def test_parent_rejects_oversized_source_before_spawning() -> None:
    context = FakeContext(_response(status="ok", svg="<svg/>"))
    worker = StandaloneMermaidWorker(
        QuickJSMermaidLimits(source_bytes=4),
        context=context,
    )

    with pytest.raises(StandaloneResourceLimitError, match="source"):
        worker.render_svg("12345")

    assert not context.process.started


class RecordingEngine:
    error: BaseException | None = None
    closed = False

    def __init__(self, _limits: QuickJSMermaidLimits) -> None:
        type(self).closed = False

    def start(self) -> None:
        if self.error is not None:
            raise self.error

    def render_svg(self, *_args: Any, **_kwargs: Any) -> str:
        return "<svg>safe</svg>"

    def close(self) -> None:
        type(self).closed = True


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (StandaloneBackendUnavailableError("secret path"), "unavailable"),
        (StandaloneResourceLimitError("secret input"), "resource"),
        (StandaloneRenderError("secret source"), "render"),
        (RuntimeError("secret traceback"), "worker"),
    ],
)
def test_child_maps_errors_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    kind: str,
) -> None:
    RecordingEngine.error = error
    connection = FakeSendConnection()
    monkeypatch.setattr(worker_module, "StandaloneQuickJSMermaidEngine", RecordingEngine)
    request = worker_module._json_bytes(
        {
            "version": 1,
            "source": "graph LR; A-->B",
            "theme": "default",
            "config": None,
            "css": None,
            "limits": worker_module.asdict(QuickJSMermaidLimits()),
        }
    )

    worker_module._worker_entry(connection, request)

    assert len(connection.sent) == 1
    response_text = connection.sent[0].decode("utf-8")
    assert worker_module.json.loads(response_text)["kind"] == kind
    assert "secret" not in response_text
    assert connection.closed
    assert RecordingEngine.closed


def test_spawned_worker_renders_with_exact_audited_wheels() -> None:
    if os.environ.get("PRODOCKIT_RUN_QUICKJS_SPIKE") != "1":
        pytest.skip("set PRODOCKIT_RUN_QUICKJS_SPIKE=1 for the audited-wheel spike")
    if importlib.metadata.version("quickjs-ng") != "0.16.2.1":
        pytest.skip("requires audited quickjs-ng==0.16.2.1")
    if importlib.metadata.version("mermaidx") != "0.9.5":
        pytest.skip("requires audited mermaidx==0.9.5")
    worker = StandaloneMermaidWorker(
        QuickJSMermaidLimits(execution_time_seconds=10.0),
        hard_timeout_seconds=20.0,
    )
    try:
        svg = worker.render_svg("graph LR; A[Start] --> B[Done]")
    finally:
        worker.close()

    assert svg.startswith("<svg")
    assert "Start" in svg
    assert "Done" in svg
    assert "foreignObject" not in svg
