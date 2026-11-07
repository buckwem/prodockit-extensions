{{ pdk_heading_counter_reset(page) }}

# Rich block pagination { #rich-block-pagination }

These specimens cover compound tables and figures, where related labels and
content must remain associated even when the surrounding page is crowded.

## Complex captioned table { #complex-captioned-table }

| COMPLEX-TABLE-HEADER | Review content |
| --- | --- |
| COMPLEX-ROW-01-START | First row with `inline code` and COMPLEX-ROW-01-END |
| COMPLEX-ROW-02-START | A longer cell that wraps naturally and contains a [relative link](../) before COMPLEX-ROW-02-END |
| COMPLEX-ROW-03-START | Third controlled row and COMPLEX-ROW-03-END |
| COMPLEX-ROW-04-START | Fourth controlled row and COMPLEX-ROW-04-END |
| COMPLEX-ROW-05-START | Fifth controlled row and COMPLEX-ROW-05-END |
| COMPLEX-ROW-06-START | Sixth controlled row and COMPLEX-ROW-06-END |
| COMPLEX-ROW-07-START | Seventh controlled row and COMPLEX-ROW-07-END |
| COMPLEX-ROW-08-START | Eighth controlled row and COMPLEX-ROW-08-END |
| COMPLEX-ROW-09-START | Ninth controlled row and COMPLEX-ROW-09-END |
| COMPLEX-ROW-10-START | Tenth controlled row and COMPLEX-ROW-10-END |
| COMPLEX-ROW-11-START | Eleventh controlled row and COMPLEX-ROW-11-END |
| COMPLEX-ROW-12-START | Twelfth controlled row and COMPLEX-ROW-12-END |
| COMPLEX-ROW-13-START | Thirteenth controlled row and COMPLEX-ROW-13-END |
| COMPLEX-ROW-14-START | Fourteenth controlled row and COMPLEX-ROW-14-END |
| COMPLEX-ROW-15-START | Fifteenth controlled row and COMPLEX-ROW-15-END |
| COMPLEX-ROW-16-START | Sixteenth controlled row and COMPLEX-ROW-16-END |
| COMPLEX-ROW-17-START | Seventeenth controlled row and COMPLEX-ROW-17-END |
| COMPLEX-ROW-18-START | Eighteenth controlled row and COMPLEX-ROW-18-END |
| COMPLEX-ROW-19-START | Nineteenth controlled row and COMPLEX-ROW-19-END |
| COMPLEX-ROW-20-START | Final controlled row and COMPLEX-ROW-20-END |

/// table-caption
    attrs: {id: tab-pagination-complex}

COMPLEX-TABLE-CAPTION describes a table with wrapped cells.
///

<div class="page-break"></div>

## Figure with a long caption near a boundary { #long-figure-caption }

<blockquote class="catalogue-boundary-spacer catalogue-boundary-spacer--medium">
FIGURE-BOUNDARY-LEAD fixes the remaining space.<br>
Calibration 01.<br>Calibration 02.<br>Calibration 03.<br>Calibration 04.<br>
Calibration 05.<br>Calibration 06.<br>Calibration 07.<br>Calibration 08.<br>
</blockquote>

![FIGURE-IMAGE-MARKER](../assets/core-sample.svg){ width="360" }
/// figure-caption | <
    attrs: {id: fig-pagination-long-caption}

FIGURE-LONG-CAPTION-START describes the image with enough sustained text to
wrap over several lines while remaining attached to the image. The caption
continues with reviewable prose so an orphaned caption fragment is visible.
FIGURE-LONG-CAPTION-END marks its complete text.
///

FIGURE-FOLLOWING-CONTENT confirms that ordinary flow resumes after the figure.
