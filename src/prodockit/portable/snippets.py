# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Capture the literal code includes that Zensical will expand with PyMdown."""

from __future__ import annotations

import re
from pathlib import Path

from prodockit.portable import PortableError
from prodockit.portable.manifest import relative_path

EXTENSION = "pymdownx.snippets"
_MARKER = re.compile(r"""^[ \t]*-+8<-+(?:[ \t]+(?=["'])|$)""")
_INCLUDE = re.compile(r"""^[ \t]*-+8<-+[ \t]+(?P<quote>["'])(?P<path>[^"'\\]+)(?P=quote)$""")
_SECTION = re.compile(r"(?<![;-])-+8<-+[ \t]+\[[ \t]*(?:start|end)[ \t]*:", re.IGNORECASE)
_FENCE = re.compile(r"(?m)^[ \t]*(?:`{3,}|~{3,})")


def directive(line: str, *, location: str, in_code: bool) -> Path | None:
    if not _MARKER.match(line) and not _SECTION.search(line):
        return None
    match = _INCLUDE.fullmatch(line)
    if not in_code or match is None:
        raise PortableError(f"{location}: portable snippets require whole-file includes in fences")
    try:
        return relative_path(match["path"].strip())
    except PortableError as error:
        raise PortableError(f"{location}: snippet must use a project-relative file path") from error


def capture(root: Path, name: Path, *, location: str, files: dict[Path, bytes]) -> Path:
    path = root / name
    if name.parts[0] in {".git", ".pdk"} or any(
        candidate.is_symlink()
        for candidate in (path, *path.parents)
        if candidate.is_relative_to(root)
    ):
        raise PortableError(f"{location}: snippet must be a regular project source file: {name}")
    try:
        if not path.is_file():
            raise FileNotFoundError(path)
        data = files[path] if path in files else path.read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise PortableError(f"{location}: cannot read UTF-8 snippet: {name}") from error
    contains_directive = any(
        _MARKER.match(line) or _SECTION.search(line) for line in text.splitlines()
    )
    if contains_directive or _FENCE.search(text):
        raise PortableError(f"{location}: snippet would introduce a fence or an include: {name}")
    files[path] = data
    return path
