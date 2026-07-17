# Installation

[Download this page as PDF](installation.pdf){.web-only}

## From PyPI

```bash
pip install prodockit
```

`prodockit` depends on [`Markdown`](https://python-markdown.github.io/)
(>= 3.4), [`zensical`](https://zensical.org/), and
[`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) (>= 4.12,
used by `prodockit.pdf` - see [PDF generation](pdf.md)).

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
