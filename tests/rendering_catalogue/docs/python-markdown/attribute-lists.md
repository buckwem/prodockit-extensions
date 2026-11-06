# Attribute lists { #attribute-lists }

Reference: [Zensical's built-in Python-Markdown extensions](https://zensical.org/docs/compatibility/markdown/python-markdown/)

## Source

```text
This paragraph has a stable identifier, class and review attribute.
{ #attribute-target .catalogue-accent data-review="attribute-list" }

[Review link](../){ .md-button #attribute-link }
```

## Rendered result

This paragraph has a stable identifier, class and review attribute.
{ #attribute-target .catalogue-accent data-review="attribute-list" }

[Review link](../){ .md-button #attribute-link }

The website must retain the identifier, class and custom attribute. The PDF
must retain both pieces of visible content and a working internal link.
