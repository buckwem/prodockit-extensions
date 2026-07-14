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

> **Status:** early, but functional - `zendoc.headings`, `zendoc.refs`, and
> `zendoc.citations` are implemented and tested. See
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
| [`zendoc.citations`](https://buckwem.github.io/zendoc-extension/extensions/citations/) | Define a source once, cite it by key anywhere with `\cite{id}` - auto-generates the bracketed, linked citation text. |

```python
import markdown

html = markdown.markdown(
    text, extensions=["attr_list", "zendoc.headings", "zendoc.refs", "zendoc.citations"]
)
```

```md
# Introduction {: #intro }

See \ref{intro} for background.\cite{skou2023}

Skoulikari, A. (2023) *Learning Git*.
{: #skou2023 data-cite-text="Skoulikari, 2023" }
```

`\ref{intro}` resolves to a link reading `1` - the heading's current
section number - and `\cite{skou2023}` resolves to `[Skoulikari, 2023]`,
linked to that source. Both stay correct if content is reordered, since
resolution happens fresh on every conversion. See the
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
