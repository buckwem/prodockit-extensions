---
icon: lucide/link
---

# Cross-References

\index{`prodockit.refs`} creates links to headings elsewhere in your
documentation. Each link shows the heading's current number and name, such as
“1.1 Configuration”, so you do not have to update it when sections move.

Use `\ref` for a link that works on the website and in the PDF. Use `\autoref`
when the PDF should also show the target's page number.

## Enable the extension {: #refs-enable }

Enable it in `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.refs"]
```

## Reference a heading {: #refs-quick-start }

Reference any heading's id with `\ref{id}`:

=== "Markdown"

    ```md
    # Introduction {: #intro }

    See \ref{intro} for background.

    ## Background
    ```

=== "Result"

    **Introduction**

    See [1 Introduction](#refs-quick-start) for background.

    **Background**

The link takes the reader to the `Introduction` heading. Its number and name
update automatically if the document changes.

## Configure cross-references

### Choose the missing-reference text

An unresolved reference displays `??` by default. Set `unresolved` if your
project uses a different marker:

```toml
[project.markdown_extensions."prodockit.refs"]
unresolved = "MISSING"
```

`source` is the only other TOML setting. It identifies the current page, but
Zensical detects it automatically; leave it unset in `zensical.toml`.

### Reference a heading before it appears {: #refs-forward-references }

A reference to a heading defined *later* in the same document resolves
correctly:

```md
See \ref{background} below.

## Background {: #background }
```

### Fix a missing reference {: #refs-unresolved-references }

If the heading id is missing or mistyped, `\ref{id}` displays `??` instead of
a link. Check that the text inside the braces exactly matches the id on the
heading.

A heading marked `unnumbered` still works as a link. Because it has no section
number, the link displays only the heading name.

```md
# Cover Page {: .unnumbered #cover-page }

See \ref{cover-page}.
```

renders `\ref{cover-page}` as `Cover Page`, linked to `#cover-page`.

### Include a page number in the PDF {: #refs-autoref }

`\ref{id}` and `\autoref{id}` render exactly the same text - the target's
number and name. The difference is that `\autoref{id}` also carries the
target's **page number** in the PDF, which is what a reader holding a
printout needs and what a website reader has no use for:

=== "Markdown"

    ```md
    Configuration is covered in \autoref{configuration}.
    ```

=== "Website"

    Configuration is covered in [1.1 Configuration](#refs-autoref).

=== "PDF"

    Configuration is covered in 1.1 Configuration on page 12.

The " on page N" suffix comes from [prodockit.pdf](../pdf.md)'s own
stylesheet, so it appears only in the PDF - a page number on a scrolling
website would be meaningless. Nothing to enable: build the PDF and it is
there.

Which to use is a per-reference decision rather than a project-wide
setting: use `\autoref{id}` where a printed reader needs to turn to
something, and `\ref{id}` where the extra "on page N" would just be noise.

An appendix needs nothing special - its letter is already the first
segment of its number, so `\ref{terms}` renders "A.1 Terms".

### Reference a figure or table {: #refs-captions }

`\ref{id}` also resolves a captioned figure or table, rendering its label:

```md
![Component Model](assets/images/component-model.png){ width="100%" }
/// figure-caption
    attrs: {id: fig-component-model}

Component Model
///

The components inside the System Context boundary are shown in
\ref{fig-component-model}.
```

which renders as a link reading **Figure 3.1**.

Figures and tables are counted separately, and both restart per page and
carry the page's chapter number - the same numbering the caption itself
shows, so a reference and the thing it points at always agree.

!!! warning "The id goes in an `attrs:` option, not `{: #id }`"
    Caption blocks take attributes the [Blocks
    API](https://facelessuser.github.io/pymdown-extensions/extensions/blocks/)
    way - an indented `attrs:` line, then a blank line, then the caption
    text. The `{: #id }` form used on headings, images and table cells
    **does not work here**: it produces no figure at all, silently, and
    the `///` lines appear as literal text.

    An id containing a colon (`fig:component-model`) also produces no
    figure, quoted or not. Use a hyphen.

Unlike a heading, a caption reference is **its label alone** - "Figure
3.1", not "Figure 3.1 Component Model". A caption is referred to
mid-sentence, where repeating its own words reads as a stutter; a
heading's number alone would say nothing about where the reader is being
sent, so that keeps its name.

## Reference {: #refs-reference }

### Syntax {: #refs-syntax }

| Syntax | Result |
| --- | --- |
| `\ref{<id>}` | The target's current number and name |
| `\autoref{<id>}` | The same link, plus “on page N” in the PDF |

`<id>` is the target heading's id - either one you set explicitly via
[`attr_list`](https://python-markdown.github.io/extensions/attr_list/)
(`# Introduction {: #intro }`), or the one
[`toc`](https://python-markdown.github.io/extensions/toc/) derived
automatically from the heading text (see [prodockit.headings](headings.md#ids)
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

### Zensical settings {: #refs-options }

| Setting | Default | What it controls |
|---|---|---|
| \index{prodockit.refs!`unresolved`} | `"??"` | Text shown when an id cannot be found. |
| \index{prodockit.refs!`source`} | `""` (detected automatically) | Advanced: identifies the current page when using the extension outside Zensical. Leave it unset in `zensical.toml`. |

`registry` is not a `zensical.toml` setting. It accepts an `IdRegistry` Python
object when you construct `RefsExtension` yourself; see the manual multi-page
example below.

### Multi-page builds {: #refs-multi-page-builds }

#### Under Zensical: automatic {: #refs-under-zensical-automatic }

Under [Zensical](https://zensical.org/), cross-page references work with no
extra configuration - just enable both extensions in `zensical.toml` as
usual:

```toml
[project.markdown_extensions."prodockit.headings"]
[project.markdown_extensions."prodockit.refs"]
```

Zensical builds each page with its own, fresh `Markdown` instance, so
`prodockit.headings` detects this (via Zensical's own per-page context) and
transparently shares one registry across every page of the build, keyed by
each page's own path - no explicit `registry`/`source` needed.

**Referencing a heading on a page built later works too**, in a single
`zensical build` pass: `prodockit.headings` pre-scans every page in the
current build's nav for its headings' ids and section numbers before any
page has actually been converted, the same way
[prodockit.citations](citations.md#citations-under-zensical-automatic)
pre-scans for citation definitions. Pages aren't necessarily built in nav
order - or even all within one shared Python process - so without this a
cross-page `\ref{id}` could resolve on one build and fall back to
`unresolved` (`??`) on the next, from the same unchanged source (see
[prodockit-extensions#54](https://github.com/buckwem/prodockit-extensions/issues/54)).
A page that *is* converted in the same process supersedes its own
pre-scanned entries with the real ones from the parsed document, so the
pre-scan only ever fills a gap.

Two pages that happen to share an identically-titled heading (e.g. both
have their own "Overview" section) don't fail the build: the *first* one
built keeps that id, and the collision is logged as a warning rather than
raised as an error - give one of them an explicit id via `attr_list` (`##
Overview {: #api-overview }`) to disambiguate and make both referenceable.

#### Under other tools: manual {: #refs-under-other-tools-manual }

Outside \index{Zensical}, give `prodockit.headings` and `prodockit.refs` the *same*
`IdRegistry` on every page yourself, converting pages in the order
cross-references should become resolvable in:

```python
import markdown
from prodockit.headings import HeadingsExtension
from prodockit.refs import RefsExtension
from prodockit.util import IdRegistry

registry = IdRegistry()

for path, text in pages:
    html = markdown.markdown(
        text,
        extensions=[
            HeadingsExtension(registry=registry, source=path),
            RefsExtension(registry=registry, source=path),
        ],
    )
```

Give `RefsExtension` the same `source=path` as `HeadingsExtension` - without
it, every resolved link is treated as cross-page (harmless, just not the
minimal same-page form for a reference that happens to target its own
page).

Here, a genuine id collision between two different `source`s *does* raise
`prodockit.util.DuplicateIdError` rather than warning - a deliberately shared
registry means you're expected to notice and fix a collision, unlike the
best-effort automatic Zensical case above.

## Customise with a CSS style sheet {: #refs-css-hooks }

`prodockit.refs` always sets a class on the `\ref{id}` link it renders -
resolved or not - so a stylesheet has a stable hook either way:

| Syntax | State | Class |
|---|---|---|
| `\ref{id}` | Resolved | `prodockit-ref` |
| `\ref{id}` | Unresolved | `prodockit-ref prodockit-ref-unresolved` |
| `\autoref{id}` | Resolved | `prodockit-autoref` |
| `\autoref{id}` | Unresolved | `prodockit-autoref prodockit-autoref-unresolved` |

An unresolved reference (see [Unresolved references](#refs-unresolved-references)
above) still gets a `class` either way; style `prodockit-ref-unresolved`
distinctly (e.g. a warning colour) to make a broken cross-reference
visually obvious without inspecting the page source. No `data-*`
attribute is left in the rendered output - the internal
`data-prodockit-ref` placeholder attribute used during resolution is
always stripped before the page is rendered.

The PDF page-number suffix for `\autoref` is attached with
`target-counter()` to resolved in-document links. Unresolved references have
no `href`, so they do not print a stray “on page” suffix.
