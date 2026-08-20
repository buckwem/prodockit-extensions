---
icon: lucide/quote
---

# Citations or References

\index{`prodockit.citations`} lets you write a reference once and cite it from
any page. A citation such as `[Skoulikari, 2023]` links readers to the full
reference.

!!! tip "Looking for an auto-generated bibliography instead?"
    This page is for a short reference list that you write yourself. To create
    a reference list automatically from a `.bib` file, use
    [Bibliography](bibliography.md).

Use this extension when you want to write and format a short reference list by
hand, but define each citation's link text only once.

## Enable the extension {: #citations-enable }

Enable it in `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.citations"]
```

## Add and cite a reference {: #citations-quick-start }

Write the full reference, then add its id and the shorter text you want to show
in citations on the line below. Cite it with `\citeref{id}`:

=== "Markdown"

    ```md
    Git is a tool used to manage version control.\citeref{skou-example}

    Skoulikari, A. (2023) *Learning Git: A Hands-On and Visual Guide to the
    Basics of Git*. Sebastopol, CA: O'Reilly Media.
    {: #skou-example .reference data-cite-text="Skoulikari, 2023" }
    ```

=== "Result"

    Git is a tool used to manage version control.\citeref{skou-example}

    Skoulikari, A. (2023) *Learning Git: A Hands-On and Visual Guide to the
    Basics of Git*. Sebastopol, CA: O'Reilly Media.
    {: #skou-example .reference data-cite-text="Skoulikari, 2023" }

The extension replaces `\citeref{skou-example}` with the linked citation
`[Skoulikari, 2023]`. Select it to jump to the full reference.

## Configure citations

### Choose the missing-citation text

An unresolved citation displays `?` by default. Set `unresolved` if your
project uses a different marker:

```toml
[project.markdown_extensions."prodockit.citations"]
unresolved = "MISSING"
```

`source` is the only other TOML setting. It identifies the current page, but
Zensical detects it automatically; leave it unset in `zensical.toml`.

Multiple comma-separated keys join into one bracket:
`\citeref{skou2023,chacon2014}` → `[Skoulikari, 2023; Chacon and Straub,
2014]`.

### Cite a source before its full reference {: #citations-forward-references }

A citation to a source defined *later* in the same document resolves
correctly:

```md
See \citeref{skou2023} for an introduction to Git.

Skoulikari, A. (2023) *Learning Git*.
{: #skou2023 data-cite-text="Skoulikari, 2023" }
```

### Fix a missing citation {: #citations-unresolved-citations }

If a citation id is missing or mistyped, the extension displays `?` for that
entry. Other valid entries in the same citation still work:

```md
\citeref{skou2023,does-not-exist}
```

This renders `[Skoulikari, 2023; ?]`. Check the id that produced `?` against
the id on the full reference.

## Reference {: #citations-reference }

### Syntax {: #citations-syntax }

Defining and citing are bundled into one extension, unlike
[prodockit.headings](headings.md)/[prodockit.refs](refs.md): a definition is
useless without somewhere to cite it, so there's no independently useful
"just defining" half to split out.

#### Defining a source

Any block element - typically a paragraph - with both an `id` and a
`data-cite-text` attribute becomes a citable source:

```md
Chacon, S. and Straub, B. (2014) *Pro Git*. 2nd edn. New York: Apress.
{: #chacon2014 .reference data-cite-text="Chacon and Straub, 2014" }
```

`data-cite-text` is the short text rendered at each citation site - it's
stripped from the rendered output (it's internal bookkeeping, not meant to
be visible), while `id` stays, since citations link straight to it.

#### Citing a source

| Syntax | Purpose |
| --- | --- |
| `\citeref{<id>}` | Cite one defined source |
| `\citeref{<id1>,<id2>,...}` | Cite several sources in one bracket |

Like [prodockit.refs](refs.md), `\citeref{...}` is recognised the same way
Python-Markdown's own inline syntax is, so it's protected inside inline
code spans and fenced code blocks:

````md
Type `\citeref{skou2023}` to cite a source.

```
\citeref{skou2023}
```
````

Neither of the two shown above is resolved; both render the literal text.

### Zensical settings {: #citations-options }

| Setting | Default | What it controls |
|---|---|---|
| \index{prodockit.citations!`unresolved`} | `"?"` | Text shown for a citation id that cannot be found. |
| \index{prodockit.citations!`source`} | `""` (detected automatically) | Advanced: identifies the current page when using the extension outside Zensical. Leave it unset in `zensical.toml`. |

`registry` is not a `zensical.toml` setting. It accepts a `CitationRegistry`
Python object when you construct `CitationsExtension` yourself; see the manual
multi-page example below.

### Multi-page builds {: #citations-multi-page-builds }

#### Under Zensical: automatic {: #citations-under-zensical-automatic }

Under [Zensical](https://zensical.org/), citing a source defined on a
*different* page (the common case - a references page separate from the
pages that cite it) works with no extra configuration, the same way
[prodockit.refs](refs.md#refs-under-zensical-automatic) shares its registry across
pages: `prodockit.citations` detects Zensical's per-page context and shares
one registry across the whole build automatically.

```toml
[project.markdown_extensions."prodockit.citations"]
```

**Citing a source before it's defined works too** - the common case, since
a references page is usually cited from earlier chapters but kept at the
*end* of nav as an appendix. Normally that's a forward reference to a page
`zensical build`'s single, one-shot pass hasn't rendered yet (unlike
`zensical serve`'s live-reload, which eventually rebuilds every page at
least once) - `prodockit.citations` avoids this by pre-scanning every page in
the current Zensical build's nav for citation definitions (reading raw
file text directly, not waiting for Python-Markdown to parse each one)
before any single page has actually been converted, the same way LaTeX
needs multiple compilation passes to resolve a `\cite` used before its
`\bibitem` - except here it happens automatically, within one `zensical
build` invocation.

Two different sources that happen to share the same key don't fail the
build: the first one scanned keeps that key, and the collision is logged as
a warning rather than raised as an error.

#### Under other tools: manual {: #citations-under-other-tools-manual }

Outside Zensical, share a `CitationRegistry` yourself, the same way as
[prodockit.headings](headings.md#sharing-a-registry-across-a-multi-page-build):

```python
import markdown
from prodockit.citations import CitationsExtension
from prodockit.util import CitationRegistry

registry = CitationRegistry()

for path, text in pages:
    html = markdown.markdown(
        text,
        extensions=[CitationsExtension(registry=registry, source=path)],
    )
```

A genuine key collision between two different `source`s raises
`prodockit.util.DuplicateIdError` here, rather than warning - a deliberately
shared registry means you're expected to notice and fix it.

### What this doesn't do (yet)

`prodockit.citations` covers citation-key management - the "define once, cite
anywhere" part. It doesn't auto-generate the references page's listing
itself from structured bibliographic data (author/year/title/publisher/URL
fields) the way a full BibTeX-style tool would - the reference entry's own
text (as shown in the examples above) is still hand-authored prose, just
like today. See [prodockit.bibliography](bibliography.md) for the
alternative that does exactly this, from a `.bib` file, in any citation
style - and for the tradeoffs between the two approaches.

## Customise with a CSS style sheet {: #citations-css-hooks }

`prodockit.citations` emits three hooks - one on the outer wrapper, one on
each individual key's own link:

| Element | State | Class |
|---|---|---|
| Outer `<span>` wrapping the whole `\citeref{...}` citation | always | `prodockit-cite` |
| Each key's own `<a>` | resolved | `prodockit-cite-resolved` |
| Each key's own `<a>` | unresolved | `prodockit-cite-unresolved` |

An unresolved key's `<a>` has no `href` (see
[Unresolved citations](#citations-unresolved-citations) above) - style
`prodockit-cite-unresolved` distinctly (e.g. a muted colour, no underline)
to make a missing citation visually obvious without inspecting the page
source. No `data-*` attribute is left in the rendered output - the
internal `data-prodockit-cite` placeholder attribute used during
resolution, and the `data-cite-text` attribute marking a definition, are
both always stripped before the page is rendered.
