# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Collect caption blocks at the Markdown block boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import markdown
import yaml
from bs4 import BeautifulSoup

from prodockit.headings import PREPARED_CAPTION_NUMBER_ATTR
from prodockit.portable import PortableError

CAPTION_EXTENSION = "pymdownx.blocks.caption"
_OPEN = re.compile(
    r"(?P<fence>/{3,})[ \t]+(?P<kind>figure-caption|table-caption)"
    r"(?:[ \t]*\|[ \t]*(?P<argument>.*?))?[ \t]*$"
)
_SELECTOR = re.compile(r"(?:[<>][ \t]*)?(?:[.#][\w:.-]+)*$")


def register_caption_rule(parser: Any) -> None:
    """Keep caption blocks distinct from prose and from literal code examples."""

    def caption(state: Any, first: int, end: int, silent: bool) -> bool:
        def content(line: int) -> str:
            return str(state.src[state.bMarks[line] + state.tShift[line] : state.eMarks[line]])

        indent = state.sCount[first]
        opening = _OPEN.fullmatch(content(first))
        if opening is None or indent - state.blkIndent >= 4:
            return False
        close = first + 1
        while close < end:
            line = content(close)
            if line.strip() and state.sCount[close] < indent:
                break
            if state.sCount[close] == indent and line.rstrip() == opening["fence"]:
                if not silent:
                    token = state.push("pdk_caption", "", 0)
                    token.map = [first, close + 1]
                    token.markup = opening["fence"]
                    state.line = close + 1
                return True
            close += 1
        return False

    parser.block.ruler.before("paragraph", "pdk_caption", caption, {"alt": ["paragraph"]})


@dataclass(frozen=True)
class Caption:
    start: int
    options_start: int
    options_end: int
    options_indent: str
    kind: str
    ident: str | None
    attrs: dict[str, Any]

    def numbered_options(self, number: str) -> str:
        attrs = {**self.attrs, PREPARED_CAPTION_NUMBER_ATTR: number}
        options = yaml.safe_dump({"attrs": attrs}, default_flow_style=True, width=10_000).strip()
        # A single flow mapping on one option line is valid at any list depth.
        return self.options_indent + options.removeprefix("{").removesuffix("}") + "\n\n"


def read_caption(
    source: str, start: int, line: int, raw: str, config: dict[str, Any]
) -> Caption:
    """Qualify an isolated caption with the configured public Markdown extension."""
    location = f"{source}:{line}"
    lines = raw.splitlines(keepends=True)
    opening = lines[0].rstrip("\n")
    indent = len(opening) - len(opening.lstrip(" "))
    parsed = _OPEN.fullmatch(opening[indent:])
    if parsed is None or (indent and indent % 4):
        raise PortableError(f"{location}: use four-space indentation for list captions")
    argument = parsed["argument"] or ""
    if not _SELECTOR.fullmatch(argument):
        raise PortableError(f"{location}: custom caption numbering or selectors are unsupported")
    option_indent = " " * (indent + 4)
    count = 1
    while count < len(lines) - 1 and lines[count].startswith(option_indent):
        count += 1
    attrs: dict[str, Any] = {}
    if count > 1:
        try:
            options = yaml.safe_load("".join(line[len(option_indent):] for line in lines[1:count]))
        except yaml.YAMLError as error:
            raise PortableError(f"{location}: invalid caption options") from error
        if (
            not isinstance(options, dict) or set(options) != {"attrs"}
            or not isinstance(options["attrs"], dict)
            or PREPARED_CAPTION_NUMBER_ATTR in options["attrs"]
        ):
            raise PortableError(f"{location}: use a caption attrs mapping")
        attrs = options["attrs"]

    # Use a stand-in for the preceding authored block. The real renderer still
    # owns the table or image, its Markdown, and the final figure layout.
    fragment = "".join(line[indent:] if line.strip() else line for line in lines)
    md = markdown.Markdown(
        extensions=[CAPTION_EXTENSION], extension_configs={CAPTION_EXTENSION: config}
    )
    figure = BeautifulSoup(md.convert("Content\n\n" + fragment), "html.parser").figure
    if figure is None or figure.select_one("figcaption .caption-prefix") is None:
        raise PortableError(
            f"{location}: configured caption extension did not render a numbered figure"
        )
    ident = figure.get("id")
    if not isinstance(ident, str) or re.fullmatch(rf"__{parsed['kind']}_\d+(?:_\d+)*", ident):
        ident = None
    return Caption(
        start,
        start + len(lines[0]),
        start + sum(map(len, lines[:count])),
        option_indent,
        parsed["kind"],
        ident,
        attrs,
    )
