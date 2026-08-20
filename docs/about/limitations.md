---
icon: lucide/triangle-alert
---

# Known limitations

This page is for document authors. It describes known \index{limitations} by what you see
and what you can do next. For causes, design trade-offs, and regression risks,
see the [Contributor internals](../devcons/limitations.md).

## A cross-page value looks stale during live preview

**What you see:** after editing a heading, citation, glossary definition, or
index-related value on one page, another open page can still show its previous
value under `zensical serve`.

**What to do:** save or refresh the affected page, or restart `zensical serve`.
Always run `zensical build --clean --strict` before publishing; a clean build
resolves the complete document together.

## A duplicate heading link resolves unpredictably

**What you see:** two pages use the same generated heading id and a
cross-reference can resolve to the wrong page.

**What to do:** give each referenced heading an explicit, unique id, preferably
with a page prefix, such as `{#methods-sampling}`.

## A bibliography citation remains as literal text

**What you see:** `\\cite{first,second}` is unchanged when using
`prodockit.bibliography`.

**What to do:** cite each BibTeX entry separately. Multiple keys in one command
are supported by `prodockit.citations`, not by the BibTeX extension.

## Mermaid or maths source appears in a PDF

**What you see:** a PDF contains Mermaid source or TeX rather than a rendered
diagram or formula.

**What to do:** run `prodockit init-tools`, install the reported Node tools, and
rebuild. The website can render these features in the browser, but the PDF must
convert them before WeasyPrint runs.

## Browser and PDF layouts differ

**What you see:** tabs, grids, captions, footnotes, videos, or interactive
elements have a simpler layout in the PDF.

**What to do:** treat the PDF as a print layout, check the built artifact, and
use the PDF-specific CSS hooks documented with the relevant feature. A PDF has
no browser JavaScript or interactive controls.

## The word count omits unexpected content

**What you see:** `{{ word_count }}` is lower than expected.

**What to do:** keep a dedicated cover page first in `nav`. The first page is
excluded automatically, as are pages marked `exclude_from_word_count: true`.

## A limitation is not listed

Run a clean build and check the current local command help first. If the
problem remains, search or open a
[GitHub issue](https://github.com/buckwem/prodockit-extensions/issues) with the
prodockit, Zensical, Python, and operating-system versions.
