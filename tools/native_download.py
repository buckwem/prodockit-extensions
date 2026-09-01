# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Bounded, validated downloads for disposable native release harnesses."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import os
import shutil
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, Protocol

ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
CHUNK_SIZE = 1024 * 1024
CACHE_ENV = "PDK_NATIVE_DOWNLOAD_CACHE"
MSI_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
DEB_MAGIC = b"!<arch>\n"


class Response(Protocol):
    headers: object

    def __enter__(self) -> Response: ...
    def __exit__(self, *args: object) -> None: ...
    def read(self, size: int = -1) -> bytes: ...


class DownloadError(RuntimeError):
    """A transient or invalid download exhausted its bounded attempts."""


class DownloadValidationError(ValueError):
    """A response did not match the fixture format requested by its path."""


def _header(headers: object, name: str) -> str:
    getter = getattr(headers, "get", None)
    return str(getter(name, "") if getter is not None else "").strip()


def _response_url(response: object, source_url: str) -> str:
    getter = getattr(response, "geturl", None)
    return str(getter()) if getter is not None else source_url


def _copy_response(response: BinaryIO, output: BinaryIO) -> int:
    size = 0
    while chunk := response.read(CHUNK_SIZE):
        output.write(chunk)
        size += len(chunk)
    return size


def _write_response(response: Response, destination: Path) -> int:
    encoding = _header(response.headers, "Content-Encoding").lower()
    with destination.open("wb") as output:
        if encoding == "gzip":
            with gzip.GzipFile(fileobj=response) as decoded:
                return _copy_response(decoded, output)
        size = _copy_response(response, output)
    expected = _header(response.headers, "Content-Length")
    if expected:
        try:
            declared = int(expected)
        except ValueError:
            declared = size
        if size != declared:
            raise DownloadValidationError(
                f"truncated payload: received {size} bytes, expected {declared}"
            )
    return size


def _validate_zip(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            if not archive.infolist():
                raise DownloadValidationError("ZIP archive contains no entries")
            if corrupt := archive.testzip():
                raise DownloadValidationError(f"ZIP member failed CRC validation: {corrupt}")
    except zipfile.BadZipFile as error:
        raise DownloadValidationError(f"invalid ZIP archive: {error}") from error


def _validate_tar(path: Path) -> None:
    try:
        with tarfile.open(path) as archive:
            if next(iter(archive), None) is None:
                raise DownloadValidationError("tar archive contains no entries")
    except (tarfile.TarError, EOFError) as error:
        raise DownloadValidationError(f"invalid tar archive: {error}") from error


def _validate_deb(path: Path) -> None:
    with path.open("rb") as source:
        magic = source.read(len(DEB_MAGIC))
        first_header = source.read(60)
    if magic != DEB_MAGIC or len(first_header) != 60 or first_header[-2:] != b"`\n":
        raise DownloadValidationError("invalid Debian ar archive")


def _validate_msi(path: Path) -> None:
    size = path.stat().st_size
    with path.open("rb") as source:
        magic = source.read(len(MSI_MAGIC))
    if magic != MSI_MAGIC or size < 512 or size % 512:
        raise DownloadValidationError("invalid or truncated MSI compound file")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def validate_download(
    path: Path,
    *,
    name: str | None = None,
    expected_sha256: str | tuple[str, ...] | None = None,
) -> None:
    """Validate the fixture format implied by ``path`` before it is used."""
    fixture_name = (name or path.name).lower()
    if fixture_name.endswith((".zip", ".vsix", ".msix", ".msixbundle", ".appx")):
        _validate_zip(path)
    elif fixture_name.endswith((".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz")):
        _validate_tar(path)
    elif fixture_name.endswith(".deb"):
        _validate_deb(path)
    elif fixture_name.endswith(".msi"):
        _validate_msi(path)
    elif not path.stat().st_size:
        raise DownloadValidationError("empty payload")
    if expected_sha256 is not None:
        accepted = (expected_sha256,) if isinstance(expected_sha256, str) else expected_sha256
        digest = _sha256(path)
        if digest not in accepted:
            raise DownloadValidationError(
                f"SHA-256 mismatch: received {digest}, expected one of "
                + ", ".join(accepted)
            )


def _cache_path(root: Path, identity: str, destination: Path) -> Path:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return root / f"{digest}-{destination.name}"


def _restore_cache(
    cached: Path,
    destination: Path,
    partial: Path,
    expected_sha256: str | tuple[str, ...] | None,
) -> bool:
    if not cached.is_file():
        return False
    try:
        validate_download(
            cached, name=destination.name, expected_sha256=expected_sha256
        )
    except DownloadValidationError as error:
        with contextlib.suppress(OSError):
            cached.unlink(missing_ok=True)
        print(f"download cache discarded: path={cached} validation={error}", flush=True)
        return False
    except OSError as error:
        print(f"download cache read skipped: path={cached} error={error}", flush=True)
        return False
    try:
        shutil.copy2(cached, partial)
        partial.replace(destination)
        size = destination.stat().st_size
    except OSError as error:
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)
        print(f"download cache read skipped: path={cached} error={error}", flush=True)
        return False
    print(f"download cache hit: path={cached} bytes={size}", flush=True)
    return True


def _store_cache(
    cached: Path,
    destination: Path,
    expected_sha256: str | tuple[str, ...] | None,
) -> None:
    cached.parent.mkdir(parents=True, exist_ok=True)
    partial = cached.with_name(cached.name + f".{os.getpid()}.part")
    try:
        shutil.copy2(destination, partial)
        validate_download(
            partial, name=destination.name, expected_sha256=expected_sha256
        )
        partial.replace(cached)
    finally:
        partial.unlink(missing_ok=True)
    print(f"download cached: path={cached}", flush=True)


def download(
    url: str,
    destination: Path,
    *,
    opener: Callable[..., Response] = urllib.request.urlopen,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    expected_sha256: str | tuple[str, ...] | None = None,
    cache_dir: Path | None = None,
    cache_key: str | None = None,
) -> Path:
    """Download and validate one fixture with bounded transient retries.

    Permanent HTTP failures are returned to the caller immediately so a
    caller can move to a compatible source. Invalid and partial payloads never
    replace ``destination``.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least one")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    last_failure = "unknown failure"
    configured_cache = os.environ.get(CACHE_ENV, "")
    cache_root = cache_dir or (Path(configured_cache) if configured_cache else None)
    cached = (
        _cache_path(cache_root, cache_key or url, destination)
        if cache_root is not None
        else None
    )
    if cached is not None and _restore_cache(
        cached, destination, partial, expected_sha256
    ):
        return destination

    for attempt in range(1, attempts + 1):
        partial.unlink(missing_ok=True)
        request = urllib.request.Request(
            url, headers={"User-Agent": "prodockit-release-ci"}
        )
        final_url = url
        response_type = "unknown"
        size = 0
        try:
            with opener(request, timeout=120) as response:
                final_url = _response_url(response, url)
                response_type = _header(response.headers, "Content-Type") or "unknown"
                size = _write_response(response, partial)
            validate_download(
                partial,
                name=destination.name,
                expected_sha256=expected_sha256,
            )
            partial.replace(destination)
        except urllib.error.HTTPError as error:
            partial.unlink(missing_ok=True)
            final_url = error.geturl()
            response_type = _header(error.headers, "Content-Type") or "unknown"
            if error.code != 429 and not 500 <= error.code <= 599:
                print(
                    "download failed permanently: "
                    f"source={url} final={final_url} type={response_type} "
                    f"bytes=0 attempt={attempt}/{attempts} http={error.code}",
                    flush=True,
                )
                raise
            last_failure = f"HTTP {error.code}: {error.reason}"
        except (DownloadValidationError, EOFError, OSError, urllib.error.URLError) as error:
            if partial.exists():
                size = partial.stat().st_size
            partial.unlink(missing_ok=True)
            last_failure = f"{type(error).__name__}: {error}"
        else:
            if cached is not None:
                try:
                    _store_cache(cached, destination, expected_sha256)
                except (DownloadValidationError, OSError) as error:
                    print(
                        f"download cache write skipped: path={cached} error={error}",
                        flush=True,
                    )
            print(
                "download complete: "
                f"source={url} final={final_url} type={response_type} "
                f"bytes={size} attempt={attempt}/{attempts}",
                flush=True,
            )
            return destination

        print(
            "download retryable failure: "
            f"source={url} final={final_url} type={response_type} "
            f"bytes={size} attempt={attempt}/{attempts} validation={last_failure}",
            flush=True,
        )
        if attempt < attempts:
            delay = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
            sleep(delay)

    raise DownloadError(
        f"download failed after {attempts} attempts: source={url}; {last_failure}"
    )
