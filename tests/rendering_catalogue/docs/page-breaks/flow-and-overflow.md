{{ pdk_heading_counter_reset(page) }}

# Flow and overflow

These cases exercise content that may split, repeat or reflow at page
boundaries. Named markers make every expected outcome inspectable.

## Long code block {: #long-code-block }

A long fenced block may split across pages; neither end may vanish.

```text
PB-CODE-FIRST = "first boundary line"
catalogue_line_02 = "deterministic code row 02"
catalogue_line_03 = "deterministic code row 03"
catalogue_line_04 = "deterministic code row 04"
catalogue_line_05 = "deterministic code row 05"
catalogue_line_06 = "deterministic code row 06"
catalogue_line_07 = "deterministic code row 07"
catalogue_line_08 = "deterministic code row 08"
catalogue_line_09 = "deterministic code row 09"
catalogue_line_10 = "deterministic code row 10"
catalogue_line_11 = "deterministic code row 11"
catalogue_line_12 = "deterministic code row 12"
catalogue_line_13 = "deterministic code row 13"
catalogue_line_14 = "deterministic code row 14"
catalogue_line_15 = "deterministic code row 15"
catalogue_line_16 = "deterministic code row 16"
catalogue_line_17 = "deterministic code row 17"
catalogue_line_18 = "deterministic code row 18"
catalogue_line_19 = "deterministic code row 19"
catalogue_line_20 = "deterministic code row 20"
catalogue_line_21 = "deterministic code row 21"
catalogue_line_22 = "deterministic code row 22"
catalogue_line_23 = "deterministic code row 23"
catalogue_line_24 = "deterministic code row 24"
catalogue_line_25 = "deterministic code row 25"
catalogue_line_26 = "deterministic code row 26"
catalogue_line_27 = "deterministic code row 27"
catalogue_line_28 = "deterministic code row 28"
catalogue_line_29 = "deterministic code row 29"
catalogue_line_30 = "deterministic code row 30"
catalogue_line_31 = "deterministic code row 31"
catalogue_line_32 = "deterministic code row 32"
catalogue_line_33 = "deterministic code row 33"
catalogue_line_34 = "deterministic code row 34"
catalogue_line_35 = "deterministic code row 35"
catalogue_line_36 = "deterministic code row 36"
catalogue_line_37 = "deterministic code row 37"
catalogue_line_38 = "deterministic code row 38"
catalogue_line_39 = "deterministic code row 39"
catalogue_line_40 = "deterministic code row 40"
catalogue_line_41 = "deterministic code row 41"
catalogue_line_42 = "deterministic code row 42"
catalogue_line_43 = "deterministic code row 43"
catalogue_line_44 = "deterministic code row 44"
catalogue_line_45 = "deterministic code row 45"
catalogue_line_46 = "deterministic code row 46"
catalogue_line_47 = "deterministic code row 47"
catalogue_line_48 = "deterministic code row 48"
catalogue_line_49 = "deterministic code row 49"
catalogue_line_50 = "deterministic code row 50"
catalogue_line_51 = "deterministic code row 51"
catalogue_line_52 = "deterministic code row 52"
catalogue_line_53 = "deterministic code row 53"
catalogue_line_54 = "deterministic code row 54"
catalogue_line_55 = "deterministic code row 55"
catalogue_line_56 = "deterministic code row 56"
catalogue_line_57 = "deterministic code row 57"
catalogue_line_58 = "deterministic code row 58"
catalogue_line_59 = "deterministic code row 59"
catalogue_line_60 = "deterministic code row 60"
catalogue_line_61 = "deterministic code row 61"
catalogue_line_62 = "deterministic code row 62"
catalogue_line_63 = "deterministic code row 63"
catalogue_line_64 = "deterministic code row 64"
catalogue_line_65 = "deterministic code row 65"
catalogue_line_66 = "deterministic code row 66"
catalogue_line_67 = "deterministic code row 67"
catalogue_line_68 = "deterministic code row 68"
catalogue_line_69 = "deterministic code row 69"
catalogue_line_70 = "deterministic code row 70"
catalogue_line_71 = "deterministic code row 71"
catalogue_line_72 = "deterministic code row 72"
catalogue_line_73 = "deterministic code row 73"
catalogue_line_74 = "deterministic code row 74"
catalogue_line_75 = "deterministic code row 75"
catalogue_line_76 = "deterministic code row 76"
catalogue_line_77 = "deterministic code row 77"
catalogue_line_78 = "deterministic code row 78"
catalogue_line_79 = "deterministic code row 79"
PB-CODE-LAST = "last boundary line"
```

## Long table with repeated headers {: #long-table }

The header must repeat when rows continue onto another page, while each row
remains intact.

| PB-TABLE-HEADER | Review value |
| --- | --- |
| PB-TABLE-ROW-01 | Deterministic table content 01 |
| PB-TABLE-ROW-02 | Deterministic table content 02 |
| PB-TABLE-ROW-03 | Deterministic table content 03 |
| PB-TABLE-ROW-04 | Deterministic table content 04 |
| PB-TABLE-ROW-05 | Deterministic table content 05 |
| PB-TABLE-ROW-06 | Deterministic table content 06 |
| PB-TABLE-ROW-07 | Deterministic table content 07 |
| PB-TABLE-ROW-08 | Deterministic table content 08 |
| PB-TABLE-ROW-09 | Deterministic table content 09 |
| PB-TABLE-ROW-10 | Deterministic table content 10 |
| PB-TABLE-ROW-11 | Deterministic table content 11 |
| PB-TABLE-ROW-12 | Deterministic table content 12 |
| PB-TABLE-ROW-13 | Deterministic table content 13 |
| PB-TABLE-ROW-14 | Deterministic table content 14 |
| PB-TABLE-ROW-15 | Deterministic table content 15 |
| PB-TABLE-ROW-16 | Deterministic table content 16 |
| PB-TABLE-ROW-17 | Deterministic table content 17 |
| PB-TABLE-ROW-18 | Deterministic table content 18 |
| PB-TABLE-ROW-19 | Deterministic table content 19 |
| PB-TABLE-ROW-20 | Deterministic table content 20 |
| PB-TABLE-ROW-21 | Deterministic table content 21 |
| PB-TABLE-ROW-22 | Deterministic table content 22 |
| PB-TABLE-ROW-23 | Deterministic table content 23 |
| PB-TABLE-ROW-24 | Deterministic table content 24 |
| PB-TABLE-ROW-25 | Deterministic table content 25 |
| PB-TABLE-ROW-26 | Deterministic table content 26 |
| PB-TABLE-ROW-27 | Deterministic table content 27 |
| PB-TABLE-ROW-28 | Deterministic table content 28 |
| PB-TABLE-ROW-29 | Deterministic table content 29 |
| PB-TABLE-ROW-30 | Deterministic table content 30 |
| PB-TABLE-ROW-31 | Deterministic table content 31 |
| PB-TABLE-ROW-32 | Deterministic table content 32 |
| PB-TABLE-ROW-33 | Deterministic table content 33 |
| PB-TABLE-ROW-34 | Deterministic table content 34 |
| PB-TABLE-ROW-35 | Deterministic table content 35 |
| PB-TABLE-ROW-36 | Deterministic table content 36 |
| PB-TABLE-ROW-37 | Deterministic table content 37 |
| PB-TABLE-ROW-38 | Deterministic table content 38 |
| PB-TABLE-ROW-39 | Deterministic table content 39 |
| PB-TABLE-ROW-40 | Deterministic table content 40 |
| PB-TABLE-ROW-41 | Deterministic table content 41 |
| PB-TABLE-ROW-42 | Deterministic table content 42 |
| PB-TABLE-ROW-43 | Deterministic table content 43 |
| PB-TABLE-ROW-44 | Deterministic table content 44 |
| PB-TABLE-ROW-45 | Deterministic table content 45 |
| PB-TABLE-ROW-46 | Deterministic table content 46 |
| PB-TABLE-ROW-47 | Deterministic table content 47 |
| PB-TABLE-ROW-48 | Deterministic table content 48 |
| PB-TABLE-ROW-49 | Deterministic table content 49 |
| PB-TABLE-ROW-50 | Deterministic table content 50 |
| PB-TABLE-ROW-51 | Deterministic table content 51 |
| PB-TABLE-ROW-52 | Deterministic table content 52 |

<div class="page-break"></div>

## Natural paragraph flow {: #natural-paragraph-flow }

<blockquote class="catalogue-natural-block">
PB-NATURAL-FIRST - the first fixed-height paragraph block.
Natural first block line 01 provides controlled prose flow.<br>
Natural first block line 02 provides controlled prose flow.<br>
Natural first block line 03 provides controlled prose flow.<br>
Natural first block line 04 provides controlled prose flow.<br>
Natural first block line 05 provides controlled prose flow.<br>
Natural first block line 06 provides controlled prose flow.<br>
Natural first block line 07 provides controlled prose flow.<br>
Natural first block line 08 provides controlled prose flow.<br>
Natural first block line 09 provides controlled prose flow.<br>
Natural first block line 10 provides controlled prose flow.<br>
Natural first block line 11 provides controlled prose flow.<br>
Natural first block line 12 provides controlled prose flow.<br>
Natural first block line 13 provides controlled prose flow.<br>
Natural first block line 14 provides controlled prose flow.<br>
Natural first block line 15 provides controlled prose flow.<br>
Natural first block line 16 provides controlled prose flow.<br>
Natural first block line 17 provides controlled prose flow.<br>
Natural first block line 18 provides controlled prose flow.<br>
Natural first block line 19 provides controlled prose flow.<br>
Natural first block line 20 provides controlled prose flow.<br>

</blockquote>

<blockquote class="catalogue-natural-block">
PB-NATURAL-MIDDLE - the second fixed-height paragraph block.
Natural middle block line 01 provides controlled prose flow.<br>
Natural middle block line 02 provides controlled prose flow.<br>
Natural middle block line 03 provides controlled prose flow.<br>
Natural middle block line 04 provides controlled prose flow.<br>
Natural middle block line 05 provides controlled prose flow.<br>
Natural middle block line 06 provides controlled prose flow.<br>
Natural middle block line 07 provides controlled prose flow.<br>
Natural middle block line 08 provides controlled prose flow.<br>
Natural middle block line 09 provides controlled prose flow.<br>
Natural middle block line 10 provides controlled prose flow.<br>
Natural middle block line 11 provides controlled prose flow.<br>
Natural middle block line 12 provides controlled prose flow.<br>
Natural middle block line 13 provides controlled prose flow.<br>
Natural middle block line 14 provides controlled prose flow.<br>
Natural middle block line 15 provides controlled prose flow.<br>
Natural middle block line 16 provides controlled prose flow.<br>
Natural middle block line 17 provides controlled prose flow.<br>
Natural middle block line 18 provides controlled prose flow.<br>
Natural middle block line 19 provides controlled prose flow.<br>
Natural middle block line 20 provides controlled prose flow.<br>

</blockquote>

<blockquote class="catalogue-natural-block">
The third block continues on a later page through normal flow, without an
authored page-break rule.
Natural last block line 01 provides controlled prose flow.<br>
Natural last block line 02 provides controlled prose flow.<br>
Natural last block line 03 provides controlled prose flow.<br>
Natural last block line 04 provides controlled prose flow.<br>
Natural last block line 05 provides controlled prose flow.<br>
Natural last block line 06 provides controlled prose flow.<br>
Natural last block line 07 provides controlled prose flow.<br>
Natural last block line 08 provides controlled prose flow.<br>
Natural last block line 09 provides controlled prose flow.<br>
Natural last block line 10 provides controlled prose flow.<br>
Natural last block line 11 provides controlled prose flow.<br>
Natural last block line 12 provides controlled prose flow.<br>
Natural last block line 13 provides controlled prose flow.<br>
Natural last block line 14 provides controlled prose flow.<br>
Natural last block line 15 provides controlled prose flow.<br>
Natural last block line 16 provides controlled prose flow.<br>
Natural last block line 17 provides controlled prose flow.<br>
Natural last block line 18 provides controlled prose flow.<br>
Natural last block line 19 provides controlled prose flow.<br>
Natural last block line 20 provides controlled prose flow.<br>

PB-NATURAL-LAST marks the end of the naturally flowing specimen.

</blockquote>

<div class="page-break"></div>

## Lists and an admonition near a boundary {: #boundary-containers }

<blockquote class="catalogue-boundary-spacer">
PB-CONTAINER-LEAD - fixed boundary spacer
Calibration line 01 fixes the remaining vertical space.<br>
Calibration line 02 fixes the remaining vertical space.<br>
Calibration line 03 fixes the remaining vertical space.<br>
Calibration line 04 fixes the remaining vertical space.<br>
Calibration line 05 fixes the remaining vertical space.<br>
Calibration line 06 fixes the remaining vertical space.<br>
Calibration line 07 fixes the remaining vertical space.<br>
Calibration line 08 fixes the remaining vertical space.<br>
Calibration line 09 fixes the remaining vertical space.<br>
Calibration line 10 fixes the remaining vertical space.<br>
Calibration line 11 fixes the remaining vertical space.<br>
Calibration line 12 fixes the remaining vertical space.<br>
Calibration line 13 fixes the remaining vertical space.<br>
Calibration line 14 fixes the remaining vertical space.<br>
Calibration line 15 fixes the remaining vertical space.<br>
Calibration line 16 fixes the remaining vertical space.<br>
Calibration line 17 fixes the remaining vertical space.<br>
Calibration line 18 fixes the remaining vertical space.<br>
Calibration line 19 fixes the remaining vertical space.<br>
Calibration line 20 fixes the remaining vertical space.<br>
Calibration line 21 fixes the remaining vertical space.<br>
Calibration line 22 fixes the remaining vertical space.<br>
Calibration line 23 fixes the remaining vertical space.<br>
Calibration line 24 fixes the remaining vertical space.<br>
Calibration line 25 fixes the remaining vertical space.<br>
Calibration line 26 fixes the remaining vertical space.<br>
Calibration line 27 fixes the remaining vertical space.<br>
Calibration line 28 fixes the remaining vertical space.<br>

</blockquote>

!!! warning "PB-ADMONITION-TITLE"

    1. Ordered boundary item with **strong content**.
    2. Second item containing `inline code`.
       - Nested unordered item.
       - Stable sibling.
    3. PB-ADMONITION-END remains present after pagination.

## Flattened tabs and grids {: #flattened-tabs-grids }

=== "PB-TAB-FIRST"

    The first tab body remains available in the static PDF.

=== "PB-TAB-SECOND"

    The second tab body remains available in the static PDF.

<div class="grid cards" markdown>

- :lucide-layout-grid: **PB-GRID-FIRST**

  First grid card body after static flattening.

- :lucide-file-text: **PB-GRID-SECOND**

  Second grid card body after static flattening.

</div>

<div class="page-break"></div>

## Footnote near a boundary {: #boundary-footnote }

<blockquote class="catalogue-boundary-spacer">
PB-FOOTNOTE-LEAD - fixed boundary spacer
Calibration line 01 fixes the remaining vertical space.<br>
Calibration line 02 fixes the remaining vertical space.<br>
Calibration line 03 fixes the remaining vertical space.<br>
Calibration line 04 fixes the remaining vertical space.<br>
Calibration line 05 fixes the remaining vertical space.<br>
Calibration line 06 fixes the remaining vertical space.<br>
Calibration line 07 fixes the remaining vertical space.<br>
Calibration line 08 fixes the remaining vertical space.<br>
Calibration line 09 fixes the remaining vertical space.<br>
Calibration line 10 fixes the remaining vertical space.<br>
Calibration line 11 fixes the remaining vertical space.<br>
Calibration line 12 fixes the remaining vertical space.<br>
Calibration line 13 fixes the remaining vertical space.<br>
Calibration line 14 fixes the remaining vertical space.<br>
Calibration line 15 fixes the remaining vertical space.<br>
Calibration line 16 fixes the remaining vertical space.<br>
Calibration line 17 fixes the remaining vertical space.<br>
Calibration line 18 fixes the remaining vertical space.<br>
Calibration line 19 fixes the remaining vertical space.<br>
Calibration line 20 fixes the remaining vertical space.<br>
Calibration line 21 fixes the remaining vertical space.<br>
Calibration line 22 fixes the remaining vertical space.<br>
Calibration line 23 fixes the remaining vertical space.<br>
Calibration line 24 fixes the remaining vertical space.<br>
Calibration line 25 fixes the remaining vertical space.<br>
Calibration line 26 fixes the remaining vertical space.<br>
Calibration line 27 fixes the remaining vertical space.<br>
Calibration line 28 fixes the remaining vertical space.<br>

</blockquote>

PB-FOOTNOTE-REFERENCE keeps its supporting note available on the appropriate
page.[^pb-footnote]

[^pb-footnote]: PB-FOOTNOTE-CONTENT is the complete boundary footnote.

<div class="page-break"></div>

## Mermaid and mathematics near a boundary {: #boundary-vectors }

<blockquote class="catalogue-boundary-spacer">
PB-VECTOR-LEAD - fixed boundary spacer
Calibration line 01 fixes the remaining vertical space.<br>
Calibration line 02 fixes the remaining vertical space.<br>
Calibration line 03 fixes the remaining vertical space.<br>
Calibration line 04 fixes the remaining vertical space.<br>
Calibration line 05 fixes the remaining vertical space.<br>
Calibration line 06 fixes the remaining vertical space.<br>
Calibration line 07 fixes the remaining vertical space.<br>
Calibration line 08 fixes the remaining vertical space.<br>
Calibration line 09 fixes the remaining vertical space.<br>
Calibration line 10 fixes the remaining vertical space.<br>
Calibration line 11 fixes the remaining vertical space.<br>
Calibration line 12 fixes the remaining vertical space.<br>
Calibration line 13 fixes the remaining vertical space.<br>
Calibration line 14 fixes the remaining vertical space.<br>
Calibration line 15 fixes the remaining vertical space.<br>
Calibration line 16 fixes the remaining vertical space.<br>
Calibration line 17 fixes the remaining vertical space.<br>
Calibration line 18 fixes the remaining vertical space.<br>
Calibration line 19 fixes the remaining vertical space.<br>
Calibration line 20 fixes the remaining vertical space.<br>
Calibration line 21 fixes the remaining vertical space.<br>
Calibration line 22 fixes the remaining vertical space.<br>
Calibration line 23 fixes the remaining vertical space.<br>
Calibration line 24 fixes the remaining vertical space.<br>
Calibration line 25 fixes the remaining vertical space.<br>
Calibration line 26 fixes the remaining vertical space.<br>
Calibration line 27 fixes the remaining vertical space.<br>
Calibration line 28 fixes the remaining vertical space.<br>

</blockquote>

```mermaid
flowchart LR
    A[PB-MERMAID-START] --> B[PB-MERMAID-END]
```

PB-MATH-VECTOR labels the display equation used for vector review.

$$
x_1 + x_2 + x_3 = 6
$$

<div class="page-break"></div>

## Long unbreakable token {: #long-unbreakable-token }

The following token must wrap inside the page rather than being clipped beyond
the content box.

<span class="catalogue-long-token">PB-LONG-TOKEN-START-CATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUECATALOGUE-PB-LONG-TOKEN-END</span>
