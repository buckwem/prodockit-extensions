# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import io
import tarfile
from base64 import b64encode
from dataclasses import replace
from pathlib import Path

import pytest

import prodockit.pdf._standalone_quickjs as quickjs_module
from prodockit.pdf._mermaid_provenance import (
    MermaidProvenance,
    MermaidProvenanceError,
    load_mermaid_provenance,
    verify_mermaid_npm_tarball,
)


def test_manifest_records_the_exact_audited_lineage() -> None:
    provenance = load_mermaid_provenance()

    assert provenance.mermaidx_version == "0.9.5"
    assert provenance.mermaidx_tag == "v0.9.5"
    assert provenance.mermaidx_commit == "d4b83e7ec3ea82235f7fb0ad834ec68e1147a569"
    assert provenance.wheel_filename == "mermaidx-0.9.5-py3-none-any.whl"
    assert provenance.wheel_sha256 == (
        "46dfbdc7c101bd5395f05bca2f0917c467b9c5d5c3cbec1fbe238c546b673039"
    )
    assert provenance.npm_name == "mermaid"
    assert provenance.npm_version == "11.16.0"
    assert provenance.npm_asset_path == "package/dist/mermaid.min.js"
    assert provenance.asset_size == 3_565_102
    assert provenance.asset_sha256 == (
        "74d7c46dabca328c2294733910a8aa1ed0c37451776e8d5295da38a2b758fb9b"
    )


def test_runtime_integrity_check_uses_the_provenance_manifest() -> None:
    provenance = load_mermaid_provenance()

    assert provenance.mermaidx_version == quickjs_module._MERMAIDX_VERSION
    assert quickjs_module._ASSET_HASHES["mermaid.js"] == provenance.asset_sha256


def test_python_package_does_not_install_mermaid_runtime_dependencies() -> None:
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    pyproject = pyproject_path.read_text(encoding="utf-8")

    dependency_block = pyproject.split("dependencies = [", 1)[1].split("]", 1)[0]
    assert "mermaidx" not in dependency_block
    assert "quickjs-ng" not in dependency_block
    assert '"pypdf' not in dependency_block
    assert '"pypdf>=4.0"' in pyproject.split("dev = [", 1)[1].split("]", 1)[0]


def _tarball(tmp_path: Path, asset: bytes) -> tuple[Path, MermaidProvenance]:
    tarball = tmp_path / "mermaid.tgz"
    with tarfile.open(tarball, "w:gz") as archive:
        info = tarfile.TarInfo("package/dist/mermaid.min.js")
        info.size = len(asset)
        info.mtime = 0
        archive.addfile(info, io.BytesIO(asset))
    data = tarball.read_bytes()
    sha512 = hashlib.sha512(data).hexdigest()
    provenance = MermaidProvenance(
        asset_sha256=hashlib.sha256(asset).hexdigest(),
        asset_size=len(asset),
        mermaidx_version="0.9.5",
        mermaidx_repository="https://example.test/mermaidx.git",
        mermaidx_tag="v0.9.5",
        mermaidx_commit="0" * 40,
        mermaidx_asset_path="mermaidx/assets/mermaid.js",
        wheel_filename="mermaidx.whl",
        wheel_sha256="0" * 64,
        wheel_asset_path="mermaidx/assets/mermaid.js",
        npm_name="mermaid",
        npm_version="11.16.0",
        npm_tarball_url="https://example.test/mermaid.tgz",
        npm_tarball_sha1=hashlib.sha1(data).hexdigest(),
        npm_tarball_sha256=hashlib.sha256(data).hexdigest(),
        npm_tarball_sha512=sha512,
        npm_integrity="sha512-" + b64encode(bytes.fromhex(sha512)).decode("ascii"),
        npm_asset_path="package/dist/mermaid.min.js",
    )
    return tarball, provenance


def test_tarball_verifier_reproduces_the_pinned_inner_asset(tmp_path: Path) -> None:
    tarball, provenance = _tarball(tmp_path, b"official mermaid bundle")

    verify_mermaid_npm_tarball(tarball, provenance=provenance)


def test_tarball_verifier_rejects_a_changed_distribution(tmp_path: Path) -> None:
    tarball, provenance = _tarball(tmp_path, b"official mermaid bundle")
    tampered = replace(provenance, npm_tarball_sha256="f" * 64)

    with pytest.raises(MermaidProvenanceError, match="tarball failed its SHA-256"):
        verify_mermaid_npm_tarball(tarball, provenance=tampered)


def test_tarball_verifier_rejects_a_changed_inner_asset(tmp_path: Path) -> None:
    tarball, provenance = _tarball(tmp_path, b"official mermaid bundle")
    wrong_asset = replace(provenance, asset_sha256="f" * 64)

    with pytest.raises(MermaidProvenanceError, match="asset failed its SHA-256"):
        verify_mermaid_npm_tarball(tarball, provenance=wrong_asset)
