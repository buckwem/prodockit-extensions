{{ pdk_heading_counter_reset(page) }}

# Complex indentation combinations

These specimens deliberately combine containers that each introduce another
indentation level. The short marker sentences make lost, duplicated or
reordered content visible in both the website and PDF.

## List with an admonition, nested list and code {: #complex-list-admonition }

1. Prepare the nested example.

    !!! note "List-owned call-out"

        The call-out belongs to the first ordered item.

        - Confirm the nested unordered item remains inside the call-out.
        - Run the indented example:

            ```console
            pdk diag
            zensical build --clean --strict
            ```

2. Confirm this sibling remains the second ordered item.

**Markdown used**

````markdown
1. Prepare the nested example.

    !!! note "List-owned call-out"

        The call-out belongs to the first ordered item.

        - Confirm the nested unordered item remains inside the call-out.
        - Run the indented example:

            ```console
            pdk diag
            zensical build --clean --strict
            ```

2. Confirm this sibling remains the second ordered item.
````

## Content tabs containing a grid {: #complex-tabs-grid }

=== "Website review"

    <div class="grid cards" markdown>

    -   :lucide-list-checks: **List card**

        1. Check the card remains inside the selected tab.
        2. Check both numbered items remain inside the card.

        !!! tip "Card-owned call-out"

            This call-out is nested inside a grid card inside a content tab.

    -   :lucide-code-xml: **Code card**

        ```yaml
        project:
          site_name: Nested catalogue
        ```

    </div>

=== "PDF review"

    - Both tab labels and both tab bodies must remain visible.
    - The grid cards must flatten into a clear reading order.

**Markdown used**

````markdown
=== "Website review"

    <div class="grid cards" markdown>

    -   :lucide-list-checks: **List card**

        1. Check the card remains inside the selected tab.
        2. Check both numbered items remain inside the card.

        !!! tip "Card-owned call-out"

            This call-out is nested inside a grid card inside a content tab.

    -   :lucide-code-xml: **Code card**

        ```yaml
        project:
          site_name: Nested catalogue
        ```

    </div>

=== "PDF review"

    - Both tab labels and both tab bodies must remain visible.
    - The grid cards must flatten into a clear reading order.
````

## Grid containing lists and admonitions {: #complex-grid-list-admonition }

<div class="grid cards" markdown>

-   :lucide-list-ordered: **Ordered-list card**

    1. First card item.
    2. Second card item.

        !!! warning "List-owned warning"

            This warning belongs to the second ordered item inside the card.

-   :lucide-list-tree: **Multi-level list card**

    - Outer unordered item
        1. Nested ordered item
            - Third-level unordered item
    - Stable outer sibling

</div>

**Markdown used**

````markdown
<div class="grid cards" markdown>

-   :lucide-list-ordered: **Ordered-list card**

    1. First card item.
    2. Second card item.

        !!! warning "List-owned warning"

            This warning belongs to the second ordered item inside the card.

-   :lucide-list-tree: **Multi-level list card**

    - Outer unordered item
        1. Nested ordered item
            - Third-level unordered item
    - Stable outer sibling

</div>
````

## Numbered steps containing tabs and a grid {: #complex-steps-tabs-grid }

/// steps
    attrs: {class: complex-steps-paginated}

//// step | Review tabbed choices

=== "Website"

    - Keep this list inside the first tab.

    !!! info "Tab-owned call-out"

        This call-out is inside a tab inside a numbered step.

=== "PDF"

    1. Flatten the first tab in source order.
    2. Flatten this second tab immediately afterwards.

////
//// step | Review the card layout

<div class="grid cards" markdown>

-   **Diagnostic card**

    ```console
    pdk diag
    ```

-   **Build card**

    !!! success "Final nested result"

        The final call-out remains inside the second card and second step.

</div>

////
///

<div class="catalogue-break-before"></div>

**Markdown used**

````markdown
/// steps
    attrs: {class: complex-steps-paginated}

//// step | Review tabbed choices

=== "Website"

    - Keep this list inside the first tab.

    !!! info "Tab-owned call-out"

        This call-out is inside a tab inside a numbered step.

=== "PDF"

    1. Flatten the first tab in source order.
    2. Flatten this second tab immediately afterwards.

////
//// step | Review the card layout

<div class="grid cards" markdown>

-   **Diagnostic card**

    ```console
    pdk diag
    ```

-   **Build card**

    !!! success "Final nested result"

        The final call-out remains inside the second card and second step.

</div>

////
///
````
