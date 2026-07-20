# Index terms

`prodockit.index` marks a term inline, wherever it's actually discussed,
for [prodockit.pdf](../pdf.md)'s own PDF-only back-of-book index (an
alphabetised list of terms with the page number(s) they appear on) - the
term both displays exactly as written and is marked for indexing in one
go, no separate "definition" step needed anywhere else, unlike
[prodockit.citations](citations.md)/[prodockit.glossary](glossary.md).

This is a Markdown extension at all - rather than the `attr_list`
convention every other prodockit extension's own marker syntax uses -
because plain `attr_list` can't wrap arbitrary inline text in a span on
its own: confirmed directly, `` [Term]{.index} `` is left as literal
text (attr_list only reaches inline content already wrapped in something
it recognises - emphasis, a link, code - each of which would force an
unwanted visual side effect just to mark a term). Raw inline HTML
(`<span class="index">Term</span>`) works today with no extension at
all, but is exactly the "disrupts normal writing flow" outcome a good
marker syntax should avoid.

## Quick start

Enable it in `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.index"]
```

then mark a term with `\index{Term}`:

=== "Markdown"

    ```md
    A \index{widget} is the basic unit of work.

    Later, this \index{widget} gets combined with a \index{gadget}.
    ```

=== "Result"

    A \index{widget} is the basic unit of work.

    Later, this \index{widget} gets combined with a \index{gadget}.

Every marked term renders inline exactly as written - `\index{widget}`
becomes plain "widget" text, nothing more, on the live website. The
marker only has an effect on the *PDF*, and only once `pdf_include_index`
is on - there's no back-of-book index on a website at all, since readers
use browser/Ctrl-F search instead. See
[Back-of-book index](../pdf.md#back-of-book-index) for what the
generated index page itself looks like, and why it needs a real two-pass
PDF build.

The same term marked more than once merges into one index entry (case-
insensitively - "Widget" and "widget" become one entry, keeping whichever
casing was used first; "widgets" is still a separate entry from "widget" -
no plural/singular normalisation).

## CSS hooks

`\index{Term}` always renders as `<span class="index">Term</span>` - no
other class or attribute, and nothing left behind to strip: unlike
`prodockit.refs`/`prodockit.citations`/`prodockit.glossary`, there's no
resolved/unresolved state to distinguish (nothing to resolve - a term
either renders or the whole page fails to parse), so no extra styling
hook is needed by default. A project wanting to visually highlight
indexed terms on the live website can target `.index` directly.
