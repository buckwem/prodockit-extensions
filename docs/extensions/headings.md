# Headings

## Overview

`zendoc.headings` gives every heading in a document an `id` and a
hierarchical section number, and records both - along with the heading's
text and level - in a shared registry keyed by a document "source" name.

It exists to be a foundation other zendoc extensions build on:
[zendoc.refs](refs.md) resolves `\ref{id}` by looking an id up in exactly
this registry. You can also enable `zendoc.headings` on its own if you just
want ids/numbers on your headings without cross-references.

Numbering is per-document and hierarchical: an `h1` is a top-level counter
("1", "2", ...), an `h2` nests under the nearest preceding `h1` ("1.1",
"1.2", ...), and so on down through `h6`. Numbers are recomputed from
scratch on every conversion, so reordering headings always produces correct
numbers on the next build - there's no stored/stale numbering state.

## Example

```md
# Introduction

## Background

## Scope

# Method
```

produces (numbers shown for illustration - `zendoc.headings` doesn't render
numbers into the heading text itself, only into the registry; see
[zendoc.refs](refs.md) for rendering a number inline):

| Heading | id | number |
|---|---|---|
| Introduction | `introduction` | `1` |
| Background | `background` | `1.1` |
| Scope | `scope` | `1.2` |
| Method | `method` | `2` |

## Ids

An id comes from one of, in order of precedence:

1. An explicit id set via
   [`attr_list`](https://python-markdown.github.io/extensions/attr_list/),
   e.g. `# Introduction {: #custom-id }`.
2. Python-Markdown's own [`toc`](https://python-markdown.github.io/extensions/toc/)
   extension, which `zendoc.headings` enables automatically (with its
   defaults) if you haven't already enabled it yourself - so if you *have*
   configured `toc` (e.g. with `permalink: true`), that configuration is
   left untouched and reused.
3. A minimal built-in slugify fallback, used only if `toc` is somehow not
   registered at all (this should not normally happen, since
   `zendoc.headings` enables it).

## Unnumbered headings

A heading with an `unnumbered` class - e.g. a cover page or title slide -
still gets an id, but is skipped when computing section numbers, so it
doesn't consume a counter position:

```md
# Cover Page {: .unnumbered }

# Introduction
```

`Introduction` above is still numbered `1`, as if `Cover Page` weren't
there at all.

## Options

| Option | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | `""` | Identifier for the current document (e.g. its file path). Used to scope this document's entries in the registry, and to safely clear/replace them on a rebuild of the same document. |
| `registry` | `IdRegistry \| None` | a new `IdRegistry()` | Share one registry across multiple documents/conversions - see below. Passed as a constructor keyword, not a string-based config value (Python-Markdown's config system can't carry arbitrary Python objects safely). |

## Sharing a registry across a multi-page build

To resolve cross-page references, every page in a build needs to write into
- and read from - the *same* `IdRegistry` instance. Construct one and pass
it to every page's extension instance, along with that page's own `source`:

```python
import markdown
from zendoc.headings import HeadingsExtension
from zendoc.util import IdRegistry

registry = IdRegistry()

for path, text in pages:
    html = markdown.markdown(
        text,
        extensions=[HeadingsExtension(registry=registry, source=path)],
    )
```

A duplicate id registered from two *different* sources raises
`zendoc.util.DuplicateIdError` - re-converting the *same* source (e.g. a
live-reload dev server) is safe and expected; its previous entries are
cleared first.
