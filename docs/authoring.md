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

![Prodockit authoring features grouped by structure and layout, evidence and navigation, and calculated values and outputs](assets/diagrams/7.1-authoring-feature-map.png){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-authoring-feature-map}

Prodockit authoring feature map
///

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
/// table-caption | <
    attrs: {id: tab-authoring-choose-a-feature}

Choose a feature
///

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
| Show when each source page was last updated | [Page update dates](update-dates.md) |
| Produce a complete PDF, a single-page PDF, or a source bundle | [PDF generation](pdf.md) |
| Find the safe first form, write behaviour, and options for every public command | [Command-line tools](command-line.md) |
/// table-caption | <
    attrs: {id: tab-authoring-use-features-beyond-markdown-extensions}

Use features beyond Markdown extensions
///

These features are part of the same authoring reference because they affect
what the document contains or produces. Installation, repository maintenance,
continuous integration, and deployment remain in their task-based sections.

## Keep deployment concerns separate

The authoring pages explain what to write, how to configure its rendered
features, and how to build local outputs. When those outputs are ready for a
hosted website, continue to [Publish a document](publishing.md). Template
updates, CI, Pages deployment, and output tests live there so they do not
interrupt the authoring reference.
