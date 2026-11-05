# Table of contents { #table-of-contents }

Reference: [Zensical's built-in Python-Markdown extensions](https://zensical.org/docs/compatibility/markdown/python-markdown/)

This page exercises every table-of-contents setting currently documented as
supported by Zensical.

## Configuration source

```toml
[project.markdown_extensions.toc]
title = "Catalogue contents"
permalink = "¶"
permalink_title = "Permanent link to this catalogue section"
toc_depth = 3
[project.markdown_extensions.toc.slugify]
object = "pymdownx.slugs.slugify"
[project.markdown_extensions.toc.slugify.kwds]
case = "lower"
```

## Title { #toc-title }

The right-hand navigation is explicitly titled **Catalogue contents**.

## Permalink { #toc-permalink }

Headings receive the configured paragraph-symbol permalink.

## Permalink title { #toc-permalink-title }

Each permalink uses **Permanent link to this catalogue section** as its
accessible title.

## Slug function { #toc-slugify }

### Mixed CASE heading { #mixed-case-heading }

The configured PyMdown slug function produces a lower-case identifier.

## Depth { #toc-depth }

### Included level-three heading { #included-level-three-heading }

Level-three headings are included in the page table of contents.

<div class="catalogue-keep-together" markdown>

#### Excluded level-four heading { #excluded-level-four-heading }

This level-four heading remains in the document but is excluded by the
configured depth of three.

</div>

The PDF must retain the heading hierarchy and internal destinations even
though it does not reproduce the website's interactive right-hand navigation.
