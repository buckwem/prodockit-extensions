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
    site_url_for,
    site_url_is_ours_to_replace,
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
        # Self-hosted GitLab with a subgroup. The namespace is every
        # segment before the last, not just the first: the URLs are built
        # from it, and `group/repo` names a project that does not exist
        # (prodockit-extensions#201). This case previously asserted the
        # truncated form, with a comment claiming it was what the badge
        # and edit URLs needed - the opposite of what they need.
        ("https://gitlab.surrey.ac.uk/group/sub/repo", ("gitlab.surrey.ac.uk", "group/sub", "repo")),
        ("git@gitlab.surrey.ac.uk:cs-dept/year3/report.git", ("gitlab.surrey.ac.uk", "cs-dept/year3", "report")),
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


def test_site_url_derives_a_github_pages_url() -> None:
    assert site_url_for("github", "Buckwem", "report", None) == "https://buckwem.github.io/report/"


def test_site_url_handles_the_owner_named_repository() -> None:
    """A repository called `<owner>.github.io` is served at the bare origin,
    not one level down inside itself."""
    assert (
        site_url_for("github", "buckwem", "buckwem.github.io", None)
        == "https://buckwem.github.io/"
    )


def test_site_url_is_not_guessed_for_gitlab() -> None:
    """Self-hosted Pages lives at an instance setting the remote URL does
    not reveal, and gitlab.com now issues unique domains - so there is
    nothing reliable to derive. A confidently wrong canonical URL points
    search engines at somewhere that does not exist."""
    assert site_url_for("gitlab", "mb0105", "report", None) is None
    assert site_url_for("other", "owner", "repo", None) is None


def test_pages_base_supplies_what_cannot_be_derived() -> None:
    base = "https://mb0105.pages.gitlab.surrey.ac.uk"
    assert (
        site_url_for("gitlab", "mb0105", "report", base)
        == "https://mb0105.pages.gitlab.surrey.ac.uk/report/"
    )
    # A trailing slash on the configured base must not double up.
    assert site_url_for("gitlab", "mb0105", "report", base + "/").endswith(".uk/report/")


@pytest.mark.parametrize(
    "current,replaceable",
    [
        # Already a Pages URL - set up to follow the repo, so it should
        # keep following it.
        ("https://buckwem.github.io/old-name/", True),
        ("https://group.gitlab.io/project/", True),
        # A code host is not a site address at all. This is what the
        # template shipped, so it is the case that matters most.
        ("https://github.com/buckwem/report/", True),
        ("https://gitlab.surrey.ac.uk/mb0105/report/", True),
        # A deliberate custom domain.
        ("https://docs.example.com/", False),
        ("https://prodockit.org/", False),
        ("", False),
    ],
)
def test_which_site_urls_may_be_replaced(current: str, replaceable: bool) -> None:
    assert site_url_is_ours_to_replace(current) is replaceable


def test_update_config_rewrites_every_setting() -> None:
    updated, changes = update_config(
        CONFIG,
        repo_url="https://github.com/new/new-repo",
        namespace="new",
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
        namespace="new",
        repo_name="new-repo",
        icon="fontawesome/brands/github",
        edit_uri="edit/main/docs/",
    )
    twice, changes = update_config(
        once,
        repo_url="https://github.com/new/new-repo",
        namespace="new",
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
        namespace="new",
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
        namespace="new",
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
            namespace="new",
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


def test_badges_carry_the_whole_gitlab_namespace() -> None:
    """A nested group has to survive into the badge URLs - `cs-dept/report`
    is a project that does not exist (prodockit-extensions#201)."""
    badges = badges_for_host("gitlab", "gitlab.surrey.ac.uk", "cs-dept/year3", "report", "main")
    assert badges is not None
    assert "https://gitlab.surrey.ac.uk/cs-dept/year3/report/-/pipelines" in badges
    assert "https://gitlab.surrey.ac.uk/cs-dept/year3/report/badges/main/pipeline.svg" in badges


def test_gitlab_com_shields_badges_encode_every_namespace_separator() -> None:
    """shields.io takes the project as a single percent-encoded path, so a
    nested namespace needs its inner separators encoded too - a raw slash
    would be read as the end of the path parameter."""
    badges = badges_for_host("gitlab", "gitlab.com", "group/sub", "repo", "main")
    assert badges is not None
    assert "stars/group%2Fsub%2Frepo" in badges
    assert "forks/group%2Fsub%2Frepo" in badges


def test_repo_name_label_shows_the_immediate_parent_not_the_whole_path() -> None:
    """`repo_name` is a header label, not a link - its target is `repo_url`,
    which carries the full namespace. A deeply nested project shows its
    immediate parent so the header stays readable, and a single-segment
    namespace is unchanged."""
    config = 'repo_name = "old/old"\n'
    assert repo_name_matching_existing(config, "cs-dept/year3", "report") == "year3/report"
    assert repo_name_matching_existing(config, "buckwem", "repo") == "buckwem/repo"
    # The bare form stays bare whatever the namespace looks like.
    assert repo_name_matching_existing('repo_name = "old"\n', "cs-dept/year3", "report") == "report"


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


def test_sync_handles_a_gitlab_subgroup_end_to_end(git_project, monkeypatch) -> None:
    """The whole point of #201: the namespace has to survive into every
    generated URL, not just into `parse_remote`'s return value. Nested
    groups are the normal arrangement on university and company GitLab
    instances."""
    project = git_project("git@gitlab.surrey.ac.uk:cs-dept/year3/report.git")
    monkeypatch.chdir(project)

    sync_repo_metadata(default_branch="main")

    config = (project / "zensical.toml").read_text(encoding="utf-8")
    assert 'repo_url = "https://gitlab.surrey.ac.uk/cs-dept/year3/report"' in config
    assert 'repo = "fontawesome/brands/gitlab"' in config
    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "https://gitlab.surrey.ac.uk/cs-dept/year3/report/badges/main/pipeline.svg" in readme
    # The truncated project this used to generate must appear nowhere.
    assert "cs-dept/report" not in config
    assert "cs-dept/report" not in readme


def test_sync_replaces_a_repo_url_used_as_site_url(git_project, monkeypatch) -> None:
    """The shape the project template shipped for a long time: `site_url`
    pointing at the repository, which put a GitHub page in every
    `<link rel="canonical">` and every sitemap entry
    (prodockit-extensions#200)."""
    config = CONFIG.replace(
        'site_name = "Example"',
        'site_name = "Example"\nsite_url = "https://github.com/old/old-repo/"',
    )
    project = git_project("https://github.com/new/new-repo.git", config=config)
    monkeypatch.chdir(project)

    result = sync_repo_metadata(default_branch="main")

    assert "site_url" in result.changes
    written = (project / "zensical.toml").read_text(encoding="utf-8")
    assert 'site_url = "https://new.github.io/new-repo/"' in written


def test_sync_leaves_a_custom_domain_alone(git_project, monkeypatch) -> None:
    """`--check` is a CI gate, so rewriting a deliberate custom domain
    would not just lose it once - it would report drift on every run
    afterwards and redden builds for a correct config."""
    config = CONFIG.replace(
        'site_name = "Example"',
        'site_name = "Example"\nsite_url = "https://docs.example.com/"',
    )
    project = git_project("https://github.com/new/new-repo.git", config=config)
    monkeypatch.chdir(project)

    result = sync_repo_metadata(default_branch="main")

    assert "site_url" not in result.changes
    assert 'site_url = "https://docs.example.com/"' in (
        project / "zensical.toml"
    ).read_text(encoding="utf-8")
    assert any("custom domain" in note for note in result.notes)


def test_sync_does_not_invent_a_site_url_that_was_never_there(git_project, monkeypatch) -> None:
    """`site_url` is optional in Zensical. A project that left it out has
    no canonical URL by choice, and adding one would change what the site
    publishes rather than keeping it in step."""
    project = git_project("https://github.com/new/new-repo.git")  # CONFIG has no site_url
    monkeypatch.chdir(project)

    sync_repo_metadata(default_branch="main")

    assert "site_url" not in (project / "zensical.toml").read_text(encoding="utf-8")


def test_sync_notes_when_it_cannot_derive_a_site_url(git_project, monkeypatch) -> None:
    config = CONFIG.replace(
        'site_name = "Example"',
        'site_name = "Example"\nsite_url = "https://github.com/old/old-repo/"',
    )
    project = git_project("git@gitlab.surrey.ac.uk:mb0105/report.git", config=config)
    monkeypatch.chdir(project)

    result = sync_repo_metadata(default_branch="main")

    assert "site_url" not in result.changes
    assert any("pages_base" in note for note in result.notes)


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


def test_a_documentation_badge_links_to_the_published_site() -> None:
    """`sync-repo` kept `site_url` correct in the config while the README
    - the page a human actually lands on - had no way through to the site
    at all (#326)."""
    badges = badges_for_host(
        "github", "github.com", "owner", "repo", "main",
        site_url="https://owner.github.io/repo/",
    )
    assert badges is not None
    assert 'href="https://owner.github.io/repo/"' in badges
    assert "Documentation" in badges
    assert badges.index("Documentation") < badges.index("Build"), "first, as the useful link"


def test_the_site_badge_reports_status_only_where_shields_can_reach_it() -> None:
    """On a public Pages host a rotting link is worth catching. On a
    self-hosted instance shields cannot reach the site, and a status badge
    would sit permanently on "down" while it worked fine."""
    public = badges_for_host(
        "gitlab", "gitlab.com", "o", "r", "main", site_url="https://o.gitlab.io/r/"
    )
    private = badges_for_host(
        "gitlab", "gitlab.surrey.ac.uk", "o", "r", "main", site_url="https://docs.surrey.ac.uk/r/"
    )
    assert public is not None and private is not None
    assert "img.shields.io/website" in public
    assert "img.shields.io/website" not in private
    assert 'href="https://docs.surrey.ac.uk/r/"' in private, "still linked"


def test_a_private_repository_loses_the_badges_shields_cannot_read() -> None:
    """On a private repository the star and fork badges render "Stars:
    repo not found" - two of three wrong on the setup bootstrap tells
    readers to create."""
    badges = badges_for_host("github", "github.com", "owner", "repo", "main", public=False)
    assert badges is not None
    assert "shields.io/github/stars" not in badges
    assert "shields.io/github/forks" not in badges
    assert "docs.yml/badge.svg" in badges, "GitHub serves this one itself, so it works"


def test_a_public_repository_keeps_them() -> None:
    badges = badges_for_host("github", "github.com", "owner", "repo", "main", public=True)
    assert badges is not None
    assert "shields.io/github/stars" in badges
    assert "shields.io/github/forks" in badges


def test_visibility_is_read_from_what_a_stranger_sees() -> None:
    """A private repository is indistinguishable from a missing one to an
    anonymous visitor - which is exactly the view shields.io has."""
    from prodockit.sync_repo import repository_is_public

    assert repository_is_public("https://x/y", fetch=lambda _: 200) is True
    assert repository_is_public("https://x/y", fetch=lambda _: 404) is False


def test_an_unanswerable_probe_changes_nothing() -> None:
    """Offline, a timeout, or a host answering something unexpected.
    Stripping somebody's badges because their network blinked would be a
    worse fault than the one this fixes."""
    from prodockit.sync_repo import repository_is_public

    def offline(_: str) -> int:
        raise OSError("no route to host")

    assert repository_is_public("https://x/y", fetch=offline) is None
    assert repository_is_public("https://x/y", fetch=lambda _: 500) is None


def test_the_same_question_gets_the_same_answer_twice(monkeypatch) -> None:
    """`sync-repo` is asked this twice in a run, and a `404` on one call
    with a timeout on the next produced two different badge rows - so it
    reported a change it had just written itself.

    A tool that rewrites files has to be deterministic within a run
    (#343).
    """
    from prodockit import sync_repo

    monkeypatch.setattr(sync_repo, "_VISIBILITY_SEEN", {})
    answers = iter([200, 404])
    monkeypatch.setattr(sync_repo, "_status_of", lambda url, timeout=10.0: next(answers))

    first = sync_repo.repository_is_public("https://github.com/o/r")
    second = sync_repo.repository_is_public("https://github.com/o/r")

    assert first is True
    assert second is True, "the second call must not see a different world"
def test_the_tool_is_installable_under_a_short_name() -> None:
    """`pdk` is the same entry point as `prodockit`, for a tool whose
    commands are typed at a prompt, often several times over while a
    setup is being repaired.

    Read from the *installed* metadata rather than from `pyproject.toml`.
    It is the stronger check - a declaration that never became a command
    would pass a file-parsing test - and it avoids `tomllib`, which is
    3.11 and later while this project supports 3.10.
    """
    from importlib.metadata import entry_points

    scripts = {e.name: e.value for e in entry_points(group="console_scripts")}

    assert "pdk" in scripts, "installed as a command, not merely declared"
    assert scripts["pdk"] == scripts["prodockit"], "the same entry point, not a copy"


def test_boot_is_the_same_command_as_bootstrap() -> None:
    """Registered rather than wrapped - one object under two names, so
    the two cannot take different options or drift in their help.

    `bootstrap` stays: the User Guide, the issues and every script
    written so far name it.
    """
    from prodockit.cli import main

    assert main.commands["boot"] is main.commands["bootstrap"]


def test_boot_accepts_what_bootstrap_accepts() -> None:
    """The point of one object rather than two: a flag added to one is
    on the other by construction."""
    from click.testing import CliRunner

    from prodockit.cli import main

    for name in ("boot", "bootstrap"):
        result = CliRunner().invoke(main, [name, "--help"])
        assert result.exit_code == 0
        for flag in ("--check", "--dry-run", "--apply", "--configure", "--config"):
            assert flag in result.output, f"{name} is missing {flag}"
