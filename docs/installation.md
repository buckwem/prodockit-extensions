# Installation

## Requirements

**Python 3.10 or later.** Tested on 3.10, 3.11, 3.12 and 3.13; `pip` will
refuse to install on anything older rather than failing later at import.

Everything below is pulled in automatically by `pip install prodockit`,
except where noted:

| Requirement | Needed for |
| --- | --- |
| [`Markdown`](https://python-markdown.github.io/) (>= 3.4) | every extension |
| [`zensical`](https://zensical.org/) | Zensical integration and `prodockit.zensical_macros` |
| [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) (>= 4.12) | `prodockit.pdf` |
| \index{dependencies!`click`} (>= 8.0) | the `prodockit` command-line tool |
| \index{dependencies!`pypdf`} (>= 4.0) | `prodockit.pdf` |
| \index{dependencies!`pandoc`} **(external binary)** | `prodockit.pdf`, and `prodockit.bibliography` even without a PDF build |
| \index{dependencies!`weasyprint`} **(external binary)** | `prodockit.pdf` |
| \index{dependencies!`pymupdf`} | only the back-of-book index - `pip install prodockit[index]` |
| \index{dependencies!`mermaid-cli`}, `mathjax-full` **(external, Node)** | only Mermaid diagrams and TeX maths in the PDF |

The external tools aren't Python packages and aren't installed by `pip` -
see [PDF generation](pdf.md) for how `prodockit.pdf` locates them, and
[Limitations and workarounds](limitations.md) for why the Node ones are
needed at all. A build with neither Mermaid diagrams nor maths needs
neither of them.

## From PyPI

```bash
pip install prodockit
```

## Enabling an extension

Each prodockit extension is registered as a standard Python-Markdown extension
under the `markdown.extensions` entry point group, so it can be enabled by
name, the same way you'd enable a built-in extension like `toc` or a
`pymdownx` one:

```python
import markdown

html = markdown.markdown(
    text,
    extensions=["prodockit.headings", "prodockit.refs", "prodockit.citations", "prodockit.glossary"],
)
```

Or, for a [Zensical](https://zensical.org/) project, in `zensical.toml`
alongside the built-in and `pymdownx` extensions. Unlike `pymdownx`'s and
Zensical's own namespaces, Zensical doesn't hoist a nested
`prodockit.headings` table into that dotted extension name, so each one needs
a quoted key instead:

```toml
[project.markdown_extensions."prodockit.headings"]
[project.markdown_extensions."prodockit.refs"]
[project.markdown_extensions."prodockit.citations"]
[project.markdown_extensions."prodockit.glossary"]
```

See each extension's own page for its options and for how to share a
registry across multiple pages of a site build:

- [prodockit.headings](extensions/headings.md)
- [prodockit.refs](extensions/refs.md)
- [prodockit.citations](extensions/citations.md)
- [prodockit.glossary](extensions/glossary.md)

`prodockit.pdf` is different: it isn't a Python-Markdown extension (no
`markdown.extensions` entry point, nothing to add to `zensical.toml`) - it's
a plain function library for a separate PDF-generation build step. See
[PDF generation](pdf.md) for how it's used.

## Development install

```bash
git clone https://github.com/buckwem/prodockit-extensions
cd prodockit-extensions
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`zensical` is a core dependency, so `zensical serve` is available as soon as
`pip install -e ".[dev]"` finishes - no extra step needed to build these
docs locally.
