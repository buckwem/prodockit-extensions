# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Check the boundaries of authored steps without changing their renderer."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import yaml
from pymdownx.blocks.block import type_html_attribute_dict

from prodockit.portable import PortableError

EXTENSION = "prodockit.steps"
_MARKER = re.compile(r"(?P<fence>/{3,})(?: *(?P<kind>steps|step)(?: *\| *(?P<title>.*?))?)? *")
_AFFECTED_ATTRIBUTES = {"data-term", "data-cite-text", "data-pdk-caption-number", "markdown"}


def register_step_rule(parser: Any) -> None:
    """Recognise one slash marker at a time so literal fences own their contents."""

    def step(state: Any, first: int, end: int, silent: bool) -> bool:
        indent = state.sCount[first]
        if indent != state.blkIndent or state.listIndent >= 0 or state.parentType == "blockquote":
            return False

        line = state.src[state.bMarks[first] + state.tShift[first]:state.eMarks[first]]
        match = _MARKER.fullmatch(line)
        if match is None:
            return False
        if silent:
            return True

        kind, title = match["kind"], match["title"]
        last = first + 1
        if kind:
            while last < end and not state.isEmpty(last) and state.sCount[last] >= indent + 4:
                last += 1

        token = state.push("pdk_step_marker", "", 0)
        token.map = [first, last]
        token.meta = {
            "kind": kind,
            "fence": match["fence"],
            "title": title,
            "options": state.getLines(first + 1, last, indent + 4, False),
        }
        if title:
            inline = state.push("inline", "", 0)
            inline.content = title
            inline.map = [first, first + 1]
        state.line = last
        return True

    parser.block.ruler.before("paragraph", "pdk_step_marker", step, {"alt": ["paragraph"]})


def _check_options(options: str, kind: str, location: str) -> None:
    if not options:
        return
    allowed = {"attrs", "start"} if kind == "steps" else {"attrs"}
    try:
        data = yaml.safe_load(options)
        if not isinstance(data, dict) or data.keys() - allowed:
            raise ValueError("unknown option or missing mapping")
        if "start" in data:
            if not isinstance(data["start"], (int, float)):
                raise ValueError("start must be a number")
            int(data["start"])
        attrs = type_html_attribute_dict(data.get("attrs", {}))
    except (ValueError, TypeError, OverflowError, yaml.YAMLError) as error:
        raise PortableError(f"{location}: invalid {kind} options") from error
    if _AFFECTED_ATTRIBUTES.intersection(name.lower() for name in attrs):
        raise PortableError(f"{location}: affected syntax in step attributes is unsupported")


@dataclass(frozen=True)
class StepBlock:
    kind: str
    fence: str
    level: int
    location: str


def qualify_steps(tokens: list[Any], source_location: Callable[[int], str]) -> None:
    """Give a balanced steps procedure the same token boundaries as other containers."""
    blocks: list[StepBlock] = []
    for token in tokens:
        level = token.level
        parent = blocks[-1] if blocks else None
        token.level += len(blocks)
        if token.type == "pdk_container_close":
            if blocks and blocks[-1].level > level:
                raise PortableError(f"{blocks[-1].location}: unclosed {blocks[-1].kind} block")
            continue
        if token.type != "pdk_step_marker":
            if parent is None or token.map is None:
                continue
            if parent.kind == "steps":
                location = source_location(token.map[0])
                raise PortableError(f"{location}: put procedure content inside a step block")
            if (token.type, level - parent.level) in {("inline", 1), ("pdk_caption", 0)}:
                token.meta["step_body_fence"] = parent.fence
            continue

        location = source_location(token.map[0])
        kind, fence = token.meta["kind"], token.meta["fence"]
        if kind is None:
            if parent is None or fence != parent.fence or level != parent.level:
                raise PortableError(f"{location}: unmatched steps fence")
            blocks.pop()
            token.type = "pdk_container_close"
            continue
        if kind == "step" and (parent is None or parent.kind != "steps" or level != parent.level):
            raise PortableError(f"{location}: a step must be inside its steps block")
        if kind == "steps" and (
            token.meta["title"] is not None or (parent is not None and parent.kind == "steps")
        ):
            raise PortableError(f"{location}: invalid steps opener")
        if parent and len(fence) <= len(parent.fence):
            raise PortableError(f"{location}: nested steps fences must use more slashes")
        _check_options(token.meta["options"], kind, location)
        blocks.append(StepBlock(kind, fence, level, location))
        token.type = "pdk_container_open"
        token.meta = {"heading_title": False}
    if blocks:
        raise PortableError(f"{blocks[-1].location}: unclosed {blocks[-1].kind} block")
