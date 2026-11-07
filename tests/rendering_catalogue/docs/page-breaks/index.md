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
| Consecutive notes | [Multiple long notes](multiple-long-notes.md#multiple-long-notes) | Every note remains intact while the sequence flows across pages |
| Consecutive footnotes | [Multiple long footnotes](multiple-long-footnotes.md#multiple-long-footnotes) | Each multi-line footnote remains complete and associated with its reference |
| Footnote edge cases | [Footnote edge cases](footnote-edge-cases.md#footnote-edge-cases) | Oversized, shared-paragraph, multi-paragraph, repeated, nested and long-token notes remain reviewable |
| Admonitions | [Admonition pagination](admonition-pagination.md#admonition-pagination) | Oversized and richly nested call-outs split without losing ownership or content |
| Interactive containers and lists | [Container pagination](container-pagination.md#container-pagination) | Expanded tabs, grid cards, steps, definitions and task states remain complete |
| Tables and figures | [Rich block pagination](rich-block-pagination.md#rich-block-pagination) | Captions remain associated and complex table rows do not split |
| Page-local bibliography | [Bibliography pagination](page-bibliography-pagination.md#page-bibliography-pagination) | Reference entries span pages without splitting, while local links and backlinks remain correctly scoped |
| Footnotes and vectors | [Boundary footnote](flow-and-overflow.md#boundary-footnote) and [Mermaid and maths](flow-and-overflow.md#boundary-vectors) | Text and vector evidence remain available |
| Overflow | [Long token](flow-and-overflow.md#long-unbreakable-token) | Text wraps inside the page content box |

The PDF tests inspect extracted text, vector evidence and relative page
placement. The website tests verify that the authored semantic structures are
also available for browser review.
