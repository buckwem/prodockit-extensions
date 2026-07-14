# Refs

## Overview

`zendoc.refs` adds a `\ref{id}` cross-reference syntax - similar in spirit
to LaTeX's `\ref` - that resolves to the *current* section number of the
heading with that id:

```md
# Introduction {: #intro }

See \ref{intro} for background.
```

renders `\ref{intro}` as a link to `#intro` reading `1`. Because the number
is looked up fresh on every conversion (see [zendoc.headings](headings.md)),
it stays correct even if sections are added, removed, or reordered - you
never have to manually renumber a cross-reference.

`zendoc.refs` depends on the id/number registry that
[zendoc.headings](headings.md) builds. If you enable `zendoc.refs` on its
own, it transparently enables `zendoc.headings` for you with matching
defaults, so a single document works with no extra configuration. If you
list both explicitly, list `zendoc.headings` first - see
[Multi-page builds](#multi-page-builds) below.

## Syntax

```
\ref{<id>}
```

`<id>` is the target heading's id - either one you set explicitly via
[`attr_list`](https://python-markdown.github.io/extensions/attr_list/)
(`# Introduction {: #intro }`), or the one
[`toc`](https://python-markdown.github.io/extensions/toc/) derived
automatically from the heading text (see [zendoc.headings](headings.md#ids)
for the exact precedence).

`\ref{...}` is recognised the same way Python-Markdown's own inline syntax
is - meaning it's protected inside inline code spans and fenced code
blocks, so it's safe to show as a literal example:

````md
Type `\ref{intro}` to reference a section.

```
\ref{intro}
```
````

Neither of the two shown above is resolved; both render the literal text.

## Forward references

A reference to a heading defined *later* in the same document resolves
correctly:

```md
See \ref{background} below.

## Background {: #background }
```

## Unresolved references

`\ref{id}` renders the `unresolved` marker (`??` by default) instead of a
number when:

- `id` doesn't exist in the registry at all - e.g. a typo, or a reference
  to a heading in a page that hasn't been converted yet in a multi-page
  build (the same way an undefined LaTeX `\ref` shows `??` until a later
  compilation pass).
- `id` exists but belongs to a heading marked `unnumbered` (see
  [zendoc.headings](headings.md#unnumbered-headings)) - it's still a valid
  link target in this case, just without a number to show.

```md
# Cover Page {: .unnumbered }

See \ref{cover-page}.
```

renders `\ref{cover-page}` as `??`, linked to `#cover-page`.

## Options

| Option | Type | Default | Description |
|---|---|---|---|
| `unresolved` | `str` | `"??"` | Text rendered when `id` doesn't resolve to a numbered heading. |
| `registry` | `IdRegistry \| None` | discovered from a sibling `zendoc.headings`, or a new one | Share one registry across multiple documents - see below. Passed as a constructor keyword, not a string-based config value. |

## Multi-page builds

To resolve cross-page references, give `zendoc.headings` and `zendoc.refs`
the *same* `IdRegistry` on every page, converting pages in the order
cross-references should become resolvable in (a reference to a page not
yet converted resolves to `unresolved`, as above):

```python
import markdown
from zendoc.headings import HeadingsExtension
from zendoc.refs import RefsExtension
from zendoc.util import IdRegistry

registry = IdRegistry()

for path, text in pages:
    html = markdown.markdown(
        text,
        extensions=[
            HeadingsExtension(registry=registry, source=path),
            RefsExtension(registry=registry),
        ],
    )
```

If you enable both extensions by name instead (e.g. from a
`mkdocs.yml`/`zensical.toml`-style config, where you can't pass a shared
`IdRegistry` object directly), list `zendoc.headings` before `zendoc.refs`:
`zendoc.refs` looks for an already-registered `zendoc.headings` instance on
the current `Markdown` object and reuses its registry automatically, so a
per-page site-generator integration (a plugin owning one shared registry
across the whole build) is the way to get cross-page resolution without
constructing extension instances by hand.
