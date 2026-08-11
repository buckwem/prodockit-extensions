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
from pathlib import Path

import click

from prodockit import __version__
from prodockit.bootstrap import (
    PROMPTS,
    BootstrapConfig,
    BootstrapConfigError,
    Context,
    Stage,
    StageReport,
    Status,
    UnsupportedHostError,
    apply_stage,
    authenticate_sudo,
    check_all,
    connection_problem,
    default_for,
    host_problem,
    missing_keys,
    needs_sudo,
    plan_all,
)
from prodockit.bootstrap import build_context as build_bootstrap_context
from prodockit.bootstrap import config_path as bootstrap_config_path
from prodockit.bootstrap import load as load_bootstrap_config
from prodockit.bootstrap import save as save_bootstrap_config
from prodockit.init_tools import (
    COMPONENT_PURPOSE,
    InitToolsError,
    ci_environment,
    gitignore_lines,
    init_tools,
    install_commands,
)
from prodockit.pdf.build import PdfBuildError
from prodockit.pdf.config import (
    build_pdf_from_zensical_config,
    build_source_bundle_from_zensical_config,
)
from prodockit.pdf.source_bundle import SourceBundleError
from prodockit.sync_repo import SyncRepoError, sync_repo_metadata


def _echo_captured_stderr(error: Exception) -> None:
    """Prints the failing external tool's own stderr, when the exception
    carried it.

    `PdfBuildError` and `SourceBundleError` both capture the stderr of the
    process that failed - `pandoc`, and through it whichever PDF engine
    pandoc invoked - and this used to print only the exception's message.
    That message names a command and an exit code and nothing else, so the
    single most useful thing prodockit knows about the failure was
    collected and then discarded.

    What that cost, concretely: a reader following the User Guide on a
    clean macOS machine got `pandoc exited with status 43` and no more.
    Status 43 is pandoc's `PandocPDFError`, meaning the PDF engine failed
    rather than pandoc itself, and the engine's own message said WeasyPrint
    could not load `libgobject-2.0-0`, named the four libraries it needs,
    and linked its installation instructions. All of that was already in
    hand (prodockit-extensions#188).

    Printed whole rather than summarised. The interesting part of a pandoc
    failure is usually the *end* - warnings come first and the traceback
    last - so a head-truncated excerpt would hide exactly the useful part,
    and there is no other way for a caller to get at it.
    """
    stderr = str(getattr(error, "stderr", "") or "").strip()
    if not stderr:
        return
    click.echo("", err=True)
    click.echo("Output from the failing command:", err=True)
    click.echo(stderr, err=True)


# `message="%(version)s"` prints the bare version, matching what
# `zensical --version` does - these two are normally installed and
# reported together, and click's own default ("prodockit, version X.Y.Z")
# would need parsing to compare them.
@click.group()
@click.version_option(__version__, "--version", message="%(version)s")
def main() -> None:
    """prodockit - extensions for Zensical needed for professional and
    academic documentation."""


def _ask_for_configuration(
    config: BootstrapConfig, *, only: list[str] | None = None
) -> BootstrapConfig:
    """Asks the configuration questions, storing each answer as it comes.

    `only` narrows it to particular fields - used when a run finds a
    couple of answers missing and asks just for those, rather than making
    someone walk the whole list again to fill one gap.

    With `only` unset every field is re-asked, as #217 requires: pressing
    Enter through keeps what is already there, so confirming an unchanged
    setup costs a few keystrokes rather than an edit.
    """
    wanted = [(k, q) for k, q in PROMPTS if only is None or k in only]
    click.echo("\nPress Enter to keep the value in brackets.\n")
    for key, question in wanted:
        while True:
            # `default_for` fills a blank answer from one already given, so
            # a first run still has something sensible to press Enter on.
            answer = click.prompt(
                question, default=default_for(config, key), show_default=True
            ).strip()
            # The host is asked first precisely so an unusable answer is
            # caught here, rather than after five more questions about a
            # setup that cannot be built (#255).
            problem = _host_answer_problem(answer) if key == "host" else None
            if problem is None:
                break
            click.echo(f"  {problem}\n", err=True)
        # Fed back in as it is given, so a later question can default off
        # an earlier answer.
        setattr(config, key, answer)
    # Stored absolute, though offered relative: `./report` is the clearest
    # thing to *read* at the prompt, and the worst thing to *keep* - it
    # would mean something different the next time bootstrap ran from
    # somewhere else.
    config.project_dir = str(config.resolved_project_dir(Path.home()))
    return config


def _host_answer_problem(answer: str) -> str | None:
    """Why this host answer will not do - its name, or its silence.

    Both halves are asked here rather than later. A name that cannot work
    is cheap to catch; a host that cannot be *reached* is worth catching
    because the alternative is discovering it at stage 6, after a key has
    been made and uploaded - and "could not reach it" looks nothing like
    "it rejected your key", which is a confusion these stages have
    already produced three times.

    Re-asking with the same answer is a real retry, not a loop: a
    university GitLab is often reachable only over a VPN, so connecting
    one and pressing Enter is exactly the fix.
    """
    if (problem := host_problem(answer)) is not None:
        return problem
    if (unreachable := connection_problem(answer)) is not None:
        return (
            f"{unreachable}.\n"
            "  If this host is only reachable from your university network, "
            "connect the VPN and press Enter to try again."
        )
    return None


def _is_interactive() -> bool:
    """Whether there is a human to answer a prompt.

    A named function rather than an inline `sys.stdin.isatty()` so it is
    one thing to reason about - and one thing to override in a test,
    where the runner substitutes its own stdin and an inline check would
    read whatever that happened to be.
    """
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):  # pragma: no cover - closed stream
        return False


def _offer_to_fill_gaps(config: BootstrapConfig, path: Path) -> BootstrapConfig:
    """Offers to ask for whatever is missing, rather than naming a file.

    Telling a first-time reader a value is "not set in your bootstrap
    config" points them at a file they may have no idea how to edit -
    and editing TOML by hand is exactly the kind of step this command
    exists to remove. So it asks.

    Skipped when stdin is not a terminal: a scripted or piped run must
    report and exit rather than block on a prompt nobody can answer.
    """
    blank = missing_keys(config)
    if not blank:
        return config
    if not _is_interactive():
        click.echo(
            f"Not configured yet ({', '.join(blank)}). Run `prodockit bootstrap "
            "--configure` to answer the questions.\n",
            err=True,
        )
        return config

    click.echo(f"Some details are not set yet: {', '.join(blank)}.")
    if not click.confirm("Answer them now?", default=True):
        click.echo("Carrying on - stages needing them will show as unknown.\n")
        return config
    config = _ask_for_configuration(config, only=blank)
    save_bootstrap_config(path, config)
    click.echo(f"\nSaved to {path}\n")
    return config


def _first_meaningful_line(text: str) -> str:
    """The most useful single line of a tool's error output.

    Git prefixes its remote errors with banner lines of `=====` and blank
    `remote:` markers, so printing the lot buries the one sentence that
    matters in eight lines of decoration.

    Warnings are skipped while any other line remains, because a warning
    is by definition not the thing that failed. apt opens with one every
    time it is run from a script:

        WARNING: apt does not have a stable CLI interface. Use with
        caution in scripts.

        E: Unsupported file ./code.deb given on commandline

    Reporting the first of those as the failure said nothing about what
    went wrong and sent the reader looking at their scripting (#233).
    """
    meaningful = []
    for line in text.splitlines():
        cleaned = line.replace("remote:", "").strip().strip("=").strip()
        if cleaned and not set(cleaned) <= {"=", "-"}:
            meaningful.append(cleaned)
    for line in meaningful:
        if not line.upper().startswith("WARNING"):
            return line
    if meaningful:  # nothing but warnings - then a warning is the best there is
        return meaningful[0]
    return text.strip().splitlines()[0] if text.strip() else "no output"


def _apply_outstanding(context: Context, reports: list[StageReport]) -> None:
    """Applies the stages that need it, asking before each.

    A stage whose work is *yours* - the two browser steps - is retried
    rather than failed. Checking too early is the normal case, not an
    error: you cannot create a project on a website and have it exist
    before you have done it. Exiting at that point threw away every stage
    already completed and made the reader start again.
    """
    outstanding = [r for r in reports if r.needs_work and r.plan is not None]
    if not outstanding:
        click.echo("Nothing to do - every stage is either set up or waiting on "
                   "configuration.")
        return

    total = len(outstanding)
    for number, report in enumerate(outstanding, start=1):
        plan = report.plan
        if plan is None:  # pragma: no cover - filtered above, narrows for mypy
            continue

        click.echo("")
        click.echo(click.style(f"[{number}/{total}] {report.stage.summary}", bold=True))
        if report.result.detail:
            click.echo(f"        {report.result.detail}")
        click.echo("")

        # A plan's manual steps are ordered against its commands rather
        # than merely coexisting with them: `instructions` prepare for the
        # commands, `follow_up` finishes what they started. Both orderings
        # have shipped broken - instructions-only skipped `brew install`
        # entirely (#230), and commands-first ran the SSH probe before the
        # reader had been told to upload the key, which fails by
        # definition and ended the run (#234).
        if plan.instructions:
            _show_steps("  What you need to do:", plan.instructions)
            if not plan.commands:
                # Guide and verify. The stage's own check is the
                # verification, and "not finished yet" is the normal
                # answer to it, not a failure - so it asks again.
                if not _verify_until_done(context, report.stage):
                    click.echo("  skipped")
                continue
            # There are commands, and they need the step above done
            # first. One acknowledgement, then run them.
            click.confirm("  Tell me when that is done", default=True)
            click.echo("")

        if plan.commands:
            click.echo("  Will run:")
            for command in plan.commands:
                click.echo(f"    {' '.join(command)}")
            click.echo("")
            default_yes = report.result.status is Status.MISSING
            count = len(plan.commands)
            if not click.confirm(f"  Run {count} command{'s' if count != 1 else ''}?",
                                 default=default_yes):
                click.echo("  skipped")
                continue

            # Get sudo's password question over with here, where there is
            # a terminal for it, rather than inside a captured subprocess
            # whose clock is running. sudo reads from /dev/tty exactly as
            # ssh does, so it asks regardless of what stdin is set to -
            # and the reader's typing time was counted against the
            # install's timeout (#243).
            if needs_sudo(plan.commands) and _is_interactive():
                click.echo("  These need administrator rights.")
                if not authenticate_sudo():
                    click.echo("  sudo was not accepted - the commands may fail.", err=True)
                click.echo("")

            outcome = apply_stage(context, report.stage)
            if outcome.failed is not None:
                click.echo(
                    f"  failed: {_first_meaningful_line(outcome.failed.stderr)}",
                    err=True,
                )
                click.echo("  Stopping - later stages depend on this one.", err=True)
                sys.exit(1)
            if outcome.ok:
                click.echo("  done")
                continue
            if plan.follow_up:
                # The commands did their half; this is the half only a
                # human can do - the VS Code shell command after
                # `brew install` put the application there (#230).
                _show_steps("  commands ran — one more step:", plan.follow_up)
            elif not plan.instructions:
                detail = outcome.verified.detail if outcome.verified else "unknown"
                click.echo(f"  ran, but still not right: {detail}", err=True)
                sys.exit(1)
            if not _verify_until_done(context, report.stage):
                click.echo("  skipped")
            continue

        # No commands and no manual steps — nothing to do for this stage.
        # Should not happen, but not worth crashing over.
        click.echo("  nothing to do")  # pragma: no cover

    click.echo("")
    click.echo("Finished. Run `prodockit bootstrap` to confirm.")


def _echo_wrapped_instruction(instruction: str) -> None:
    """One `--dry-run` instruction line, keeping a multi-line step aligned."""
    first, *rest = instruction.splitlines() or [""]
    click.echo(f"        you: {first}")
    for line in rest:
        click.echo(f"             {line}")


def _show_steps(title: str, steps: list[str]) -> None:
    """Prints a numbered list of things a human has to do.

    A step may span several lines - the SSH upload prints the public key
    itself between marker lines (#238) - and continuation lines are
    indented to hang under the step's text rather than under its number,
    so the block reads as one step rather than as several unnumbered
    ones.
    """
    click.echo(title)
    for number, step in enumerate(steps, start=1):
        label = f"{number}. "
        first, *rest = step.splitlines() or [""]
        click.echo(f"    {label}{first}")
        for line in rest:
            click.echo(f"    {' ' * len(label)}{line}")
    click.echo("")


def _verify_until_done(context: Context, stage: Stage) -> bool:
    """Waits for a manual step, re-checking until it takes or you stop.

    Returns whether it ended up satisfied. A failed check here means "not
    yet", not "broken" - so it says so, and asks again.
    """
    while True:
        click.confirm("  Tell me when that is done", default=True)
        result = stage.check(context)
        if not result.needs_work:
            click.echo("  confirmed")
            return True
        click.echo(f"  not there yet - {result.detail}")
        if not click.confirm("  Try again?", default=True):
            return False


@main.command()
@click.option(
    "--check",
    "check_only",
    is_flag=True,
    help="Report each stage's state and change nothing.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the exact commands a real run would use, without running them.",
)
@click.option(
    "--apply",
    "apply_stages",
    is_flag=True,
    help="Actually set up the stages that need it, asking before each one.",
)
@click.option(
    "--configure",
    is_flag=True,
    help="Answer the configuration questions again, then stop.",
)
@click.option(
    "--config",
    "config_file",
    default=None,
    help="Path to bootstrap's own config file. Defaults to your user config directory.",
)
def bootstrap(
    check_only: bool,
    dry_run: bool,
    apply_stages: bool,
    configure: bool,
    config_file: str | None,
) -> None:
    """Set up this machine and your project from scratch.

    Checks all 17 stages - editor, git, SSH key/config/agent/upload,
    clone, history, remote, commit identity, the project's own
    environment, pandoc, Node and the rest - and reports which are
    already done. Rerunnable: a stage that is set up correctly
    is left alone.

    This cannot be the first thing you run: it is a prodockit command, so
    Python and `pip install prodockit` necessarily come first.

    With no options this reports what it finds and changes nothing - the
    safe default, and the question most people are actually asking. Phase
    1 installs nothing either way.
    """
    # Bare `prodockit bootstrap` is a checking run. Defaulting to the
    # read-only behaviour matters more than usual here: the alternative
    # default is a command that starts installing software because someone
    # typed it to see what it did.
    if not dry_run and not apply_stages and not configure:
        check_only = True

    path = Path(config_file) if config_file else bootstrap_config_path()
    try:
        config = load_bootstrap_config(path)
    except BootstrapConfigError as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    # Asked for explicitly, or because applying without the answers would
    # clone into a directory named after nothing.
    if configure or (apply_stages and not config.is_complete):
        config = _ask_for_configuration(config)
        save_bootstrap_config(path, config)
        click.echo(f"\nSaved to {path}")
        if configure:
            return

    # Offer to fill anything still blank before checking, so the run that
    # follows can actually judge the project stages rather than reporting
    # three unknowns and leaving the reader to work out what to do.
    config = _offer_to_fill_gaps(config, path)

    try:
        context = build_bootstrap_context(config)
    except UnsupportedHostError as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)


    reports = check_all(context) if check_only else plan_all(context)

    if apply_stages:
        _apply_outstanding(context, reports)
        return

    symbols = {
        Status.OK: "ok  ",
        Status.MISSING: "MISS",
        Status.WRONG: "WRONG",
        Status.UNKNOWN: "?   ",
    }
    for number, report in enumerate(reports, start=1):
        symbol = symbols[report.result.status]
        detail = f" - {report.result.detail}" if report.result.detail else ""
        click.echo(f"{number:2}  {symbol}  {report.stage.summary}{detail}")
        if dry_run and report.plan is not None:
            # In the order they actually happen: prepare, run, finish.
            for instruction in report.plan.instructions:
                _echo_wrapped_instruction(instruction)
            for command in report.plan.commands:
                click.echo(f"        run: {' '.join(command)}")
            for instruction in report.plan.follow_up:
                _echo_wrapped_instruction(instruction)

    outstanding = [r for r in reports if r.needs_work]
    click.echo()
    if not outstanding:
        click.echo(f"All {len(reports)} stages are set up.")
        return
    click.echo(f"{len(outstanding)} of {len(reports)} stages need work.")
    if check_only:
        click.echo("Run with --dry-run to see the exact commands that would fix them.")
    # Non-zero so this is usable as a check in a script, matching
    # `sync-repo --check` and `pins --check`.
    sys.exit(1)


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
        _echo_captured_stderr(error)
        sys.exit(1)
    click.echo(f"Wrote {output_path}")


@main.command("source-bundle")
@click.option(
    "-f",
    "--config-file",
    default="zensical.toml",
    show_default=True,
    help="Path to your project's Zensical config file.",
)
def source_bundle(config_file: str) -> None:
    """Bundle your project's Markdown content and CONFIG_FILE into a
    separate PDF - one file per page - for a submission that needs the
    underlying source alongside the rendered document.

    A separate command from `prodockit pdf`, so a project that wants only
    one of the two PDFs doesn't pay for the other. See the PDF generation
    docs for what gets included and how to change it.
    """
    click.echo(f"Building source bundle from {config_file}...")
    try:
        output_path = build_source_bundle_from_zensical_config(config_file)
    except (SourceBundleError, ValueError, OSError) as error:
        click.echo(f"Error: {error}", err=True)
        _echo_captured_stderr(error)
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
        "Package to manage, repeatable. Defaults to zensical, weasyprint, "
        "markdown, pymdown-extensions and pandoc - the build inputs whose "
        "version changes this project's own published output."
    ),
)
@click.option(
    "--set",
    "assignments",
    multiple=True,
    metavar="PACKAGE=VERSION",
    help=(
        "Set a version without prompting, repeatable. Implies --no-input, so "
        "any package not named is reported and left untouched."
    ),
)
@click.option(
    "--latest",
    "take_latest",
    is_flag=True,
    help=(
        "Take PyPI's newest release for every package without prompting. "
        "Implies --no-input, so a package with no known newest is left "
        "untouched rather than asked about."
    ),
)
@click.option(
    "--no-input",
    "no_input",
    is_flag=True,
    help=(
        "Never prompt. Packages given a version by --set or --latest are "
        "updated; the rest are reported and left untouched. Implied by both "
        "of those."
    ),
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
    no_input: bool,
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
    Enter to take the newest release, or type a version. With `--set`,
    `--latest` or `--no-input` it never prompts, so it can run unattended.
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
    # Naming a version on the command line is a statement that nobody is
    # here to answer a prompt - a release script, a drift job. Prompting
    # for the packages it did not name would hang such a run, and with no
    # stdin to hang on it aborted instead, writing nothing at all: not even
    # the package it had been told explicitly to set.
    quiet = no_input or bool(assignments) or take_latest
    skipped: list[str] = []
    interrupted = False
    for state in states.values():
        if not state.sites or state.package in chosen:
            continue
        if take_latest and state.latest:
            chosen[state.package] = state.latest
            continue
        if quiet:
            skipped.append(state.package)
            continue
        default = state.latest or state.current
        if default is None:
            continue
        try:
            answer = click.prompt(
                f"\n{state.package}: version to set",
                default=default,
                show_default=True,
            ).strip()
        except click.Abort:
            # Ctrl-C, or stdin ending. It cancels the packages still to
            # come, not the answers already given - those were asked for,
            # and discarding them writes nothing while looking like a run
            # that simply did not get that far.
            interrupted = True
            break
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
            if not updated:
                # Separates the rewrites from whatever came last - the
                # report, or a prompt left mid-line by an interrupt.
                click.echo("")
            # site.package is always lower-cased, for lookup against the
            # managed set - name_as_written carries a CI variable's real
            # case (PANDOC_VERSION, not pandoc_VERSION) and must be used
            # here too, or this progress line shows a rewrite that isn't
            # the one apply_version() actually performed.
            new_spec = f"{site.name_as_written or site.package}{site.extras}{site.op}{version}"
            click.echo(f"  {site.path}:{site.line}  {site.spec} -> {new_spec}")
            updated += 1

    if skipped:
        click.echo(f"\nLeft untouched (no version given): {', '.join(skipped)}")

    if updated:
        click.echo(f"\nUpdated {updated} declaration(s). Rebuild and diff before committing.")
    elif chosen or not skipped:
        # Only when something *was* asked for. With nothing set and nothing
        # prompted for, "every declaration already matches" would claim a
        # comparison the run never made.
        click.echo("\nNothing to change - every declaration already matches.")

    if interrupted:
        click.echo(
            "\nStopped at the prompt - anything answered above was written, "
            "the rest was left untouched.",
            err=True,
        )
        sys.exit(1)
