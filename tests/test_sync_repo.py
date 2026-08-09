# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for `prodockit.sync_repo` - keeping repo links, brand icon and
README badges in step with the git remote a checkout actually uses."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from prodockit.sync_repo import (
    SyncRepoError,
    badges_for_host,
    detect_default_branch,
    edit_uri_for_host,
    icon_for_host,
    parse_remote,
    repo_name_matching_existing,
    sync_repo_metadata,
    update_config,
    update_readme,
)

CONFIG = """\
[project]
site_name = "Example"
docs_dir = "docs"
repo_url = "https://github.com/old/old-repo"
repo_name = "old-repo"
edit_uri = "edit/master/docs/"

[project.theme.icon]
repo = "fontawesome/brands/git-alt"
"""

README = """\
# Example

<!-- repo-badges:start -->
old badges
<!-- repo-badges:end -->

Body text.
"""


# --- Remote parsing --------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/owner/repo", ("github.com", "owner", "repo")),
        ("https://github.com/owner/repo.git", ("github.com", "owner", "repo")),
        ("git@github.com:owner/repo.git", ("github.com", "owner", "repo")),
        ("ssh://git@gitlab.com/owner/repo.git", ("gitlab.com", "owner", "repo")),
        # Self-hosted GitLab with a subgroup - the repo is the last segment,
        # the owner the first, which is what the badge/edit URLs need.
        ("https://gitlab.surrey.ac.uk/group/sub/repo", ("gitlab.surrey.ac.uk", "group", "repo")),
    ],
)
def test_parse_remote_handles_ssh_and_https_forms(url: str, expected: tuple[str, str, str]) -> None:
    assert parse_remote(url) == expected


@pytest.mark.parametrize("url", ["", "not-a-url", "https://github.com/", "https://github.com/only"])
def test_parse_remote_rejects_what_it_cannot_parse(url: str) -> None:
    with pytest.raises(SyncRepoError):
        parse_remote(url)


# --- Host mapping ----------------------------------------------------------


def test_icon_for_host_recognises_known_hosts() -> None:
    assert icon_for_host("github.com")[:2] == ("github", "fontawesome/brands/github")
    assert icon_for_host("gitlab.com")[:2] == ("gitlab", "fontawesome/brands/gitlab")
    assert icon_for_host("bitbucket.org")[:2] == ("bitbucket", "fontawesome/brands/bitbucket")


def test_icon_for_host_matches_a_self_hosted_gitlab() -> None:
    """Matched on a substring, so an institution's own GitLab still gets the
    GitLab icon and edit_uri rather than the generic fallback."""
    kind, icon, label = icon_for_host("gitlab.surrey.ac.uk")
    assert (kind, icon) == ("gitlab", "fontawesome/brands/gitlab")
    assert label == "GitLab"


def test_icon_for_host_falls_back_for_an_unknown_host() -> None:
    kind, icon, label = icon_for_host("git.example.com")
    assert kind == "other"
    assert icon == "fontawesome/brands/git-alt"
    assert label == "git.example.com"


def test_edit_uri_uses_the_real_default_branch_not_master() -> None:
    """Zensical's own default hardcodes `master`; this is the reason for
    setting edit_uri explicitly at all."""
    assert edit_uri_for_host("github", "docs", "main") == "edit/main/docs/"
    assert edit_uri_for_host("gitlab", "content/", "develop") == "edit/develop/content/"


def test_edit_uri_is_left_unset_for_a_host_with_no_known_edit_url() -> None:
    assert edit_uri_for_host("bitbucket", "docs", "main") is None
    assert edit_uri_for_host("other", "docs", "main") is None


# --- Config rewriting ------------------------------------------------------


def test_update_config_rewrites_every_setting() -> None:
    updated, changes = update_config(
        CONFIG,
        repo_url="https://github.com/new/new-repo",
        owner="new",
        repo_name="new-repo",
        icon="fontawesome/brands/github",
        edit_uri="edit/main/docs/",
    )
    assert 'repo_url = "https://github.com/new/new-repo"' in updated
    assert 'repo_name = "new-repo"' in updated
    assert 'repo = "fontawesome/brands/github"' in updated
    assert 'edit_uri = "edit/main/docs/"' in updated
    assert set(changes) == {"repo_url", "repo_name", "theme.icon.repo", "edit_uri"}


def test_update_config_reports_no_changes_when_already_in_sync() -> None:
    once, _ = update_config(
        CONFIG,
        repo_url="https://github.com/new/new-repo",
        owner="new",
        repo_name="new-repo",
        icon="fontawesome/brands/github",
        edit_uri="edit/main/docs/",
    )
    twice, changes = update_config(
        once,
        repo_url="https://github.com/new/new-repo",
        owner="new",
        repo_name="new-repo",
        icon="fontawesome/brands/github",
        edit_uri="edit/main/docs/",
    )
    assert twice == once
    assert changes == []


def test_update_config_preserves_comments_and_unrelated_settings() -> None:
    """A line-level rewrite rather than a TOML round-trip, so the comments
    carrying the reasoning for each setting survive."""
    text = '# why this is set\nrepo_url = "https://github.com/old/old"\n' + CONFIG
    updated, _ = update_config(
        text,
        repo_url="https://github.com/new/new",
        owner="new",
        repo_name="new",
        icon="fontawesome/brands/github",
        edit_uri=None,
    )
    assert "# why this is set" in updated
    assert 'site_name = "Example"' in updated


def test_update_config_inserts_edit_uri_when_the_config_predates_it() -> None:
    without = CONFIG.replace('edit_uri = "edit/master/docs/"\n', "")
    updated, changes = update_config(
        without,
        repo_url="https://github.com/new/new-repo",
        owner="new",
        repo_name="new-repo",
        icon="fontawesome/brands/github",
        edit_uri="edit/main/docs/",
    )
    assert 'edit_uri = "edit/main/docs/"' in updated
    assert "edit_uri" in changes
    # Inserted directly after repo_name, not appended somewhere arbitrary.
    lines = updated.splitlines()
    assert lines[lines.index('edit_uri = "edit/main/docs/"') - 1].startswith("repo_name =")


def test_update_config_raises_when_a_required_setting_is_missing() -> None:
    with pytest.raises(SyncRepoError, match="repo_url"):
        update_config(
            "[project]\n",
            repo_url="https://github.com/new/new",
            owner="new",
            repo_name="new",
            icon="fontawesome/brands/github",
            edit_uri=None,
        )


# --- repo_name shape -------------------------------------------------------


def test_repo_name_keeps_the_owner_prefix_when_the_config_already_uses_one() -> None:
    """Both shapes are legitimate and Zensical prints repo_name verbatim in
    the header, so the existing value decides - otherwise syncing would
    silently restyle the header of every project using the other one."""
    text = 'repo_name = "someone/some-repo"'
    assert repo_name_matching_existing(text, "new", "new-repo") == "new/new-repo"


def test_repo_name_stays_bare_when_the_config_uses_the_bare_form() -> None:
    assert repo_name_matching_existing('repo_name = "some-repo"', "new", "new-repo") == "new-repo"


# --- README badges ---------------------------------------------------------


def test_badges_are_generated_for_github_and_gitlab() -> None:
    github = badges_for_host("github", "github.com", "owner", "repo", "main")
    assert github is not None
    assert "github.com/owner/repo/actions" in github
    assert "img.shields.io/github/stars/owner/repo" in github

    gitlab = badges_for_host("gitlab", "gitlab.com", "owner", "repo", "develop")
    assert gitlab is not None
    assert "https://gitlab.com/owner/repo/badges/develop/pipeline.svg" in gitlab
    assert "img.shields.io/gitlab/stars/owner%2Frepo" in gitlab


def test_gitlab_badges_point_at_a_self_hosted_instance_not_gitlab_com() -> None:
    """The badge row is chosen by host kind, and "gitlab" matches any
    instance - so building the URLs from the kind alone sent every link to
    gitlab.com, naming a repository that does not exist there
    (prodockit-extensions#198).
    """
    badges = badges_for_host("gitlab", "gitlab.surrey.ac.uk", "mb0105", "report", "main")
    assert badges is not None
    assert "gitlab.com" not in badges
    assert "https://gitlab.surrey.ac.uk/mb0105/report/-/pipelines" in badges
    assert "https://gitlab.surrey.ac.uk/mb0105/report/badges/main/pipeline.svg" in badges


def test_self_hosted_gitlab_omits_the_badges_shields_cannot_read() -> None:
    """Stars and forks have no instance-served equivalent, and shields.io
    resolves its gitlab endpoints against gitlab.com - so on a self-hosted
    instance those two badges could only ever render broken. A missing
    badge beats one that is permanently unavailable."""
    badges = badges_for_host("gitlab", "gitlab.example.org", "owner", "repo", "main")
    assert badges is not None
    assert "img.shields.io" not in badges
    assert badges.count("<img") == 1


def test_no_badges_are_invented_for_a_host_without_a_known_set() -> None:
    assert badges_for_host("bitbucket", "bitbucket.org", "owner", "repo", "main") is None
    assert badges_for_host("other", "git.example.com", "owner", "repo", "main") is None


def test_update_readme_replaces_only_the_marked_block() -> None:
    updated, changed = update_readme(README, "NEW BADGES")
    assert changed
    assert "NEW BADGES" in updated
    assert "old badges" not in updated
    assert updated.startswith("# Example")
    assert updated.rstrip().endswith("Body text.")


def test_update_readme_fills_an_empty_marker_pair() -> None:
    """A template ships the two markers with nothing between them, for
    `sync-repo` to fill in on first run. That was the one shape the block
    pattern could not match, because the start group consumed the only
    newline present and the end marker was then required to have another
    one before it - so the badges were never written, and sync-repo
    reported the markers as missing (prodockit-extensions#198).
    """
    text = "# Example\n\n<!-- repo-badges:start -->\n<!-- repo-badges:end -->\n\nBody text.\n"
    updated, changed = update_readme(text, "NEW BADGES")
    assert changed
    assert "NEW BADGES" in updated
    assert updated == (
        "# Example\n\n<!-- repo-badges:start -->\nNEW BADGES\n"
        "<!-- repo-badges:end -->\n\nBody text.\n"
    )


def test_update_readme_is_idempotent_over_its_own_output() -> None:
    """Guards the newline the substitution now adds before the end marker:
    reinserting one on every run would grow a blank line each time, and
    `--check` would report drift forever."""
    text = "<!-- repo-badges:start -->\n<!-- repo-badges:end -->\n"
    once, _ = update_readme(text, "BADGES")
    twice, changed_again = update_readme(once, "BADGES")
    assert twice == once
    assert not changed_again


def test_update_readme_leaves_a_readme_without_markers_alone() -> None:
    """A project that doesn't want managed badges just omits the markers -
    a valid state, not an error."""
    text = "# Example\n\nNo markers here.\n"
    updated, changed = update_readme(text, "NEW BADGES")
    assert updated == text
    assert not changed


# --- End to end, against a real git repo -----------------------------------


@pytest.fixture()
def git_project(tmp_path: Path):
    """A real git repo with a remote, a config and a README - so the tests
    exercise the actual `git remote get-url` path rather than a stub."""

    def _make(remote_url: str, *, config: str = CONFIG, readme: str | None = README) -> Path:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=tmp_path, check=True)
        (tmp_path / "zensical.toml").write_text(config, encoding="utf-8")
        if readme is not None:
            (tmp_path / "README.md").write_text(readme, encoding="utf-8")
        return tmp_path

    return _make


def test_sync_updates_config_and_readme_from_the_real_remote(git_project, monkeypatch) -> None:
    project = git_project("https://github.com/new/new-repo.git")
    monkeypatch.chdir(project)

    result = sync_repo_metadata(default_branch="main")

    assert result.changed
    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert 'repo_url = "https://github.com/new/new-repo"' in config
    assert 'repo_name = "new-repo"' in config
    assert 'repo = "fontawesome/brands/github"' in config
    assert 'edit_uri = "edit/main/docs/"' in config
    assert "github.com/new/new-repo/actions" in (project / "README.md").read_text(encoding="utf-8")


def test_sync_is_idempotent(git_project, monkeypatch) -> None:
    project = git_project("https://github.com/new/new-repo.git")
    monkeypatch.chdir(project)

    sync_repo_metadata(default_branch="main")
    second = sync_repo_metadata(default_branch="main")

    assert not second.changed
    assert second.changes == []


def test_check_reports_drift_without_writing(git_project, monkeypatch) -> None:
    project = git_project("https://github.com/new/new-repo.git")
    monkeypatch.chdir(project)
    before = (project / "zensical.toml").read_text(encoding="utf-8")

    result = sync_repo_metadata(default_branch="main", check=True)

    assert result.changed
    assert "repo_url" in result.changes
    assert (project / "zensical.toml").read_text(encoding="utf-8") == before, (
        "check mode must not write - it exists to report drift in CI"
    )


def test_sync_reports_a_missing_remote_clearly(tmp_path: Path, monkeypatch) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "zensical.toml").write_text(CONFIG, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SyncRepoError, match="no 'origin' git remote"):
        sync_repo_metadata()


def test_sync_notes_when_a_host_has_no_badge_set(git_project, monkeypatch) -> None:
    project = git_project("https://bitbucket.org/new/new-repo.git")
    monkeypatch.chdir(project)

    result = sync_repo_metadata(default_branch="main")

    assert any("badge set" in note for note in result.notes)
    assert "old badges" in (project / "README.md").read_text(encoding="utf-8")


def test_detect_default_branch_falls_back_without_a_remote_head(tmp_path: Path) -> None:
    """A checkout with no refs/remotes/origin/HEAD gets "main" rather than an
    error - a wrong edit_uri is a better failure than a stopped build."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert detect_default_branch(cwd=str(tmp_path)) == "main"
