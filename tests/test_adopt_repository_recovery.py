# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Ambiguous hosting operations must never trigger duplicate creation or pushes."""

import json
import subprocess
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from prodockit import adopt_repo_tools, adopt_repository


def test_activity_heading_uses_adopt_blue():
    @click.command()
    def command():
        adopt_repository.activity_heading("Site details", "Check the title and addresses.")

    result = CliRunner().invoke(command, color=True)
    assert result.exit_code == 0
    assert click.style("Activity — Site details", fg="blue", bold=True) in result.output
    assert "Check the title and addresses." in result.output


@pytest.mark.parametrize("host", ["github.com", "gitlab.surrey.ac.uk"])
@pytest.mark.parametrize("failure", ["exit", "timeout"])
@pytest.mark.parametrize(
    "outcome",
    ["connect", "decline", "missing", "wrong-url", "wrong-visibility", "bad-json", "probe-timeout"],
)
def test_ambiguous_creation(tmp_path, monkeypatch, host, failure, outcome):
    repository = f"https://{host}/team/report"
    config = tmp_path / "zensical.toml"
    config.write_text(f'[project]\nrepo_url = "{repository}"\n')
    monkeypatch.setattr(adopt_repo_tools, "ensure", lambda *a, **kw: True)
    calls = []
    client = "gh" if host == "github.com" else "glab"

    def run(command, root):
        calls.append(command)
        if command[1:3] == ["remote", "get-url"]:
            return SimpleNamespace(returncode=1, stdout="")
        if command[1:3] == ["repo", "create"]:
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, 60)
            return SimpleNamespace(returncode=1, stdout="")
        if command[1:3] == ["repo", "view"] or command[1] == "api":
            if outcome == "probe-timeout":
                raise subprocess.TimeoutExpired(command, 60)
            url = repository if outcome != "wrong-url" else f"https://{host}/other/report"
            payload = (
                {"url": url, "isPrivate": outcome != "wrong-visibility"}
                if client == "gh"
                else {
                    "web_url": url,
                    "visibility": "public" if outcome == "wrong-visibility" else "private",
                }
            )
            return SimpleNamespace(
                returncode=1 if outcome == "missing" else 0,
                stdout="invalid" if outcome == "bad-json" else json.dumps(payload),
            )
        return SimpleNamespace(returncode=0, stdout=str(root))

    monkeypatch.setattr(adopt_repository, "_run", run)

    @click.command()
    def command():
        adopt_repository.setup(config, offline=False)

    result = CliRunner().invoke(
        command, input="y\nn\nprivate\ny\n" + ("y\n" if outcome == "connect" else "n\n")
    )
    assert result.exit_code == 0, result.output
    titles = [
        "Git and hosting tools",
        "Local repository",
        "Commit name and email",
        "Sign in to the hosting service",
        "Connect the hosted repository",
        "Create the hosted repository",
    ]
    positions = [result.output.index(f"Activity — {title}") for title in titles]
    assert positions == sorted(positions)
    assert sum(c[1:3] == ["repo", "create"] for c in calls) == 1
    assert (["git", "remote", "add", "origin", repository] in calls) == (outcome == "connect")
    assert not any("push" in c or "commit" in c or "set-url" in c for c in calls)
    if client == "glab":
        assert ["glab", "api", "projects/team%2Freport", "--hostname", host] in calls
    if outcome == "connect":
        assert "Origin configured" in result.output
    elif outcome != "decline":
        assert "Could not verify" in result.output


@pytest.mark.parametrize(
    "payload", [{}, [], {"url": "https://github.com/team/report", "isPrivate": "false"}]
)
def test_verification_rejects_incomplete_metadata(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(
        adopt_repository,
        "_run",
        lambda *a: SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
    )
    assert not adopt_repository._verify_created_repository(
        tmp_path, "gh", "https://github.com/team/report", "public"
    )


def test_authentication_timeout_has_specific_recovery(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(adopt_repository, "_run", lambda *a: SimpleNamespace(returncode=1))
    monkeypatch.setattr(click, "confirm", lambda *a, **kw: True)

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(adopt_repository.subprocess, "run", timeout)
    assert not adopt_repository._authenticate(tmp_path, "gh", "github.com")
    output = capsys.readouterr().out
    assert "Sign-in timed out" in output
    assert "gh auth login --hostname github.com" in output
    assert "pdk adopt --apply" in output
