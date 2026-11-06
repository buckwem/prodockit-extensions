{{ pdk_heading_counter_reset(page) }}

# Forced and kept content

These specimens use fixed A4 geometry, pinned fonts and named markers. The
website exposes the authored structures; the PDF assertions verify relative
placement without depending on absolute page numbers.

## Explicit break after content {: #explicit-break-after }

### Source pattern

```html
<p>Content before the break</p>
<div class="page-break"></div>
<p>Content after the break</p>
```

### Rendered specimen

<p id="pb-forced-after-start">PB-FORCED-AFTER-START</p>
<div class="page-break"></div>
<p id="pb-forced-after-end">PB-FORCED-AFTER-END</p>

The two named markers must be on different PDF pages.

## Explicit break before content {: #explicit-break-before }

### Source pattern

```html
<p>Content before the break</p>
<div class="catalogue-break-before">Content after the break</div>
```

### Rendered specimen

<p id="pb-forced-before-start">PB-FORCED-BEFORE-START</p>
<div class="catalogue-break-before" id="pb-forced-before-end">
PB-FORCED-BEFORE-END
</div>

The second marker must begin on a later PDF page.

<div class="page-break"></div>

## Keep a block together {: #keep-together }

<blockquote class="catalogue-boundary-spacer catalogue-boundary-spacer--large">
PB-KEEP-LEAD - fixed boundary spacer
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

<figure class="catalogue-keep-together catalogue-keep-box" id="pb-keep-box">

<strong>PB-KEEP-START</strong>

This block is deliberately too tall for the remaining space. The renderer
must move it as a unit rather than splitting it.
Kept block line 01 remains inside the protected container.<br>
Kept block line 02 remains inside the protected container.<br>
Kept block line 03 remains inside the protected container.<br>
Kept block line 04 remains inside the protected container.<br>
Kept block line 05 remains inside the protected container.<br>
Kept block line 06 remains inside the protected container.<br>
Kept block line 07 remains inside the protected container.<br>
Kept block line 08 remains inside the protected container.<br>
Kept block line 09 remains inside the protected container.<br>
Kept block line 10 remains inside the protected container.<br>
Kept block line 11 remains inside the protected container.<br>
Kept block line 12 remains inside the protected container.<br>
Kept block line 13 remains inside the protected container.<br>
Kept block line 14 remains inside the protected container.<br>
Kept block line 15 remains inside the protected container.<br>
Kept block line 16 remains inside the protected container.<br>
Kept block line 17 remains inside the protected container.<br>
Kept block line 18 remains inside the protected container.<br>

<strong>PB-KEEP-END</strong>

</figure>

The lead marker must be on the preceding page; both keep markers must share
one page.

<div class="page-break"></div>

## Keep a heading with following content {: #heading-with-content }

<blockquote class="catalogue-boundary-spacer catalogue-boundary-spacer--large">
PB-HEADING-LEAD - fixed boundary spacer
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

### PB-HEADING-TITLE {: #pb-heading-title }

PB-HEADING-FOLLOWING-CONTENT remains with the heading when the remaining space
cannot hold both blocks.

<div class="page-break"></div>

## Keep a figure with its caption {: #figure-with-caption }

<blockquote class="catalogue-boundary-spacer">
PB-FIGURE-LEAD - fixed boundary spacer
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

![Website and PDF review flow](../assets/core-sample.svg){ width="360" }
/// figure-caption | <
    attrs: {id: fig-page-break-review}

PB-FIGURE-CAPTION
///

The caption and vector image form one atomic figure and move together.
