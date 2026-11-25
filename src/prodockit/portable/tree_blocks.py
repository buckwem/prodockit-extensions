# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Recognise raw tree listings without replacing Prodockit's tree renderer."""

from __future__ import annotations

import re
from typing import Any

import yaml
from pymdownx.blocks.block import type_html_attribute_dict

from prodockit.portable import PortableError
from prodockit.tree import TreeBlock

EXTENSION = "prodockit.tree"
_OPEN = re.compile(r"(?P<fence>/{3,}) *tree *")
_AFFECTED_ATTRIBUTES = {"data-term", "data-cite-text", "data-pdk-caption-number", "markdown"}


def register_tree_rule(parser: Any) -> None:
    """Reserve the listing and its closing fence before the step-marker rule."""

    def tree(state: Any, first: int, end: int, silent: bool) -> bool:
        indent = state.sCount[first]
        if indent != state.blkIndent or state.listIndent >= 0 or state.parentType == "blockquote":
            return False

        def content(line: int) -> str:
            return str(state.src[state.bMarks[line] + state.tShift[line]:state.eMarks[line]])

        opening = _OPEN.fullmatch(content(first))
        if opening is None:
            return False
        if silent:
            return True
        fence = opening["fence"]
        close = first + 1
        while close < end:
            if not state.isEmpty(close) and state.sCount[close] < indent:
                break
            if state.sCount[close] == indent and content(close).rstrip(" ") == fence:
                break
            close += 1
        closed = close < end and state.sCount[close] == indent and (
            content(close).rstrip(" ") == fence
        )

        token = state.push("pdk_tree", "", 0)
        token.markup = fence
        token.map = [first, close + 1 if closed else first + 1]
        token.meta = {"closed": closed, "options": ""}
        if closed:
            option_end = first + 1
            while (
                option_end < close
                and not state.isEmpty(option_end)
                and state.sCount[option_end] >= indent + 4
            ):
                option_end += 1
            token.meta["options"] = state.getLines(first + 1, option_end, indent + 4, False)
        state.line = token.map[1]
        return True

    parser.block.ruler.before("paragraph", "pdk_tree", tree, {"alt": ["paragraph"]})


def check_options(source: str, location: str) -> None:
    if not source:
        return
    try:
        options = yaml.safe_load(source)
        if not isinstance(options, dict) or options.keys() - (TreeBlock.OPTIONS.keys() | {"attrs"}):
            raise ValueError("unknown tree option")
        for name, value in options.items():
            if name == "attrs":
                attrs = type_html_attribute_dict(value)
                if _AFFECTED_ATTRIBUTES.intersection(key.lower() for key in attrs):
                    raise PortableError(f"{location}: affected syntax in tree attributes")
            else:
                TreeBlock.OPTIONS[name][1](value)
                if name == "indent" and int(value) < 1:
                    raise ValueError("tree indentation must be positive")
    except PortableError:
        raise
    except (ValueError, TypeError, OverflowError, yaml.YAMLError) as error:
        raise PortableError(f"{location}: invalid tree options") from error
