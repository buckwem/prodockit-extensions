{{ pdk_heading_counter_reset(page) }}

# Deep admonition combinations

These separate specimens make admonitions one level in a longer ownership
chain. Each marker must remain inside all of its surrounding containers.

## Tab, list, admonition and code {: #deep-tab-list-admonition-code }

=== "Deep review path"

    1. Start with an ordered item inside the content tab.

        !!! warning "Four-level warning"

            The warning belongs to the ordered item inside the tab.

            - Keep this list inside the warning.
            - Keep this command with the list:

                ```console
                pdk config --check
                ```

    2. Keep this sibling as the second item inside the same tab.

=== "Static review path"

    The PDF expands both tab bodies and preserves their source order.

**Markdown used**

````markdown
=== "Deep review path"

    1. Start with an ordered item inside the content tab.

        !!! warning "Four-level warning"

            The warning belongs to the ordered item inside the tab.

            - Keep this list inside the warning.
            - Keep this command with the list:

                ```console
                pdk config --check
                ```

    2. Keep this sibling as the second item inside the same tab.

=== "Static review path"

    The PDF expands both tab bodies and preserves their source order.
````

## Grid, admonition and numbered steps {: #deep-grid-admonition-steps }

<div class="grid cards" markdown>

-   :lucide-layers-3: **Deep procedure card**

    !!! example "Card-owned procedure"

        The numbered procedure belongs to the admonition and card.

        /// steps
        //// step | Inspect the nested structure

        - Confirm the step owns this list.
        - Confirm the admonition still owns the step.

        ////
        //// step | Run the nested check

        ```console
        pdk diag
        ```

        ////
        ///

-   :lucide-check-check: **Stable sibling card**

    This card confirms that closing the deep procedure did not consume its
    sibling.

</div>

**Markdown used**

````markdown
<div class="grid cards" markdown>

-   :lucide-layers-3: **Deep procedure card**

    !!! example "Card-owned procedure"

        The numbered procedure belongs to the admonition and card.

        /// steps
        //// step | Inspect the nested structure

        - Confirm the step owns this list.
        - Confirm the admonition still owns the step.

        ////
        //// step | Run the nested check

        ```console
        pdk diag
        ```

        ////
        ///

-   :lucide-check-check: **Stable sibling card**

    This card confirms that closing the deep procedure did not consume its
    sibling.

</div>
````
