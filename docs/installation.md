# Installation

## From PyPI

```bash
pip install zendoc
```

`zendoc` depends on [`Markdown`](https://python-markdown.github.io/)
(>= 3.4) and [`zensical`](https://zensical.org/).

## Enabling an extension

Each zendoc extension is registered as a standard Python-Markdown extension
under the `markdown.extensions` entry point group, so it can be enabled by
name, the same way you'd enable a built-in extension like `toc` or a
`pymdownx` one:

```python
import markdown

html = markdown.markdown(
    text,
    extensions=["zendoc.headings", "zendoc.refs", "zendoc.citations", "zendoc.glossary"],
)
```

Or, for a [Zensical](https://zensical.org/) project, in `zensical.toml`
alongside the built-in and `pymdownx` extensions. Unlike `pymdownx`'s and
Zensical's own namespaces, Zensical doesn't hoist a nested
`zendoc.headings` table into that dotted extension name, so each one needs
a quoted key instead:

```toml
[project.markdown_extensions."zendoc.headings"]
[project.markdown_extensions."zendoc.refs"]
[project.markdown_extensions."zendoc.citations"]
[project.markdown_extensions."zendoc.glossary"]
```

See each extension's own page for its options and for how to share a
registry across multiple pages of a site build:

- [zendoc.headings](extensions/headings.md)
- [zendoc.refs](extensions/refs.md)
- [zendoc.citations](extensions/citations.md)
- [zendoc.glossary](extensions/glossary.md)

## Development install

```bash
git clone https://github.com/buckwem/zendoc-extension
cd zendoc-extension
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`zensical` is a core dependency, so `zensical serve` is available as soon as
`pip install -e ".[dev]"` finishes - no extra step needed to build these
docs locally.
