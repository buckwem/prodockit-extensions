# Nested content

Nested rendering is a dedicated coverage area. It grows whenever a new
capability is brought into scope rather than remaining a fixed regression
fixture. The matrix is deliberately risk-based, not a Cartesian product.

## Reviewed matrix {: #nested-matrix }

| Container or interaction | Embedded capabilities | Canonical specimen |
| --- | --- | --- |
| Blockquotes | Strong text, inline code, links, ordered lists, captions, snippets, citations and glossary terms | [Core and Python-Markdown](python-markdown.md#nested-core-markdown), [PyMdown](pymdown.md#nested-caption), [Prodockit](prodockit.md#nested-prodockit-citation-glossary) |
| Ordered, unordered, nested and task lists | Details, footnotes, task states, index terms, admonitions and code blocks | [Core and Python-Markdown](python-markdown.md#nested-list-combinations), [PyMdown](pymdown.md#nested-details), [Prodockit](prodockit.md#nested-prodockit-index), [Complex combinations](complex-combinations.md#complex-list-admonition) |
| Admonitions | Abbreviations, definitions, tables, Markdown in HTML, mathematics, formatting, icons, keys, code, custom fences, buttons, tooltips, Mermaid, headings, references, trees, tabs, grids, lists and steps | [Python-Markdown](python-markdown.md#nested-admonition-content), [PyMdown](pymdown.md#nested-math-and-formatting), [Zensical authoring](zensical-authoring.md#nested-button-tooltip), [Prodockit](prodockit.md#nested-prodockit-references), [Deep admonitions](deep-admonitions.md) |
| Details and content tabs | Prose, highlighted blocks, inline code, grids, lists and admonitions | [PyMdown details](pymdown.md#nested-details), [PyMdown tabs](pymdown.md#nested-tabs), [Tabs containing a grid](complex-combinations.md#complex-tabs-grid) |
| Grids and images | Icons, images, links, card prose, multi-level lists, admonitions and code | [Zensical authoring](zensical-authoring.md#nested-layout), [Grid combinations](complex-combinations.md#complex-grid-list-admonition) |
| Numbered steps | Content tabs, lists, admonitions, grids and code blocks | [Steps containing tabs and a grid](complex-combinations.md#complex-steps-tabs-grid) |
| Markdown in HTML | Strong text inside retained HTML containers | [Python-Markdown](python-markdown.md#nested-admonition-content) |
| Tables and cells | Links, code, abbreviations, mathematics and icons | [Zensical authoring](zensical-authoring.md#nested-table-cells) |
| Captions and figures | Images and tables inside blockquotes or admonitions | [PyMdown](pymdown.md#nested-caption), [Prodockit](prodockit.md#nested-prodockit-table) |
| Footnotes | References originating inside list items | [Python-Markdown](python-markdown.md#nested-footnote) |
| Directives | No public specimen | [Waiver](../zensical-authoring/index.md#directives-waiver) while the separate Zensical Spark wheel is not publicly supported |

Every capability in `catalogue.toml` must require one of these appropriate
nested specimens or record why nesting has no independent meaning.
