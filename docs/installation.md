---
icon: lucide/package-plus
---

{{ heading_counter_reset(page) }}

# Installation

This is the manual setup route. Use it when you want to choose and install the
package, external tools, and enabled extensions directly. The alternatives are
[adoption](adopt.md), which integrates prodockit into an established document,
and [bootstrap](devcons/bootstrap.md), which prepares a machine and a project
based on `prodockit-template`. Bootstrap is not a general installer for an
unrelated Zensical project.

## Requirements

**Python 3.10 or later.** Tested on 3.10, 3.11, 3.12, 3.13 and 3.14; `pip` will
refuse to install on anything older rather than failing later at import.

Everything below is pulled in automatically by `pip install prodockit`,
except where noted:

\ref{tab-installation-requirements} lists the runtime dependencies installed with prodockit and explains why each one is needed.

| Requirement {: width="36%" } | Needed for |
| --- | --- |
| [`Markdown`](https://python-markdown.github.io/) (>= 3.10.3) | every extension |
| [`zensical`](https://zensical.org/) (>= 0.0.57) | Zensical integration and `prodockit.zensical_macros` |
| [PyMdown Extensions](https://facelessuser.github.io/pymdown-extensions/) (>= 11.0.2) | `prodockit.steps` and `prodockit.tree` are built directly on the PyMdown Blocks API; `prodockit.pdf` also preserves the output of PyMdown features |
| [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) (>= 4.12) | `prodockit.pdf` |
| \index{dependencies!`click`} (>= 8.0) | the `prodockit` command-line tool |
| [`PyYAML`](https://pyyaml.org/) (>= 6.0) | `prodockit adopt` support for existing `mkdocs.yml`/`mkdocs.yaml` projects |
| [`packaging`](https://packaging.pypa.io/) (>= 24.0) | comparing an adopted project's recorded Prodockit version floor with the installed release |
| \index{dependencies!`pypdf`} (>= 4.0) | `prodockit.pdf` |
| \index{dependencies!`tomli`} (>= 2.0) | reading a template manifest on Python 3.10, where `tomllib` does not exist yet |
| \index{dependencies!`pymupdf`} (>= 1.24) | only the back-of-book index - `pip install prodockit[index]` |
/// table-caption | <
    attrs: {id: tab-installation-requirements}

Requirements
///

The floors in \ref{tab-installation-requirements} are the ones declared in
`pyproject.toml`, and a test keeps the table in step with them - the two had
drifted apart, with
`Markdown` recorded here as >= 3.4 long after the real floor moved to
3.10.3 (prodockit-extensions#372).

### Not installed by pip {: #installation-external }

These are the ones `pip install prodockit` does **not** bring, and they
differ in kind:

\ref{tab-installation-not-installed-by-pip} identifies the external tools that pip cannot install and the features that use them.

| Requirement {: width="36%" } | Needed for |
| --- | --- |
| \index{dependencies!`weasyprint`} (>= 69) | `prodockit.pdf`. A Python package, but not a dependency of prodockit - install it yourself. `prodockit.pdf` runs its command-line rather than importing it |
| \index{dependencies!`pandoc`} (>= 3, builds pin 3.10.1) | `prodockit.pdf`, and `prodockit.bibliography` even without a PDF build. Genuinely not a Python package - there is nothing for `pip` to install |
| \index{dependencies!`mermaid-cli`}, `mathjax-full` (Node >= 22) | only Mermaid diagrams and TeX maths in the PDF |
| Chrome or Chromium | only Mermaid diagrams - `mermaid-cli` renders them through a headless browser |
| A citation style (`.csl`) | only `prodockit.bibliography`. Fetched per build, not vendored - see below |
/// table-caption | <
    attrs: {id: tab-installation-not-installed-by-pip}

Not installed by pip
///

The citation style is a download rather than an install. Pandoc
resolves `harvard-cite-them-right.csl` from the directory it runs in, and
every CI script here fetches it immediately before building:

```bash
curl -fsSL -o harvard-cite-them-right.csl "https://www.zotero.org/styles/harvard-cite-them-right"
```

It is deliberately **not** committed: it is third-party content with its
own licence and its own release cadence, and a vendored copy would go
stale silently while every build kept succeeding. `prodockit bootstrap`
fetches it for a bootstrapped project. An adopted or manually installed
project can fetch it in its own build workflow, and `.gitignore` should keep a
local copy out of commits.

`weasyprint` is worth separating from `pandoc` rather than filing both as
"external binaries": one is a `pip install` away and the other is not,
and a reader who treats them alike goes looking for a package that does
not exist, or misses one that does.

Pandoc is version-sensitive in a way that changes output rather than
breaking the build: a major version below 3 renders code blocks as
justified prose, and the builds pin an exact release because two 3.x
versions have already disagreed about the same source. `prodockit
bootstrap` installs the pinned version where a package manager allows it
and tells you when your local pandoc differs - see
[Pinning build inputs](devcons/pinning-drift.md).

See [PDF generation](pdf.md) for how `prodockit.pdf` locates these, and
[Known limitations](about/limitations.md) for why the Node
ones are needed at all. A build with neither Mermaid diagrams nor maths
needs neither of them, and no browser.

## From PyPI

Install the current prodockit package into the active project environment:

```bash
pip install prodockit
```

For a minimal project that needs no PDF toolchain, continue with
[Build your first site](getting-started.md). The external tools above can be
added later when the document needs their features.

## Enabling an extension

Each prodockit extension is registered as a standard Python-Markdown extension
under the `markdown.extensions` entry point group, so it can be enabled by
name, the same way you'd enable a built-in extension like `toc` or a
`pymdownx` one:

```python
import markdown

html = markdown.markdown(
    text,
    extensions=["prodockit.headings", "prodockit.refs", "prodockit.tables"],
)
```

Or, for a [Zensical](https://zensical.org/) project, in `zensical.toml`
alongside the built-in and `pymdownx` extensions. Unlike `pymdownx`'s and
Zensical's own namespaces, Zensical doesn't hoist a nested
`prodockit.headings` table into that dotted extension name, so each one needs
a quoted key instead:

```toml
[project.markdown_extensions."prodockit.headings"]
[project.markdown_extensions."prodockit.refs"]
[project.markdown_extensions."prodockit.citations"]
[project.markdown_extensions."prodockit.glossary"]
[project.markdown_extensions."prodockit.tables"]
[project.markdown_extensions."prodockit.tree"]
[project.markdown_extensions."prodockit.steps"]
[project.markdown_extensions."prodockit.bibliography"]
[project.markdown_extensions."prodockit.index"]
```

Enable only the ones you use - each is independent, and none of them
requires another.

### The nine extensions {: #installation-the-extensions }

See each extension's own page for its syntax, examples, and configuration:

\ref{tab-installation-the-nine-extensions} maps each Markdown extension to the authoring feature it provides.

| Extension {: width="40%" } | What it adds |
| --- | --- |
| [`prodockit.headings`](extensions/headings.md) | Numbered headings, and a number a cross-reference can point at |
| [`prodockit.refs`](extensions/refs.md) | Cross-references that resolve to a number *and* a name |
| [`prodockit.citations`](extensions/citations.md) | Citation handling |
| [`prodockit.glossary`](extensions/glossary.md) | Acronyms and a glossary |
| [`prodockit.tables`](extensions/tables.md) | Column widths, dense tables, multi-row headers, merged cells, rotated headings |
| [`prodockit.tree`](extensions/tree.md) | A directory listing that looks like one |
| [`prodockit.steps`](extensions/steps.md) | Numbered steps a reader works through in order |
| [`prodockit.bibliography`](extensions/bibliography.md) | A bibliography built from your `.bib` files |
| [`prodockit.index`](extensions/index-terms.md) | A back-of-book index (PDF only) |
/// table-caption | <
    attrs: {id: tab-installation-the-nine-extensions}

The nine extensions
///

### What is *not* an extension {: #installation-not-extensions }

Several parts of prodockit have no `markdown.extensions` entry point and
nothing to add to `zensical.toml`, because they are not Markdown syntax:

\ref{tab-installation-what-is-not-an-extension} distinguishes the standalone commands and integrations from Markdown extensions.

| | |
| --- | --- |
| [`prodockit pdf`](pdf.md) | A separate PDF-generation build step |
| [`prodockit source-bundle`](pdf.md#bundling-source-into-a-pdf) | Packages documentation source as a separate PDF |
| [`prodockit.zensical_macros`](macros.md) | A `define_env()` module for Zensical's macros plugin, named under its `modules` config rather than as an extension |
| [`prodockit.testing`](devcons/testing.md) | pytest fixtures and checks for an already-built site and PDF |
| [`prodockit bootstrap`](devcons/bootstrap.md) | Sets up a machine and a project based on `prodockit-template` |
| [`prodockit sync-repo`](devcons/repo-metadata.md) | Keeps repository metadata and README badges matching the git remote |
| [`prodockit pins`](devcons/pinning-drift.md) | Moves build-input version pins together |
| [`prodockit template-sync`](devcons/template-sync.md) | Brings a project back into step with the template it came from |
| [`prodockit init-tools` / `init-mathjax`](command-line.md#publish-and-verify) | Sets up optional Mermaid and maths rendering tools |
/// table-caption | <
    attrs: {id: tab-installation-what-is-not-an-extension}

What is not an extension
///

Contributors changing the package itself should use the editable installation
and repository checks in
[Development and code map](devcons/development.md#create-a-development-environment).
