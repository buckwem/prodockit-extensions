# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import subprocess
import zipfile
from pathlib import Path

import pytest

from prodockit.pdf import weasyprint_runtime as runtime
from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_prepare import (
    RuntimeEnvironment,
    RuntimeProviderUnavailableError,
    prepare_windows_weasyprint_runtime,
)
from prodockit.pdf.runtime_store import ArtifactDescriptor, RuntimeStoreError


def _environment(*, architecture: str = "amd64") -> RuntimeEnvironment:
    return RuntimeEnvironment("windows", architecture, "cpython", "3.14")


def test_provider_resolves_only_the_reviewed_windows_x64_release() -> None:
    descriptor = runtime.WindowsWeasyPrintProvider().resolve(
        ComponentPolicy("supported"), _environment()
    )

    assert descriptor.version == "70.0"
    assert descriptor.source_url == runtime.WEASYPRINT_ASSET_URL
    assert descriptor.sha256 == runtime.WEASYPRINT_ASSET_SHA256
    assert descriptor.expected_paths == (
        "onedir/weasyprint/weasyprint.exe",
        "LICENSE",
    )


@pytest.mark.parametrize(
    ("policy", "environment", "message"),
    [
        (ComponentPolicy("69.0"), _environment(), "supports WeasyPrint 70.0"),
        (ComponentPolicy("supported"), _environment(architecture="arm64"), "Windows x64 only"),
    ],
)
def test_provider_rejects_unqualified_versions_and_architectures(
    policy: ComponentPolicy,
    environment: RuntimeEnvironment,
    message: str,
) -> None:
    with pytest.raises(RuntimeProviderUnavailableError, match=message):
        runtime.WindowsWeasyPrintProvider().resolve(policy, environment)


def test_download_is_bounded_to_the_reviewed_size_and_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"reviewed fixture"

    class Response:
        def __init__(self) -> None:
            self._read = False
            self.headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return runtime.WEASYPRINT_ASSET_URL

        def read(self, _size: int) -> bytes:
            if self._read:
                return b""
            self._read = True
            return payload

    monkeypatch.setattr(runtime, "WEASYPRINT_ASSET_BYTES", len(payload))
    monkeypatch.setattr(runtime, "_open_download", lambda _request, _timeout: Response())
    destination = tmp_path / "artifact.zip"

    runtime._download_official_artifact(runtime.WEASYPRINT_ASSET_URL, destination)

    assert destination.read_bytes() == payload
    with pytest.raises(RuntimeStoreError, match="unapproved"):
        runtime._download_official_artifact("https://example.invalid/runtime.zip", destination)


def test_probe_uses_the_absolute_executable_and_renders_a_pdf(tmp_path: Path) -> None:
    executable = tmp_path / runtime.WEASYPRINT_EXECUTABLE
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture")
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "WeasyPrint version 70.0\n", "")
        Path(command[-1]).write_bytes(b"%PDF-1.7 fixture")
        return subprocess.CompletedProcess(command, 0, "", "")

    assert runtime.probe_runtime(tmp_path, runner=run) == "70.0"
    assert calls[0][0] == str(executable)
    assert calls[1][0] == str(executable)


class _FixtureProvider:
    def __init__(self, archive: Path, environment: RuntimeEnvironment) -> None:
        self.archive = archive
        self.environment = environment

    def resolve(
        self, _policy: ComponentPolicy, environment: RuntimeEnvironment
    ) -> ArtifactDescriptor:
        assert environment == self.environment
        return ArtifactDescriptor(
            component="weasyprint",
            version="70.0",
            source_url="https://example.invalid/weasyprint.zip",
            sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            licence="BSD-3-Clause",
            provenance="local G3 fixture",
            platform=environment.system,
            architecture=environment.architecture,
            environment_identity=environment.identity,
            archive_format="zip",
            expected_paths=(runtime.WEASYPRINT_EXECUTABLE.as_posix(), "LICENSE"),
        )

    def acquire(self, _descriptor: ArtifactDescriptor, destination: Path) -> None:
        destination.write_bytes(self.archive.read_bytes())

    def probe(self, _descriptor: ArtifactDescriptor, prepared: Path) -> None:
        assert runtime.executable_in_runtime(prepared).read_bytes() == b"fixture"


def test_windows_preparation_returns_the_validated_project_runtime(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config = project / "zensical.toml"
    config.write_text("[project]\n", encoding="utf-8")
    archive = tmp_path / "weasyprint.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(runtime.WEASYPRINT_EXECUTABLE.as_posix(), b"fixture")
        bundle.writestr("LICENSE", b"BSD-3-Clause")
    environment = _environment()
    provider = _FixtureProvider(archive, environment)

    prepared = prepare_windows_weasyprint_runtime(
        config,
        providers={"weasyprint": provider},
        environment=environment,
    )

    assert prepared is not None
    assert prepared.cached is False
    assert runtime.executable_in_runtime(prepared.path).read_bytes() == b"fixture"


def test_non_windows_preparation_keeps_the_existing_system_runtime(tmp_path: Path) -> None:
    environment = RuntimeEnvironment("darwin", "arm64", "cpython", "3.14")

    assert (
        prepare_windows_weasyprint_runtime(
            tmp_path / "zensical.toml", environment=environment
        )
        is None
    )
    assert not (tmp_path / ".prodockit").exists()
