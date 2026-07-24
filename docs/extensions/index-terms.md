# Index (pdf-only)

`prodockit.index` marks a term inline, wherever it's actually discussed,
for a PDF-only back-of-book index (an alphabetised list of terms with the
page number(s) they appear on) - the term both displays exactly as
written and is marked for indexing in one go, no separate "definition"
step needed anywhere else, unlike
[prodockit.citations](citations.md)/[prodockit.glossary](glossary.md).
Marking and generating the index are both covered on this page - PDF-only
(there's no equivalent on the live website, where readers use
browser/Ctrl-F search instead), but the actual index page is built by
[prodockit.pdf](../pdf.md), via the `prodockit.pdf.index` module - see
[`prodockit.pdf.index`](../pdf.md#prodockitpdfindex) if you're scripting
your own build pipeline rather than using `prodockit pdf`/`zensical.toml`.

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

## Requirements {: #index-terms-requirements }

Marking a term needs nothing beyond the extension itself. Actually
*generating* the index page additionally needs the optional `pymupdf`
dependency (a term's own page number can only be known once WeasyPrint
has already laid the PDF out once - see
[Generating the index](#index-terms-generating-the-index) below for why):

```bash
pip install prodockit[index]   # or plain: pip install pymupdf
```

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
is on - see [Generating the index](#index-terms-generating-the-index)
below for the generated index page itself.

The same term marked more than once merges into one index entry (case-
insensitively - "Widget" and "widget" become one entry, keeping whichever
casing was used first; "widgets" is still a separate entry from "widget" -
no plural/singular normalisation).

## Generating the index {: #index-terms-generating-the-index }

Set `pdf_include_index = true` under `[project.extra]` in `zensical.toml`
for a traditional, two-column back-of-book index - terms grouped under a
bold letter heading (A, B, C, ...), each followed by the page number(s)
it appears on - appended as its own page(s) at the very end of the
document:

```toml
[project.extra]
pdf_include_index = true
pdf_index_title = "Index"   # optional - that page's own heading text
```

The `\index{widget}`/`\index{gadget}` example above renders to an index
page like:

```text
Index

G
Gadget, 3

W
Widget, 1, 3
```

with its own page list deduplicated and sorted; consecutive pages
collapse into an en-dash range (`67–70`) rather than listing every page
individually, and non-consecutive pages/ranges are comma-separated (`64,
175`) - standard back-of-book index convention.

A term is alphabetised (and letter-grouped) ignoring any leading
punctuation - `--set-upstream option (git push)` and `-u option (git
branch)` are filed under **S** and **U** respectively (matching where
"set-upstream"/"u" itself would sort), not lumped into a separate
"symbols" section, the same way a technical book's own index treats
command-line options.

This is the one feature in `prodockit.pdf` that genuinely needs a
two-pass build: a term's own page number can only be known once
WeasyPrint has already laid the whole PDF out once - confirmed directly,
before settling on this design, that CSS's own `target-counter()` *can*
resolve a page number in a single pass, but can't deduplicate two markers
that land on the same page (nothing on the Python side can know that
without already knowing the layout) - accepted as a real limitation and
not used here, in favour of a genuinely clean, deduplicated index. See
[`prodockit.pdf.index`](../pdf.md#prodockitpdfindex) for exactly how the
two passes work, if you're scripting your own build pipeline.

## Sub-entries {: #index-terms-sub-entries }

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
appear inline themselves. Renders a nested entry like:

```text
G

Git
    ssh keys, 13, 89
```

A parent with no marker of its own anywhere (like `Git` above) still gets
its own line - a bare category label with no trailing page list - so its
children have somewhere to nest under.

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

Combine this with [sub-entries](#index-terms-sub-entries) by putting the
backticks around just the last segment - nesting a code-styled `git
commit` entry under a plain `Git` one:

```md
\index{Git!`git commit`}
```

Both render an index entry in your document's own monospace font,
matching how the term already displays inline:

```text
G

Git
    git commit, 13, 89
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
