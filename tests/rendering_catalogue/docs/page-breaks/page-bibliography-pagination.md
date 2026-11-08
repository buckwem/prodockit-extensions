{{ pdk_heading_counter_reset(page) }}

# Page-local bibliography pagination { #page-bibliography-pagination }

This single Markdown source deliberately produces several physical PDF pages.
Its citations and footnotes appear throughout the source, while one
`\pagebibliography` marker must collect every resolved citation from this file
only and append the generated **References** section to the bottom of the web
page. The generated list must paginate without splitting an entry, and it must
be able to share a physical page with an ordinary footnote area.

## Source span one

CITATION-CALL-01 cites \cite{pagination01}.

CITATION-CALL-02 cites \cite{pagination02}.

CITATION-CALL-03 cites \cite{pagination03}.

CITATION-CALL-04 cites \cite{pagination04}.

SOURCE-PAGE-ONE-CALL cites \cite{pagination05} and carries a supporting
footnote.[^source-page-one]

[^source-page-one]: SOURCE-PAGE-ONE-FOOTNOTE is a multi-line note associated with the first physical span of this Markdown source. It contains enough explanatory text to wrap naturally and make clipping, overlap or movement to the wrong physical page visible.

CITATION-CALL-06 cites \cite{pagination06}.

CITATION-CALL-07 cites \cite{pagination07}.

CITATION-CALL-08 cites \cite{pagination08}.

CITATION-CALL-09 cites \cite{pagination09}.

CITATION-CALL-10 cites \cite{pagination10}.

<div class="page-break"></div>

## Source span two

CITATION-CALL-11 cites \cite{pagination11}.

CITATION-CALL-12 cites \cite{pagination12}.

CITATION-CALL-13 cites \cite{pagination13}.

CITATION-CALL-14 cites \cite{pagination14}.

SOURCE-PAGE-TWO-CALL cites \cite{pagination15} and carries a second supporting
footnote.[^source-page-two]

[^source-page-two]: SOURCE-PAGE-TWO-FOOTNOTE verifies that a later physical page retains its own note while all citations still belong to the same Markdown source bibliography. This wording also wraps across several lines at the fixed catalogue width.

CITATION-CALL-16 cites \cite{pagination16}.

CITATION-CALL-17 cites \cite{pagination17}.

CITATION-CALL-18 cites \cite{pagination18}.

CITATION-CALL-19 cites \cite{pagination19}.

CITATION-CALL-20 cites \cite{pagination20}.

<div class="page-break"></div>

## Source span three

CITATION-CALL-21 cites \cite{pagination21}.

CITATION-CALL-22 cites \cite{pagination22}.

CITATION-CALL-23 cites \cite{pagination23}.

CITATION-CALL-24 cites \cite{pagination24}.

CITATION-CALL-25 cites \cite{pagination25}.

CITATION-CALL-26 cites \cite{pagination26}.

CITATION-CALL-27 cites \cite{pagination27}.

CITATION-CALL-28 cites \cite{pagination28}.

CITATION-CALL-29 cites \cite{pagination29}.

SOURCE-PAGE-THREE-CALL cites \cite{pagination30} and carries the final
supporting footnote before the generated list.[^source-page-three]

[^source-page-three]: SOURCE-PAGE-THREE-FOOTNOTE checks the boundary where an ordinary footnote area and the page-local bibliography may share one physical PDF page without overlap. The note must remain complete and associated with this call.

REPEATED-CITATION-CALL-01 cites \cite{pagination01} again, while
REPEATED-CITATION-CALL-02 cites \cite{pagination02} again.

\pagebibliography

PAGE-BIBLIOGRAPHY-FOLLOWING is authored after the marker. It must remain before
the generated **References** section on the website and in the PDF.
