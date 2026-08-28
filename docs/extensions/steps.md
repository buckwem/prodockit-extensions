---
icon: lucide/list-ordered
---

{{ heading_counter_reset(page) }}

# Numbered steps

\index{`prodockit.steps`} presents a procedure as numbered steps that a reader works
through in order. Each step has room for a title, instructions, commands, and
supporting content. A joining line makes the sequence clear on both the website
and in the PDF.

Use an ordinary numbered list for a list of facts. Use `prodockit.steps` when
the reader needs to complete one action before moving to the next.

## Enable the extension {: #steps-enabling-it }

Add the extension to `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.steps"]
```

## Write a procedure {: #steps-writing-one }

Copy this complete example:

````markdown
/// steps

//// step | Load the key into the agent

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519_gitlab
```

////

//// step | Upload the public key

Paste it into your host's SSH keys page.

////

///
````

It renders as:

/// steps

//// step | Load the key into the agent

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519_gitlab
```

////

//// step | Upload the public key

Paste it into your host's SSH keys page.

////

///

### Opening and closing the blocks

This extension uses the fenced-container syntax from
[PyMdown Blocks](https://facelessuser.github.io/pymdown-extensions/extensions/blocks/).
An opening fence names the block; its closing fence uses the same number of
slashes without the name. Nested blocks must use a different fence length. In
a numbered procedure:

- `/// steps` opens the complete ordered procedure; `///` closes it.
- `//// step` opens one step; `////` closes it.
- Add a title after `|`, as in `//// step | Upload the public key`.
- Leave off `|` and the title when a step needs only body content.

The blank line after a step header is not required for a simple paragraph, but
some block content needs it. Keeping the blank lines shown in the example is
the safe, consistent form for paragraphs, fenced code, admonitions, and content
tabs.

!!! warning "Fence lengths must differ when blocks are nested"
    The `step` fence uses four slashes because it is nested inside the
    three-slash `steps` fence. If a step contains another Blocks-based
    container, give that nested block another unused fence length.

!!! tip "Showing Markdown that contains a code fence"
    The copyable example uses four backticks around the complete Markdown
    sample because the sample itself contains a three-backtick `bash` fence.
    The outer fence must be longer than a fence inside it.

### Content inside a step

A step body is ordinary block Markdown. It can contain multiple paragraphs,
code fences, admonitions, or content tabs. For example, the
[Build your first site](../getting-started.md) walkthrough places macOS,
Windows, and Linux commands in tabs inside its first two steps.

## Configure numbered steps

There are no additional `prodockit.steps` settings in `zensical.toml`.
Configure each procedure inside its `/// steps` Markdown block.

### Continue numbering after a break {: #steps-continuing }

A long procedure can be split across sections or pages. Set `start` on the
later block so its first step continues at the required number:

=== "Markdown"

    ```markdown
    /// steps
        start: 9

    //// step | Point the clone at your own project

    Update the remote URL before pushing.

    ////

    ///
    ```

=== "Result"

    /// steps
        start: 9

    //// step | Point the clone at your own project

    Update the remote URL before pushing.

    ////

    ///

Options use YAML syntax. Put them directly below `/// steps`, with no blank
line between the header and its options, and indent each option by at least
four spaces. The blank line after the final option separates the options from
the procedure's content.

### Add an id or other HTML attributes

Use the Blocks API's `attrs` option to add attributes to the generated ordered
list. This complete example combines an id with continued numbering:

=== "Markdown"

    ```markdown
    /// steps
        start: 9
        attrs: {id: 'setup-continued'}

    //// step | Verify the remote

    Run `git remote -v` before pushing.

    ////

    ///
    ```

=== "Result"

    /// steps
        start: 9
        attrs: {id: 'setup-continued'}

    //// step | Verify the remote

    Run `git remote -v` before pushing.

    ////

    ///

`attrs` is inherited from the underlying Blocks API rather than defined by
`prodockit.steps`; `start` is the extension's only steps-specific option.

## Reference {: #steps-reference }

The block markers and options accepted by a steps block are summarised in
\ref{tab-extensions-steps-reference}.

| Syntax | Purpose |
| --- | --- |
| `/// steps` | Open or close the ordered procedure |
| `//// step` | Open or close one step without a title |
| `//// step \| Title` | Open one step with a title |
| \index{prodockit.steps!`start`}: 9 | Start this procedure at step 9 |
| `attrs: {...}` | Add HTML attributes to the generated `<ol>` |
/// table-caption | <
    attrs: {id: tab-extensions-steps-reference}

Reference
///

Each title becomes a separate paragraph before the step body. A step may have
no title, but every `step` must be inside a `steps` block for the resulting
HTML to be a valid ordered list.

## Customise the appearance {: #steps-generated-html }

Prodockit's managed `docs/stylesheets/pdk.css` contains the numbered-step
defaults used by the examples on this page. Put project-specific changes in
`docs/stylesheets/extra.css`, which is loaded afterwards.

### Generated HTML {: #steps-generated-html-structure }

The first example produces this structure:

```html
<ol class="prodockit-steps">
  <li>
    <p class="prodockit-step-title">Load the key into the agent</p>
    <pre><code>ssh-add --apple-use-keychain ~/.ssh/id_ed25519_gitlab</code></pre>
  </li>
  <li>
    <p class="prodockit-step-title">Upload the public key</p>
    <p>Paste it into your host's SSH keys page.</p>
  </li>
</ol>
```

The two stable class names are:

\ref{tab-extensions-steps-generated-html} identifies the stable HTML classes emitted for a procedure and its individual steps.

| Selector | Element |
| --- | --- |
| `ol.prodockit-steps` | The complete procedure |
| `.prodockit-step-title` | A step's optional title paragraph |
/// table-caption | <
    attrs: {id: tab-extensions-steps-generated-html}

Generated HTML
///

The title is an element rather than bold text, so it can be styled separately
from emphasis used in the step body.

If you override the rules from `pdk.css` in `extra.css`, retain these details:

- the joining line is positioned from the number's own size, so changing
  `--step-size` does not move the line away from the number;
- the line's `::after` pseudo-element uses the same `font-size` as the number's
  `::before` pseudo-element, keeping `em`-based measurements aligned;
- the final step has no trailing joining line.

The [bootstrap quick start](../devcons/bootstrap.md#bootstrap-quick-start) and
[Build your first site](../getting-started.md) are larger working examples.

Contributors changing the generated representation should read
[Extension integration](../devcons/extension-internals.md#preserve-website-and-pdf-block-behaviour).
