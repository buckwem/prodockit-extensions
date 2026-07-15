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
extension, via `zensical.toml`. `zendoc.pdf` is a plain function library
instead, since a PDF build pipeline isn't a Markdown syntax extension.

> **Status:** early, but functional - `zendoc.headings`, `zendoc.refs`,
> `zendoc.citations`, `zendoc.glossary`, and `zendoc.pdf` are implemented
> and tested.

**[Full documentation](https://buckwem.github.io/zendoc-extension/)**

## Installation

```bash
pip install zendoc
```

## Extensions

| Extension | Description |
|---|---|
| [`zendoc.headings`](https://buckwem.github.io/zendoc-extension/extensions/headings/) | Gives every heading an id and a hierarchical section number ("1", "1.1", "1.2", "2", ...). |
| [`zendoc.refs`](https://buckwem.github.io/zendoc-extension/extensions/refs/) | `\ref{id}` section cross-references, resolving to the target's current number - similar in spirit to LaTeX's `\ref`. |
| [`zendoc.citations`](https://buckwem.github.io/zendoc-extension/extensions/citations/) | Define a source once, cite it by key anywhere with `\cite{id}` - auto-generates the bracketed, linked citation text. |
| [`zendoc.glossary`](https://buckwem.github.io/zendoc-extension/extensions/glossary/) | Define a term once (an acronym expansion, a glossary entry), insert it by id anywhere with `\gls{id}` - similar in spirit to LaTeX's `glossaries` package. |

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
[docs](https://buckwem.github.io/zendoc-extension/) for options, multi-page
registry sharing, and full syntax details.

## PDF generation

[`zendoc.pdf`](https://buckwem.github.io/zendoc-extension/pdf/) is a
Pandoc/WeasyPrint pipeline for building a standalone PDF from
Zensical-rendered HTML - not a Python-Markdown extension, a plain function
library: HTML fixups for Pandoc's own reader/writer quirks
(`zendoc.pdf.html`), a Lua filter for chapter numbering and caption
ordering (`zendoc.pdf.lua`), and the compiled CSS a paginated PDF needs on
top of a project's own website stylesheet (`zendoc.pdf.css`), plus
standalone helpers for admonition icons and Mermaid diagram pre-rendering.
See the [docs](https://buckwem.github.io/zendoc-extension/pdf/) for the
full pipeline and each module's own reference.

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
