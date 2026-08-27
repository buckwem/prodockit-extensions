---
icon: lucide/calendar-clock
---

{{ heading_counter_reset(page) }}

# Page update dates

\index{page update dates} records when each source page was last changed. During
the publication build, Prodockit finds the HTML page produced from each
Markdown file and supplies its update date. It uses the latest Git author date
when history is available and the Markdown file's modification date otherwise.

## Place the website date

Write the introductory text you want and put
`<!-- prodockit-update-date -->` at the exact insertion point:

```markdown
Document reviewed: <!-- prodockit-update-date -->
```

The completed website renders, for example:

> Document reviewed: 2026-08-27

The text before or after the marker is ordinary Markdown and is entirely the
author's choice. Without a marker, Prodockit retains the default behaviour and
places an **Updated** fact at the bottom of the generated page.

During `zensical serve`, the marker itself is invisible and only the author's
text is shown. Run the static build followed by `prodockit update-dates` to
inspect the date in its final position.

## Understand the PDF position

The PDF uses the same page date automatically. `prodockit pdf` prints
`Updated on YYYY-MM-DD` below the page number for each source section. The PDF
position follows the document's running-footer design and is not controlled by
the website marker.

The website and PDF need no date macro, Markdown extension, or change to
`zensical.toml`.

## Override one page's date

To override the automatic date for one page, add `revision_date` to that
page's YAML front matter:

```yaml
---
revision_date: 2026-08-27
---

# Page title
```

The explicit value appears in a `zensical serve` preview and takes priority
in the completed website and PDF. Use it only when the displayed date needs
to be controlled independently of the file's history.

This page was updated: <!-- prodockit-update-date -->

Continue to [Build with revision dates](publishing.md#build-with-revision-dates)
for the two publication commands, Git and non-Git behaviour, and CI history
requirements.

