# zendoc

A family of extensions for [Zensical](https://zensical.org/) needed for
professional and academic documentation: section cross-references,
bibliography/citation handling, a glossary, and a Pandoc/WeasyPrint PDF
pipeline for the downloadable, submittable document these usually need
alongside the website itself. Each piece is independent, so you only pay
for what you use.

Most of zendoc is [Python-Markdown](https://python-markdown.github.io/)
extensions, in the spirit of [pymdown-extensions](https://facelessuser.github.io/pymdown-extensions/) -
configure one the same way as any other Zensical/`pymdownx` Markdown
extension, via `zensical.toml`. `zendoc.pdf` is a command-line tool
instead (`zendoc pdf`), since a PDF build pipeline isn't a Markdown syntax
extension - it reads the same `zensical.toml` too.

> **Status:** early, but functional - `zendoc.headings`, `zendoc.refs`,
> `zendoc.citations`, `zendoc.glossary`, `zendoc.pdf`, and
> `zendoc.zensical_macros` are implemented and tested.

**[Full documentation](https://buckwem.github.io/zendoc-extensions/)**

## Installation

```bash
pip install zendoc
```

## Extensions

| Extension | Description |
|---|---|
| [`zendoc.headings`](https://buckwem.github.io/zendoc-extensions/extensions/headings/) | Gives every heading an id and a hierarchical section number ("1", "1.1", "1.2", "2", ...). |
| [`zendoc.refs`](https://buckwem.github.io/zendoc-extensions/extensions/refs/) | `\ref{id}` section cross-references, resolving to the target's current number - similar in spirit to LaTeX's `\ref`. |
| [`zendoc.citations`](https://buckwem.github.io/zendoc-extensions/extensions/citations/) | Define a source once, cite it by key anywhere with `\cite{id}` - auto-generates the bracketed, linked citation text. |
| [`zendoc.glossary`](https://buckwem.github.io/zendoc-extensions/extensions/glossary/) | Define a term once (an acronym expansion, a glossary entry), insert it by id anywhere with `\gls{id}` - similar in spirit to LaTeX's `glossaries` package. |

```python
import markdown

html = markdown.markdown(
    text,
    extensions=[
        "attr_list", "zendoc.headings", "zendoc.refs", "zendoc.citations", "zendoc.glossary"
    ],
)
```

```md
# Introduction {: #intro }

See \ref{intro} for background.\cite{skou2023} This uses \gls{css}.

Skoulikari, A. (2023) *Learning Git*.
{: #skou2023 data-cite-text="Skoulikari, 2023" }

**CSS** - Cascading Style Sheets.
{: #css data-term="CSS" }
```

`\ref{intro}` resolves to a link reading `1` - the heading's current
section number; `\cite{skou2023}` resolves to `[Skoulikari, 2023]`, linked
to that source; `\gls{css}` resolves to `CSS`, linked to its own
definition. All three stay correct if content is reordered, since
resolution happens fresh on every conversion. See the
[docs](https://buckwem.github.io/zendoc-extensions/) for options, multi-page
registry sharing, and full syntax details.

## PDF generation

[`zendoc.pdf`](https://buckwem.github.io/zendoc-extensions/pdf/) builds a
standalone PDF from your site, via Pandoc and WeasyPrint (both need to be
installed separately - see the docs). No Python required - it reads the
same `zensical.toml` your site already has:

```bash
zendoc pdf
```

That's it - run it from your project root and it builds a complete PDF,
table of contents included, from every page in your `nav`. See the
[docs](https://buckwem.github.io/zendoc-extensions/pdf/) for the
`zensical.toml` settings it reads, and for the Python API
(`build_pdf()`, `zendoc.pdf.html`/`.lua`/`.css`/`.icons`/`.mermaid`) if
you're scripting your own build pipeline instead.

## Website macros

[`zendoc.zensical_macros`](https://buckwem.github.io/zendoc-extensions/macros/)
provides a site-wide word count, the git-detected repository URL, chapter/
appendix numbering that continues across pages, and reference/acronym/
glossary spacing that matches `zendoc.pdf`'s own PDF output - as Jinja
variables/macros for Zensical's own macros plugin:

```toml
[project.markdown_extensions.zensical.extensions.macros]
modules = ["zendoc.zensical_macros"]
```

See the [docs](https://buckwem.github.io/zendoc-extensions/macros/) for the
full variable/macro list.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`zensical` is a core dependency, so `zensical serve` is available as soon as
`zendoc` is installed - no extra step needed to build the documentation
locally.

## License

MIT - see [LICENSE](LICENSE).
