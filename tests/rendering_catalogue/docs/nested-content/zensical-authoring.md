# Nested Zensical authoring

These representative cases confirm that Phase 4 authoring components remain
intact inside common containers. Phase 5 owns the broader risk-based nested
content matrix.

## Nested configured extensions {: #nested-configured-extensions }

!!! note "Configured extension output"

    **Strong text with _nested emphasis_ remains semantic.**

    https://example.com/nested-phase-four

    The configured macro still resolves here: {{ catalogue_phase }}.

## Nested button and tooltip {: #nested-button-tooltip }

!!! info "Interactive links inside a call-out"

    [Nested review button](#nested-layout "Nested tooltip text"){ .md-button }

## Nested layout and image {: #nested-layout }

<div class="grid cards" markdown>

- :lucide-image: **Nested image**

  ![Nested website and PDF review flow](../assets/core-sample.svg){ loading=lazy width="240" }

- :lucide-layout-grid: **Nested card**

  The grid keeps this text with its card in both outputs.

</div>

## Nested diagram {: #nested-diagram }

!!! example "Mermaid inside an admonition"

    ```mermaid
    flowchart LR
        N[Nested source] --> O[Rendered output]
    ```

## Nested table cells {: #nested-table-cells }

| Cell case | Embedded content |
| --- | --- |
| Inline elements | [Link](#nested-table-cells), `code`, HTML and :lucide-table-2: |
| Mathematics | $x^2 + y^2 = z^2$ |

*[HTML]: HyperText Markup Language
