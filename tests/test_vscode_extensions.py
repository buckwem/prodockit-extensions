# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Validated, cached Open VSX fallback downloads for issue #722."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from prodockit.vscode_extensions import (
    ExtensionInstallError,
    cache_path,
    obtain_open_vsx,
    validate_vsix,
)


def _vsix(path: Path, extension: str, version: str) -> None:
    publisher, name = extension.split(".", 1)
    manifest = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<PackageManifest xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">'
        f'<Metadata><Identity Id="{name}" Version="{version}" '
        f'Publisher="{publisher}" /></Metadata></PackageManifest>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "extension/package.json",
            json.dumps({"publisher": publisher, "name": name, "version": version}),
        )
        archive.writestr("extension.vsixmanifest", manifest)


def test_validate_vsix_proves_both_manifest_identities(tmp_path: Path) -> None:
    path = tmp_path / "extension.vsix"
    _vsix(path, "ms-python.python", "2026.4.0")

    validate_vsix(path, "ms-python.python", "2026.4.0")

    with pytest.raises(ExtensionInstallError, match=r"expected 2026\.5\.0"):
        validate_vsix(path, "ms-python.python", "2026.5.0")


def test_obtain_open_vsx_reuses_only_a_validated_cache_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDK_NATIVE_DOWNLOAD_CACHE", str(tmp_path))
    path = cache_path("ms-python.python", "2026.4.0", "linux-x64")
    path.parent.mkdir(parents=True)
    _vsix(path, "ms-python.python", "2026.4.0")
    monkeypatch.setattr(
        "prodockit.vscode_extensions.open_vsx_metadata",
        lambda *_args: pytest.fail("a cache hit must not contact the registry"),
    )

    evidence = obtain_open_vsx("ms-python.python", "2026.4.0", target="linux-x64")

    assert evidence.cached
    assert evidence.archive == path


def test_obtain_open_vsx_discards_a_truncated_cache_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDK_NATIVE_DOWNLOAD_CACHE", str(tmp_path))
    path = cache_path("ms-python.python", "2026.4.0", "linux-x64")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"truncated")
    monkeypatch.setattr(
        "prodockit.vscode_extensions.open_vsx_metadata",
        lambda *_args: ("https://open-vsx.org/file.vsix", "MIT"),
    )

    def replace_download(_url: str, destination: Path) -> None:
        _vsix(destination, "ms-python.python", "2026.4.0")

    monkeypatch.setattr("prodockit.vscode_extensions._download", replace_download)

    evidence = obtain_open_vsx(
        "ms-python.python", "2026.4.0", target="linux-x64", retry_delays=()
    )

    assert not evidence.cached
    validate_vsix(path, "ms-python.python", "2026.4.0")
