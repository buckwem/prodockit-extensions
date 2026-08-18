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

#: Written ``{: .header }`` on a cell of a body row, to say that the row
#: belongs in the header. A Markdown table has exactly one header row and
#: no syntax for a second, so a table whose heading needs two lines has
#: to fake one - and a faked header does not repeat when the table breaks
#: across pages, because only what is inside ``<thead>`` repeats. Moving
#: the row into ``<thead>`` is the whole fix: WeasyPrint already repeats
#: a multi-row header, spans and all (prodockit-extensions#474).
HEADER_MARKER = "header"

#: Set on a header cell whose text is turned on its side, and on the span
#: that turns it. Rotation is the only way a wide table's headings stop
#: deciding its width - but `transform` does not affect layout, so the
#: column has to be given a width as well, which is why `rotate` without
#: `width` is refused rather than rendered.
ROTATE_CLASS = "prodockit-rotate"

#: The angles worth having. Anything else gives a heading nobody can read
#: and a row height nobody can predict.
ROTATE_ANGLES = (90, 270)


class TableError(ValueError):
    """A table that cannot be built as asked.

    Raised rather than rendered approximately: a heading rotated inside a
    full-width column looks like the feature worked, and a silent wrong
    answer is the failure this project keeps meeting.
    """


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
            # Before anything reads the header: a promoted row is part of
            # it, and may carry the width or the compact marker itself.
            _promote_header_rows(table)
            _apply_spans(table)
            headers = [c for row in table.findall("./thead/tr") for c in row]
            _apply_compact(table, headers)
            _apply_rotation(headers)
            # Widths come from the first header row only - it is the one
            # with a cell per column, which is what a <colgroup> needs.
            widths = [th.get("width") for th in header_row.findall("th")]
            if not any(widths):
                continue
            for th in header_row.findall("th"):
                if "width" in th.attrib:
                    del th.attrib["width"]
            colgroup = etree.Element("colgroup")
            for width in widths:
                col = etree.SubElement(colgroup, "col")
                if width:
                    col.set("style", f"width: {width};")
            table.insert(0, colgroup)
            _add_class(table, SIZED_TABLE_CLASS)


def _promote_header_rows(table: etree.Element) -> None:
    """Moves rows marked ``{: .header }`` out of the body and into the head.

    Only the leading run of them: a header is the top of a table, and a
    marked row further down is a mistake worth leaving visible rather
    than quietly re-ordering the table around.

    The cells become ``<th>``. That is what makes the row repeat - a
    browser and WeasyPrint alike repeat everything in ``<thead>`` when a
    table breaks across pages, which is the whole point of the marker
    (prodockit-extensions#474).
    """
    head, body = table.find("thead"), table.find("tbody")
    if head is None or body is None:
        return
    for row in list(body):
        cells = list(row)
        marked = [c for c in cells if HEADER_MARKER in (c.get("class") or "").split()]
        if not marked:
            break  # the leading run has ended
        for cell in marked:
            rest = [c for c in (cell.get("class") or "").split() if c != HEADER_MARKER]
            if rest:
                cell.set("class", " ".join(rest))
            else:
                del cell.attrib["class"]
        for cell in cells:
            cell.tag = "th"
        body.remove(row)
        head.append(row)


def _span(cell: etree.Element, name: str) -> int:
    """A cell's colspan/rowspan as a number, defaulting to one."""
    try:
        value = int(cell.get(name, "1"))
    except ValueError as error:
        raise TableError(
            f"{name} must be a whole number, not {cell.get(name)!r}"
        ) from error
    if value < 1:
        raise TableError(f"{name} must be at least 1, not {value}")
    return value


def _is_placeholder(cell: etree.Element) -> bool:
    """Whether a cell is the empty filler a merged cell leaves behind.

    Only an empty one. A placeholder with text in it is somebody's
    content, and dropping it silently would be worse than the ragged row
    it causes - so it is left alone, where it shows up immediately.
    """
    return not (cell.text or "").strip() and len(cell) == 0


def _apply_spans(table: etree.Element) -> None:
    """Removes the placeholder cells a merged cell leaves behind.

    `attr_list` already turns ``{: colspan=2 }`` into a real attribute -
    nothing here translates it. What it cannot do is drop the cells the
    span now covers, and a pipe table has to keep its columns even to
    parse at all, so the author writes them empty:

        | Item {: rowspan=2 } | Measured {: colspan=2 } | | Note |

    Left in place they push the row wider than the header, and the table
    comes out ragged (prodockit-extensions#474).
    """
    rows = [row for section in table for row in section if row.tag == "tr"]

    # A colspan swallows the cells written after it, on its own row.
    for row in rows:
        for cell in list(row):
            extra = _span(cell, "colspan") - 1
            while extra > 0:
                cells = list(row)
                index = cells.index(cell) + 1
                if index >= len(cells) or not _is_placeholder(cells[index]):
                    break
                row.remove(cells[index])
                extra -= 1

    # A rowspan swallows one cell in each row below, at its own column.
    # Column positions have to account for spans already reaching into
    # the row from above, which is what `covered` tracks.
    covered: dict[int, set[int]] = {}
    for r, row in enumerate(rows):
        column = 0
        for cell in list(row):
            while column in covered.get(r, set()):
                column += 1
            across, down = _span(cell, "colspan"), _span(cell, "rowspan")
            for dr in range(1, down):
                covered.setdefault(r + dr, set()).update(
                    range(column, column + across)
                )
                below = rows[r + dr] if r + dr < len(rows) else None
                if below is None:
                    continue
                # The cell sitting where this span lands, if it is filler.
                position = 0
                for other in list(below):
                    while position in covered.get(r + dr, set()) and position < column:
                        position += 1
                    if position == column and _is_placeholder(other):
                        below.remove(other)
                        break
                    position += _span(other, "colspan")
            column += across


def _apply_rotation(cells: list[etree.Element]) -> None:
    """Turns a header cell's text on its side.

    `transform` is the only thing that rotates text in both outputs -
    WeasyPrint ignores `writing-mode` entirely, silently, and the column
    still narrows if a width is set, so the heading looks merely wrapped
    rather than broken.

    But `transform` never affects layout: a rotated box occupies its
    unrotated space. So rotation alone cannot narrow a column, and
    `rotate` without `width` is refused - that combination renders a
    rotated heading in a full-width column, which looks like it worked
    (prodockit-extensions#474).
    """
    for cell in cells:
        raw = cell.get("rotate")
        if raw is None:
            continue
        try:
            angle = int(raw)
        except ValueError as error:
            raise TableError(f"rotate must be a whole number, not {raw!r}") from error
        if angle not in ROTATE_ANGLES:
            raise TableError(
                f"rotate must be one of {', '.join(map(str, ROTATE_ANGLES))}, not {angle} - "
                "270 reads bottom-to-top and 90 top-to-bottom, and any other angle "
                "gives a heading nobody can read and a row height nobody can predict"
            )
        if not cell.get("width"):
            raise TableError(
                f'rotate={angle} needs a width on the same cell, e.g. '
                f'{{: rotate={angle} width="1.6em" }} - rotating the text does not '
                "narrow the column on its own, because a rotated box still takes up "
                "the space it would have taken unrotated"
            )
        height = cell.get("height")
        del cell.attrib["rotate"]
        if height is not None:
            del cell.attrib["height"]

        # The text moves into a span: the cell keeps its place in the
        # table's grid, and only its content turns.
        span = etree.Element("span")
        span.set("class", ROTATE_CLASS)
        style = f"transform: rotate({angle}deg);"
        if height:
            # Pre-rotation width is post-rotation height, so this is what
            # a long heading wraps against.
            style += f" width: {height};"
        span.set("style", style)
        span.text = cell.text
        cell.text = None
        for child in list(cell):
            cell.remove(child)
            span.append(child)
        cell.append(span)

        _add_class(cell, ROTATE_CLASS)
        cell_style = cell.get("style", "")
        if height:
            cell_style += f" height: {height};"
        cell.set("style", cell_style.strip())


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
