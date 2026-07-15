# zendoc

zendoc is a family of extensions for [Zensical](https://zensical.org/)
needed for professional and academic documentation - the pieces a report,
dissertation, or technical document commonly needs that Zensical doesn't
provide out of the box: section cross-references, bibliography/citation
handling, a glossary, and a Pandoc/WeasyPrint PDF pipeline for the
downloadable, submittable document these usually need alongside the
website itself. Each piece is independent, so you only pay for what you
use.

Most of zendoc is [Python-Markdown](https://python-markdown.github.io/)
extensions, in the spirit of [pymdown-extensions](https://facelessuser.github.io/pymdown-extensions/) -
enable one in `zensical.toml` the same way as any other Zensical or
`pymdownx` extension (see [Installation](installation.md)).
[zendoc.pdf](pdf.md) is a command-line tool instead, since a PDF build
pipeline isn't a Markdown syntax extension - no Python required, it reads
the same `zensical.toml` too.

## Extensions

| Extension | Description |
|---|---|
| [zendoc.headings](extensions/headings.md) | Gives every heading an id and a hierarchical section number ("1", "1.1", "1.2", "2", ...). |
| [zendoc.refs](extensions/refs.md) | `\ref{id}` section cross-references, resolving to the target's current number - similar in spirit to LaTeX's `\ref`. |
| [zendoc.citations](extensions/citations.md) | Define a source once, cite it by key anywhere with `\cite{id}` - auto-generates the bracketed, linked citation text. |
| [zendoc.glossary](extensions/glossary.md) | Define a term once (an acronym expansion, a glossary entry), insert it by id anywhere with `\gls{id}` - similar in spirit to LaTeX's `glossaries` package. |

## PDF generation

| Module | Description |
|---|---|
| [zendoc.pdf](pdf.md) | Builds a standalone PDF from your site, via Pandoc and WeasyPrint. Run `zendoc pdf` from your project root - everything is read from your own `zensical.toml`. |

```bash
zendoc pdf
```

See [PDF generation](pdf.md) for the `zensical.toml` settings it reads, and
for the Python API if you're scripting your own build pipeline instead.

## Quick example

```python
import markdown

html = markdown.markdown(
    """
# Introduction

See \\ref{background} for context.\\cite{skou2023}

## Background

...

Skoulikari, A. (2023) *Learning Git*.
{: #skou2023 data-cite-text="Skoulikari, 2023" }
""",
    extensions=["attr_list", "zendoc.headings", "zendoc.refs", "zendoc.citations"],
)
```

`\ref{background}` resolves to `1.1` - the current section number of the
heading it points to - and `\cite{skou2023}` resolves to `[Skoulikari,
2023]`, linked to that source's own paragraph. Both stay correct if
headings/sources are reordered, since resolution happens fresh on every
conversion.

## Status

Early, but functional. `zendoc.headings`, `zendoc.refs`, `zendoc.citations`,
`zendoc.glossary`, and `zendoc.pdf` are implemented and tested; auto-
generating a full references list from structured bibliographic data is not
yet built (see [zendoc.citations](extensions/citations.md#what-this-doesnt-do-yet)),
and `zendoc.pdf` has no formal, versioned public API yet (see
[zendoc-extension#7](https://github.com/buckwem/zendoc-extension/issues/7)).
See the [Release Notes](about/changelog.md) for what's landed so far.
