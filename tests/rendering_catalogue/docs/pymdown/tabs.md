# Content tabs { #tabs }

Reference: [Zensical's supported Python Markdown Extensions](https://zensical.org/docs/compatibility/markdown/python-markdown-extensions/)

## Configuration source

```toml
[project.markdown_extensions.pymdownx.tabbed]
alternate_style = true
combine_header_slug = true
[project.markdown_extensions.pymdownx.tabbed.slugify]
object = "pymdownx.slugs.slugify"
[project.markdown_extensions.pymdownx.tabbed.slugify.kwds]
case = "lower"
```

## Alternate style { #tabbed-alternate-style }

The tab set uses the supported alternate style.

## Combined header slug { #tabbed-combined-header-slug }

The tab identifiers include the enclosing heading identifier.

## Slug function { #tabbed-slugify }

Mixed-case tab labels produce lower-case identifiers.

## Source

```text
## Review group { #review-group }

=== "Mixed CASE Tab"

    First tab body.

=== "Second Tab"

    Second tab body.
```

## Review group { #review-group }

=== "Mixed CASE Tab"

    First tab body.

=== "Second Tab"

    Second tab body.

The website provides an accessible interactive tab set. The PDF must flatten
both labelled tab bodies in their source order.
