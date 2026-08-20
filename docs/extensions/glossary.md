---
icon: lucide/book-open
---

# Acronyms and Glossary

\index{`prodockit.glossary`} lets you define an acronym or term once and reuse
it throughout your documentation. Each use links readers to the definition.

Use it for terms that readers may want to look up, such as an acronym or a
specialist word.

## Enable the extension {: #glossary-enable }

Enable it in `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.glossary"]
```

## Define and use a term {: #glossary-quick-start }

Write the definition, then add its id and the text that should appear in your
sentences on the line below. Insert the linked term with `\gls{id}`:

=== "Markdown"

    ```md
    This site uses a \gls{css-example} to control appearance.

    **CSS style sheet** - A file containing Cascading Style Sheets rules.
    {: #css-example .glossary data-term="CSS style sheet" }
    ```

=== "Result"

    This site uses a \gls{css-example} to control appearance.

    **CSS style sheet** - A file containing Cascading Style Sheets rules.
    {: #css-example .glossary data-term="CSS style sheet" }

The extension replaces `\gls{css-example}` with **CSS style sheet** and links
it to the definition. Select the link to jump to the definition.

## Configure glossary terms

### Use a term before its definition {: #glossary-forward-references }

You can use a term before its definition appears on the page:

```md
This example uses a \gls{css} for its layout.

**CSS style sheet** - A file containing Cascading Style Sheets rules.
{: #css data-term="CSS style sheet" }
```

### Fix a missing term {: #glossary-unresolved-references }

If a term id is missing or mistyped, the extension displays `?` instead of a
link:

```md
\gls{does-not-exist}
```

Check that the text inside the braces exactly matches the id on the definition.

### Keep acronyms and glossary terms on separate pages

You can keep acronym expansions on one page and longer glossary definitions on
another. `\gls{id}` works with a definition on either page:

```md
<!-- acronyms.md -->
**CSS** - Cascading Style Sheets.
{: #css .acronym data-term="CSS" }
```

```md
<!-- glossary.md -->
**Cascading Style Sheets** - The language used to control appearance.
{: #css-def .glossary data-term="Cascading Style Sheets" }
```

#### Link the two entries

Use an ordinary Markdown link when the link text needs to say “glossary” or
“acronyms”. The text inside square brackets is what the reader sees:

```md
<!-- acronyms.md -->
**CSS** - Cascading Style Sheets. See the [glossary](glossary.md#css-def) for what this means in practice.
{: #css .acronym data-term="CSS" }
```

```md
<!-- glossary.md -->
**Cascading Style Sheets** - The language used to control appearance. See the [Acronyms](acronyms.md#css) entry for the expansion.
{: #css-def .glossary data-term="Cascading Style Sheets" }
```

Use `\gls{id}` to insert the term itself. Use `[link text](page.md#id)` when
you want to choose different words for the link.

## Reference {: #glossary-reference }

### Syntax {: #glossary-syntax }

Like [prodockit.citations](citations.md), defining and inserting are bundled
into one extension: a definition is useless without somewhere to use it.

#### Defining a term

Any block element - typically a paragraph - with both an `id` and a
`data-term` attribute becomes usable with `\gls{id}`:

```md
**GUI** - Graphical User Interface.
{: #gui .acronym data-term="GUI" }
```

`data-term` is the text inserted at each `\gls{id}` site - it's stripped
from the rendered output (it's internal bookkeeping, not meant to be
visible), while `id` stays, since references link straight to it.

#### Using a term

| Syntax | Purpose |
| --- | --- |
| `\gls{<id>}` | Insert one term's registered display text and link it to its definition |

Unlike `\citeref{...}`, `\gls{...}` only ever takes a single id - there's no
multi-term/bracketed form, since inserting a term's own text doesn't
compose the way a citation list does.

Like [prodockit.refs](refs.md)/[prodockit.citations](citations.md), `\gls{...}`
is recognised the same way Python-Markdown's own inline syntax is, so it's
protected inside inline code spans and fenced code blocks:

````md
Type `\gls{css}` to insert a term.

```
\gls{css}
```
````

Neither of the two shown above is resolved; both render the literal text.

### Options {: #glossary-options }

| Option | Type | Default | Description |
|---|---|---|---|
| \index{prodockit.glossary!`source`} | `str` | `""` | Identifier for the current document (e.g. its file path). Used to scope this document's own term definitions in the registry, and to build a correct link when a `\gls{id}` target lives on a different page. |
| \index{prodockit.glossary!`unresolved`} | `str` | `"?"` | Text rendered for a `\gls{id}` that doesn't resolve to a definition. |
| \index{prodockit.glossary!`registry`} | `GlossaryRegistry \| None` | discovered automatically, or a new one | Share one registry across multiple documents - see below. Passed as a constructor keyword, not a string-based config value. |

### Multi-page builds {: #glossary-multi-page-builds }

#### Under Zensical: automatic {: #glossary-under-zensical-automatic }

Under [Zensical](https://zensical.org/), referencing a term defined on a
*different* page (the common case - Acronyms/Glossary appendix pages
separate from the pages that use them) works with no extra configuration,
the same way [prodockit.citations](citations.md#citations-under-zensical-automatic)
shares its registry across pages:

```toml
[project.markdown_extensions."prodockit.glossary"]
```

**Using a term before it's defined works too**, the same way as
`prodockit.citations`: `prodockit.glossary` pre-scans every page in the current
Zensical build's nav for term definitions before any page has actually
been converted, so a term used from an early chapter but defined on an
Acronyms/Glossary page kept at the end of nav resolves correctly within a
single `zensical build` pass.

Two different sources that happen to define the same id don't fail the
build: the first one scanned keeps that id, and the collision is logged as
a warning rather than raised as an error.

#### Under other tools: manual {: #glossary-under-other-tools-manual }

Outside Zensical, share a `GlossaryRegistry` yourself, the same way as
[prodockit.citations](citations.md#citations-under-other-tools-manual):

```python
import markdown
from prodockit.glossary import GlossaryExtension
from prodockit.util import GlossaryRegistry

registry = GlossaryRegistry()

for path, text in pages:
    html = markdown.markdown(
        text,
        extensions=[GlossaryExtension(registry=registry, source=path)],
    )
```

A genuine id collision between two different `source`s raises
`prodockit.util.DuplicateIdError` here, rather than warning - a deliberately
shared registry means you're expected to notice and fix it.

## Customise with a CSS style sheet {: #glossary-css-hooks }

`prodockit.glossary` always sets a class on the `\gls{id}` link it renders -
resolved or not - so a stylesheet has a stable hook either way:

| State | Class |
|---|---|
| Resolved | `prodockit-gls` |
| Unresolved | `prodockit-gls prodockit-gls-unresolved` |

An unresolved id's `<a>` has no `href` (see
[Unresolved references](#glossary-unresolved-references) above) - style
`prodockit-gls-unresolved` distinctly (e.g. a warning colour) to make a
missing term visually obvious without inspecting the page source. No
`data-*` attribute is left in the rendered output - the internal
`data-prodockit-gls` placeholder attribute used during resolution, and the
`data-term` attribute marking a definition, are both always stripped
before the page is rendered.
