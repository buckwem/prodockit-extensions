# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Validated project-local storage for optional PDF runtime components.

Providers resolve and acquire artifacts; this module owns the common trust
boundary: locking, digest checks, safe extraction, smoke testing, atomic
activation and preservation of a last-known-good runtime.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import time
import unicodedata
import uuid
import zipfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from prodockit.pdf.runtime_config import COMPONENTS

STORE_SCHEMA_VERSION = 1
MARKER_NAME = ".prodockit-runtime.json"
MAX_ARCHIVE_MEMBERS = 20_000
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
_CACHE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_DOWNLOADS_DIRECTORY = "d"
_RUNTIMES_DIRECTORY = "r"
_STAGING_DIRECTORY = "s"
_WINDOWS_RESERVED = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
)


class RuntimeStoreError(RuntimeError):
    """Project-local runtime state is invalid or could not be updated."""


class RuntimePreparationError(RuntimeStoreError):
    """Preparation failed without damaging the prior active runtime."""

    def __init__(self, message: str, *, fallback: Path | None = None) -> None:
        super().__init__(message)
        self.fallback = fallback


@dataclass(frozen=True)
class ArtifactDescriptor:
    """Resolved immutable artifact metadata supplied by an approved provider."""

    component: str
    version: str
    source_url: str
    sha256: str
    licence: str
    provenance: str
    platform: str
    architecture: str
    environment_identity: str
    archive_format: str
    expected_paths: tuple[str, ...]

    def validate(self) -> None:
        if self.component not in COMPONENTS:
            raise RuntimeStoreError(f"unknown PDF runtime component {self.component!r}")
        for name, value in (
            ("version", self.version),
            ("platform", self.platform),
            ("architecture", self.architecture),
        ):
            if not _safe_cache_key(value):
                raise RuntimeStoreError(f"artifact {name} is not a safe cache key: {value!r}")
        if self.version in {"latest", "supported"}:
            raise RuntimeStoreError("an artifact descriptor must contain an exact resolved version")
        if self.archive_format not in {"zip", "tar"}:
            raise RuntimeStoreError("artifact archive_format must be 'zip' or 'tar'")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise RuntimeStoreError("artifact sha256 must be 64 lowercase hexadecimal characters")
        for name, value in (
            ("source_url", self.source_url),
            ("licence", self.licence),
            ("provenance", self.provenance),
            ("environment_identity", self.environment_identity),
        ):
            if not value.strip():
                raise RuntimeStoreError(f"artifact {name} must not be empty")
        if not self.expected_paths:
            raise RuntimeStoreError("artifact expected_paths must not be empty")
        for expected in self.expected_paths:
            _safe_archive_path(expected)

    @property
    def platform_key(self) -> str:
        return f"{self.platform}-{self.architecture}"

    @property
    def artifact_id(self) -> str:
        return ":".join((self.component, self.version, self.platform_key, self.cache_key))

    @property
    def cache_key(self) -> str:
        metadata = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        metadata_digest = hashlib.sha256(metadata.encode("utf-8")).hexdigest()[:12]
        return f"{self.sha256[:16]}-{metadata_digest}"


@dataclass(frozen=True)
class PreparationResult:
    """The active runtime selected by one successful preparation."""

    component: str
    path: Path
    version: str
    sha256: str
    cached: bool


AcquireArtifact = Callable[[Path], None]
ProbeArtifact = Callable[[Path], None]


def runtime_store_root(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".prodockit" / "cache" / "pdf"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _windows_reserved(name: str) -> bool:
    return name.rstrip(". ").split(".", 1)[0].casefold() in _WINDOWS_RESERVED


def _safe_cache_key(value: str) -> bool:
    return bool(_CACHE_KEY.fullmatch(value)) and not _windows_reserved(value)


def _safe_archive_path(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\0" in name:
        raise RuntimeStoreError(f"unsafe archive path: {name!r}")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or any(
            part in {"", "."}
            or ":" in part
            or part.endswith((" ", "."))
            or _windows_reserved(part)
            or any(ord(character) < 32 for character in part)
            for part in path.parts
        )
    ):
        raise RuntimeStoreError(f"unsafe archive path: {name!r}")
    return path


def _check_archive_budget(count: int, extracted_bytes: int) -> None:
    if count > MAX_ARCHIVE_MEMBERS:
        raise RuntimeStoreError(
            f"archive has {count} entries; limit is {MAX_ARCHIVE_MEMBERS}"
        )
    if extracted_bytes > MAX_EXTRACTED_BYTES:
        raise RuntimeStoreError(
            f"archive expands to {extracted_bytes} bytes; limit is {MAX_EXTRACTED_BYTES}"
        )


def _validated_member_path(name: str, seen: set[str]) -> PurePosixPath:
    path = _safe_archive_path(name.rstrip("/"))
    normalised = unicodedata.normalize("NFC", path.as_posix()).casefold()
    if normalised in seen:
        raise RuntimeStoreError(f"duplicate archive path: {name!r}")
    seen.add(normalised)
    return path


def _extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        _check_archive_budget(len(members), sum(member.file_size for member in members))
        seen: set[str] = set()
        validated: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for member in members:
            path = _validated_member_path(member.filename, seen)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise RuntimeStoreError(f"archive contains a symbolic link: {member.filename!r}")
            kind = stat.S_IFMT(mode)
            if kind and kind not in {stat.S_IFREG, stat.S_IFDIR}:
                raise RuntimeStoreError(
                    f"archive contains a special entry: {member.filename!r}"
                )
            if member.flag_bits & 0x1:
                raise RuntimeStoreError(f"archive contains an encrypted entry: {member.filename!r}")
            validated.append((member, path))
        for member, path in validated:
            target = destination.joinpath(*path.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            permissions = (member.external_attr >> 16) & 0o777
            if permissions:
                target.chmod(permissions)


def _extract_tar(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, mode="r:*") as archive:
        members = archive.getmembers()
        _check_archive_budget(len(members), sum(member.size for member in members))
        seen: set[str] = set()
        validated: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
        for member in members:
            path = _validated_member_path(member.name, seen)
            if not (member.isfile() or member.isdir()):
                raise RuntimeStoreError(
                    f"archive contains a link or special entry: {member.name!r}"
                )
            validated.append((member, path))
        for member, path in validated:
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeStoreError(f"cannot read archive entry: {member.name!r}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)


def extract_archive(archive_path: Path, destination: Path, archive_format: str) -> None:
    """Extract a validated archive without trusting archive-owned paths."""

    if any(destination.iterdir()):
        raise RuntimeStoreError(f"staging directory is not empty: {destination}")
    try:
        if archive_format == "zip":
            _extract_zip(archive_path, destination)
        elif archive_format == "tar":
            _extract_tar(archive_path, destination)
        else:
            raise RuntimeStoreError(f"unsupported archive format {archive_format!r}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise RuntimeStoreError(f"cannot extract {archive_path.name}: {error}") from error


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise RuntimeStoreError(f"runtime contains a symbolic link: {path}")
        if not path.is_file() or path.name == MARKER_NAME:
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update((path.stat().st_mode & 0o111).to_bytes(2, "big"))
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def _safe_mkdir(boundary: Path, directory: Path) -> None:
    """Create a directory chain without following a project-local symlink."""

    if boundary.is_symlink():
        raise RuntimeStoreError(f"project root must not be a symbolic link: {boundary}")
    try:
        boundary.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise RuntimeStoreError(f"cannot create project directory {boundary}: {error}") from error
    if not boundary.is_dir():
        raise RuntimeStoreError(f"project root is not a directory: {boundary}")
    try:
        relative = directory.relative_to(boundary)
    except ValueError as error:
        raise RuntimeStoreError(f"runtime path escapes its project: {directory}") from error
    current = boundary
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeStoreError(f"runtime directory must not be a symbolic link: {current}")
        try:
            current.mkdir()
        except FileExistsError:
            if not current.is_dir() or current.is_symlink():
                raise RuntimeStoreError(f"runtime path is not a directory: {current}") from None


def _safe_existing_directory(boundary: Path, directory: Path) -> bool:
    """Check an existing directory chain without creating or following it."""

    if not boundary.is_dir() or boundary.is_symlink():
        return False
    try:
        relative = directory.relative_to(boundary)
    except ValueError:
        return False
    current = boundary
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            return False
    return True


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class _FileLock:
    def __init__(self, path: Path, timeout: float) -> None:
        self.path = path
        self.timeout = timeout
        self._stream: Any = None

    def __enter__(self) -> _FileLock:
        if self.path.is_symlink():
            raise RuntimeStoreError(f"runtime lock must not be a symbolic link: {self.path}")
        self._stream = self.path.open("a+b")
        if os.name == "nt":  # pragma: no cover - exercised by Windows CI
            self._stream.seek(0, os.SEEK_END)
            if self._stream.tell() == 0:
                self._stream.write(b"\0")
                self._stream.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._acquire()
                return self
            except (BlockingIOError, OSError) as error:
                if isinstance(error, OSError) and error.errno not in {
                    None,
                    errno.EACCES,
                    errno.EAGAIN,
                }:
                    self._stream.close()
                    raise RuntimeStoreError(f"cannot lock {self.path}: {error}") from error
                if time.monotonic() >= deadline:
                    self._stream.close()
                    raise RuntimeStoreError(
                        f"timed out waiting for PDF runtime lock {self.path}"
                    ) from error
                time.sleep(0.05)

    def _acquire(self) -> None:
        if os.name == "nt":  # pragma: no cover - exercised by Windows CI
            import msvcrt

            self._stream.seek(0)
            msvcrt.locking(  # type: ignore[attr-defined]
                self._stream.fileno(), msvcrt.LK_NBLCK, 1  # type: ignore[attr-defined]
            )
        else:
            import fcntl

            fcntl.flock(self._stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def __exit__(self, *_args: object) -> None:
        if self._stream is None:
            return
        if os.name == "nt":  # pragma: no cover - exercised by Windows CI
            import msvcrt

            self._stream.seek(0)
            msvcrt.locking(  # type: ignore[attr-defined]
                self._stream.fileno(), msvcrt.LK_UNLCK, 1  # type: ignore[attr-defined]
            )
        else:
            import fcntl

            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        self._stream.close()


class RuntimeStore:
    """Own and validate one project's derived PDF runtime store."""

    def __init__(self, project_root: str | Path, *, lock_timeout: float = 30.0) -> None:
        self.project_root = Path(project_root).resolve()
        self.root = runtime_store_root(self.project_root)
        self.lock_timeout = lock_timeout

    @contextmanager
    def component_lock(self, component: str) -> Iterator[None]:
        if component not in COMPONENTS:
            raise RuntimeStoreError(f"unknown PDF runtime component {component!r}")
        _safe_mkdir(self.project_root, self.root / ".locks")
        # References and the manifest are shared by every component. A single
        # store lock prevents two valid parallel preparations from replacing
        # each other's current/previous maps with stale snapshots.
        with _FileLock(self.root / ".locks" / "store.lock", self.lock_timeout):
            yield

    def _cleanup_staging(self, component: str) -> None:
        # Also clean the pre-G3 name so an interrupted upgrade does not leave
        # stale partial state behind. New names are intentionally compact:
        # PyInstaller-loaded DLLs still encounter Windows path-length limits.
        for name in (_STAGING_DIRECTORY, "staging"):
            staging = self.root / name
            _safe_mkdir(self.project_root, staging)
            for path in staging.glob(f"*-{component}-*"):
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)

    def _entry_path(self, entry: Mapping[str, Any]) -> Path | None:
        relative = entry.get("path")
        if not isinstance(relative, str):
            return None
        try:
            safe = _safe_archive_path(relative)
        except RuntimeStoreError:
            return None
        path = self.root.joinpath(*safe.parts)
        try:
            path.relative_to(self.root)
        except ValueError:
            return None
        return path

    def _valid_entry(
        self,
        entry: object,
        descriptor: ArtifactDescriptor | None = None,
        *,
        component: str | None = None,
    ) -> Path | None:
        if not isinstance(entry, dict):
            return None
        path = self._entry_path(entry)
        if path is None or not _safe_existing_directory(self.project_root, path):
            return None
        marker = _read_json(path / MARKER_NAME)
        required = {
            "component",
            "version",
            "source_url",
            "sha256",
            "licence",
            "provenance",
            "platform",
            "architecture",
            "environment_identity",
            "archive_format",
            "expected_paths",
            "tree_sha256",
            "prepared_at",
            "artifact_schema_version",
        }
        if not required <= marker.keys() or any(
            marker.get(key) != entry.get(key) for key in required
        ):
            return None
        expected_component = descriptor.component if descriptor is not None else component
        if expected_component is not None and marker.get("component") != expected_component:
            return None
        if marker.get("artifact_schema_version") != STORE_SCHEMA_VERSION:
            return None
        if descriptor is not None:
            expected = asdict(descriptor)
            expected["expected_paths"] = list(descriptor.expected_paths)
            if any(marker.get(key) != value for key, value in expected.items()):
                return None
        try:
            if _tree_sha256(path) != marker["tree_sha256"]:
                return None
        except (OSError, RuntimeStoreError):
            return None
        return path

    def active(self, component: str) -> PreparationResult | None:
        """Return a healthy active component without modifying the store."""

        if component not in COMPONENTS:
            raise RuntimeStoreError(f"unknown PDF runtime component {component!r}")
        if not _safe_existing_directory(self.project_root, self.root):
            return None
        current = _read_json(self.root / "current.json")
        entry = current.get(component)
        path = self._valid_entry(entry, component=component)
        if path is None or not isinstance(entry, dict):
            return None
        return PreparationResult(
            component=component,
            path=path,
            version=str(entry["version"]),
            sha256=str(entry["sha256"]),
            cached=True,
        )

    def active_for(self, descriptor: ArtifactDescriptor) -> PreparationResult | None:
        """Return the active runtime only when it matches this exact host policy."""

        descriptor.validate()
        if not _safe_existing_directory(self.project_root, self.root):
            return None
        current = _read_json(self.root / "current.json")
        path = self._valid_entry(
            current.get(descriptor.component),
            descriptor,
            component=descriptor.component,
        )
        if path is None:
            return None
        return PreparationResult(
            descriptor.component,
            path,
            descriptor.version,
            descriptor.sha256,
            True,
        )

    def _download(self, descriptor: ArtifactDescriptor, acquire: AcquireArtifact) -> Path:
        downloads = self.root / _DOWNLOADS_DIRECTORY
        _safe_mkdir(self.project_root, downloads)
        destination = downloads / f"{descriptor.sha256}.{descriptor.archive_format}"
        if (
            destination.is_file()
            and not destination.is_symlink()
            and sha256_file(destination) == descriptor.sha256
        ):
            return destination
        destination.unlink(missing_ok=True)
        partial = (
            self.root
            / _STAGING_DIRECTORY
            / f"download-{descriptor.component}-{uuid.uuid4().hex}.partial"
        )
        _safe_mkdir(self.project_root, partial.parent)
        try:
            acquire(partial)
            if not partial.is_file() or partial.is_symlink():
                raise RuntimeStoreError("artifact provider did not create the requested download")
            archive_bytes = partial.stat().st_size
            if archive_bytes > MAX_ARCHIVE_BYTES:
                raise RuntimeStoreError(
                    f"artifact is {archive_bytes} bytes; limit is {MAX_ARCHIVE_BYTES}"
                )
            actual = sha256_file(partial)
            if actual != descriptor.sha256:
                raise RuntimeStoreError(
                    f"artifact SHA-256 mismatch: expected {descriptor.sha256}, got {actual}"
                )
            os.replace(partial, destination)
            return destination
        finally:
            partial.unlink(missing_ok=True)

    def _stage(
        self,
        descriptor: ArtifactDescriptor,
        archive: Path,
        probe: ProbeArtifact,
    ) -> tuple[Path, dict[str, Any]]:
        staging = (
            self.root
            / _STAGING_DIRECTORY
            / f"runtime-{descriptor.component}-{uuid.uuid4().hex[:8]}"
        )
        _safe_mkdir(self.project_root, staging.parent)
        staging.mkdir(parents=True)
        try:
            extract_archive(archive, staging, descriptor.archive_format)
            for expected in descriptor.expected_paths:
                path = staging.joinpath(*_safe_archive_path(expected).parts)
                if not path.is_file() or path.is_symlink():
                    raise RuntimeStoreError(f"artifact is missing expected file {expected!r}")
            probe(staging)
            entry: dict[str, Any] = {
                **asdict(descriptor),
                "artifact_schema_version": STORE_SCHEMA_VERSION,
                "tree_sha256": _tree_sha256(staging),
                "prepared_at": int(time.time()),
            }
            (staging / MARKER_NAME).write_text(
                json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return staging, entry
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def _activate(
        self,
        descriptor: ArtifactDescriptor,
        staging: Path,
        entry: dict[str, Any],
        old_current: object,
        old_current_was_valid: bool,
    ) -> Path:
        target = (
            self.root / _RUNTIMES_DIRECTORY / descriptor.cache_key
        )
        _safe_mkdir(self.project_root, target.parent)
        displaced = (
            self.root
            / _STAGING_DIRECTORY
            / f"displaced-{descriptor.component}-{uuid.uuid4().hex[:8]}"
        )
        if target.exists():
            os.replace(target, displaced)
        try:
            os.replace(staging, target)
        except BaseException:
            if displaced.exists() and not target.exists():
                os.replace(displaced, target)
            raise
        finally:
            if displaced.exists():
                shutil.rmtree(displaced, ignore_errors=True)

        entry["path"] = target.relative_to(self.root).as_posix()
        current = _read_json(self.root / "current.json")
        previous = _read_json(self.root / "previous.json")
        if old_current_was_valid:
            previous[descriptor.component] = old_current
        current[descriptor.component] = entry
        manifest = _read_json(self.root / "manifest.json")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            artifacts = {}
        artifacts[descriptor.artifact_id] = entry
        _atomic_json(self.root / "previous.json", previous)
        _atomic_json(self.root / "current.json", current)
        _atomic_json(
            self.root / "manifest.json",
            {"schema_version": STORE_SCHEMA_VERSION, "artifacts": artifacts},
        )
        return target

    def prepare(
        self,
        descriptor: ArtifactDescriptor,
        *,
        acquire: AcquireArtifact,
        probe: ProbeArtifact,
    ) -> PreparationResult:
        """Acquire, validate and atomically activate one immutable artifact."""

        descriptor.validate()
        with self.component_lock(descriptor.component):
            self._cleanup_staging(descriptor.component)
            current = _read_json(self.root / "current.json")
            previous = _read_json(self.root / "previous.json")
            old_current = current.get(descriptor.component)
            active = self._valid_entry(
                old_current, descriptor, component=descriptor.component
            )
            if active is not None:
                return PreparationResult(
                    descriptor.component,
                    active,
                    descriptor.version,
                    descriptor.sha256,
                    True,
                )
            valid_old_current = self._valid_entry(
                old_current, component=descriptor.component
            )
            fallback = valid_old_current or self._valid_entry(
                previous.get(descriptor.component), component=descriptor.component
            )
            try:
                archive = self._download(descriptor, acquire)
                staging, entry = self._stage(descriptor, archive, probe)
                target = self._activate(
                    descriptor,
                    staging,
                    entry,
                    old_current,
                    valid_old_current is not None,
                )
            except Exception as error:
                suffix = f"; last-known-good remains at {fallback}" if fallback else ""
                raise RuntimePreparationError(
                    f"could not prepare {descriptor.component} "
                    f"{descriptor.version}: {error}{suffix}",
                    fallback=fallback,
                ) from error
            return PreparationResult(
                descriptor.component,
                target,
                descriptor.version,
                descriptor.sha256,
                False,
            )


__all__ = [
    "ArtifactDescriptor",
    "PreparationResult",
    "RuntimePreparationError",
    "RuntimeStore",
    "RuntimeStoreError",
    "extract_archive",
    "runtime_store_root",
    "sha256_file",
]
