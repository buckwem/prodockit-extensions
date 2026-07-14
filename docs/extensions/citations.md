# Citations

## Overview

`zendoc.citations` lets you define a source once and cite it by key from
anywhere in a build, instead of hand-typing a bracketed link at every
citation site. Define a source's paragraph with an id and a short display
text via
[`attr_list`](https://python-markdown.github.io/extensions/attr_list/):

```md
Skoulikari, A. (2023) *Learning Git: A Hands-On and Visual Guide to the
Basics of Git*. Sebastopol, CA: O'Reilly Media.
{: #skou2023 .reference data-cite-text="Skoulikari, 2023" }
```

then cite it from anywhere with `\cite{skou2023}`:

```md
Git is a tool used to manage version control.\cite{skou2023}
```

renders as `Git is a tool used to manage version control.[Skoulikari,
2023]`, with `[Skoulikari, 2023]` linked to `#skou2023`. Unlike a hand-typed
`[[Skoulikari, 2023](references.md#skou2023)]`, you never have to work out
the relative path to the references page, retype the display text, or fix
every citation site if the display text needs to change - it's defined once.

Defining and citing are bundled into one extension, unlike
[zendoc.headings](headings.md)/[zendoc.refs](refs.md): a definition is
useless without somewhere to cite it, so there's no independently useful
"just defining" half to split out.

## Syntax

### Defining a source

Any block element - typically a paragraph - with both an `id` and a
`data-cite-text` attribute becomes a citable source:

```md
Chacon, S. and Straub, B. (2014) *Pro Git*. 2nd edn. New York: Apress.
{: #chacon2014 .reference data-cite-text="Chacon and Straub, 2014" }
```

`data-cite-text` is the short text rendered at each citation site - it's
stripped from the rendered output (it's internal bookkeeping, not meant to
be visible), while `id` stays, since citations link straight to it.

### Citing a source

```
\cite{<id>}
\cite{<id1>,<id2>,...}
```

A single key renders one bracketed, linked citation:
`\cite{skou2023}` → `[Skoulikari, 2023]`.

Multiple comma-separated keys join with `; ` inside one bracket:
`\cite{skou2023,chacon2014}` → `[Skoulikari, 2023; Chacon and Straub,
2014]`.

Like [zendoc.refs](refs.md), `\cite{...}` is recognised the same way
Python-Markdown's own inline syntax is, so it's protected inside inline
code spans and fenced code blocks:

````md
Type `\cite{skou2023}` to cite a source.

```
\cite{skou2023}
```
````

Neither of the two shown above is resolved; both render the literal text.

### Forward references

A citation to a source defined *later* in the same document resolves
correctly, the same way [zendoc.refs](refs.md#forward-references) does:

```md
See \cite{skou2023} above.

Skoulikari, A. (2023) *Learning Git*.
{: #skou2023 data-cite-text="Skoulikari, 2023" }
```

## Unresolved citations

A key that doesn't resolve to a definition renders the `unresolved` marker
(`?` by default) in place of that one entry - the rest of a multi-key
citation still resolves normally:

```md
\cite{skou2023,does-not-exist}
```

renders `[Skoulikari, 2023; ?]` - the unresolved entry has no link, unlike
a resolved one.

## Options

| Option | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | `""` | Identifier for the current document (e.g. its file path). Used to scope this document's own citation definitions in the registry. |
| `unresolved` | `str` | `"?"` | Text rendered for a `\cite{id}` key that doesn't resolve to a definition. |
| `registry` | `CitationRegistry \| None` | discovered automatically, or a new one | Share one registry across multiple documents - see below. Passed as a constructor keyword, not a string-based config value. |

## Multi-page builds

### Under Zensical: automatic

Under [Zensical](https://zensical.org/), citing a source defined on a
*different* page (the common case - a references page separate from the
pages that cite it) works with no extra configuration, the same way
[zendoc.refs](refs.md#under-zensical-automatic) shares its registry across
pages: `zendoc.citations` detects Zensical's per-page context and shares
one registry across the whole build automatically.

```toml
[project.markdown_extensions."zendoc.citations"]
```

Two different sources that happen to share the same key don't fail the
build: the first one built keeps that key, and the collision is logged as
a warning rather than raised as an error.

### Under other tools: manual

Outside Zensical, share a `CitationRegistry` yourself, the same way as
[zendoc.headings](headings.md#sharing-a-registry-across-a-multi-page-build):

```python
import markdown
from zendoc.citations import CitationsExtension
from zendoc.util import CitationRegistry

registry = CitationRegistry()

for path, text in pages:
    html = markdown.markdown(
        text,
        extensions=[CitationsExtension(registry=registry, source=path)],
    )
```

A genuine key collision between two different `source`s raises
`zendoc.util.DuplicateIdError` here, rather than warning - a deliberately
shared registry means you're expected to notice and fix it.

## What this doesn't do (yet)

`zendoc.citations` covers citation-key management - the "define once, cite
anywhere" part. It doesn't auto-generate the references page's listing
itself from structured bibliographic data (author/year/title/publisher/URL
fields) the way a full BibTeX-style tool would - the reference entry's own
text (as shown in the examples above) is still hand-authored prose, just
like today. Building that out is a natural next step, not yet implemented.
