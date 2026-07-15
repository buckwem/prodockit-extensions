# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The `zendoc` command-line tool - no Python required. Add `zendoc` (this
package) to your project, then run:

```bash
zendoc pdf
```

from wherever your `zensical.toml` lives, and it builds a PDF the same way
`zensical build`/`zensical serve` build your site: reading everything it
needs from that same config file. See `zendoc.pdf.config` for exactly what
it reads.
"""

from __future__ import annotations

import sys

import click

from zendoc.pdf.build import PdfBuildError
from zendoc.pdf.config import build_pdf_from_zensical_config


@click.group()
def main() -> None:
    """zendoc - extensions for Zensical needed for professional and
    academic documentation."""


@main.command()
@click.option(
    "-f",
    "--config-file",
    default="zensical.toml",
    show_default=True,
    help="Path to your project's Zensical config file.",
)
def pdf(config_file: str) -> None:
    """Build a PDF from your project, using CONFIG_FILE for everything -
    nav, docs directory, fonts, page size, and so on. See the PDF
    generation docs for the full list of `zensical.toml` settings this
    reads."""
    click.echo(f"Building PDF from {config_file}...")
    try:
        output_path = build_pdf_from_zensical_config(config_file)
    except (PdfBuildError, ValueError, OSError) as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)
    click.echo(f"Wrote {output_path}")
