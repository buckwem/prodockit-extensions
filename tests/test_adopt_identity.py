# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from types import SimpleNamespace

import click
import tomlkit
from click.testing import CliRunner

from prodockit import adopt_identity, adopt_repo_tools, adopt_repository


def test_guided_identity_saves_and_preserves_comments(tmp_path, monkeypatch):
    path = tmp_path / "zensical.toml"
    path.write_text(
        '[project]\n# Keep this comment\nsite_name = "Documentation"\nsite_url = "https://www.example.com/"\n'
    )
    monkeypatch.setattr(adopt_identity.shutil, "which", lambda name: None)

    @click.command()
    def command():
        adopt_identity.configure(path, apply=True, interactive=True)

    result = CliRunner().invoke(
        command, input="y\nReport\ny\ngithub.com\ny\nauthor\nreport\ny\n\ny\n"
    )
    assert result.exit_code == 0, result.output
    project = tomlkit.parse(path.read_text())["project"]
    assert project["site_name"] == "Report"
    assert project["site_url"] == "https://author.github.io/report/"
    assert project["repo_url"] == "https://github.com/author/report"
    assert project["repo_name"] == "author/report"
    assert "# Keep this comment" in path.read_text()
    assert not (tmp_path / ".git").exists()


def test_preview_is_read_only_and_has_numbered_corrections(tmp_path, monkeypatch, capsys):
    path = tmp_path / "zensical.toml"
    source = '[project]\nsite_name = "Documentation"\n'
    path.write_text(source)
    monkeypatch.setattr(
        click, "prompt", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("prompt"))
    )
    adopt_identity.configure(path, apply=False, interactive=True)
    assert path.read_text() == source
    output = capsys.readouterr().out
    assert "Run 'pdk adopt --apply' to correct:" in output
    assert "1. Site title (site_name)" in output


def test_complete_identity_does_not_prompt(tmp_path, monkeypatch):
    path = tmp_path / "zensical.toml"
    source = '[project]\nsite_name="Report"\nsite_url="https://custom.test/"\nrepo_url="https://github.com/me/report"\nrepo_name="Custom name"\n'
    path.write_text(source)
    monkeypatch.setattr(
        click, "confirm", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("prompt"))
    )
    assert not adopt_identity.configure(path, apply=True, interactive=True)
    assert path.read_text() == source


def test_repository_existing_remote_is_untouched(tmp_path, monkeypatch):
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nsite_name="Report"\nrepo_url="https://github.com/me/report"\n')
    calls = []
    monkeypatch.setattr(adopt_repo_tools.shutil, "which", lambda name: name)

    def run(command, root):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=str(tmp_path))

    monkeypatch.setattr(adopt_repository, "_run", run)
    adopt_repository.setup(path, offline=False)
    assert len(calls) == 5
    assert all("add" not in command and "init" not in command for command in calls)


def test_repository_creation_is_separately_confirmed_without_push(tmp_path, monkeypatch):
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nrepo_url="https://github.com/me/report"\n')
    calls = []
    monkeypatch.setattr(adopt_repo_tools.shutil, "which", lambda name: name)

    def run(command, root):
        calls.append(command)
        return SimpleNamespace(
            returncode=1 if command[1:3] == ["remote", "get-url"] else 0, stdout=str(tmp_path)
        )

    monkeypatch.setattr(adopt_repository, "_run", run)

    @click.command()
    def command():
        adopt_repository.setup(path, offline=False)

    result = CliRunner().invoke(command, input="y\nn\nprivate\ny\n")
    assert result.exit_code == 0, result.output
    assert ["gh", "repo", "create", "me/report", "--private"] in calls
    assert not any("push" in command or "commit" in command for command in calls)


def test_correction_summary_groups_commands(capsys):
    from prodockit.cli import _adopt_correction_summary

    _adopt_correction_summary(
        [
            SimpleNamespace(id="publishing.details", status="warn", summary="Site address missing"),
            SimpleNamespace(
                id="maintenance.adopt-readiness", status="warn", summary="Fonts missing"
            ),
        ]
    )
    assert capsys.readouterr().out == (
        "Run 'pdk adopt --apply' to correct:\n1. Site address missing\n2. Fonts missing\n"
    )


def test_declining_local_git_setup_does_not_mutate(tmp_path, monkeypatch):
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nsite_name="Report"\nrepo_url="https://github.com/me/report"\n')
    calls = []
    monkeypatch.setattr(adopt_repo_tools.shutil, "which", lambda name: name)

    def run(command, root):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(adopt_repository, "_run", run)

    @click.command()
    def command():
        adopt_repository.setup(path, offline=False)

    result = CliRunner().invoke(command, input="n\n")
    assert result.exit_code == 0
    assert calls == [["git", "rev-parse", "--show-toplevel"]]


def test_remote_creation_is_deferred_offline(tmp_path, monkeypatch):
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nrepo_url="https://gitlab.com/team/report"\n')
    calls = []
    monkeypatch.setattr(adopt_repo_tools.shutil, "which", lambda name: name)

    def run(command, root):
        calls.append(command)
        return SimpleNamespace(returncode=1 if "get-url" in command else 0, stdout=str(root))

    monkeypatch.setattr(adopt_repository, "_run", run)

    @click.command()
    def command():
        adopt_repository.setup(path, offline=True)

    result = CliRunner().invoke(command, input="y\nn\n")
    assert result.exit_code == 0
    assert "deferred in offline mode" in result.output
    assert not any("create" in command or "add" in command for command in calls)


def test_site_only_choice_does_not_ask_repository_questions(tmp_path, monkeypatch):
    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nsite_name="Documentation"\n')
    monkeypatch.setattr(
        adopt_identity.subprocess,
        "run",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Git must not run")),
    )

    @click.command()
    def command():
        adopt_identity.configure(path, apply=True, interactive=True, repository_setup=False)

    result = CliRunner().invoke(command, input="y\nMy local site\nn\ny\n")
    assert result.exit_code == 0, result.output
    project = tomlkit.parse(path.read_text())["project"]
    assert project["site_name"] == "My local site"
    assert "repo_url" not in project
    assert "Repository host" not in result.output


def test_overall_decline_does_not_enter_repository_setup(tmp_path, monkeypatch):
    from prodockit import cli

    path = tmp_path / "zensical.toml"
    path.write_text('[project]\nsite_name="Report"\n')
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    choices = iter([False, False])
    monkeypatch.setattr(click, "confirm", lambda *a, **kw: next(choices))
    seen = []
    monkeypatch.setattr(
        adopt_identity, "configure", lambda *a, **kw: seen.append(kw["repository_setup"])
    )
    monkeypatch.setattr(
        adopt_repository,
        "setup",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("repository setup")),
    )
    cli._adopt_finish_details(tmp_path, apply=True, offline=False)
    assert seen == [False]
