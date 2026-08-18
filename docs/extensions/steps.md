# Numbered steps

`prodockit.steps` lays out a procedure as steps a reader works through in
order: a number to find your place by, room for a command and its
explanation, and a line joining one step to the next.

A procedure is not a list of facts, and an ordinary numbered list does not
say so - it gives each step one line and runs the command into the prose.

## Writing one {: #steps-writing-one }

```md
/// steps

//// step | Load the key into the agent
```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519_gitlab
```
////

//// step | Upload the public key
Paste it into your host's SSH keys page.
////

///
```

Each `//// step` takes an optional title after `|`. The body is parsed as
blocks, so a step can hold paragraphs, code fences, admonitions or content
tabs - whatever the step actually needs.

## Continuing a procedure

A long procedure is often split across sections, and the second half should
continue rather than begin again:

```md
/// steps
    start: 9

//// step | Point the clone at your own project
////

///
```

`attrs` works as it does on every other block - the Blocks API reserves it -
so a style or an id can be put on the list without this extension knowing
about either:

```md
/// steps
    start: 9
    attrs: {id: 'setup-continued'}
```

## Why the starting number is written twice

`start: 9` emits **both** `<ol start="9">` and
`counter-reset: list-item 8`, and that is the whole reason this is an
extension rather than a documented HTML snippet.

A browser reads `start`. WeasyPrint ignores it entirely and numbers from 1,
so the PDF disagreed with the website while each looked correct on its own.
`counter-reset` is what WeasyPrint reads. An author maintaining that pair by
hand will one day change one of them, and the failure is silent and
PDF-only.

## What it produces {: #steps-what-it-produces }

Structure only - `prodockit` ships the markup, your project ships the look,
the same arrangement [prodockit.tables](tables.md) and
[prodockit.tree](tree.md) have:

```html
<ol class="prodockit-steps">
  <li><p class="prodockit-step-title">Load the key into the agent</p>
      <pre>…</pre></li>
```

The title is an element rather than bold text, so it can be styled apart
from other emphasis, collected, or given an id later.

`docs/stylesheets/extra.css` in this repository carries a stylesheet to
start from. Two things in it are worth keeping, because both fail silently
and only in the PDF:

- **the joining line is positioned from the number's own size** - half a
  circle, less half a line - so changing `--step-size` to any value in any
  unit leaves the two aligned
- **`::after` carries the same `font-size` as `::before`**. The number sets
  its own size so the digits fit, so an `em` means one thing inside the
  circle and another in the line's `left` - measured at 8.8pt adrift once
  the text was scaled up

## Enabling it {: #steps-enabling-it }

```toml
[project.markdown_extensions."prodockit.steps"]
```

The [bootstrap quick start](../devcons/bootstrap.md#bootstrap-quick-start) in this
repository is written in it.
