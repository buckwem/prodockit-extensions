# Code highlighting

Reference: [Zensical's supported Python Markdown Extensions](https://zensical.org/docs/compatibility/markdown/python-markdown-extensions/)

Authoring reference: [Zensical code blocks](https://zensical.org/docs/authoring/code-blocks/)

## Highlight { #highlight }

### Configuration source

```toml
[project.markdown_extensions.pymdownx.highlight]
pygments_lang_class = true
auto_title = true
linenums = true
linenums_style = "pymdownx-inline"
anchor_linenums = true
line_spans = "__span"
```

### Source

````text
```python
def phase_three() -> str:
    return "ready"
```
````

### Rendered result

```python
def phase_three() -> str:
    return "ready"
```

## Language class { #highlight-language-class }

The highlighted container must expose its Python language class.

## Automatic title { #highlight-auto-title }

The code block must display the automatic **Python** title.

## Line numbers { #highlight-line-numbers }

Both lines must have visible line numbers.

## Line-number style { #highlight-line-number-style }

The `pymdownx-inline` style must keep line numbers separate from copied code.

## Anchored line numbers { #highlight-anchor-line-numbers }

Each line number must provide a stable internal link.

## Line spans { #highlight-line-spans }

Each source line must be wrapped by an identifier beginning with `__span`.

## InlineHilite { #inlinehilite }

### Source

```text
Inline Python: `#!python print("ready")`.
```

### Rendered result

Inline Python: `#!python print("ready")`.

The PDF keeps the highlighted code and title but flattens browser-only line
anchors into static line numbers.
