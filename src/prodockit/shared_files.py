# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Versioned files shared by the prodockit documentation repositories.

The files are carried inside the wheel.  A repository opts in with a small
manifest that maps a packaged resource to its local destination.  That makes
the installed prodockit release the source of truth: checks need no sibling
checkout, live branch, network request, or separately maintained checksum.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib


MANIFEST = ".prodockit-shared-files.toml"
MANIFEST_VERSION = 1

# Logical resource names are deliberately finite.  A manifest can select a
# shipped file, but cannot turn this command into an arbitrary package-file
# reader.  The source path is where hatch places the canonical file in a wheel.
RESOURCES = {
    "pdk.css": ("assets", "pdk.css"),
    "pdk-pdf.css": ("assets", "pdk-pdf.css"),
}

# An editable install imports directly from src/ and therefore does not see
# hatch's wheel-only force-include mapping.  This fallback points at the same
# canonical source file that the wheel build maps into prodockit/assets.
DEVELOPMENT_SOURCES = {
    "pdk.css": Path(__file__).resolve().parents[2] / "docs" / "stylesheets" / "pdk.css",
    "pdk-pdf.css": Path(__file__).resolve().parents[2]
    / "docs"
    / "stylesheets"
    / "pdk-pdf.css",
}


class SharedFileError(Exception):
    """Raised when a shared-file manifest or destination is unsafe or invalid."""


@dataclass(frozen=True)
class SharedFile:
    """One packaged resource and its project-relative destination."""

    source: str
    target: str


@dataclass(frozen=True)
class SharedFileState:
    """The comparison result for one declared shared file."""

    file: SharedFile
    expected: bytes
    actual: bytes | None

    @property
    def status(self) -> str:
        if self.actual is None:
            return "missing"
        if self.actual != self.expected:
            return "different"
        return "current"

    @property
    def expected_sha256(self) -> str:
        return hashlib.sha256(self.expected).hexdigest()

    @property
    def actual_sha256(self) -> str | None:
        if self.actual is None:
            return None
        return hashlib.sha256(self.actual).hexdigest()


def manifest_path(root: str | os.PathLike[str]) -> Path:
    return Path(root).resolve() / MANIFEST


def _target_path(project: Path, target: str) -> Path:
    """Resolve a destination and reject symlinks that escape the project."""

    candidate = (project / target).resolve()
    try:
        candidate.relative_to(project)
    except ValueError:
        raise SharedFileError(
            f"shared-file target must stay inside the project: {target!r}"
        ) from None
    return candidate


def _safe_target(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SharedFileError("every shared file needs a non-empty target")
    raw = value.strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or re.match(r"^[A-Za-z]:/", raw)
        or ".." in path.parts
        or path == PurePosixPath(".")
    ):
        raise SharedFileError(f"shared-file target must stay inside the project: {value!r}")
    return path.as_posix()


def load_manifest(root: str | os.PathLike[str] = ".") -> list[SharedFile]:
    """Read the opt-in manifest, returning an empty list when it is absent."""

    path = manifest_path(root)
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise SharedFileError(f"could not read {MANIFEST}: {error}") from error

    version = data.get("version")
    if version != MANIFEST_VERSION:
        raise SharedFileError(
            f"{MANIFEST} needs version = {MANIFEST_VERSION}; found {version!r}"
        )
    entries = data.get("files")
    if not isinstance(entries, list) or not entries:
        raise SharedFileError(f"{MANIFEST} needs at least one [[files]] entry")

    result: list[SharedFile] = []
    targets: set[str] = set()
    for number, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise SharedFileError(f"{MANIFEST} files entry {number} must be a table")
        source = entry.get("source")
        if not isinstance(source, str) or source not in RESOURCES:
            choices = ", ".join(sorted(RESOURCES))
            raise SharedFileError(
                f"{MANIFEST} files entry {number} has unknown source {source!r}; "
                f"choose {choices}"
            )
        target = _safe_target(entry.get("target"))
        if target in targets:
            raise SharedFileError(f"{MANIFEST} declares {target} more than once")
        targets.add(target)
        result.append(SharedFile(source=source, target=target))
    return result


def resource_bytes(source: str) -> bytes:
    """Read one canonical resource from the wheel or editable source tree."""

    try:
        parts = RESOURCES[source]
    except KeyError as error:
        raise SharedFileError(f"unknown shared-file source {source!r}") from error

    packaged = resources.files("prodockit")
    for part in parts:
        packaged = packaged.joinpath(part)
    try:
        return packaged.read_bytes()
    except (FileNotFoundError, OSError):
        fallback = DEVELOPMENT_SOURCES.get(source)
        if fallback is None or not fallback.is_file():
            raise SharedFileError(
                f"the installed prodockit package does not contain {source}; reinstall it"
            ) from None
        return fallback.read_bytes()


def inspect(
    root: str | os.PathLike[str] = ".",
    manifest_root: str | os.PathLike[str] | None = None,
) -> list[SharedFileState]:
    """Compare every incoming declaration with a project's destinations.

    ``manifest_root`` lets template-sync inspect the new template's manifest
    before it has copied that manifest into an older project.  Other callers
    retain the original opt-in behaviour by omitting it.
    """

    project = Path(root).resolve()
    states: list[SharedFileState] = []
    declared_by = project
    if manifest_root is not None and manifest_path(manifest_root).is_file():
        declared_by = Path(manifest_root)
    for item in load_manifest(declared_by):
        target = _target_path(project, item.target)
        try:
            actual = target.read_bytes() if target.is_file() else None
        except OSError as error:
            raise SharedFileError(f"could not read {item.target}: {error}") from error
        states.append(
            SharedFileState(file=item, expected=resource_bytes(item.source), actual=actual)
        )
    return states


def apply(root: str | os.PathLike[str], states: list[SharedFileState]) -> list[str]:
    """Replace missing or different destinations, returning changed paths."""

    project = Path(root).resolve()
    changed: list[str] = []
    for state in states:
        if state.status == "current":
            continue
        target = _target_path(project, state.file.target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(state.expected)
        except OSError as error:
            raise SharedFileError(f"could not write {state.file.target}: {error}") from error
        changed.append(state.file.target)
    return changed


def drift(states: list[SharedFileState]) -> list[SharedFileState]:
    """Return only missing or different files."""

    return [state for state in states if state.status != "current"]


__all__ = [
    "MANIFEST",
    "SharedFile",
    "SharedFileError",
    "SharedFileState",
    "apply",
    "drift",
    "inspect",
    "load_manifest",
    "manifest_path",
    "resource_bytes",
]
