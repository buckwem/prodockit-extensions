# Zensical rendering review catalogue

!!! warning "Maintainer review material"

    This is a test catalogue, not reader-facing Prodockit documentation. Its
    examples exist to make website and PDF rendering available for systematic
    review.

The catalogue is a separate Zensical project. It will provide one stable
specimen for every reviewed capability, describe the expected website and PDF
results, and make intentional differences between interactive and static
output explicit.

## Coverage status

Phase 1 established the inventory and coverage contract. Phases 2 and 3 add
base Markdown, built-in Python-Markdown and supported PyMdown specimens. Other
capabilities remain `planned` until their source, website expectation, PDF
expectation and nested-content decision have been implemented and tested.

| Inventory area | Entries | Implemented | Planned |
| --- | ---: | ---: | ---: |
| Built-in Python-Markdown extensions and material settings | 13 | 13 | 0 |
| Zensical-supported PyMdown extensions and material settings | 30 | 30 | 0 |
| Other extensions in the supported Prodockit configuration | 4 | 0 | 4 |
| Zensical authoring areas | 17 | 1 | 16 |
| Prodockit authoring extensions | 9 | 0 | 9 |
| **Total** | **73** | **44** | **29** |

The machine-readable source of truth is
[`catalogue.toml`](https://github.com/buckwem/prodockit-extensions/blob/main/tests/rendering_catalogue/catalogue.toml).

## Coverage rules

An implemented capability must identify a real specimen page and anchor and
define evidence for both the website and PDF. A waived capability must explain
why it cannot or should not be represented.

Every capability must also make a nested-content decision. Extensions and
authoring components start as candidates for the [nested-content
matrix](nested-content/index.md); configuration-only entries may inherit the
decision of their parent extension.

## Phase 2 review pages

- [Core Markdown](markdown/index.md)
- [Built-in Python-Markdown extensions](python-markdown/index.md)
- [Core and Python-Markdown nested content](nested-content/python-markdown.md)

## Phase 3 review pages

- [Supported PyMdown extensions](pymdown/index.md)
- [Nested PyMdown content](nested-content/pymdown.md)

## Reviewed upstream sources

- [Python-Markdown extensions](https://zensical.org/docs/compatibility/markdown/python-markdown/)
- [Python Markdown Extensions](https://zensical.org/docs/compatibility/markdown/python-markdown-extensions/)
- [Zensical authoring](https://zensical.org/docs/authoring/markdown/)
- [Prodockit authoring reference](https://prodockit.org/authoring/)
