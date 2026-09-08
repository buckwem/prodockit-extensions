# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Validated, cached installation of the citation style Adopt supports."""

from __future__ import annotations

import os
import shutil
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from prodockit.toolchain import _cache_root

DEFAULT_CSL_STYLE = "harvard-cite-them-right.csl"
CSL_STYLE_URL = "https://www.zotero.org/styles/harvard-cite-them-right"
CSL_NAMESPACE = "http://purl.org/net/xbiblio/csl"
MAX_CSL_BYTES = 2 * 1024 * 1024


class CslError(Exception):
    """A configured citation style could not be provisioned safely."""


def cache_path() -> Path:
    """Return the stable native-download cache path for the supported style."""
    return _cache_root() / "csl" / DEFAULT_CSL_STYLE


def validate(path: Path) -> None:
    """Require a bounded XML document with the root shape defined by CSL."""
    try:
        size = path.stat().st_size
        if not size:
            raise CslError(f"citation style is empty: {path}")
        if size > MAX_CSL_BYTES:
            raise CslError(f"citation style is unexpectedly large: {path}")
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise CslError(f"citation style is not valid XML: {path}: {error}") from error
    if root.tag != f"{{{CSL_NAMESPACE}}}style":
        raise CslError(f"download is XML but not a CSL style: {path}")
    if not root.get("version") or root.find(f"{{{CSL_NAMESPACE}}}info") is None:
        raise CslError(f"citation style is missing required CSL metadata: {path}")


def _atomic_copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + f".{os.getpid()}.part")
    try:
        shutil.copy2(source, temporary)
        validate(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _download(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + f".{os.getpid()}.part")
    request = urllib.request.Request(CSL_STYLE_URL, headers={"User-Agent": "prodockit-adopt"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as out:
            remaining = MAX_CSL_BYTES + 1
            while remaining:
                block = response.read(min(1024 * 1024, remaining))
                if not block:
                    break
                out.write(block)
                remaining -= len(block)
        validate(temporary)
        temporary.replace(destination)
    except (OSError, urllib.error.URLError, CslError) as error:
        raise CslError(f"could not download {CSL_STYLE_URL}: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def install(destination: Path, *, offline: bool = False) -> Path:
    """Install the supported style atomically, preferring a validated cache."""
    if destination.exists():
        if not destination.is_file():
            raise CslError(f"configured citation-style path is not a file: {destination}")
        return destination

    cached = cache_path()
    if cached.is_file():
        try:
            validate(cached)
            return _atomic_copy(cached, destination)
        except CslError as error:
            if offline:
                raise CslError(
                    f"offline mode found an invalid cached citation style at {cached}; "
                    f"remove it and obtain {CSL_STYLE_URL} online"
                ) from error
            cached.unlink(missing_ok=True)

    if offline:
        raise CslError(
            "offline mode needs the validated citation style cache; "
            f"obtain {CSL_STYLE_URL} online first (cache: {cached})"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    _download(destination)
    cached.parent.mkdir(parents=True, exist_ok=True)
    _atomic_copy(destination, cached)
    return destination


__all__ = [
    "CSL_STYLE_URL",
    "DEFAULT_CSL_STYLE",
    "CslError",
    "cache_path",
    "install",
    "validate",
]
