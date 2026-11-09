---
icon: lucide/map-pin
---

{{ pdk_heading_counter_reset(page) }}

# Image hotspots

Turn regions of a map, diagram or other local raster image into links. Hotspots
follow the image as it resizes. On the website, a list beneath the image
offers the same destinations as text links. In a Prodockit PDF, click
the corresponding region directly on the image.

## Enable image hotspots

Add the `image-hotspots` fence to the existing SuperFences configuration in
`zensical.toml`. Keep any other fences already configured.

```toml
[project.markdown_extensions.pymdownx.superfences]
custom_fences = [
  { name = "image-hotspots", class = "image-hotspots", format = "prodockit.image_hotspots.format_hotspots" },
]
```

Load the managed `stylesheets/pdk.css` in `extra_css`. After upgrading
Prodockit in an existing project, run `pdk shared-files --apply` to refresh
the stylesheet.

## Define the rectangles

Write each `rect` as `[left, top, width, height]` in **source-image pixels**,
measured from the top-left corner. Use the original dimensions shown in an
image editor. Prodockit reads the local image's dimensions at build time and
converts the horizontal values to percentages of its width and the vertical
values to percentages of its height.

Use a path to an image inside the docs directory, relative to the Markdown
page. Supply image alt text and a descriptive label for each link. An `href`
can be a same-page fragment, a relative documentation link such as
`../pdf.md`, or a full HTTP(S) URL. Quote fragments in YAML because `#`
starts a comment. The hotspot focus order follows the order in the block.

## Example 1 · Alton Public Gardens

Each red pin links to its corresponding stop below the map. This image is
939 × 987 pixels.

~~~markdown
```image-hotspots
image: ../assets/alton-public-gardens-labels.png
alt: Map of Alton Public Gardens with four numbered pins.
hotspots:
  - { label: "Public Gardens stop 1", href: "#stop-1", rect: [624, 417, 38, 59] }
  - { label: "Public Gardens stop 2", href: "#stop-2", rect: [115, 168, 39, 59] }
  - { label: "Public Gardens stop 3", href: "#stop-3", rect: [213, 435, 39, 59] }
  - { label: "Public Gardens stop 4", href: "#stop-4", rect: [409, 618, 40, 59] }
```
~~~

```image-hotspots
image: ../assets/alton-public-gardens-labels.png
alt: Map of Alton Public Gardens with four numbered pins.
hotspots:
  - { label: "Public Gardens stop 1", href: "#stop-1", rect: [624, 417, 38, 59] }
  - { label: "Public Gardens stop 2", href: "#stop-2", rect: [115, 168, 39, 59] }
  - { label: "Public Gardens stop 3", href: "#stop-3", rect: [213, 435, 39, 59] }
  - { label: "Public Gardens stop 4", href: "#stop-4", rect: [409, 618, 40, 59] }
```

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).

### Stop 1 { #stop-1 }

The east side of the gardens, near Lady Place car park.

### Stop 2 { #stop-2 }

The northwest edge, alongside Westbrooke Road.

### Stop 3 { #stop-3 }

The western path near the circular path feature.

### Stop 4 { #stop-4 }

The junction of paths near the centre of the gardens.

## Example 2 · Prodockit authoring feature map

The first two boxes in the middle column jump to headings below the diagram.
The third opens the online PDF guide using its full HTTPS URL. This image is
2509 × 1013 pixels.

~~~markdown
```image-hotspots
image: ../assets/diagrams/7.1-authoring-feature-map.png
alt: Flowchart grouping authoring features by structure, evidence, and calculated outputs.
hotspots:
  - { label: "Structure and layout", href: "#structure-and-layout", rect: [692, 10, 442, 222] }
  - { label: "Evidence and navigation", href: "#evidence-and-navigation", rect: [692, 390, 442, 222] }
  - { label: "Calculated values and outputs", href: "https://prodockit.org/pdf/", rect: [692, 771, 442, 222] }
```
~~~

```image-hotspots
image: ../assets/diagrams/7.1-authoring-feature-map.png
alt: Flowchart grouping authoring features by structure, evidence, and calculated outputs.
hotspots:
  - { label: "Structure and layout", href: "#structure-and-layout", rect: [692, 10, 442, 222] }
  - { label: "Evidence and navigation", href: "#evidence-and-navigation", rect: [692, 390, 442, 222] }
  - { label: "Calculated values and outputs", href: "https://prodockit.org/pdf/", rect: [692, 771, 442, 222] }
```

### Structure and layout { #structure-and-layout }

Use headings, tables, directory trees and numbered steps to organise the
document.

### Evidence and navigation { #evidence-and-navigation }

Use cross-references, citations, a bibliography, a glossary or an index to
connect readers to supporting material.
