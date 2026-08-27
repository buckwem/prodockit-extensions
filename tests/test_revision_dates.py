# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

import prodockit.cli as cli_module
import prodockit.revision_dates as revision_dates
from prodockit.cli import main
from prodockit.revision_dates import (
    PageRevision,
    RevisionDateError,
    RevisionUpdateResult,
    update_built_site_revision_dates,
)

HTML = """<!doctype html>
<html><body>
<article class="md-content__inner md-typeset">
<h1>Home</h1>
</article>
</body></html>
"""


def _write_project(
    root: Path,
    *,
    config_name: str = "zensical.toml",
    directory_urls: bool = True,
) -> Path:
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text("# Home\n", encoding="utf-8")
    config = root / config_name
    if config.suffix == ".toml":
        config.write_text(
            "[project]\n"
            'site_name = "Revision test"\n'
            f"use_directory_urls = {str(directory_urls).lower()}\n"
            'nav = [{ "Home" = "index.md" }]\n',
            encoding="utf-8",
        )
    else:
        config.write_text(
            "site_name: Revision test\n"
            f"use_directory_urls: {str(directory_urls).lower()}\n"
            "nav:\n    - Home: index.md\n",
            encoding="utf-8",
        )
    return config


def _write_built_page(root: Path, relative: str = "index.html", html: str = HTML) -> Path:
    output = root / "site" / relative
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def _git(root: Path, *arguments: str, environment: dict[str, str] | None = None) -> str:
    env = os.environ.copy()
    if environment:
        env.update(environment)
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _init_git(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Revision Test")
    _git(root, "config", "user.email", "revision@example.test")


def _commit(root: Path, message: str, *, author: str, committer: str) -> None:
    _git(root, "add", "-A")
    _git(
        root,
        "commit",
        "-m",
        message,
        environment={"GIT_AUTHOR_DATE": author, "GIT_COMMITTER_DATE": committer},
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_full_git_history_updates_built_html_and_leaves_sources_unchanged(
    tmp_path: Path,
) -> None:
    config = _write_project(tmp_path)
    _init_git(tmp_path)
    _commit(
        tmp_path,
        "Create page",
        author="2024-01-02T03:04:05+02:00",
        committer="2030-01-01T00:00:00+00:00",
    )
    page = tmp_path / "docs" / "index.md"
    page.write_text("# Home\n\nUpdated.\n", encoding="utf-8")
    _commit(
        tmp_path,
        "Update page",
        author="2024-03-04T05:06:07-05:00",
        committer="2031-01-01T00:00:00+00:00",
    )
    output = _write_built_page(tmp_path)
    source_before = page.read_bytes()
    config_before = config.read_bytes()

    result = update_built_site_revision_dates(config)

    html = output.read_text(encoding="utf-8")
    assert "prodockit:update-date:start" in html
    assert 'title="Updated"' in html
    assert "2024-03-04" in html
    assert result.pages == (PageRevision("index.md", "2024-03-04", "git"),)
    assert page.read_bytes() == source_before
    assert config.read_bytes() == config_before


def test_non_git_project_uses_controlled_file_modification_time(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    page = tmp_path / "docs" / "index.md"
    timestamp = datetime(2022, 7, 8, 12, 0, tzinfo=timezone.utc).timestamp()
    os.utime(page, (timestamp, timestamp))
    output = _write_built_page(tmp_path)

    result = update_built_site_revision_dates(config)

    assert "2022-07-08" in output.read_text(encoding="utf-8")
    assert result.pages == (PageRevision("index.md", "2022-07-08", "mtime"),)
    assert not (tmp_path / ".git").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_modification_dates_option_overrides_git_author_date(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _init_git(tmp_path)
    _commit(
        tmp_path,
        "Committed page",
        author="2021-02-03T00:00:00+00:00",
        committer="2021-02-04T00:00:00+00:00",
    )
    page = tmp_path / "docs" / "index.md"
    timestamp = datetime(2026, 8, 27, tzinfo=timezone.utc).timestamp()
    os.utime(page, (timestamp, timestamp))
    output = _write_built_page(tmp_path)

    result = update_built_site_revision_dates(config, use_modification_dates=True)

    assert "2026-08-27" in output.read_text(encoding="utf-8")
    assert result.pages == (PageRevision("index.md", "2026-08-27", "mtime"),)


def test_manual_date_is_inserted_when_the_theme_did_not_render_it(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    page = tmp_path / "docs" / "index.md"
    page.write_text('---\nrevision_date: "2020-01-02"\n---\n\n# Home\n', encoding="utf-8")
    output = _write_built_page(tmp_path)

    result = update_built_site_revision_dates(config)

    assert "2020-01-02" in output.read_text(encoding="utf-8")
    assert result.pages == (PageRevision("index.md", "2020-01-02", "manual"),)


def test_existing_theme_update_fact_is_not_duplicated(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    page = tmp_path / "docs" / "index.md"
    page.write_text('---\nrevision_date: "2020-01-02"\n---\n\n# Home\n', encoding="utf-8")
    existing = HTML.replace(
        "</article>",
        '<aside class="md-source-file"><span class="md-icon" title="Last update"></span>'
        "2020-01-02</aside>\n</article>",
    )
    output = _write_built_page(tmp_path, html=existing)
    before = output.read_bytes()

    result = update_built_site_revision_dates(config)

    assert output.read_bytes() == before
    assert result.pages == (PageRevision("index.md", "2020-01-02", "manual"),)


def test_repeated_update_replaces_its_marker_without_duplication(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    page = tmp_path / "docs" / "index.md"
    timestamp = datetime(2022, 7, 8, tzinfo=timezone.utc).timestamp()
    os.utime(page, (timestamp, timestamp))
    output = _write_built_page(tmp_path)
    update_built_site_revision_dates(config)
    first = output.read_bytes()

    update_built_site_revision_dates(config)

    assert output.read_bytes() == first
    assert first.count(b"prodockit:update-date:start") == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_untracked_file_uses_mtime_without_weakening_tracked_dates(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _init_git(tmp_path)
    _commit(
        tmp_path,
        "Tracked page",
        author="2023-02-03T00:00:00+00:00",
        committer="2023-02-04T00:00:00+00:00",
    )
    untracked = tmp_path / "docs" / "new.md"
    untracked.write_text("# New\n", encoding="utf-8")
    timestamp = datetime(2025, 6, 7, tzinfo=timezone.utc).timestamp()
    os.utime(untracked, (timestamp, timestamp))
    _write_built_page(tmp_path)
    new_output = _write_built_page(tmp_path, "new/index.html")

    result = update_built_site_revision_dates(config)

    assert "2023-02-03" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "2025-06-07" in new_output.read_text(encoding="utf-8")
    assert result.pages == (
        PageRevision("index.md", "2023-02-03", "git"),
        PageRevision("new.md", "2025-06-07", "mtime"),
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_shallow_history_fails_before_changing_output(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    _write_project(origin)
    _init_git(origin)
    _commit(
        origin,
        "Page history",
        author="2024-02-01T00:00:00+00:00",
        committer="2024-02-01T00:00:00+00:00",
    )
    (origin / "unrelated.txt").write_text("later\n", encoding="utf-8")
    _commit(
        origin,
        "Unrelated tip",
        author="2024-03-01T00:00:00+00:00",
        committer="2024-03-01T00:00:00+00:00",
    )
    checkout = tmp_path / "shallow"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", origin.as_uri(), str(checkout)],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    output = _write_built_page(checkout)
    before = output.read_bytes()

    with pytest.raises(RevisionDateError, match="shallow checkout"):
        update_built_site_revision_dates(checkout / "zensical.toml")

    assert output.read_bytes() == before


def test_missing_git_supports_non_repo_but_rejects_detected_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_project(tmp_path)
    _write_built_page(tmp_path)
    monkeypatch.setattr(revision_dates.shutil, "which", lambda _name: None)

    result = update_built_site_revision_dates(config)

    assert result.pages[0].updated_source == "mtime"
    (tmp_path / ".git").mkdir()
    with pytest.raises(RevisionDateError, match="git is not installed"):
        update_built_site_revision_dates(config)


def test_missing_site_or_required_page_has_clear_recovery(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    with pytest.raises(RevisionDateError, match="run zensical build first"):
        update_built_site_revision_dates(config)

    (tmp_path / "site").mkdir()
    with pytest.raises(RevisionDateError, match="built page not found"):
        update_built_site_revision_dates(config)


def test_non_nav_markdown_without_an_output_page_is_skipped(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    (tmp_path / "docs" / "snippet.md").write_text("Included fragment\n", encoding="utf-8")
    _write_built_page(tmp_path)

    result = update_built_site_revision_dates(config)

    assert [page.source_path for page in result.pages] == ["index.md"]


def test_directory_urls_false_maps_a_page_to_html(tmp_path: Path) -> None:
    config = _write_project(tmp_path, directory_urls=False)
    page = tmp_path / "docs" / "guide.md"
    page.write_text("# Guide\n", encoding="utf-8")
    output = _write_built_page(tmp_path, "guide.html")
    _write_built_page(tmp_path)

    update_built_site_revision_dates(config)

    assert "prodockit:update-date:start" in output.read_text(encoding="utf-8")


def test_unrecognised_built_html_fails_instead_of_guessing(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    output = _write_built_page(tmp_path, html="<html><body>Different theme</body></html>")
    before = output.read_bytes()

    with pytest.raises(RevisionDateError, match="content article"):
        update_built_site_revision_dates(config)

    assert output.read_bytes() == before


def test_update_dates_cli_reports_sources_and_routes_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, bool]] = []

    def update(config_file: str, *, use_modification_dates: bool) -> RevisionUpdateResult:
        calls.append((config_file, use_modification_dates))
        return RevisionUpdateResult(
            Path("public"),
            (
                PageRevision("tracked.md", "2026-08-27", "mtime"),
                PageRevision("manual.md", "2020-01-02", "manual"),
            ),
        )

    monkeypatch.setattr(cli_module, "update_built_site_revision_dates", update)

    result = CliRunner().invoke(
        main,
        ["update-dates", "--config-file", "project.toml", "--modification-dates"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [("project.toml", True)]
    assert "1 from file modification times" in result.output
    assert "tracked.md uses its file modification time" in result.output
    assert "Updated public" in result.output


def test_update_dates_cli_reports_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise RevisionDateError("site is missing")

    monkeypatch.setattr(cli_module, "update_built_site_revision_dates", fail)

    result = CliRunner().invoke(main, ["update-dates"])

    assert result.exit_code == 1
    assert "Error: site is missing" in result.output
