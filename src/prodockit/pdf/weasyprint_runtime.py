# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Qualified project-local WeasyPrint runtime for Windows x64.

The artifact is downloaded directly from the official upstream release,
verified by its reviewed SHA-256 digest, and activated by ``RuntimeStore``.
Nothing here changes PATH, the registry, the active Python environment, or
the host's native-library installation.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_prepare import (
    RuntimeEnvironment,
    RuntimeProviderUnavailableError,
)
from prodockit.pdf.runtime_store import ArtifactDescriptor, RuntimeStoreError

WEASYPRINT_VERSION = "70.0"
WEASYPRINT_ASSET_URL = (
    "https://github.com/Kozea/WeasyPrint/releases/download/"
    "v70.0/weasyprint-windows-onedir.zip"
)
WEASYPRINT_ASSET_SHA256 = (
    "ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53"
)
WEASYPRINT_ASSET_BYTES = 32_271_073
WEASYPRINT_EXECUTABLE = Path("onedir/weasyprint/weasyprint.exe")
WEASYPRINT_LICENCE = Path("LICENSE")

_WINDOWS_X64 = frozenset({"amd64", "x86_64"})
_DOWNLOAD_HOSTS = frozenset(
    {
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
)
_DOWNLOAD_TIMEOUT = 45.0
_DOWNLOAD_ATTEMPTS = 3
_PROBE_TIMEOUT = 120.0


def _validate_download_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _DOWNLOAD_HOSTS:
        raise RuntimeStoreError(f"refusing unapproved WeasyPrint download URL: {url}")
    if parsed.username or parsed.password:
        raise RuntimeStoreError("refusing a WeasyPrint download URL containing credentials")


class _TrustedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_download(request: urllib.request.Request, timeout: float) -> Any:
    opener = urllib.request.build_opener(_TrustedRedirectHandler())
    return opener.open(request, timeout=timeout)


def _download_official_artifact(url: str, destination: Path) -> None:
    _validate_download_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "Prodockit-PDF-Runtime/1"})
    last_error: Exception | None = None
    for attempt in range(_DOWNLOAD_ATTEMPTS):
        destination.unlink(missing_ok=True)
        try:
            with _open_download(request, _DOWNLOAD_TIMEOUT) as response:
                final_url = response.geturl()
                _validate_download_url(final_url)
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) != WEASYPRINT_ASSET_BYTES:
                    raise RuntimeStoreError(
                        "official WeasyPrint artifact size changed: expected "
                        f"{WEASYPRINT_ASSET_BYTES}, got {content_length}"
                    )
                written = 0
                with destination.open("xb") as output:
                    while chunk := response.read(1024 * 1024):
                        written += len(chunk)
                        if written > WEASYPRINT_ASSET_BYTES:
                            raise RuntimeStoreError(
                                "official WeasyPrint artifact exceeded its reviewed size"
                            )
                        output.write(chunk)
                if written != WEASYPRINT_ASSET_BYTES:
                    raise RuntimeStoreError(
                        "official WeasyPrint artifact was truncated: expected "
                        f"{WEASYPRINT_ASSET_BYTES} bytes, got {written}"
                    )
            return
        except (OSError, ValueError, urllib.error.URLError, RuntimeStoreError) as error:
            last_error = error
            destination.unlink(missing_ok=True)
            if attempt + 1 < _DOWNLOAD_ATTEMPTS:
                time.sleep(2**attempt)
    assert last_error is not None
    raise RuntimeStoreError(
        f"could not download the official WeasyPrint artifact after "
        f"{_DOWNLOAD_ATTEMPTS} attempts: {last_error}"
    ) from last_error


def executable_in_runtime(runtime: Path) -> Path:
    executable = runtime / WEASYPRINT_EXECUTABLE
    if not executable.is_file() or executable.is_symlink():
        raise RuntimeStoreError(
            f"prepared WeasyPrint runtime is missing {WEASYPRINT_EXECUTABLE.as_posix()}"
        )
    return executable


def probe_runtime(
    runtime: Path,
    *,
    runner: Any = subprocess.run,
    render: bool = True,
) -> str:
    """Exercise the absolute CLI path and return its reported version."""

    executable = executable_in_runtime(runtime)
    try:
        version_result = runner(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeStoreError(f"could not start prepared WeasyPrint: {error}") from error
    version_output = "\n".join(
        part.strip()
        for part in (version_result.stdout, version_result.stderr)
        if part.strip()
    )
    if version_result.returncode or WEASYPRINT_VERSION not in version_output:
        raise RuntimeStoreError(
            "prepared WeasyPrint returned an unexpected version result: "
            + (version_output or f"exit status {version_result.returncode}")
        )
    if not render:
        return WEASYPRINT_VERSION

    with tempfile.TemporaryDirectory(prefix="prodockit-weasyprint-probe-") as temporary:
        directory = Path(temporary)
        source = directory / "probe.html"
        output = directory / "probe.pdf"
        source.write_text(
            "<!doctype html><meta charset='utf-8'><p>PDF runtime test</p>",
            encoding="utf-8",
        )
        try:
            rendered = runner(
                [str(executable), "--quiet", str(source), str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_PROBE_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeStoreError(f"prepared WeasyPrint render failed: {error}") from error
        if rendered.returncode:
            detail = "\n".join(
                part.strip() for part in (rendered.stdout, rendered.stderr) if part.strip()
            )
            raise RuntimeStoreError(
                "prepared WeasyPrint render failed: "
                + (detail or f"exit status {rendered.returncode}")
            )
        try:
            valid_pdf = output.read_bytes().startswith(b"%PDF")
        except OSError:
            valid_pdf = False
        if not valid_pdf:
            raise RuntimeStoreError("prepared WeasyPrint did not produce a PDF")
    return WEASYPRINT_VERSION


class WindowsWeasyPrintProvider:
    """Resolve and verify the official Windows x64 onedir release."""

    def resolve(
        self, policy: ComponentPolicy, environment: RuntimeEnvironment
    ) -> ArtifactDescriptor:
        if environment.system != "windows" or environment.architecture not in _WINDOWS_X64:
            raise RuntimeProviderUnavailableError(
                "the project-local WeasyPrint runtime supports Windows x64 only; "
                f"this host is {environment.system} {environment.architecture}"
            )
        if policy.version not in {"supported", WEASYPRINT_VERSION}:
            raise RuntimeProviderUnavailableError(
                f"this release supports WeasyPrint {WEASYPRINT_VERSION}; "
                f"pdk-pdf.toml requests {policy.version}"
            )
        return ArtifactDescriptor(
            component="weasyprint",
            version=WEASYPRINT_VERSION,
            source_url=WEASYPRINT_ASSET_URL,
            sha256=WEASYPRINT_ASSET_SHA256,
            licence="BSD-3-Clause",
            provenance="official Kozea/WeasyPrint v70.0 Windows onedir release",
            platform=environment.system,
            architecture=environment.architecture,
            environment_identity=environment.identity,
            archive_format="zip",
            expected_paths=(
                WEASYPRINT_EXECUTABLE.as_posix(),
                WEASYPRINT_LICENCE.as_posix(),
            ),
        )

    def acquire(self, descriptor: ArtifactDescriptor, destination: Path) -> None:
        if descriptor.source_url != WEASYPRINT_ASSET_URL:
            raise RuntimeStoreError("refusing an unreviewed WeasyPrint artifact")
        _download_official_artifact(descriptor.source_url, destination)

    def probe(self, descriptor: ArtifactDescriptor, runtime: Path) -> None:
        if descriptor.version != WEASYPRINT_VERSION:
            raise RuntimeStoreError("refusing to probe an unsupported WeasyPrint runtime")
        probe_runtime(runtime)


__all__ = [
    "WEASYPRINT_ASSET_BYTES",
    "WEASYPRINT_ASSET_SHA256",
    "WEASYPRINT_ASSET_URL",
    "WEASYPRINT_EXECUTABLE",
    "WEASYPRINT_VERSION",
    "WindowsWeasyPrintProvider",
    "executable_in_runtime",
    "probe_runtime",
]
