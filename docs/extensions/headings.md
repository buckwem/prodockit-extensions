---
icon: lucide/heading
---

# Headings

\index{`prodockit.headings`} numbers the headings in your document as sections,
such as `1`, `1.1`, and `1.2`. The numbers update automatically when you add,
remove, or move a heading.

Use it when your document needs numbered sections. Add
[Cross-References](refs.md) when you also want to link readers to those
sections by number and name.

## Enable the extension {: #headings-enable }

Enable it in `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.headings"]
numbering = "continuous"
```

`continuous` carries the numbering across the pages in your Zensical
navigation. Use `per-document` instead when every page should start again at
section 1.

## Number headings {: #headings-quick-start }

Each `#` heading starts a main section (`1`, `2`, and so on). A `##` heading
starts a section inside it (`1.1`, `1.2`, and so on):

=== "Markdown"

    ```md
    # Introduction

    ## Background

    ## Scope

    # Method
    ```

=== "Result"

    | Heading | id | number |
    |---|---|---|
    | Introduction | `introduction` | `1` |
    | Background | `background` | `1.1` |
    | Scope | `scope` | `1.2` |
    | Method | `method` | `2` |

The extension calculates the section numbers, but it does not add them to the
visible heading text on the website. [Cross-References](refs.md) uses the
calculated numbers in links such as “1.1 Background”.

!!! note "Why the heading itself does not visibly change"
    The section numbers appear in [Cross-References](refs.md), rather than next
    to the website's heading text.

## Configure headings

### Choose how numbering continues {: #continuous-numbering-across-pages-zensical }

The `numbering` setting accepts two values:

| Value | Result |
| --- | --- |
| `"continuous"` | Continue the main section numbers across pages in Zensical navigation order. |
| `"per-document"` | Start each page's main section numbering at 1. This is the extension's default. |

For a multi-page documentation site, set the option in `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.headings"]
numbering = "continuous"
```

For example, if one page ends at section 3, the next page starts at section 4.
This also lets [Cross-References](refs.md) show one consistent set of section
numbers across the site.

### Number appendices {: #appendices }

Add `is_appendix: true` to the settings at the top of the page (its
\index{front matter}) to use letter-based numbering instead of the normal
numeric sequence - `"A"`, `"A.1"`,
`"A.1.1"` - once you've enabled
[continuous numbering](#continuous-numbering-across-pages-zensical) (see
Reference below). An \index{appendix} page doesn't consume a number from the
numeric sequence at all, so pages after it aren't left with a gap. Letters
are assigned sequentially in \index{nav order} - the first `is_appendix` page
becomes `"A"`, the second `"B"`, and so on, independent of how many
numbered pages come before them.

For example, with this nav order:

```toml
nav = [
  {"Install tooling" = "installtooling.md"},
  {"Glossary" = "glossary.md"},
  {"References" = "references.md"},
]
```

and `glossary.md` flagged as an appendix:

```md
<!-- glossary.md -->
---
is_appendix: true
---

# Glossary

## Terms {: #terms }
```

a [prodockit.refs](refs.md) reference to `Terms` from another page:

```md
<!-- references.md -->
# References

See \ref{terms} for defined terms.
```

renders to (a link to `glossary.md#terms`, shown here as a code block
since `glossary.md` isn't a real page on *this* site):

```html
<p>See <a class="prodockit-ref" href="glossary.md#terms">A.1</a> for defined terms.</p>
```

`Glossary`'s own `h1` becomes `"A"` (the first appendix page in nav) and
its `Terms` subheading becomes `"A.1"` - and `References`, the page after
it, still gets the next plain number in the numeric sequence (`"2"`, not
`"3"`), exactly as if the appendix page had never consumed one. Only
meaningful under [Zensical](https://zensical.org/); ignored otherwise.

### Leave a heading unnumbered {: #unnumbered-headings }

A heading with an \index{headings!`unnumbered`} class - e.g. a cover page or title slide -
still gets an id, but is skipped when computing section numbers, so it
doesn't consume a counter position:

```md
# Cover Page {: .unnumbered }

# Introduction
```

`Introduction` above is still numbered `1`, as if `Cover Page` weren't
there at all.

### Hide a heading from PDF navigation {: #unlisted-and-unbookmarked-headings-pdf-only }

A PDF built by [prodockit.pdf](../pdf.md) has *two* tables of contents, and
`unnumbered` alone only reaches one of them:

- The generated **Table of Contents page**, built from every heading
  Pandoc sees. Add \index{headings!`unlisted`} to also keep a heading off
  this page - it still keeps its `id` and number (if any), the same as
  `unnumbered` above. Pandoc itself defines this class and honours it via
  `pandoc.structure.table_of_contents()`; prodockit doesn't add or change
  its meaning.
- The **bookmark outline** - the navigation pane a PDF reader shows down
  the side. This is built separately by WeasyPrint from every `h1`-`h6` in
  the document, and `unlisted` has no effect on it at all. Add
  \index{headings!`unbookmarked`} to also remove a heading from the
  outline.

```md
# Cover Page {: .unnumbered .unlisted .unbookmarked }
```

This distinction matters because outline nesting follows heading level:
an `unlisted` (but not `unbookmarked`) `h1` still becomes a *top-level*
outline node, and every following heading of lower level nests underneath
it instead of under its real chapter - not just one stray entry, but a
misnested chunk of the outline. See
[Table of contents and bookmark outline](../pdf.md#table-of-contents-and-bookmark-outline)
for the underlying stylesheet rule and worked example.

## Reference {: #headings-reference }

### Ids

An id comes from one of, in order of precedence:

1. An explicit id set via
   [`attr_list`](https://python-markdown.github.io/extensions/attr_list/),
   e.g. `# Introduction {: #custom-id }`.
2. Python-Markdown's own [`toc`](https://python-markdown.github.io/extensions/toc/)
   extension, which `prodockit.headings` enables automatically (with its
   defaults) if you haven't already enabled it yourself - so if you *have*
   configured `toc` (e.g. with `permalink: true`), that configuration is
   left untouched and reused.
3. A minimal built-in slugify fallback, used only if `toc` is somehow not
   registered at all (this should not normally happen, since
   `prodockit.headings` enables it).

### Zensical settings {: #headings-options }

| Setting | Default | What it controls |
|---|---|---|
| \index{prodockit.headings!`numbering`} | `"per-document"` | Use `"continuous"` to carry main section numbers across pages in Zensical navigation order. |
| \index{prodockit.headings!`appendix_attr`} | `"is_appendix"` | Name of the front matter setting that marks an appendix page. Change this only if your project uses another name. |
| \index{prodockit.headings!`source`} | `""` (detected automatically) | Advanced: identifies the current page when using the extension outside Zensical. Leave it unset in `zensical.toml`. |

`registry` is not a `zensical.toml` setting. It accepts an `IdRegistry` Python
object when you construct `HeadingsExtension` yourself; the manual multi-page
example below shows when that is useful.

### Sharing a registry across a multi-page build

To resolve cross-page references, every page in a build needs to write into
- and read from - the *same* \index{`IdRegistry`} instance, each scoped by its own,
distinct `source`.

Under [Zensical](https://zensical.org/), this happens automatically with no
configuration - see [prodockit.refs](refs.md#refs-multi-page-builds) for details:
`prodockit.headings` detects Zensical's per-page context (each page gets its
own fresh `Markdown` instance) and uses it to derive `source` from the
page's own path, sharing one registry across the whole build. This
auto-detection only activates when you *haven't* set an explicit `registry`
or `source` yourself, and has no effect at all outside Zensical.

For any other tool, construct a registry yourself and pass it to every
page's extension instance, along with that page's own `source`:

```python
import markdown
from prodockit.headings import HeadingsExtension
from prodockit.util import IdRegistry

registry = IdRegistry()

for path, text in pages:
    html = markdown.markdown(
        text,
        extensions=[HeadingsExtension(registry=registry, source=path)],
    )
```

A duplicate id registered from two *different* sources raises
`prodockit.util.DuplicateIdError` here - re-converting the *same* source (e.g.
a live-reload dev server) is safe and expected; its previous entries are
cleared first. (Zensical's automatic sharing above uses the same registry,
but logs a warning and keeps the first registration instead of raising -
appropriate for a best-effort default rather than a setup you configured
deliberately.)

!!! warning "The 'keeping the first' winner isn't stable across builds"
    A heading name shared across two or more pages (e.g. every page having
    its own "Quick start"/"Options"/"Syntax" section - common in a set of
    parallel extension/module docs) produces a "collides with ... -
    keeping the first" warning under Zensical's automatic sharing above -
    but *which* page's registration actually wins isn't something you can
    rely on: Zensical doesn't render pages in a guaranteed stable order,
    confirmed directly by running `zensical build` repeatedly against
    identical source and observing the reported winner change from one
    run to the next. Anything depending on that id - a `\ref{id}`/a hand-
    typed anchor link - can silently point at the wrong page's heading
    depending on which build produced it.

    The fix is to give every colliding heading its own explicit, unique
    id via `attr_list`, rather than leaving it to whichever page happens
    to register first:

    ```md
    ## Quick start {: #refs-quick-start }
    ```

    A page-prefixed slug (`<page>-<heading>`) is a simple, collision-proof
    convention - this project's own documentation uses exactly this
    scheme throughout (every extension page shares several heading names
    with the others), so its own markdown source is a worked example if
    you want to see it applied across a whole site.

### Looking up the same numbers from your own build tooling

`prodockit.headings.prescan(appendix_attr="is_appendix")` returns
`(start_counts, appendix_letters)` - both `dict[str, ...]` keyed by
nav-relative page path - the exact same pre-scan `HeadingsExtension` itself
uses internally for `numbering="continuous"`. A consuming project's own
build tooling can call this directly to stay in sync automatically, rather
than re-deriving the same page-order/heading-count logic a second,
independent way - e.g. a template macro that emits a presentational CSS
counter-reset per page, matching whatever number `prodockit.headings` computes
for that page's first heading (see
[prodockit.zensical_macros](../macros.md#heading_counter_resetpage)). Returns
`None` outside a Zensical build.

## Customise with a CSS style sheet {: #headings-css-hooks }

`prodockit.headings` doesn't add any class of its own to a heading - only an
`id` (see above), the class(es) already on the heading (e.g. `unnumbered`),
and whatever the numbers themselves feed into via the registry (typically
consumed by [prodockit.refs](refs.md), or by a template's own build tooling via
`prescan()` above to drive presentational CSS). There is currently no
`prodockit-heading`-style class to hook a stylesheet onto directly.
