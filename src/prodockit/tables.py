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

#: Set by ``{: .compact }`` on any header cell. A dense table - many
#: columns, most of them short - is held wide by the theme's own
#: ``min-width: 5rem`` on every header cell and by a generous 1.25em of
#: horizontal padding, and overflows whatever its content is. Measured on
#: a real 14-column table against 1009px of A4 landscape: 1586.7px as
#: shipped, 1190.7px with the minimum dropped, 993.1px with the padding
#: tightened as well - so neither is enough on its own, and this turns off
#: both together (prodockit-extensions#489).
COMPACT_TABLE_CLASS = "prodockit-table-compact"

#: The class an author writes, before it is moved to the table.
COMPACT_MARKER = "compact"


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
            _apply_compact(table, headers)
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
            _add_class(table, SIZED_TABLE_CLASS)


def _add_class(element: etree.Element, name: str) -> None:
    """Adds a class without disturbing any already there."""
    classes = (element.get("class") or "").split()
    if name not in classes:
        element.set("class", " ".join([*classes, name]))


def _apply_compact(table: etree.Element, headers: list[etree.Element]) -> None:
    """Moves ``{: .compact }`` from a header cell onto the table.

    Written on a cell because that is where `attr_list` can reach in a
    Markdown table - there is no syntax for attaching a class to the
    table itself - and read from any cell rather than only the first, so
    an author who marks the column they were looking at gets what they
    meant.

    The marker is removed from the cell: it describes the table, and
    leaving it behind would style one cell as well.
    """
    marked = [th for th in headers if COMPACT_MARKER in (th.get("class") or "").split()]
    if not marked:
        return
    for th in marked:
        rest = [c for c in (th.get("class") or "").split() if c != COMPACT_MARKER]
        if rest:
            th.set("class", " ".join(rest))
        else:
            del th.attrib["class"]
    _add_class(table, COMPACT_TABLE_CLASS)


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
