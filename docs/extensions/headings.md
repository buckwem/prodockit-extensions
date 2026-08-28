---
icon: lucide/heading
---

{{ heading_counter_reset(page) }}

# Headings

\index{`prodockit.headings`} numbers the headings in your document as sections,
such as `1`, `1.1`, and `1.2`. The numbers update automatically when you add,
remove, or move a heading.

Use it when your document needs numbered sections. Add
[Cross-references](refs.md) when you also want to link readers to those
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

    The rendered result in \ref{tab-extensions-headings-number-headings} shows the number and identifier assigned to each heading.

    | Heading | id | number |
    |---|---|---|
    | Introduction | `introduction` | `1` |
    | Background | `background` | `1.1` |
    | Scope | `scope` | `1.2` |
    | Method | `method` | `2` |
    /// table-caption | <
        attrs: {id: tab-extensions-headings-number-headings}

    Number headings
    ///

The result in \ref{tab-extensions-headings-number-headings} shows the numbering
the extension also supplies to
[Cross-references](refs.md). The shared prodockit website styles can also show
those numbers beside headings and in the page navigation. This reference site
has that presentation enabled, so the example headings on this page are
visibly numbered.

!!! note "Calculation and presentation are separate"
    A site can hide the visible numbers without changing the numbers resolved
    by `\ref{}`. The template-level `extra.website_heading_numbering` switch
    controls the website presentation; `extra.heading_numbering` controls
    whether document-style numbering is enabled for the project and its PDF.

## Configure headings

Configuration decides whether numbering continues across pages, where a page's
counter starts, and which headings are deliberately excluded. The following
subsections cover those choices in that order.

### Choose how numbering continues {: #continuous-numbering-across-pages-zensical }

The `numbering` setting accepts two values:

\ref{tab-extensions-headings-choose-how-numbering-continues} compares page-by-page numbering with numbering that continues across the site.

| Value | Result |
| --- | --- |
| `"continuous"` | Continue the main section numbers across pages in Zensical navigation order. |
| `"per-document"` | Start each page's main section numbering at 1. This is the extension's default. |
/// table-caption | <
    attrs: {id: tab-extensions-headings-choose-how-numbering-continues}

Choose how numbering continues
///

Choose the continuation behaviour from
\ref{tab-extensions-headings-choose-how-numbering-continues}, then set it in
`zensical.toml`:

```toml
[project.markdown_extensions."prodockit.headings"]
numbering = "continuous"
```

For example, if one page ends at section 3, the next page starts at section 4.
This also lets [Cross-references](refs.md) show one consistent set of section
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

For example:

=== "Markdown"

    ```md
    ---
    is_appendix: true
    ---

    # Glossary

    ## Terms {: #terms }
    ```

=== "Result"

    The rendered result in \ref{tab-extensions-headings-number-appendices} shows letters used for appendix headings and decimal numbers retained beneath them.

    | Heading | Number |
    | --- | --- |
    | Glossary | A |
    | Terms | A.1 |
    /// table-caption | <
        attrs: {id: tab-extensions-headings-number-appendices}

    Number appendices
    ///

The appendix result in \ref{tab-extensions-headings-number-appendices} is also
used by a [prodockit.refs](refs.md) reference to `Terms` from another page:

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

=== "Markdown"

    ```md
    # Cover Page {: .unnumbered }

    # Introduction
    ```

=== "Result"

    The rendered result in \ref{tab-extensions-headings-leave-a-heading-unnumbered} shows how an unnumbered heading affects the headings that follow it.

    | Heading | Number |
    | --- | --- |
    | Cover Page | none |
    | Introduction | 1 |
    /// table-caption | <
        attrs: {id: tab-extensions-headings-leave-a-heading-unnumbered}

    Leave a heading unnumbered
    ///

In \ref{tab-extensions-headings-leave-a-heading-unnumbered}, `Introduction` is
still numbered `1`, as if `Cover Page` weren't
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

Use this section to look up id generation and the complete Zensical settings
after choosing the numbering behaviour in the worked examples.

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

The numbering modes and their defaults are collected in
\ref{tab-extensions-headings-zensical-settings}.

| Setting {: width="32%" } | Default | What it controls |
|---|---|---|
| \index{prodockit.headings!`numbering`} | `"per-document"` | Use `"continuous"` to carry main section numbers across pages in Zensical navigation order. |
| \index{prodockit.headings!`appendix_attr`} | `"is_appendix"` | Name of the front matter setting that marks an appendix page. Change this only if your project uses another name. |
| \index{prodockit.headings!`source`} | `""` (detected automatically) | Advanced: identifies the current page when using the extension outside Zensical. Leave it unset in `zensical.toml`. |
/// table-caption | <
    attrs: {id: tab-extensions-headings-zensical-settings}

Zensical settings
///

### Cross-page numbering in Zensical

Zensical shares heading information across the complete navigation
automatically. With `numbering = "continuous"`, adding or reordering a page
updates later section numbers without a manual starting value.

Give repeated headings explicit ids. If several pages each contain `## Quick
start`, their automatically generated ids collide and the build warns; which
page renders first is not a stable way to choose a link target:

```md
## Quick start {: #refs-quick-start }
```

For integration with another Markdown renderer, see
[Extension integration](../devcons/extension-internals.md#share-definitions-across-pages).

## Customise with a CSS style sheet {: #headings-css-hooks }

`prodockit.headings` doesn't add any class of its own to a heading - only an
`id` (see above), the class(es) already on the heading (e.g. `unnumbered`),
and whatever numbers are consumed by [prodockit.refs](refs.md). There is no
`prodockit-heading`-style class to hook a stylesheet onto directly.
