# Installation

## From PyPI

```bash
pip install zendoc
```

`zendoc` depends only on [`Markdown`](https://python-markdown.github.io/)
(>= 3.4) - no other runtime dependencies.

## Enabling an extension

Each zendoc extension is registered as a standard Python-Markdown extension
under the `markdown.extensions` entry point group, so it can be enabled by
name, the same way you'd enable a built-in extension like `toc` or a
`pymdownx` one:

```python
import markdown

html = markdown.markdown(text, extensions=["zendoc.headings", "zendoc.refs"])
```

Or in a `mkdocs.yml`/`zensical.toml`-style config:

```yaml
markdown_extensions:
  - zendoc.headings
  - zendoc.refs
```

```toml
[project.markdown_extensions.zendoc.headings]
[project.markdown_extensions.zendoc.refs]
```

See each extension's own page for its options and for how to share one
registry across multiple pages of a site build:

- [zendoc.headings](extensions/headings.md)
- [zendoc.refs](extensions/refs.md)

## Development install

```bash
git clone https://github.com/buckwem/zendoc-extension
cd zendoc-extension
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

To build these docs locally:

```bash
pip install -e ".[docs]"
zensical serve
```
