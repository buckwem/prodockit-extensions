# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Protect literal text while scanning native Markdown HTML blocks."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from markdown.util import BLOCK_LEVEL_ELEMENTS

_LITERAL_TAGS = {"pre", "code"}
_BLOCK_ROOTS = set(BLOCK_LEVEL_ELEMENTS) - {"hr"}
_LITERAL_OPEN = re.compile(r"<(?:pre|code)(?=[\s>])", re.IGNORECASE)


class _LiteralText(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.line_starts = [0, *(match.end() for match in re.finditer("\n", source))]
        self.frames: list[str] = []
        self.ranges: list[tuple[int, int]] = []
        self.root: str | None = None
        self.root_depth = 0
        self.valid = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_startendtag(tag, attrs)
        if self.root is None and tag in _BLOCK_ROOTS:
            line, column = self.getpos()
            line_start = self.line_starts[line - 1]
            if not self.source[line_start:line_start + column].strip():
                self.root = tag
        if tag == self.root:
            self.root_depth += 1
        if self.root is not None and tag in _LITERAL_TAGS:
            self.frames.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if any(name == "markdown" for name, _ in attrs):
            self.valid = False

    def handle_endtag(self, tag: str) -> None:
        if self.root is None:
            return
        if tag in _LITERAL_TAGS:
            if self.frames and self.frames[-1] == tag:
                self.frames.pop()
            else:
                self.valid = False
        if tag == self.root:
            self.root_depth -= 1
            if self.root_depth == 0:
                self.root = None
                if self.frames:
                    self.valid = False

    def handle_data(self, data: str) -> None:
        if self.frames:
            line, column = self.getpos()
            start = self.line_starts[line - 1] + column
            self.ranges.append((start, start + len(data)))


def mask_literal_text(source: str) -> str:
    """Mask only text inside balanced literal tags in a raw HTML block."""
    if not _LITERAL_OPEN.search(source):
        return source
    parser = _LiteralText(source)
    parser.feed(source)
    parser.close()
    if not parser.valid or parser.root is not None or parser.frames:
        return source

    parts: list[str] = []
    cursor = 0
    for start, end in parser.ranges:
        parts.extend((source[cursor:start], re.sub(r"[^\n]", " ", source[start:end])))
        cursor = end
    parts.append(source[cursor:])
    return "".join(parts)
