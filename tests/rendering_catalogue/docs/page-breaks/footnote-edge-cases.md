{{ pdk_heading_counter_reset(page) }}

# Footnote edge cases { #footnote-edge-cases }

These six specimens extend the ordinary and crowded-footnote checks with the
structures most likely to fail at a page boundary. Named markers make every
reference and complete note reviewable in both the website and PDF.

## One footnote longer than a page { #oversized-footnote }

OVERSIZED-REFERENCE introduces one deliberately exceptional note whose body is
too tall for a single A4 footnote area.[^oversized] It may continue onto a
second page, but its text must remain complete and ordered.

[^oversized]: OVERSIZED-FOOTNOTE-START begins the oversized note.

    OVERSIZED-PARAGRAPH-01 explains that an individual note may contain sustained commentary whose length exceeds the available footnote area on one page. The renderer must not clip or discard this paragraph.

    OVERSIZED-PARAGRAPH-02 continues the same note with independent prose so its order can be checked after pagination. The note remains attached to its original call.

    OVERSIZED-PARAGRAPH-03 adds another complete paragraph and enough words to produce several wrapped lines at the fixed catalogue width.

    OVERSIZED-PARAGRAPH-04 checks that a continuation does not restart numbering or appear before an earlier paragraph from the same note.

    OVERSIZED-PARAGRAPH-05 provides further controlled text for a note that cannot fit in the remaining page area.

    OVERSIZED-PARAGRAPH-06 keeps the specimen realistic while making loss, duplication or reordering visible in extracted text.

    OVERSIZED-PARAGRAPH-07 marks the middle of the note and confirms that the continuation remains legible.

    OVERSIZED-PARAGRAPH-08 adds a separate paragraph whose spacing should remain visible rather than being flattened into the preceding text.

    OVERSIZED-PARAGRAPH-09 continues the ordered sequence with enough prose to wrap naturally across several lines.

    OVERSIZED-PARAGRAPH-10 verifies that double-digit paragraph markers remain in the expected sequence.

    OVERSIZED-PARAGRAPH-11 supplies more reviewable text and must remain within the footnote area rather than entering the body or footer.

    OVERSIZED-PARAGRAPH-12 continues the note without introducing a second footnote number.

    OVERSIZED-PARAGRAPH-13 checks that a later continuation retains the same text styling and indentation.

    OVERSIZED-PARAGRAPH-14 provides another complete block for detecting clipping near a page boundary.

    OVERSIZED-PARAGRAPH-15 keeps the note taller than one ordinary A4 content area at the pinned catalogue settings.

    OVERSIZED-PARAGRAPH-16 is the penultimate block and must appear after every earlier marker.

    OVERSIZED-PARAGRAPH-17 continues the sustained content without ending the note prematurely.

    OVERSIZED-PARAGRAPH-18 adds enough controlled text to force the continuation block onto another page at the pinned A4 settings.

    OVERSIZED-PARAGRAPH-19 remains complete and ordered after the page boundary.

    OVERSIZED-PARAGRAPH-20 confirms that the continuation does not return to body-text sizing.

    OVERSIZED-PARAGRAPH-21 supplies another independent paragraph for visual spacing review.

    OVERSIZED-PARAGRAPH-22 must follow every earlier marker without duplication.

    OVERSIZED-PARAGRAPH-23 continues the same single oversized note.

    OVERSIZED-PARAGRAPH-24 checks that the ruled continuation layout remains stable.

    OVERSIZED-PARAGRAPH-25 makes clipping near the second page boundary easy to detect.

    OVERSIZED-PARAGRAPH-26 remains part of the note rather than ordinary body content.

    OVERSIZED-PARAGRAPH-27 provides further text for a realistic extreme case.

    OVERSIZED-PARAGRAPH-28 checks that later paragraph spacing remains consistent.

    OVERSIZED-PARAGRAPH-29 is the penultimate block and must remain readable.

    OVERSIZED-PARAGRAPH-30 concludes the sustained content. OVERSIZED-FOOTNOTE-END marks the complete end of the oversized note.

<div class="page-break"></div>

## Two footnotes in one paragraph { #two-footnotes-one-paragraph }

TWO-CALLS-PARAGRAPH contains TWO-CALLS-FIRST near its opening[^two-first] and
TWO-CALLS-SECOND later in the same paragraph.[^two-second] Both notes must use
the same reference page, retain numeric order and remain complete.

[^two-first]: TWO-CALLS-FIRST-BODY is the complete first note from the shared paragraph.
[^two-second]: TWO-CALLS-SECOND-BODY is the complete second note from the shared paragraph.

## Multi-paragraph footnote { #multi-paragraph-footnote }

MULTI-PARAGRAPH-REFERENCE introduces a note containing two genuine Markdown
paragraphs.[^multi-paragraph]

[^multi-paragraph]: MULTI-PARAGRAPH-FIRST is the first paragraph. Its final sentence makes the break before the next paragraph visually reviewable.

    MULTI-PARAGRAPH-SECOND is the second paragraph. It must not be silently joined to the first paragraph in the PDF.

## Repeated reference to one footnote { #repeated-footnote-reference }

REPEATED-FIRST-CALL introduces one shared note.[^repeated] Later in the same
paragraph, REPEATED-SECOND-CALL refers to that same note again.[^repeated]
The note body must appear once while both calls retain the same number.

[^repeated]: REPEATED-FOOTNOTE-BODY appears exactly once in the collected footnotes and once in the PDF footnote area.

<div class="page-break"></div>

## Footnotes inside nested content { #nested-footnote-boundaries }

- NESTED-LIST-REFERENCE is inside an unordered list item.[^nested-list]
- The sibling item confirms that the list continues after the reference.

!!! warning "Nested admonition boundary"
    NESTED-ADMONITION-REFERENCE is inside an admonition.[^nested-admonition]
    Its complete note must stay associated with this call.

/// steps

1. NESTED-STEP-REFERENCE is inside a numbered step.[^nested-step]

2. The second step confirms that the steps container continues normally.

///

[^nested-list]: NESTED-LIST-BODY is the complete note referenced from the list item.
[^nested-admonition]: NESTED-ADMONITION-BODY is the complete note referenced from the warning.
[^nested-step]: NESTED-STEP-BODY is the complete note referenced from the numbered step.

## Long URL and unbreakable text { #long-footnote-token }

LONG-TOKEN-REFERENCE introduces a note containing a long URL and a continuous
token.[^long-token] Both must remain inside the printable page width.

[^long-token]: LONG-URL-START https://example.invalid/catalogue/footnotes/this/is/a/deliberately/long/path/with/many/segments/and-a-final-resource-name?review=footnote-pagination&format=pdf LONG-URL-END LONG-TOKEN-START ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 LONG-TOKEN-END.
