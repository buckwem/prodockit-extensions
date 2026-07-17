# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""prodockit.tables: percentage or fixed column widths on a Markdown table,
via a ``width`` attribute already attachable to a header cell with
``attr_list`` - e.g. ``| Name {: width="30%" } | Description |``.

Builds on Python-Markdown's own ``tables`` extension (auto-enabled if not
already present, the same way ``prodockit.refs`` auto-enables
``prodockit.headings``) - this extension only ever adds a ``<colgroup>`` to
a table that already has at least one width-attributed header cell; a table
with none is left completely untouched.

Column widths beyond what's explicitly given are deliberately *not*
computed here: with ``table-layout: fixed`` (see the ``prodockit-table-sized``
CSS hook below), a browser/WeasyPrint's own table layout algorithm already
gives an explicitly-widthed column its width and splits whatever's left
evenly across the rest - the "standard algorithm" for sharing remaining
space the CSS table layout algorithm has always implemented, not something
worth re-deriving in Python.
"""

from __future__ import annotations

import xml.etree.ElementTree as etree

from markdown import Markdown
from markdown.extensions import Extension
from markdown.extensions.tables import TableExtension
from markdown.treeprocessors import Treeprocessor

SIZED_TABLE_CLASS = "prodockit-table-sized"


class TableWidthTreeprocessor(Treeprocessor):
    """Turns a header cell's ``width`` attribute (set via ``attr_list``, e.g.
    ``{: width="30%" }``) into a ``<colgroup>`` entry for that column,
    leaving the actual column-width math to CSS's own ``table-layout: fixed``
    algorithm rather than computing it here.

    Runs at a lower priority than 'attr_list' (registered at 8) so it always
    sees whatever ``width`` attr_list already assigned to a header cell,
    rather than racing it.
    """

    def run(self, root: etree.Element) -> None:
        for table in root.iter("table"):
            header_row = table.find("./thead/tr")
            if header_row is None:
                continue
            headers = header_row.findall("th")
            widths = [th.get("width") for th in headers]
            if not any(widths):
                continue
            for th in headers:
                if "width" in th.attrib:
                    del th.attrib["width"]
            colgroup = etree.Element("colgroup")
            for width in widths:
                col = etree.SubElement(colgroup, "col")
                if width:
                    col.set("style", f"width: {width};")
            table.insert(0, colgroup)
            existing_classes = (table.get("class") or "").split()
            if SIZED_TABLE_CLASS not in existing_classes:
                table.set("class", " ".join([*existing_classes, SIZED_TABLE_CLASS]))


class TablesExtension(Extension):
    """Python-Markdown extension turning a header cell's ``width`` attr_list
    attribute into column widths, via a generated ``<colgroup>``."""

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)
        if "table" not in md.parser.blockprocessors:
            TableExtension().extendMarkdown(md)
        md.treeprocessors.register(
            TableWidthTreeprocessor(md),
            "prodockit-tables",
            3,
        )


def makeExtension(**kwargs: object) -> TablesExtension:
    return TablesExtension(**kwargs)
