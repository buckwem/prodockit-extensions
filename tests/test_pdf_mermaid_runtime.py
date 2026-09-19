# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from prodockit.pdf import mermaid_runtime as runtime
from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_prepare import RuntimeEnvironment, RuntimeProviderUnavailableError
from prodockit.pdf.runtime_store import RuntimeStoreError, sha256_file


def _environment(system: str = "linux", architecture: str = "x86_64") -> RuntimeEnvironment:
    return RuntimeEnvironment(system, architecture, "cpython", "3.14")


@pytest.mark.parametrize("policy", ["latest", "supported", runtime.MERMAID_RUNTIME_VERSION])
def test_provider_resolves_reviewed_composite(policy: str) -> None:
    descriptor = runtime.MermaidProvider().resolve(
        ComponentPolicy(policy), _environment()
    )

    assert descriptor.version == "0.9.5"
    assert descriptor.sha256 == runtime._RUNTIME_SHA256["linux-x86_64"]
    assert "mermaidx-0.9.5" in descriptor.provenance
    assert "site-packages/mermaidx/assets/mermaid.js" in descriptor.expected_paths


@pytest.mark.parametrize(
    ("system", "architecture", "key"),
    [
        ("darwin", "arm64", "darwin-arm64"),
        ("linux", "aarch64", "linux-aarch64"),
        ("windows", "AMD64", "windows-x86_64"),
    ],
)
def test_provider_normalises_supported_hosts(
    system: str, architecture: str, key: str
) -> None:
    descriptor = runtime.MermaidProvider().resolve(
        ComponentPolicy("supported"), _environment(system, architecture)
    )
    assert descriptor.sha256 == runtime._RUNTIME_SHA256[key]


def test_provider_rejects_unsupported_version_and_host() -> None:
    provider = runtime.MermaidProvider()
    with pytest.raises(RuntimeProviderUnavailableError, match="supports Mermaid runtime"):
        provider.resolve(ComponentPolicy("0.8.0"), _environment())
    with pytest.raises(RuntimeProviderUnavailableError, match="supported hosts"):
        provider.resolve(ComponentPolicy("supported"), _environment("darwin", "x86_64"))


def _wheel(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_composite_archive_is_deterministic_and_rooted_in_site_packages(
    tmp_path: Path,
) -> None:
    first_wheel = _wheel(tmp_path / "one.whl", {"alpha/__init__.py": b"one\n"})
    second_wheel = _wheel(tmp_path / "two.whl", {"beta/LICENSE": b"MIT\n"})
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    runtime._build_runtime_archive((first_wheel, second_wheel), first)
    runtime._build_runtime_archive((first_wheel, second_wheel), second)

    assert sha256_file(first) == sha256_file(second)
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == [
            "site-packages/alpha/__init__.py",
            "site-packages/beta/LICENSE",
        ]


def test_composite_refuses_executable_path_hooks_and_duplicate_paths(tmp_path: Path) -> None:
    hook = _wheel(tmp_path / "hook.whl", {"unsafe.pth": b"import bad\n"})
    with pytest.raises(RuntimeStoreError, match="path hook"):
        runtime._build_runtime_archive((hook,), tmp_path / "hook.zip")

    first = _wheel(tmp_path / "first.whl", {"Package/file.py": b"one"})
    second = _wheel(tmp_path / "second.whl", {"package/FILE.py": b"two"})
    with pytest.raises(RuntimeStoreError, match="duplicate"):
        runtime._build_runtime_archive((first, second), tmp_path / "duplicate.zip")


def test_runtime_site_packages_rejects_incomplete_cache(tmp_path: Path) -> None:
    (tmp_path / "site-packages").mkdir()
    with pytest.raises(RuntimeStoreError, match="incomplete"):
        runtime.runtime_site_packages(tmp_path)


def test_provider_refuses_changed_composite_metadata(tmp_path: Path) -> None:
    provider = runtime.MermaidProvider()
    descriptor = provider.resolve(ComponentPolicy("supported"), _environment())
    changed = type(descriptor)(
        **{**descriptor.__dict__, "source_url": "https://files.pythonhosted.org/changed"}
    )

    with pytest.raises(RuntimeStoreError, match="unreviewed Mermaid"):
        provider.acquire(changed, tmp_path / "mermaid.zip")
