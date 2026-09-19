# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from tools import weasyprint_windows_s0 as s0


def _archive(path: Path, *, unsafe: str | None = None) -> s0.ArtifactSpec:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("onedir/weasyprint/weasyprint.exe", b"prototype")
        archive.writestr("LICENSE", b"BSD-3-Clause")
        if unsafe:
            archive.writestr(unsafe, b"escape")
    content = path.read_bytes()
    return s0.ArtifactSpec(
        version="test",
        release_url="https://example.invalid/release",
        asset_url="https://example.invalid/asset.zip",
        asset_name="asset.zip",
        sha256=hashlib.sha256(content).hexdigest(),
        archive_bytes=len(content),
    )


def test_prepare_verifies_extracts_and_reuses_the_artifact(tmp_path: Path) -> None:
    archive = tmp_path / "artifact.zip"
    spec = _archive(archive)
    work = tmp_path / "work"

    cold = s0.prepare_artifact(work, spec, archive_override=archive)
    warm = s0.prepare_artifact(work, spec, archive_override=archive)

    assert cold.extracted is True
    assert warm.extracted is False
    assert cold.downloaded is False
    assert warm.downloaded is False
    assert cold.executable.read_bytes() == b"prototype"
    marker = json.loads((work / "runtime/.s0-artifact.json").read_text(encoding="utf-8"))
    assert marker["sha256"] == spec.sha256


def test_prepare_rejects_an_archive_with_the_wrong_digest(tmp_path: Path) -> None:
    archive = tmp_path / "artifact.zip"
    spec = _archive(archive)
    archive.write_bytes(archive.read_bytes() + b"changed")

    with pytest.raises(s0.AcceptanceError, match="SHA-256"):
        s0.prepare_artifact(tmp_path / "work", spec, archive_override=archive)


def test_extract_rejects_parent_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "artifact.zip"
    spec = _archive(archive, unsafe="../escaped.txt")

    with pytest.raises(s0.AcceptanceError, match="unsafe archive path"):
        s0.prepare_artifact(tmp_path / "work", spec, archive_override=archive)


def test_extract_rejects_windows_separator_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "artifact.zip"
    spec = _archive(archive, unsafe="..\\escaped.txt")

    with pytest.raises(s0.AcceptanceError, match="unsafe archive path"):
        s0.prepare_artifact(tmp_path / "work", spec, archive_override=archive)


def test_extract_requires_the_cli_and_licence(tmp_path: Path) -> None:
    archive_path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("README.rst", b"missing required files")
    content = archive_path.read_bytes()
    spec = s0.ArtifactSpec(
        version="test",
        release_url="https://example.invalid/release",
        asset_url="https://example.invalid/asset.zip",
        asset_name="asset.zip",
        sha256=hashlib.sha256(content).hexdigest(),
        archive_bytes=len(content),
    )

    with pytest.raises(s0.AcceptanceError, match="missing required paths"):
        s0.prepare_artifact(tmp_path / "work", spec, archive_override=archive_path)


def test_s0_pin_matches_the_reviewed_official_release() -> None:
    assert s0.SPEC.version == "70.0"
    assert s0.SPEC.archive_bytes == 32_271_073
    assert s0.SPEC.sha256 == ("ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53")
    assert s0.SPEC.asset_url.startswith("https://github.com/Kozea/WeasyPrint/releases/")
