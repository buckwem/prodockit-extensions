# Page breaks

This section contains deterministic PDF specimens for both explicitly forced
page breaks and renderer-controlled keep/avoid behaviour. It tests the places
where a website can reflow freely but a paged document must make a stable,
reviewable decision.

The catalogue uses A4 pages, fixed margins, pinned fonts and named content
markers. Tests compare whether selected markers occur on the same page or
different pages; they do not depend on a global page number or byte-identical
PDF output.

| Review area | Specimen | Expected PDF relationship |
| --- | --- | --- |
| Explicit breaks | [Break before and after](forced-and-kept.md#explicit-break-after) | Markers occur on different pages |
| Kept content | [Block, heading and figure](forced-and-kept.md#keep-together) | Related markers stay on the same page |
| Long code and tables | [Flow across boundaries](flow-and-overflow.md#long-code-block) | First and last markers occur on different pages; table headers repeat |
| Natural flow | [Fixed-height paragraphs](flow-and-overflow.md#natural-paragraph-flow) | Content crosses a boundary without an authored break |
| Nested containers | [Lists, admonitions, tabs and grids](flow-and-overflow.md#boundary-containers) | All static content remains present |
| Footnotes and vectors | [Boundary footnote](flow-and-overflow.md#boundary-footnote) and [Mermaid and maths](flow-and-overflow.md#boundary-vectors) | Text and vector evidence remain available |
| Overflow | [Long token](flow-and-overflow.md#long-unbreakable-token) | Text wraps inside the page content box |

The PDF tests inspect extracted text, vector evidence and relative page
placement. The website tests verify that the authored semantic structures are
also available for browser review.
