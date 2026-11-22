# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Complete half-open source spans for prepared Markdown, including copies."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from prodockit.portable import PortableError


class Replacement(Protocol):
    start: int
    end: int
    kind: str
    value: str


@dataclass(frozen=True)
class SourceText:
    """LF text for parsing, with offsets into the original decoded Unicode."""

    original: str
    text: str
    crlf_ends: tuple[int, ...]

    @classmethod
    def read(cls, original: str) -> SourceText:
        ends = tuple(
            match.end() - index - 1 for index, match in enumerate(re.finditer("\r\n", original))
        )
        return cls(original, original.replace("\r\n", "\n").replace("\r", "\n"), ends)

    def original_offset(self, offset: int) -> int:
        return offset + bisect_right(self.crlf_ends, offset)


def _line_starts(text: str) -> list[int]:
    return [0] + [index + 1 for index, character in enumerate(text) if character == "\n"]


def _position(
    starts: list[int], offset: int, *, original_offset: int | None = None
) -> dict[str, int]:
    line = bisect_right(starts, offset) - 1
    return {
        "offset": offset if original_offset is None else original_offset,
        "line": line + 1,
        "column": offset - starts[line] + 1,
    }


def apply_edits(
    source: SourceText, edits: Sequence[Replacement]
) -> tuple[str, list[dict[str, Any]]]:
    """Cover every generated character; source offsets count Unicode characters.

    Lines and columns are one-based; end positions are exclusive. A transformed
    span maps to the authored construct as a whole. Copies retain exact line
    and column correspondence after newline normalisation.
    """
    pieces: list[str] = []
    spans: list[tuple[str, int, int, int, int]] = []
    cursor = generated = 0

    def append(kind: str, start: int, end: int, value: str) -> None:
        nonlocal generated
        if start == end and not value:
            return
        pieces.append(value)
        spans.append((kind, start, end, generated, generated + len(value)))
        generated += len(value)

    for edit in sorted(edits, key=lambda item: item.start):
        if not cursor <= edit.start <= edit.end <= len(source.text):
            raise PortableError("overlapping or invalid source transformations")
        append("copy", cursor, edit.start, source.text[cursor : edit.start])
        append(edit.kind, edit.start, edit.end, edit.value)
        cursor = edit.end
    append("copy", cursor, len(source.text), source.text[cursor:])
    output = "".join(pieces)
    source_starts, generated_starts = _line_starts(source.text), _line_starts(output)
    mapping = [
        {
            "kind": kind,
            "source_start": _position(
                source_starts, start, original_offset=source.original_offset(start)
            ),
            "source_end": _position(
                source_starts, end, original_offset=source.original_offset(end)
            ),
            "generated_start": _position(generated_starts, left),
            "generated_end": _position(generated_starts, right),
        }
        for kind, start, end, left, right in spans
    ]
    return output, mapping


def original_location(mapping: list[dict[str, Any]], line: int, column: int = 1) -> tuple[int, int]:
    """Translate a valid generated location; replacements point at their source start."""
    if line < 1 or column < 1:
        raise PortableError("line and column must be positive")
    for span in mapping:
        start, end = span["generated_start"], span["generated_end"]
        if (start["line"], start["column"]) <= (line, column) < (end["line"], end["column"]):
            source = span["source_start"]
            if span["kind"] != "copy":
                return source["line"], source["column"]
            return (
                source["line"] + line - start["line"],
                source["column"] + column - start["column"] if line == start["line"] else column,
            )
    if mapping:
        end = mapping[-1]["generated_end"]
        if (line, column) == (end["line"], end["column"]):
            source = mapping[-1]["source_end"]
            return source["line"], source["column"]
    elif (line, column) == (1, 1):
        return 1, 1
    raise PortableError("location is outside the prepared source map")


def validate_source_map(original: str, generated: str, mapping: list[dict[str, Any]]) -> None:
    """Check positions, complete coverage and unchanged spans against captured text."""
    if not isinstance(mapping, list):
        raise PortableError("source map must be a list")
    source = SourceText.read(original)
    source_starts, generated_starts = _line_starts(source.text), _line_starts(generated)
    raw_cursor = normal_cursor = generated_cursor = 0
    for span in mapping:
        kind = span["kind"]
        raw_end = span["source_end"]["offset"]
        generated_end = span["generated_end"]["offset"]
        if (
            not isinstance(kind, str)
            or not kind
            or type(raw_end) is not int
            or type(generated_end) is not int
            or not raw_cursor <= raw_end <= len(original)
            or not generated_cursor <= generated_end <= len(generated)
        ):
            raise PortableError("invalid source map span")
        copied = original[raw_cursor:raw_end].replace("\r\n", "\n").replace("\r", "\n")
        normal_end = normal_cursor + len(copied)
        expected = {
            "kind": kind,
            "source_start": _position(source_starts, normal_cursor, original_offset=raw_cursor),
            "source_end": _position(source_starts, normal_end, original_offset=raw_end),
            "generated_start": _position(generated_starts, generated_cursor),
            "generated_end": _position(generated_starts, generated_end),
        }
        if (
            span != expected
            or source.original_offset(normal_end) != raw_end
            or (kind == "copy" and copied != generated[generated_cursor:generated_end])
        ):
            raise PortableError("source map positions or copied text do not match")
        raw_cursor, normal_cursor, generated_cursor = raw_end, normal_end, generated_end
    if raw_cursor != len(original) or generated_cursor != len(generated):
        raise PortableError("source map does not cover the complete document")
