# zendoc

A [Python-Markdown](https://python-markdown.github.io/) extension providing
section cross-references and bibliography/citation handling, factored out of
[zendoc-template](https://github.com/buckwem/zendoc-template) so it can be
installed and reused independently of that template.

> **Status:** early - section cross-references are implemented; citation
> handling isn't yet. See
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

### Section cross-references

Every heading gets an id and a hierarchical section number (h1 → `1`, a
nested h2 → `1.1`, and so on), tracked in a shared registry. Reference one
with `\ref{id}` - similar in spirit to LaTeX's `\ref` - and it resolves to
the target's *current* number, so it stays correct if sections are
reordered:

```markdown
# Introduction {: #intro }

See \ref{intro} for background.
```

renders `\ref{intro}` as a link to `#intro` reading `1`. A heading with no
explicit id gets one derived from its text (reusing Python-Markdown's own
`toc` extension, enabled automatically if you haven't already). A reference
to an unknown id, or to a heading marked `unnumbered` (`{: .unnumbered }`),
renders `??` (configurable via the `unresolved` option) rather than
resolving to nothing.

To share one registry - and therefore resolve cross-page references -
across multiple documents in a site build, construct the extension with an
explicit `registry` and a per-document `source`:

```python
from zendoc import IdRegistry
from zendoc.extension import ZendocExtension

registry = IdRegistry()
for path, text in pages:
    html = markdown.markdown(
        text, extensions=[ZendocExtension(registry=registry, source=path)]
    )
```

A reference to a heading in a page that hasn't been converted yet in the
current build resolves to `??`, the same way an undefined LaTeX `\ref` does
until a later compilation pass.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT - see [LICENSE](LICENSE).
