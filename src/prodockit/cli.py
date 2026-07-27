# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The `prodockit` command-line tool - no Python required. Add `prodockit`
(this package) to your project, then run its commands from wherever your
`zensical.toml` lives:

```bash
prodockit pdf         # build a PDF from your site
prodockit sync-repo   # match repo links/icon/badges to your git remote
```

Both read what they need from that same config file, the way
`zensical build`/`zensical serve` do. See `prodockit.pdf.config` and
`prodockit.sync_repo` for exactly what each one reads.

This module is the CLI for the whole package, not just the PDF build -
`prodockit.pdf.cli` re-exports `main` from here so that the older
`prodockit.pdf.cli:main` entry point keeps working.
"""

from __future__ import annotations

import sys

import click

from prodockit.pdf.build import PdfBuildError
from prodockit.pdf.config import build_pdf_from_zensical_config
from prodockit.pdf.source_bundle import SourceBundleError
from prodockit.sync_repo import SyncRepoError, sync_repo_metadata


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
    except (PdfBuildError, SourceBundleError, ValueError, OSError) as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)
    click.echo(f"Wrote {output_path}")


@main.command("sync-repo")
@click.option(
    "-f",
    "--config-file",
    default="zensical.toml",
    show_default=True,
    help="Path to your project's Zensical config file.",
)
@click.option(
    "--readme",
    "readme_path",
    default="README.md",
    show_default=True,
    help="README to update the repo-badges block in. Pass an empty value to skip it.",
)
@click.option(
    "--remote",
    default="origin",
    show_default=True,
    help="Which git remote to read the repository URL from.",
)
@click.option(
    "--branch",
    "default_branch",
    default=None,
    help=(
        "Default branch to build edit_uri and GitLab build-badge links "
        "from. Detected from the remote when not given."
    ),
)
@click.option(
    "--check",
    is_flag=True,
    help=(
        "Report what would change and exit non-zero if anything would, "
        "without writing. For CI, to catch a config that has drifted from "
        "the remote it is served from."
    ),
)
def sync_repo(
    config_file: str,
    readme_path: str,
    remote: str,
    default_branch: str | None,
    check: bool,
) -> None:
    """Match your repo links, brand icon and README badges to the git
    remote this checkout actually uses.

    Updates `repo_url`, `repo_name`, `theme.icon.repo` and `edit_uri` in
    CONFIG_FILE, and the badge row between the `repo-badges` markers in
    your README if those markers are present. Run it after changing a
    remote, or as a build step before `zensical build`.
    """
    try:
        result = sync_repo_metadata(
            config_file,
            readme_path=readme_path or None,
            remote=remote,
            default_branch=default_branch,
            check=check,
        )
    except SyncRepoError as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    for note in result.notes:
        click.echo(f"Note: {note}")

    if not result.changed:
        click.echo(f"Already in sync with the {result.label} remote ({result.repo_url})")
        return

    changed = ", ".join(result.changes)
    if check:
        click.echo(
            f"Out of sync with the {result.label} remote ({result.repo_url}); "
            f"would update: {changed}",
            err=True,
        )
        sys.exit(1)
    click.echo(f"Detected {result.label} remote ({result.repo_url}); updated: {changed}")
