# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Safety and repository-boundary tests for live-provider Phase 2."""

from __future__ import annotations

import base64
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from prodockit.bootstrap.stages import WEASYPRINT_MIN_VERSION

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
live = importlib.import_module("bootstrap_live_provider_read_write")


def fixture_values(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema": 2,
        "provider": "surrey",
        "hostname": live.SURREY_HOSTNAME,
        "source_remote": live.SURREY_SOURCE,
        "source_head": "1" * 40,
        "destination_namespace": live.SURREY_NAMESPACE,
        "destination_project": live.SURREY_PROJECT,
        "destination_remote": live.SURREY_DESTINATION,
        "template_marker_path": ".prodockit-template.toml",
        "template_marker_sha256": "a" * 64,
    }
    values.update(updates)
    return values


def write_fixture(path: Path, **updates: object) -> Path:
    path.write_text(json.dumps(fixture_values(**updates)), encoding="utf-8")
    return path


def git(*arguments: str, cwd: Path, environment: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def public_key(payload: bytes = b"phase-two-test-key") -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"ssh-ed25519 {encoded} prodockit-liveprovider-phase2"


def write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o700)
    return path


def test_revocation_import_does_not_require_wheel_dependencies(tmp_path: Path) -> None:
    """The fresh safety controller must start without third-party wheel tooling."""

    (tmp_path / "sitecustomize.py").write_text(
        """\
import builtins

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "packaging" or name.startswith("packaging."):
        raise ModuleNotFoundError("packaging deliberately unavailable")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "bootstrap_live_provider_lifecycle.py"),
            "--help",
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr


def test_surrey_fixture_is_the_exact_configured_destination(tmp_path: Path) -> None:
    fixture = live.Fixture.read(write_fixture(tmp_path / "fixture.json"))

    assert fixture.source_remote == ("git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git")
    assert fixture.destination_namespace == "assessment-liveprovider-2026"
    assert fixture.destination_project == "report-liveprovider-2026-mb0105"
    assert fixture.destination_remote == (
        "git@gitlab.surrey.ac.uk:assessment-liveprovider-2026/report-liveprovider-2026-mb0105.git"
    )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"schema": 1}, "schema must be 2"),
        ({"hostname": "gitlab.com"}, "must use gitlab.surrey.ac.uk"),
        ({"source_remote": "git@gitlab.surrey.ac.uk:other/template.git"}, "must derive"),
        ({"destination_namespace": "other"}, "must derive"),
        ({"source_head": "short"}, "complete Git object ID"),
        ({"template_marker_path": "../marker"}, "stay within"),
        ({"template_marker_sha256": "A" * 64}, "lowercase"),
    ],
)
def test_fixture_fails_closed(tmp_path: Path, updates: dict[str, object], message: str) -> None:
    values = fixture_values(**updates)
    if "destination_namespace" in updates:
        values["destination_remote"] = (
            f"git@{values['hostname']}:"
            f"{values['destination_namespace']}/{values['destination_project']}.git"
        )
    with pytest.raises(live.LiveProviderError, match=message):
        live.Fixture.read(write_fixture(tmp_path / "fixture.json", **values))


def test_fixture_rejects_unknown_fields(tmp_path: Path) -> None:
    values = fixture_values(token="must-not-be-accepted")
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(values), encoding="utf-8")

    with pytest.raises(live.LiveProviderError, match="unknown token"):
        live.Fixture.read(path)


def test_public_providers_use_the_anonymous_template(tmp_path: Path) -> None:
    for provider, hostname in (("github", "github.com"),):
        namespace = "prodockit-live-tests"
        project = "bootstrap-phase-two"
        fixture = live.Fixture.read(
            write_fixture(
                tmp_path / f"{provider}.json",
                provider=provider,
                hostname=hostname,
                source_remote=live.PUBLIC_TEMPLATE,
                destination_namespace=namespace,
                destination_project=project,
                destination_remote=f"git@{hostname}:{namespace}/{project}.git",
            )
        )
        assert fixture.source_remote.startswith("https://github.com/")


def test_phase_two_requires_an_exclusive_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    socket = tmp_path / "agent.sock"
    approved = public_key()
    fingerprint = live.public_key_fingerprint(approved)
    identity = live.AgentIdentity(socket, approved, fingerprint)
    monkeypatch.setattr(live, "select_agent_identity", lambda *_args: identity)
    monkeypatch.setattr(live.shutil, "which", lambda _name: "/usr/bin/ssh-add")
    two = subprocess.CompletedProcess(
        [],
        0,
        approved + "\n" + public_key(b"another-key") + "\n",
        "",
    )
    monkeypatch.setattr(live.subprocess, "run", lambda *_args, **_kwargs: two)

    with pytest.raises(live.LiveProviderError, match="exactly one identity"):
        live.validate_exclusive_agent(socket, fingerprint)

    one = subprocess.CompletedProcess([], 0, approved + "\n", "")
    monkeypatch.setattr(live.subprocess, "run", lambda *_args, **_kwargs: one)
    assert live.validate_exclusive_agent(socket, fingerprint) == identity


def test_temporary_home_contains_only_the_agents_public_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = live.Fixture(**fixture_values())
    record = public_key()
    identity = live.AgentIdentity(
        tmp_path / "agent.sock", record, live.public_key_fingerprint(record)
    )
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("gitlab.surrey.ac.uk ssh-ed25519 AAAA\n", encoding="utf-8")
    monkeypatch.setattr(live, "make_ssh_shim", lambda *_args: tmp_path / "bin" / "ssh")

    live.prepare_home(
        tmp_path / "home",
        fixture=fixture,
        known_hosts=known_hosts,
        agent=identity,
        system_ssh=Path("/usr/bin/ssh"),
    )

    key = tmp_path / "home" / ".ssh" / "id_ed25519_gitlab"
    config = tmp_path / "home" / ".ssh" / "config"
    assert key.read_text(encoding="utf-8").strip() == record
    assert key.with_suffix(".pub").read_text(encoding="utf-8").strip() == record
    assert "PRIVATE KEY" not in key.read_text(encoding="utf-8")
    assert f"IdentityFile {live.ssh_config_path(key)}" in config.read_text(encoding="utf-8")
    assert "IdentityFile ~/" not in config.read_text(encoding="utf-8")


def test_user_tooling_is_copied_without_exposing_the_host_home(tmp_path: Path) -> None:
    host_home = tmp_path / "host"
    fonts = host_home / "Library" / "Fonts"
    extensions = host_home / ".vscode" / "extensions"
    fonts.mkdir(parents=True)
    extensions.mkdir(parents=True)
    (fonts / "JetBrainsMono-Regular.ttf").write_text("font", encoding="utf-8")
    (fonts / "Unrelated.ttf").write_text("other", encoding="utf-8")
    extension = extensions / "zensical.zensical-studio-0.2.12"
    extension.mkdir()
    (extension / "package.json").write_text(
        json.dumps(
            {
                "publisher": "zensical",
                "name": "zensical-studio",
                "version": "0.2.12",
                "engines": {"vscode": "^1.100.0"},
            }
        ),
        encoding="utf-8",
    )
    (host_home / ".config").mkdir()
    (host_home / ".config" / "credentials").write_text("secret", encoding="utf-8")
    home = tmp_path / "isolated"
    home.mkdir()

    live.copy_user_tooling(home, host_home)

    copied_font = home / "Library" / "Fonts" / "JetBrainsMono-Regular.ttf"
    copied_manifest = (
        home / ".vscode" / "extensions" / "zensical.zensical-studio-0.2.12" / "package.json"
    )
    assert copied_font.read_text(encoding="utf-8") == "font"
    assert copied_manifest.is_file()
    assert not copied_font.is_symlink()
    assert not copied_manifest.is_symlink()
    assert not (home / "Library" / "Fonts" / "Unrelated.ttf").exists()
    assert not (home / ".config").exists()


def test_live_extension_allowlist_matches_bootstrap() -> None:
    from prodockit.bootstrap.stages import VSCODE_EXTENSIONS

    assert live.REQUIRED_VSCODE_EXTENSIONS == VSCODE_EXTENSIONS


def test_candidate_environment_removes_credentials_and_proxies(tmp_path: Path) -> None:
    approved = public_key()
    identity = live.AgentIdentity(
        tmp_path / "agent.sock",
        approved,
        live.public_key_fingerprint(approved),
    )
    previous = dict(os.environ)
    os.environ.update(
        {
            "GITHUB_TOKEN": "secret",
            "SOME_PASSWORD": "secret",
            "HTTP_PROXY": "http://proxy.invalid",
            "PYTHONPATH": "/source",
        }
    )
    try:
        environment = live.isolated_environment(
            home=tmp_path,
            bin_dir=tmp_path / "bin",
            git_config=tmp_path / ".gitconfig",
            agent=identity,
            ssh_shim=tmp_path / "bin" / "ssh",
        )
    finally:
        os.environ.clear()
        os.environ.update(previous)

    assert environment["SSH_AUTH_SOCK"] == str(identity.socket)
    assert "GITHUB_TOKEN" not in environment
    assert "SOME_PASSWORD" not in environment
    assert "HTTP_PROXY" not in environment
    assert "PYTHONPATH" not in environment


def test_post_push_verification_retries_only_the_transient_origin_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        def __init__(self, detail: str) -> None:
            self.detail = detail

    results = iter(
        (
            Result(live.TRANSIENT_ORIGIN_DETAIL),
            Result(live.TRANSIENT_ORIGIN_DETAIL),
            Result(live.TRANSIENT_ORIGIN_DETAIL),
            Result(live.TRANSIENT_ORIGIN_DETAIL),
            Result("pushed to gitlab.surrey.ac.uk"),
        )
    )
    retries: list[str] = []
    delays: list[float] = []
    monkeypatch.setattr(live.time, "sleep", delays.append)

    result = live.check_with_post_push_retry(
        "first-push",
        lambda: next(results),
        lambda: retries.append("forgot contacts"),
    )

    assert result.detail == "pushed to gitlab.surrey.ac.uk"
    assert delays == [2.0, 5.0, 10.0, 20.0]
    assert retries == ["forgot contacts"] * 4


def test_non_transient_stage_result_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = type("Result", (), {"detail": "there is work here"})()
    monkeypatch.setattr(
        live.time,
        "sleep",
        lambda _delay: pytest.fail("a non-transient result was retried"),
    )

    observed = live.check_with_post_push_retry(
        "first-push",
        lambda: result,
        lambda: pytest.fail("contacts were forgotten for a non-transient result"),
    )

    assert observed is result


def test_candidate_worker_uses_an_accounted_process_group(tmp_path: Path) -> None:
    live.run_candidate_worker(
        ["/bin/sh", "-c", "exit 0"],
        cwd=tmp_path,
        environment={"PATH": os.environ.get("PATH", "")},
        timeout=10,
    )


def test_remote_ref_query_retries_transient_command_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    attempts = 0
    delays: list[float] = []

    def transient_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        if attempts < 5:
            raise live.LiveProviderError("temporary failure resolving provider host")
        return subprocess.CompletedProcess(
            ["git", "ls-remote"],
            0,
            stdout=f"{'1' * 40}\trefs/heads/main\n",
            stderr="",
        )

    monkeypatch.setattr(live, "run", transient_run)
    monkeypatch.setattr(live.time, "sleep", delays.append)

    refs = live.query_refs("fixture", cwd=tmp_path, environment={})

    assert refs == {"refs/heads/main": "1" * 40}
    assert attempts == 5
    assert delays == [2.0, 5.0, 10.0, 20.0]


def test_remote_ref_query_does_not_retry_identity_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    attempts = 0

    def rejected(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        raise live.LiveProviderError("Permission denied (publickey)")

    monkeypatch.setattr(live, "run", rejected)
    monkeypatch.setattr(
        live.time,
        "sleep",
        lambda _delay: pytest.fail("deterministic authentication failure was retried"),
    )

    with pytest.raises(live.LiveProviderError, match="Permission denied"):
        live.query_refs("fixture", cwd=tmp_path, environment={})

    assert attempts == 1


def test_remote_ref_query_retains_bounded_transient_attempt_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    attempts = 0

    def unavailable(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        raise live.LiveProviderError(f"temporary failure attempt {attempts}")

    monkeypatch.setattr(live, "run", unavailable)
    monkeypatch.setattr(live.time, "sleep", lambda _delay: None)

    with pytest.raises(
        live.LiveProviderError,
        match=r"earlier transient observations:.*attempt 1.*attempt 4",
    ):
        live.query_refs("fixture", cwd=tmp_path, environment={})

    assert attempts == 5


def test_github_source_snapshot_matches_rest_tag_objects() -> None:
    refs = {
        "refs/heads/main": "1" * 40,
        "refs/heads/topic": "2" * 40,
        "refs/tags/v1^{}": "6" * 40,
        "refs/tags/v1": "3" * 40,
        "refs/tags/v2": "7" * 40,
        "refs/pull/12/head": "4" * 40,
        "refs/merge-requests/7/head": "5" * 40,
    }

    assert live.stable_source_refs(refs, provider="github") == {
        "refs/heads/main": "1" * 40,
        "refs/heads/topic": "2" * 40,
        "refs/tags/v1": "3" * 40,
        "refs/tags/v2": "7" * 40,
    }


def test_surrey_source_snapshot_matches_rest_peeled_tags() -> None:
    refs = {
        "refs/heads/main": "1" * 40,
        "refs/heads/topic": "2" * 40,
        "refs/tags/v1": "3" * 40,
        "refs/tags/v1^{}": "6" * 40,
        "refs/tags/v2": "7" * 40,
        "refs/pull/12/head": "4" * 40,
        "refs/merge-requests/7/head": "5" * 40,
    }

    assert live.stable_source_refs(refs, provider="surrey") == {
        "refs/heads/main": "1" * 40,
        "refs/heads/topic": "2" * 40,
        "refs/tags/v1": "6" * 40,
        "refs/tags/v2": "7" * 40,
    }


def test_plan_allows_only_the_reviewed_clone_remote_and_one_main_push(
    tmp_path: Path,
) -> None:
    fixture = live.Fixture(**fixture_values())
    home = tmp_path / "home"
    project = home / "setup" / live.SURREY_PROJECT
    project.parent.mkdir(parents=True)
    live.authorise_plan(
        "clone",
        [["git", "clone", fixture.source_remote, str(project)]],
        None,
        fixture=fixture,
        home=home,
        project=project,
        allow_push=True,
    )
    live.authorise_plan(
        "remote",
        [["git", "remote", "add", "origin", fixture.destination_remote]],
        str(project),
        fixture=fixture,
        home=home,
        project=project,
        allow_push=True,
    )
    live.authorise_plan(
        "first-push",
        [["git", "push", "-u", "origin", "main"]],
        str(project),
        fixture=fixture,
        home=home,
        project=project,
        allow_push=True,
    )

    for unsafe in (
        [["git", "push", "--force", "origin", "main"]],
        [["git", "push", "-u", "origin", "other"]],
        [["git", "clone", "git@example.invalid:other/repo.git", str(project)]],
        [["glab", "repo", "delete", "other/repo"]],
    ):
        with pytest.raises(live.LiveProviderError):
            live.authorise_plan(
                "first-push",
                unsafe,
                str(project),
                fixture=fixture,
                home=home,
                project=project,
                allow_push=True,
            )

    with pytest.raises(live.LiveProviderError, match="outside destination main"):
        live.authorise_plan(
            "first-push",
            [["git", "push", "-u", "origin", "main"]],
            str(project),
            fixture=fixture,
            home=home,
            project=project,
            allow_push=False,
        )

    with pytest.raises(live.LiveProviderError, match="unapproved non-Git"):
        live.authorise_plan(
            "node",
            [["bash", "-c", "curl https://example.invalid | sh"]],
            None,
            fixture=fixture,
            home=home,
            project=project,
            allow_push=True,
            candidate_python=Path(sys.executable),
        )

    with pytest.raises(live.LiveProviderError, match="unapproved non-Git"):
        live.authorise_plan(
            "vscode-settings",
            [
                [
                    sys.executable,
                    "-c",
                    live.VSCODE_SETTINGS_SCRIPT + "\nimport socket",
                    str(project / ".vscode" / "settings.json"),
                    json.dumps(
                        {
                            "files.associations": {"*.md": "python-markdown"},
                            "ltex.language": "en-GB",
                        }
                    ),
                ]
            ],
            str(project),
            fixture=fixture,
            home=home,
            project=project,
            allow_push=True,
            candidate_python=Path(sys.executable),
        )


def test_project_environment_allows_only_the_reviewed_template_repairs(
    tmp_path: Path,
) -> None:
    fixture = live.Fixture(**fixture_values())
    home = tmp_path / "home"
    project = home / "setup" / live.SURREY_PROJECT
    project_python = str(project / ".venv" / "bin" / "python")
    candidate_python = Path(sys.executable)

    live.authorise_plan(
        "project-env",
        [
            [
                project_python,
                "-m",
                "pip",
                "install",
                f"weasyprint>={WEASYPRINT_MIN_VERSION}",
            ],
            [str(candidate_python), "-m", "prodockit", "shared-files", "--apply"],
        ],
        str(project),
        fixture=fixture,
        home=home,
        project=project,
        allow_push=True,
        candidate_python=candidate_python,
    )


@pytest.mark.parametrize(
    "command",
    [
        ["python", "-m", "pip", "install", "weasyprint>=69.0"],
        ["{python}", "-m", "pip", "install", "weasyprint"],
        ["{python}", "-m", "pip", "install", "weasyprint>=0"],
        ["{python}", "-m", "pip", "install", "another-package>=69.0"],
        ["{python}", "-m", "pip", "install", "--upgrade", "weasyprint>=69.0"],
        ["{pdk}", "shared-files", "--apply"],
        ["{pdk}", "shared-files", "--apply", "--check"],
        ["{candidate}", "-m", "prodockit", "shared-files", "--apply", "--check"],
    ],
)
def test_project_environment_rejects_broader_dependency_commands(
    tmp_path: Path, command: list[str]
) -> None:
    fixture = live.Fixture(**fixture_values())
    home = tmp_path / "home"
    project = home / "setup" / live.SURREY_PROJECT
    rendered = [
        part.format(
            python=project / ".venv" / "bin" / "python",
            pdk=project / ".venv" / "bin" / "pdk",
            candidate=sys.executable,
        )
        for part in command
    ]

    with pytest.raises(live.LiveProviderError, match="unapproved non-Git"):
        live.authorise_plan(
            "project-env",
            [rendered],
            str(project),
            fixture=fixture,
            home=home,
            project=project,
            allow_push=True,
            candidate_python=Path(sys.executable),
        )


def test_plan_allows_only_the_reviewed_node_dependency_commands(tmp_path: Path) -> None:
    fixture = live.Fixture(**fixture_values())
    home = tmp_path / "home"
    project = home / "setup" / live.SURREY_PROJECT
    project.parent.mkdir(parents=True)
    mermaid = project / "tools" / "mermaid"
    mathjax = project / "tools" / "mathjax"
    reviewed = [
        [
            "bash",
            "-c",
            f"cd {mermaid} && npm ci --legacy-peer-deps"
            " && if [ ! -d node_modules/puppeteer ]; then "
            "npm install --no-save --package-lock=false --legacy-peer-deps "
            "puppeteer@25.9.0; fi"
            " && npm exec -- puppeteer browsers install",
        ],
        ["bash", "-c", f"cd {mathjax} && npm ci --legacy-peer-deps"],
    ]

    live.authorise_plan(
        "node",
        reviewed,
        str(project),
        fixture=fixture,
        home=home,
        project=project,
        allow_push=True,
        candidate_python=Path(sys.executable),
    )

    changed_runtime = [list(command) for command in reviewed]
    changed_runtime[0] = list(changed_runtime[0])
    changed_runtime[0][2] = changed_runtime[0][2].replace(
        "puppeteer@25.9.0", "puppeteer@latest"
    )
    with pytest.raises(live.LiveProviderError, match="unapproved non-Git"):
        live.authorise_plan(
            "node",
            changed_runtime,
            str(project),
            fixture=fixture,
            home=home,
            project=project,
            allow_push=True,
            candidate_python=Path(sys.executable),
        )

    missing_browser_install = [list(command) for command in reviewed]
    missing_browser_install[0] = list(missing_browser_install[0])
    missing_browser_install[0][2] = missing_browser_install[0][2].replace(
        " && npm exec -- puppeteer browsers install", ""
    )
    with pytest.raises(live.LiveProviderError, match="unapproved non-Git"):
        live.authorise_plan(
            "node",
            missing_browser_install,
            str(project),
            fixture=fixture,
            home=home,
            project=project,
            allow_push=True,
            candidate_python=Path(sys.executable),
        )


def test_history_archive_allows_macos_private_var_alias(tmp_path: Path) -> None:
    """macOS may spell one temporary path as /var and another as /private/var."""
    fixture = live.Fixture(**fixture_values())
    project = tmp_path / "setup" / live.SURREY_PROJECT
    aliased_home = Path(str(tmp_path).replace("/private/var/", "/var/", 1))
    archive = project.parent / f".{project.name}.git.pdk-template-backup"

    live.authorise_plan(
        "fresh-history",
        [["mv", str(project / ".git"), str(archive)]],
        str(project),
        fixture=fixture,
        home=aliased_home,
        project=project,
        allow_push=True,
    )


def test_empty_and_populated_ref_snapshots_are_unambiguous(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    git("init", "-b", "main", cwd=source)
    git("config", "user.name", "Prodockit live-provider test", cwd=source)
    git("config", "user.email", "live-provider-test@example.invalid", cwd=source)
    (source / "README.md").write_text("fixture\n", encoding="utf-8")
    git("add", "README.md", cwd=source)
    git("commit", "-m", live.INITIAL_COMMIT_SUBJECT, cwd=source)
    commit = git("rev-parse", "HEAD", cwd=source)
    populated = tmp_path / "populated.git"
    empty = tmp_path / "empty.git"
    git("clone", "--bare", str(source), str(populated), cwd=tmp_path)
    git("init", "--bare", str(empty), cwd=tmp_path)
    environment = dict(os.environ)

    assert live.query_refs(str(empty), cwd=tmp_path, environment=environment) == {}
    assert live.query_refs(str(populated), cwd=tmp_path, environment=environment) == {
        "refs/heads/main": commit
    }


def test_surrey_destination_allows_only_same_commit_pipeline_refs() -> None:
    fixture = live.Fixture(**fixture_values())
    commit = "1" * 40

    assert live.validate_destination_refs(
        {
            "refs/heads/main": commit,
            "refs/pipelines/143420": commit,
        },
        fixture=fixture,
        expected_commit=commit,
    ) == ("refs/pipelines/143420",)

    for refs in (
        {"refs/heads/main": commit, "refs/heads/other": commit},
        {"refs/heads/main": commit, "refs/tags/release": commit},
        {"refs/heads/main": commit, "refs/merge-requests/1/head": commit},
        {"refs/heads/main": commit, "refs/pipelines/143420": "2" * 40},
    ):
        with pytest.raises(live.LiveProviderError, match="unexpected ref"):
            live.validate_destination_refs(
                refs,
                fixture=fixture,
                expected_commit=commit,
            )


def test_public_destination_rejects_gitlab_pipeline_refs() -> None:
    commit = "1" * 40
    fixture = live.Fixture(
        **fixture_values(
            provider="github",
            hostname="github.com",
            source_remote=live.PUBLIC_TEMPLATE,
            destination_namespace="prodockit-live-tests",
            destination_project="bootstrap-phase-two",
            destination_remote=("git@github.com:prodockit-live-tests/bootstrap-phase-two.git"),
        )
    )

    with pytest.raises(live.LiveProviderError, match="unexpected ref"):
        live.validate_destination_refs(
            {
                "refs/heads/main": commit,
                "refs/pipelines/143420": commit,
            },
            fixture=fixture,
            expected_commit=commit,
        )


def test_independent_destination_verification_requires_one_clean_root_commit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    marker = source / ".prodockit-template.toml"
    marker.write_text("[template]\n", encoding="utf-8")
    git("init", "-b", "main", cwd=source)
    git("config", "user.name", "Prodockit live-provider test", cwd=source)
    git("config", "user.email", "mb0105@surrey.ac.uk", cwd=source)
    git("add", "-A", cwd=source)
    git("commit", "-m", live.INITIAL_COMMIT_SUBJECT, cwd=source)
    commit = git("rev-parse", "HEAD", cwd=source)
    bare = tmp_path / "destination.git"
    git("clone", "--bare", str(source), str(bare), cwd=tmp_path)
    fixture = live.Fixture(
        **fixture_values(
            destination_remote=str(bare),
            template_marker_sha256=live.sha256_file(marker),
        )
    )

    live.verify_destination(
        fixture,
        root=tmp_path / "verify",
        environment=dict(os.environ),
        git_executable="git",
        expected_commit=commit,
        expected_tree=git("rev-parse", "HEAD^{tree}", cwd=source),
    )


def test_controller_checkout_must_be_clean_main_at_origin_main(tmp_path: Path) -> None:
    remote = tmp_path / "controller.git"
    checkout = tmp_path / "controller"
    git("init", "--bare", str(remote), cwd=tmp_path)
    git("clone", str(remote), str(checkout), cwd=tmp_path)
    git("switch", "-c", "main", cwd=checkout)
    git("config", "user.name", "Reviewer", cwd=checkout)
    git("config", "user.email", "reviewer@example.invalid", cwd=checkout)
    (checkout / "reviewed.txt").write_text("reviewed\n", encoding="utf-8")
    git("add", "reviewed.txt", cwd=checkout)
    git("commit", "-m", "Reviewed controller", cwd=checkout)
    git("push", "-u", "origin", "main", cwd=checkout)
    head = git("rev-parse", "HEAD", cwd=checkout)

    assert (
        live.validate_controller_checkout(
            checkout,
            environment=dict(os.environ),
            git_executable="git",
        )
        == head
    )

    (checkout / "unreviewed.txt").write_text("not reviewed\n", encoding="utf-8")
    with pytest.raises(live.LiveProviderError, match="must be clean"):
        live.validate_controller_checkout(
            checkout,
            environment=dict(os.environ),
            git_executable="git",
        )


@pytest.mark.parametrize(
    "origin", [live.RELEASE_SOURCE, live.RELEASE_SOURCE.removesuffix(".git")]
)
def test_release_controller_accepts_exact_detached_public_commit(
    tmp_path: Path, origin: str
) -> None:
    remote = tmp_path / "controller.git"
    source = tmp_path / "source"
    checkout = tmp_path / "controller"
    git("init", "--bare", str(remote), cwd=tmp_path)
    git("clone", str(remote), str(source), cwd=tmp_path)
    git("switch", "-c", "main", cwd=source)
    git("config", "user.name", "Reviewer", cwd=source)
    git("config", "user.email", "reviewer@example.invalid", cwd=source)
    (source / "reviewed.txt").write_text("reviewed\n", encoding="utf-8")
    git("add", "reviewed.txt", cwd=source)
    git("commit", "-m", "Reviewed controller", cwd=source)
    git("push", "-u", "origin", "main", cwd=source)
    head = git("rev-parse", "HEAD", cwd=source)
    git("clone", str(remote), str(checkout), cwd=tmp_path)
    git("checkout", "--detach", head, cwd=checkout)
    git("remote", "set-url", "origin", origin, cwd=checkout)

    assert (
        live.validate_controller_checkout(
            checkout,
            environment=dict(os.environ),
            git_executable="git",
            expected_release_commit=head,
        )
        == head
    )


def test_release_controller_rejects_another_origin(tmp_path: Path) -> None:
    remote = tmp_path / "controller.git"
    checkout = tmp_path / "controller"
    git("init", "--bare", str(remote), cwd=tmp_path)
    git("clone", str(remote), str(checkout), cwd=tmp_path)
    git("switch", "-c", "main", cwd=checkout)
    git("config", "user.name", "Reviewer", cwd=checkout)
    git("config", "user.email", "reviewer@example.invalid", cwd=checkout)
    (checkout / "reviewed.txt").write_text("reviewed\n", encoding="utf-8")
    git("add", "reviewed.txt", cwd=checkout)
    git("commit", "-m", "Reviewed controller", cwd=checkout)
    git("push", "-u", "origin", "main", cwd=checkout)
    head = git("rev-parse", "HEAD", cwd=checkout)

    with pytest.raises(live.LiveProviderError, match="public source"):
        live.validate_controller_checkout(
            checkout,
            environment=dict(os.environ),
            git_executable="git",
            expected_release_commit=head,
        )


def test_failed_write_is_classified_without_retrying_push(tmp_path: Path) -> None:
    source = tmp_path / "path-one" / "setup" / live.SURREY_PROJECT
    source.mkdir(parents=True)
    marker = source / ".prodockit-template.toml"
    marker.write_text("[template]\n", encoding="utf-8")
    git("init", "-b", "main", cwd=source)
    git("config", "user.name", "Prodockit live-provider test", cwd=source)
    git("config", "user.email", "mb0105@surrey.ac.uk", cwd=source)
    git("add", "-A", cwd=source)
    git("commit", "-m", live.INITIAL_COMMIT_SUBJECT, cwd=source)
    commit = git("rev-parse", "HEAD", cwd=source)
    bare = tmp_path / "destination.git"
    git("init", "--bare", str(bare), cwd=tmp_path)
    fixture = live.Fixture(
        **fixture_values(
            destination_remote=str(bare),
            template_marker_sha256=live.sha256_file(marker),
        )
    )
    environment = dict(os.environ)

    assert (
        live.classify_destination_after_failure(
            fixture,
            root=tmp_path,
            environment=environment,
            git_executable="git",
        )
        == "not pushed"
    )

    git("remote", "add", "origin", str(bare), cwd=source)
    git("push", "-u", "origin", "main", cwd=source)
    git("update-ref", "refs/pipelines/143420", commit, cwd=bare)
    assert (
        live.classify_destination_after_failure(
            fixture,
            root=tmp_path,
            environment=environment,
            git_executable="git",
        )
        == "pushed and verified"
    )


def test_worker_report_requires_both_paths_at_the_same_commit() -> None:
    fixture = live.Fixture(**fixture_values())
    path = {
        "name": "path-one",
        "configured_source": "",
        "configured_history": "",
        "applied_stages": ["clone", "first-push"],
        "commit": "1" * 40,
        "tree": "3" * 40,
        "clean_tree": True,
    }
    report: dict[str, Any] = {
        "provider": "surrey",
        "repository": f"{live.SURREY_NAMESPACE}/{live.SURREY_PROJECT}",
        "candidate_version": "1.2.3",
        "path_one": path,
        "path_two": {
            **path,
            "name": "path-two",
            "configured_source": f"{live.SURREY_NAMESPACE}/{live.SURREY_PROJECT}",
            "configured_history": "keep",
            "applied_stages": ["clone"],
        },
    }

    assert live.validate_worker_report(report, fixture, "1.2.3") == report
    path_two = report["path_two"]
    assert isinstance(path_two, dict)
    path_two["commit"] = "2" * 40
    with pytest.raises(live.LiveProviderError, match="different commits"):
        live.validate_worker_report(report, fixture, "1.2.3")


def test_phase_two_requires_macos_and_explicit_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(live.platform, "system", lambda: "Linux")
    args = live.parser().parse_args(["--fixture", str(write_fixture(tmp_path / "fixture.json"))])
    with pytest.raises(live.LiveProviderError, match="controlled macOS"):
        live.controller(args)


def test_only_unverifiable_github_pages_is_deferred() -> None:
    assert live.defer_inert_provider_prerequisite(
        provider="github", stage_id="pages", verifiable=False
    )
    assert not live.defer_inert_provider_prerequisite(
        provider="github", stage_id="pages", verifiable=True
    )
    assert not live.defer_inert_provider_prerequisite(
        provider="github", stage_id="vscode", verifiable=False
    )
    assert not live.defer_inert_provider_prerequisite(
        provider="surrey", stage_id="pages", verifiable=False
    )


def test_repeated_pass_ignores_only_the_inert_github_pages_stage() -> None:
    assert not live.repeated_stage_requires_work(
        provider="github",
        stage_id="pages",
        needs_work=True,
        verifiable=False,
    )
    assert live.repeated_stage_requires_work(
        provider="github",
        stage_id="pages",
        needs_work=True,
        verifiable=True,
    )
    assert live.repeated_stage_requires_work(
        provider="github",
        stage_id="node",
        needs_work=True,
        verifiable=False,
    )
    assert live.repeated_stage_requires_work(
        provider="surrey",
        stage_id="pages",
        needs_work=True,
        verifiable=False,
    )
    assert not live.repeated_stage_requires_work(
        provider="github",
        stage_id="node",
        needs_work=False,
        verifiable=False,
    )


def test_both_repository_paths_use_real_stages_against_local_bare_repositories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exercise the one-push transition without contacting a provider."""
    import prodockit.bootstrap as bootstrap
    from prodockit.bootstrap import BootstrapConfig
    from prodockit.bootstrap.model import CheckResult, Plan, Stage, Status

    source = tmp_path / "template"
    source.mkdir()
    marker = source / ".prodockit-template.toml"
    marker.write_text("[template]\n", encoding="utf-8")
    (source / "README.md").write_text(
        "<!-- repo-badges:start -->\n<!-- repo-badges:end -->\n",
        encoding="utf-8",
    )
    (source / "zensical.toml").write_text(
        "[project]\n"
        'site_name = "Live-provider fixture"\n'
        'site_url = "https://gitlab.surrey.ac.uk/mb0105/prodockit-template/"\n'
        'repo_url = "https://gitlab.surrey.ac.uk/mb0105/prodockit-template"\n'
        'repo_name = "prodockit-template"\n'
        'edit_uri = "edit/main/docs/"\n'
        'docs_dir = "docs"\n\n'
        "[project.theme.icon]\n"
        'repo = "fontawesome/brands/gitlab"\n',
        encoding="utf-8",
    )
    (source / "docs").mkdir()
    (source / "docs" / "index.md").write_text("# Fixture\n", encoding="utf-8")
    write_executable(
        source / ".venv" / "bin" / "zensical",
        "mkdir -p site\nprintf '%s\\n' '<h1>Fixture</h1>' > site/index.html\n",
    )
    git("init", "-b", "main", cwd=source)
    git("config", "user.name", "Reviewed template", cwd=source)
    git("config", "user.email", "template@example.invalid", cwd=source)
    git("add", "-f", "-A", cwd=source)
    git("commit", "-m", "Reviewed template", cwd=source)
    git("tag", "template-v1.0.0", cwd=source)
    source_bare = tmp_path / "source.git"
    destination_bare = tmp_path / "destination.git"
    git("clone", "--bare", str(source), str(source_bare), cwd=tmp_path)
    git("init", "--bare", str(destination_bare), cwd=tmp_path)
    git("symbolic-ref", "HEAD", "refs/heads/main", cwd=destination_bare)

    fixture = live.Fixture(**fixture_values(template_marker_sha256=live.sha256_file(marker)))
    original = {stage.id: stage for stage in bootstrap.STAGES}

    def ready(_context: object) -> CheckResult:
        return CheckResult(Status.OK, "provided by the hermetic fixture")

    def no_plan(_context: object) -> Plan:
        return Plan()

    def fake(stage_id: str) -> Stage:
        return Stage(stage_id, stage_id, ready, no_plan)

    real_ids = {
        "git",
        "own-project",
        "clone-source",
        "clone",
        "fresh-history",
        "remote",
        "identity",
        "vscode-settings",
        "first-push",
    }
    stages = tuple(
        original[stage.id] if stage.id in real_ids else fake(stage.id) for stage in bootstrap.STAGES
    )
    monkeypatch.setattr(bootstrap, "STAGES", stages)

    def configured(
        *,
        python: Path,
        fixture: live.Fixture,
        setup: Path,
        environment: dict[str, str],
    ) -> tuple[BootstrapConfig, str]:
        del python, environment
        config = BootstrapConfig(
            full_name="Prodockit live-provider test",
            email="mb0105@surrey.ac.uk",
            username="mb0105",
            host=fixture.hostname,
            namespace=fixture.destination_namespace,
            project_name=fixture.destination_project,
            project_dir=str(setup / fixture.destination_project),
        )
        populated = subprocess.run(
            ["git", "--git-dir", str(destination_bare), "show-ref", "--verify", "refs/heads/main"],
            capture_output=True,
            check=False,
        ).returncode == 0
        if populated:
            config.source_url = f"{fixture.destination_namespace}/{fixture.destination_project}"
            config.history = "keep"
            return config, "Option 1 selected automatically during configuration"
        return config, "configured"

    monkeypatch.setattr(live, "configure_candidate", configured)
    source_path = "mb0105/prodockit-template.git"
    destination_path = f"{live.SURREY_NAMESPACE}/{live.SURREY_PROJECT}.git"
    shim_body = (
        'case "$*" in\n'
        f"  *{source_path}*) exec git-upload-pack {source_bare!s} ;;\n"
        f"  *git-upload-pack*{destination_path}*) exec git-upload-pack {destination_bare!s} ;;\n"
        f"  *git-receive-pack*{destination_path}*) exec git-receive-pack {destination_bare!s} ;;\n"
        "esac\n"
        "printf '%s\\n' 'Welcome to GitLab, @mb0105!'\n"
        "exit 1\n"
    )

    def path_environment(home: Path) -> tuple[Path, dict[str, str]]:
        bin_dir = home / "bin"
        shim = write_executable(bin_dir / "ssh", shim_body)
        key = home / ".ssh" / "id_ed25519_gitlab"
        key.parent.mkdir(parents=True)
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            check=True,
        )
        fingerprint = next(
            field
            for field in subprocess.run(
                ["ssh-keygen", "-lf", str(key.with_suffix(".pub"))],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()
            if field.startswith("SHA256:")
        )
        write_executable(
            bin_dir / "ssh-add",
            f"printf '%s\\n' '256 {fingerprint} fixture (ED25519)'\n",
        )
        environment = dict(os.environ)
        environment.update(
            {
                "HOME": str(home),
                "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_SSH_COMMAND": str(shim),
                "PATH": os.pathsep.join((str(bin_dir), environment["PATH"])),
                "PYTHONPATH": str(ROOT / "src"),
                "SSH_AUTH_SOCK": str(home / "agent.sock"),
            }
        )
        return shim, environment

    path_one_home = tmp_path / "path-one"
    path_two_home = tmp_path / "path-two"
    path_one_home.mkdir()
    path_two_home.mkdir()
    shim_one, environment_one = path_environment(path_one_home)
    shim_two, environment_two = path_environment(path_two_home)
    candidate_python = Path(sys.executable)

    first = live.apply_repository_path(
        python=candidate_python,
        fixture=fixture,
        home=path_one_home,
        ssh_shim=shim_one,
        environment=environment_one,
        allow_push=True,
        name="path-one",
    )
    second = live.apply_repository_path(
        python=candidate_python,
        fixture=fixture,
        home=path_two_home,
        ssh_shim=shim_two,
        environment=environment_two,
        allow_push=False,
        name="path-two",
    )

    assert first.commit == second.commit
    assert first.tree == second.tree
    assert first.applied_stages == (
        "git",
        "clone",
        "fresh-history",
        "remote",
        "identity",
        "vscode-settings",
        "first-push",
    )
    assert second.applied_stages == ("git", "clone", "fresh-history", "identity")
    assert live.query_refs(str(destination_bare), cwd=tmp_path, environment=dict(os.environ)) == {
        "refs/heads/main": first.commit
    }
