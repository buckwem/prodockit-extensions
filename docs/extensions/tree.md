---
icon: lucide/folder-tree
---

{{ heading_counter_reset(page) }}

# Directory trees

\index{`prodockit.tree`} turns an indented list of folders and files into a directory
tree. Use it to show readers where files belong in a project.

## Enable the extension {: #tree-enabling-it }

```toml
[project.markdown_extensions."prodockit.tree"]
```

## Write a tree {: #tree-writing-one }

=== "Markdown"

    ```md
    /// tree
    docs/ - the documentation source tree
      index.md - the home page
      stylesheets/ - style sheets for the website and PDF
        pdk.css - managed website and PDF defaults
        extra.css - project website and PDF changes
        pdk-pdf.css - managed PDF defaults
        print.css - project PDF changes
    zensical.toml - project configuration
    ///
    ```

=== "Result"

    /// tree
    docs/ - the documentation source tree
      index.md - the home page
      stylesheets/ - style sheets for the website and PDF
        pdk.css - managed website and PDF defaults
        extra.css - project website and PDF changes
        pdk-pdf.css - managed PDF defaults
        print.css - project PDF changes
    zensical.toml - project configuration
    ///

The complete block starts and ends with a three-slash fence. Its body follows
three rules:

- **Indentation is the structure.** Two spaces per level by default.
- **A trailing `/` means a directory.** Anything else is a file. Nothing
  else marks one, so nothing else can disagree with it.
- **` - ` starts a description**, and it is optional. The spaces are
  required, which is what keeps `harvard-cite-them-right.csl` in one
  piece.

## Configure indentation and icons

There are no additional `prodockit.tree` settings in `zensical.toml`.
Configure each tree inside its Markdown block. Put the options directly below
`/// tree`, indent them by at least four spaces, and leave a blank line before
the listing:

| Option | Default | What it does |
|---|---|---|
| \index{prodockit.tree!`indent`} | `2` | How many spaces one level costs. Set `4` for a listing written that way. |
| `directory_icon` | `':lucide-folder:'` | Icon shortcode placed before every directory. |
| `file_icon` | `':lucide-file:'` | Icon shortcode placed before every file. |

This example changes both the indentation and the icons:

=== "Markdown"

    ```md
    /// tree
        indent: 4
        directory_icon: ':octicons-file-directory-16:'
        file_icon: ':octicons-file-16:'

    docs/
        index.md
    ///
    ```

=== "Result"

    /// tree
        indent: 4
        directory_icon: ':octicons-file-directory-16:'
        file_icon: ':octicons-file-16:'

    docs/
        index.md
    ///

### Fix indentation errors

A listing is read for its shape, so an entry attached to the wrong parent
is a diagram that is wrong and looks right. Rather than guess, the build
stops:

```text
TreeError: indent of 3 is not a multiple of 2: 'index.md'
TreeError: indented 2 levels at once: 'index.md'
```

### A report project {: #tree-example }

Use the block for a structure readers need to understand. This example shows
the main files supplied by `prodockit-template`:

/// tree
docs/
  index.md - cover page
  section1.md - first report section
  acronyms.md - acronym definitions
  glossary.md - glossary definitions
  references.md - generated reference list
  stylesheets/
    pdk.css - managed website and PDF defaults
    extra.css - project website and PDF changes
    pdk-pdf.css - managed PDF defaults
    print.css - project PDF changes
tools/
  mermaid/ - diagram renderer
  mathjax/ - maths renderer
zensical.toml - navigation and extension configuration
references.bib - bibliography source
///

The package's own source-code map now lives under
[Contributor internals](../devcons/development.md#find-the-code).

## Reference {: #tree-reference }

| Syntax or option | Purpose |
| --- | --- |
| `/// tree` | Open or close a directory tree |
| A trailing `/` | Mark an entry as a directory |
| ` - description` | Add an optional description |
| `indent: 4` | Use four spaces for each level instead of two |
| `directory_icon: '…'` | Choose the directory icon |
| `file_icon: '…'` | Choose the file icon |
| `attrs: {...}` | Add an id, class, or other attribute to the tree |

The `tree` block follows the same fence, option, and nesting rules as
[PyMdown Blocks](https://facelessuser.github.io/pymdown-extensions/extensions/blocks/).

## Customise the appearance {: #tree-what-it-produces }

The extension adds stable class names that you can target in your project's
CSS style sheet. Prodockit's managed `docs/stylesheets/pdk.css` contains the
default styles used by the examples on this page. Put project-specific
changes in `docs/stylesheets/extra.css`, which is loaded afterwards.

### Generated HTML {: #tree-generated-html }

The extension provides structure; your project supplies the appearance:

```html
<div class="prodockit-tree">
  <ul>
    <li class="tree-directory">
      <span class="tree-icon">…</span>
      <span class="tree-name">docs</span>
      <span class="tree-note">the documentation source tree</span>
      <ul>
        <li class="tree-file">
          <span class="tree-icon">…</span>
          <span class="tree-name">index.md</span>
        </li>
      </ul>
    </li>
  </ul>
</div>
```

Stable class names include `.prodockit-tree`, `.tree-directory`, `.tree-file`,
`.tree-icon`, `.tree-name`, and `.tree-note`.

`docs/stylesheets/pdk.css` carries the maintained starting point. When
overriding it in `docs/stylesheets/extra.css`, keep the rail and stub
positioned from one shared measurement, so changing indentation cannot pull
them apart, and stop the last child's rail at its own stub rather than
continuing past the final entry.
