---
icon: lucide/link
---

{{ heading_counter_reset(page) }}

# Cross-references

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

Most documents use the defaults. The following settings are for changing the
visible unresolved marker or integrating a renderer that cannot identify the
current source page automatically.

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

Set a figure's width once, on the image as shown above. The caption follows
the image's effective rendered width on both the website and in the PDF, so a
long caption wraps at the figure edges. This also applies when a PDF height
limit scales a tall image down; do not repeat the width on the caption block.

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

Use the following subsections when you need the exact inline forms or settings
rather than the worked examples above. They cover the two reference commands,
the Zensical options, and how destinations are resolved across pages.

### Syntax {: #refs-syntax }

The two reference forms and their rendered results are compared in
\ref{tab-extensions-refs-syntax}.

| Syntax | Result |
| --- | --- |
| `\ref{<id>}` | The target's current number and name |
| `\autoref{<id>}` | The same link, plus “on page N” in the PDF |
/// table-caption | <
    attrs: {id: tab-extensions-refs-syntax}

Syntax
///

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

\ref{tab-extensions-refs-zensical-settings} lists the settings that control
unresolved text and advanced source identification.

| Setting {: width="32%" } | Default | What it controls |
|---|---|---|
| \index{prodockit.refs!`unresolved`} | `"??"` | Text shown when an id cannot be found. |
| \index{prodockit.refs!`source`} | `""` (detected automatically) | Advanced: identifies the current page when using the extension outside Zensical. Leave it unset in `zensical.toml`. |
/// table-caption | <
    attrs: {id: tab-extensions-refs-zensical-settings}

Zensical settings
///

### Cross-page references {: #refs-multi-page-builds }

Under Zensical, cross-page references work automatically when headings and
references are enabled. Prodockit reads heading ids and numbers across the
navigation before individual pages finish rendering, so a reference can point
to a page built later.

Two pages with the same generated heading id produce a warning. Give the
headings distinct explicit ids so every destination is stable.

For integration with another Markdown renderer, see
[Extension integration](../devcons/extension-internals.md#share-definitions-across-pages).

## Customise with a CSS style sheet {: #refs-css-hooks }

`prodockit.refs` always sets a class on the `\ref{id}` link it renders -
resolved or not - so a stylesheet has a stable hook either way:

\ref{tab-extensions-refs-customise-with-a-css-style-sheet} lists the resolved and unresolved reference classes available to a custom stylesheet.

| Syntax | State | Class |
|---|---|---|
| `\ref{id}` | Resolved | `prodockit-ref` |
| `\ref{id}` | Unresolved | `prodockit-ref prodockit-ref-unresolved` |
| `\autoref{id}` | Resolved | `prodockit-autoref` |
| `\autoref{id}` | Unresolved | `prodockit-autoref prodockit-autoref-unresolved` |
/// table-caption | <
    attrs: {id: tab-extensions-refs-customise-with-a-css-style-sheet}

Customise with a CSS style sheet
///

An unresolved reference (see [Unresolved references](#refs-unresolved-references)
above) still gets a `class` either way; style `prodockit-ref-unresolved`
distinctly (e.g. a warning colour) to make a broken cross-reference
visually obvious. Unresolved references have no destination, so an unresolved
`\autoref` does not print a stray page-number suffix in the PDF.
