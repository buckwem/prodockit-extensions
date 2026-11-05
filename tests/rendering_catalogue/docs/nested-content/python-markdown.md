# Core and Python-Markdown nesting { #nested-python-markdown }

This page records representative nested cases for the capabilities introduced
in Phase 2. The combinations are deliberately risk-based rather than a full
Cartesian product.

## Core Markdown in a blockquote { #nested-core-markdown }

> A quoted paragraph with **strong text**, `inline code` and a
> [relative link](../python-markdown/).
>
> 1. First quoted item
> 2. Second quoted item

## Extensions inside an admonition { #nested-admonition-content }

!!! info "Nested extension review"
    HTML appears here with its abbreviation expansion.

    A nested definition list
    :   A definition rendered inside the call-out.

    | Nested table | Result |
    | --- | --- |
    | Table parser | active |

    This paragraph has nested attributes.
    { #nested-attribute-target .nested-attribute data-review="nested-attribute" }

    <div class="nested-markdown-in-html" markdown>

    **Markdown in HTML** remains active inside the admonition.

    </div>

## Footnote reference in a list { #nested-footnote }

- This list item contains a nested footnote reference.[^nested-review]
- This item provides a stable sibling for visual comparison.

The table-of-contents extension is document-level, so the ledger records that
nested coverage is not independently meaningful for it. Its heading-depth and
permalink behaviour are reviewed on the standalone page.

*[HTML]: HyperText Markup Language

[^nested-review]: This footnote was referenced from inside a list item.
