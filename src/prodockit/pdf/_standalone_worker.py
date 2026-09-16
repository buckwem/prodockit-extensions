# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Killable one-render-per-process boundary for default Mermaid rendering.

The parent exchanges bounded JSON bytes with a fresh spawned Python process,
so it never unpickles data returned by the renderer process.
"""

from __future__ import annotations

import json
import multiprocessing
import threading
from collections.abc import Callable
from dataclasses import asdict
from multiprocessing.connection import Connection
from typing import Any, Protocol, cast

from ._standalone_quickjs import (
    QuickJSMermaidLimits,
    StandaloneBackendUnavailableError,
    StandaloneQuickJSMermaidEngine,
    StandaloneRenderError,
    StandaloneResourceLimitError,
)

_PROTOCOL_VERSION = 1
_MAX_REQUEST_BYTES = 13 * 1024 * 1024
_MAX_RESPONSE_BYTES = 64 * 1024 * 1024 + 4096
_PROCESS_STOP_SECONDS = 1.0


class StandaloneWorkerTimeoutError(RuntimeError):
    """The parent stopped a renderer process at its hard deadline."""


class StandaloneWorkerCrashError(RuntimeError):
    """The renderer process exited without a valid response."""


class StandaloneWorkerProtocolError(RuntimeError):
    """The renderer process returned invalid or excessive protocol data."""


class _WorkerProcess(Protocol):
    exitcode: int | None

    def start(self) -> None: ...

    def is_alive(self) -> bool: ...

    def join(self, timeout: float | None = None) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def close(self) -> None: ...


class _WorkerContext(Protocol):
    def Pipe(self, duplex: bool = True) -> tuple[Connection, Connection]: ...

    def Process(
        self,
        *,
        target: Callable[..., None],
        args: tuple[Any, ...],
        daemon: bool | None = None,
    ) -> _WorkerProcess: ...


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _require_request_text(label: str, value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    if len(value.encode("utf-8")) > maximum:
        raise StandaloneResourceLimitError(f"{label} exceeds its size limit.")
    return value


def _decode_request(
    payload: bytes,
) -> tuple[str, str, dict[str, Any] | None, str | None, QuickJSMermaidLimits]:
    if len(payload) > _MAX_REQUEST_BYTES:
        raise ValueError("request is too large")
    value = json.loads(payload)
    if not isinstance(value, dict) or value.get("version") != _PROTOCOL_VERSION:
        raise ValueError("invalid request envelope")
    source = value.get("source")
    theme = value.get("theme")
    config = value.get("config")
    css = value.get("css")
    limits = value.get("limits")
    if not isinstance(source, str) or not isinstance(theme, str):
        raise ValueError("invalid request values")
    if config is not None and not isinstance(config, dict):
        raise ValueError("invalid configuration")
    if css is not None and not isinstance(css, str):
        raise ValueError("invalid CSS")
    if not isinstance(limits, dict):
        raise ValueError("invalid limits")
    return source, theme, config, css, QuickJSMermaidLimits(**limits)


def _error_response(kind: str) -> bytes:
    return _json_bytes({"version": _PROTOCOL_VERSION, "status": "error", "kind": kind})


def _worker_entry(send_connection: Connection, request_payload: bytes) -> None:
    """Runs in the spawned child; never returns exception details to its parent."""
    response = _error_response("worker")
    engine: StandaloneQuickJSMermaidEngine | None = None
    try:
        source, theme, config, css, limits = _decode_request(request_payload)
        engine = StandaloneQuickJSMermaidEngine(limits)
        engine.start()
        svg = engine.render_svg(source, theme=theme, config=config, css=css)
        candidate = _json_bytes(
            {"version": _PROTOCOL_VERSION, "status": "ok", "svg": svg}
        )
        response = (
            candidate
            if len(candidate) <= _MAX_RESPONSE_BYTES
            else _error_response("resource")
        )
    except StandaloneBackendUnavailableError:
        response = _error_response("unavailable")
    except StandaloneResourceLimitError:
        response = _error_response("resource")
    except StandaloneRenderError:
        response = _error_response("render")
    except (TypeError, ValueError, json.JSONDecodeError):
        response = _error_response("protocol")
    except BaseException:
        response = _error_response("worker")
    finally:
        if engine is not None:
            try:
                engine.close()
            except BaseException:
                response = _error_response("worker")
        try:
            send_connection.send_bytes(response)
        except (BrokenPipeError, EOFError, OSError):
            pass
        finally:
            send_connection.close()


def _stop_process(process: _WorkerProcess) -> None:
    if not process.is_alive():
        process.join(0)
        return
    process.terminate()
    process.join(_PROCESS_STOP_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(_PROCESS_STOP_SECONDS)


class StandaloneMermaidWorker:
    """Runs each render in a new spawn-context process with a hard deadline."""

    def __init__(
        self,
        limits: QuickJSMermaidLimits | None = None,
        *,
        hard_timeout_seconds: float = 15.0,
        context: _WorkerContext | None = None,
    ) -> None:
        if isinstance(hard_timeout_seconds, bool) or hard_timeout_seconds <= 0:
            raise ValueError("hard_timeout_seconds must be greater than zero")
        self._limits = limits or QuickJSMermaidLimits()
        self._hard_timeout_seconds = hard_timeout_seconds
        self._context = context or cast(_WorkerContext, multiprocessing.get_context("spawn"))
        self._lock = threading.Lock()
        self._stop_lock = threading.Lock()
        self._closed = False
        self._active_process: _WorkerProcess | None = None

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def close(self) -> None:
        with self._lock:
            self._closed = True
            process = self._active_process
        if process is not None:
            self._ensure_stopped(process)

    def render_svg(
        self,
        source: str,
        *,
        theme: str = "default",
        config: dict[str, Any] | None = None,
        css: str | None = None,
    ) -> str:
        source = _require_request_text("Mermaid source", source, self._limits.source_bytes)
        theme = _require_request_text("Mermaid theme", theme, self._limits.source_bytes)
        css = (
            None
            if css is None
            else _require_request_text("Mermaid CSS", css, self._limits.source_bytes)
        )
        if config is not None and not isinstance(config, dict):
            raise TypeError("Mermaid configuration must be a dictionary")
        if len(_json_bytes(config)) > self._limits.source_bytes:
            raise StandaloneResourceLimitError(
                "Mermaid configuration exceeds its size limit."
            )
        request = _json_bytes(
            {
                "version": _PROTOCOL_VERSION,
                "source": source,
                "theme": theme,
                "config": config,
                "css": css,
                "limits": asdict(self._limits),
            }
        )
        if len(request) > _MAX_REQUEST_BYTES:
            raise StandaloneResourceLimitError("Mermaid worker request exceeds its size limit.")

        receive_connection, send_connection = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=_worker_entry,
            args=(send_connection, request),
            daemon=False,
        )
        started = False
        try:
            with self._lock:
                if self._closed:
                    raise RuntimeError("The standalone Mermaid worker is closed.")
                if self._active_process is not None:
                    raise RuntimeError("The standalone Mermaid worker is already rendering.")
                self._active_process = process
                process.start()
                started = True

            send_connection.close()
            if not receive_connection.poll(self._hard_timeout_seconds):
                self._ensure_stopped(process)
                raise StandaloneWorkerTimeoutError(
                    "The standalone Mermaid worker exceeded its hard timeout."
                )
            try:
                response = receive_connection.recv_bytes(_MAX_RESPONSE_BYTES)
            except OSError as exc:
                self._ensure_stopped(process)
                raise StandaloneWorkerProtocolError(
                    "The standalone Mermaid worker response exceeded its size limit."
                ) from exc
            except EOFError as exc:
                process.join(_PROCESS_STOP_SECONDS)
                raise StandaloneWorkerCrashError(
                    "The standalone Mermaid worker exited without a response."
                ) from exc
            process.join(_PROCESS_STOP_SECONDS)
            if process.is_alive():
                self._ensure_stopped(process)
                raise StandaloneWorkerCrashError(
                    "The standalone Mermaid worker did not exit cleanly."
                )
            if process.exitcode != 0:
                raise StandaloneWorkerCrashError(
                    "The standalone Mermaid worker exited unexpectedly."
                )
            return self._decode_response(response)
        finally:
            receive_connection.close()
            send_connection.close()
            if started or process.is_alive():
                self._ensure_stopped(process)
            process.close()
            with self._lock:
                if self._active_process is process:
                    self._active_process = None

    def _ensure_stopped(self, process: _WorkerProcess) -> None:
        with self._stop_lock:
            _stop_process(process)

    @staticmethod
    def _decode_response(payload: bytes) -> str:
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StandaloneWorkerProtocolError(
                "The standalone Mermaid worker returned malformed data."
            ) from exc
        if not isinstance(value, dict) or value.get("version") != _PROTOCOL_VERSION:
            raise StandaloneWorkerProtocolError(
                "The standalone Mermaid worker returned an invalid envelope."
            )
        status = value.get("status")
        svg = value.get("svg")
        if status == "ok" and isinstance(svg, str):
            return svg
        if status != "error" or not isinstance(value.get("kind"), str):
            raise StandaloneWorkerProtocolError(
                "The standalone Mermaid worker returned an invalid result."
            )
        kind = value["kind"]
        if kind == "unavailable":
            raise StandaloneBackendUnavailableError(
                "The standalone Mermaid runtime is unavailable in the worker."
            )
        if kind == "resource":
            raise StandaloneResourceLimitError(
                "The standalone Mermaid worker reached a resource limit."
            )
        if kind == "render":
            raise StandaloneRenderError("Mermaid rendering failed in the worker.")
        if kind == "worker":
            raise StandaloneWorkerCrashError("The standalone Mermaid worker failed internally.")
        raise StandaloneWorkerProtocolError(
            "The standalone Mermaid worker returned an unknown error kind."
        )
