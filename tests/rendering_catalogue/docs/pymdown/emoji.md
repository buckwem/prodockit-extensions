# Emoji and icons { #emoji }

Reference: [Zensical's supported Python Markdown Extensions](https://zensical.org/docs/compatibility/markdown/python-markdown-extensions/)

## Configuration source

```toml
[project.markdown_extensions.pymdownx.emoji]
emoji_index = "zensical.extensions.emoji.twemoji"
emoji_generator = "zensical.extensions.emoji.to_svg"
options.custom_icons = ["overrides/.icons"]
```

## Emoji index { #emoji-index }

The Zensical Twemoji index also exposes the bundled icon namespaces used by
the material test-tube specimen.

## Emoji generator { #emoji-generator }

The Zensical SVG generator produces inline SVG for icons, so they do not rely
on a font glyph.

## Custom icons { #custom-icons }

The custom icon directory contributes the catalogue Phase 3 specimen.

## Source

```text
:material-test-tube: :catalogue-phase:
```

## Rendered result

:material-test-tube:{ title="Bundled test-tube icon" }
:catalogue-phase:{ title="Custom Phase 3 icon" }

Both icons must remain visible as vectors on the website and in the PDF.
