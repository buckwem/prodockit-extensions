---
icon: lucide/braces
---

{{ heading_counter_reset(page) }}

# Website macros {: #macros-website-macros }

\index{`prodockit.zensical_macros`} provides a handful of Jinja variables and macros
for Zensical's own [macros plugin](https://zensical.org/docs/authoring/macros/)
- the pieces a professional/academic report's website commonly wants that
aren't specific to any one project: a site-wide word count, the git-detected
repository URL, the latest release tag, chapter/appendix numbering that
continues across pages, and reference/acronym/glossary list spacing that
matches [`prodockit.pdf`](pdf.md)'s own PDF output.

## Quick start {: #macros-quick-start }

Add it alongside your own project's `macros.py` (which keeps anything
genuinely project-specific - a custom macro, institution branding, and so
on):

```toml
[project.markdown_extensions.zensical.extensions.macros]
module_name = "macros"
modules = ["prodockit.zensical_macros"]
on_error_fail = true
```

Zensical's macros plugin loads `module_name` and every entry in `modules`,
merging all of their variables/macros into the same Jinja environment - so
a project with no macros of its own can drop `module_name`/`macros.py`
entirely and just use:

```toml
[project.markdown_extensions.zensical.extensions.macros]
modules = ["prodockit.zensical_macros"]
on_error_fail = true
```

Keep `on_error_fail = true` in automated and local builds. If Jinja cannot
render a page variable or macro call, Zensical then stops the build instead of
returning the unrendered page and allowing a broken site to be published.

## Variables

The values exposed directly to page templates are listed in
\ref{tab-macros-variables}.

| Variable {: width="32%" } | Description |
|---|---|
| `{% raw %}{{ word_count }}{% endraw %}` | Prose word count across every nav page except the first (assumed to be the cover page) and any page flagged `exclude_from_word_count: true` in its own front matter - a comma-formatted string (e.g. `"9,971"`). |
| `{% raw %}{{ repo_url }}{% endraw %}` | The fully-qualified `https://` URL for the current checkout's git `origin` remote (converted from `git@host:path.git` SSH syntax, with any embedded CI credentials stripped) - `""` if there's no git remote configured. |
| `{% raw %}{{ release }}{% endraw %}` | The latest git tag reachable from `HEAD` (e.g. `"1.2.0"`) - `""` if this checkout has no tags at all. Resolves identically for the website and for `prodockit pdf`, since both render through this same macro environment - unlike `prodockit.pdf`'s own [`{RELEASE}` cover-page marker](pdf.md#cover-page-markers), which queries the host's GitHub/GitLab API instead, for a project whose cover page isn't part of a live, macro-rendered site at all. |
| `{% raw %}{{ site_name }}{% endraw %}` | `project.site_name` from `zensical.toml`. |
/// table-caption | <
    attrs: {id: tab-macros-variables}

Variables
///

## Macros

\ref{tab-macros-macros} lists the callable helpers and the content each one
inserts.

| Macro {: width="38%" } | Description |
|---|---|
| `{% raw %}{{ heading_counter_reset(page) }}{% endraw %}` | Place near the top of every page - continues chapter/section numbering (and the matching sidebar numbering) across pages, from this page's position in nav. See below. |
| `{% raw %}{{ reference_style() }}{% endraw %}` | Place once near the top of a references page - controls `.reference` paragraph spacing. See below. |
| `{% raw %}{{ acronym_style() }}{% endraw %}` | Place once near the top of an acronyms page - matches `reference_style()`'s default spacing. |
| `{% raw %}{{ glossary_style() }}{% endraw %}` | Place once near the top of a glossary page - matches `reference_style()`'s default spacing. |
/// table-caption | <
    attrs: {id: tab-macros-macros}

Macros
///

## Show macro syntax as text {: #macros-literal-syntax }

The macros plugin processes Jinja delimiters before Markdown code formatting.
Backticks therefore do not protect a literal macro example. A literal
`{% raw %}{{ word_count }}{% endraw %}`, GitHub expression, or compact
`{% raw %}{#heading-id}{% endraw %}` example can stop every macro on that page
from being rendered.

When readers should see the syntax rather than run it, wrap the literal text
between <code>&#123;% raw %&#125;</code> and
<code>&#123;% endraw %&#125;</code> in the Markdown source. For example:

<pre><code>&#123;% raw %&#125;
&#123;&#123; word_count &#125;&#125;
$&#123;&#123; github.token &#125;&#125;
&#123;#heading-id&#125;
&#123;% endraw %&#125;</code></pre>

The raw wrapper is removed from the website and the intended braces remain.
Use an unwrapped expression when it is meant to run.

### `heading_counter_reset(page)`

Continues heading numbering from wherever the previous page left off. The
numbering stays aligned with `\ref{}` links and updates when pages are
reordered or headings are added or removed.

Set `project.extra.heading_numbering = false` in `zensical.toml` to turn
numbering off entirely (content and sidebar) across the whole site. A page
flagged `is_appendix: true` in its own front matter gets letter-based
numbering instead - "Appendix A", "A.1", "A.1.1" - matching
`prodockit.headings`' own `appendix_attr` default.

Contributors changing how page numbers are discovered should read
[Extension integration](devcons/extension-internals.md#share-definitions-across-pages).

### `reference_style()` / `acronym_style()` / `glossary_style()`

Controls list-entry spacing, driven by the same `project.extra.*` settings
[`prodockit.pdf`](pdf.md) reads for the PDF, so both outputs stay in sync from
one configured value:

\ref{tab-macros-reference-style-acronym-style-glossary-style} shows which configured style value each helper returns.

| Setting {: width="32%" } | Default | What it does |
|---|---|---|
| \index{prodockit.zensical_macros!`reference_style`} | `"european"` | `"european"`: single line spacing throughout, no indent, entries close together. `"global"`: single line spacing within each entry, double spacing *between* entries, with a hanging indent on wrapped lines (the common APA/MLA/Chicago style). Only `reference_style()`/the References page switches look - acronyms/glossary always use the tight "european" spacing. |
| \index{prodockit.zensical_macros!`reference_spacing_european`} | `"-0.8em"` | Gap between entries, "european" style - also used unconditionally for the acronym/glossary lists. |
| \index{prodockit.zensical_macros!`reference_indent_global`} | `"1.27cm"` | Hanging indent on wrapped lines, "global" style. |
| \index{prodockit.zensical_macros!`reference_spacing_global`} | `"2em"` | Gap between entries, "global" style. |
/// table-caption | <
    attrs: {id: tab-macros-reference-style-acronym-style-glossary-style}

reference_style() / acronym_style() / glossary_style()
///

For supported versions and the pre-1.0 stability boundary, see
[Support and compatibility](about/support.md).

## Page dates are not macros

Build-derived dates do not require the macros plugin. Use
[Page update dates](update-dates.md) to choose where a website date appears,
write its accompanying text, or override one page's automatic date.
