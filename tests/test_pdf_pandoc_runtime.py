# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from prodockit.pdf import pandoc_runtime as runtime
from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_prepare import RuntimeEnvironment, RuntimeProviderUnavailableError


@pytest.mark.parametrize(
    ("system", "architecture", "suffix"),
    [
        ("darwin", "arm64", "pandoc-3.10.1-arm64/bin/pandoc"),
        ("darwin", "x86_64", "pandoc-3.10.1-x86_64/bin/pandoc"),
        ("linux", "aarch64", "pandoc-3.10.1/bin/pandoc"),
        ("linux", "x86_64", "pandoc-3.10.1/bin/pandoc"),
        ("windows", "amd64", "pandoc-3.10.1/pandoc.exe"),
        ("windows", "arm64", "pandoc-3.10.1/pandoc.exe"),
        ("windows", "aarch64", "pandoc-3.10.1/pandoc.exe"),
    ],
)
def test_provider_resolves_reviewed_platform_assets(
    system: str, architecture: str, suffix: str
) -> None:
    environment = RuntimeEnvironment(system, architecture, "cpython", "3.14")

    descriptor = runtime.PandocProvider().resolve(ComponentPolicy("supported"), environment)

    assert descriptor.version == runtime.PANDOC_VERSION
    assert descriptor.source_url.startswith("https://github.com/jgm/pandoc/releases/download/")
    assert len(descriptor.sha256) == 64
    assert descriptor.expected_paths == (suffix,)
    if system == "windows":
        assert descriptor.ignored_link_paths == ()
    else:
        assert len(descriptor.ignored_link_paths) == 2


def test_provider_rejects_unqualified_version_and_host() -> None:
    supported = RuntimeEnvironment("linux", "x86_64", "cpython", "3.14")
    unsupported = RuntimeEnvironment("freebsd", "arm64", "cpython", "3.14")

    with pytest.raises(RuntimeProviderUnavailableError, match=r"supports Pandoc 3\.10\.1"):
        runtime.PandocProvider().resolve(ComponentPolicy("3.9.0"), supported)
    with pytest.raises(RuntimeProviderUnavailableError, match="no qualified artifact"):
        runtime.PandocProvider().resolve(ComponentPolicy("supported"), unsupported)


@pytest.mark.parametrize("architecture", ["arm64", "aarch64"])
def test_windows_arm64_reuses_the_reviewed_x64_artifact(architecture: str) -> None:
    x64 = RuntimeEnvironment("windows", "amd64", "cpython", "3.14")
    arm64 = RuntimeEnvironment("windows", architecture, "cpython", "3.14")

    x64_descriptor = runtime.PandocProvider().resolve(ComponentPolicy("supported"), x64)
    arm64_descriptor = runtime.PandocProvider().resolve(ComponentPolicy("supported"), arm64)

    assert arm64_descriptor.source_url == x64_descriptor.source_url
    assert arm64_descriptor.sha256 == x64_descriptor.sha256
    assert arm64_descriptor.expected_paths == x64_descriptor.expected_paths
    assert arm64_descriptor.architecture == architecture
    assert arm64_descriptor.environment_identity == f"windows:{architecture}:cpython:3.14"


def test_probe_uses_absolute_executable_and_exercises_citeproc(tmp_path: Path) -> None:
    environment = RuntimeEnvironment("linux", "x86_64", "cpython", "3.14")
    executable = tmp_path / "pandoc-3.10.1/bin/pandoc"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture")
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "pandoc 3.10.1\n", "")
        return subprocess.CompletedProcess(
            command,
            0,
            '<div id="refs"><div>Runtime Probe</div></div>',
            "",
        )

    assert runtime.probe_runtime(tmp_path, environment, runner=run) == "3.10.1"
    assert calls[0][0] == str(executable)
    assert calls[1][0] == str(executable)
    assert "--citeproc" in calls[1]


def test_windows_arm64_probe_explains_the_x64_emulation_requirement(tmp_path: Path) -> None:
    environment = RuntimeEnvironment("windows", "arm64", "cpython", "3.14")
    executable = tmp_path / "pandoc-3.10.1/pandoc.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture")

    def fail_to_start(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("not a valid application")

    with pytest.raises(
        runtime.RuntimeStoreError,
        match="Windows ARM64 requires the Windows 11 x64 app emulation component",
    ):
        runtime.probe_runtime(tmp_path, environment, runner=fail_to_start)
