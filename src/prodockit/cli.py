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

import pathlib
import sys
import textwrap
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import click

import prodockit
from prodockit import __version__
from prodockit.adopt import (
    MANIFEST as ADOPT_MANIFEST,
)
from prodockit.adopt import (
    AdoptError,
    AdoptOptions,
)
from prodockit.adopt import (
    apply_step as apply_adopt_step,
)
from prodockit.adopt import (
    assess as assess_adoption,
)
from prodockit.adopt import (
    load_manifest as load_adopt_manifest,
)
from prodockit.adopt import (
    write_manifest as write_adopt_manifest,
)
from prodockit.bootstrap import (
    PROMPTS,
    STAGES,
    BootstrapConfig,
    BootstrapConfigError,
    Context,
    Plan,
    Stage,
    StageReport,
    Status,
    UnsupportedHostError,
    apply_stage,
    authenticate_sudo,
    check_all,
    connection_problem,
    default_for,
    forget_contacts,
    host_problem,
    missing_keys,
    needs_sudo,
    own_project_exists,
    own_project_has_content,
    pdkboot_config_path,
    plan_all,
    project_on_host,
    question_for,
    resolve_host,
    site_url,
    surrey,
)
from prodockit.bootstrap import build_context as build_bootstrap_context
from prodockit.bootstrap import config_path as bootstrap_config_path
from prodockit.bootstrap import load as load_bootstrap_config
from prodockit.bootstrap import save as save_bootstrap_config
from prodockit.bootstrap.config import keep_out_of_git
from prodockit.bootstrap.recovery import (
    PdkbootRunJournal,
    pdkboot_report_path,
    recovery_advice,
)
from prodockit.init_tools import (
    COMPONENT_PURPOSE,
    InitToolsError,
    ci_environment,
    gitignore_lines,
    init_tools,
    install_commands,
)
from prodockit.mathjax import MathJaxError, install_mathjax
from prodockit.pdf.build import PdfBuildError
from prodockit.pdf.config import (
    build_pdf_from_built_site,
    build_pdf_from_zensical_config,
    build_source_bundle_from_zensical_config,
)
from prodockit.pdf.site import BuiltSiteError
from prodockit.pdf.source_bundle import SourceBundleError
from prodockit.sync_repo import SyncRepoError, sync_repo_metadata

_PDKBOOT_MODE: ContextVar[bool] = ContextVar("pdkboot_mode", default=False)
_P = ParamSpec("_P")
_R = TypeVar("_R")


# These are presentation groups, not execution units: stages still run in
# their established dependency order and are rechecked immediately before
# use. Keeping the grouping here means the replacement command can evolve
# without changing legacy bootstrap's model or output.
_PDKBOOT_PHASES: tuple[tuple[str, frozenset[str]], ...] = (
    ("Preflight", frozenset({"own-venv"})),
    ("Core tools", frozenset({"vscode", "git"})),
    (
        "Git and host",
        frozenset({"ssh-key", "ssh-config", "ssh-agent", "ssh-upload"}),
    ),
    (
        "Project",
        frozenset(
            {
                "clone-source",
                "clone",
                "fresh-history",
                "own-project",
                "pages",
                "remote",
                "identity",
            }
        ),
    ),
    (
        "Build toolchain",
        frozenset({"pandoc", "project-env", "node"}),
    ),
    (
        "Editor and project",
        frozenset({"extensions", "vscode-settings", "csl-style", "mathjax"}),
    ),
    ("Publish", frozenset({"first-push", "site"})),
)

# Legacy bootstrap asks where contents come from before it checks or creates
# the destination repository. pdkboot can correct that dependency without
# changing the command users already rely on: establish the host repository
# first, then decide whether it has usable contents, then clone. On a missing
# repository this lets the same run create an empty destination and continue
# from the template instead of reaching a later stage with no clone.
_PDKBOOT_PROJECT_ORDER = (
    "own-project",
    "pages",
    "clone-source",
    "clone",
    "fresh-history",
    "remote",
    "identity",
)


def _pdkboot_stages() -> tuple[Stage, ...]:
    """The pdkboot-only dependency order, leaving legacy STAGES untouched."""
    by_id = {stage.id: stage for stage in STAGES}
    project_ids = frozenset(_PDKBOOT_PROJECT_ORDER)
    first_project = min(i for i, stage in enumerate(STAGES) if stage.id in project_ids)
    before = tuple(stage for stage in STAGES[:first_project] if stage.id not in project_ids)
    after = tuple(stage for stage in STAGES[first_project:] if stage.id not in project_ids)
    return (*before, *(by_id[stage_id] for stage_id in _PDKBOOT_PROJECT_ORDER), *after)


_PDKBOOT_INSTALL_STAGES = frozenset(
    {
        "own-venv",
        "vscode",
        "git",
        "ssh-key",
        "clone",
        "pandoc",
        "project-env",
        "node",
        "extensions",
        "csl-style",
        "mathjax",
    }
)
_PDKBOOT_CONFIGURE_STAGES = frozenset(
    {"ssh-config", "ssh-agent", "remote", "identity", "vscode-settings"}
)


def _pdkboot_phase(stage_id: str) -> tuple[int, str] | None:
    """Return the display phase for a real bootstrap stage."""
    for number, (name, stage_ids) in enumerate(_PDKBOOT_PHASES, start=1):
        if stage_id in stage_ids:
            return number, name
    return None


def _pdkboot_action(report: StageReport, plan: Plan | None = None) -> str:
    """Describe work in terms a reader can use to judge its risk."""
    plan = plan or report.plan
    if plan is None:
        return "WAIT" if report.result.status is Status.BLOCKED else "CHECK"
    if plan.action:
        return plan.action.upper()
    if plan.choices:
        return "CHOOSE"
    if report.stage.id == "fresh-history":
        return "ARCHIVE"
    if report.stage.id == "ssh-upload":
        return "MANUAL"
    if report.stage.id == "git" and report.result.status is Status.WRONG:
        return "CONFIGURE"
    if plan.is_manual:
        return "MANUAL"
    if report.stage.id in {"first-push", "site"}:
        return "PUBLISH"
    if report.stage.id in _PDKBOOT_CONFIGURE_STAGES:
        return "CONFIGURE"
    if report.stage.id in _PDKBOOT_INSTALL_STAGES:
        return "INSTALL" if report.result.status is Status.MISSING else "REPAIR"
    if report.result.status is Status.WRONG:
        return "REPAIR"
    return "INSTALL" if plan.commands else "MANUAL"


def _pdkboot_work_summary(reports: Sequence[StageReport]) -> str:
    """Compact counts of the kinds of outstanding work in this pass."""
    order = ("INSTALL", "UPGRADE", "CONFIGURE", "REPAIR", "ARCHIVE", "CHOOSE", "MANUAL", "PUBLISH")
    counts = dict.fromkeys(order, 0)
    for report in reports:
        if report.needs_work and report.plan is not None:
            action = _pdkboot_action(report)
            counts[action] = counts.get(action, 0) + 1
    return " · ".join(f"{count} {action.lower()}" for action in order if (count := counts[action]))


def _pdkboot_journal(
    context: Context,
    reports: Sequence[StageReport],
    config_path: Path | None,
) -> PdkbootRunJournal | None:
    """Start the recovery record for an apply run, if it has a location."""
    if not context.pdkboot or config_path is None:
        return None
    stages = []
    for report in reports:
        status = {
            Status.OK: "satisfied",
            Status.BLOCKED: "waiting",
            Status.UNKNOWN: "unknown",
        }.get(report.result.status, "planned")
        stages.append(
            {
                "id": report.stage.id,
                "summary": report.stage.summary,
                "status": status,
                "detail": report.result.detail,
                "action": (
                    _pdkboot_action(report) if report.needs_work and report.plan is not None else ""
                ),
            }
        )
    path = pdkboot_report_path(config_path)
    journal = PdkbootRunJournal(
        path,
        version=__version__,
        config_path=config_path,
        resume=["pdkboot", "--config", str(config_path), "--apply"],
        stages=stages,
    )
    if journal.error is None:
        keep_out_of_git(
            path,
            reason="Local pdkboot recovery state; do not commit.",
        )
    return journal


def _resume_command(context: Context, config_path: Path | None) -> str:
    """The rerun that preserves this command and its chosen configuration."""
    if not context.pdkboot:
        return "prodockit bootstrap --apply"
    if config_path is None:
        return "pdkboot --apply"
    return f'pdkboot --config "{config_path}" --apply'


class _PdkbootCommandProgress:
    """Keep a quiet install visibly alive without hiding its failures."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = 0.0
        self._label = ""
        self._interactive = bool(sys.stdout.isatty())

    def __call__(self, event: str, number: int, total: int, command: list[str]) -> None:
        if event == "start":
            self._started = time.monotonic()
            self._label = f"command {number}/{total}: {_readable_command(command, 64)}"
            self._stop.clear()
            if not self._interactive:
                click.echo(f"  Working on {self._label} ...")
                return
            line = f"  ⠋ Working on {self._label} (0s)"
            click.echo(line, nl=False)
            self._thread = threading.Thread(target=self._pulse, daemon=True)
            self._thread.start()
            return

        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.2)
            self._thread = None
        elapsed = max(0, round(time.monotonic() - self._started))
        result = "failed" if event == "failed" else "done"
        prefix = "\r  " if self._interactive else "  "
        finished = f"  {self._label} - {result} ({elapsed}s)"
        clear = "\x1b[K" if self._interactive else ""
        click.echo(f"{prefix}{finished.removeprefix('  ')}{clear}")

    def _pulse(self) -> None:
        frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        frame = 0
        while not self._stop.wait(0.2):
            elapsed = max(0, round(time.monotonic() - self._started))
            line = f"  {frames[frame % len(frames)]} Working on {self._label} ({elapsed}s)"
            click.echo(f"\r{line}\x1b[K", nl=False)
            frame += 1


@contextmanager
def pdkboot_mode() -> Iterator[None]:
    """Run the bootstrap callback with the phased ``pdkboot`` behaviour."""
    token = _PDKBOOT_MODE.set(True)
    try:
        yield
    finally:
        _PDKBOOT_MODE.reset(token)


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


#: Host, name, login ID, assessed - then three more when it is assessed
#: (course, stage, year), or two when it is not (namespace, repository
#: name).
_SURREY_QUESTIONS_ASSESSED = 7
_SURREY_QUESTIONS_UNASSESSED = 6

#: The hosts offered by bootstrap, in the order a first-time reader sees
#: them. Surrey remains first because it is the existing default; GitHub
#: precedes the public GitLab service to match the requested menu (#534).
_HOST_OPTIONS = ("gitlab.surrey.ac.uk", "github.com", "gitlab.com")


def _ask_surrey(config: BootstrapConfig) -> None:
    """The short path for Surrey's GitLab (prodockit-extensions#420).

    Three questions, or four when the work is assessed, in place of five
    - because a student's email, GitLab username, group and repository
    name all follow from their login ID and course code. Every answer
    that can be derived is one fewer chance to type a namespace that does
    not exist and find out six stages later.
    """
    # Numbered against the assessed total until the answer to "assessed"
    # is known - that path asks one more question than the other, and it
    # reads as the default the same way `click.confirm`'s own default
    # does.
    login = surrey.login_id(
        click.prompt(
            f"3/{_SURREY_QUESTIONS_ASSESSED} Enter the 6 character email ID used "
            "for your Surrey login. For example, if your login ID is "
            "`ab1234@surrey.ac.uk`, enter `ab1234`"
        )
    )
    # Asked before the course code, not after: unassessed work never uses
    # a course code, so asking it first meant answering a question whose
    # answer was then thrown away (#458).
    assessed = click.confirm(
        f"4/{_SURREY_QUESTIONS_ASSESSED} Is this an assessed assignment?",
        default=True,
    )
    assessment = surrey.Assessment.not_assessed()
    course = ""
    year = ""
    namespace = ""
    project = ""
    if assessed:
        course = surrey.course_code(
            click.prompt(f"5/{_SURREY_QUESTIONS_ASSESSED} Your course code, e.g. `comm058`")
        )
        click.echo("")
        for number, name, _suffix in surrey.STAGES:
            click.echo(f"    {number}. {name}")
        while True:
            try:
                assessment = surrey.Assessment.at_stage(
                    click.prompt(
                        f"6/{_SURREY_QUESTIONS_ASSESSED} Which stage is it being "
                        "assessed at? [1, 2 or 3]"
                    )
                )
                break
            except ValueError:
                click.echo("  Type 1, 2 or 3.\n", err=True)
        click.echo("")
        while True:
            # Named here rather than above: the year question names SRA
            # and LSA, and nothing before it had said what those are. The
            # stage menu just shown introduces them, so this refers back
            # to it rather than repeating it (prodockit-extensions#437).
            year = surrey.module_year(
                click.prompt(
                    f"7/{_SURREY_QUESTIONS_ASSESSED} What year does the module "
                    "start in? A semester 2 module should be the year after the "
                    "Christmas break. For SRA and LSA the year should be the year "
                    "prior to the year the retake is being assessed.",
                    default=surrey.default_year(),
                    show_default=True,
                )
            )
            if year:
                break
            click.echo("  Four figures, e.g. 2026.\n", err=True)
    else:
        # Said rather than left to be noticed: the count changes here,
        # the same way it does when the host turns out to be Surrey's
        # GitLab above - a reader who saw "4/7" is owed the reason the
        # next question reads "5/6".
        click.echo(
            f"\n  Unassessed work has no course-derived group or attempt, so "
            f"this is {_SURREY_QUESTIONS_UNASSESSED} questions rather than "
            f"{_SURREY_QUESTIONS_ASSESSED}.\n"
        )
        # Unassessed work has no cohort group to go to and no attempt to
        # record, so neither is asked for. Both of these are offered as
        # the ordinary answer and typed over only by somebody who wants
        # something else.
        namespace = click.prompt(
            f"5/{_SURREY_QUESTIONS_UNASSESSED} The group or namespace the project lives under",
            default=login,
            show_default=True,
        ).strip()
        project = click.prompt(
            f"6/{_SURREY_QUESTIONS_UNASSESSED} The name of the repository, and "
            "of the folder it lands in here",
            default=f"report-{login}",
            show_default=True,
        ).strip()

    config.username = login
    config.email = surrey.email_for(login)
    config.namespace = namespace or surrey.namespace_for(course, login, assessment, year)
    config.project_name = project or surrey.project_name_for(course, login, year, assessment)
    config.project_dir = f"./{config.project_name}"

    # Bulleted rather than numbered: these are three facts to note, not
    # three things to do, and numbering them invites someone to look for
    # a step 4.
    click.echo("")
    click.echo(click.style("Note these down:", bold=True))
    for fact in (
        f"Your GitLab repository will be in the group or namespace {config.namespace}.",
        f"Your repository, and the folder it lands in here, will be {config.project_name}.",
        f"Commits will be signed {config.full_name} <{config.email}>.",
    ):
        click.echo(_wrapped(f"* {fact}", first="  ", rest="    "))


def _ask_each(
    config: BootstrapConfig,
    questions: list[tuple[str, str]],
    *,
    offset: int,
    total: int,
) -> None:
    """Asks `questions` in order, storing each answer as it comes.

    Numbered against `total` rather than against its own length, so two
    passes over one list still count up to the same end. Eight unnumbered
    questions read as an open-ended interrogation; "3/8" says how much is
    left, and matches how the stages themselves are reported.
    """
    for position, (key, question) in enumerate(questions, start=offset + 1):
        # Asked here rather than mid-run. A prompt during `--apply` is
        # answered once and forgotten, so a rerun asks again, and
        # declining leaves a stage undone with nowhere to go. Recorded as
        # configuration, the decision survives, shows in the report as a
        # setting rather than an inference, and leaves nothing surprising
        # to decide while commands are running
        # (prodockit-extensions#332).
        #
        # Asked in its own shape, with every path named - so the
        # free-text prompt below is skipped rather than asked a second
        # time in worse words.
        answered_here = key == "source_url" and not config.source_url.strip()
        if answered_here and _explain_existing_project(config):
            continue
        while True:
            # `default_for` fills a blank answer from one already given, so
            # a first run still has something sensible to press Enter on.
            if key == "host":
                current = resolve_host(default_for(config, key))
                default_choice = (
                    str(_HOST_OPTIONS.index(current.hostname) + 1)
                    if current is not None and current.hostname in _HOST_OPTIONS
                    else "1"
                )
                click.echo(f"{position}/{total} {question_for(config, key, question)}")
                for number, hostname in enumerate(_HOST_OPTIONS, start=1):
                    click.echo(f"  {number}. {hostname}")
                click.echo("")
                choice = click.prompt(
                    "  Select a git service",
                    type=click.Choice(["1", "2", "3"]),
                    default=default_choice,
                    show_choices=False,
                    show_default=True,
                )
                answer = _HOST_OPTIONS[int(choice) - 1]
            else:
                answer = click.prompt(
                    f"{position}/{total} {question_for(config, key, question)}",
                    default=default_for(config, key),
                    show_default=True,
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

    The host decides what follows it. Surrey's GitLab derives five of
    these answers from three questions of its own, so the list is chosen
    *after* the host is known rather than before
    (prodockit-extensions#420).
    """
    click.echo("\nPress Enter to keep the value in brackets.\n")
    if only is not None:
        wanted = [(k, q) for k, q in PROMPTS if k in only]
        # `source_url` is never reported missing - blank is a valid answer
        # - so a run filling in a few gaps skipped the question about an
        # existing project entirely, and ended without the summary that
        # goes with it. Included whenever it has no answer yet (#344).
        if not config.source_url.strip():
            wanted += [(k, q) for k, q in PROMPTS if k == "source_url"]
        _ask_each(config, wanted, offset=0, total=len(wanted))
        config.project_dir = str(config.resolved_project_dir(Path.home()))
        return config

    asked = dict(PROMPTS)
    # Numbered against the general list, because the shorter one is not
    # known to apply until this is answered.
    _ask_each(config, [("host", asked["host"])], offset=0, total=len(PROMPTS))
    if surrey.applies_to(config.host):
        # Said rather than left to be noticed: the count changes here, and
        # a reader who saw "1/8" is owed the reason it is now "2/5".
        click.echo(
            f"\n  {config.host} fills in the rest from your login ID and course "
            f"code, so this is {_SURREY_QUESTIONS_ASSESSED} questions rather "
            f"than {len(PROMPTS)}.\n"
        )
        _ask_each(
            config,
            [("full_name", asked["full_name"])],
            offset=1,
            total=_SURREY_QUESTIONS_ASSESSED,
        )
        _ask_surrey(config)
    else:
        rest = [(k, q) for k, q in PROMPTS if k != "host"]
        _ask_each(config, rest, offset=1, total=len(PROMPTS))
    # Stored absolute, though offered relative: `./report` is the clearest
    # thing to *read* at the prompt, and the worst thing to *keep* - it
    # would mean something different the next time bootstrap ran from
    # somewhere else.
    config.project_dir = str(config.resolved_project_dir(Path.home()))
    return config


def _took(seconds: float) -> str:
    """How long that was, in the units a reader would use out loud.

    Seconds up to a minute, then minutes and seconds - a PDF build is
    usually tens of seconds and occasionally several minutes, and
    "182.4s" makes a reader do the division themselves.
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(round(seconds), 60)
    return f"{minutes}m {remainder}s"


def _wrapped(text: str, *, first: str = "  ", rest: str = "  ") -> str:
    """A paragraph wrapped to the width, however long its values are.

    Written with hardcoded line breaks to begin with, which only line up
    for one length of project name: a longer one overflowed the first
    line and left the others short. The values here - a namespace, a
    project, a hostname - are exactly the parts that vary.
    """
    return textwrap.fill(
        " ".join(text.split()),
        width=78,
        initial_indent=first,
        subsequent_indent=rest,
        # A repository name is one thing, not a phrase. Left to itself
        # textwrap splits on the hyphens inside it, so
        # `report-linux-v2` could arrive as `report-linux-` on one line
        # and `v2` on the next - unreadable, and worse, uncopyable.
        break_long_words=False,
        break_on_hyphens=False,
    )


def _explain_existing_project(config: BootstrapConfig) -> bool:
    """Puts the choice about where the project comes from, and records it.

    The template is always one of the answers, named rather than implied.
    It is what happens when nothing else is chosen, and a reader who
    cannot see it among the options has to infer it from the absence of
    anything else - which is how the silent version of this decision went
    unnoticed in the first place (prodockit-extensions#332).

    Where a repository already has content, both of the other answers
    clone it: the difference is what becomes of its history and its
    remote, which is the only part there is to decide. "Existing project
    or template" framed that wrongly - somebody starting again still
    wants the contents that are already there.

    No default. One answer deletes commits that cannot be recovered, and
    none of them is safe enough to be taken by pressing Enter.
    """
    try:
        context = (
            build_bootstrap_context(config, pdkboot=True)
            if _PDKBOOT_MODE.get()
            else build_bootstrap_context(config)
        )
    except UnsupportedHostError:
        # Nothing can be asked about a host that cannot be used. The
        # ordinary prompt runs instead, and the host stage refuses later.
        return False
    # Qualified with the namespace: `report-windows-v1` alone is not
    # something `git clone` can resolve, and the reader should see the
    # same shape they would type themselves.
    name = f"{config.namespace.strip()}/{config.project_name.strip()}"
    host = config.host

    # "Cannot tell" is not "not there". On a machine with no SSH key yet
    # - which is every machine, before stage 3 - `git ls-remote` fails on
    # authentication, and saying the project does not exist told a reader
    # their work was missing when it was on the host in front of them
    # (prodockit-extensions#344).
    if project_on_host(context) is None:
        click.echo("")
        click.echo(
            _wrapped(
                f"Could not check whether {name} exists on {host} - this machine "
                "cannot reach it yet, which is what the SSH stages set up. The "
                "template will be used for the contents, and you can run "
                "--configure again afterwards to choose differently."
            )
        )
        click.echo("")
        config.source_url = ""
        config.history = ""
        return True

    if not own_project_has_content(context):
        # No decision here, because there is nothing to decide between: an
        # empty repository has no contents to keep, and cloning it would
        # leave no zensical.toml, no requirements.txt and no tools/ - every
        # later stage would fail on the absence.
        #
        # The permissions an issued repository carries are not lost by
        # this. They belong to the repository on the host, and the remote
        # stage points `origin` at it either way - so a student's work
        # still lands where their instructor can see it and their
        # classmates cannot. Said out loud, because "the template will be
        # used" on its own reads as though the issued repository were
        # being ignored.
        state = "is empty" if own_project_exists(context) else "does not exist yet"
        click.echo("")
        click.echo(
            _wrapped(
                f"{name} {state} on {host}, so the template will be used for the "
                f"contents. Your work will still be pushed to {name}, which keeps "
                "whatever permissions were set on it."
            )
        )
        click.echo("")
        config.source_url = ""
        config.history = ""
        return True

    if context.pdkboot:
        config.source_url = name
        config.history = "keep"
        click.echo("")
        click.echo(
            _wrapped(
                f"Option 1 selected automatically: {name} has work on {host}, so "
                "pdkboot will clone the full repository and keep its existing commit "
                "history and origin."
            )
        )
        click.echo("")
        return True

    click.echo("")
    click.echo(_wrapped(f"{name} already exists on {host} and has content in it."))
    click.echo(_wrapped("Do you want to:"))
    click.echo("")
    for number, option in enumerate(
        (
            f"clone the full repo {name!r}, then leave the existing git records "
            "and sync origin unchanged",
            f"clone the full repo {name!r}, then delete the existing git records "
            "and set up a new remote repo",
            "start from the template in a new repository of your own. Choose this "
            f"only if {name} is not the repository your work belongs in - a "
            "repository issued to you carries the permissions that decide who can "
            "read it, and a new one will not have them.",
        ),
        start=1,
    ):
        click.echo(_wrapped(option, first=f"  {number}. ", rest="     "))
    click.echo("")
    choice = click.prompt(
        "  Select 1, 2 or 3", type=click.Choice(["1", "2", "3"]), show_choices=False
    )
    if choice == "3":
        config.source_url = ""
        config.history = ""
    else:
        # Both clone the repository; only its history differs.
        config.source_url = name
        config.history = "keep" if choice == "1" else "reset"
    click.echo("")
    return True


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


def _offer_to_fill_gaps(config: BootstrapConfig, path: Path) -> tuple[BootstrapConfig, bool]:
    """Offers to ask for whatever is missing, rather than naming a file.

    Telling a first-time reader a value is "not set in your bootstrap
    config" points them at a file they may have no idea how to edit -
    and editing TOML by hand is exactly the kind of step this command
    exists to remove. So it asks.

    Skipped when stdin is not a terminal: a scripted or piped run must
    report and exit rather than block on a prompt nobody can answer.

    Returns the config and whether a *whole* configuration was answered
    here, which the caller stops on: twenty-three stage lines printed
    after it scroll the namespace and repository name off the screen, and
    those are the two things a reader has to take to a website
    (prodockit-extensions#433).
    """
    blank = missing_keys(config)
    answered_in_full = False
    # `host` has a default, so it is never *empty* and never reported
    # missing - which is right for somebody who has a stored answer, and
    # wrong for somebody who has never been asked. On a first run there is
    # no file yet, and the host decides everything below it, so it is
    # asked here too rather than only by `--configure`
    # (prodockit-extensions#279).
    if blank and not path.exists():
        blank = ["host", *blank]
    if not blank:
        return config, answered_in_full
    if not _is_interactive():
        click.echo(
            f"Not configured yet ({', '.join(blank)}). Run `prodockit bootstrap "
            "--configure` to answer the questions.\n",
            err=True,
        )
        return config, answered_in_full

    click.echo(f"Some details are not set yet: {', '.join(blank)}.")
    if not click.confirm("Answer them now?", default=True):
        click.echo("Carrying on - stages needing them will show as unknown.\n")
        return config, answered_in_full
    # Nothing set at all is the configure arriving by a different door,
    # not a repair - so it is asked as one. Passing the fields by name
    # took the general eight questions, which is how the path written for
    # Surrey students became the one path a student's first run never
    # took (prodockit-extensions#430).
    everything = {key for key, _ in PROMPTS} - {"source_url"}
    first_run = everything <= set(blank)
    answered_in_full = first_run
    config = _ask_for_configuration(config, only=None if first_run else blank)
    save_bootstrap_config(path, config)
    keep_out_of_git(path)
    click.echo(f"\nSaved to {path}\n")
    return config, answered_in_full


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


def _readable_command(command: Sequence[str], limit: int = 110) -> str:
    """One command, fit to be read rather than executed.

    A command carrying a whole script as one argument - `python -c`,
    `bash -c` - prints as a wall of source and asks the reader to approve
    it (prodockit-extensions#261). The script becomes a placeholder; the
    reader who wants the exact text has `--dry-run`, which is what that
    is for.
    """
    if len(command) >= 6 and command[1] == "-c" and "DYLD_FALLBACK_LIBRARY_PATH" in command[2]:
        return (
            f"update {command[3]} so activated project shells use "
            f"DYLD_FALLBACK_LIBRARY_PATH={command[5]}"
        )

    parts = []
    for argument in command:
        if "\n" in argument:
            first = argument.strip().splitlines()[0]
            parts.append(f"<script: {first[:40]}...>")
        else:
            parts.append(argument)
    rendered = " ".join(parts)
    if len(rendered) > limit:
        return rendered[: limit - 1] + "…"
    return rendered


def _announce_apply(
    context: Context,
    outstanding: int,
    reports: Sequence[StageReport] = (),
) -> None:
    """Says what is about to happen, before it starts happening.

    `--apply` opened straight into `[1/11] Visual Studio Code`, which
    tells a reader which step they are on and nothing about what they
    have started or where it will land
    (prodockit-extensions#258). Three facts are worth having before the
    first prompt: what this is, where it is working, and that the two
    things it cannot check for itself are as the reader intends.
    """
    click.echo("")
    click.echo(
        click.style(
            f"prodockit {__version__} - setting up your development environment",
            bold=True,
        )
    )
    click.echo("")
    # Which prodockit this is, not only which version it claims to be.
    # A report arrived showing commands that the version named in its own
    # header had not contained for a release - an older install, further
    # up PATH, in a shell that had never been reopened. The version alone
    # could not have shown that; the path does
    # (prodockit-extensions#399).
    click.echo(f"  Running:  {Path(sys.argv[0]).name} from {Path(prodockit.__file__).parent}")
    click.echo(f"  Host:     {context.host.hostname}")
    click.echo(f"  Project:  {context.config.resolved_project_dir(context.home)}")
    click.echo(f"  To do:    {outstanding} of {len(STAGES)} stages")
    if context.pdkboot and reports:
        summary = _pdkboot_work_summary(reports)
        if summary:
            click.echo(f"  Work:     {summary}")
    click.echo("")
    click.echo(
        "  Run this from the setup directory containing .pdkboot.toml. The project\n"
        "  shown above will be created beneath it. Use the virtual environment\n"
        "  prodockit itself is installed in - stage 16 builds the project's own.\n"
        "  Nothing is changed without asking first."
    )
    click.echo("")


def _apply_outstanding(
    context: Context, reports: list[StageReport], config_path: Path | None = None
) -> None:
    """Applies the stages that need it, asking before each.

    A stage whose work is *yours* - the two browser steps - is retried
    rather than failed. Checking too early is the normal case, not an
    error: you cannot create a project on a website and have it exist
    before you have done it. Exiting at that point threw away every stage
    already completed and made the reader start again.
    """
    journal = _pdkboot_journal(context, reports, config_path)
    if journal is not None and journal.error is not None:
        click.echo(f"Warning: recovery report unavailable: {journal.error}", err=True)
        journal = None

    outstanding = [r for r in reports if r.needs_work and r.plan is not None]
    if not outstanding:
        if journal is not None:
            journal.settle()
        click.echo("Nothing to do - every stage is either set up or waiting on configuration.")
        if journal is not None:
            click.echo(f"Recovery report: {journal.path}")
        return

    _announce_apply(context, len(outstanding), reports)
    if journal is not None:
        click.echo(f"  Report:   {journal.path}")
        click.echo("")
    try:
        _work_through(context, reports, config_path, journal)
    except _StartAgain as done_but_unseen:
        if journal is not None:
            journal.finish("waiting")
        # Not an error, and not a stage left undone: the reader did what
        # was asked, and this process simply cannot see it (#397).
        click.echo("")
        click.echo(f"  {done_but_unseen} is done, but this run cannot see it.")
        click.echo("")
        resume_command = _resume_command(context, config_path)
        click.echo(f"Run `{resume_command}` again to carry on from here.")
        return
    except (KeyboardInterrupt, click.Abort):
        if journal is not None:
            journal.finish(
                "interrupted",
                failure={
                    "stage": journal.data["current_stage"],
                    "message": "run interrupted by the user",
                },
            )
        click.echo("\nInterrupted. No later stages were started.", err=True)
        if journal is not None:
            click.echo(f"Recovery report: {journal.path}", err=True)
        raise
    except SystemExit:
        if journal is not None and journal.data["status"] == "running":
            journal.finish(
                "failed",
                failure={
                    "stage": journal.data["current_stage"],
                    "message": "stage did not complete",
                },
            )
        raise
    if journal is not None:
        journal.settle()
    click.echo("")
    check_command = "pdkboot" if context.pdkboot else "prodockit bootstrap"
    click.echo(f"Finished. Run `{check_command}` to confirm.")
    if journal is not None:
        click.echo(f"Recovery report: {journal.path}")


def _work_through(
    context: Context,
    reports: list[StageReport],
    config_path: Path | None,
    journal: PdkbootRunJournal | None = None,
) -> None:
    """Each stage in turn, asking before it acts on any of them."""

    # Every stage, not just the ones needing work. A run that skipped the
    # rest silently jumped from `[1/17] Git` to `[2/17] SSH keypair` while
    # actually being at stages 2 and 3 of nineteen - so the numbers agreed
    # with nothing the reader could check, and the stages already set up
    # were invisible rather than reassuring
    # (prodockit-extensions#284).
    total = len(reports)
    shown_phase: tuple[int, str] | None = None
    for number, report in enumerate(reports, start=1):
        # Asked again, here, rather than trusting the pass taken before
        # any of this ran. Earlier stages change the machine the later
        # ones are about: "where the project comes from" was decided
        # before there was an SSH key, found nothing on the host, and
        # reported `ok` - so the question was skipped on the very run
        # that had just made the host reachable
        # (prodockit-extensions#351).
        #
        # Within a pass the memo makes a repeat free; between stages it
        # must not, which is what dropping it here buys.
        forget_contacts(context)
        result = report.stage.check(context)
        plannable = result.needs_work and result.status not in (Status.UNKNOWN, Status.BLOCKED)
        report = StageReport(
            stage=report.stage,
            result=result,
            plan=report.stage.plan(context) if plannable else None,
        )
        phase = _pdkboot_phase(report.stage.id) if context.pdkboot else None
        if phase is not None and phase != shown_phase:
            phase_number, phase_name = phase
            click.echo("")
            boundary = click.style("═" * 78, fg="bright_cyan")
            click.echo(boundary)
            click.echo(
                click.style(
                    f"Phase {phase_number}/{len(_PDKBOOT_PHASES)} — {phase_name}",
                    bold=True,
                    fg="bright_cyan",
                )
            )
            click.echo(boundary)
            shown_phase = phase
        if not report.needs_work:
            if journal is not None:
                journal.stage(
                    report.stage.id,
                    "satisfied",
                    detail=report.result.detail,
                )
            # With the detail, as the report itself prints it. Without
            # it, "ok" said nothing about *why* - and for the stage that
            # decides where the project comes from, "searched and found
            # nothing" and "never managed to look" read identically
            # (#356).
            detail = f" - {report.result.detail}" if report.result.detail else ""
            click.echo(f"{number:2}  ok    {report.stage.summary}{detail}")
            continue
        if report.plan is None:
            # Distinguish a stage whose state is unknown from one waiting on
            # a prerequisite. Both have no safe action, but the reader needs
            # different information to recover.
            detail = f" - {report.result.detail}" if report.result.detail else ""
            symbol = (
                "WAIT" if context.pdkboot and report.result.status is Status.BLOCKED else "?   "
            )
            click.echo(f"{number:2}  {symbol}  {report.stage.summary}{detail}")
            if journal is not None:
                journal.stage(
                    report.stage.id,
                    ("waiting" if report.result.status is Status.BLOCKED else "unknown"),
                    detail=report.result.detail,
                )
            continue
        # Built now, not at the start of the run. `plan_all` computes every
        # plan before anything has been applied, so a plan that depends on
        # what an earlier stage creates was describing a machine that no
        # longer exists by the time the reader sees it.
        #
        # The SSH upload step is the case that showed it: it embeds the
        # public key, and on a fresh machine the keypair stage has not run
        # when the plans are built - so it fell back to "paste the contents
        # of ~/.ssh/id_ed25519_gitlab.pub" about a key that existed by the
        # time the step was reached (prodockit-extensions#281).
        #
        # In pdkboot this exact plan is also passed to `apply_stage`: mutable
        # or network-sensitive commands must not change after the reader has
        # reviewed and approved them. Legacy bootstrap retains its existing
        # re-planning behaviour until it is deliberately replaced.
        plan = report.plan if context.pdkboot else report.stage.plan(context)
        action = _pdkboot_action(report, plan) if context.pdkboot else ""
        if journal is not None:
            journal.stage(
                report.stage.id,
                "running",
                detail=report.result.detail,
                action=action,
            )

        click.echo("")
        if context.pdkboot:
            # A full-width boundary survives terminals without colour and
            # pasted logs. The old bold-only ``[15/23]`` line disappeared
            # among instructions and command output during long installs.
            click.echo(click.style("─" * 78, fg="cyan"))
            heading = f"Stage [{number}/{total}] {report.stage.summary}"
            click.echo(click.style(heading, bold=True, fg="cyan"))
        else:
            click.echo(click.style(f"[{number}/{total}] {report.stage.summary}", bold=True))
        if context.pdkboot:
            click.echo(f"  Action:   {action}")
            click.echo(f"  Current:  {report.result.detail or 'not yet satisfied'}")
            click.echo(f"  Goal:     {report.stage.summary}")
        elif report.result.detail:
            click.echo(f"        {report.result.detail}")
        click.echo("")

        # A plan's manual steps are ordered against its commands rather
        # than merely coexisting with them: `instructions` prepare for the
        # commands, `follow_up` finishes what they started. Both orderings
        # have shipped broken - instructions-only skipped `brew install`
        # entirely (#230), and commands-first ran the SSH probe before the
        # reader had been told to upload the key, which fails by
        # definition and ended the run (#234).
        if plan.choices:
            # A choice, not a confirmation. Rendered with no default,
            # because one of these answers deletes commits that cannot be
            # recovered (#348).
            for line in plan.instructions:
                click.echo(_wrapped(line))
            click.echo("")
            for number, option in enumerate(plan.choices, start=1):
                click.echo(_wrapped(option, first=f"  {number}. ", rest="     "))
            click.echo("")
            picked = click.prompt(
                f"  {plan.confirm}",
                type=click.Choice([str(n) for n in range(1, len(plan.choices) + 1)]),
                show_choices=False,
            )
            _record_clone_source(context.config, picked, config_path)
            if journal is not None:
                journal.stage(report.stage.id, "completed", action=action)
            click.echo("")
            continue

        if plan.instructions:
            _show_steps("  What you need to do:", plan.instructions)
            if not plan.commands:
                # Guide and verify. The stage's own check is the
                # verification, and "not finished yet" is the normal
                # answer to it, not a failure - so it asks again.
                verified = _verify_until_done(context, report.stage, plan, config_path)
                if journal is not None:
                    journal.stage(
                        report.stage.id,
                        "completed" if verified else "skipped",
                        action=action,
                    )
                if not verified:
                    click.echo("  skipped")
                continue
            if not context.pdkboot:
                if not click.confirm(f"  {plan.confirm}", default=not plan.destructive):
                    if journal is not None:
                        journal.stage(report.stage.id, "skipped", action=action)
                    click.echo("  skipped")
                    continue
                click.echo("")
        if plan.commands:
            if plan.describe:
                click.echo("  Will do:")
                click.echo(f"    {plan.describe}")
            else:
                click.echo("  Will run:")
                for command in plan.commands:
                    click.echo(
                        _wrapped(
                            _readable_command(command, 10_000),
                            first="    ",
                            rest="      ",
                        )
                    )
            if plan.cwd:
                click.echo(f"  Working directory: {plan.cwd}")
            click.echo("")
            # Yes unless it destroys something. A reader who typed
            # `--apply` has said what they want; making them say it again
            # seventeen times, with the answer changing according to a
            # status they cannot see, is how a prompt stops being read
            # (#259).
            default_yes = not plan.destructive
            count = len(plan.commands)
            if context.pdkboot and plan.instructions and plan.confirm:
                question = plan.confirm
            elif plan.describe:
                question = f"Apply {count} change{'s' if count != 1 else ''}?"
            else:
                question = f"Run {count} command{'s' if count != 1 else ''}?"
            if not click.confirm(f"  {question}", default=default_yes):
                if journal is not None:
                    journal.stage(report.stage.id, "skipped", action=action)
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

            # Output streams from here, so the reader can see progress -
            # but the *check* that follows is captured and can take
            # seconds (an `ssh -T` carries a ten-second connect timeout),
            # which reads as a hang right after a command has visibly
            # finished. So both ends are announced (#244).
            if context.pdkboot and plan.needs_terminal:
                click.echo("  This command needs the terminal; its output will be shown.")
            elif context.pdkboot:
                click.echo("  Routine command output is hidden; failures are shown in full.")
            else:
                click.echo("  Working - the commands' own output follows.")
                click.echo("")
            outcome = (
                apply_stage(
                    context,
                    report.stage,
                    plan,
                    progress=None if plan.needs_terminal else _PdkbootCommandProgress(),
                )
                if context.pdkboot
                else apply_stage(context, report.stage)
            )
            click.echo("")
            click.echo("  Commands finished, checking the result...")
            if outcome.failed is not None:
                # The command's own output has just gone past on screen,
                # so there is usually no captured stderr to summarise -
                # point at what the reader can see rather than invent a
                # sentence (#244).
                captured = "\n".join(
                    part.strip()
                    for part in (outcome.failed.stdout, outcome.failed.stderr)
                    if part.strip()
                )
                if context.pdkboot and captured:
                    click.echo("  Command output:", err=True)
                    for line in captured.splitlines():
                        click.echo(f"    {line}", err=True)
                summary = (
                    _first_meaningful_line(outcome.failed.stderr)
                    if outcome.failed.stderr.strip()
                    else (
                        _first_meaningful_line(outcome.failed.stdout)
                        if outcome.failed.stdout.strip()
                        else f"exit status {outcome.failed.returncode}"
                    )
                )
                click.echo(f"  failed: {summary}", err=True)
                click.echo("  Stopping - later stages depend on this one.", err=True)
                advice = (
                    recovery_advice(
                        report.stage.id,
                        context.platform,
                        outcome.ran[-1] if outcome.ran else [],
                        outcome.failed,
                    )
                    if context.pdkboot
                    else None
                )
                if advice is not None:
                    _show_steps("  Recovery:", list(advice.steps))
                if context.pdkboot:
                    click.echo(
                        f"  Fix the problem, then run `{_resume_command(context, config_path)}` "
                        "again; "
                        "completed stages will be rechecked and skipped.",
                        err=True,
                    )
                if journal is not None:
                    journal.stage(
                        report.stage.id,
                        "failed",
                        detail=summary,
                        action=action,
                    )
                    journal.finish(
                        "failed",
                        failure={
                            "stage": report.stage.id,
                            "returncode": outcome.failed.returncode,
                            "message": summary,
                            "category": advice.category if advice is not None else "",
                            "recovery": list(advice.steps) if advice is not None else [],
                        },
                    )
                sys.exit(1)
            if outcome.ok and not plan.follow_up:
                recovered_detail = ""
                if outcome.recovered is not None:
                    recovered_detail = (
                        "command returned "
                        f"{outcome.recovered.returncode}, but the stage now verifies correctly"
                    )
                    click.echo(f"  recovered: {recovered_detail}")
                    captured = "\n".join(
                        part.strip()
                        for part in (
                            outcome.recovered.stdout,
                            outcome.recovered.stderr,
                        )
                        if part.strip()
                    )
                    if captured:
                        click.echo("  Command output:")
                        for line in captured.splitlines():
                            click.echo(f"    {line}")
                if journal is not None:
                    journal.stage(
                        report.stage.id,
                        "completed",
                        detail=recovered_detail,
                        action=action,
                    )
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
                if context.pdkboot:
                    click.echo(
                        f"  Fix the problem, then run `{_resume_command(context, config_path)}` "
                        "again; "
                        "completed stages will be rechecked and skipped.",
                        err=True,
                    )
                if journal is not None:
                    journal.stage(
                        report.stage.id,
                        "failed",
                        detail=detail,
                        action=action,
                    )
                    journal.finish(
                        "failed",
                        failure={"stage": report.stage.id, "message": detail},
                    )
                sys.exit(1)
            verified = _verify_until_done(context, report.stage, plan, config_path)
            if journal is not None:
                journal.stage(
                    report.stage.id,
                    "completed" if verified else "skipped",
                    action=action,
                )
            if not verified:
                click.echo("  skipped")
            continue

        # No commands and no manual steps — nothing to do for this stage.
        # Should not happen, but not worth crashing over.
        if journal is not None:
            journal.stage(report.stage.id, "skipped", action=action)
        click.echo("  nothing to do")  # pragma: no cover


def _echo_wrapped_instruction(instruction: str) -> None:
    """One `--dry-run` instruction line, keeping a multi-line step aligned."""
    first, *rest = instruction.splitlines() or [""]
    click.echo(f"        you: {first}")
    for line in rest:
        click.echo(f"             {line}")


def _echo_dry_run_command(command: Sequence[str]) -> None:
    """Show an exact command without losing indentation inside scripts."""
    rendered = " ".join(command)
    first, *rest = rendered.splitlines() or [""]
    click.echo(f"        run: {first}")
    for line in rest:
        click.echo(f"             {line}")


_PDKBOOT_WAIT_DETAILS = (
    "no project directory yet",
    "no project to install",
    "no clone to repoint yet",
    "no clone to set an identity in yet",
    "could not list extensions - is VS Code installed?",
)


def _pdkboot_waiting(report: StageReport) -> bool:
    """Whether a pdkboot report has no safe work until a prerequisite exists."""
    return report.result.status is Status.BLOCKED or (
        report.result.status is Status.MISSING
        and report.result.detail.startswith(_PDKBOOT_WAIT_DETAILS)
    )


def _report_contacts(context: Context) -> None:
    """Says how many times this pass reached the host.

    Printed rather than merely recorded because the number is the point:
    a host that stops answering after too many logins in quick succession
    is answering a question about *this tool's* behaviour, and the only
    way to tune anything later is to know what a real run costs
    (prodockit-extensions#304).

    Silent when nothing reached the host, which is the common case for a
    run that stops early on unanswered configuration.
    """
    contacts = context.contacts
    if contacts is None or not contacts.asked:
        return
    saved = f", {contacts.reused} reused" if contacts.reused else ""
    click.echo(f"{contacts.made} connection(s) to {context.host.hostname}{saved}.")


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


def _record_clone_source(config: BootstrapConfig, picked: str, config_path: Path | None) -> None:
    """Writes down which of the three paths was chosen.

    Both of the first two clone the repository itself - the difference is
    what becomes of its history and its remote, which is the only part
    there is to decide. Saved immediately, so a rerun reads the answer
    rather than asking again.
    """
    if picked == "3":
        config.source_url = ""
        config.history = ""
    else:
        config.source_url = f"{config.namespace.strip()}/{config.project_name.strip()}"
        config.history = "keep" if picked == "1" else "reset"
    if config_path is not None:
        save_bootstrap_config(config_path, config)


class _StartAgain(Exception):
    """A step whose effect only a new run can see has just been done.

    Carries the stage it happened in, so the run can end by saying what
    to type next rather than by re-checking something that cannot have
    changed in this process (prodockit-extensions#397).
    """


def _typed_yes(question: str) -> bool:
    """A question the Enter key cannot answer.

    `[Y/n]` is answered by pressing Enter, and a reader twelve stages
    into a twenty-three stage setup presses it in rhythm. For a browser
    step that means claiming to have done something they have not, and
    the run continues as though a manual stage was complete
    (prodockit-extensions#374). Typing the word costs three seconds and
    buys one moment of attention at the only points where the tool cannot
    do the work itself.

    "no" is a real answer, not a way of getting past the prompt: it
    leaves the stage outstanding and says so at the end.
    """
    while True:
        said = click.prompt(f"  {question} (yes/no)", default="", show_default=False)
        answer = said.strip().lower()
        if answer == "yes":
            return True
        if answer in {"no", "n"}:
            return False
        click.echo("  type 'yes' once it is done, or 'no' to leave it for now")


def _verify_until_done(
    context: Context,
    stage: Stage,
    plan: Plan,
    config_path: Path | None = None,
) -> bool:
    """Waits for a manual step, re-checking until it takes or you stop.

    Returns whether it ended up satisfied. A failed check here means "not
    yet", not "broken" - so it says so, and asks again.
    """
    while True:
        if not _typed_yes(plan.confirm):
            return False
        # The reader has just been to a browser, so anything remembered
        # about the host is older than what they did. Without this the
        # retry loop replayed its first answer and "Try again?" could
        # never succeed (#321).
        forget_contacts(context)
        result = stage.check(context)
        if not result.needs_work:
            _remember_browser_confirmation(context, stage, config_path)
            click.echo("  confirmed")
            return True
        if not result.verifiable:
            # Nothing gained by asking again: this check cannot see the
            # answer from outside, whatever the reader just did (#374).
            # Their word is taken, and the stage that can prove it says
            # so at the end of the run.
            _remember_browser_confirmation(context, stage, config_path)
            click.echo(f"  taken on trust - {result.detail}")
            return True
        if plan.needs_a_new_run:
            # Asked first, answered second. A started service *is* usually
            # visible to the next command that looks - `ssh-add` opens the
            # agent's pipe afresh each time - so the check above is given
            # its chance, and a run that can carry on carries on
            # (prodockit-extensions#435).
            #
            # Only when it still cannot be seen does the run end, because
            # asking again would put the same question to the same
            # unchanged answer.
            raise _StartAgain(stage.summary)
        if result.status is Status.BLOCKED:
            # Waiting on an earlier stage, not on anything the reader can
            # do in a browser. Asking again would loop for ever on a
            # question they have already answered correctly (#336).
            click.echo(f"  waiting - {result.detail}")
            return False
        click.echo(f"  not there yet - {result.detail}")
        if not click.confirm("  Try again?", default=True):
            return False


def _remember_browser_confirmation(
    context: Context,
    stage: Stage,
    config_path: Path | None,
) -> None:
    """Persist the site URL an author has just confirmed in a browser."""
    if not context.pdkboot or stage.id != "site" or config_path is None:
        return
    context.config.confirmed_site_url = site_url(context)
    save_bootstrap_config(config_path, context.config)


def _shared_file_report(states: Sequence[Any], *, verbose: bool = False) -> None:
    """Print shared-file states without making pins depend on CLI internals."""

    click.echo("\nShared files")
    for state in states:
        # Imported lazily by each command; keeping this display helper
        # structural avoids importing a maintenance-only module at startup.
        target = state.file.target
        status = state.status
        label = {"current": "ok", "missing": "MISS", "different": "WRONG"}[status]
        click.echo(f"  {label:<5} {target}")
        if verbose:
            click.echo(
                f"        expected sha256 {state.expected_sha256}"
            )
            actual = state.actual_sha256
            click.echo(f"        actual   sha256 {actual or 'missing'}")


@main.command("shared-files")
@click.option(
    "-r",
    "--root",
    default=".",
    show_default=True,
    help="Project root containing .prodockit-shared-files.toml.",
)
@click.option(
    "--check",
    is_flag=True,
    help="Exit non-zero if a managed file is missing or differs.",
)
@click.option("--apply", "apply_changes", is_flag=True, help="Replace missing or different files.")
@click.option("--verbose", is_flag=True, help="Also show expected and actual SHA-256 hashes.")
def shared_files(root: str, check: bool, apply_changes: bool, verbose: bool) -> None:
    """Check or restore files shared by the prodockit documentation sites.

    The installed prodockit release supplies the canonical content. A
    repository opts in through `.prodockit-shared-files.toml`; no sibling
    checkout or network request is used.
    """

    from prodockit.shared_files import SharedFileError, apply, drift, inspect

    if check and apply_changes:
        raise click.UsageError("--check and --apply cannot be used together")
    try:
        states = inspect(root)
    except SharedFileError as error:
        raise click.ClickException(str(error)) from error

    if not states:
        click.echo("No shared-file manifest found. Nothing to check.")
        return

    _shared_file_report(states, verbose=verbose)
    problems = drift(states)
    if check:
        if problems:
            click.echo("\nShared-file drift detected.", err=True)
            click.echo("Run `prodockit shared-files --apply`, review the changes, and commit them.")
            raise click.exceptions.Exit(1)
        click.echo("\nEvery managed shared file matches the installed prodockit release.")
        return

    if not apply_changes:
        if problems:
            click.echo("\nNo changes made.")
            click.echo("Run `prodockit shared-files --apply` to replace the files shown above.")
        else:
            click.echo("\nEvery managed shared file is already current.")
        return

    try:
        changed = apply(root, states)
    except SharedFileError as error:
        raise click.ClickException(str(error)) from error
    if not changed:
        click.echo("\nEvery managed shared file is already current. No changes made.")
        return
    click.echo("\nUpdated:")
    for path in changed:
        click.echo(f"  {path}")
    click.echo("\nReview the local changes before committing them.")


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
    help=(
        ".pdk-bootstrap.toml is the default in the current directory. Pass "
        "another bootstrap config path; an existing legacy user config is still read."
    ),
)
def bootstrap(
    check_only: bool,
    dry_run: bool,
    apply_stages: bool,
    configure: bool,
    config_file: str | None,
) -> None:
    """Set up this machine and your project from scratch.

    Checks all 23 stages - prodockit's own environment, editor, git, SSH
    key/config/agent/upload, clone, history, remote, commit identity, the
    project's own environment, pandoc, Node and the rest - and reports
    which are already done. Rerunnable: a stage that is set up correctly
    is left alone.

    This cannot be the first thing you run: it is a prodockit command, so
    Python and `pip install prodockit` necessarily come first.

    With no options this reports what it finds and changes nothing - the
    safe default, and the question most people are actually asking. Phase
    1 installs nothing either way.
    """
    modes = {
        "--check": check_only,
        "--dry-run": dry_run,
        "--apply": apply_stages,
        "--configure": configure,
    }
    selected = [name for name, enabled in modes.items() if enabled]
    if len(selected) > 1:
        raise click.UsageError(f"Choose only one operating mode; got {', '.join(selected)}.")

    # Bare `prodockit bootstrap` is a checking run. Defaulting to the
    # read-only behaviour matters more than usual here: the alternative
    # default is a command that starts installing software because someone
    # typed it to see what it did.
    if not dry_run and not apply_stages and not configure:
        check_only = True

    path = (
        Path(config_file)
        if config_file
        else (pdkboot_config_path() if _PDKBOOT_MODE.get() else bootstrap_config_path())
    )
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
        if keep_out_of_git(path):
            click.echo(f"Added {path.name} to .gitignore - it holds your own details.")
        if configure:
            return

    # Offer to fill anything still blank before checking, so the run that
    # follows can actually judge the project stages rather than reporting
    # three unknowns and leaving the reader to work out what to do.
    config, answered_in_full = _offer_to_fill_gaps(config, path)
    if answered_in_full:
        # Stopping where `--configure` stops, and for the same reason: the
        # run has just told the reader the namespace and repository name
        # to note down, and a stage report would scroll both away (#433).
        check_command = "pdkboot" if _PDKBOOT_MODE.get() else "prodockit bootstrap"
        click.echo(f"Run `{check_command}` to see what is set up.")
        return

    try:
        # The pdkboot profile affects how the command runner itself is
        # constructed, not only how reports are presented. On Windows the
        # runner must give Git the built-in OpenSSH executable connected to
        # Windows' ssh-agent. Setting ``context.pdkboot`` afterwards left
        # the already-built runner in legacy mode: ``ssh -T`` authenticated,
        # while ``git ls-remote`` immediately reported ``Permission denied``.
        context = (
            build_bootstrap_context(config, pdkboot=True)
            if _PDKBOOT_MODE.get()
            else build_bootstrap_context(config)
        )
    except UnsupportedHostError as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    if context.pdkboot:
        stages = _pdkboot_stages()
        reports = check_all(context, stages) if check_only else plan_all(context, stages)
    else:
        reports = check_all(context) if check_only else plan_all(context)

    if apply_stages:
        _apply_outstanding(context, reports, path)
        return

    symbols = {
        Status.OK: "ok  ",
        Status.MISSING: "MISS",
        Status.WRONG: "WRONG",
        Status.UNKNOWN: "?   ",
        Status.BLOCKED: "WAIT",
    }
    for number, report in enumerate(reports, start=1):
        symbol = symbols[report.result.status]
        waiting = context.pdkboot and _pdkboot_waiting(report)
        if waiting:
            symbol = "WAIT"
        detail = f" - {report.result.detail}" if report.result.detail else ""
        click.echo(f"{number:2}  {symbol}  {report.stage.summary}{detail}")
        if dry_run and report.plan is not None and not waiting:
            # In the order they actually happen: prepare, run, finish.
            for instruction in report.plan.instructions:
                _echo_wrapped_instruction(instruction)
            if report.plan.cwd:
                click.echo(f"        in:  {report.plan.cwd}")
            for command in report.plan.commands:
                _echo_dry_run_command(command)
            for instruction in report.plan.follow_up:
                _echo_wrapped_instruction(instruction)

    outstanding = [r for r in reports if r.needs_work]
    click.echo()
    _report_contacts(context)
    if not outstanding:
        click.echo(f"All {len(reports)} stages are set up.")
        return
    click.echo(f"{len(outstanding)} of {len(reports)} stages need work.")
    if check_only:
        # Both halves, because only one was ever offered. A reader who has
        # just been told fourteen stages need work is being shown how to
        # look, and not how to act - and `--apply` is the one they came
        # for (prodockit-extensions#376).
        click.echo(
            "Run with --dry-run to see how the configuration will be applied, "
            "or with --apply to apply it."
        )
    elif dry_run:
        # The same gap at the other end: a reader who has just read the
        # commands is the one most ready to run them, and nothing said how
        # (#376).
        click.echo("Run with --apply to work through these, asking before each one.")
    # Non-zero so this is usable as a check in a script, matching
    # `sync-repo --check` and `pins --check`.
    sys.exit(1)


def _run_pdf_command(
    config_file: str,
    markdown_file: str | None,
    *,
    legacy: bool,
) -> None:
    """Shared presentation for the public and legacy PDF renderers."""
    builder = build_pdf_from_zensical_config if legacy else build_pdf_from_built_site
    if markdown_file:
        click.echo(f"Building PDF from {config_file} using {markdown_file}...")
    else:
        click.echo(f"Building PDF from {config_file}...")

    def say(number: int, total: int, title: str) -> None:
        # A PDF build is minutes of silence otherwise, and a silent
        # terminal is indistinguishable from a hung one - the same
        # reasoning as the install output in `bootstrap --apply`
        # (prodockit-extensions#375).
        click.echo(f"  [{number}/{total}] {title}")

    started = time.monotonic()
    try:
        output_path = builder(config_file, markdown_file=markdown_file, on_stage=say)
    except (BuiltSiteError, PdfBuildError, SourceBundleError, ValueError, OSError) as error:
        click.echo(f"Error: {error}", err=True)
        _echo_captured_stderr(error)
        sys.exit(1)
    click.echo(f"Wrote {output_path} in {_took(time.monotonic() - started)}")


def _pdf_options(command: Callable[_P, _R]) -> Callable[_P, _R]:
    """Apply the identical input options to the public and legacy commands."""
    command = click.option(
        "-m",
        "--markdown-file",
        default=None,
        help=(
            "Include only this Markdown file in the PDF (relative to docs_dir), "
            "ignoring nav for the PDF contents. The public pdf command still "
            "rebuilds the full site; CONFIG_FILE supplies everything else."
        ),
    )(command)
    return click.option(
        "-f",
        "--config-file",
        default="zensical.toml",
        show_default=True,
        help="Path to your project's Zensical config file.",
    )(command)


@main.command()
@_pdf_options
def pdf(config_file: str, markdown_file: str | None) -> None:
    """Build a PDF from your project, using CONFIG_FILE for everything -
    nav, docs directory, fonts, page size, and so on. See the PDF
    generation docs for the full list of `zensical.toml` settings this
    reads."""
    _run_pdf_command(config_file, markdown_file, legacy=False)


@main.command("pdf-legacy", hidden=True)
@_pdf_options
def pdf_legacy(config_file: str, markdown_file: str | None) -> None:
    """Legacy PDF renderer using Zensical's undocumented Python APIs."""
    _run_pdf_command(config_file, markdown_file, legacy=True)


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


@main.command("init-mathjax")
@click.option(
    "--root",
    default=".",
    show_default=True,
    help="Project directory to install into.",
)
@click.option(
    "--no-gitignore",
    is_flag=True,
    help="Do not add the installed files to .gitignore.",
)
def init_mathjax_command(root: str, no_gitignore: bool) -> None:
    """Install MathJax for the website, from tools/mathjax's own copy.

    Writes `docs/javascripts/mathjax.js` and copies the browser bundle
    beside it, out of the `mathjax-full` install `prodockit pdf` already
    renders through - so a formula cannot typeset one way on screen and
    another in print, and the site works offline.

    Neither file is committed: both are added to `.gitignore`, because
    the bundle is third-party code that does not belong in your
    repository. Anything that builds the site without running
    `prodockit bootstrap` - a CI job, most obviously - should run this
    first.
    """
    try:
        result = install_mathjax(root, update_gitignore=not no_gitignore)
    except MathJaxError as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)
    click.echo(f"Wrote {result.config}")
    click.echo(f"Copied {result.bundle}")
    for line in result.ignored:
        click.echo(f"Ignored {line}")


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
        click.echo("\nIn CI, mermaid-cli drives Chrome through Puppeteer. Install Chrome and set:")
        for name, value in ci_environment().items():
            click.echo(f"  {name}: {value}")
        click.echo(
            "  (PUPPETEER_SKIP_DOWNLOAD, not the older "
            "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD, which puppeteer 25.x ignores)"
        )


_ADOPT_PHASES = ("Assess", "Integrate", "Optional renderers", "Verify")


def _adopt_phase_heading(number: int, name: str) -> None:
    click.echo("")
    click.echo(click.style("═" * 78, bold=True, fg="bright_cyan"))
    click.echo(click.style(f"Phase {number}/{len(_ADOPT_PHASES)} — {name}", bold=True))
    click.echo(click.style("═" * 78, bold=True, fg="bright_cyan"))


def _adopt_stage_heading(number: int, total: int, summary: str) -> None:
    click.echo("")
    click.echo(click.style("─" * 78, fg="cyan"))
    click.echo(click.style(f"Stage [{number}/{total}] {summary}", bold=True, fg="cyan"))


@main.command("adopt")
@click.option(
    "--configure",
    is_flag=True,
    help="Choose optional components and save the choices for this project.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show the stages and changes without writing or installing anything.",
)
@click.option(
    "--apply",
    is_flag=True,
    help="Apply the required stages, asking before each change.",
)
@click.option(
    "--mermaid/--no-mermaid",
    default=None,
    help="Include or omit Mermaid diagram rendering. Omitted unless selected.",
)
@click.option(
    "--maths/--no-maths",
    default=None,
    help="Include or omit MathJax rendering for mathematical notation. Omitted unless selected.",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show the files and commands behind each concise stage description.",
)
def adopt_command(
    configure: bool,
    dry_run: bool,
    apply: bool,
    mermaid: bool | None,
    maths: bool | None,
    verbose: bool,
) -> None:
    """Add prodockit components to an existing Zensical or MkDocs document.

    Run this from the directory containing zensical.toml, zensical.yml,
    zensical.yaml, mkdocs.yml or mkdocs.yaml, with the project's virtual
    environment active. The command
    changes only local project files:
    it does not configure Git, SSH, an editor, a remote repository or Pages,
    and it never commits or pushes.

    With no mode option it reports what is present. Use --configure to choose
    the independent Mermaid and maths options, --dry-run to review the plan,
    and --apply to perform it one prominent stage at a time.
    """
    if dry_run and apply:
        raise click.UsageError("choose either --dry-run or --apply, not both")
    root = Path.cwd()
    try:
        saved = load_adopt_manifest(root)
    except AdoptError as error:
        raise click.ClickException(str(error)) from error
    options = AdoptOptions(
        mermaid=saved.mermaid if mermaid is None else mermaid,
        maths=saved.maths if maths is None else maths,
    )

    if configure:
        # Two separate questions deliberately: a document can contain one
        # without the other, and neither should pull Node into a project by
        # association with the other.
        click.echo("Choose only the optional renderers this document uses.\n")
        options = AdoptOptions(
            mermaid=click.confirm(
                "Does this document contain Mermaid diagrams?",
                default=options.mermaid,
            ),
            maths=click.confirm(
                "Does this document contain mathematical notation?",
                default=options.maths,
            ),
        )
        path = write_adopt_manifest(root, options)
        click.echo(f"\nSaved the choices to {path}.")
        click.echo("Run `prodockit adopt --dry-run` to review the installation stages.")
        return

    try:
        steps = assess_adoption(root, options)
    except AdoptError as error:
        raise click.ClickException(str(error)) from error

    click.echo(click.style("prodockit adoption — existing documentation project", bold=True))
    click.echo(f"\n  Project:  {root}")
    click.echo("  Changes:  local project files only")
    click.echo(
        "  Options:  "
        + " · ".join(
            (
                f"Mermaid {'on' if options.mermaid else 'off'}",
                f"maths {'on' if options.maths else 'off'}",
            )
        )
    )
    click.echo(f"  Choices:  {root / ADOPT_MANIFEST}")
    click.echo("  Excluded: Git, SSH, remotes, editors, commits and pushes")

    current_phase = ""
    total = len(steps)
    failed = False
    applied_stages = 0
    for number, step in enumerate(steps, start=1):
        if step.phase != current_phase:
            current_phase = step.phase
            _adopt_phase_heading(_ADOPT_PHASES.index(step.phase) + 1, step.phase)

        # Earlier stages can make the project ready to build during this same
        # --apply run. Refresh the final read-only readiness check so its
        # status describes the files now on disk rather than the initial plan.
        if apply and step.id == "verify":
            step = next(item for item in assess_adoption(root, options) if item.id == "verify")

        if not step.selected:
            click.echo(f"{number:2}  SKIP  {step.summary} — {step.detail}")
            continue
        if step.status == "wait":
            click.echo(f"{number:2}  WAIT  {step.summary} — {step.detail}")
            continue
        if step.status == "ok" and not verbose:
            click.echo(f"{number:2}  ok    {step.summary} — {step.detail}")
            continue

        _adopt_stage_heading(number, total, step.summary)
        action = "CHECK" if step.status == "ok" else "CONFIGURE"
        click.echo(f"  Action:   {action}")
        click.echo(f"  Current:  {step.detail}")
        if step.id == "dependency":
            click.echo(f"  Will do:  {step.detail}")
        elif step.id == "core":
            click.echo("  Will do:  enable the standard extensions and add shared website styles")
        elif step.id == "mermaid":
            click.echo(
                "  Will do:  scaffold and install the project-local Mermaid renderer with npm"
            )
        elif step.id == "maths":
            click.echo(
                "  Will do:  scaffold MathJax, install it with npm, and configure the website"
            )
        elif step.id == "verify":
            click.echo("  Next:     run `zensical build --clean` after this command finishes")

        if step.status == "wrong":
            failed = True
            click.echo(
                "\n  This stage must be corrected before project files can be changed.",
                err=True,
            )
            continue
        if not step.needs_work or not apply:
            continue
        if not click.confirm("\n  Apply this stage?", default=True):
            click.echo("  skipped")
            continue
        try:
            written = apply_adopt_step(root, options, step.id)
        except AdoptError as error:
            raise click.ClickException(str(error)) from error
        applied_stages += 1
        click.echo("  done")
        if verbose:
            for path in written:
                click.echo(f"    changed {path}")

    if failed:
        raise click.ClickException(
            "the assessment found a blocking stage; correct it and rerun `prodockit adopt`"
        )

    if not apply:
        outstanding = sum(step.needs_work for step in steps)
        if outstanding:
            mode = "No changes made." if not dry_run else "Dry run complete; no changes made."
            click.echo(f"\n{outstanding} selected stage(s) need work. {mode}")
            click.echo("Run `prodockit adopt --apply` to apply them.")
        else:
            click.echo("\nAll selected prodockit components are configured.")
        return

    if applied_stages == 0:
        if any(step.needs_work for step in steps):
            click.echo("\nNo changes were applied.")
            click.echo("Rerun `prodockit adopt --apply` when you are ready to apply them.")
        else:
            click.echo("\nAll selected prodockit components are already configured.")
            click.echo("No changes made.")
        return

    click.echo("\nAdoption stages finished.")
    click.echo("Run `zensical build --clean`, then review the local changes with `git diff`.")
    click.echo("Nothing has been committed or pushed.")


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
        "prodockit, markdown, pymdown-extensions and pandoc - the build inputs whose "
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
        "declared inconsistently across files, or any declared shared "
        "file differs from this prodockit release, without writing."
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

    shared_states: list[Any] = []
    if check:
        from prodockit.shared_files import SharedFileError, inspect

        try:
            shared_states = list(inspect(root))
        except SharedFileError as error:
            click.echo(f"Error: {error}", err=True)
            raise click.exceptions.Exit(1) from error
        if shared_states:
            _shared_file_report(shared_states)

    if not any_sites and not shared_states:
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
        shared_problems = [state for state in shared_states if state.status != "current"]
        if problems or shared_problems:
            click.echo("")
            for problem in problems:
                click.echo(f"Drift: {problem}", err=True)
            for state in shared_problems:
                click.echo(
                    f"Drift: {state.file.target} is {state.status}",
                    err=True,
                )
            if shared_problems:
                click.echo(
                    "Run `prodockit shared-files --apply`, review the changes, and commit them."
                )
            raise click.exceptions.Exit(1)
        if shared_states:
            click.echo("\nEvery managed package and shared file is current and consistent.")
        else:
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
            new_spec = (
                version
                if site.kind == "version-file"
                else f"{site.name_as_written or site.package}{site.extras}{site.op}{version}"
            )
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


#: Short names for the commands typed most, and typed repeatedly - while
#: a machine is being brought up, or a submission checked.
#:
#: A table rather than a line each, so the rule is one thing to read and
#: one thing to test. Two aliases did not need it; a third would have
#: meant three places to keep in step, which is how a list starts
#: disagreeing with itself (prodockit-extensions#366).
#:
#: The long names all stay. They are what the User Guide, the changelog
#: and anything anyone has scripted use.
def _wrong_directory(here: pathlib.Path) -> str:
    """Why this is the wrong place, and where to go instead.

    Written for the terminal it will actually be run in. VS Code opens
    its integrated terminal at the workspace root, and a workspace is
    frequently the folder *holding* the projects rather than one of them -
    so "not a git repository" on its own would be true, unhelpful, and
    exactly the case a reader hits first.
    """

    def is_repo(path: pathlib.Path) -> bool:
        # A directory nobody can read is not a repository as far as this
        # is concerned. `/tmp` holds mounted images whose entries raise
        # on stat, and crashing while explaining a wrong directory is a
        # poor way to explain anything.
        try:
            return (path / ".git").exists()
        except OSError:
            return False

    inside = next((p for p in here.parents if is_repo(p)), None)
    if inside is not None:
        return (
            f"{here} is inside {inside.name}, but not at its top. "
            f"Run this from the project root: cd {inside}"
        )
    try:
        children = sorted(here.iterdir())
    except OSError:
        children = []
    projects = sorted(child.name for child in children if child.is_dir() and is_repo(child))
    if projects:
        listed = ", ".join(projects[:4]) + (", ..." if len(projects) > 4 else "")
        return (
            f"{here} holds projects rather than being one ({listed}). "
            "Open a terminal in the project you want brought into step, "
            "or cd into it."
        )
    return (
        f"{here} is not a git repository. Run this from the top of the project "
        "you want brought into step."
    )


def _run_template_sync(
    do_apply: bool,
    verbose: bool,
    push: bool,
    force: tuple[str, ...],
    github: str | None,
    surrey: str | None,
    template_path: str | None = None,
) -> None:
    """Drives the ten stages, and prints what each one found.

    Separate from the click function so the whole run is reachable from a
    test without going through the command line, and so the ordering the
    stages depend on lives somewhere it can be read in one piece.
    """
    import subprocess
    from collections.abc import Iterable

    from prodockit.template_sync import (
        MANIFEST_FILE,
        STAMP_FILE,
        TemplateSyncError,
        append_ignores,
        append_log,
        apply_config_changes,
        apply_file_actions,
        apply_seeds,
        baseline_report,
        blocking_changes,
        branch_name,
        classification_report,
        config_changes,
        default_branch,
        derive_baseline,
        edited_managed_stylesheets,
        git_reader,
        git_runner,
        ignore_the_log,
        latest_prodockit_version,
        leftovers,
        load_manifest,
        missing_ignores,
        missing_seeds,
        now,
        pending_writes,
        plan_template_files,
        prodockit_requirement,
        prodockit_upgrade_required,
        publish,
        publish_blockers,
        read_config,
        read_stamp,
        resolve_template,
        stage_changes,
        start_branch,
        update_report,
        write_stamp,
        written_report,
    )

    project = pathlib.Path.cwd()
    # Run from the project, and only from its root. A subdirectory would
    # half-work: git resolves upwards so the branch and the staging would
    # land correctly, while every path this writes is relative to here and
    # would be created in the wrong place. Failing outright is the only
    # honest answer to being in the wrong directory.
    if not (project / ".git").exists():
        raise TemplateSyncError(_wrong_directory(project))
    if push and not do_apply:
        raise TemplateSyncError(
            "--push sends an applied update to GitHub or GitLab, so use it with "
            "--apply: prodockit template-sync --apply --push"
        )
    git = git_runner(project)

    started = now()
    logged: list[str] = []

    def say(text: str = "") -> None:
        """Prints, and keeps the line for the log."""
        click.echo(text)
        logged.append(text)

    def say_detail(text: str = "") -> None:
        """Keep diagnostic detail in the log; show it with --verbose."""
        if verbose:
            click.echo(text)
        logged.append(text)

    def say_report(
        render: Callable[..., Iterable[str]], *args: Any, details_only: bool = False
    ) -> None:
        """A block the terminal may want in summary and the log always in full.

        Rendered twice rather than once: the reports are pure functions
        over data already computed, and a log that only holds what the
        terminal was asked for is no use for diagnosing the run that did
        not ask for --verbose.
        """
        if verbose or not details_only:
            for line in render(*args, verbose=verbose):
                click.echo(f"  {line}")
        logged.extend(f"  {line}" for line in render(*args, verbose=True))

    try:
        say("Checking this project for template updates...")
        say_detail()

        # 1. Which template this project tracks.
        if template_path:
            # Named outright, so nothing is derived and nothing is fetched.
            template = pathlib.Path(template_path).resolve()
            say_detail(f"Template source: {template} (--template-path)")
        else:
            remote = subprocess.run(
                ["git", "-C", str(project), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            ).stdout.strip()
            template_remote = resolve_template(remote or None, github=github, surrey=surrey)
            say_detail(f"Template source: {template_remote}")
            template, how = _template_checkout(project, template_remote)
            say_detail(f"Template checkout: {template} ({how})")

        say_detail()

        # 2. What the manifest says.
        manifest_path = template / MANIFEST_FILE
        if not manifest_path.exists():
            raise TemplateSyncError(
                f"{template} has no {MANIFEST_FILE} - it is not a prodockit template, "
                "or predates the manifest"
            )
        manifest = load_manifest(manifest_path.read_text(encoding="utf-8"))
        requirements_path = template / "requirements.txt"
        package_requirement = (
            prodockit_requirement(requirements_path.read_text(encoding="utf-8"))
            if requirements_path.exists()
            else None
        )
        latest_package = latest_prodockit_version()
        package_version = (
            latest_package
            if (latest_package and prodockit_upgrade_required(__version__, latest_package))
            else None
        )
        package_reason = "latest available"
        if (
            package_requirement
            and prodockit_upgrade_required(__version__, package_requirement.version)
            and (
                package_version is None
                or prodockit_upgrade_required(package_version, package_requirement.version)
            )
        ):
            package_version = package_requirement.version
            package_reason = "template requires"
        package_upgrade = package_version is not None
        package_extras = ""
        if package_requirement and "[" in package_requirement.specifier:
            package_extras = package_requirement.specifier.split("]", 1)[0] + "]"
        package_specifier = (
            f"prodockit{package_extras}>={package_version}" if package_version else None
        )
        say_detail(
            "Prodockit release check: "
            + (f"PyPI reports {latest_package}" if latest_package else "PyPI could not be checked")
        )
        files = subprocess.run(
            ["git", "-C", str(template), "ls-files"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ).stdout.split()
        say_report(classification_report, manifest, files, details_only=True)
        say_detail()

        # 3. Where this project came from.
        stamp = read_stamp(project)
        owned = [f for f in files if manifest.owner(f) == "template"]

        def blob_of(path: pathlib.Path) -> str | None:
            if not path.exists():
                return None
            return subprocess.run(
                ["git", "-C", str(template), "hash-object", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            ).stdout.strip()

        versions = subprocess.run(
            ["git", "-C", str(template), "rev-list", "--first-parent", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ).stdout.split()
        trees: dict[str, dict[str, str]] = {}

        def blob_at(version: str, path: str) -> str | None:
            if version not in trees:
                listing = subprocess.run(
                    ["git", "-C", str(template), "ls-tree", "-r", version],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                ).stdout.splitlines()
                trees[version] = {
                    name: meta.split()[2]
                    for meta, name in (line.split("\t", 1) for line in listing)
                }
            return trees[version].get(path)

        baseline = derive_baseline(
            owned,
            lambda p: blob_of(project / manifest.rename(p)),
            [stamp] if stamp else versions,
            blob_at,
        )
        say_detail(
            "Comparison point: "
            + ("recorded by an earlier sync" if stamp else "worked out from file contents")
        )
        say_report(baseline_report, baseline, details_only=True)
        say_detail()

        # 4. Whether it is safe to write.
        dirty = [
            line[3:]
            for line in subprocess.run(
                ["git", "-C", str(project), "status", "--porcelain"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            ).stdout.splitlines()
        ]
        blocked = blocking_changes(manifest, dirty)
        if blocked:
            raise TemplateSyncError(
                "these files have changes that have not been committed, and the "
                f"template may need to update them: {', '.join(blocked)}. Commit or "
                "undo those changes, then run template-sync again; nothing has been "
                "changed by this run"
            )

        # 5 and 6. What would change.
        plan = plan_template_files(
            manifest,
            files,
            lambda p: blob_of(project / manifest.rename(p)),
            lambda p: blob_at(versions[0], p) if versions else None,
            baseline,
            force=force,
        )

        # 7 to 9. Work out every change before reporting, including shared
        # settings and starter files. A preview that reports only ordinary
        # template files is not a preview of what --apply will do.
        ignores_path = project / ".gitignore"
        ignores = missing_ignores(
            manifest,
            ignores_path.read_text(encoding="utf-8").splitlines() if ignores_path.exists() else [],
        )
        stale = leftovers(
            manifest,
            subprocess.run(
                ["git", "-C", str(project), "ls-files"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            ).stdout.split(),
        )

        config_path = project / "zensical.toml"
        template_config: dict[str, Any] = {}
        added: list[str] = []
        updated: list[str] = []
        if config_path.exists():
            template_config = read_config((template / "zensical.toml").read_text(encoding="utf-8"))
            project_config = read_config(config_path.read_text(encoding="utf-8"))
            added, updated = config_changes(manifest, template_config, project_config)

        pending = pending_writes(plan, project, lambda p: (template / p).read_bytes())
        seeds = missing_seeds(manifest, lambda name: (project / name).exists())
        # The stamp counts as work of its own. A template release that
        # only reclassifies files leaves every file identical, so nothing
        # else is pending - but the project now matches a newer version
        # than the stamp records, and leaving it stale makes the *next*
        # run derive its baseline from the wrong place and report
        # unedited files as edited.
        wanted_stamp = versions[0] if versions else (baseline.version or "")
        stamp_is_stale = bool(baseline.version) and read_stamp(project) != wanted_stamp
        work_needed = bool(pending or seeds or added or updated or ignores or stamp_is_stale)

        # Normal mode answers the author's questions and stops. Diagnostic
        # classification, baseline and every routine filename remain in
        # --verbose and in the always-detailed log.
        decisions = [action for action in plan if action.action in {"keep", "forced"}]
        summary_actions = list(pending)
        summary_actions.extend(action for action in decisions if action not in summary_actions)

        say("Changes available:" if work_needed or package_upgrade else "Result:")
        terminal_actions = plan if verbose else summary_actions
        for line in update_report(terminal_actions, verbose=verbose):
            say(f"  {line}")
        if not verbose:
            logged.extend(f"  {line}" for line in update_report(plan, verbose=True))

        if seeds:
            say(f"  Starter files to add: {len(seeds)}")
            for path in seeds:
                say_detail(f"      {manifest.rename(path)}")
        if added or updated:
            say(
                "  Project settings to update: "
                f"{len(added) + len(updated)} "
                f"({len(added)} new, {len(updated)} changed)"
            )
            for key in added:
                say_detail(f"      add {key}")
            for key in updated:
                say_detail(f"      update {key}")
        if ignores:
            say(f"  Other project setup updates: {len(ignores)}")
            for entry in ignores:
                say_detail(f"      {entry}")
        if stamp_is_stale and not (pending or seeds or added or updated or ignores):
            say("  The saved template version needs refreshing; no project content will change.")
        if package_upgrade and package_specifier and package_version:
            say("  Prodockit needs upgrading:")
            say(f"      installed: {__version__}")
            say(f"      {package_reason}: {package_version}")
            say("      in the activated project environment, run:")
            say(f'        python -m pip install --upgrade "{package_specifier}"')

        kept = [action for action in plan if action.action == "keep"]
        forced = [action for action in plan if action.action == "forced"]
        stylesheet_edits = edited_managed_stylesheets(plan)
        if stylesheet_edits:
            say()
            say("Warning - managed stylesheet changes found:")
            for path in stylesheet_edits:
                say(f"    {path}")
            say("  pdk.css and pdk-pdf.css are supplied and updated by prodockit.")
            say("  Move website changes to extra.css and PDF-only changes to print.css.")
            say("  Then use --force FILE-PATH if you want the managed copy restored.")
        if kept:
            say()
            say("Your edited files are protected:")
            say("  Without --force, your versions stay unchanged.")
            say("  The newer template copies will be saved beside them as .new files.")
            say(
                "  For each file you want to replace, add `--force FILE-PATH`, "
                "using the file path shown above."
            )
        if forced:
            say()
            say("You used --force:")
            say("  The named files will be replaced by the template versions.")
            say("  Remove --force to keep your versions instead.")

        if stale:
            say_detail(f"Older template files left alone: {len(stale)}")
            for path in stale:
                say_detail(f"      {path}")

        def explain_package_only_update() -> None:
            """Explain the non-Git work that a package-only update needs."""
            say("No template files need changing, so there is nothing to commit or push.")
            say("After upgrading prodockit, rebuild the Pages or documentation pipeline.")
            say(
                "The rebuild is still needed: it republishes the website and PDF using "
                "the newer package even though no template file changed."
            )

        say()
        if not do_apply:
            if work_needed:
                say("Preview only - no template changes have been made.")
                say("Add `--apply` to the command you just ran to make these changes.")
            elif package_upgrade:
                explain_package_only_update()
            elif kept:
                say("No safe changes need applying; the files you edited remain unchanged.")
            else:
                say("Your project is already up to date with the template.")
            return

        if not work_needed:
            # Nothing to do, so no branch. A run that branched anyway left
            # an empty branch behind, which then blocked the next run - the
            # ordinary way to use this is to run it repeatedly, and most of
            # those runs find nothing.
            if package_upgrade:
                explain_package_only_update()
            else:
                say("Your project is already up to date with the template. Nothing was changed.")
            return

        # 10, first: the branch, before anything is written.
        name = branch_name(baseline.version or "unknown")
        if not start_branch(git, name):
            raise TemplateSyncError(
                f"could not create or open the separate update branch {name}. "
                "Nothing has been changed"
            )
        say(f"Applying the update on a separate branch: {name}")

        written = apply_file_actions(plan, project, lambda p: (template / p).read_bytes())
        written += apply_seeds(manifest, project, lambda p: (template / p).read_bytes())
        # Everything else a run writes: the shared files it merges, and the
        # stamp. Staged alongside, or a reader is handed a half-staged change
        # and has to work out for themselves which parts belong to it.
        also_written: list[str] = []

        if config_path.exists() and (added or updated):
            config_path.write_text(
                apply_config_changes(
                    config_path.read_text(encoding="utf-8"), template_config, added, updated
                ),
                encoding="utf-8",
            )
            say_detail(f"zensical.toml: {len(added)} settings added, {len(updated)} updated")
            also_written.append("zensical.toml")

        if ignores:
            ignores_path.write_text(
                append_ignores(
                    ignores_path.read_text(encoding="utf-8") if ignores_path.exists() else "",
                    ignores,
                ),
                encoding="utf-8",
            )
            say_detail(f".gitignore: {len(ignores)} entries added")
            also_written.append(".gitignore")

        say()
        say("Changes made:")
        say_report(written_report, written)

        # 10, last: the stamp describes a state that now exists.
        if baseline.version:
            write_stamp(project, wanted_stamp)
            also_written.append(STAMP_FILE)
        stage_changes(git, [w.path for w in written] + also_written)
        say()
        if not push:
            say("The changes are ready for you to review.")
            say("Nothing has been committed or sent to GitHub or GitLab.")
            say_detail("Git detail: the changes are staged but not committed.")
            return

        # 11: onto the branch the host actually builds from. A sync sitting
        # on an update branch publishes nothing - a pipeline guarded on the
        # default branch never sees it - so a reader who wanted their site
        # rebuilt is not finished until this happens.
        read = git_reader(project)
        target = default_branch(read)
        if target is None:
            raise TemplateSyncError(
                "cannot find the main branch to update. The changes remain ready on "
                f"{name}; nothing has been sent to GitHub or GitLab"
            )
        blockers = publish_blockers(read, target, name)
        if blockers:
            say("The changes are ready, but cannot be sent directly to the main project:")
            for problem in blockers:
                say(f"  - {problem}")
            say("Nothing has been committed or sent to GitHub or GitLab.")
            return

        version = wanted_stamp[:9] if wanted_stamp else "the template"
        message = f"Sync with the template at {version}"
        say("Ready to update the main project directly:")
        say(f"  Save this update as one commit ({len(written) + len(also_written)} files).")
        say(f"  Add it to {target}.")
        say(f"  Send {target} to GitHub or GitLab, which starts the site build.")
        say("  This does not create a pull request or merge request.")
        say()
        if not click.confirm("Update the main project now?", default=False):
            say("Stopped safely. Nothing was committed or sent to GitHub or GitLab.")
            return

        publish(git, name, target, message)
        say()
        say(f"Updated {target} and sent it to GitHub or GitLab.")
        say("The automated site build can now start.")
    finally:
        # Written however the run ended. A run that raised is the one
        # most worth reading afterwards, so the log is not conditional
        # on reaching the end.
        log_path = append_log(project, logged, started)
        newly_ignored = ignore_the_log(project)
        note = "  (added to .gitignore)" if newly_ignored else ""
        click.echo(f"log       {log_path.name}{note}")


def _template_checkout(project: pathlib.Path, remote: str) -> tuple[pathlib.Path, str]:
    """Where the template can be read from, and how it got there.

    A sibling checkout wins if there is one: that is how the three
    repositories are laid out during development, and a maintainer
    working across them means the copy beside the project. Nobody else
    has one, so everyone else gets the remote fetched into a cache.

    The whole history is cloned rather than a shallow copy. Deriving a
    baseline by content walks the template's versions and reads the tree
    at each of them, so a shallow clone would answer "no version matches"
    for any project more than a commit or two behind - which is every
    project this is for.
    """
    from prodockit.template_sync import (
        MANIFEST_FILE,
        cache_path_for,
        cache_root,
        ensure_template,
        git_runner,
    )

    name = remote.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    skipped = None
    for candidate in (project.parent / name, project.parent.parent / "GitHub" / name):
        if not (candidate / ".git").exists():
            continue
        if (candidate / MANIFEST_FILE).exists():
            return candidate, "beside this project"
        # A checkout with no manifest cannot answer anything this asks, so
        # it is passed over rather than preferred into a dead end. An old
        # clone left beside a project - one taken before the manifest
        # existed - stopped the command outright, with a perfectly good
        # copy a fetch away.
        skipped = candidate
        break

    path = cache_path_for(remote, cache_root())
    what = ensure_template(remote, path, git_runner(project))
    how = {
        "cloned": "fetched just now",
        "updated": "fetched, up to date",
        "offline": "cached copy - could not reach the host, so this may be behind",
    }[what]
    if skipped is not None:
        how += f"; passed over {skipped}, which predates the manifest"
    return path, how


@main.command("template-sync")
@click.option(
    "--apply",
    "do_apply",
    is_flag=True,
    help="Make the reported changes on a separate branch. Without --apply, "
    "template-sync only previews them.",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show the template source, comparison details, and individual file paths.",
)
@click.option(
    "--push",
    is_flag=True,
    help="After asking, commit the update and send it directly to main so the site "
    "rebuilds. Use only if your project does not require a PR/MR. Needs --apply.",
)
@click.option(
    "--force",
    "force",
    multiple=True,
    metavar="FILE-PATH",
    help=(
        "Replace one edited file with the template's version. Use the path shown "
        "in the report. Repeat --force FILE-PATH for another file."
    ),
)
@click.option(
    "--github",
    "github",
    is_flag=False,
    flag_value="",
    default=None,
    metavar="[OWNER/REPO]",
    help="Take the template from github.com - bare for the usual one.",
)
@click.option(
    "--surrey",
    "surrey",
    is_flag=False,
    flag_value="",
    default=None,
    metavar="[GROUP/REPO]",
    help="Take the template from gitlab.surrey.ac.uk - bare for the usual one.",
)
@click.option(
    "--template-path",
    "template_path",
    default=None,
    metavar="PATH",
    type=click.Path(exists=True, file_okay=False),
    help=(
        "Read the template from a checkout already on this machine, rather "
        "than working out where it lives. For developing this command, and "
        "for a machine that cannot reach the template's host."
    ),
)
def template_sync(
    do_apply: bool,
    verbose: bool,
    push: bool,
    force: tuple[str, ...],
    github: str | None,
    surrey: str | None,
    template_path: str | None,
) -> None:
    """Check for and apply updates from the project's template.

    Your writing, figures, and bibliography are left alone. Without --apply,
    this only previews the changes. With --apply, it makes the changes on a
    separate branch for you to review.

    Use --verbose for technical details. Every run also keeps those details in
    .prodockit-template.log for troubleshooting.
    """
    from prodockit.template_sync import TemplateSyncError

    try:
        _run_template_sync(do_apply, verbose, push, force, github, surrey, template_path)
    except TemplateSyncError as error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)


COMMAND_ALIASES = {
    "boot": "bootstrap",
    "source": "source-bundle",
}

# Registered rather than wrapped: one command object under two names, so
# they cannot take different options or drift in their help.
for _alias, _target in COMMAND_ALIASES.items():
    main.add_command(main.commands[_target], name=_alias)
