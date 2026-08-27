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
from prodockit.project_config import find_project_config, load_project_config
from prodockit.revision_dates import (
    PageRevision,
    RevisionBuildResult,
    RevisionDateError,
    build_site_with_revision_dates,
)


def _write_project(root: Path, *, config_name: str = "zensical.toml") -> Path:
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text("# Home\n", encoding="utf-8")
    (root / ".gitignore").write_text("site/\n", encoding="utf-8")
    config = root / config_name
    if config.suffix == ".toml":
        config.write_text(
            '[project]\nsite_name = "Revision test"\nnav = [{ "Home" = "index.md" }]\n',
            encoding="utf-8",
        )
    else:
        config.write_text(
            "site_name: Revision test\nnav:\n    - Home: index.md\n",
            encoding="utf-8",
        )
    return config


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


def _capture_staged(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    captured: dict[str, bytes] = {}

    def build(_config, staged_docs: Path, *, strict: bool) -> tuple[str, str]:
        for page in staged_docs.rglob("*.md"):
            captured[page.relative_to(staged_docs).as_posix()] = page.read_bytes()
        captured["strict"] = str(strict).encode()
        return "Build finished", ""

    monkeypatch.setattr(revision_dates, "_build_staged_site", build)
    return captured


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_full_git_history_uses_author_dates_and_leaves_source_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    original = page.read_bytes()
    captured = _capture_staged(monkeypatch)

    result = build_site_with_revision_dates(config, include_creation=True, strict=True)

    staged = captured["index.md"].decode()
    assert 'revision_date: "2024-03-04"' in staged
    assert 'git_creation_date_localized: "2024-01-02"' in staged
    assert captured["strict"] == b"True"
    assert result.pages == (PageRevision("index.md", "git", "git"),)
    assert page.read_bytes() == original
    assert _git(tmp_path, "status", "--short") == ""
    assert not list(tmp_path.glob(".prodockit-revision-dates-*"))


def test_non_git_project_uses_controlled_file_modification_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_project(tmp_path)
    page = tmp_path / "docs" / "index.md"
    timestamp = datetime(2022, 7, 8, 12, 0, tzinfo=timezone.utc).timestamp()
    os.utime(page, (timestamp, timestamp))
    captured = _capture_staged(monkeypatch)

    result = build_site_with_revision_dates(config)

    assert 'revision_date: "2022-07-08"' in captured["index.md"].decode()
    assert result.pages == (PageRevision("index.md", "mtime"),)


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_untracked_file_uses_mtime_without_weakening_tracked_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_project(tmp_path)
    _init_git(tmp_path)
    _commit(
        tmp_path,
        "Tracked page",
        author="2023-02-03T00:00:00+00:00",
        committer="2023-02-04T00:00:00+00:00",
    )
    untracked = tmp_path / "docs" / "new page.md"
    untracked.write_text("# New\n", encoding="utf-8")
    timestamp = datetime(2025, 6, 7, tzinfo=timezone.utc).timestamp()
    os.utime(untracked, (timestamp, timestamp))
    captured = _capture_staged(monkeypatch)

    result = build_site_with_revision_dates(config)

    assert 'revision_date: "2023-02-03"' in captured["index.md"].decode()
    assert 'revision_date: "2025-06-07"' in captured["new page.md"].decode()
    assert result.pages == (
        PageRevision("index.md", "git"),
        PageRevision("new page.md", "mtime"),
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_uncommitted_edit_keeps_the_last_committed_author_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_project(tmp_path)
    _init_git(tmp_path)
    _commit(
        tmp_path,
        "Committed page",
        author="2021-02-03T00:00:00+00:00",
        committer="2021-02-04T00:00:00+00:00",
    )
    page = tmp_path / "docs" / "index.md"
    page.write_text("# Home\n\nUncommitted edit.\n", encoding="utf-8")
    timestamp = datetime(2026, 8, 27, tzinfo=timezone.utc).timestamp()
    os.utime(page, (timestamp, timestamp))
    captured = _capture_staged(monkeypatch)

    result = build_site_with_revision_dates(config)

    assert 'revision_date: "2021-02-03"' in captured["index.md"].decode()
    assert result.pages == (PageRevision("index.md", "git"),)


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_follow_preserves_creation_date_across_a_unicode_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_project(tmp_path)
    _init_git(tmp_path)
    _commit(
        tmp_path,
        "Original name",
        author="2020-01-02T00:00:00+00:00",
        committer="2020-01-03T00:00:00+00:00",
    )
    _git(tmp_path, "mv", "docs/index.md", "docs/Café page.md")
    _commit(
        tmp_path,
        "Rename page",
        author="2024-04-05T00:00:00+00:00",
        committer="2024-04-06T00:00:00+00:00",
    )
    captured = _capture_staged(monkeypatch)

    result = build_site_with_revision_dates(config, include_creation=True)

    staged = captured["Café page.md"].decode()
    assert 'revision_date: "2024-04-05"' in staged
    assert 'git_creation_date_localized: "2020-01-02"' in staged
    assert result.pages == (PageRevision("Café page.md", "git", "git"),)


def test_manual_metadata_wins_and_crlf_unicode_are_preserved_in_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_project(tmp_path)
    page = tmp_path / "docs" / "index.md"
    source = (
        "---\r\n"
        'revision_date: "1999-12-31"\r\n'
        'git_creation_date_localized: "1999-01-01"\r\n'
        "---\r\n\r\n"
        "# Café résumé\r\n"
    ).encode()
    page.write_bytes(source)
    captured = _capture_staged(monkeypatch)

    result = build_site_with_revision_dates(config, include_creation=True)

    assert captured["index.md"] == source
    assert page.read_bytes() == source
    assert result.pages == (PageRevision("index.md", "manual", "manual"),)


def test_generated_front_matter_preserves_crlf_and_unicode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_project(tmp_path)
    page = tmp_path / "docs" / "index.md"
    page.write_bytes("# Café\r\n\r\nRésumé.\r\n".encode())
    timestamp = datetime(2021, 4, 5, tzinfo=timezone.utc).timestamp()
    os.utime(page, (timestamp, timestamp))
    captured = _capture_staged(monkeypatch)

    build_site_with_revision_dates(config)

    staged = captured["index.md"]
    assert b'revision_date: "2021-04-05"\r\n' in staged
    assert b"Caf\xc3\xa9\r\n" in staged
    assert b"\n" not in staged.replace(b"\r\n", b"")


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_shallow_history_fails_instead_of_using_a_plausible_boundary_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    monkeypatch.chdir(checkout)

    with pytest.raises(RevisionDateError, match="shallow checkout") as caught:
        build_site_with_revision_dates(checkout / "zensical.toml")

    assert "fetch-depth: 0" in str(caught.value)
    assert 'GIT_DEPTH: "0"' in str(caught.value)


def test_missing_git_supports_non_repo_but_rejects_detected_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_project(tmp_path)
    _capture_staged(monkeypatch)
    monkeypatch.setattr(revision_dates.shutil, "which", lambda _name: None)

    result = build_site_with_revision_dates(config)

    assert result.pages[0].updated_source == "mtime"
    (tmp_path / ".git").mkdir()
    with pytest.raises(RevisionDateError, match="git is not installed"):
        build_site_with_revision_dates(config)


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_empty_repository_uses_modification_dates(tmp_path: Path, monkeypatch) -> None:
    config = _write_project(tmp_path)
    _init_git(tmp_path)
    captured = _capture_staged(monkeypatch)

    result = build_site_with_revision_dates(config)

    assert result.pages == (PageRevision("index.md", "mtime"),)
    assert b"revision_date:" in captured["index.md"]


def test_failed_build_removes_temporary_config_and_does_not_change_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_project(tmp_path)
    page = tmp_path / "docs" / "index.md"
    original = page.read_bytes()
    monkeypatch.setattr(revision_dates, "_git_history", lambda _root: None)
    monkeypatch.setattr(revision_dates, "_zensical_cli", lambda: "zensical")
    monkeypatch.setattr(
        revision_dates.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 2, "", "broken page"),
    )

    with pytest.raises(RevisionDateError, match="status 2") as caught:
        build_site_with_revision_dates(config)

    assert caught.value.stderr == "broken page"
    assert page.read_bytes() == original
    assert not list(tmp_path.glob(".prodockit-revision-dates-*"))


@pytest.mark.parametrize("config_name", ["zensical.toml", "mkdocs.yml"])
def test_staged_config_keeps_root_and_overrides_only_docs_dir(
    tmp_path: Path, config_name: str
) -> None:
    config_path = _write_project(tmp_path, config_name=config_name)
    config = load_project_config(config_path)
    staged = tmp_path / ".prodockit-revision-dates-test" / "docs"

    source = revision_dates._staged_config_source(config, staged)

    configured = ".prodockit-revision-dates-test/docs"
    if config_path.suffix == ".toml":
        assert f'docs_dir = "{configured}"' in source
        assert '[project]\ndocs_dir = ' in source
    else:
        assert source.startswith(f'docs_dir: "{configured}"\n')
    assert "site_name" in source


def test_config_environment_override_selects_the_staged_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path)
    staged = tmp_path / ".prodockit-revision-dates-test.toml"
    staged.write_text("[project]\n", encoding="utf-8")
    monkeypatch.setenv(revision_dates.CONFIG_OVERRIDE_ENV, str(staged))

    assert find_project_config(tmp_path) == staged


def test_build_cli_reports_fallbacks_and_routes_options(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool, bool]] = []

    def build(config_file: str, *, include_creation: bool, strict: bool) -> RevisionBuildResult:
        calls.append((config_file, include_creation, strict))
        return RevisionBuildResult(
            Path("public"),
            (
                PageRevision("tracked.md", "git", "git"),
                PageRevision("new.md", "mtime"),
                PageRevision("manual.md", "manual", "manual"),
            ),
            "Build finished",
        )

    monkeypatch.setattr(cli_module, "build_site_with_revision_dates", build)

    result = CliRunner().invoke(
        main,
        ["build", "--config-file", "project.toml", "--creation-dates", "--strict"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [("project.toml", True, True)]
    assert "1 from Git" in result.output
    assert "1 from file modification times" in result.output
    assert "new.md uses its file modification time" in result.output
    assert "1 unavailable without Git history" in result.output
    assert "new.md has no Git creation date" in result.output
    assert "Built public" in result.output


def test_build_cli_reports_revision_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise RevisionDateError("history is incomplete", stderr="git detail")

    monkeypatch.setattr(cli_module, "build_site_with_revision_dates", fail)

    result = CliRunner().invoke(main, ["build"])

    assert result.exit_code == 1
    assert "Error: history is incomplete" in result.output
    assert "git detail" in result.output


@pytest.mark.skipif(shutil.which("git") is None, reason="Git harness needs the local Git CLI")
def test_real_zensical_build_renders_revision_and_creation_facts(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _init_git(tmp_path)
    _commit(
        tmp_path,
        "Initial page",
        author="2020-05-06T00:00:00+00:00",
        committer="2030-05-06T00:00:00+00:00",
    )
    page = tmp_path / "docs" / "index.md"
    original = page.read_bytes()

    result = build_site_with_revision_dates(config, include_creation=True, strict=True)

    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "2020-05-06" in html
    assert 'title="Last update"' in html
    assert 'title="Created"' in html
    assert result.pages == (PageRevision("index.md", "git", "git"),)
    assert page.read_bytes() == original
    assert _git(tmp_path, "status", "--short") == ""
