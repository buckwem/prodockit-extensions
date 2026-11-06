{{ pdk_heading_counter_reset(page) }}

# Nested Prodockit content

This page supplies representative container interactions for the Prodockit
extensions implemented in Phase 4. Phase 5 can extend the matrix when new
high-risk combinations are brought into scope.

## Nested heading and references {: #nested-prodockit-references }

!!! info "Numbered content inside a call-out"

    ### Nested review target {: #nested-review-target }

    The nested heading is numbered and can be cited as
    \ref{nested-review-target}.

## Nested citation and glossary {: #nested-prodockit-citation-glossary }

> A nested quotation can cite \citeref{nested-source} and use \gls{api}.
>
> Nested Maintainers (2026) *Container interactions*.
> {: #nested-source .reference data-cite-text="Nested Maintainers, 2026" }
>
> API
> : Application Programming Interface
> {: #api .glossary data-term="API" }

## Nested table {: #nested-prodockit-table }

!!! example "Captioned table in an admonition"

    | Case | State |
    | --- | --- |
    | Nested table | Reviewable |
    /// table-caption | <
        attrs: {id: tab-nested-prodockit}

    Nested Prodockit table
    ///

## Nested directory tree {: #nested-prodockit-tree }

!!! note "Tree in an admonition"

    /// tree
    docs/
      nested-content/
        prodockit.md
    ///

## Nested numbered steps {: #nested-prodockit-steps }

!!! tip "Steps in an admonition"

    /// steps
    //// step | Inspect the website

    Confirm the nested container remains intact.

    ////
    //// step | Inspect the PDF

    Confirm the same content remains in reading order.

    ////
    ///

## Nested index marker {: #nested-prodockit-index }

- This list item registers \index{nested content!Prodockit} for the generated
  index while retaining the surrounding list structure.
