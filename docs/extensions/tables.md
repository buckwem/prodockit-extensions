---
icon: lucide/table
---

# Tables

\index{`prodockit.tables`} adds layout controls to an ordinary Markdown table.
You can change column widths, reduce spacing, use more than one header row,
merge cells, and rotate long headings.

## Enable the extension {: #tables-enable }

Enable it in `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.tables"]
```

Choose the feature that solves the table's problem:

| Need | Attribute |
| --- | --- |
| Set a column width | `width="30%"` or a fixed width such as `8rem` |
| Fit many short columns | `.compact` |
| Repeat more than one header row | `.header` |
| Merge cells | `colspan=2` or `rowspan=2` |
| Turn a long heading vertically | `rotate=90` or `rotate=270`, with `width` |

The next examples show each feature in isolation before combining them.

## Set column widths {: #tables-quick-start }

### Percentages that add up to 100%

Give every column an explicit percentage and they're used exactly as
written:

=== "Markdown"

    ```md
    | Name {: width="25%" } | Description {: width="50%" } | Due {: width="25%" } |
    |---|---|---|
    | Headings | Heading ids and section numbers | Q1 |
    | Refs | Cross-references, resolved by number | Q2 |
    ```

=== "Result"

    | Name {: width="25%" } | Description {: width="50%" } | Due {: width="25%" } |
    |---|---|---|
    | Headings | Heading ids and section numbers | Q1 |
    | Refs | Cross-references, resolved by number | Q2 |

### Percentages that don't add up to 100%

Leave a column without a width and it uses the remaining space. If several
columns have no width, they share that space evenly:

=== "Markdown"

    ```md
    | Name {: width="20%" } | Description | Due {: width="15%" } |
    |---|---|---|
    | Headings | Heading ids and section numbers | Q1 |
    | Refs | Cross-references, resolved by number | Q2 |
    ```

=== "Result"

    | Name {: width="20%" } | Description | Due {: width="15%" } |
    |---|---|---|
    | Headings | Heading ids and section numbers | Q1 |
    | Refs | Cross-references, resolved by number | Q2 |

`Name` and `Due` get the widths given; `Description`, left unannotated,
takes the remaining 65%. A column left unannotated in a table with no
`width` anywhere at all is completely untouched, though - only a table
with at least one `width` gets a `<colgroup>`.

### Fixed widths for every column

A fixed width is useful when a column should stay the same size even when the
page becomes wider or narrower. You can give every column a fixed width:

=== "Markdown"

    ```md
    | Icon {: width="60px" } | Description {: width="200px" } | Format {: width="100px" } |
    |---|---|---|
    | :material-file-pdf-box: | A downloadable PDF | PDF |
    | :material-file-document: | A Markdown source file | Markdown |
    ```

=== "Result"

    | Icon {: width="60px" } | Description {: width="200px" } | Format {: width="100px" } |
    |---|---|---|
    | :material-file-pdf-box: | A downloadable PDF | PDF |
    | :material-file-document: | A Markdown source file | Markdown |

### Mixing percentages and fixed widths

Percentage and fixed-width columns can appear in the same table. A column can
still be left without a width and use the remaining space:

=== "Markdown"

    ```md
    | # {: width="40px" } | Name {: width="50%" } | Description |
    |---|---|---|
    | 1 | prodockit.headings | Heading ids and section numbers |
    | 2 | prodockit.tables | Column widths on a table |
    ```

=== "Result"

    | # {: width="40px" } | Name {: width="50%" } | Description |
    |---|---|---|
    | 1 | prodockit.headings | Heading ids and section numbers |
    | 2 | prodockit.tables | Column widths on a table |

### Left-aligning a header

By default a header cell is centred and a body cell is left-aligned - the
browser's own default styling for `<th>`/`<td>`, unrelated to
`prodockit.tables`. To left-align a header too, use Python-Markdown's own
column-alignment syntax - a `:` on the left side of that column's own
dashes in the separator row - which applies to the header *and* every
body cell in that column alike, and combines with `width` on the same
header cell with no conflict:

=== "Markdown"

    ```md
    | Name {: width="30%" } | Description |
    |:---|---|
    | Headings | Heading ids and section numbers |
    | Refs | Cross-references, resolved by number |
    ```

=== "Result"

    | Name {: width="30%" } | Description |
    |:---|---|
    | Headings | Heading ids and section numbers |
    | Refs | Cross-references, resolved by number |

`:---:`/`---:` center- or right-align a column the same way - see
[Python-Markdown's own `tables` docs](https://python-markdown.github.io/extensions/tables/)
for the full syntax. This isn't a `prodockit.tables` feature; it's
documented here because it's the natural companion to `width` when
sizing a column, not something `prodockit.tables` needs to reimplement.

## Configure table layouts

### Use a compact layout {: #tables-compact }

A table with many short columns is held wide by the theme itself: every
header cell carries a `min-width` of `5rem`, and every cell 1.25em of
padding either side. A column holding `H` is then as wide as one holding a
sentence, and the table overflows whatever it contains.

Mark it `{: .compact }` on any header cell:

=== "Markdown"

    ```md
    | Threat {: .compact } | Likelihood | Impact | Risk |
    |---|---|---|---|
    | Credential theft | H | H | H |
    ```

=== "Result"

    | Threat {: .compact } | Likelihood | Impact | Risk |
    |---|---|---|---|
    | Credential theft | H | H | H |

The minimum goes and the padding tightens, in the PDF as well as on the
website. Measured on a 14-column table against 1009px of A4 landscape:

| | table width |
|---|---|
| as written | 1586.7px |
| minimum dropped | 1190.7px |
| and the padding tightened | 993.1px |

Both are needed - neither is enough alone, which is why it is one marker
rather than two.

It is opt-in on purpose. A table that reads well at its default should
keep it, and a table quietly changing shape because a column was added is
the kind of surprise worth avoiding.

The marker is written on a header cell because that is the only place
`attr_list` can reach in a Markdown table; it is moved onto the table and
removed from the cell, so it styles the table rather than that one column.
Any header cell will do. It combines with `width`, which answers a
different question - how wide one column is, rather than how tightly every
cell is set.

### Use more than one header row {: #tables-multi-row-header }

A Markdown table has exactly one header row and no syntax for a second, so
a heading that needs two lines has to be written as a body row. That row
then stops repeating when the table breaks across pages, because only what
is inside `<thead>` repeats - which is precisely when a second heading line
is needed.

Mark it `{: .header }`:

```md
| Target {: rowspan=2 } | Measured {: colspan=2 } | | Note {: rowspan=2 } |
|---|---|---|---|
| | Before {: .header } | After | |
| Widget | 1 | 2 | ok |
```

The row moves into `<thead>` and its cells become `th`, so both lines
repeat on every page the table reaches.

The marker has to go on a cell that **has text** - `attr_list` has nothing
to attach to in an empty one. Any cell in the row will do. Only the leading
run of marked rows is promoted: a header is the top of a table, and a
marked row further down stays where it is rather than the table being
quietly re-ordered around it.

### Merge cells {: #tables-merged-cells }

`colspan` and `rowspan` are `attr_list`'s own attributes and need nothing
new. What `prodockit.tables` adds is removing the empty cells they leave
behind - a pipe table has to keep its columns even to parse, so a merged
cell is written with blank ones after it, and left in place they push the
row wider than the header.

A placeholder with text in it is kept. It is somebody's content, and
dropping it silently would be worse than the ragged row it causes.

```md
| Target {: rowspan=2 } | Measured {: colspan=2 } | | Note {: rowspan=2 } |
|---|---|---|---|
| | Before {: .header } | After | |
| Widget | 1 | 2 | ok |
```

The empty cell after `Measured` and the empty cells beneath the two
`rowspan=2` headings are structural placeholders. The extension removes those
placeholders after applying the spans.

### Rotate headings {: #tables-rotated-headings }

A wide table is often wide because of its headings, not its data. Turn them
on their side:

```md
| Control | Availability requirement {: rotate=270 width="1.8em" height="105pt" } |
|---|---|
| Backups | H |
```

`270` reads bottom-to-top, `90` top-to-bottom, and nothing else is allowed:
another angle gives a heading nobody can read and a row height nobody can
predict.

All three parts are needed, and `rotate` without `width` is refused rather
than rendered. The reason is worth knowing: `transform` does not affect
layout, so a rotated box still occupies the space it would have occupied
unrotated. **The width is what buys the space; the rotation is what keeps
the heading readable once the column is narrow.** A rotated heading in a
full-width column looks like the feature worked.

`height` sizes the header row, since the rotated text reserves none of its
own, and is what a long heading wraps against.

Rotation uses `transform` in both outputs rather than `writing-mode`, which
WeasyPrint ignores silently - the text stays horizontal in the PDF while
the column still narrows, so it looks merely wrapped rather than broken.

## Reference {: #tables-reference }

### Syntax {: #tables-syntax }

Builds on Python-Markdown's own `tables` extension (auto-enabled if not
already present, the same way [prodockit.refs](refs.md) auto-enables
[prodockit.headings](headings.md)).

Attach table attributes to header cells. A column's width is a property of the
whole column, so declare it once on the heading rather than on a body cell.

| Attribute | Where to put it | Effect |
| --- | --- | --- |
| `width="<css-length>"` | Header cell | Set that column's width |
| `.compact` | Any header cell | Apply the compact layout to the whole table |
| `.header` | A non-empty cell in a leading body row | Move that row into `<thead>` |
| `colspan=<n>` | Cell being widened | Merge it with the following placeholder cells |
| `rowspan=<n>` | Cell being deepened | Merge it with placeholder cells below |
| `rotate=90` or `rotate=270` | Header cell that also has `width` | Rotate the heading text |
| `height="<css-length>"` | Rotated header cell | Reserve height for the rotated text |

The minimal width form is:

```
| Column {: width="<css-length>" } | ... |
|---|---|
```

`<css-length>` is any valid CSS width value - a percentage (`"30%"`) or a
fixed length (`"120px"`, `"4cm"`, `"3em"`, ...) - passed through to the
generated `<colgroup>` as-is, with no validation of its own; an invalid
value behaves exactly as it would in any other hand-written CSS, since
`prodockit.tables` doesn't parse or interpret it beyond that.

## Customise with a CSS style sheet {: #tables-css-hooks }

A table with at least one `width`-attributed header cell gets a
`<colgroup>` (one `<col>` per column, `style="width: ..."` set only on the
columns that had one) inserted as its first child, and
`class="prodockit-table-sized"` on the `<table>` itself:

| Element | Condition | Hook |
|---|---|---|
| `<table>` | at least one header cell has `width` | `class="prodockit-table-sized"` |
| `<table>` | any header cell has `.compact` | `class="prodockit-table-compact"` |
| `<th>` | heading has `rotate=90` or `rotate=270` | `class="prodockit-rotate"` plus an inline transform |
| `<col>` | that column's header cell had `width` | `style="width: <value>;"` |
| `<col>` | that column's header cell had no `width` | none - left for `table-layout: fixed` to size |

The `width` attribute itself is always stripped from the `<th>` once
read - it isn't meant to also linger on the header cell.

`prodockit-table-sized` only *marks* a table as sized - it isn't styled by
`prodockit.tables` itself. A stylesheet needs to apply `table-layout: fixed`
itself for the `<colgroup>` widths (and the "share what's left" behaviour)
to take effect at all. Under Zensical's Material-based theme specifically,
its own default table styling (border, padding, alternating rows) is
scoped `.md-typeset table:not([class])` - confirmed directly in Zensical's
bundled CSS - so a table carrying `prodockit-table-sized` (or any other
class) gets **none** of it, not just no width control:

```css
.md-typeset table.prodockit-table-sized,
.md-typeset table.prodockit-table-compact {
  table-layout: fixed;
  width: 100%;
  background-color: var(--md-default-bg-color);
  border: 0.05rem solid var(--md-typeset-table-color);
  border-radius: 0.1rem;
  font-size: 0.64rem;
}
```

The rules rebuild the theme's *own* table appearance rather than inventing
one: a table that asks for a column width has to keep looking like the
table beside it that didn't. Using the theme's `--md-typeset-table-color`
rather than a literal matters for the same reason - the variable follows
the colour scheme, so the table is right in dark mode too. The full set is
in this project's own `docs/stylesheets/extra.css`.

[prodockit.pdf](../pdf.md) already includes the equivalent rule in its own
generated CSS (as well as its own table border/padding, unaffected by this
theme-specific quirk), so a sized table works in the PDF with no extra
configuration; a project's own website theme needs the CSS above added
itself (see this project's own `docs/stylesheets/extra.css` for a working
example) - `prodockit.tables` doesn't ship a bundled website stylesheet the
way `prodockit.pdf` ships one for the PDF path.

A table with no `width`-attributed header cells at all is left completely
untouched - no `<colgroup>`, no `prodockit-table-sized` class - so enabling
`prodockit.tables` has no effect on any table that doesn't use it.
