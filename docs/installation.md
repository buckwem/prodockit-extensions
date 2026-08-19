# Installation

## Requirements

**Python 3.10 or later.** Tested on 3.10, 3.11, 3.12 and 3.13; `pip` will
refuse to install on anything older rather than failing later at import.

Everything below is pulled in automatically by `pip install prodockit`,
except where noted:

| Requirement | Needed for |
| --- | --- |
| [`Markdown`](https://python-markdown.github.io/) (>= 3.10.3) | every extension |
| [`zensical`](https://zensical.org/) (>= 0.0.55) | Zensical integration and `prodockit.zensical_macros` |
| \index{dependencies!`pymdown-extensions`} (>= 11.0.1) | `prodockit.pdf` matches the class shapes it emits |
| [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) (>= 4.12) | `prodockit.pdf` |
| \index{dependencies!`click`} (>= 8.0) | the `prodockit` command-line tool |
| \index{dependencies!`pypdf`} (>= 4.0) | `prodockit.pdf` |
| \index{dependencies!`tomli`} (>= 2.0) | reading a template manifest on Python 3.10, where `tomllib` does not exist yet |
| \index{dependencies!`pymupdf`} (>= 1.24) | only the back-of-book index - `pip install prodockit[index]` |

The floors above are the ones declared in `pyproject.toml`, and a test
keeps this table in step with them - the two had drifted apart, with
`Markdown` recorded here as >= 3.4 long after the real floor moved to
3.10.3 (prodockit-extensions#372).

### Not installed by pip {: #installation-external }

These are the ones `pip install prodockit` does **not** bring, and they
differ in kind:

| Requirement | Needed for |
| --- | --- |
| \index{dependencies!`weasyprint`} (>= 69) | `prodockit.pdf`. A Python package, but not a dependency of prodockit - install it yourself. `prodockit.pdf` runs its command-line rather than importing it |
| \index{dependencies!`pandoc`} (>= 3, builds pin 3.10.1) | `prodockit.pdf`, and `prodockit.bibliography` even without a PDF build. Genuinely not a Python package - there is nothing for `pip` to install |
| \index{dependencies!`mermaid-cli`}, `mathjax-full` (Node >= 22) | only Mermaid diagrams and TeX maths in the PDF |
| Chrome or Chromium | only Mermaid diagrams - `mermaid-cli` renders them through a headless browser |
| A citation style (`.csl`) | only `prodockit.bibliography`. Fetched per build, not vendored - see below |

The citation style is a download rather than an install. Pandoc
resolves `harvard-cite-them-right.csl` from the directory it runs in, and
every CI script here fetches it immediately before building:

```bash
curl -fsSL -o harvard-cite-them-right.csl "https://www.zotero.org/styles/harvard-cite-them-right"
```

It is deliberately **not** committed: it is third-party content with its
own licence and its own release cadence, and a vendored copy would go
stale silently while every build kept succeeding. `prodockit bootstrap`
fetches it for you, and `.gitignore` keeps a local copy out of commits.

`weasyprint` is worth separating from `pandoc` rather than filing both as
"external binaries": one is a `pip install` away and the other is not,
and a reader who treats them alike goes looking for a package that does
not exist, or misses one that does.

Pandoc is version-sensitive in a way that changes output rather than
breaking the build: a major version below 3 renders code blocks as
justified prose, and the builds pin an exact release because two 3.x
versions have already disagreed about the same source. `prodockit
bootstrap` installs the pinned version where a package manager allows it
and tells you when your local pandoc differs - see
[Pinning build inputs](devcons/pinning-drift.md).

See [PDF generation](pdf.md) for how `prodockit.pdf` locates these, and
[Limitations and workarounds](devcons/limitations.md) for why the Node
ones are needed at all. A build with neither Mermaid diagrams nor maths
needs neither of them, and no browser.

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
