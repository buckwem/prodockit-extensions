# prodockit

prodockit is a family of extensions for [Zensical](https://zensical.org/)
needed for professional and academic documentation - the pieces a report,
dissertation, or technical document commonly needs that Zensical doesn't
provide out of the box: section cross-references, bibliography/citation
handling, a glossary, and a Pandoc/WeasyPrint PDF pipeline for the
downloadable, submittable document these usually need alongside the
website itself.

Most of prodockit is [Python-Markdown](https://python-markdown.github.io/)
extensions, that are enabled in `zensical.toml`. [prodockit.pdf](pdf.md) is a command-line tool instead, since a PDF build pipeline isn't a Markdown syntax extension - no Python required, it reads the same `zensical.toml` too. In addition, there are a set of website macros to help use the features of prodockit.

It's a kit for professional documentation, built on Zensical's own Markdown and Pandoc/WeasyPrint PDF pipeline.

## Extensions

| Extension | Description |
|---|---|
| [prodockit.headings](extensions/headings.md) | Gives every heading an id and a hierarchical section number ("1", "1.1", "1.2", "2", ...). |
| [prodockit.refs](extensions/refs.md) | `\ref{id}` section cross-references, resolving to the target's current number - similar in spirit to LaTeX's `\ref`. |
| [prodockit.citations](extensions/citations.md) | Define a source once, cite it by key anywhere with `\cite{id}` - auto-generates the bracketed, linked citation text. |
| [prodockit.glossary](extensions/glossary.md) | Define a term once (an acronym expansion, a glossary entry), insert it by id anywhere with `\gls{id}` - similar in spirit to LaTeX's `glossaries` package. |

## PDF generation

| Module | Description |
|---|---|
| [prodockit.pdf](pdf.md) | Builds a standalone PDF from your site, via Pandoc and WeasyPrint. Run `prodockit pdf` from your project root - everything is read from your own `zensical.toml`. |

```bash
prodockit pdf
```

See [PDF generation](pdf.md) for the `zensical.toml` settings it reads, and
for the Python API if you're scripting your own build pipeline instead.

## Website macros

| Module | Description |
|---|---|
| [prodockit.zensical_macros](macros.md) | Jinja variables/macros for Zensical's macros plugin: a site-wide word count, the git-detected repository URL, chapter/appendix numbering that continues across pages, and reference/acronym/glossary spacing that matches `prodockit.pdf`'s own PDF output. |

```toml
[project.markdown_extensions.zensical.extensions.macros]
modules = ["prodockit.zensical_macros"]
```

See [Website macros](macros.md) for the full variable/macro list.

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
    extensions=["attr_list", "prodockit.headings", "prodockit.refs", "prodockit.citations"],
)
```

`\ref{background}` resolves to `1.1` - the current section number of the
heading it points to - and `\cite{skou2023}` resolves to `[Skoulikari,
2023]`, linked to that source's own paragraph. Both stay correct if
headings/sources are reordered, since resolution happens fresh on every
conversion.

## Status

Early, but functional. `prodockit.headings`, `prodockit.refs`, `prodockit.citations`,
`prodockit.glossary`, `prodockit.pdf`, and `prodockit.zensical_macros` are
implemented and tested; auto-generating a full references list from
structured bibliographic data is not yet built (see
[prodockit.citations](extensions/citations.md#what-this-doesnt-do-yet)), and
none of `prodockit.pdf`/`prodockit.zensical_macros` has a formal, versioned public
API yet (see [prodockit-extensions#7](https://github.com/buckwem/prodockit-extensions/issues/7)).
See the [Release Notes](about/changelog.md) for what's landed so far.
