# Website macros

`zendoc.zensical_macros` provides a handful of Jinja variables and macros
for Zensical's own [macros plugin](https://zensical.org/docs/authoring/macros/)
- the pieces a professional/academic report's website commonly wants that
aren't specific to any one project: a site-wide word count, the git-detected
repository URL, chapter/appendix numbering that continues across pages, and
reference/acronym/glossary list spacing that matches
[`zendoc.pdf`](pdf.md)'s own PDF output.

## Quick start

Add it alongside your own project's `macros.py` (which keeps anything
genuinely project-specific - a custom macro, institution branding, and so
on):

```toml
[project.markdown_extensions.zensical.extensions.macros]
module_name = "macros"
modules = ["zendoc.zensical_macros"]
```

Zensical's macros plugin loads `module_name` and every entry in `modules`,
merging all of their variables/macros into the same Jinja environment - so
a project with no macros of its own can drop `module_name`/`macros.py`
entirely and just use:

```toml
[project.markdown_extensions.zensical.extensions.macros]
modules = ["zendoc.zensical_macros"]
```

## Variables

| Variable | Description |
|---|---|
| `{{ word_count }}` | Prose word count across every nav page except the first (assumed to be the cover page) and any page flagged `exclude_from_word_count: true` in its own front matter - a comma-formatted string (e.g. `"9,971"`). |
| `{{ repo_url }}` | The fully-qualified `https://` URL for the current checkout's git `origin` remote (converted from `git@host:path.git` SSH syntax, with any embedded CI credentials stripped) - `""` if there's no git remote configured. |
| `{{ site_name }}` | `project.site_name` from `zensical.toml`. |

## Macros

| Macro | Description |
|---|---|
| `{{ heading_counter_reset(page) }}` | Place near the top of every page - continues chapter/section numbering (and the matching sidebar numbering) across pages, from this page's position in nav. See below. |
| `{{ reference_style() }}` | Place once near the top of a references page - controls `.reference` paragraph spacing. See below. |
| `{{ acronym_style() }}` | Place once near the top of an acronyms page - matches `reference_style()`'s default spacing. |
| `{{ glossary_style() }}` | Place once near the top of a glossary page - matches `reference_style()`'s default spacing. |

### `heading_counter_reset(page)`

Emits a `<style>` block that continues heading numbering from wherever the
*previous* page left off, using
[`zendoc.headings.prescan()`](extensions/headings.md) - the single source
of truth for what number/letter a page actually gets, so this always
matches what `\ref{}` resolves to for a heading on this page. Nothing else
needs to change when pages are reordered or headings are added/removed.

Set `project.extra.heading_numbering = false` in `zensical.toml` to turn
numbering off entirely (content and sidebar) across the whole site. A page
flagged `is_appendix: true` in its own front matter gets letter-based
numbering instead - "Appendix A", "A.1", "A.1.1" - matching
`zendoc.headings`' own `appendix_attr` default.

### `reference_style()` / `acronym_style()` / `glossary_style()`

Controls list-entry spacing, driven by the same `project.extra.*` settings
[`zendoc.pdf`](pdf.md) reads for the PDF, so both outputs stay in sync from
one configured value:

| Setting | Default | What it does |
|---|---|---|
| `reference_style` | `"european"` | `"european"`: single line spacing throughout, no indent, entries close together. `"global"`: single line spacing within each entry, double spacing *between* entries, with a hanging indent on wrapped lines (the common APA/MLA/Chicago style). Only `reference_style()`/the References page switches look - acronyms/glossary always use the tight "european" spacing. |
| `reference_spacing_european` | `"-0.8em"` | Gap between entries, "european" style - also used unconditionally for the acronym/glossary lists. |
| `reference_indent_global` | `"1.27cm"` | Hanging indent on wrapped lines, "global" style. |
| `reference_spacing_global` | `"2em"` | Gap between entries, "global" style. |

## Status

No formal, versioned public API stability contract yet (see
[zendoc-extensions#7](https://github.com/buckwem/zendoc-extensions/issues/7)).
