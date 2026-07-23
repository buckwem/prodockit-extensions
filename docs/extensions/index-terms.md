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

## Quick start {: #index-terms-quick-start }

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

## Sub-entries

`\index{Parent!Child!Grandchild}` - `!` separates up to three levels in
practice, matching LaTeX `makeidx`'s own long-established
`\index{primary!secondary!tertiary}` convention - nests a term under
another, the same way a printed book's own index groups related entries
together (e.g. "staging area" with "adding"/"modified" indented beneath
it) rather than listing every term as one flat alphabetical run:

=== "Markdown"

    ```md
    Now generate the \index{Git!ssh keys} to use for authentication.
    ```

=== "Result"

    Now generate the \index{Git!ssh keys} to use for authentication.

Only the *last* segment displays inline (`ssh keys` above) - wherever the
term is actually mentioned in your prose - the earlier segments (`Git`)
are only ever used to build the generated index's own nesting, and never
appear inline themselves. See
[Back-of-book index](../pdf.md#back-of-book-index) for what a nested
index entry looks like once built.

## Code-styled terms

Backticks around the *last* segment mark a command or other code term -
it displays inline in a real `<code>` element instead of plain text, and
the generated index entry renders the same way:

=== "Markdown"

    ```md
    Run \index{`git commit`} to save your changes.
    ```

=== "Result"

    Run \index{`git commit`} to save your changes.

Combine this with [sub-entries](#sub-entries) by putting the backticks
around just the last segment - nesting a code-styled `git commit` entry
under a plain `Git` one:

```md
\index{Git!`git commit`}
```

!!! note "Showing this syntax as literal example text"
    Unlike a plain `\index{Term}` (protected by a real code span, the same
    way this page's own examples above are written), the code-styled
    pattern has to run *before* Python-Markdown's own backtick handling,
    so it can recognise its own inner backticks - a side effect is that
    wrapping the whole call in inline backticks doesn't protect it the
    way it does for the plain syntax. A fenced code block (as every
    example on this page already uses) still works, since it's stashed
    before any inline pattern - this one included - ever runs.

## Linked terms

A term can be a markdown link - the same "not exempted from later inline
passes" behaviour that lets `\index{*emphasised*}` work also resolves a
link, rather than leaving `[Text](url)` as literal text:

=== "Markdown"

    ```md
    \index{[Git](https://git-scm.com/)} is a version control system.
    ```

=== "Result"

    \index{[Git](https://git-scm.com/)} is a version control system.

`prodockit.pdf.index`'s own `mark_index_terms()` still extracts the
plain "Git" text correctly either way - it already strips a nested
`<code>`/`<em>` the same way, via BeautifulSoup's `get_text()`.

!!! warning "`attr_list` (`{target="_blank"}`) doesn't combine cleanly"
    This project's own convention for an external link -
    `` [Git](https://git-scm.com/){target="_blank"} `` - doesn't work
    wrapped in `\index{}`: `attr_list` attaches the attribute to
    whichever element comes immediately before it, which after
    `\index{}` processes is the *outer* `<span class="index">`, not the
    link itself - a `target` on a `<span>` does nothing, silently losing
    the "open in a new tab" behaviour. Putting the attribute *inside* the
    `\index{}` call doesn't work either, since its own `{`/`}` braces
    confuse `\index{}`'s own regex, which stops at the first `}` it
    finds. If you need `target="_blank"` on a linked term, use a raw
    inline `<a>` tag instead, which needs no `attr_list` at all:

    ```md
    \index{<a href="https://git-scm.com/" target="_blank">Git</a>} is a version control system.
    ```

## CSS hooks {: #index-terms-css-hooks }

A flat `\index{Term}` renders as `<span class="index">Term</span>` - no
other class or attribute, and nothing left behind to strip. A
hierarchical `\index{Parent!Child}` additionally carries the full path on
`data-index-term` (`<span class="index"
data-index-term="Parent!Child">Child</span>`), read by
`prodockit.pdf.index` to build the nested index - harmless for a
project's own CSS, which would only ever need to target the shared
`.index` class either way. A [code-styled term](#code-styled-terms)
further carries `data-index-code="true"` and wraps its own text in a real
`<code>` element (`<span class="index" data-index-code="true"
data-index-term="Term"><code>Term</code></span>`) - picking up whatever
`code {}` styling your project already has, on the website and in the
generated index alike, with nothing extra to configure. Unlike
`prodockit.refs`/`prodockit.citations`/`prodockit.glossary`, there's no
resolved/unresolved state to distinguish (nothing to resolve - a term
either renders or the whole page fails to parse), so no extra styling
hook is needed by default. A project wanting to visually highlight
indexed terms on the live website can target `.index` directly.
