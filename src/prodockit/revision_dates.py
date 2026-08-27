# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Build a Zensical site with revision metadata, without editing its source.

Git history is authoritative when it exists.  A project outside Git, or a
Markdown file with no history of its own, uses that file's modification time
for ``revision_date``.  The source tree is copied to a temporary directory and
only those copies receive generated front matter before Zensical's documented
CLI builds the real ``site_dir``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped, unused-ignore]

from prodockit.project_config import CONFIG_OVERRIDE_ENV, ProjectConfig, load_project_config


class RevisionDateError(RuntimeError):
    """Revision metadata or the documented Zensical build failed."""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


@dataclass(frozen=True)
class PageRevision:
    """How one staged Markdown page obtained its revision metadata."""

    source_path: str
    updated_source: str
    created_source: str | None = None


@dataclass(frozen=True)
class RevisionBuildResult:
    """Summary and captured output from a completed site build."""

    site_dir: Path
    pages: tuple[PageRevision, ...]
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ResolvedRevisionDates:
    """Automatic dates resolved for one Markdown source file."""

    updated: str
    updated_source: str
    created: str | None = None


@dataclass(frozen=True)
class _GitHistory:
    executable: str
    repository: Path

    def dates(self, source: Path, *, include_creation: bool) -> tuple[str | None, str | None]:
        """Return the newest and oldest author dates for one source file."""
        try:
            relative = source.resolve().relative_to(self.repository.resolve())
        except ValueError:
            return None, None
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
            return None, None
        updated = _date_part(timestamps[0], source)
        created = _date_part(timestamps[-1], source) if include_creation else None
        return updated, created


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
    include_creation: bool = False,
) -> dict[Path, ResolvedRevisionDates]:
    """Resolve automatic revision dates once for a collection of pages."""
    history = _git_history(root)
    resolved: dict[Path, ResolvedRevisionDates] = {}
    for source in sources:
        git_updated, git_created = (
            history.dates(source, include_creation=include_creation)
            if history is not None
            else (None, None)
        )
        if git_updated is not None:
            resolved[source] = ResolvedRevisionDates(git_updated, "git", git_created)
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


def _inject_front_matter(source: Path, destination: Path, values: dict[str, str]) -> None:
    """Add generated values to a staged page, retaining all author metadata."""
    if not values:
        return
    # Decode bytes directly rather than using TextIO's universal-newline
    # translation: a CRLF authoring tree should remain CRLF in staging too.
    text = destination.read_bytes().decode("utf-8")
    _metadata, closing = _front_matter(text, source)
    newline = "\r\n" if "\r\n" in text else "\n"
    rendered = "".join(f'{key}: {json.dumps(value)}{newline}' for key, value in values.items())
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    content = text.removeprefix("\ufeff")
    if closing is None:
        updated = f"---{newline}{rendered}---{newline}{newline}{content}"
    else:
        lines = content.splitlines(keepends=True)
        lines.insert(closing, rendered)
        updated = "".join(lines)
    destination.write_text(f"{bom}{updated}", encoding="utf-8", newline="")


def _toml_with_docs_dir(source: str, docs_dir: str, config_path: Path) -> str:
    lines = source.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in source else "\n"
    project_start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^\s*\[project\]\s*(?:#.*)?$", line.rstrip("\r\n"))
        ),
        None,
    )
    if project_start is None:
        raise RevisionDateError(f"{config_path} has no [project] table")
    project_end = next(
        (
            index
            for index, line in enumerate(lines[project_start + 1 :], start=project_start + 1)
            if re.match(r"^\s*\[.+\]\s*(?:#.*)?$", line.rstrip("\r\n"))
        ),
        len(lines),
    )
    replacement = f"docs_dir = {json.dumps(docs_dir)}{newline}"
    for index in range(project_start + 1, project_end):
        if re.match(r"^\s*docs_dir\s*=", lines[index]):
            lines[index] = replacement
            break
    else:
        lines.insert(project_start + 1, replacement)
    return "".join(lines)


def _yaml_with_docs_dir(source: str, docs_dir: str) -> str:
    lines = source.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in source else "\n"
    replacement = f"docs_dir: {json.dumps(docs_dir)}{newline}"
    for index, line in enumerate(lines):
        if re.match(r"^docs_dir\s*:", line):
            lines[index] = replacement
            break
    else:
        insert_at = 1 if lines and lines[0].strip() == "---" else 0
        lines.insert(insert_at, replacement)
    return "".join(lines)


def _staged_config_source(config: ProjectConfig, staged_docs: Path) -> str:
    source = config.path.read_bytes().decode("utf-8")
    # Zensical requires docs_dir below the configuration root and its current
    # path normalizer expects the configured value to be relative, even when
    # an absolute path names the same child directory.
    configured_docs = staged_docs.relative_to(config.root).as_posix()
    if config.path.suffix.lower() == ".toml":
        return _toml_with_docs_dir(source, configured_docs, config.path)
    return _yaml_with_docs_dir(source, configured_docs)


def _zensical_cli() -> str:
    scripts = Path(sys.executable).parent
    names = ("zensical.exe", "zensical") if sys.platform == "win32" else ("zensical",)
    for name in names:
        candidate = scripts / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which("zensical") or "zensical"


def _build_staged_site(
    config: ProjectConfig,
    staged_docs: Path,
    *,
    strict: bool,
) -> tuple[str, str]:
    suffix = config.path.suffix
    temporary_config: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=".prodockit-revision-dates-",
            suffix=suffix,
            dir=config.root,
            delete=False,
        ) as handle:
            temporary_config = Path(handle.name)
            handle.write(_staged_config_source(config, staged_docs))
        command = [
            _zensical_cli(),
            "build",
            "--clean",
            "--config-file",
            str(temporary_config),
        ]
        if strict:
            command.append("--strict")
        environment = os.environ.copy()
        environment[CONFIG_OVERRIDE_ENV] = str(temporary_config)
        try:
            result = subprocess.run(
                command,
                cwd=config.root,
                env=environment,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            raise RevisionDateError(f"could not run zensical build: {error}") from error
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise RevisionDateError(
                f"zensical build exited with status {result.returncode}", stderr=detail
            )
        return result.stdout, result.stderr
    finally:
        if temporary_config is not None:
            temporary_config.unlink(missing_ok=True)


def build_site_with_revision_dates(
    config_path: str | Path = "zensical.toml",
    *,
    include_creation: bool = False,
    strict: bool = False,
) -> RevisionBuildResult:
    """Build the configured site from staged Markdown with generated dates."""
    config = load_project_config(config_path)
    if not config.docs_dir.is_dir():
        raise RevisionDateError(f"documentation directory not found: {config.docs_dir}")
    pages: list[PageRevision] = []
    sources = sorted(config.docs_dir.rglob("*.md"))
    automatic_dates = resolve_revision_dates(
        config.root,
        sources,
        include_creation=include_creation,
    )

    # Zensical requires docs_dir to remain inside the project root.  The
    # hidden staging tree is transient and the context manager removes it on
    # both success and failure, so the checkout's final status is unchanged.
    with tempfile.TemporaryDirectory(
        prefix=".prodockit-revision-dates-", dir=config.root
    ) as temporary:
        staged_docs = Path(temporary) / "docs"
        # Follow symlinks into ordinary copies.  Preserving a Markdown
        # symlink would let front-matter injection follow it back into an
        # author-owned source outside the staging directory.
        shutil.copytree(config.docs_dir, staged_docs, symlinks=False)

        for source in sources:
            relative = source.relative_to(config.docs_dir)
            destination = staged_docs / relative
            text = source.read_bytes().decode("utf-8")
            metadata, _closing = _front_matter(text, source)
            updated_is_manual = any(
                key in metadata for key in ("git_revision_date_localized", "revision_date")
            )
            created_is_manual = "git_creation_date_localized" in metadata
            needs_updated = not updated_is_manual
            needs_created = include_creation and not created_is_manual
            updated: str | None = None
            created: str | None = None
            updated_source = "manual" if updated_is_manual else ""
            created_source = "manual" if include_creation and created_is_manual else None

            if needs_updated or needs_created:
                automatic = automatic_dates[source]
                if needs_updated:
                    updated = automatic.updated
                    updated_source = automatic.updated_source
                if needs_created and automatic.created is not None:
                    created = automatic.created
                    created_source = "git"

            values: dict[str, str] = {}
            if updated is not None:
                values["revision_date"] = updated
            if created is not None:
                values["git_creation_date_localized"] = created
            _inject_front_matter(source, destination, values)
            pages.append(PageRevision(relative.as_posix(), updated_source, created_source))

        stdout, stderr = _build_staged_site(config, staged_docs, strict=strict)

    return RevisionBuildResult(config.site_dir, tuple(pages), stdout, stderr)


__all__ = [
    "CONFIG_OVERRIDE_ENV",
    "PageRevision",
    "ResolvedRevisionDates",
    "RevisionBuildResult",
    "RevisionDateError",
    "build_site_with_revision_dates",
    "resolve_revision_dates",
]
