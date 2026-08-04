# Refs

\index{`prodockit.refs`} adds a `\ref{id}` cross-reference syntax - similar in spirit
to LaTeX's `\ref` - that resolves to the *current* number and name of the
heading with that id, e.g. "1.1 Configuration". It depends on the id/number registry that
[prodockit.headings](headings.md) builds; enabling `prodockit.refs` on its own
transparently enables `prodockit.headings` too, with matching defaults, so a
single document works with no extra configuration.

## Quick start {: #refs-quick-start }

Enable it in `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.refs"]
```

then reference any heading's id with `\ref{id}`:

```md
# Introduction {: #intro }

See \ref{intro} for background.

## Background
```

renders to:

<!-- These are real headings, so that the \ref link below them resolves
     against real ids - but they are an illustration, not this page's own
     structure. The three classes keep them out of the chapter numbering
     (`unnumbered`), the PDF's Table of Contents (`unlisted`) and the PDF's
     bookmark outline (`example-heading`, see docs/stylesheets/extra.css);
     `prodockit.refs` itself emits none of them. -->
<h1 id="intro" class="unnumbered unlisted example-heading">Introduction</h1>
<p>See <a class="prodockit-ref" href="#intro">1 Introduction</a> for background.</p>
<h2 id="background" class="unnumbered unlisted example-heading">Background</h2>

Because the number is looked up fresh on every conversion, it stays correct
even if sections are added, removed, or reordered - you never have to
manually renumber a cross-reference. Referencing a heading defined on a
*different* page (see [Multi-page builds](#refs-multi-page-builds) below) links
to that page directly (e.g. `other.md#intro`, which Zensical rewrites into
the correct clean URL) rather than a bare `#intro` fragment, which would
only work if the target happened to be on the same page.

### Forward references {: #refs-forward-references }

A reference to a heading defined *later* in the same document resolves
correctly:

```md
See \ref{background} below.

## Background {: #background }
```

### Unresolved references {: #refs-unresolved-references }

`\ref{id}` renders the `unresolved` marker (`??` by default) instead of a
reference when `id` doesn't exist in the registry at all - a typo, or a
reference to a heading in a page that hasn't been converted yet in a
multi-page build (the same way an undefined LaTeX `\ref` shows `??` until
a later compilation pass).

A heading marked `unnumbered` (see
[prodockit.headings](headings.md#unnumbered-headings)) is *not* unresolved:
it has no number, but it does have a name, so it renders as just the name.

```md
# Cover Page {: .unnumbered #cover-page }

See \ref{cover-page}.
```

renders `\ref{cover-page}` as `Cover Page`, linked to `#cover-page`.

## Referencing by name and page {: #refs-autoref }

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

### CSS hooks {: #refs-autoref-css-hooks }

| State | Class |
|---|---|
| Resolved | `prodockit-autoref` |
| Unresolved | `prodockit-autoref prodockit-autoref-unresolved` |

The page-number suffix is attached with `target-counter()` on
`a.prodockit-autoref[href^="#"]::after`, scoped to in-document links: an
unresolved reference carries no `href` at all, and any other link would
resolve to nothing and print a stray "on page" with no number after it.

## Reference {: #refs-reference }

### Syntax {: #refs-syntax }

```
\ref{<id>}
```

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

### Options {: #refs-options }

| Option | Type | Default | Description |
|---|---|---|---|
| \index{prodockit.refs!`unresolved`} | `str` | `"??"` | Text rendered when `id` doesn't resolve to a numbered heading. |
| \index{prodockit.refs!`source`} | `str` | `""`, auto-detected under Zensical | Identifier for the current document (e.g. its path) - used only to decide whether a resolved target is on this same page (bare `#id`) or a different one (a real link to it). Doesn't affect resolution itself. |
| \index{prodockit.refs!`registry`} | `IdRegistry \| None` | discovered from a sibling `prodockit.headings`, or a new one | Share one registry across multiple documents - see below. Passed as a constructor keyword, not a string-based config value. |

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

### CSS hooks {: #refs-css-hooks }

`prodockit.refs` always sets a class on the `\ref{id}` link it renders -
resolved or not - so a stylesheet has a stable hook either way:

| State | Class |
|---|---|
| Resolved | `prodockit-ref` |
| Unresolved | `prodockit-ref prodockit-ref-unresolved` |

An unresolved reference (see [Unresolved references](#refs-unresolved-references)
above) still gets a `class` either way; style `prodockit-ref-unresolved`
distinctly (e.g. a warning colour) to make a broken cross-reference
visually obvious without inspecting the page source. No `data-*`
attribute is left in the rendered output - the internal
`data-prodockit-ref` placeholder attribute used during resolution is
always stripped before the page is rendered.
