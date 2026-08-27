# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Add revision metadata to a completed Zensical site.

Git history is authoritative when it exists.  A project outside Git, or a
Markdown file with no history of its own, uses that file's modification time
for its update date.  The postprocessor changes only generated HTML in the
configured ``site_dir``; it does not edit source files or invoke Zensical.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped, unused-ignore]

from prodockit.project_config import ProjectConfig, load_project_config


class RevisionDateError(RuntimeError):
    """Revision metadata or the documented Zensical build failed."""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


@dataclass(frozen=True)
class PageRevision:
    """How one staged Markdown page obtained its revision metadata."""

    source_path: str
    updated_date: str
    updated_source: str


@dataclass(frozen=True)
class RevisionUpdateResult:
    """Summary of revision facts added to a completed site."""

    site_dir: Path
    pages: tuple[PageRevision, ...]


@dataclass(frozen=True)
class ResolvedRevisionDates:
    """Automatic dates resolved for one Markdown source file."""

    updated: str
    updated_source: str


@dataclass(frozen=True)
class _GitHistory:
    executable: str
    repository: Path

    def updated_date(self, source: Path) -> str | None:
        """Return the newest author date for one source file."""
        try:
            relative = source.resolve().relative_to(self.repository.resolve())
        except ValueError:
            return None
        command = [
            self.executable,
            "-C",
            str(self.repository),
            "--literal-pathspecs",
            "log",
            "--follow",
            "--format=%aI",
            "--",
            relative.as_posix(),
        ]
        result = _run(command)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else ""
            raise RevisionDateError(
                f"git could not read the history of {relative.as_posix()}{suffix}"
            )
        timestamps = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not timestamps:
            return None
        return _date_part(timestamps[0], source)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise RevisionDateError(f"could not run {command[0]}: {error}") from error


def _git_metadata_above(root: Path) -> bool:
    """Detect a checkout even when the Git executable is unavailable."""
    return any((candidate / ".git").exists() for candidate in (root, *root.parents))


def _git_history(root: Path) -> _GitHistory | None:
    """Locate a readable, complete repository or identify a non-Git project."""
    executable = shutil.which("git")
    if executable is None:
        if _git_metadata_above(root):
            raise RevisionDateError(
                "this project contains Git repository metadata, but git is not installed or "
                "not on PATH; install Git before building revision dates"
            )
        return None

    located = _run([executable, "-C", str(root), "rev-parse", "--show-toplevel"])
    if located.returncode:
        detail = (located.stderr or located.stdout).strip()
        if "not a git repository" in detail.lower():
            return None
        raise RevisionDateError(f"git could not locate the repository: {detail or 'unknown error'}")
    repository = Path(located.stdout.strip()).resolve()

    shallow = _run(
        [executable, "-C", str(repository), "rev-parse", "--is-shallow-repository"]
    )
    if shallow.returncode:
        detail = (shallow.stderr or shallow.stdout).strip()
        raise RevisionDateError(
            f"git could not check whether the repository history is complete: "
            f"{detail or 'unknown error'}"
        )
    if shallow.stdout.strip().lower() == "true":
        raise RevisionDateError(
            "revision dates need complete Git history, but this is a shallow checkout; "
            "use fetch-depth: 0 in GitHub Actions or GIT_DEPTH: \"0\" in GitLab CI, "
            "then fetch the full history before rebuilding"
        )
    head = _run([executable, "-C", str(repository), "rev-parse", "--verify", "HEAD"])
    if head.returncode:
        # An initialized repository with an unborn branch is a legitimate
        # no-history project. Its pages have only filesystem dates, just like
        # files outside Git; there is no shallow boundary to misrepresent.
        revisions = _run([executable, "-C", str(repository), "rev-list", "--all", "--count"])
        if revisions.returncode == 0 and revisions.stdout.strip() == "0":
            return None
        detail = (head.stderr or head.stdout).strip()
        raise RevisionDateError(
            f"git could not read the current revision: {detail or 'unknown error'}"
        )
    return _GitHistory(executable, repository)


def _date_part(timestamp: str, source: Path) -> str:
    try:
        return datetime.fromisoformat(timestamp).date().isoformat()
    except ValueError as error:
        raise RevisionDateError(
            f"git returned an invalid author timestamp for {source}: {timestamp!r}"
        ) from error


def _mtime_date(source: Path) -> str:
    try:
        modified = source.stat().st_mtime
    except OSError as error:
        raise RevisionDateError(
            f"could not read the modification time of {source}: {error}"
        ) from error
    return datetime.fromtimestamp(modified, tz=timezone.utc).date().isoformat()


def resolve_revision_dates(
    root: Path,
    sources: list[Path],
    *,
    use_modification_dates: bool = False,
) -> dict[Path, ResolvedRevisionDates]:
    """Resolve automatic revision dates once for a collection of pages."""
    history = None if use_modification_dates else _git_history(root)
    resolved: dict[Path, ResolvedRevisionDates] = {}
    for source in sources:
        git_updated = history.updated_date(source) if history is not None else None
        if git_updated is not None:
            resolved[source] = ResolvedRevisionDates(git_updated, "git")
        else:
            resolved[source] = ResolvedRevisionDates(_mtime_date(source), "mtime")
    return resolved


def _front_matter(text: str, source: Path) -> tuple[dict[str, Any], int | None]:
    """Return page metadata and the closing fence's line index."""
    content = text.removeprefix("\ufeff")
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, None
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing is None:
        raise RevisionDateError(f"unterminated YAML front matter in {source}")
    try:
        value = yaml.safe_load("".join(lines[1:closing])) or {}
    except yaml.YAMLError as error:
        raise RevisionDateError(f"invalid YAML front matter in {source}: {error}") from error
    if not isinstance(value, dict):
        raise RevisionDateError(f"YAML front matter in {source} must be a mapping")
    return value, closing


_MARKER_START = "<!-- prodockit:update-date:start -->"
_MARKER_END = "<!-- prodockit:update-date:end -->"
_ARTICLE_END = "</article>"
_EXISTING_UPDATE_TITLES = ('title="Last update"', 'title="Updated"')
_CLOCK_ICON_PATH = (
    "M21 13.1c-.1 0-.3.1-.4.2l-1 1 2.1 2.1 1-1c.2-.2.2-.6 0-.8l-1.3-1.3c-.1-.1-.2-.2-.4-.2"
    "m-1.9 1.8-6.1 6V23h2.1l6.1-6.1zM12.5 7v5.2l4 2.4-1 1L11 13V7zM11 21.9c-5.1-.5-9-4.8-9-9.9"
    "C2 6.5 6.5 2 12 2c5.3 0 9.6 4.1 10 9.3-.3-.1-.6-.2-1-.2s-.7.1-1 .2C19.6 7.2 16.2 4 12 4"
    "c-4.4 0-8 3.6-8 8 0 4.1 3.1 7.5 7.1 7.9l-.1.2z"
)


def _built_page_path(config: ProjectConfig, source: Path) -> Path:
    relative = source.relative_to(config.docs_dir)
    directory_urls = bool(config.project.get("use_directory_urls", True))
    if relative.name.lower() == "index.md":
        return config.site_dir / relative.with_suffix(".html")
    if directory_urls:
        return config.site_dir / relative.with_suffix("") / "index.html"
    return config.site_dir / relative.with_suffix(".html")


def _manual_update_date(source: Path) -> str | None:
    text = source.read_bytes().decode("utf-8")
    metadata, _closing = _front_matter(text, source)
    value = metadata.get("git_revision_date_localized") or metadata.get("revision_date")
    return str(value) if value is not None else None


def _update_fact(date: str, newline: str) -> str:
    safe_date = escape(date)
    return newline.join(
        (
            _MARKER_START,
            '<aside class="md-source-file prodockit-update-date">',
            '  <span class="md-source-file__fact">',
            '    <span class="md-icon" title="Updated">',
            '      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<path d="{_CLOCK_ICON_PATH}"/></svg>',
            "    </span>",
            f"    {safe_date}",
            "  </span>",
            "</aside>",
            _MARKER_END,
        )
    )


def _write_update_fact(output: Path, date: str) -> bool:
    try:
        text = output.read_bytes().decode("utf-8")
    except OSError as error:
        raise RevisionDateError(f"could not read built page {output}: {error}") from error
    newline = "\r\n" if "\r\n" in text else "\n"
    fact = _update_fact(date, newline)
    if _MARKER_START in text:
        start = text.index(_MARKER_START)
        try:
            end = text.index(_MARKER_END, start) + len(_MARKER_END)
        except ValueError as error:
            raise RevisionDateError(f"incomplete Prodockit update marker in {output}") from error
        updated = f"{text[:start]}{fact}{text[end:]}"
    elif any(title in text for title in _EXISTING_UPDATE_TITLES):
        return False
    else:
        end = text.rfind(_ARTICLE_END)
        if end < 0 or 'class="md-content__inner md-typeset"' not in text:
            raise RevisionDateError(
                f"could not find Zensical's content article in {output}; "
                "rebuild the site with a supported Zensical layout"
            )
        updated = f"{text[:end]}{fact}{newline}{text[end:]}"
    if updated != text:
        output.write_text(updated, encoding="utf-8", newline="")
    return True


def update_built_site_revision_dates(
    config_path: str | Path = "zensical.toml",
    *,
    use_modification_dates: bool = False,
) -> RevisionUpdateResult:
    """Add update dates to an already-built site without invoking Zensical."""
    config = load_project_config(config_path)
    if not config.docs_dir.is_dir():
        raise RevisionDateError(f"documentation directory not found: {config.docs_dir}")
    if not config.site_dir.is_dir():
        raise RevisionDateError(
            f"built site not found: {config.site_dir}; run zensical build first"
        )
    pages: list[PageRevision] = []
    sources = sorted(config.docs_dir.rglob("*.md"))
    automatic_dates = resolve_revision_dates(
        config.root,
        sources,
        use_modification_dates=use_modification_dates,
    )
    required = {page.source_path for page in config.nav_pages}
    for source in sources:
        relative = source.relative_to(config.docs_dir).as_posix()
        output = _built_page_path(config, source)
        if not output.is_file():
            if relative in required:
                raise RevisionDateError(
                    f"built page not found for {relative}: expected {output}; "
                    "run zensical build before updating dates"
                )
            continue
        manual = _manual_update_date(source)
        automatic = automatic_dates[source]
        date = manual or automatic.updated
        source_name = "manual" if manual else automatic.updated_source
        written = _write_update_fact(output, date)
        if not written and not manual:
            source_name = "existing"
        pages.append(PageRevision(relative, date, source_name))

    return RevisionUpdateResult(config.site_dir, tuple(pages))


__all__ = [
    "PageRevision",
    "ResolvedRevisionDates",
    "RevisionDateError",
    "RevisionUpdateResult",
    "resolve_revision_dates",
    "update_built_site_revision_dates",
]
