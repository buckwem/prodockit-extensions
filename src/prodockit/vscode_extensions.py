# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Validated VS Code extension fallback downloads.

VS Code's own CLI remains the primary Marketplace client.  This module is the
bounded fallback used only after that idempotent install has exhausted its
transient retries: it resolves an exact, reviewed Open VSX release, validates
both manifests in the VSIX, and caches only the validated archive.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from prodockit.renderer_resilience import DEFAULT_RETRY_DELAYS

DOWNLOAD_CACHE_ENV = "PDK_NATIVE_DOWNLOAD_CACHE"
OPEN_VSX_URL_ENV = "PDK_OPEN_VSX_URL"
OPEN_VSX_DEFAULT = "https://open-vsx.org"

# Licensing is deliberately reviewed here rather than accepting whatever a
# second registry happens to publish under a familiar identifier.
REVIEWED_LICENSES = {
    "ms-python.python": "MIT",
    "zensical.zensical-studio": "MIT",
    "tamasfe.even-better-toml": "SEE LICENSE IN LICENSE.md",
    "ltex-plus.vscode-ltex-plus": "MPL-2.0",
}


class ExtensionInstallError(RuntimeError):
    """An extension fallback could not be resolved or validated safely."""


@dataclass(frozen=True)
class ExtensionEvidence:
    extension: str
    version: str
    platform: str
    source: str
    archive: Path
    cached: bool
    attempts: tuple[str, ...] = ()


def target_platform() -> str:
    machine = (
        platform.machine()
        .casefold()
        .replace("x86_64", "x64")
        .replace("amd64", "x64")
        .replace("aarch64", "arm64")
    )
    operating_system = (
        "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"
    )
    return f"{operating_system}-{machine or 'unknown'}"


def _cache_root() -> Path:
    configured = os.environ.get(DOWNLOAD_CACHE_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    running_on: str = sys.platform
    if running_on == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "prodockit" / "Cache" / "downloads"
    if running_on == "darwin":
        return Path.home() / "Library" / "Caches" / "prodockit" / "downloads"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "prodockit/downloads"


def cache_path(extension: str, version: str, target: str | None = None) -> Path:
    safe_id = extension.casefold().replace("/", "_")
    return _cache_root() / "vsix" / safe_id / version / f"{target or target_platform()}.vsix"


def transient_extension_failure(detail: str) -> bool:
    lowered = detail.casefold()
    return any(
        marker in lowered
        for marker in (
            "http 429",
            "server returned 429",
            "server returned 5",
            "service unavailable",
            "bad gateway",
            "gateway timeout",
            "econnreset",
            "eai_again",
            "timed out",
            "unexpected eof",
            "end of central directory record signature not found",
            "invalid zip",
            "corrupt zip",
        )
    )


def _read_json(archive: zipfile.ZipFile, name: str) -> dict[str, object]:
    try:
        value = json.loads(archive.read(name).decode("utf-8"))
    except (KeyError, UnicodeError, json.JSONDecodeError) as error:
        raise ExtensionInstallError(f"VSIX has no valid {name}: {error}") from error
    if not isinstance(value, dict):
        raise ExtensionInstallError(f"VSIX {name} is not a JSON object")
    return value


def validate_vsix(path: Path, extension: str, version: str) -> None:
    publisher, name = extension.split(".", 1)
    try:
        with zipfile.ZipFile(path) as archive:
            if not archive.infolist() or archive.testzip() is not None:
                raise ExtensionInstallError("VSIX ZIP integrity check failed")
            package = _read_json(archive, "extension/package.json")
            observed = f"{package.get('publisher', '')}.{package.get('name', '')}".casefold()
            if observed != extension.casefold():
                raise ExtensionInstallError(
                    f"VSIX identity is {observed or 'missing'}, expected {extension}"
                )
            if str(package.get("version", "")) != version:
                raise ExtensionInstallError(
                    f"VSIX version is {package.get('version') or 'missing'}, expected {version}"
                )
            try:
                root = ElementTree.fromstring(archive.read("extension.vsixmanifest"))
            except (KeyError, ElementTree.ParseError) as error:
                raise ExtensionInstallError(
                    f"VSIX manifest is missing or invalid: {error}"
                ) from error
            identity = next(
                (
                    element
                    for element in root.iter()
                    if element.tag.rsplit("}", 1)[-1] == "Identity"
                ),
                None,
            )
            if identity is None:
                raise ExtensionInstallError("VSIX manifest has no Identity")
            manifest_id = identity.attrib.get("Id", "")
            manifest_publisher = identity.attrib.get("Publisher", "")
            manifest_version = identity.attrib.get("Version", "")
            acceptable_ids = {name.casefold(), extension.casefold()}
            if (
                manifest_id.casefold() not in acceptable_ids
                or manifest_publisher.casefold() != publisher.casefold()
            ):
                raise ExtensionInstallError(
                    "VSIX manifest identity does not match "
                    f"{publisher}.{name}: {manifest_publisher}.{manifest_id}"
                )
            if manifest_version != version:
                raise ExtensionInstallError(
                    f"VSIX manifest version is {manifest_version or 'missing'}, expected {version}"
                )
    except (OSError, zipfile.BadZipFile) as error:
        raise ExtensionInstallError(f"VSIX archive validation failed: {error}") from error


def _request_json(url: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "prodockit-bootstrap"})
    with urllib.request.urlopen(request, timeout=30) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ExtensionInstallError("Open VSX metadata is not a JSON object")
    return value


def open_vsx_metadata(extension: str, version: str) -> tuple[str, str]:
    publisher, name = extension.split(".", 1)
    base = os.environ.get(OPEN_VSX_URL_ENV, OPEN_VSX_DEFAULT).rstrip("/")
    url = f"{base}/api/{publisher}/{name}/{version}"
    metadata = _request_json(url)
    observed = f"{metadata.get('namespace', '')}.{metadata.get('name', '')}".casefold()
    if observed != extension.casefold() or str(metadata.get("version", "")) != version:
        raise ExtensionInstallError(
            f"Open VSX returned {observed} {metadata.get('version')}, "
            f"expected {extension} {version}"
        )
    expected_license = REVIEWED_LICENSES.get(extension.casefold())
    observed_license = str(metadata.get("license", "")).strip()
    if expected_license is None or observed_license.casefold() != expected_license.casefold():
        raise ExtensionInstallError(
            f"Open VSX licence for {extension} {version} is "
            f"{observed_license or 'missing'}, expected {expected_license or 'a reviewed licence'}"
        )
    if metadata.get("verified") is not True:
        raise ExtensionInstallError(f"Open VSX publisher for {extension} is not verified")
    files = metadata.get("files")
    download = files.get("download") if isinstance(files, dict) else None
    if not isinstance(download, str):
        raise ExtensionInstallError("Open VSX metadata has no download URL")
    parsed = urllib.parse.urlparse(download)
    allowed_host = urllib.parse.urlparse(base).hostname
    if parsed.scheme != "https" or parsed.hostname != allowed_host:
        raise ExtensionInstallError(f"Open VSX returned an untrusted download URL: {download}")
    return download, observed_license


def _download(url: str, destination: Path) -> None:
    partial = destination.with_name(destination.name + f".{os.getpid()}.part")
    request = urllib.request.Request(url, headers={"User-Agent": "prodockit-bootstrap"})
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if not partial.stat().st_size:
            raise ExtensionInstallError("downloaded an empty VSIX")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def obtain_open_vsx(
    extension: str,
    version: str,
    *,
    target: str | None = None,
    retry_delays: Sequence[float] = DEFAULT_RETRY_DELAYS,
    sleeper: Callable[[float], None] = time.sleep,
) -> ExtensionEvidence:
    destination = cache_path(extension, version, target)
    if destination.is_file():
        try:
            validate_vsix(destination, extension, version)
            return ExtensionEvidence(
                extension, version, target or target_platform(), "open-vsx", destination, True
            )
        except ExtensionInstallError:
            destination.unlink(missing_ok=True)
    failures: list[str] = []
    for attempt, delay in enumerate((*retry_delays, 0.0), start=1):
        try:
            # Metadata is part of the remote operation. Retrying only the file
            # would make a transient registry outage defeat the fallback before
            # any archive request was attempted.
            url, _license = open_vsx_metadata(extension, version)
            _download(url, destination)
            validate_vsix(destination, extension, version)
            return ExtensionEvidence(
                extension,
                version,
                target or target_platform(),
                "open-vsx",
                destination,
                False,
                tuple(failures),
            )
        except urllib.error.HTTPError as error:
            destination.unlink(missing_ok=True)
            detail = f"attempt {attempt}: HTTP {error.code} {error.reason}"
            failures.append(detail)
            if error.code != 429 and not 500 <= error.code <= 599:
                break
        except (ExtensionInstallError, OSError, urllib.error.URLError) as error:
            destination.unlink(missing_ok=True)
            detail = f"attempt {attempt}: {error}"
            failures.append(detail)
            if not transient_extension_failure(detail):
                break
        if delay:
            sleeper(float(delay))
    raise ExtensionInstallError(
        f"Open VSX fallback failed for {extension} {version}: {'; '.join(failures)}"
    )


def fallback_install(
    command: Sequence[str],
    extension: str,
    version: str,
    *,
    run: Callable[[Sequence[str]], object],
) -> tuple[object, ExtensionEvidence]:
    evidence = obtain_open_vsx(extension, version)
    local_command = [command[0], "--install-extension", str(evidence.archive), "--force"]
    result = run(local_command)
    return result, evidence


def probe_open_vsx(extension: str, version: str) -> tuple[bool, str]:
    try:
        url, license_name = open_vsx_metadata(extension, version)
    except (ExtensionInstallError, OSError, urllib.error.URLError) as error:
        return False, str(error)
    return True, f"verified publisher; {license_name}; {url}"


__all__ = [
    "REVIEWED_LICENSES",
    "ExtensionEvidence",
    "ExtensionInstallError",
    "cache_path",
    "fallback_install",
    "obtain_open_vsx",
    "probe_open_vsx",
    "target_platform",
    "transient_extension_failure",
    "validate_vsix",
]
