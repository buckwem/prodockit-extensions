---
title: Layout and integrations specimen
description: Phase 4 review cases for Zensical layout and configured integrations.
icon: lucide/layout-template
status: new
---

# Layout and integrations

This page covers Zensical authoring features that need project-level metadata,
theme styling, or configured integrations rather than only an underlying
Markdown token.

## Front matter {: #front-matter }

Reference: [Zensical front matter](https://zensical.org/docs/authoring/frontmatter/)

### Source

```yaml
---
title: Layout and integrations specimen
description: Phase 4 review cases for Zensical layout and configured integrations.
icon: lucide/layout-template
status: new
---
```

### Rendered result

The browser title and page metadata use the configured title and description.
The navigation entry carries the configured icon and Phase 4 status marker.

## BetterEm {: #betterem }

Reference: [PyMdown BetterEm](https://facelessuser.github.io/pymdown-extensions/extensions/betterem/)

### Source

```md
**Strong text containing _nested emphasis_ remains correctly nested.**
```

### Rendered result

**Strong text containing _nested emphasis_ remains correctly nested.**

## MagicLink {: #magiclink }

Reference: [PyMdown MagicLink](https://facelessuser.github.io/pymdown-extensions/extensions/magiclink/)

### Source

```md
https://example.com/catalogue-phase-four
```

### Rendered result

https://example.com/catalogue-phase-four

## Buttons {: #buttons }

Reference: [Zensical buttons](https://zensical.org/docs/authoring/buttons/)

### Source

```md
[Review Phase 4 :lucide-arrow-right:](#grids){ .md-button .md-button--primary }
```

### Rendered result

[Review Phase 4 :lucide-arrow-right:](#grids){ .md-button .md-button--primary }

The website presents the link as a button. The PDF keeps a clear, usable link
without depending on hover or click styling.

## Grids {: #grids }

Reference: [Zensical grids](https://zensical.org/docs/authoring/grids/)

### Source

```html
<div class="grid cards" markdown>

- :lucide-globe: **Website** - interactive review output
- :lucide-file-text: **PDF** - static review output

</div>
```

### Rendered result

<div class="grid cards" markdown>

- :lucide-globe: **Website** - interactive review output
- :lucide-file-text: **PDF** - static review output

</div>

The website arranges the cards responsively. The PDF retains both complete
cards in reading order.

## Images and GLightbox {: #images-and-glightbox }

References: [Zensical images and GLightbox](https://zensical.org/docs/authoring/images/)

### Source

```md
![Website and PDF review flow](../assets/core-sample.svg){ loading=lazy width="360" }
```

### Rendered result

![Website and PDF review flow](../assets/core-sample.svg){ loading=lazy width="360" }

The website wraps the image in a GLightbox link for zooming. The static PDF
removes the interactive wrapper and retains the image at the authored size.

## Tooltips {: #tooltips }

Reference: [Zensical tooltips](https://zensical.org/docs/authoring/tooltips/)

### Source

```md
[Hover for the review note](#tooltips "Phase 4 tooltip text")
```

### Rendered result

[Hover for the review note](#tooltips "Phase 4 tooltip text")

The website exposes the title through its tooltip treatment. The PDF retains
the link text and destination without requiring hover interaction.

## Macros {: #macros }

Reference: [Zensical macros compatibility](https://zensical.org/docs/compatibility/mkdocs/plugins/#macros)

### Source

{% raw %}
```md
{{ catalogue_phase }}
```
{% endraw %}

### Rendered result

{{ catalogue_phase }}

The rendered text comes from the checked-in `catalogue_macros.py` module; raw
Jinja syntax must not leak into either output.
