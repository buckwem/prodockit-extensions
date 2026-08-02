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

from prodockit import __version__
from prodockit.init_tools import (
    COMPONENT_PURPOSE,
    InitToolsError,
    ci_environment,
    gitignore_lines,
    init_tools,
    install_commands,
)
from prodockit.pdf.build import PdfBuildError
from prodockit.pdf.config import build_pdf_from_zensical_config
from prodockit.pdf.source_bundle import SourceBundleError
from prodockit.sync_repo import SyncRepoError, sync_repo_metadata


# `message="%(version)s"` prints the bare version, matching what
# `zensical --version` does - these two are normally installed and
# reported together, and click's own default ("prodockit, version X.Y.Z")
# would need parsing to compare them.
@click.group()
@click.version_option(__version__, "--version", message="%(version)s")
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


@main.command("init-tools")
@click.option(
    "--dir",
    "tools_dir",
    default="tools",
    show_default=True,
    help="Directory to scaffold into. Must match what prodockit.pdf looks for.",
)
@click.option(
    "--mermaid/--no-mermaid",
    default=True,
    show_default=True,
    help="Scaffold the mermaid-cli tooling, for ```mermaid diagrams in the PDF.",
)
@click.option(
    "--mathjax/--no-mathjax",
    default=True,
    show_default=True,
    help="Scaffold the mathjax-full tooling, for TeX maths in the PDF.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite files that already exist, instead of leaving them alone.",
)
def init_tools_command(tools_dir: str, mermaid: bool, mathjax: bool, force: bool) -> None:
    """Set up the Node tooling needed to render Mermaid diagrams and TeX
    maths in your PDF.

    WeasyPrint has no JS engine, so both are pre-rendered to static images
    by external tools before Pandoc sees them. This writes the manifests
    `prodockit pdf` expects to find, and prints the commands to install
    them. A project using neither feature doesn't need any of this.
    """
    components = tuple(
        name for name, wanted in (("mermaid", mermaid), ("mathjax", mathjax)) if wanted
    )
    if not components:
        click.echo("Nothing to do: both --no-mermaid and --no-mathjax were given.", err=True)
        sys.exit(1)

    try:
        result = init_tools(tools_dir, components=components, force=force)
    except InitToolsError as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    for path in result.written:
        click.echo(f"Wrote {path}")
    for path in result.skipped:
        click.echo(f"Kept existing {path} (use --force to overwrite)")

    click.echo("\nScaffolded for:")
    for component in result.components:
        click.echo(f"  - {COMPONENT_PURPOSE[component]}")

    click.echo("\nNext, install them:")
    for command in install_commands(result):
        click.echo(f"  {command}")

    click.echo("\nAdd to .gitignore (commit the manifests and lockfiles, not the installs):")
    for line in gitignore_lines(result):
        click.echo(f"  {line}")

    if "mermaid" in result.components:
        click.echo(
            "\nIn CI, mermaid-cli drives Chrome through Puppeteer. Install "
            "Chrome and set:"
        )
        for name, value in ci_environment().items():
            click.echo(f"  {name}: {value}")
        click.echo(
            "  (PUPPETEER_SKIP_DOWNLOAD, not the older "
            "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD, which puppeteer 25.x ignores)"
        )


@main.command()
@click.option(
    "-r",
    "--root",
    default=".",
    show_default=True,
    help="Project root to scan for version declarations.",
)
@click.option(
    "-p",
    "--package",
    "packages",
    multiple=True,
    help=(
        "Package to manage, repeatable. Defaults to zensical and "
        "weasyprint - the two whose version changes this project's own "
        "published output."
    ),
)
@click.option(
    "--set",
    "assignments",
    multiple=True,
    metavar="PACKAGE=VERSION",
    help="Set a version without prompting, repeatable. Implies --no-input.",
)
@click.option(
    "--latest",
    "take_latest",
    is_flag=True,
    help="Take PyPI's newest release for every package without prompting.",
)
@click.option(
    "--check",
    is_flag=True,
    help=(
        "Report and exit non-zero if any package is behind PyPI or "
        "declared inconsistently across files, without writing. For a "
        "scheduled drift job."
    ),
)
@click.option(
    "--offline",
    is_flag=True,
    help="Skip the PyPI lookup. Only reports what the files already declare.",
)
def pins(
    root: str,
    packages: tuple[str, ...],
    assignments: tuple[str, ...],
    take_latest: bool,
    check: bool,
    offline: bool,
) -> None:
    """Show and update pinned build-input versions across every file that
    declares one.

    A pinned project ends up naming the same version in several places at
    once - a floor in `pyproject.toml`, an exact pin in each CI workflow.
    This finds them all and moves them together, keeping each site's own
    operator, so a floor stays a floor and an exact pin stays exact.

    Run it with no options for an interactive prompt per package: press
    Enter to take the newest release, or type a version.
    """
    from prodockit.pins import (
        DEFAULT_PACKAGES,
        PinError,
        apply_version,
        discover,
        resolve_latest,
    )

    selected = tuple(p.lower() for p in packages) or DEFAULT_PACKAGES
    states = discover(root, selected)
    resolve_latest(states, offline=offline)

    chosen: dict[str, str] = {}
    for assignment in assignments:
        name, _, value = assignment.partition("=")
        name = name.strip().lower()
        if not value.strip():
            click.echo(f"Error: --set expects PACKAGE=VERSION, got {assignment!r}", err=True)
            sys.exit(1)
        if name not in states:
            click.echo(
                f"Error: {name!r} is not being managed. Add it with --package {name}.", err=True
            )
            sys.exit(1)
        chosen[name] = value.strip()

    # --- report -----------------------------------------------------------
    any_sites = False
    for state in states.values():
        click.echo(f"\n{state.package}")
        if not state.sites:
            click.echo("  not declared anywhere - nothing to update")
        else:
            any_sites = True
            for site in state.sites:
                click.echo(f"  {site.path}:{site.line}  {site.spec}")
        if not state.on_pypi:
            # A runner label or image tag - inventoried and rewritable, but
            # there is no package index to ask what is newest.
            click.echo("  not on PyPI - set the version yourself")
        elif state.latest:
            marker = "  <- newer available" if state.is_behind else ""
            click.echo(f"  newest on PyPI: {state.latest}{marker}")
        elif state.latest_error:
            click.echo(f"  newest on PyPI: unknown - {state.latest_error}")
        if not state.is_consistent:
            click.echo(f"  ⚠ declared inconsistently: {', '.join(state.versions)}")

    if not any_sites:
        click.echo("\nNo version declarations found. Nothing to do.")
        return

    # --- check mode -------------------------------------------------------
    if check:
        problems = [
            f"{s.package} is at {s.current} but {s.latest} is available"
            for s in states.values()
            if s.is_behind
        ] + [
            f"{s.package} is declared inconsistently ({', '.join(s.versions)})"
            for s in states.values()
            if not s.is_consistent
        ]
        if problems:
            click.echo("")
            for problem in problems:
                click.echo(f"Drift: {problem}", err=True)
            sys.exit(1)
        click.echo("\nEvery managed package is current and consistent.")
        return

    # --- decide -----------------------------------------------------------
    for state in states.values():
        if not state.sites or state.package in chosen:
            continue
        if take_latest:
            if state.latest:
                chosen[state.package] = state.latest
            continue
        default = state.latest or state.current
        if default is None:
            continue
        answer = click.prompt(
            f"\n{state.package}: version to set",
            default=default,
            show_default=True,
        ).strip()
        if answer:
            chosen[state.package] = answer

    # --- apply ------------------------------------------------------------
    updated = 0
    for package, version in chosen.items():
        state = states[package]
        if not state.sites:
            continue
        try:
            changed = apply_version(root, state, version)
        except PinError as error:
            click.echo(f"Error: {error}", err=True)
            sys.exit(1)
        for site in changed:
            new_spec = f"{site.package}{site.extras}{site.op}{version}"
            click.echo(f"  {site.path}:{site.line}  {site.spec} -> {new_spec}")
            updated += 1

    if updated:
        click.echo(f"\nUpdated {updated} declaration(s). Rebuild and diff before committing.")
    else:
        click.echo("\nNothing to change - every declaration already matches.")
