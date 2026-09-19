# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Bounded downloads for reviewed PDF-runtime artifacts."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from prodockit.pdf.runtime_store import RuntimeStoreError

_DOWNLOAD_HOSTS = frozenset(
    {
        "github.com",
        "codeload.github.com",
        "files.pythonhosted.org",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
)
_DOWNLOAD_TIMEOUT = 45.0
_DOWNLOAD_ATTEMPTS = 3


def validate_release_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _DOWNLOAD_HOSTS:
        raise RuntimeStoreError(f"refusing unapproved runtime download URL: {url}")
    if parsed.username or parsed.password:
        raise RuntimeStoreError("refusing a runtime download URL containing credentials")


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
        validate_release_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_download(request: urllib.request.Request, timeout: float) -> Any:
    opener = urllib.request.build_opener(_TrustedRedirectHandler())
    return opener.open(request, timeout=timeout)


def download_release_asset(
    url: str,
    destination: Path,
    *,
    expected_bytes: int,
    label: str,
) -> None:
    """Download one immutable reviewed asset with strict host and size bounds."""

    validate_release_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "Prodockit-PDF-Runtime/1"})
    last_error: Exception | None = None
    for attempt in range(_DOWNLOAD_ATTEMPTS):
        destination.unlink(missing_ok=True)
        try:
            with _open_download(request, _DOWNLOAD_TIMEOUT) as response:
                validate_release_url(response.geturl())
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) != expected_bytes:
                    raise RuntimeStoreError(
                        f"official {label} artifact size changed: expected "
                        f"{expected_bytes}, got {content_length}"
                    )
                written = 0
                with destination.open("xb") as output:
                    while chunk := response.read(1024 * 1024):
                        written += len(chunk)
                        if written > expected_bytes:
                            raise RuntimeStoreError(
                                f"official {label} artifact exceeded its reviewed size"
                            )
                        output.write(chunk)
                if written != expected_bytes:
                    raise RuntimeStoreError(
                        f"official {label} artifact was truncated: expected "
                        f"{expected_bytes} bytes, got {written}"
                    )
            return
        except (OSError, ValueError, urllib.error.URLError, RuntimeStoreError) as error:
            last_error = error
            destination.unlink(missing_ok=True)
            if attempt + 1 < _DOWNLOAD_ATTEMPTS:
                time.sleep(2**attempt)
    assert last_error is not None
    raise RuntimeStoreError(
        f"could not download the official {label} artifact after "
        f"{_DOWNLOAD_ATTEMPTS} attempts: {last_error}"
    ) from last_error


__all__ = ["download_release_asset", "validate_release_url"]
