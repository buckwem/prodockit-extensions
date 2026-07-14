# zendoc

zendoc is a family of [Python-Markdown](https://python-markdown.github.io/)
extensions for section cross-references and bibliography/citation handling,
in the spirit of [pymdown-extensions](https://facelessuser.github.io/pymdown-extensions/):
each extension is independent and enabled separately, so you only pay for
what you use.

zendoc is built for use with [Zensical](https://zensical.org/) - enable it
in `zensical.toml` the same way as any other Zensical or `pymdownx`
extension (see [Installation](installation.md)). It's a standard
Python-Markdown extension though, with no Zensical-specific dependency, so
it also works with MkDocs or any other tool built on Python-Markdown.

zendoc was factored out of
[zendoc-template](https://github.com/buckwem/zendoc-template), a Zensical
project, so it can be installed and reused independently of that template -
see [zendoc-template#25](https://github.com/buckwem/zendoc-template/issues/25)
for the tracking issue and original motivation.

## Extensions

| Extension | Description |
|---|---|
| [zendoc.headings](extensions/headings.md) | Gives every heading an id and a hierarchical section number ("1", "1.1", "1.2", "2", ...). |
| [zendoc.refs](extensions/refs.md) | `\ref{id}` section cross-references, resolving to the target's current number - similar in spirit to LaTeX's `\ref`. |

Bibliography/citation handling is planned but not implemented yet.

## Quick example

```python
import markdown

html = markdown.markdown(
    """
# Introduction

See \\ref{background} for context.

## Background

...
""",
    extensions=["zendoc.headings", "zendoc.refs"],
)
```

`\ref{background}` resolves to `1.1` - the current section number of the
heading it points to - and stays correct if headings are reordered, because
numbering is recomputed fresh on every conversion.

## Status

Early. `zendoc.headings` and `zendoc.refs` are implemented and tested;
citation-key management is not yet built. See the
[Release Notes](about/changelog.md) for what's landed so far.
