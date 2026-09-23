# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Find standalone Jinja controls that can break a Markdown pipe table.

This deliberately scans source rather than rendering a chosen Jinja branch:
both branches must remain valid, and a diagnostic must not need the website's
template context. A header and delimiter establish a table; only untrimmed
controls followed by another row in that same source table are reported.
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"^[ ]{0,3}(?P<marker>`{3,}|~{3,})(?P<rest>.*)$")
_CONTROL = re.compile(
    r"^[ ]{0,3}\{%(?P<leading>-?)\s*(?P<kind>if|elif|else|endif)"
    r"\b.*?(?P<trailing>-?)%\}\s*$"
)
_RAW_START = re.compile(r"^[ ]{0,3}\{%[-]?\s*raw\s*[-]?%\}\s*$")
_RAW_END = re.compile(r"^[ ]{0,3}\{%[-]?\s*endraw\s*[-]?%\}\s*$")
_DELIMITER = re.compile(r":?-{3,}:?\Z")


def _without_html_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    """Mask HTML comments without joining text on opposite sides of one."""
    visible = list(line)
    position = 0
    while position < len(line):
        if in_comment:
            end = line.find("-->", position)
            stop = len(line) if end < 0 else end + 3
            visible[position:stop] = " " * (stop - position)
            if end < 0:
                return "".join(visible), True
            position = stop
            in_comment = False
            continue
        start = line.find("<!--", position)
        if start < 0:
            break
        visible[start : start + 4] = " " * 4
        position = start + 4
        in_comment = True
    return "".join(visible), in_comment


def _visible_lines(source: str) -> list[str]:
    """Exclude quoted examples, code, comments and Jinja raw blocks."""
    lines = source.splitlines()
    visible: list[str] = []
    fence: tuple[str, int] | None = None
    comment = False
    raw = False
    front_matter = lines[:1] in (["---"], ["+++"])
    front_marker = lines[0] if front_matter else ""
    for number, original in enumerate(lines):
        if front_matter:
            visible.append("")
            if number > 0 and original.strip() == front_marker:
                front_matter = False
            continue
        if fence is not None:
            marker = _FENCE.match(original)
            if marker is not None:
                run = marker.group("marker")
                if run[0] == fence[0] and len(run) >= fence[1] and not marker.group("rest").strip():
                    fence = None
            visible.append("")
            continue
        if raw:
            if _RAW_END.fullmatch(original):
                raw = False
            visible.append("")
            continue
        line, comment = _without_html_comments(original, comment)
        if original.startswith(("    ", "\t")) or original.lstrip().startswith(">"):
            visible.append("")
            continue
        if _RAW_START.fullmatch(line):
            raw = True
            visible.append("")
            continue
        marker = _FENCE.match(line)
        if marker is not None:
            run = marker.group("marker")
            fence = (run[0], len(run))
            visible.append("")
            continue
        visible.append(line)
    return visible


def _cells(line: str) -> tuple[str, ...] | None:
    """Split on unescaped pipes outside balanced Markdown inline code."""
    text = line.strip()
    if not text:
        return None
    separators: list[int] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] == "\\" and cursor + 1 < len(text):
            cursor += 2
            continue
        if text[cursor] == "`":
            end = cursor
            while end < len(text) and text[end] == "`":
                end += 1
            run_length = end - cursor
            closing = text.find("`" * run_length, end)
            while closing >= 0 and (
                (closing > 0 and text[closing - 1] == "`")
                or (closing + run_length < len(text) and text[closing + run_length] == "`")
            ):
                closing = text.find("`" * run_length, closing + run_length)
            if closing >= 0:
                cursor = closing + run_length
                continue
            cursor = end
            continue
        if text[cursor] == "|":
            separators.append(cursor)
        cursor += 1
    if not separators:
        return None
    bounds = [-1, *separators, len(text)]
    parts = [
        text[bounds[index] + 1 : bounds[index + 1]].strip()
        for index in range(len(bounds) - 1)
    ]
    if separators[0] == 0:
        parts.pop(0)
    if separators[-1] == len(text) - 1:
        parts.pop()
    return tuple(parts) if parts else None


def _starts_table(header: str, delimiter: str) -> bool:
    headings = _cells(header)
    markers = _cells(delimiter)
    return bool(
        headings
        and markers
        and len(headings) == len(markers)
        and any(headings)
        and all(_DELIMITER.fullmatch(cell) for cell in markers)
    )


def untrimmed_table_controls(source: str) -> tuple[int, ...]:
    """One-based source lines for untrimmed controls between table rows."""
    lines = _visible_lines(source)
    findings: list[int] = []
    pending: list[int] = []
    in_table = False
    table_condition_depth = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if _starts_table(line, following):
            in_table = True
            table_condition_depth = 0
            pending.clear()
            index += 2
            continue
        if not in_table:
            index += 1
            continue
        control = _CONTROL.fullmatch(line)
        if control is not None:
            if not control.group("trailing"):
                pending.append(index + 1)
            if control.group("kind") == "if":
                table_condition_depth += 1
            elif control.group("kind") == "endif" and table_condition_depth:
                table_condition_depth -= 1
                # A closing control can detach a caption even with no later row.
                findings.extend(pending)
                pending.clear()
        elif (cells := _cells(line)) is not None and not all(
            _DELIMITER.fullmatch(cell) for cell in cells
        ):
            findings.extend(pending)
            pending.clear()
        else:
            in_table = False
            table_condition_depth = 0
            pending.clear()
        index += 1
    return tuple(findings)


__all__ = ["untrimmed_table_controls"]
