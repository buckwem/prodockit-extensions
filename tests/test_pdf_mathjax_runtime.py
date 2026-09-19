# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from prodockit.pdf import mathjax_runtime as runtime
from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_prepare import RuntimeEnvironment, RuntimeProviderUnavailableError
from prodockit.pdf.runtime_store import RuntimeStoreError


def _environment() -> RuntimeEnvironment:
    return RuntimeEnvironment("linux", "x86_64", "cpython", "3.14")


@pytest.mark.parametrize("policy", ["latest", "supported", runtime.MATHJAX_VERSION])
def test_provider_resolves_the_reviewed_prebuilt_release(policy: str) -> None:
    descriptor = runtime.MathJaxProvider().resolve(
        ComponentPolicy(policy), _environment()
    )

    assert descriptor.version == runtime.MATHJAX_VERSION
    assert descriptor.source_url == runtime.MATHJAX_ARCHIVE_URL
    assert descriptor.sha256 == runtime.MATHJAX_ARCHIVE_SHA256
    assert runtime.MATHJAX_COMPONENT.as_posix() in descriptor.expected_paths
    assert runtime.MATHJAX_LICENCE.as_posix() in descriptor.expected_paths


def test_provider_rejects_an_unreviewed_exact_version() -> None:
    with pytest.raises(RuntimeProviderUnavailableError, match=r"supports MathJax 4\.1\.3"):
        runtime.MathJaxProvider().resolve(ComponentPolicy("4.0.0"), _environment())


def test_probe_uses_packaged_adapter_and_cached_component(tmp_path: Path) -> None:
    root = tmp_path / runtime.MATHJAX_DIRECTORY
    root.mkdir(parents=True)
    (tmp_path / runtime.MATHJAX_COMPONENT).write_bytes(b"fixture")
    (tmp_path / runtime.MATHJAX_LICENCE).write_text("Apache-2.0\n", encoding="utf-8")
    calls: list[tuple[list[str], str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, str(kwargs["input"])))
        return subprocess.CompletedProcess(command, 0, "<svg></svg>", "")

    assert runtime.probe_runtime(tmp_path, runner=run, node="/usr/bin/node") == "4.1.3"
    assert len(calls) == 2
    assert calls[0][0] == [
        "/usr/bin/node",
        str(runtime.adapter_path()),
        str(root),
        "inline",
    ]
    assert calls[1][0][-1] == "display"


def test_probe_explains_that_node_but_not_npm_is_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / runtime.MATHJAX_DIRECTORY
    root.mkdir(parents=True)
    (tmp_path / runtime.MATHJAX_COMPONENT).write_bytes(b"fixture")
    (tmp_path / runtime.MATHJAX_LICENCE).write_text("Apache-2.0\n", encoding="utf-8")
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeStoreError, match=r"Node\.js on PATH; no npm packages"):
        runtime.probe_runtime(tmp_path)


def test_provider_refuses_changed_download_metadata(tmp_path: Path) -> None:
    descriptor = runtime.MathJaxProvider().resolve(ComponentPolicy("latest"), _environment())
    changed = type(descriptor)(**{**descriptor.__dict__, "sha256": "0" * 64})

    with pytest.raises(RuntimeStoreError, match="unreviewed MathJax"):
        runtime.MathJaxProvider().acquire(changed, tmp_path / "mathjax.zip")
