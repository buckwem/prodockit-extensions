# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The `prodockit` command-line tool - no Python required. Add `prodockit` (this
package) to your project, then run:

```bash
prodockit pdf
```

from wherever your `zensical.toml` lives, and it builds a PDF the same way
`zensical build`/`zensical serve` build your site: reading everything it
needs from that same config file. See `prodockit.pdf.config` for exactly what
it reads.
"""

from __future__ import annotations

import sys

import click

from prodockit.pdf.build import PdfBuildError
from prodockit.pdf.config import build_pdf_from_zensical_config


@click.group()
def main() -> None:
    """prodockit - extensions for Zensical needed for professional and
    academic documentation."""


@main.command()
@click.option(
    "-f",
    "--config-file",
    default="zensical.toml",
    show_default=True,
    help="Path to your project's Zensical config file.",
)
@click.option(
    "-m",
    "--markdown-file",
    default=None,
    help=(
        "Build the PDF from just this one markdown file (relative to "
        "docs_dir), ignoring nav, using CONFIG_FILE for everything else."
    ),
)
def pdf(config_file: str, markdown_file: str | None) -> None:
    """Build a PDF from your project, using CONFIG_FILE for everything -
    nav, docs directory, fonts, page size, and so on. See the PDF
    generation docs for the full list of `zensical.toml` settings this
    reads."""
    if markdown_file:
        click.echo(f"Building PDF from {config_file} using {markdown_file}...")
    else:
        click.echo(f"Building PDF from {config_file}...")
    try:
        output_path = build_pdf_from_zensical_config(config_file, markdown_file=markdown_file)
    except (PdfBuildError, ValueError, OSError) as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)
    click.echo(f"Wrote {output_path}")
