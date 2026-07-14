# zendoc

zendoc is a family of [Python-Markdown](https://python-markdown.github.io/)
extensions for section cross-references and bibliography/citation handling,
in the spirit of [pymdown-extensions](https://facelessuser.github.io/pymdown-extensions/):
each extension is independent and enabled separately, so you only pay for
what you use.

zendoc is built for use with [Zensical](https://zensical.org/) - enable it
in `zensical.toml` the same way as any other Zensical or `pymdownx`
extension (see [Installation](installation.md)).

## Extensions

| Extension | Description |
|---|---|
| [zendoc.headings](extensions/headings.md) | Gives every heading an id and a hierarchical section number ("1", "1.1", "1.2", "2", ...). |
| [zendoc.refs](extensions/refs.md) | `\ref{id}` section cross-references, resolving to the target's current number - similar in spirit to LaTeX's `\ref`. |
| [zendoc.citations](extensions/citations.md) | Define a source once, cite it by key anywhere with `\cite{id}` - auto-generates the bracketed, linked citation text. |
| [zendoc.glossary](extensions/glossary.md) | Define a term once (an acronym expansion, a glossary entry), insert it by id anywhere with `\gls{id}` - similar in spirit to LaTeX's `glossaries` package. |

## Quick example

```python
import markdown

html = markdown.markdown(
    """
# Introduction

See \\ref{background} for context.\\cite{skou2023}

## Background

...

Skoulikari, A. (2023) *Learning Git*.
{: #skou2023 data-cite-text="Skoulikari, 2023" }
""",
    extensions=["attr_list", "zendoc.headings", "zendoc.refs", "zendoc.citations"],
)
```

`\ref{background}` resolves to `1.1` - the current section number of the
heading it points to - and `\cite{skou2023}` resolves to `[Skoulikari,
2023]`, linked to that source's own paragraph. Both stay correct if
headings/sources are reordered, since resolution happens fresh on every
conversion.

## Status

Early, but functional. `zendoc.headings`, `zendoc.refs`, `zendoc.citations`,
and `zendoc.glossary` are implemented and tested; auto-generating a full
references list from structured bibliographic data is not yet built (see
[zendoc.citations](extensions/citations.md#what-this-doesnt-do-yet)). See
the [Release Notes](about/changelog.md) for what's landed so far.
