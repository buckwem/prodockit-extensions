# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Machine-verifiable provenance for the standalone Mermaid JavaScript asset."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from base64 import b64encode
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

_MANIFEST_NAME = "_mermaid_provenance.json"


class MermaidProvenanceError(RuntimeError):
    """The recorded asset lineage is malformed or does not match an artifact."""


@dataclass(frozen=True)
class MermaidProvenance:
    """Pinned identities connecting the runtime asset to its published sources."""

    asset_sha256: str
    asset_size: int
    mermaidx_version: str
    mermaidx_repository: str
    mermaidx_tag: str
    mermaidx_commit: str
    mermaidx_asset_path: str
    wheel_filename: str
    wheel_sha256: str
    wheel_asset_path: str
    npm_name: str
    npm_version: str
    npm_tarball_url: str
    npm_tarball_sha1: str
    npm_tarball_sha256: str
    npm_tarball_sha512: str
    npm_integrity: str
    npm_asset_path: str


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MermaidProvenanceError(f"The {name} provenance section must be an object.")
    return value


def _text(section: dict[str, Any], key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise MermaidProvenanceError(f"The provenance field {key!r} must be text.")
    return value


def _positive_integer(section: dict[str, Any], key: str) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MermaidProvenanceError(f"The provenance field {key!r} must be positive.")
    return value


@lru_cache(maxsize=1)
def load_mermaid_provenance() -> MermaidProvenance:
    """Loads and validates the immutable manifest shipped with ProDockit."""
    try:
        manifest_text = (
            resources.files("prodockit.pdf").joinpath(_MANIFEST_NAME).read_text(encoding="utf-8")
        )
        manifest = json.loads(manifest_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MermaidProvenanceError("The Mermaid provenance manifest is unavailable.") from exc
    root = _mapping(manifest, "root")
    if root.get("schema") != 1:
        raise MermaidProvenanceError("The Mermaid provenance manifest schema is unsupported.")
    runtime = _mapping(root.get("runtime_asset"), "runtime_asset")
    source = _mapping(root.get("mermaidx_source"), "mermaidx_source")
    distribution = _mapping(root.get("mermaidx_distribution"), "mermaidx_distribution")
    npm = _mapping(root.get("upstream_npm"), "upstream_npm")
    provenance = MermaidProvenance(
        asset_sha256=_text(runtime, "sha256"),
        asset_size=_positive_integer(runtime, "size"),
        mermaidx_version=_text(distribution, "version"),
        mermaidx_repository=_text(source, "repository"),
        mermaidx_tag=_text(source, "tag"),
        mermaidx_commit=_text(source, "commit"),
        mermaidx_asset_path=_text(source, "asset_path"),
        wheel_filename=_text(distribution, "wheel_filename"),
        wheel_sha256=_text(distribution, "wheel_sha256"),
        wheel_asset_path=_text(distribution, "asset_path"),
        npm_name=_text(npm, "name"),
        npm_version=_text(npm, "version"),
        npm_tarball_url=_text(npm, "tarball_url"),
        npm_tarball_sha1=_text(npm, "tarball_sha1"),
        npm_tarball_sha256=_text(npm, "tarball_sha256"),
        npm_tarball_sha512=_text(npm, "tarball_sha512"),
        npm_integrity=_text(npm, "integrity"),
        npm_asset_path=_text(npm, "asset_path"),
    )
    for field_name, digest, length in (
        ("asset_sha256", provenance.asset_sha256, 64),
        ("wheel_sha256", provenance.wheel_sha256, 64),
        ("npm_tarball_sha1", provenance.npm_tarball_sha1, 40),
        ("npm_tarball_sha256", provenance.npm_tarball_sha256, 64),
        ("npm_tarball_sha512", provenance.npm_tarball_sha512, 128),
    ):
        invalid_character = any(
            character not in "0123456789abcdef" for character in digest
        )
        if len(digest) != length or invalid_character:
            raise MermaidProvenanceError(f"The provenance digest {field_name!r} is invalid.")
    integrity = "sha512-" + b64encode(
        bytes.fromhex(provenance.npm_tarball_sha512)
    ).decode("ascii")
    if provenance.npm_integrity != integrity:
        raise MermaidProvenanceError("The npm integrity value does not match its SHA-512 digest.")
    if provenance.mermaidx_asset_path != provenance.wheel_asset_path:
        raise MermaidProvenanceError("The source and wheel asset paths do not match.")
    return provenance


def verify_mermaid_npm_tarball(
    tarball: str | Path,
    *,
    provenance: MermaidProvenance | None = None,
) -> None:
    """Verifies the pinned npm tarball and the exact runtime asset inside it."""
    expected = provenance or load_mermaid_provenance()
    try:
        data = Path(tarball).read_bytes()
    except OSError as exc:
        raise MermaidProvenanceError("The Mermaid npm tarball is unavailable.") from exc
    if hashlib.sha256(data).hexdigest() != expected.npm_tarball_sha256:
        raise MermaidProvenanceError("The Mermaid npm tarball failed its SHA-256 check.")
    if hashlib.sha1(data).hexdigest() != expected.npm_tarball_sha1:
        raise MermaidProvenanceError("The Mermaid npm tarball failed its SHA-1 check.")
    if hashlib.sha512(data).hexdigest() != expected.npm_tarball_sha512:
        raise MermaidProvenanceError("The Mermaid npm tarball failed its SHA-512 check.")
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            member = archive.getmember(expected.npm_asset_path)
            if not member.isfile() or member.size != expected.asset_size:
                raise MermaidProvenanceError(
                    "The Mermaid runtime asset has an unexpected archive entry."
                )
            extracted = archive.extractfile(member)
            if extracted is None:
                raise MermaidProvenanceError("The Mermaid runtime asset cannot be read.")
            asset = extracted.read(expected.asset_size + 1)
    except (KeyError, tarfile.TarError, OSError) as exc:
        raise MermaidProvenanceError("The Mermaid npm tarball is malformed.") from exc
    if len(asset) != expected.asset_size:
        raise MermaidProvenanceError("The Mermaid runtime asset has an unexpected size.")
    if hashlib.sha256(asset).hexdigest() != expected.asset_sha256:
        raise MermaidProvenanceError("The Mermaid runtime asset failed its SHA-256 check.")
