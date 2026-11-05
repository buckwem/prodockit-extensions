# Markdown in HTML { #markdown-in-html }

Reference: [Zensical's built-in Python-Markdown extensions](https://zensical.org/docs/compatibility/markdown/python-markdown/)

## Source

```text
<div class="markdown-in-html-sample" markdown>

**Markdown remains active** inside this HTML container.

- First contained item
- Second contained item

</div>
```

## Rendered result

<div class="markdown-in-html-sample" markdown>

**Markdown remains active** inside this HTML container.

- First contained item
- Second contained item

</div>

The output must preserve the container while converting its Markdown children
to semantic HTML and corresponding PDF content.
