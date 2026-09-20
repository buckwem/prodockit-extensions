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
| [`zensical`](https://zensical.org/) (>= 0.0.61) | Zensical integration and `prodockit.zensical_macros` |
| [PyMdown Extensions](https://facelessuser.github.io/pymdown-extensions/) (>= 11.0.2) | `prodockit.steps` and `prodockit.tree` are built directly on the PyMdown Blocks API; `prodockit.pdf` also preserves the output of PyMdown features |
| [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) (>= 4.12) | `prodockit.pdf` |
| \index{dependencies!`click`} (>= 8.0) | the `prodockit` command-line tool |
| [`PyYAML`](https://pyyaml.org/) (>= 6.0) | `prodockit adopt` support for Zensical projects that retain a compatible `mkdocs.yml` or `mkdocs.yaml` configuration filename |
| [`packaging`](https://packaging.pypa.io/) (>= 24.0) | comparing an adopted project's recorded Prodockit version floor with the installed release |
| \index{dependencies!`pypdf`} (>= 4.0) | `prodockit.pdf` |
| \index{dependencies!`tomli`} (>= 2.0) | reading a template manifest on Python 3.10, where `tomllib` does not exist yet |
| [`tomlkit`](https://tomlkit.readthedocs.io/) (>= 0.13.2) | editing Adopt's TOML configuration and review ledger while preserving existing comments and formatting |
| `pathspec` (>= 0.12) | respecting `.gitignore` when collecting documentation sources outside a Git repository |
/// table-caption | <
    attrs: {id: tab-installation-requirements}

Requirements installed with Prodockit
///

The floors in \ref{tab-installation-requirements} are declared in
`pyproject.toml`, and a test keeps the table in step with them. They are
compatibility floors, not a recommendation to assemble a toolchain from each
minimum independently. Run `prodockit pins` to select the supported set.

## Installed on first PDF use {: #requirements-pdf-python }

The project commits `pdf-requirements.txt` separately from its website
requirements. On macOS and Linux, `pdk pdf` installs its WeasyPrint declaration
into the active project environment on first use, validates the native loader,
and records the requirements and environment fingerprint beneath
`.prodockit/cache/pdf/python/`. An unchanged warm build does not invoke pip.
When the document enables a back-of-book index, the same preparation adds
PyMuPDF (>= 1.24); otherwise it is not installed. Windows x64 uses the verified
standalone WeasyPrint runtime and ignores the Python WeasyPrint declaration.

## Not installed by pip {: #requirements-external }

The requirements in this section are not supplied by
`pip install prodockit`, and they differ in kind.

\ref{tab-installation-not-installed-by-pip} identifies the external tools that
pip cannot install and the features that use them.

| Requirement {: width="36%" } | Needed for |
| --- | --- |
| \index{dependencies!`pandoc`} (3.10.1) | `prodockit.pdf`, and `prodockit.bibliography` even without a PDF build. `pdk pdf` downloads the verified official archive into the project cache on first use. |
| Inter 4.1 and JetBrains Mono 2.304 | `prodockit.pdf`. `pdk pdf` assembles and verifies a minimal project-local OFL font bundle; host font installation is not used. |
| `mathjax-full` (Node >= 22) | TeX maths in the PDF and website verification |
| Chrome or Chromium | website verification for MathJax; default Mermaid PDF rendering does not use it |
| A citation style (`.csl`) | only `prodockit.bibliography`. The standard style is fetched and validated by Bootstrap or Adopt; custom styles remain author-owned - see below |
/// table-caption | <
    attrs: {id: tab-installation-not-installed-by-pip}

Not installed by pip
///

The citation style is a download rather than a Python package. Pandoc resolves
`harvard-cite-them-right.csl` from the directory it runs in. Bootstrap fetches
that standard style for a new template project, and Adopt now offers the same
validated download when an existing project's configuration names it but the
file is missing. Adopt retains its validated download in Prodockit's native
download cache, so a later offline Adopt run can restore a known-good copy.

The style is deliberately not committed: it is third-party content with its
own licence and release cadence. Adopt preserves an existing file and never
guesses a source for a differently named custom style; obtain that chosen
style yourself and place it at the path configured by `csl_style`. A manual
installation can fetch the supported standard style with:

```bash
curl -fsSL -o harvard-cite-them-right.csl "https://www.zotero.org/styles/harvard-cite-them-right"
```

Pandoc is version-sensitive in a way that changes output rather than breaking
the build: a major version below 3 renders code blocks as justified prose, and
3.x releases have disagreed about the same source. PDF and bibliography paths
therefore resolve the same absolute executable from `.prodockit/cache/pdf/`;
Bootstrap, Adopt, `PATH`, and the project's virtual environment do not select it.
See [Version pinning and
drift](devcons/pinning-drift.md).

See [PDF generation](pdf.md) for how `prodockit.pdf` locates these tools and
[Known limitations](about/limitations.md) for why the Node tools are needed.
A build with neither Mermaid diagrams nor maths needs neither of them, and no
browser.
