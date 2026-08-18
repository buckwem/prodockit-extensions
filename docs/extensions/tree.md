# Directory trees

`prodockit.tree` turns an indented listing into a file tree - rails,
folder emphasis and aligned descriptions - without any of that being
typed per line.

A listing written as a bullet list is three decisions on every row: which
icon, whether to embolden the folder, and where the description starts.
Each can be made differently on the next row, and none of them is checked.

## Writing one {: #tree-writing-one }

```md
/// tree
docs/ - the documentation source tree
  index.md - the cover page
  stylesheets/ - CSS for both outputs
    extra.css - website customisations
    print.css - PDF-only styles
zensical.toml - project configuration
///
```

Three rules, and nothing else to remember:

- **Indentation is the structure.** Two spaces per level by default.
- **A trailing `/` means a directory.** Anything else is a file. Nothing
  else marks one, so nothing else can disagree with it.
- **` - ` starts a description**, and it is optional. The spaces are
  required, which is what keeps `harvard-cite-them-right.csl` in one
  piece.

## Options

| Option | Default | What it does |
|---|---|---|
| `indent` | `2` | How many spaces one level costs. Set `4` for a listing written that way. |

```md
/// tree
    indent: 4

docs/
    index.md
///
```

## Ragged indentation is refused

A listing is read for its shape, so an entry attached to the wrong parent
is a diagram that is wrong and looks right. Rather than guess, the build
stops:

```text
TreeError: indent of 3 is not a multiple of 2: 'index.md'
TreeError: indented 2 levels at once: 'index.md'
```

## What it produces {: #tree-what-it-produces }

Structure only - `prodockit` ships the markup, your project ships the
look, the same arrangement [prodockit.tables](tables.md) has:

```html
<div class="prodockit-tree">
  <ul>
    <li class="tree-directory"><code class="tree-name">docs/</code>
      <span class="tree-note">the documentation source tree</span>
      <ul>
        <li class="tree-file"><code class="tree-name">index.md</code>…
```

`docs/stylesheets/extra.css` in this repository carries a stylesheet to
start from. Two things in it are worth keeping: the rail and the stub are
positioned from one measurement, so changing the indentation cannot leave
them disagreeing about where a level begins; and the last child's rail
stops at its own stub rather than running past the last entry at nothing.

## Enabling it {: #tree-enabling-it }

```toml
[project.markdown_extensions."prodockit.tree"]
```
