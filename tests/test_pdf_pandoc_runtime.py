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
    unsupported = RuntimeEnvironment("windows", "arm64", "cpython", "3.14")

    with pytest.raises(RuntimeProviderUnavailableError, match=r"supports Pandoc 3\.10\.1"):
        runtime.PandocProvider().resolve(ComponentPolicy("3.9.0"), supported)
    with pytest.raises(RuntimeProviderUnavailableError, match="no qualified artifact"):
        runtime.PandocProvider().resolve(ComponentPolicy("supported"), unsupported)


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
