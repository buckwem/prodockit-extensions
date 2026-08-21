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
| Change one cell's shading | `shade="off"` or `shade="8%"` |
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

There are no additional `prodockit.tables` settings in `zensical.toml`.
Configure each table in its Markdown by adding the attributes shown in the
examples below.

### Use a compact layout {: #tables-compact }

A table with many short columns can become wider than the page. Add `.compact`
to reduce the minimum column width and cell spacing.

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

Use it only when the normal table is too wide. Put the marker on any header
cell. It affects the whole table and can be combined with column widths.

### Use more than one header row {: #tables-multi-row-header }

A Markdown table normally has one header row. Mark the first additional row
with `.header` when a grouped heading needs a second row.

Mark it `{: .header }`:

=== "Markdown"

    ```md
    | Target {: rowspan=2 } | Measured {: colspan=2 } | | Note {: rowspan=2 } |
    |---|---|---|---|
    | | Before {: .header } | After | |
    | Widget | 1 | 2 | ok |
    ```

=== "Result"

    | Target {: rowspan=2 } | Measured {: colspan=2 } | | Note {: rowspan=2 } |
    |---|---|---|---|
    | | Before {: .header } | After | |
    | Widget | 1 | 2 | ok |

Both header rows then repeat when a long table continues onto another PDF
page.

The marker has to go on a cell that **has text** - `attr_list` has nothing
to attach to in an empty one. Any cell in the row will do. Only the leading
run of marked rows is promoted: a header is the top of a table, and a
marked row further down stays where it is rather than the table being
quietly re-ordered around it.

### Merge cells {: #tables-merged-cells }

Use `colspan` to join cells across columns and `rowspan` to join cells down
rows. Keep an empty placeholder for every cell covered by the span, as shown
below.

=== "Markdown"

    ```md
    | Target {: rowspan=2 } | Measured {: colspan=2 } | | Note {: rowspan=2 } |
    |---|---|---|---|
    | | Before {: .header } | After | |
    | Widget | 1 | 2 | ok |
    ```

=== "Result"

    | Target {: rowspan=2 } | Measured {: colspan=2 } | | Note {: rowspan=2 } |
    |---|---|---|---|
    | | Before {: .header } | After | |
    | Widget | 1 | 2 | ok |

The empty cell after `Measured` and the empty cells beneath the two
`rowspan=2` headings are structural placeholders. The extension removes those
placeholders after applying the spans.

### Adjust cell shading {: #tables-cell-shading }

Header cells have a subtle 5% shade by default. Remove it from one cell with
`shade="off"`, or give any header or body cell an explicit percentage:

=== "Markdown"

    ```md
    | Unshaded {: shade="off" } | Grouped heading {: colspan=2 shade="8%" } | |
    |---|---|---|
    | Normal | Highlighted {: shade="5%" } | Normal |
    ```

=== "Result"

    | Unshaded {: shade="off" } | Grouped heading {: colspan=2 shade="8%" } | |
    |---|---|---|
    | Normal | Highlighted {: shade="5%" } | Normal |

Shading applies to the whole surviving merged cell, so `shade` combines with
`colspan` and `rowspan` on the same attribute list. A percentage must be from
`0%` to `100%`; use `off` when the intent is to suppress the default header
shade explicitly.

### Rotate headings {: #tables-rotated-headings }

A wide table is often wide because of its headings, not its data. Turn them
on their side:

=== "Markdown"

    ```md
    | Control | Availability requirement {: rotate=270 width="1.8em" height="105pt" } |
    |---|---|
    | Backups | H |
    ```

=== "Result"

    | Control | Availability requirement {: rotate=270 width="1.8em" height="105pt" } |
    |---|---|
    | Backups | H |

`270` reads bottom-to-top, `90` top-to-bottom, and nothing else is allowed:
another angle gives a heading nobody can read and a row height nobody can
predict.

Set `width` with `rotate`; a missing width is rejected because rotating text
alone does not make the column narrower. Set `height` when a long heading
needs more room.

## Reference {: #tables-reference }

### Syntax {: #tables-syntax }

Builds on Python-Markdown's own `tables` extension (auto-enabled if not
already present, the same way [prodockit.refs](refs.md) auto-enables
[prodockit.headings](headings.md)).

Attach table attributes to header cells. A column's width is a property of the
whole column, so declare it once on the heading rather than on a body cell.

| Attribute | Where to put it | Effect |
| --- | --- | --- |
| \index{prodockit.tables!`width`}=`"<css-length>"` | Header cell | Set that column's width |
| `.compact` | Any header cell | Apply the compact layout to the whole table |
| `.header` | A non-empty cell in a leading body row | Move that row into `<thead>` |
| `colspan=<n>` | Cell being widened | Merge it with the following placeholder cells |
| `rowspan=<n>` | Cell being deepened | Merge it with placeholder cells below |
| `shade="off"` | Any cell | Remove shading from that cell |
| `shade="<percentage>"` | Any cell | Shade that cell by an explicit percentage |
| \index{prodockit.tables!`rotate`}=90 or `rotate=270` | Header cell that also has `width` | Rotate the heading text |
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

The extension adds stable classes that a website CSS style sheet can target:

| Element | Condition | Hook |
|---|---|---|
| `<table>` | at least one header cell has `width` | `class="prodockit-table-sized"` |
| `<table>` | any header cell has `.compact` | `class="prodockit-table-compact"` |
| `<th>` | heading has `rotate=90` or `rotate=270` | `class="prodockit-rotate"` plus an inline transform |
| `<th>` or `<td>` | cell has `shade="off"` | `class="prodockit-table-cell-unshaded"` |
| `<th>` or `<td>` | cell has `shade="<percentage>"` | `class="prodockit-table-cell-shaded"` plus `--prodockit-table-cell-shade` |
| `<col>` | that column has `width` | `style="width: <value>;"` |

Add at least this rule for sized and compact website tables:

```css
.md-typeset table:not([class]),
.md-typeset table.prodockit-table-sized,
.md-typeset table.prodockit-table-compact {
  border-collapse: collapse;
}

.md-typeset table.prodockit-table-sized,
.md-typeset table.prodockit-table-compact {
  table-layout: fixed;
  width: 100%;
  background-color: var(--md-default-bg-color);
  border: 0.05rem solid var(--md-typeset-table-color);
  border-radius: 0.1rem;
  font-size: 0.64rem;
}

.md-typeset table:not([class]) th,
.md-typeset table.prodockit-table-sized th,
.md-typeset table.prodockit-table-compact th {
  background-color: rgba(0, 0, 0, 0.05);
}

.md-typeset table th.prodockit-table-cell-unshaded,
.md-typeset table td.prodockit-table-cell-unshaded {
  background-color: transparent;
}

.md-typeset table th.prodockit-table-cell-shaded,
.md-typeset table td.prodockit-table-cell-shaded {
  background-color: rgba(0, 0, 0, var(--prodockit-table-cell-shade));
}

.md-typeset table:not([class]) th,
.md-typeset table:not([class]) td,
.md-typeset table.prodockit-table-sized th,
.md-typeset table.prodockit-table-sized td,
.md-typeset table.prodockit-table-compact th,
.md-typeset table.prodockit-table-compact td {
  border: 0.05rem solid var(--md-typeset-table-color);
}
```

The complete light- and dark-mode rules used by this site are in
`docs/stylesheets/extra.css`. PDF builds already include equivalent layout
rules with the light website scheme's line colour and the same width.
Contributors changing the generated table structure should read
[Extension integration](../devcons/extension-internals.md#table-layout-contracts).
