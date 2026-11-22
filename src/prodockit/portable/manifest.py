# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Versioned preparation manifests and deterministic content fingerprints."""

from __future__ import annotations

import json
import platform
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from typing import Any

from prodockit import __version__
from prodockit.portable import PortableError
from prodockit.portable.inputs import digest
from prodockit.portable.source_map import validate_source_map

SCHEMA = 2


def toolchain(pandoc: Path | None) -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for name in (
        "Markdown",
        "markdown-it-py",
        "pymdown-extensions",
        "zensical",
        "PyYAML",
        "beautifulsoup4",
        "Pillow",
        "tomlkit",
    ):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {
        "python": platform.python_version(),
        "packages": packages,
        "pandoc": (
            {"path": str(pandoc.resolve()), "sha256": digest(pandoc.read_bytes())}
            if pandoc is not None
            else None
        ),
    }


def content_id(manifest: dict[str, Any]) -> str:
    """Exclude only the per-invocation generation name and this digest itself."""
    content = {
        key: value for key, value in manifest.items() if key not in {"generation", "content_id"}
    }
    return digest(
        json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def relative_path(value: str) -> Path:
    if not isinstance(value, str):
        raise PortableError("prepared relative path must be a string")
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise PortableError(f"invalid prepared relative path: {value!r}")
    if path == PurePosixPath(".") or ":" in value:
        raise PortableError(f"invalid prepared relative path: {value!r}")
    return Path(*path.parts)


def generated_hashes(root: Path) -> dict[str, str]:
    files = [root / "zensical.toml"]
    for name in ("docs", ".inputs"):
        directory = root / name
        if directory.is_symlink() or not directory.is_dir():
            raise PortableError(f"prepared input directory is missing or symlinked: {name}")
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise PortableError(f"symlinked prepared input: {path.relative_to(root)}")
            if path.is_file():
                files.append(path)
    result: dict[str, str] = {}
    for path in sorted(files):
        if path.is_symlink() or not path.is_file():
            raise PortableError(f"prepared input changed: {path.relative_to(root)}")
        result[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return result


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """The manifest is the completion marker, published after all other inputs."""
    manifest["content_id"] = content_id(manifest)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    )
    temporary.replace(path)


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") != SCHEMA
            or manifest.get("mode") != "portable"
        ):
            raise PortableError("unsupported portable manifest; run pdk -p prepare again")
        required = {
            "content_id": str,
            "prodockit": str,
            "generation": str,
            "original_config": str,
            "original_docs_dir": str,
            "input_hashes": dict,
            "generated_hashes": dict,
            "captured_inputs": dict,
            "pages": dict,
            "source_paths": dict,
            "toolchain": dict,
            "directory_urls": bool,
        }
        if any(type(manifest.get(key)) is not kind for key, kind in required.items()):
            raise PortableError("incomplete portable manifest; prepare again")
        if manifest["generation"] != path.parent.name:
            raise PortableError("portable manifest belongs to a different generation")
        if content_id(manifest) != manifest["content_id"]:
            raise PortableError(
                "portable manifest content fingerprint does not match; prepare again"
            )
        for name, value in manifest["generated_hashes"].items():
            relative_path(name)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise PortableError("invalid prepared content hash")
        if set(manifest["captured_inputs"]) != set(manifest["input_hashes"]):
            raise PortableError("captured input inventory does not match the original inputs")
        if manifest["captured_inputs"].get(manifest["original_config"]) != ".inputs/config.toml":
            raise PortableError("portable manifest does not identify its captured configuration")
        for original, captured in manifest["captured_inputs"].items():
            relative = relative_path(captured)
            if (
                not Path(original).is_absolute()
                or relative.parts[0] != ".inputs"
                or manifest["generated_hashes"].get(captured) != manifest["input_hashes"][original]
            ):
                raise PortableError(f"captured input does not match its original bytes: {original}")
        if set(manifest["source_paths"]) != set(manifest["pages"]):
            raise PortableError("portable manifest source inventory does not match its pages")
        markdown = {
            name.removeprefix("docs/")
            for name in manifest["generated_hashes"]
            if name.startswith("docs/") and Path(name).suffix.lower() == ".md"
        }
        if markdown != set(manifest["pages"]):
            raise PortableError("portable manifest page inventory does not match prepared Markdown")
        for source, paths in manifest["source_paths"].items():
            relative_path(source)
            if (
                paths["generated"] != f"docs/{source}"
                or paths["captured"] != f".inputs/docs/{source}"
            ):
                raise PortableError(f"invalid source mapping for {source}")
            if paths["original"] != str(
                Path(manifest["original_docs_dir"]) / relative_path(source)
            ):
                raise PortableError(f"invalid original source mapping for {source}")
            if manifest["captured_inputs"].get(paths["original"]) != paths["captured"]:
                raise PortableError(f"source mapping has no captured input: {source}")
            page = manifest["pages"][source]
            for key, fields in (("targets", ("id", "text")), ("links", ("page", "id", "text"))):
                if not isinstance(page[key], list) or any(
                    not isinstance(item, dict)
                    or any(not isinstance(item.get(field), str) for field in fields)
                    for item in page[key]
                ):
                    raise PortableError(f"invalid {key} in portable manifest: {source}")
            for link in page["links"]:
                if link["page"] not in manifest["pages"]:
                    raise PortableError(f"reference destination is missing from manifest: {source}")
        runtime = manifest["toolchain"]
        if not isinstance(runtime.get("python"), str) or not isinstance(
            runtime.get("packages"), dict
        ):
            raise PortableError("invalid portable preparation toolchain")
        pandoc = runtime["pandoc"]
        if pandoc is not None and (
            not isinstance(pandoc, dict)
            or not isinstance(pandoc.get("path"), str)
            or not Path(pandoc["path"]).is_absolute()
            or not isinstance(pandoc.get("sha256"), str)
        ):
            raise PortableError("invalid Pandoc preparation toolchain")
        return manifest
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, PortableError):
            raise
        raise PortableError(f"invalid portable manifest: {error}; prepare again") from error


def validate_inputs(root: Path, manifest: dict[str, Any]) -> None:
    actual = generated_hashes(root)
    expected = manifest["generated_hashes"]
    changed = sorted(
        name for name in actual.keys() | expected.keys() if actual.get(name) != expected.get(name)
    )
    if changed:
        raise PortableError(f"prepared input changed: {changed[0]}; prepare again")
    if manifest["prodockit"] != __version__:
        raise PortableError("Prodockit version changed; prepare again")
    runtime = manifest["toolchain"].get("pandoc")
    if toolchain(Path(runtime["path"]) if runtime else None) != manifest["toolchain"]:
        raise PortableError("portable preparation toolchain changed; prepare again")
    for source, paths in manifest["source_paths"].items():
        try:
            validate_source_map(
                (root / paths["captured"]).read_bytes().decode("utf-8"),
                (root / paths["generated"]).read_bytes().decode("utf-8"),
                manifest["pages"][source]["source_map"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PortableError(f"invalid source map for {source}; prepare again") from error
