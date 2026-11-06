# Zensical rendering review catalogue {: .unnumbered }

!!! warning "Maintainer review material"

    This is a test catalogue, not reader-facing Prodockit documentation. Its
    examples exist to make website and PDF rendering available for systematic
    review.

The catalogue is a separate Zensical project. It will provide one stable
specimen for every reviewed capability, describe the expected website and PDF
results, and make intentional differences between interactive and static
output explicit.

## Coverage status

Phase 1 established the inventory and coverage contract. Phases 2 and 3 added
base Markdown, built-in Python-Markdown and supported PyMdown specimens. Phase
4 adds the configured integrations, Zensical authoring surface and Prodockit
extensions. Directives is explicitly waived until its early-access Zensical
Spark wheel is publicly supported. Phase 5 adds risk-based nested content and
controlled page-boundary coverage. Phase 6 collects the website, complete and
per-page PDFs, thumbnail contact sheet and coverage report into one review
bundle.

| Inventory area | Entries | Implemented | Waived | Planned |
| --- | ---: | ---: | ---: | ---: |
| Built-in Python-Markdown extensions and material settings | 13 | 13 | 0 | 0 |
| Zensical-supported PyMdown extensions and material settings | 30 | 30 | 0 | 0 |
| Other extensions in the supported Prodockit configuration | 4 | 4 | 0 | 0 |
| Zensical authoring areas | 17 | 16 | 1 | 0 |
| Prodockit authoring extensions | 9 | 9 | 0 | 0 |
| **Total** | **73** | **72** | **1** | **0** |

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

## Phase 4 review pages

- [Zensical authoring](zensical-authoring/index.md)
- [Prodockit integrations](prodockit/index.md)
- [Nested Zensical authoring](nested-content/zensical-authoring.md)
- [Nested Prodockit content](nested-content/prodockit.md)

## Phase 5 review pages

- [Nested-content matrix](nested-content/index.md)
- [Forced and kept content](page-breaks/forced-and-kept.md)
- [Flow and overflow](page-breaks/flow-and-overflow.md)

## Phase 6 review outputs

The review bundle adds these generated outputs to this hidden catalogue:

- [complete catalogue PDF](rendering-catalogue.pdf)
- [PDF thumbnail contact sheet](contact-sheet.html)
- [capability coverage report](coverage-report.html)

Each catalogue page also has a matching PDF under `page-pdfs/`. The coverage
report links every capability to its source, website specimen, complete PDF,
per-page PDF and automated test status.

## Reviewed upstream sources

- [Python-Markdown extensions](https://zensical.org/docs/compatibility/markdown/python-markdown/)
- [Python Markdown Extensions](https://zensical.org/docs/compatibility/markdown/python-markdown-extensions/)
- [Zensical authoring](https://zensical.org/docs/authoring/markdown/)
- [Prodockit authoring reference](https://prodockit.org/authoring/)
