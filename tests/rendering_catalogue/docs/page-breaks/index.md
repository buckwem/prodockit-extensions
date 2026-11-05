# Page breaks

This section will contain deterministic PDF specimens for both explicitly
forced page breaks and renderer-controlled keep/avoid behaviour.

The cases will use fixed page geometry, fonts and named content markers so
tests can assert that selected markers appear on the same page or different
pages. Coverage will include headings and following content, figures and
captions, code blocks, tables, lists, admonitions, flattened tabs and grids,
footnotes, Mermaid diagrams, mathematics and overflow-prone content.

The tests will inspect PDF text and drawing evidence rather than depending on
whole-file bytes or global page numbers. Phase 1 reserves this section and its
contract; the controlled specimens are added in a later phase.
