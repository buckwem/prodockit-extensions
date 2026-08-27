---
icon: lucide/pencil-line
---

{{ heading_counter_reset(page) }}

# Authoring reference

This section is for a document author who has built a first Zensical site and
wants to add structure or specialist content to its \index{Markdown} pages,
use values calculated across the document, or produce a PDF. You do not need
to read every page: choose the feature or tool the document needs and start
with its smallest complete example.

## Build on PyMdown Blocks

Two prodockit extensions are built directly on \index{PyMdown Blocks} (see the
[upstream Blocks guide](https://facelessuser.github.io/pymdown-extensions/extensions/blocks/)):
`prodockit.steps` for procedures and `prodockit.tree` for directory listings.
They use PyMdown's slash-fenced container syntax, nesting rules, and block
options rather than introducing a separate container language.

If you already use PyMdown Blocks, the structure will be familiar. If you do
not, start with [Numbered steps](extensions/steps.md): its first example shows
the complete opening and closing fences before explaining nested blocks.

## Follow the same three stages

Every extension guide starts with the same learning path:

/// steps

//// step | Enable the extension

Add the extension's table to `zensical.toml`. Each prodockit extension is
independent, so enabling headings does not silently enable citations, tables,
or another feature.

////

//// step | Write the Markdown

Start with the complete copyable example. The guide shows both its Markdown
source and rendered result before introducing variations.

////

//// step | Configure only when needed

Keep the defaults for a first use. The configuration section explains the
available `zensical.toml` settings and shows a rendered example when an option
changes visible output.

////

///

## Choose a feature

| Document need | Reference |
|---|---|
| Number sections and give headings stable links | [Headings](extensions/headings.md) |
| Refer to a heading, figure, or table without typing its changing number | [Cross-references](extensions/refs.md) |
| Define short references directly in Markdown | [Hand-written citations and references](extensions/citations.md) |
| Expand abbreviations and define specialist terms | [Acronyms and glossary](extensions/glossary.md) |
| Control column widths, merged cells, and dense layouts | [Tables](extensions/tables.md) |
| Show a folder and file hierarchy | [Directory trees](extensions/tree.md) |
| Present a procedure with connected numbered stages | [Numbered steps](extensions/steps.md) |
| Cite a BibTeX library in a selected CSL style | [Bibliography](extensions/bibliography.md) |
| Mark terms for a PDF back-of-book index | [Index](extensions/index-terms.md) |

`prodockit.citations` and `prodockit.bibliography` are two approaches to the
same broad task. A small document can define sources directly in Markdown;
a report with an existing `.bib` library normally uses the bibliography
extension. You do not need to enable both.

## Use features beyond Markdown extensions

Some authoring features are commands or Zensical template helpers rather than
Python-Markdown extensions:

| Document need | Reference |
|---|---|
| Insert calculated values such as word counts, repository details, or document-wide layout settings | [Website macros](macros.md) |
| Show when each source page was last updated | [Page update dates](#page-update-dates) |
| Produce a complete PDF, a single-page PDF, or a source bundle | [PDF generation](pdf.md) |
| Find the safe first form, write behaviour, and options for every public command | [Command-line tools](command-line.md) |

These features are part of the same authoring reference because they affect
what the document contains or produces. Installation, repository maintenance,
continuous integration, and deployment remain in their task-based sections.

## Page update dates

During the publication build, Prodockit finds the HTML page produced from each
Markdown file and supplies its update date. It uses the latest Git author date
when history is available and the Markdown file's modification date otherwise.

To choose where the date appears on the website, write the introductory text
you want and put `<!-- prodockit-update-date -->` at the exact insertion point:

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

The PDF uses the same page date automatically. `prodockit pdf` prints
`Updated on YYYY-MM-DD` below the page number for each source section. The
website and PDF therefore need no date macro, Markdown extension, or change to
`zensical.toml`.

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

## Keep deployment concerns separate

The authoring pages explain what to write, how to configure its rendered
features, and how to build local outputs. When those outputs are ready for a
hosted website, continue to [Publish a document](publishing.md). Template
updates, CI, Pages deployment, and output tests live there so they do not
interrupt the authoring reference.
