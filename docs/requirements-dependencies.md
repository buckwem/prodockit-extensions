---
icon: lucide/package-search
---

{{ heading_counter_reset(page) }}

# Requirements and dependencies

This chapter records the software Prodockit uses, the version floors declared
by the package, and the external tools that Python package installation cannot
supply. Authors normally do not need to select these versions individually:
use `prodockit pins` whenever a project must be returned to the supported,
tested combination.

The supported preparation route uses Python 3.14. The package's technical
floor remains Python 3.10, and installation is tested on 3.10, 3.11, 3.12,
3.13 and 3.14; `pip` refuses older versions before import.

## Installed with Prodockit

Everything in this section is pulled in automatically by
`pip install prodockit`, except where noted.

\ref{tab-installation-requirements} lists the runtime dependencies installed
with Prodockit and explains why each one is needed.

| Requirement {: width="36%" } | Needed for |
| --- | --- |
| [`Markdown`](https://python-markdown.github.io/) (>= 3.10.3) | every extension |
| [`zensical`](https://zensical.org/) (>= 0.0.59) | Zensical integration and `prodockit.zensical_macros` |
| [PyMdown Extensions](https://facelessuser.github.io/pymdown-extensions/) (>= 11.0.2) | `prodockit.steps` and `prodockit.tree` are built directly on the PyMdown Blocks API; `prodockit.pdf` also preserves the output of PyMdown features |
| [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) (>= 4.12) | `prodockit.pdf` |
| \index{dependencies!`click`} (>= 8.0) | the `prodockit` command-line tool |
| [`PyYAML`](https://pyyaml.org/) (>= 6.0) | `prodockit adopt` support for Zensical projects that retain a compatible `mkdocs.yml` or `mkdocs.yaml` configuration filename |
| [`packaging`](https://packaging.pypa.io/) (>= 24.0) | comparing an adopted project's recorded Prodockit version floor with the installed release |
| \index{dependencies!`pypdf`} (>= 4.0) | `prodockit.pdf` |
| \index{dependencies!`tomli`} (>= 2.0) | reading a template manifest on Python 3.10, where `tomllib` does not exist yet |
| \index{dependencies!`pymupdf`} (>= 1.24) | only the back-of-book index - `pip install prodockit[index]` |
/// table-caption | <
    attrs: {id: tab-installation-requirements}

Requirements installed with Prodockit
///

The floors in \ref{tab-installation-requirements} are declared in
`pyproject.toml`, and a test keeps the table in step with them. They are
compatibility floors, not a recommendation to assemble a toolchain from each
minimum independently. Run `prodockit pins` to select the supported set.

## Not installed by pip {: #requirements-external }

The requirements in this section are not supplied by
`pip install prodockit`, and they differ in kind.

\ref{tab-installation-not-installed-by-pip} identifies the external tools that
pip cannot install and the features that use them.

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

The citation style is a download rather than an install. Pandoc resolves
`harvard-cite-them-right.csl` from the directory it runs in, and every CI
script here fetches it immediately before building:

```bash
curl -fsSL -o harvard-cite-them-right.csl "https://www.zotero.org/styles/harvard-cite-them-right"
```

It is deliberately not committed: it is third-party content with its own
licence and release cadence. `prodockit bootstrap` fetches it for a
bootstrapped project. An adopted or manually installed project can fetch it in
its own build workflow, and `.gitignore` should keep a local copy out of
commits.

WeasyPrint is worth separating from Pandoc rather than filing both as external
binaries: one is a `pip install` away and the other is not.

Pandoc is version-sensitive in a way that changes output rather than breaking
the build: a major version below 3 renders code blocks as justified prose, and
the builds pin an exact release because 3.x releases have disagreed about the
same source. Bootstrap installs the pinned version where a package manager
allows it and reports local drift. See [Version pinning and
drift](devcons/pinning-drift.md).

See [PDF generation](pdf.md) for how `prodockit.pdf` locates these tools and
[Known limitations](about/limitations.md) for why the Node tools are needed.
A build with neither Mermaid diagrams nor maths needs neither of them, and no
browser.
