{{ pdk_heading_counter_reset(page) }}

# Admonition pagination { #admonition-pagination }

These specimens test call-outs that must split, retain their visual ownership
and preserve nested structures when a page boundary interrupts them.

## Oversized admonition { #oversized-admonition }

!!! note "ADMONITION-OVERSIZED-TITLE"
    ADMONITION-OVERSIZED-START begins a call-out taller than one page.

    Oversized line 01 remains inside the call-out.<br>
    Oversized line 02 remains inside the call-out.<br>
    Oversized line 03 remains inside the call-out.<br>
    Oversized line 04 remains inside the call-out.<br>
    Oversized line 05 remains inside the call-out.<br>
    Oversized line 06 remains inside the call-out.<br>
    Oversized line 07 remains inside the call-out.<br>
    Oversized line 08 remains inside the call-out.<br>
    Oversized line 09 remains inside the call-out.<br>
    Oversized line 10 remains inside the call-out.<br>
    Oversized line 11 remains inside the call-out.<br>
    Oversized line 12 remains inside the call-out.<br>
    Oversized line 13 remains inside the call-out.<br>
    Oversized line 14 remains inside the call-out.<br>
    Oversized line 15 remains inside the call-out.<br>
    Oversized line 16 remains inside the call-out.<br>
    Oversized line 17 remains inside the call-out.<br>
    Oversized line 18 remains inside the call-out.<br>
    Oversized line 19 remains inside the call-out.<br>
    Oversized line 20 remains inside the call-out.<br>
    Oversized line 21 remains inside the call-out.<br>
    Oversized line 22 remains inside the call-out.<br>
    Oversized line 23 remains inside the call-out.<br>
    Oversized line 24 remains inside the call-out.<br>
    Oversized line 25 remains inside the call-out.<br>
    Oversized line 26 remains inside the call-out.<br>
    Oversized line 27 remains inside the call-out.<br>
    Oversized line 28 remains inside the call-out.<br>
    Oversized line 29 remains inside the call-out.<br>
    Oversized line 30 remains inside the call-out.<br>
    Oversized line 31 remains inside the call-out.<br>
    Oversized line 32 remains inside the call-out.<br>
    Oversized line 33 remains inside the call-out.<br>
    Oversized line 34 remains inside the call-out.<br>
    Oversized line 35 remains inside the call-out.<br>
    Oversized line 36 remains inside the call-out.<br>
    Oversized line 37 remains inside the call-out.<br>
    Oversized line 38 remains inside the call-out.<br>
    Oversized line 39 remains inside the call-out.<br>
    Oversized line 40 remains inside the call-out.<br>
    Oversized line 41 remains inside the call-out.<br>
    Oversized line 42 remains inside the call-out.<br>
    Oversized line 43 remains inside the call-out.<br>
    Oversized line 44 remains inside the call-out.<br>
    Oversized line 45 remains inside the call-out.<br>

    ADMONITION-OVERSIZED-END marks the complete call-out.

<div class="page-break"></div>

## Rich admonition near a boundary { #rich-admonition-boundary }

<blockquote class="catalogue-boundary-spacer catalogue-boundary-spacer--medium">
RICH-ADMONITION-LEAD fixes the available space before the call-out.<br>
Calibration 01.<br>Calibration 02.<br>Calibration 03.<br>Calibration 04.<br>
Calibration 05.<br>Calibration 06.<br>Calibration 07.<br>Calibration 08.<br>
Calibration 09.<br>Calibration 10.<br>Calibration 11.<br>Calibration 12.<br>
</blockquote>

!!! warning "RICH-ADMONITION-TITLE"
    RICH-ADMONITION-START begins the nested content.

    - A list item remains inside the warning.
    - A second item contains `inline code` and a nested list:
        1. First ordered child.
        2. Second ordered child.

    | RICH-TABLE-HEADER | Value |
    | --- | --- |
    | RICH-TABLE-ROW-1 | Retained |
    | RICH-TABLE-ROW-2 | Retained |

    ```console
    RICH-CODE-START
    pdk diag
    RICH-CODE-END
    ```

    RICH-ADMONITION-END completes the nested call-out.
