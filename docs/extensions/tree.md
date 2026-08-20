---
icon: lucide/folder-tree
---

# Directory trees

`prodockit.tree` turns an indented list of folders and files into a directory
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
        extra.css - website style sheet
        print.css - PDF style sheet
    zensical.toml - project configuration
    ///
    ```

=== "Result"

    /// tree
    docs/ - the documentation source tree
      index.md - the home page
      stylesheets/ - style sheets for the website and PDF
        extra.css - website style sheet
        print.css - PDF style sheet
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

| Option | Default | What it does |
|---|---|---|
| `indent` | `2` | How many spaces one level costs. Set `4` for a listing written that way. |
| `directory_icon` | `':lucide-folder:'` | Icon shortcode placed before every directory. |
| `file_icon` | `':lucide-file:'` | Icon shortcode placed before every file. |

```md
/// tree
    indent: 4

docs/
    index.md
///
```

Put options directly below `/// tree`. Indent each option by at least four
spaces, then leave a blank line before the listing. For example:

```md
/// tree
    directory_icon: ':octicons-file-directory-16:'
    file_icon: ':octicons-file-16:'

docs/
  index.md
///
```

### Fix indentation errors

A listing is read for its shape, so an entry attached to the wrong parent
is a diagram that is wrong and looks right. Rather than guess, the build
stops:

```text
TreeError: indent of 3 is not a multiple of 2: 'index.md'
TreeError: indented 2 levels at once: 'index.md'
```

### This repository, as a tree {: #tree-example }

The block above, used on something real - prodockit's own layout, so the
pages describing each extension can be found beside the module that
implements it:

/// tree
src/ - The package itself
  prodockit/ - Everything importable
    headings.py - Heading numbering and ids
    refs.py - Cross-references, resolved by number
    citations.py - Citations and their reference list
    glossary.py - Acronyms and the glossary
    bibliography.py - Bibliography rendering, through pandoc
    tables.py - Table column widths
    index.py - Back-of-book index markers
    steps.py - Numbered steps
    tree.py - This extension
    zensical_macros.py - The Jinja macros a Zensical build calls
    settings.py - Reading configuration out of zensical.toml
    cli.py - The `prodockit` command
    pins.py - `prodockit pins`, which manages build-input versions
    sync_repo.py - `prodockit sync-repo`
    init_tools.py - `prodockit init-tools` and `init-mathjax`
    tools.py - Finding git, pandoc and node when PATH cannot
    wordcount.py - Word counting for the cover page
    util.py - Shared helpers
    pdf/ - The PDF pipeline, not a Markdown extension
      build.py - Orchestrates pandoc and WeasyPrint
      css.py - The stylesheet the PDF is built with
      html.py - Fixing up each page's HTML before pandoc
      lua.py - The pandoc filter
      index.py - Building the back-of-book index from the laid-out PDF
      mermaid.py - Rendering diagrams to images
      source_bundle.py - `prodockit source-bundle`
      release.py - Resolving the release marker on the cover page
    bootstrap/ - `prodockit bootstrap`, machine setup
      stages.py - Every stage, as a check and a plan
      model.py - Hosts, runners and the stage record
      surrey.py - What a University of Surrey setup can derive
      fetch.py - Asking a URL what it says
      config.py - The questions and where the answers are kept
    testing/ - A pytest plugin projects can use on their own builds
docs/ - This documentation site
  extensions/ - A page per Markdown extension
  devcons/ - Design notes and the decisions behind them
  stylesheets/ - Including the stylesheets these extensions expect
tests/ - The test suite
tools/ - Node tooling used only by the PDF build
pyproject.toml - Packaging, dependencies and the entry points each extension registers
zensical.toml - This site's own configuration
///

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
CSS style sheet. This repository's `docs/stylesheets/extra.css` contains the
styles used by the examples on this page.

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

`docs/stylesheets/extra.css` in this repository carries a CSS style sheet to start
from. Keep the rail and stub positioned from one shared measurement, so
changing indentation cannot pull them apart, and stop the last child's rail at
its own stub rather than continuing past the final entry.
