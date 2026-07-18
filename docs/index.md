<div class="cover-hero" markdown="1">
<div class="cover-hero-text" markdown="1">

# <span class="cover-hero-title-light">prodockit</span> {: .cover-hero-title }

A family of extensions for Zensical needed for professional and academic documentation.
{: .cover-hero-subtitle }

[:material-file-pdf-box: Download PDF](site_documentation.pdf){ .md-button .md-button--primary target="_blank" .web-only }

</div>
<div class="cover-hero-graphic" markdown="1">

![Illustration of abstract flowing concentric lines, representing professional documentation](assets/cover-hero-light.svg#only-light){ .off-glb .hero-light }
![Illustration of abstract flowing concentric lines, representing professional documentation](assets/cover-hero-dark.svg#only-dark){ .off-glb .hero-dark }

</div>
</div>

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
| [prodockit.tables](extensions/tables.md) | Percentage or fixed column widths on a table, via a `width` attribute already attachable to a header cell with `attr_list`. |
| [prodockit.bibliography](extensions/bibliography.md) | An alternative to `prodockit.citations`: define sources in a BibTeX/BibLaTeX `.bib` file and format `\cite{id}`/the reference list in any Citation Style Language style, via Pandoc's own `--citeproc`. |

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
`prodockit.glossary`, `prodockit.tables`, `prodockit.bibliography`, `prodockit.pdf`,
and `prodockit.zensical_macros` are implemented and tested.
`prodockit.citations` itself still doesn't auto-generate a full references
list from structured bibliographic data (see
[prodockit.citations](extensions/citations.md#what-this-doesnt-do-yet)) -
[prodockit.bibliography](extensions/bibliography.md) is the alternative
that does, via a `.bib` file and Pandoc's own `--citeproc`. None of
`prodockit.bibliography`/`prodockit.pdf`/`prodockit.zensical_macros` has a
formal, versioned public API yet (see
[prodockit-extensions#7](https://github.com/buckwem/prodockit-extensions/issues/7)).
See the [Release Notes](about/changelog.md) for what's landed so far.
