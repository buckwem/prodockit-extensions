# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Safety tests for the manually authorised live-provider harness."""

from __future__ import annotations

import base64
import importlib
import json
import os
import subprocess
import sys
import zipfile
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
live = importlib.import_module("tools.bootstrap_live_provider_read_only")

MARKER_DIGEST = "a" * 64


def fixture_values(**updates: str) -> dict[str, str]:
    values = {
        "provider": "surrey",
        "hostname": live.SURREY_HOSTNAME,
        "namespace": live.SURREY_NAMESPACE,
        "project": live.SURREY_PROJECT,
        "remote": live.SURREY_REMOTE,
        "marker_path": ".prodockit-live-provider-fixture.json",
        "marker_sha256": MARKER_DIGEST,
    }
    values.update(updates)
    return values


def write_fixture(path: Path, **updates: str) -> Path:
    path.write_text(json.dumps(fixture_values(**updates)), encoding="utf-8")
    return path


def write_wheel(path: Path, *, version: str = "1.2.3") -> Path:
    metadata = f"Metadata-Version: 2.1\nName: prodockit\nVersion: {version}\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"prodockit-{version}.dist-info/METADATA", metadata)
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


def write_executable(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o700)
    return path


def test_surrey_fixture_is_the_exact_bootstrap_derivation(tmp_path: Path) -> None:
    fixture = live.Fixture.read(write_fixture(tmp_path / "fixture.json"))

    assert fixture.namespace == "assessment-liveprovider-2026"
    assert fixture.project == "report-liveprovider-2026-mb0105"
    assert fixture.remote == (
        "git@gitlab.surrey.ac.uk:"
        "assessment-liveprovider-2026/report-liveprovider-2026-mb0105.git"
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("namespace", "assessment-other-2026", "must be exactly"),
        ("project", "report-liveprovider-2026-other", "must be exactly"),
        ("hostname", "gitlab.com", "must use gitlab.surrey.ac.uk"),
        ("remote", "git@gitlab.surrey.ac.uk:wrong/project.git", "must be exactly"),
        ("marker_path", "../secret", "relative path"),
        ("marker_sha256", "short", "64 lowercase"),
    ],
)
def test_surrey_fixture_fails_closed(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    with pytest.raises(live.LiveProviderError, match=message):
        live.Fixture.read(write_fixture(tmp_path / "fixture.json", **{field: value}))


def test_surrey_rejects_a_self_consistent_but_wrong_derived_destination(
    tmp_path: Path,
) -> None:
    namespace = "assessment-other-2026"
    project = "report-other-2026-mb0105"
    with pytest.raises(live.LiveProviderError, match="account mb0105"):
        live.Fixture.read(
            write_fixture(
                tmp_path / "fixture.json",
                namespace=namespace,
                project=project,
                remote=f"git@gitlab.surrey.ac.uk:{namespace}/{project}.git",
            )
        )


def test_github_fixture_is_explicitly_allowlisted(tmp_path: Path) -> None:
    fixture = live.Fixture.read(
        write_fixture(
            tmp_path / "fixture.json",
            provider="github",
            hostname="github.com",
            namespace="prodockit-live-tests",
            project="bootstrap-existing",
            remote="git@github.com:prodockit-live-tests/bootstrap-existing.git",
        )
    )

    assert fixture.remote == "git@github.com:prodockit-live-tests/bootstrap-existing.git"


def test_fixture_rejects_unknown_or_missing_fields(tmp_path: Path) -> None:
    values = fixture_values()
    values.pop("project")
    values["token"] = "must-never-exist"
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(values), encoding="utf-8")

    with pytest.raises(live.LiveProviderError, match="missing project; unknown token"):
        live.Fixture.read(path)


def test_wheel_digest_filename_and_metadata_must_all_agree(tmp_path: Path) -> None:
    wheel = write_wheel(tmp_path / "prodockit-1.2.3-py3-none-any.whl")
    digest = live.sha256_file(wheel)

    assert live.inspect_wheel(wheel, digest) == live.WheelInfo(wheel.resolve(), "1.2.3", digest)

    with pytest.raises(live.LiveProviderError, match="SHA-256 is"):
        live.inspect_wheel(wheel, "0" * 64)

    wrongly_named = write_wheel(tmp_path / "prodockit-9.9.9-py3-none-any.whl")
    with pytest.raises(live.LiveProviderError, match="does not match embedded version"):
        live.inspect_wheel(wrongly_named, live.sha256_file(wrongly_named))


def test_non_prodockit_wheel_is_rejected(tmp_path: Path) -> None:
    wheel = tmp_path / "prodockit-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "other-1.2.3.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: other\nVersion: 1.2.3\n",
        )

    with pytest.raises(live.LiveProviderError, match="candidate metadata is other"):
        live.inspect_wheel(wheel, live.sha256_file(wheel))


def agent_public_key(
    comment: str = "prodockit-liveprovider-deploy-key",
    payload: bytes = b"prodockit live-provider fixture key",
) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"ssh-ed25519 {encoded} {comment}"


def test_agent_identity_selects_one_approved_ed25519_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    agent_socket = tmp_path / "agent.sock"
    public_key = agent_public_key()
    fingerprint = live.public_key_fingerprint(public_key)
    monkeypatch.setattr(live, "validate_agent_socket", lambda path: path.resolve())
    monkeypatch.setattr(live.shutil, "which", lambda _name: "/usr/bin/ssh-add")
    result = live.subprocess.CompletedProcess([], 0, public_key + "\n", "")
    monkeypatch.setattr(live.subprocess, "run", lambda *_args, **_kwargs: result)

    assert live.select_agent_identity(agent_socket, fingerprint) == live.AgentIdentity(
        socket=agent_socket.resolve(),
        public_key=public_key,
        fingerprint=fingerprint,
    )

    with pytest.raises(live.LiveProviderError, match="does not expose exactly one"):
        live.select_agent_identity(agent_socket, "SHA256:" + "A" * 43)


def test_agent_identity_accepts_unrelated_keys_but_rejects_missing_or_duplicate_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    agent_socket = tmp_path / "agent.sock"
    public_key = agent_public_key()
    fingerprint = live.public_key_fingerprint(public_key)
    monkeypatch.setattr(live, "validate_agent_socket", lambda path: path.resolve())
    monkeypatch.setattr(live.shutil, "which", lambda _name: "/usr/bin/ssh-add")

    with_unrelated = live.subprocess.CompletedProcess(
        [],
        0,
        f"{public_key}\n{agent_public_key('other', b'unrelated agent key')}\n",
        "",
    )
    monkeypatch.setattr(live.subprocess, "run", lambda *_args, **_kwargs: with_unrelated)
    selected = live.select_agent_identity(agent_socket, fingerprint)
    assert selected.public_key == public_key

    duplicate_match = live.subprocess.CompletedProcess(
        [], 0, f"{public_key}\n{agent_public_key('same-key-different-comment')}\n", ""
    )
    monkeypatch.setattr(live.subprocess, "run", lambda *_args, **_kwargs: duplicate_match)
    with pytest.raises(live.LiveProviderError, match="exactly one identity matching"):
        live.select_agent_identity(agent_socket, fingerprint)

    malformed = live.subprocess.CompletedProcess([], 0, "ssh-rsa not-base64\n", "")
    monkeypatch.setattr(live.subprocess, "run", lambda *_args, **_kwargs: malformed)
    with pytest.raises(live.LiveProviderError, match="does not expose exactly one"):
        live.select_agent_identity(agent_socket, fingerprint)


def test_agent_socket_must_be_a_socket(tmp_path: Path) -> None:
    ordinary_file = tmp_path / "not-a-socket"
    ordinary_file.write_text("not a socket\n", encoding="utf-8")

    with pytest.raises(live.LiveProviderError, match="must name an SSH agent socket"):
        live.validate_agent_socket(ordinary_file)


def test_ssh_configuration_quotes_paths_with_spaces() -> None:
    assert live.ssh_config_path(Path("/Library/Group Containers/agent.sock")) == (
        '"/Library/Group Containers/agent.sock"'
    )


def test_known_hosts_accepts_only_the_exact_selected_provider(tmp_path: Path) -> None:
    accepted = tmp_path / "known-hosts"
    accepted.write_text(
        "gitlab.surrey.ac.uk ssh-ed25519 AAAAC3fixture\n", encoding="utf-8"
    )
    assert live.validate_known_hosts(accepted, live.SURREY_HOSTNAME) == accepted.resolve()

    for value in (
        "* ssh-ed25519 AAAAC3fixture\n",
        "|1|hashed|host ssh-ed25519 AAAAC3fixture\n",
        "github.com ssh-ed25519 AAAAC3fixture\n",
        "gitlab.surrey.ac.uk,github.com ssh-ed25519 AAAAC3fixture\n",
    ):
        accepted.write_text(value, encoding="utf-8")
        with pytest.raises(live.LiveProviderError, match="exact selected provider"):
            live.validate_known_hosts(accepted, live.SURREY_HOSTNAME)


def test_fixture_host_allowlist_and_report_stay_out_of_synced_source(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    safe = tmp_path / "private" / "fixture.json"
    safe.parent.mkdir()
    safe.write_text("{}", encoding="utf-8")

    assert (
        live.private_metadata_path(
            safe,
            label="fixture allowlist",
            checkout=checkout,
            must_exist=True,
        )
        == safe.resolve()
    )
    for unsafe in (checkout / "fixture.json", tmp_path / "OneDrive" / "report.json"):
        unsafe.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(live.LiveProviderError, match="outside the source checkout"):
            live.private_metadata_path(
                unsafe,
                label="retained report",
                checkout=checkout,
                must_exist=False,
            )


def test_refs_parser_requires_complete_object_ids_and_names() -> None:
    refs = live.parse_refs(
        f"{'1' * 40}\trefs/heads/main\n{'2' * 40}\trefs/tags/v1.0\n"
    )
    assert refs == {"refs/heads/main": "1" * 40, "refs/tags/v1.0": "2" * 40}

    with pytest.raises(live.LiveProviderError, match="unexpected ls-remote"):
        live.parse_refs("short refs/heads/main\n")


def test_remote_refs_are_rechecked_after_a_failed_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = live.Fixture(**fixture_values())
    refs = {"refs/heads/main": "1" * 40}
    calls: list[str] = []

    def observed_refs(*_args: object, **_kwargs: object) -> dict[str, str]:
        calls.append("checked")
        return refs

    monkeypatch.setattr(live, "remote_refs", observed_refs)

    with pytest.raises(RuntimeError, match="stage failed"), live.unchanged_remote_refs(
        fixture,
        expected_head="1" * 40,
        cwd=tmp_path,
        environment={},
    ):
        raise RuntimeError("stage failed")

    assert calls == ["checked", "checked"]


def test_remote_ref_change_after_failure_takes_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = live.Fixture(**fixture_values())
    observations = iter(
        (
            {"refs/heads/main": "1" * 40},
            {"refs/heads/main": "2" * 40},
        )
    )
    monkeypatch.setattr(live, "remote_refs", lambda *_args, **_kwargs: next(observations))

    with pytest.raises(
        live.LiveProviderError, match="provider refs changed"
    ), live.unchanged_remote_refs(
        fixture,
        expected_head="1" * 40,
        cwd=tmp_path,
        environment={},
    ):
        raise RuntimeError("stage failed")


def test_remote_ref_recheck_failure_is_inconclusive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = live.Fixture(**fixture_values())
    calls = 0

    def observed_refs(*_args: object, **_kwargs: object) -> dict[str, str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise live.LiveProviderError("provider unavailable")
        return {"refs/heads/main": "1" * 40}

    monkeypatch.setattr(live, "remote_refs", observed_refs)

    with pytest.raises(
        live.LiveProviderError, match="could not verify provider refs"
    ), live.unchanged_remote_refs(
        fixture,
        expected_head="1" * 40,
        cwd=tmp_path,
        environment={},
    ):
        pass


def test_only_clone_and_local_filemode_plans_are_authorised(tmp_path: Path) -> None:
    fixture = live.Fixture(**fixture_values())
    project = tmp_path / fixture.project

    live.authorised_plan(
        "clone", [["/usr/bin/git", "clone", fixture.remote, str(project)]], None, fixture, project
    )
    live.authorised_plan(
        "fresh-history",
        [["git", "config", "core.fileMode", "false"]],
        str(project),
        fixture,
        project,
    )

    forbidden = (
        ("clone", [["git", "clone", fixture.remote, str(project), "--mirror"]], None),
        ("fresh-history", [["git", "push", "origin", "main"]], str(project)),
        ("remote", [["prodockit", "sync-repo"]], str(project)),
        ("clone", [["bash", "-c", "git clone something"]], None),
    )
    for stage, commands, cwd in forbidden:
        with pytest.raises(live.LiveProviderError, match="outside phase one"):
            live.authorised_plan(stage, commands, cwd, fixture, project)


def test_isolated_environment_replaces_agents_and_removes_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in live.SECRET_ENVIRONMENT_NAMES:
        monkeypatch.setenv(name, f"inherited-{name}")
    monkeypatch.setenv("PYTHONPATH", "/source/checkout")
    monkeypatch.setenv("PATH", "/system/bin")
    agent_identity = live.AgentIdentity(
        socket=tmp_path / "agent.sock",
        public_key=agent_public_key(),
        fingerprint=live.public_key_fingerprint(agent_public_key()),
    )

    environment = live.isolated_environment(
        home=tmp_path,
        bin_dir=tmp_path / "bin",
        git_config=tmp_path / ".gitconfig",
        agent_identity=agent_identity,
        ssh_shim=tmp_path / "bin" / "ssh",
    )

    assert environment["SSH_AUTH_SOCK"] == str(agent_identity.socket)
    assert "SSH_AGENT_PID" not in environment
    assert environment["GIT_SSH_COMMAND"].startswith(str(tmp_path / "bin" / "ssh"))
    assert "StrictHostKeyChecking=yes" in environment["GIT_SSH_COMMAND"]
    assert "PYTHONPATH" not in environment
    for name in live.SECRET_ENVIRONMENT_NAMES - {
        "GIT_SSH_COMMAND",
        "SSH_AGENT_PID",
        "SSH_AUTH_SOCK",
    }:
        assert name not in environment


def test_selected_stages_are_stable_keys_not_positions() -> None:
    assert live.SELECTED_STAGE_IDS == (
        "ssh-upload",
        "own-project",
        "clone-source",
        "clone",
        "fresh-history",
        "remote",
    )


def test_retained_stage_detail_redacts_temporary_home(tmp_path: Path) -> None:
    original = live.StageResult("clone", "ok", f"cloned into {tmp_path}/checkout")

    assert live.redacted_stage(original, tmp_path).detail == (
        "cloned into <temporary-home>/checkout"
    )


def worker_summary(tmp_path: Path, **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "provider": "surrey",
        "repository": f"{live.SURREY_NAMESPACE}/{live.SURREY_PROJECT}",
        "candidate_version": "1.2.3",
        "expected_head": "1" * 40,
        "observed_head": "1" * 40,
        "clean_tree": True,
        "stages": [
            {"stage": stage, "status": "ok", "detail": f"verified {stage}"}
            for stage in live.SELECTED_STAGE_IDS
        ],
    }
    value.update(updates)
    return value


def test_worker_summary_is_closed_and_requires_all_final_checks(tmp_path: Path) -> None:
    fixture = live.Fixture(**fixture_values())
    value = worker_summary(tmp_path)

    accepted = live.validate_worker_summary(
        value,
        fixture=fixture,
        candidate_version="1.2.3",
        expected_head="1" * 40,
        temporary_root=tmp_path,
    )
    assert accepted == value

    value["unexpected"] = "must not be retained"
    with pytest.raises(live.LiveProviderError, match="invalid report schema"):
        live.validate_worker_summary(
            value,
            fixture=fixture,
            candidate_version="1.2.3",
            expected_head="1" * 40,
            temporary_root=tmp_path,
        )


def test_worker_summary_rejects_failed_or_path_leaking_stage(tmp_path: Path) -> None:
    fixture = live.Fixture(**fixture_values())
    failed = worker_summary(tmp_path)
    assert isinstance(failed["stages"], list)
    failed["stages"][0]["status"] = "wrong"
    with pytest.raises(live.LiveProviderError, match="did not verify Bootstrap stage"):
        live.validate_worker_summary(
            failed,
            fixture=fixture,
            candidate_version="1.2.3",
            expected_head="1" * 40,
            temporary_root=tmp_path,
        )

    leaking = worker_summary(tmp_path)
    assert isinstance(leaking["stages"], list)
    leaking["stages"][0]["detail"] = f"read {tmp_path}/.ssh/private"
    with pytest.raises(live.LiveProviderError, match="unsafe detail"):
        live.validate_worker_summary(
            leaking,
            fixture=fixture,
            candidate_version="1.2.3",
            expected_head="1" * 40,
            temporary_root=tmp_path,
        )


def test_phase_one_requires_macos_and_explicit_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(live.platform, "system", lambda: "Linux")
    args = live.parser().parse_args(["--fixture", str(write_fixture(tmp_path / "fixture.json"))])

    with pytest.raises(live.LiveProviderError, match="restricted to an ephemeral macOS"):
        live.controller(args)


def test_worker_exercises_the_six_real_stages_without_a_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Use Git's URL rewrite as a provider that has no network transport."""
    source = tmp_path / "fixture-source"
    source.mkdir()
    marker = source / ".prodockit-live-provider-fixture.json"
    marker.write_text('{"fixture": "surrey-existing-repository"}\n', encoding="utf-8")
    (source / "README.md").write_text("# Read-only fixture\n", encoding="utf-8")
    (source / "zensical.toml").write_text(
        "[project]\n"
        'site_name = "Read-only fixture"\n'
        'docs_dir = "docs"\n'
        f'repo_url = "https://{live.SURREY_HOSTNAME}/{live.SURREY_NAMESPACE}/'
        f'{live.SURREY_PROJECT}"\n'
        f'repo_name = "{live.SURREY_PROJECT}"\n'
        'edit_uri = "edit/main/docs/"\n\n'
        "[project.theme.icon]\n"
        'repo = "fontawesome/brands/gitlab"\n',
        encoding="utf-8",
    )
    (source / "docs").mkdir()
    (source / "docs" / "index.md").write_text("# Fixture\n", encoding="utf-8")
    git("init", "-b", "main", cwd=source)
    git("config", "user.name", "Prodockit test", cwd=source)
    git("config", "user.email", "test@example.invalid", cwd=source)
    git("add", "-A", cwd=source)
    git("commit", "-m", "Fixture", cwd=source)
    expected_head = git("rev-parse", "HEAD", cwd=source)

    bare = tmp_path / "provider.git"
    git("clone", "--bare", str(source), str(bare), cwd=tmp_path)
    refs_before = git("show-ref", cwd=bare)

    root = tmp_path / "run"
    bin_dir = root / "bin"
    ssh_dir = root / ".ssh"
    checkout = root / "checkout"
    for directory in (bin_dir, ssh_dir, checkout):
        directory.mkdir(parents=True)
    private = ssh_dir / "id_ed25519_gitlab"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private)],
        check=True,
    )
    fingerprint = next(
        field
        for field in subprocess.run(
            ["ssh-keygen", "-lf", str(private.with_suffix(".pub"))],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        if field.startswith("SHA256:")
    )
    ssh_shim = write_executable(
        bin_dir / "ssh",
        "case \"$*\" in\n"
        f"  *git-upload-pack*) exec git-upload-pack {bare!s} ;;\n"
        "esac\n"
        "printf '%s\\n' 'Welcome to GitLab, @mb0105!'\n"
        "exit 1\n",
    )
    write_executable(
        bin_dir / "ssh-add",
        f"printf '%s\\n' '256 {fingerprint} fixture (ED25519)'\n",
    )

    # The production remote check invokes a new Python process. This hook
    # makes its one visibility query deterministic and makes every other
    # Python socket connection fail, so a future network call breaks the test.
    hook = tmp_path / "network-block"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(
        "import importlib\n"
        "import socket\n"
        "sync_repo = importlib.import_module('prodockit.sync_repo')\n"
        "sync_repo._status_of = lambda _url, timeout=5.0: None\n"
        "def blocked(*_args, **_kwargs):\n"
        "    raise RuntimeError('external network access is forbidden')\n"
        "socket.socket.connect = blocked\n",
        encoding="utf-8",
    )
    source_root = ROOT / "src"
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "empty-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    monkeypatch.setenv("PATH", os.pathsep.join((str(bin_dir), os.environ["PATH"])))
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(hook), str(source_root))))

    fixture_path = write_fixture(
        root / "fixture.json", marker_sha256=live.sha256_file(marker)
    )
    worker_report = root / "worker-report.json"
    live.worker(
        Namespace(
            fixture=fixture_path,
            root=root,
            ssh_shim=ssh_shim,
            expected_head=expected_head,
            worker_report=worker_report,
        )
    )

    summary = json.loads(worker_report.read_text(encoding="utf-8"))
    assert [stage["stage"] for stage in summary["stages"]] == list(
        live.SELECTED_STAGE_IDS
    )
    assert all(stage["status"] == "ok" for stage in summary["stages"])
    assert summary["expected_head"] == summary["observed_head"] == expected_head
    assert git("show-ref", cwd=bare) == refs_before
    project = checkout / live.SURREY_PROJECT
    assert git("status", "--short", cwd=project) == ""
    assert git("remote", "get-url", "origin", cwd=project) == live.SURREY_REMOTE
