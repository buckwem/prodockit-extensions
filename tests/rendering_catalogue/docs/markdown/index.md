# Core Markdown { #core-markdown }

Reference: [Zensical Markdown authoring](https://zensical.org/docs/authoring/markdown/)

Related authoring reference: [Zensical lists](https://zensical.org/docs/authoring/lists/).

This page is the baseline for Markdown that does not require an optional
extension. It deliberately combines inline and block content so the website
and PDF can be reviewed together.

## Inline content { #core-inline-content }

### Source

```text
Plain text with **strong emphasis**, *emphasis*, `inline code`,
[a relative link](../python-markdown/) and an escaped \*asterisk\*.
```

### Rendered result

Plain text with **strong emphasis**, *emphasis*, `inline code`,
[a relative link](../python-markdown/) and an escaped \*asterisk\*.

## Blocks { #core-blocks }

### Source

```text
> A blockquote containing **formatted text**.

- First unordered item
  - Nested unordered item
- Second unordered item

Ordered list:

1. First ordered item
2. Second ordered item

---
```

### Rendered result

> A blockquote containing **formatted text**.

- First unordered item
    - Nested unordered item
- Second unordered item

Ordered list:

1. First ordered item
2. Second ordered item

---

## Code and image { #core-code-and-image }

```python
def catalogue_status(implemented: int, total: int) -> str:
    return f"{implemented}/{total} capabilities implemented"
```

![Two panels showing website output flowing to PDF output](../assets/core-sample.svg)

The SVG must remain visible and retain its alternative text in the website.
The corresponding graphic and surrounding text must also reach the PDF.
