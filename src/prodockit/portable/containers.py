# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Identify native indentation-based containers for portable source checks."""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Any

_CLASSES = r"[\w-]+(?: +[\w-]+)*"
_OPENINGS = {
    "admonition": re.compile(rf'!!! ?{_CLASSES}(?: +"(?P<title>.*?)")? *'),
    "pymdownx.details": re.compile(
        rf'\?{{3}}\+? ?(?:(?:{_CLASSES})? +"(?P<title>.*?)"|{_CLASSES}) *'
    ),
    "pymdownx.tabbed": re.compile(r'===(?:\+!?|!\+?)? +"(?P<title>.*?)" *'),
}


def register_container_rule(parser: Any, extensions: Collection[str]) -> None:
    """Tokenise the body at native four-space indentation without rendering it."""
    openings = [(name, pattern) for name, pattern in _OPENINGS.items() if name in extensions]
    if not openings:
        return

    def container(state: Any, first: int, end: int, silent: bool) -> bool:
        indent = state.sCount[first]
        if (
            indent != state.blkIndent or state.listIndent >= 0
            or state.parentType == "blockquote" or state.level >= state.md.options.maxNesting - 3
        ):
            return False

        line = state.src[state.bMarks[first] + state.tShift[first]:state.eMarks[first]]
        for extension, pattern in openings:
            match = pattern.fullmatch(line)
            if match is not None:
                is_admonition = extension == "admonition"
                heading_title = extension == "pymdownx.details" and (
                    match["title"] or ""
                ).startswith("#")
                break
        else:
            return False
        if silent:
            return True

        last = first + 1
        while last < end and (state.isEmpty(last) or state.sCount[last] >= indent + 4):
            last += 1

        opening = state.push("pdk_container_open", "", 1)
        opening.map = [first, last]
        title = match["title"] or ""
        opening.meta = {"heading_title": heading_title}
        if title:
            inline = state.push("inline", "", 0)
            inline.content = title
            inline.map = [first, first + 1]

        parent_type = state.parentType
        state.parentType = "pdk_container"
        state.blkIndent = indent + 4
        body_start = len(state.tokens)
        try:
            state.md.block.tokenize(state, first + 1, last)
        finally:
            state.blkIndent = indent
            state.parentType = parent_type
        if is_admonition:
            for token in state.tokens[body_start:]:
                if (token.type, token.level - opening.level) in {
                    ("inline", 2), ("pdk_caption", 1),
                }:
                    token.meta["admonition_indent"] = indent + 4
        state.push("pdk_container_close", "", -1)
        state.line = last
        return True

    parser.block.ruler.before("paragraph", "pdk_container", container, {"alt": ["paragraph"]})


def is_aligned_fence(raw: str, marker: str, info: str) -> bool:
    """Recognise a closed literal fence that SuperFences also consumes."""
    lines = raw.splitlines()
    indent = lines[0].partition(marker)[0]
    return (
        len(lines) >= 2
        and not indent.strip(" ")
        and re.fullmatch(r"[\w+#.-]*", info.strip()) is not None
        and lines[-1].rstrip(" \t") == indent + marker
        and all(not line.strip() or line.startswith(indent) for line in lines[1:-1])
    )
