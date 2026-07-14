# zendoc

A [Python-Markdown](https://python-markdown.github.io/) extension providing
section cross-references and bibliography/citation handling, factored out of
[zendoc-template](https://github.com/buckwem/zendoc-template) so it can be
installed and reused independently of that template.

> **Status:** early scaffolding only. No cross-reference or citation logic
> has been ported over yet - see
> [zendoc-template#25](https://github.com/buckwem/zendoc-template/issues/25)
> for the tracking issue and scope.

## Installation

```bash
pip install zendoc
```

## Usage

Enable it like any other Python-Markdown extension:

```python
import markdown

html = markdown.markdown(text, extensions=["zendoc"])
```

Or in a `zensical.toml`/`mkdocs.yml`-style config:

```toml
[project.markdown_extensions.zendoc]
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT - see [LICENSE](LICENSE).
