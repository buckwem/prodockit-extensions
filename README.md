# zendoc

A family of [Python-Markdown](https://python-markdown.github.io/) extensions
for section cross-references and bibliography/citation handling, in the
spirit of [pymdown-extensions](https://facelessuser.github.io/pymdown-extensions/):
each extension is independent and enabled separately. Built for use with
[Zensical](https://zensical.org/) - configure it the same way as any other
Zensical/`pymdownx` Markdown extension, via `zensical.toml` - but since it's
a standard Python-Markdown extension, it works with any tool built on
Python-Markdown (MkDocs, etc.). Factored out of
[zendoc-template](https://github.com/buckwem/zendoc-template), a Zensical
project, so it can be installed and reused independently of that template.

> **Status:** early - `zendoc.headings` and `zendoc.refs` are implemented;
> citation handling isn't yet. See
> [zendoc-template#25](https://github.com/buckwem/zendoc-template/issues/25)
> for the tracking issue and scope.

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

```python
import markdown

html = markdown.markdown(text, extensions=["zendoc.headings", "zendoc.refs"])
```

```md
# Introduction {: #intro }

See \ref{intro} for background.
```

`\ref{intro}` resolves to a link reading `1` - the heading's current
section number - and stays correct if sections are reordered, since
numbering is recomputed on every conversion. See the
[docs](https://buckwem.github.io/zendoc-extension/) for options, multi-page
registry sharing, and full syntax details.

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
