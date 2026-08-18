# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""``prodockit.tree`` - a directory listing that looks like one.

A file tree written as a bullet list is three decisions per line: which
icon, whether to embolden the folder, and where the description starts.
Every one of them can be made differently on the next line, and the
listing this replaces had already drifted from the directory it claimed
to map (prodockit-extensions#379).

Written on pymdownx's Blocks API - the machinery Material's own
admonitions and tabs use, and the same one ``prodockit.steps`` is built
on - so the body is the listing itself::

    /// tree
    docs/ - the documentation source tree
      index.md - the cover page
      stylesheets/ - CSS for both outputs
        extra.css - website customisations
    zensical.toml - project configuration
    ///

Indentation is the structure and a trailing ``/`` is the only marker: an
entry ending in one is a directory, anything else is a file. Nothing
about the icon, the emphasis or the alignment is typed per line, so
nothing about them can disagree between two lines.

The description is optional and separated by `` - ``. It becomes an
element of its own rather than trailing text, so a stylesheet can align
the column, dim it, or drop it from the PDF without touching the names.

**Indentation must be consistent, and ragged indentation is an error
rather than a guess.** A listing is read for its shape; silently
attaching an entry to the wrong parent because its indent was three
spaces where the line above used two would be worse than refusing it.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree
from typing import Any, ClassVar

from pymdownx.blocks import BlocksExtension
from pymdownx.blocks.block import Block, type_number, type_string

#: The wrapper, and the parts of each entry. Named rather than styled
#: here: prodockit ships the structure, a project ships the look - the
#: same arrangement `prodockit.steps` and `prodockit.tables` have.
TREE_CLASS = "prodockit-tree"
DIRECTORY_CLASS = "tree-directory"
FILE_CLASS = "tree-file"
NAME_CLASS = "tree-name"
ICON_CLASS = "tree-icon"
NOTE_CLASS = "tree-note"

#: `name - description`, with the description optional. Spaces around the
#: dash are required: a hyphen inside a filename (`pull_request_template`
#: has none, but `harvard-cite-them-right.csl` does) must not be read as
#: the start of a description.
_ENTRY = re.compile(r"^(?P<name>\S+)(?:\s+-\s+(?P<note>\S.*))?$")


class TreeError(ValueError):
    """A listing that cannot be read as a tree.

    Raised rather than guessed at: an entry silently attached to the
    wrong parent is a wrong diagram, and a wrong diagram is read as fact.
    """


def _depth(line: str, unit: int) -> int:
    """How deep `line` sits, in units of `unit` spaces."""
    indent = len(line) - len(line.lstrip(" "))
    if indent % unit:
        raise TreeError(
            f"indent of {indent} is not a multiple of {unit}: {line.strip()!r}"
        )
    return indent // unit


class TreeBlock(Block):  # type: ignore[misc]
    """``/// tree`` - the listing."""

    NAME = "tree"
    ARGUMENT = None
    #: `indent` is how many spaces one level costs. Two by default,
    #: because that is what a listing pasted from `tree` or written by
    #: hand tends to use, and four is common enough to be worth allowing
    #: rather than silently mis-reading.
    #: Lucide's outlined folder and file by default: at the size an entry
#: is set in, a filled folder reads as a dark blob competing with the
#: name beside it, where an outline still reads as a folder.
#:
#: The icons are written as shortcodes and left for the project's own
    #: icon extension to render, so a tree gets whatever set that project
    #: already uses - Material's by default here, or anything under a
    #: configured `custom_icons` directory. Emitting SVG directly would
    #: have hard-coded one set into every document.
    OPTIONS: ClassVar[dict[str, list[Any]]] = {
        "indent": [2, type_number],
        "directory_icon": [":lucide-folder:", type_string],
        "file_icon": [":lucide-file:", type_string],
    }

    def on_create(self, parent: etree.Element) -> etree.Element:
        wrapper = etree.SubElement(parent, "div")
        wrapper.set("class", TREE_CLASS)
        return wrapper

    def on_markdown(self) -> str:
        """Raw, because the body is a listing rather than prose.

        Markdown would turn the indentation into nested lists of its own
        and the ``-`` separators into list items, which is exactly the
        structure this replaces.
        """
        return "raw"

    def on_end(self, block: etree.Element) -> None:
        listing = block.text or ""
        block.text = None
        for child in list(block):
            block.remove(child)
        _build(
            block,
            listing,
            int(self.options["indent"]),
            str(self.options["directory_icon"]),
            str(self.options["file_icon"]),
        )


def _build(
    block: etree.Element,
    listing: str,
    unit: int,
    directory_icon: str = ":lucide-folder:",
    file_icon: str = ":lucide-file:",
) -> None:
    """Turns an indented listing into nested `<ul>`s under `block`."""
    root = etree.SubElement(block, "ul")
    # (depth, the <ul> children at that depth are appended to)
    open_lists: list[tuple[int, etree.Element]] = [(0, root)]
    last: etree.Element | None = None

    for raw in listing.splitlines():
        if not raw.strip():
            continue
        depth = _depth(raw, unit)
        entry = _ENTRY.match(raw.strip())
        if entry is None:  # pragma: no cover - the regex accepts any non-blank
            raise TreeError(f"cannot read entry: {raw.strip()!r}")

        while open_lists and open_lists[-1][0] > depth:
            open_lists.pop()
        if depth > open_lists[-1][0]:
            if last is None:
                raise TreeError(f"first entry is indented: {raw.strip()!r}")
            if depth > open_lists[-1][0] + 1:
                raise TreeError(
                    f"indented {depth - open_lists[-1][0]} levels at once: "
                    f"{raw.strip()!r}"
                )
            open_lists.append((depth, etree.SubElement(last, "ul")))

        last = _entry(
            open_lists[-1][1],
            entry.group("name"),
            entry.group("note"),
            directory_icon,
            file_icon,
        )


def _entry(
    parent: etree.Element,
    name: str,
    note: str | None,
    directory_icon: str = ":lucide-folder:",
    file_icon: str = ":lucide-file:",
) -> etree.Element:
    """One `<li>`, classed by what it is rather than by what was typed.

    The trailing `/` is the marker, not part of the name: it decides the
    class and is then dropped, so a listing reads `docs` with a folder
    icon rather than `docs/` with one as well. Writing it is how an
    author says "directory" without typing an icon.
    """
    item = etree.SubElement(parent, "li")
    directory = name.endswith("/")
    item.set("class", DIRECTORY_CLASS if directory else FILE_CLASS)
    icon = etree.SubElement(item, "span")
    icon.set("class", ICON_CLASS)
    # Left as a shortcode: the inline processor runs after this, so the
    # project's own icon extension renders it from the set that project
    # has configured.
    icon.text = directory_icon if directory else file_icon
    label = etree.SubElement(item, "span")
    label.set("class", NAME_CLASS)
    label.text = name.rstrip("/") if directory else name
    if note:
        description = etree.SubElement(item, "span")
        description.set("class", NOTE_CLASS)
        description.text = note
    return item


class TreeExtension(BlocksExtension):  # type: ignore[misc]
    """Registers ``/// tree``."""

    def extendMarkdownBlocks(self, md: object, block_mgr: object) -> None:
        block_mgr.register(TreeBlock, self.getConfigs())  # type: ignore[attr-defined]


def makeExtension(**kwargs: object) -> TreeExtension:
    return TreeExtension(**kwargs)
