# prodockit

A family of extensions for [Zensical](https://zensical.org/) needed for
professional and academic documentation: section cross-references,
bibliography/citation handling, a glossary, and a Pandoc/WeasyPrint PDF
pipeline for the downloadable, submittable document these usually need
alongside the website itself.

Most of prodockit is [Python-Markdown](https://python-markdown.github.io/)
extensions, enabled in `zensical.toml`. `prodockit.pdf` is a command-line
tool instead (`prodockit pdf`), since a PDF build pipeline isn't a Markdown
syntax extension - it reads the same `zensical.toml` too. In addition,
there's a set of website macros (`prodockit.zensical_macros`) to help use
prodockit's features.

It's a kit for professional documentation, built on Zensical's own
Markdown and Pandoc/WeasyPrint PDF pipeline.

> **Status:** early, but functional - `prodockit.headings`, `prodockit.refs`,
> `prodockit.citations`, `prodockit.glossary`, `prodockit.tables`,
> `prodockit.bibliography`, `prodockit.index`, `prodockit.pdf`, and
> `prodockit.zensical_macros` are implemented and tested.

**[Full documentation](https://buckwem.github.io/prodockit-extensions/)**

## Installation

Requires **Python 3.10 or later** (tested on 3.10-3.13).

```bash
pip install prodockit
```

`prodockit.pdf` and `prodockit.bibliography` additionally need `pandoc`,
and the PDF build needs `weasyprint` - external binaries, not Python
packages, so `pip` doesn't install them. See
[Installation](https://buckwem.github.io/prodockit-extensions/installation/)
for the full list, including the optional Node tooling for Mermaid
diagrams and TeX maths in the PDF.

## Extensions

| Extension | Description |
|---|---|
| [`prodockit.headings`](https://buckwem.github.io/prodockit-extensions/extensions/headings/) | Gives every heading an id and a hierarchical section number ("1", "1.1", "1.2", "2", ...). |
| [`prodockit.refs`](https://buckwem.github.io/prodockit-extensions/extensions/refs/) | `\ref{id}` section cross-references, resolving to the target's current number - similar in spirit to LaTeX's `\ref`. |
| [`prodockit.citations`](https://buckwem.github.io/prodockit-extensions/extensions/citations/) | Define a source once, cite it by key anywhere with `\citeref{id}` - auto-generates the bracketed, linked citation text. |
| [`prodockit.glossary`](https://buckwem.github.io/prodockit-extensions/extensions/glossary/) | Define a term once (an acronym expansion, a glossary entry), insert it by id anywhere with `\gls{id}` - similar in spirit to LaTeX's `glossaries` package. |
| [`prodockit.tables`](https://buckwem.github.io/prodockit-extensions/extensions/tables/) | Percentage or fixed column widths on a table, via a `width` attribute already attachable to a header cell with `attr_list`. |
| [`prodockit.bibliography`](https://buckwem.github.io/prodockit-extensions/extensions/bibliography/) | An alternative to `prodockit.citations`: define sources in a BibTeX/BibLaTeX `.bib` file and format `\cite{id}`/the reference list in any Citation Style Language style, via Pandoc's own `--citeproc`. |
| [`prodockit.index`](https://buckwem.github.io/prodockit-extensions/extensions/index-terms/) | Mark a term inline with `\index{Term}` for a traditional, PDF-only back-of-book index - with hierarchical sub-entries and code-styled terms. |

```python
import markdown

html = markdown.markdown(
    text,
    extensions=[
        "attr_list", "prodockit.headings", "prodockit.refs", "prodockit.citations", "prodockit.glossary"
    ],
)
```

```md
# Introduction {: #intro }

See \ref{intro} for background.\citeref{skou2023} This uses \gls{css}.

Skoulikari, A. (2023) *Learning Git*.
{: #skou2023 data-cite-text="Skoulikari, 2023" }

**CSS** - Cascading Style Sheets.
{: #css data-term="CSS" }
```

`\ref{intro}` resolves to a link reading `1` - the heading's current
section number; `\citeref{skou2023}` resolves to `[Skoulikari, 2023]`, linked
to that source; `\gls{css}` resolves to `CSS`, linked to its own
definition. All three stay correct if content is reordered, since
resolution happens fresh on every conversion. See the
[docs](https://buckwem.github.io/prodockit-extensions/) for options, multi-page
registry sharing, and full syntax details.

## PDF generation

[`prodockit.pdf`](https://buckwem.github.io/prodockit-extensions/pdf/) builds a
standalone PDF from your site, via Pandoc and WeasyPrint (both need to be
installed separately - see the docs). No Python required - it reads the
same `zensical.toml` your site already has:

```bash
prodockit pdf
```

That's it - run it from your project root and it builds a complete PDF,
table of contents included, from every page in your `nav`. Also handles a
table too wide for a portrait page - printed sideways, on its own
landscape page(s), spanning multiple pages with a repeated heading row -
`{.web-only}`/`{.pdf-only}` markers for content that should only appear
in one of the two outputs, and a two-column, letter-headed back-of-book
index (`pdf_include_index`) generated from `prodockit.index`'s own
`\index{Term}` markers. See the
[docs](https://buckwem.github.io/prodockit-extensions/pdf/) for the
`zensical.toml` settings it reads, and for the Python API
(`build_pdf()`, `prodockit.pdf.html`/`.lua`/`.css`/`.icons`/`.mermaid`/`.rotate`)
if you're scripting your own build pipeline instead.

## Website macros

[`prodockit.zensical_macros`](https://buckwem.github.io/prodockit-extensions/macros/)
provides a site-wide word count, the git-detected repository URL, the
latest release tag, chapter/appendix numbering that continues across
pages, and reference/acronym/glossary spacing that matches
`prodockit.pdf`'s own PDF output - as Jinja variables/macros for
Zensical's own macros plugin:

```toml
[project.markdown_extensions.zensical.extensions.macros]
modules = ["prodockit.zensical_macros"]
```

See the [docs](https://buckwem.github.io/prodockit-extensions/macros/) for the
full variable/macro list.

## Repository metadata

[`prodockit sync-repo`](https://buckwem.github.io/prodockit-extensions/repository-metadata/)
keeps `repo_url`, `repo_name`, the header brand icon, `edit_uri` and your
README's badge row matching the git remote your checkout actually uses -
so forking or mirroring a project between GitHub, GitLab and Bitbucket
doesn't leave stale links or the wrong icon behind:

```bash
prodockit sync-repo          # update everything from `origin`
prodockit sync-repo --check  # report drift and exit non-zero, for CI
```

It also sets `edit_uri` explicitly, which fixes the "edit this page"
button on a self-hosted GitLab and stops it pointing at a `master` branch
that may not exist.

## Version pinning and drift

A documentation build has more inputs than its own source: `zensical`
renders the site, `weasyprint` lays out the PDF, and the CI runner image
carries `pandoc`, the fonts and Chrome. Left unpinned, an upgrade doesn't
fail the build - it quietly publishes a different document.

Pinning them means declaring the same version in several files at once,
which nothing keeps in step.
[`prodockit pins`](https://buckwem.github.io/prodockit-extensions/version-pinning/)
finds every declaration and moves them together, keeping each one's own
operator so a library floor stays a floor and a build pin stays exact:

```bash
prodockit pins               # prompt per package; Enter takes the newest
prodockit pins --check       # behind PyPI, or files disagreeing? exit non-zero
prodockit pins -p ubuntu     # runner images and container tags too
```

It reads `pyproject.toml`, GitHub Actions workflows, `.gitlab-ci.yml` and
`requirements`/`constraints` files, so the same command works on either
host. The docs also carry a weekly drift job for GitHub Actions and
GitLab CI that rebuilds with the newest versions, diffs the output byte
for byte, and opens an issue when an upgrade would change what you
publish.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`zensical` is a core dependency, so `zensical serve` is available as soon as
`prodockit` is installed - no extra step needed to build the documentation
locally.

## Contributing

Contributions are welcome - see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE).
