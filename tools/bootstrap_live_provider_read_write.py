# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise Bootstrap's two repository paths against a writable provider.

Phase two is deliberately separate from the read-only live-provider harness.
It accepts a fresh repository-scoped identity, permits exactly one ordinary
push to ``main`` of an already-created empty destination, then uses a second
fresh local home to prove that Bootstrap preserves the populated repository.
It never creates or deletes a provider project and receives no provider API
token.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import venv
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any, NoReturn

from bootstrap_live_provider_read_only import (
    AGENT_FINGERPRINT_RE,
    OBJECT_ID_RE,
    PROVIDER_HOSTS,
    SHA256_RE,
    AgentIdentity,
    LiveProviderError,
    environment_python,
    inspect_wheel,
    make_ssh_shim,
    private_metadata_path,
    public_key_fingerprint,
    run,
    select_agent_identity,
    sha256_file,
    ssh_config_path,
    utc_now,
    validate_known_hosts,
)
from canonical_wheel import WheelIdentityError
from canonical_wheel import inspect_wheel as inspect_canonical_wheel
from live_provider_state import ResetHandoff, StateError

SURREY_HOSTNAME = "gitlab.surrey.ac.uk"
SURREY_SOURCE = "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git"
SURREY_NAMESPACE = "assessment-liveprovider-2026"
SURREY_PROJECT = "report-liveprovider-2026-mb0105"
SURREY_DESTINATION = (
    "git@gitlab.surrey.ac.uk:assessment-liveprovider-2026/report-liveprovider-2026-mb0105.git"
)
PUBLIC_TEMPLATE = "https://github.com/buckwem/prodockit-template.git"
RELEASE_SOURCE = "https://github.com/buckwem/prodockit-extensions.git"
INITIAL_COMMIT_SUBJECT = "Initial commit"
REQUIRED_VSCODE_EXTENSIONS = (
    "ms-python.python",
    "zensical.zensical-studio",
    "tamasfe.even-better-toml",
    "ltex-plus.vscode-ltex-plus",
)
# Provider reads immediately after a push can remain temporarily unavailable
# while GitLab creates its pipeline ref. Keep this bounded and read-only: no
# commit or push operation is ever repeated.
READ_RETRY_DELAYS = (2.0, 5.0, 10.0, 20.0)
TRANSIENT_ORIGIN_DETAIL = "could not reach origin to see what is there"
GITLAB_PIPELINE_REF_RE = re.compile(r"refs/pipelines/[1-9][0-9]*")
VSCODE_SETTINGS_SCRIPT = """
import json, sys, pathlib
path, incoming = pathlib.Path(sys.argv[1]), json.loads(sys.argv[2])
path.parent.mkdir(parents=True, exist_ok=True)
try:
    current = json.loads(path.read_text(encoding="utf-8") or "{}")
except FileNotFoundError:
    current = {}
if not isinstance(current, dict):
    raise ValueError(f"{path} is not a JSON object")
raw_associations = current.get("files.associations")
associations = dict(raw_associations) if isinstance(raw_associations, dict) else {}
associations.update(incoming.pop("files.associations", {}))
if associations:
    current["files.associations"] = associations
current.update(incoming)
path.write_text(json.dumps(current, indent=2) + "\\n", encoding="utf-8")
"""

MUTABLE_STAGE_IDS = {
    "git",
    "clone",
    "fresh-history",
    "remote",
    "identity",
    "project-env",
    "node",
    "vscode-settings",
    "csl-style",
    "mathjax",
    "first-push",
}
PREREQUISITE_STAGE_IDS = {
    "own-venv",
    "vscode",
    "ssh-key",
    "ssh-config",
    "ssh-agent",
    "ssh-upload",
    "own-project",
    "pages",
    "clone-source",
    "pandoc",
    "extensions",
}
FORBIDDEN_ARGUMENTS = {
    "--delete",
    "--force",
    "--force-with-lease",
    "-f",
    "--mirror",
    "--prune",
}
REPORT_KEYS = {
    "provider",
    "repository",
    "candidate_version",
    "path_one",
    "path_two",
}


def refs_digest(refs: dict[str, str]) -> str:
    """Return the canonical digest shared with the lifecycle controller."""

    encoded = json.dumps(refs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Fixture:
    """The two exact repositories authorised for one Phase 2 run."""

    schema: int
    provider: str
    hostname: str
    source_remote: str
    source_head: str
    destination_namespace: str
    destination_project: str
    destination_remote: str
    template_marker_path: str
    template_marker_sha256: str

    @classmethod
    def read(cls, path: Path) -> Fixture:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LiveProviderError(f"could not read the Phase 2 fixture: {error}") from error
        if not isinstance(value, dict):
            raise LiveProviderError("the Phase 2 fixture must be one JSON object")
        required = {
            "schema",
            "provider",
            "hostname",
            "source_remote",
            "source_head",
            "destination_namespace",
            "destination_project",
            "destination_remote",
            "template_marker_path",
            "template_marker_sha256",
        }
        missing = required - set(value)
        unknown = set(value) - required
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing {', '.join(sorted(missing))}")
            if unknown:
                details.append(f"unknown {', '.join(sorted(unknown))}")
            raise LiveProviderError("invalid Phase 2 fixture: " + "; ".join(details))
        fixture = cls(**value)
        fixture.validate()
        return fixture

    def validate(self) -> None:
        if self.schema != 2:
            raise LiveProviderError("the Phase 2 fixture schema must be 2")
        if self.provider not in PROVIDER_HOSTS:
            raise LiveProviderError(f"unsupported provider {self.provider!r}")
        expected_hostname = PROVIDER_HOSTS[self.provider][0]
        if self.hostname != expected_hostname:
            raise LiveProviderError(
                f"{self.provider} must use {expected_hostname}, not {self.hostname}"
            )
        expected_destination = (
            f"git@{self.hostname}:{self.destination_namespace}/{self.destination_project}.git"
        )
        if self.destination_remote != expected_destination:
            raise LiveProviderError(f"destination remote must be exactly {expected_destination}")
        if self.provider == "surrey":
            if (
                self.source_remote != SURREY_SOURCE
                or self.destination_namespace != SURREY_NAMESPACE
                or self.destination_project != SURREY_PROJECT
                or self.destination_remote != SURREY_DESTINATION
            ):
                raise LiveProviderError(
                    "the Surrey Phase 2 fixture must derive from account mb0105, "
                    "course liveprovider, First assessment, year 2026"
                )
        elif self.source_remote != PUBLIC_TEMPLATE:
            raise LiveProviderError(f"the public provider template must be {PUBLIC_TEMPLATE}")
        if not OBJECT_ID_RE.fullmatch(self.source_head):
            raise LiveProviderError("source_head must be one complete Git object ID")
        marker = Path(self.template_marker_path)
        if marker.is_absolute() or not marker.parts or ".." in marker.parts:
            raise LiveProviderError("template_marker_path must stay within the template")
        if not SHA256_RE.fullmatch(self.template_marker_sha256):
            raise LiveProviderError(
                "template_marker_sha256 must be 64 lowercase hexadecimal characters"
            )


@dataclass(frozen=True)
class PathResult:
    name: str
    configured_source: str
    configured_history: str
    applied_stages: tuple[str, ...]
    commit: str
    tree: str
    clean_tree: bool


def query_refs(
    remote: str,
    *,
    cwd: Path,
    environment: dict[str, str],
    git_executable: str = "git",
) -> dict[str, str]:
    """Return sorted advertised refs, accepting a genuinely empty repository."""
    failure: LiveProviderError | None = None
    for delay in (0.0, *READ_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            result = run(
                [git_executable, "ls-remote", "--refs", remote],
                cwd=cwd,
                environment=environment,
            )
        except LiveProviderError as error:
            failure = error
            continue
        break
    else:
        assert failure is not None
        raise failure
    refs: dict[str, str] = {}
    for number, line in enumerate(result.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split()
        if (
            len(fields) != 2
            or not OBJECT_ID_RE.fullmatch(fields[0])
            or not fields[1].startswith("refs/")
            or fields[1] in refs
        ):
            raise LiveProviderError(f"unexpected ls-remote output on line {number}")
        refs[fields[1]] = fields[0]
    return dict(sorted(refs.items()))


def validate_destination_refs(
    refs: dict[str, str],
    *,
    fixture: Fixture,
    expected_commit: str,
) -> tuple[str, ...]:
    """Accept destination main plus GitLab's same-commit pipeline bookkeeping."""
    if refs.get("refs/heads/main") != expected_commit:
        raise LiveProviderError("the destination main ref differs from the tested commit")
    provider_refs: list[str] = []
    for name, object_id in refs.items():
        if name == "refs/heads/main":
            continue
        if (
            fixture.provider == "surrey"
            and GITLAB_PIPELINE_REF_RE.fullmatch(name)
            and object_id == expected_commit
        ):
            provider_refs.append(name)
            continue
        raise LiveProviderError(f"the destination contains an unexpected ref: {name}")
    return tuple(sorted(provider_refs))


def check_with_post_push_retry(
    stage_id: str,
    check: Callable[[], Any],
    before_retry: Callable[[], None],
) -> Any:
    """Retry only the transient read used to verify an already-finished push."""
    result = check()
    if stage_id != "first-push" or result.detail != TRANSIENT_ORIGIN_DETAIL:
        return result
    for delay in READ_RETRY_DELAYS:
        time.sleep(delay)
        before_retry()
        result = check()
        if result.detail != TRANSIENT_ORIGIN_DETAIL:
            break
    return result


def validate_exclusive_agent(socket: Path, fingerprint: str) -> AgentIdentity:
    """Require a dedicated agent containing exactly the approved identity."""
    selected = select_agent_identity(socket, fingerprint)
    executable = shutil.which("ssh-add")
    if executable is None:
        raise LiveProviderError("ssh-add is required to inspect the dedicated agent")
    environment = {"PATH": os.environ.get("PATH", ""), "SSH_AUTH_SOCK": str(selected.socket)}
    result = subprocess.run(
        [executable, "-L"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    identities = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode or len(identities) != 1:
        raise LiveProviderError("the Phase 2 SSH agent must expose exactly one identity")
    if public_key_fingerprint(identities[0]) != fingerprint:
        raise LiveProviderError("the dedicated agent identity changed during validation")
    return selected


def isolated_environment(
    *,
    home: Path,
    bin_dir: Path,
    git_config: Path,
    agent: AgentIdentity,
    ssh_shim: Path,
) -> dict[str, str]:
    """Build the candidate environment without inherited credentials."""
    safe_inherited = {
        "DYLD_FALLBACK_LIBRARY_PATH",
        "LANG",
        "LC_ALL",
        "PATH",
        "SHELL",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TERM",
        "TMPDIR",
        "USER",
        "WEASYPRINT_DLL_DIRECTORIES",
    }
    environment = {name: value for name, value in os.environ.items() if name in safe_inherited}
    environment.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "GIT_CONFIG_GLOBAL": str(git_config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": os.pathsep.join((str(bin_dir), environment.get("PATH", ""))),
            "PYTHONUTF8": "1",
            "SSH_AUTH_SOCK": str(agent.socket),
            "GIT_SSH_COMMAND": shlex.join(
                (
                    str(ssh_shim),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=10",
                    "-o",
                    "IdentitiesOnly=yes",
                    "-o",
                    "StrictHostKeyChecking=yes",
                )
            ),
        }
    )
    return environment


def prepare_home(
    home: Path,
    *,
    fixture: Fixture,
    known_hosts: Path,
    agent: AgentIdentity,
    system_ssh: Path,
    host_home: Path | None = None,
) -> Path:
    """Create the pinned SSH setup and copy reviewed user tooling metadata."""
    ssh_dir = home / ".ssh"
    bin_dir = home / "bin"
    ssh_dir.mkdir(parents=True, mode=0o700)
    bin_dir.mkdir(parents=True, mode=0o700)
    if host_home is not None:
        copy_user_tooling(home, host_home)
    suffix = PROVIDER_HOSTS[fixture.provider][1]
    key_record = ssh_dir / f"id_ed25519_{suffix}"
    copied_public = key_record.with_suffix(".pub")
    copied_known_hosts = ssh_dir / "known_hosts"
    # Bootstrap's guided keypair check asks ssh-keygen to fingerprint both
    # paths. A public OpenSSH record is valid input for that operation, so use
    # the agent's approved public record at both normal paths. The candidate
    # can exercise its real checks while the private half remains inside the
    # dedicated agent (for example, 1Password) and is never copied to disk.
    key_record.write_text(agent.public_key + "\n", encoding="utf-8")
    copied_public.write_text(agent.public_key + "\n", encoding="utf-8")
    shutil.copyfile(known_hosts, copied_known_hosts)
    key_record.chmod(0o600)
    copied_public.chmod(0o600)
    copied_known_hosts.chmod(0o600)
    config = ssh_dir / "config"
    config.write_text(
        f"Host {fixture.hostname}\n"
        f"    HostName {fixture.hostname}\n"
        "    User git\n"
        # OpenSSH expands ``~`` from the account database rather than the
        # candidate's temporary HOME on macOS. An absolute path is essential:
        # otherwise the live harness can name and load the developer's real
        # key from ~/.ssh into the supposedly dedicated agent.
        f"    IdentityFile {ssh_config_path(key_record)}\n"
        "    AddKeysToAgent yes\n"
        "    UseKeychain yes\n"
        f"    IdentityAgent {ssh_config_path(agent.socket)}\n"
        "    IdentitiesOnly yes\n"
        "    BatchMode yes\n"
        "    StrictHostKeyChecking yes\n"
        f"    UserKnownHostsFile {ssh_config_path(copied_known_hosts)}\n"
        "    GlobalKnownHostsFile /dev/null\n"
        "    ConnectTimeout 10\n",
        encoding="utf-8",
    )
    config.chmod(0o600)
    return make_ssh_shim(bin_dir, system_ssh, config)


def copy_user_tooling(home: Path, host_home: Path) -> None:
    """Copy only the user-scoped prerequisites needed by Bootstrap checks.

    The candidate must not receive writable links into the real home. Font
    files and extension manifests are copied into its disposable home instead;
    any candidate write is therefore discarded with that temporary directory.
    """
    font_source = host_home / "Library" / "Fonts"
    font_target = home / "Library" / "Fonts"
    if font_source.is_dir():
        selected_fonts = [
            path
            for path in font_source.iterdir()
            if path.is_file()
            and any(
                name in path.name.casefold().replace(" ", "").replace("-", "")
                for name in ("inter", "jetbrainsmono")
            )
        ]
        if selected_fonts:
            font_target.mkdir(parents=True)
            for source in selected_fonts:
                if not _within(source, host_home):
                    raise LiveProviderError("an approved font resolves outside the host home")
                shutil.copyfile(source, font_target / source.name)

    extension_source = host_home / ".vscode" / "extensions"
    extension_target = home / ".vscode" / "extensions"
    if not extension_source.is_dir():
        return
    for source in extension_source.iterdir():
        if not source.is_dir() or not any(
            source.name.casefold().startswith(f"{identifier}-")
            for identifier in REQUIRED_VSCODE_EXTENSIONS
        ):
            continue
        manifest = source / "package.json"
        if not manifest.is_file() or not _within(manifest, host_home):
            continue
        target = extension_target / source.name
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(manifest, target / "package.json")


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def expected_email(fixture: Fixture) -> str:
    """Return the exact non-privileged identity used for test commits."""
    return (
        "mb0105@surrey.ac.uk"
        if fixture.provider == "surrey"
        else "live-provider-test@example.invalid"
    )


def validate_controller_checkout(
    checkout: Path,
    *,
    environment: dict[str, str],
    git_executable: str,
    expected_release_commit: str | None = None,
) -> str:
    """Require a clean reviewed controller checkout.

    Manual Phase 3 runs use local ``main`` at ``origin/main``. Protected
    provider jobs may instead use a detached checkout of one exact public
    GitHub release commit, because the GitLab mirror can legitimately lag.
    """
    observations = {
        "branch": ["branch", "--show-current"],
        "head": ["rev-parse", "HEAD"],
        "origin_main": ["rev-parse", "origin/main"],
        "origin": ["remote", "get-url", "origin"],
        "status": ["status", "--porcelain"],
    }
    values = {
        name: run(
            [git_executable, "-C", str(checkout), *arguments],
            cwd=checkout,
            environment=environment,
        ).stdout.strip()
        for name, arguments in observations.items()
    }
    if values["status"]:
        raise LiveProviderError("the Phase 2 controller checkout must be clean")
    if expected_release_commit is not None:
        if not OBJECT_ID_RE.fullmatch(expected_release_commit):
            raise LiveProviderError("the release commit must be one complete Git object ID")
        if values["branch"] not in {"", "main"}:
            raise LiveProviderError("the release controller is on an unexpected branch")
        if values["origin"] != RELEASE_SOURCE:
            raise LiveProviderError("the release controller did not come from the public source")
        if values["head"] != expected_release_commit:
            raise LiveProviderError(
                "the release controller differs from the exact requested commit"
            )
        return values["head"]
    if values["branch"] != "main":
        raise LiveProviderError("the Phase 2 controller must run from the default main branch")
    if values["head"] != values["origin_main"]:
        raise LiveProviderError("the Phase 2 controller must match reviewed origin/main")
    return values["head"]


def authorise_plan(
    stage_id: str,
    commands: Sequence[Sequence[str]],
    cwd: str | None,
    *,
    fixture: Fixture,
    home: Path,
    project: Path,
    allow_push: bool,
    candidate_python: Path | None = None,
) -> None:
    """Reject plans that exceed Phase 2's local and one-push boundary."""
    if cwd is not None and not _within(Path(cwd), home):
        raise LiveProviderError(f"stage {stage_id} would run outside the temporary home")
    push_count = 0
    for raw in commands:
        command = [str(part) for part in raw]
        if not command:
            raise LiveProviderError(f"stage {stage_id} generated an empty command")
        rendered = " ".join(command)
        lowered = rendered.casefold()
        if any(argument in FORBIDDEN_ARGUMENTS for argument in command):
            raise LiveProviderError(f"stage {stage_id} generated a destructive Git flag")
        if any(token in rendered for token in ("refs/*", "refs/heads/*", ":main", "main:")):
            raise LiveProviderError(f"stage {stage_id} generated an unsafe refspec")
        if any(word in lowered for word in ("printenv", "env |", "credential.helper")):
            raise LiveProviderError(f"stage {stage_id} generated a credential-reading command")
        executable = Path(command[0]).name.casefold().removesuffix(".exe")
        if executable in {"gh", "glab"}:
            raise LiveProviderError(f"stage {stage_id} generated a provider API command")
        if executable == "git":
            args = command[1:]
            allowed_git: list[list[str]] = []
            if stage_id == "clone":
                allowed_git = [
                    ["clone", fixture.source_remote, str(project)],
                    ["clone", fixture.destination_remote, str(project)],
                ]
            elif stage_id == "git":
                allowed_git = [
                    [
                        "config",
                        "--global",
                        "user.name",
                        "Prodockit live-provider test",
                    ],
                    [
                        "config",
                        "--global",
                        "user.email",
                        expected_email(fixture),
                    ],
                ]
            elif stage_id == "fresh-history":
                allowed_git = [
                    ["init", "-b", "main"],
                    ["config", "core.fileMode", "false"],
                ]
            elif stage_id == "remote":
                allowed_git = [
                    ["remote", "add", "origin", fixture.destination_remote],
                    ["remote", "set-url", "origin", fixture.destination_remote],
                ]
            elif stage_id == "identity":
                allowed_git = [
                    ["config", "--local", "user.name", "Prodockit live-provider test"],
                    [
                        "config",
                        "--local",
                        "user.email",
                        expected_email(fixture),
                    ],
                ]
            elif stage_id == "first-push":
                allowed_git = [
                    ["add", "-A"],
                    ["commit", "-m", INITIAL_COMMIT_SUBJECT],
                    ["push", "-u", "origin", "main"],
                ]
            if args not in allowed_git:
                raise LiveProviderError(f"stage {stage_id} generated an unapproved Git command")
            if args and args[0] == "push":
                push_count += 1
                if not allow_push or args != ["push", "-u", "origin", "main"]:
                    raise LiveProviderError("Bootstrap generated a push outside destination main")
        else:
            _authorise_non_git_command(
                stage_id,
                command,
                fixture=fixture,
                home=home,
                project=project,
                candidate_python=candidate_python,
            )
        for argument in command[1:]:
            if argument.startswith(("/", "~")):
                candidate = Path(argument).expanduser()
                if (
                    candidate.exists()
                    and not _within(candidate, home)
                    and not str(candidate).startswith(("/usr/", "/opt/", "/Applications/"))
                ):
                    # System executables and package-manager inputs are allowed;
                    # writable project operands are not.
                    raise LiveProviderError(
                        f"stage {stage_id} refers to a path outside the temporary home"
                    )
    if push_count > 1:
        raise LiveProviderError("Bootstrap generated more than one push")


def _authorise_non_git_command(
    stage_id: str,
    command: list[str],
    *,
    fixture: Fixture,
    home: Path,
    project: Path,
    candidate_python: Path | None,
) -> None:
    """Allow only the expected local build operations around repository work."""
    if fixture.source_remote in command or fixture.destination_remote in command:
        raise LiveProviderError(f"stage {stage_id} passed a provider remote to a non-Git command")
    executable = Path(command[0]).name.casefold()
    candidate = str(candidate_python) if candidate_python is not None else ""
    project_python = str(project / ".venv" / "bin" / "python")
    project_zensical = str(project / ".venv" / "bin" / "zensical")
    accepted = False
    if stage_id == "fresh-history":
        accepted = command == [
            "mv",
            str(project / ".git"),
            str(project.parent / f".{project.name}.git.pdk-template-backup"),
        ]
    elif stage_id == "remote":
        accepted = command == [candidate, "-m", "prodockit", "sync-repo"]
    elif stage_id == "project-env":
        accepted = command in (
            [candidate, "-m", "venv", str(project / ".venv")],
            [
                project_python,
                "-m",
                "pip",
                "install",
                "-r",
                str(project / "requirements.txt"),
            ],
        )
        if (
            not accepted
            and len(command) == 6
            and command[0] == candidate
            and command[1] == "-c"
            and command[3] == str(project / ".venv" / "bin" / "activate")
            and command[5] in {"/opt/homebrew/lib", "/usr/local/lib"}
        ):
            accepted = _safe_embedded_python(command[2])
    elif stage_id == "node":
        wanted = {
            f"cd {shlex.quote(str(project / 'tools' / component))} && npm ci --legacy-peer-deps"
            for component in ("mermaid", "mathjax")
        }
        accepted = executable == "bash" and command[1:2] == ["-c"] and command[2] in wanted
    elif stage_id == "vscode-settings":
        accepted = (
            len(command) == 5
            and command[0] == candidate
            and command[1] == "-c"
            and command[2] == VSCODE_SETTINGS_SCRIPT
            and command[3] == str(project / ".vscode" / "settings.json")
        )
        if accepted:
            try:
                settings = json.loads(command[4])
            except json.JSONDecodeError:
                accepted = False
            else:
                accepted = isinstance(settings, dict) and set(settings) <= {
                    "files.associations",
                    "ltex.language",
                }
    elif stage_id == "csl-style":
        accepted = command == [
            "curl",
            "-fsSL",
            "-o",
            "harvard-cite-them-right.csl",
            "https://www.zotero.org/styles/harvard-cite-them-right",
        ]
    elif stage_id == "mathjax":
        accepted = command == [candidate, "-m", "prodockit", "init-mathjax"]
    elif stage_id == "first-push":
        accepted = command == [project_zensical, "build", "--clean"]
    if not accepted:
        raise LiveProviderError(
            f"stage {stage_id} generated an unapproved non-Git command: {shlex.join(command)}"
        )


def _safe_embedded_python(script: str) -> bool:
    """Bound the two reviewed file-rewrite scripts emitted by Bootstrap."""
    lowered = script.casefold()
    forbidden = (
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "http",
        "shutil",
        "os.system",
        "unlink(",
        "rmtree(",
    )
    return "from pathlib import path" in lowered and not any(
        token in lowered for token in forbidden
    )


@contextmanager
def use_environment(environment: dict[str, str]) -> Iterator[None]:
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(environment)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def configure_candidate(
    *,
    python: Path,
    fixture: Fixture,
    setup: Path,
    environment: dict[str, str],
) -> tuple[Any, str]:
    """Run the real questionnaire and verify its saved derivation."""
    if fixture.provider == "surrey":
        answers = "1\nProdockit live-provider test\nmb0105\ny\nliveprovider\n1\n2026\n"
    else:
        answers = (
            "2\nProdockit live-provider test\n"
            "live-provider-test@example.invalid\n"
            f"{fixture.destination_namespace}\n{fixture.destination_namespace}\n"
            f"{fixture.destination_project}\n\n"
        )
    result = subprocess.run(
        [str(python), "-m", "prodockit", "bootstrap", "--configure"],
        cwd=setup,
        env=environment,
        input=answers,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise LiveProviderError(f"Bootstrap configuration failed: {result.stderr.strip()}")
    from prodockit.bootstrap import load

    config = load(setup / ".pdkboot.toml")
    expected = {
        "host": fixture.hostname,
        "namespace": fixture.destination_namespace,
        "project_name": fixture.destination_project,
        "full_name": "Prodockit live-provider test",
    }
    for name, value in expected.items():
        if getattr(config, name) != value:
            raise LiveProviderError(f"Bootstrap configuration derived an unexpected {name}")
    if Path(config.project_dir).resolve() != (setup / fixture.destination_project).resolve():
        raise LiveProviderError("Bootstrap configuration derived an unexpected project path")
    return config, result.stdout


def apply_repository_path(
    *,
    python: Path,
    fixture: Fixture,
    home: Path,
    ssh_shim: Path,
    environment: dict[str, str],
    allow_push: bool,
    name: str,
) -> PathResult:
    """Configure and run production stages through ``first-push``."""
    from prodockit.bootstrap import (
        STAGES,
        SubprocessRunner,
        apply_stage,
        build_context,
        forget_contacts,
    )

    setup = home / "setup"
    setup.mkdir(parents=True)
    with use_environment(environment):
        config, _configure_output = configure_candidate(
            python=python,
            fixture=fixture,
            setup=setup,
            environment=environment,
        )
        context = build_context(
            config,
            runner=SubprocessRunner(git_ssh_executable=str(ssh_shim)),
            home=home,
            guided=True,
        )
        project = config.resolved_project_dir(home)
        applied: list[str] = []
        clone_source_detail = ""
        for stage in STAGES:
            if stage.id == "site":
                break
            forget_contacts(context)
            result = stage.check(context)
            if stage.id == "clone-source":
                clone_source_detail = result.detail
            if not result.needs_work:
                continue
            if stage.id in PREREQUISITE_STAGE_IDS:
                raise LiveProviderError(
                    f"Phase 2 prerequisite {stage.id} is not ready: {result.detail}"
                )
            if stage.id not in MUTABLE_STAGE_IDS:
                raise LiveProviderError(f"Phase 2 did not authorise stage {stage.id}")
            plan = stage.plan(context)
            authorise_plan(
                stage.id,
                plan.commands,
                plan.cwd,
                fixture=fixture,
                home=home,
                project=project,
                allow_push=allow_push,
                candidate_python=python,
            )
            outcome = apply_stage(context, stage, plan)
            if not outcome.ok:
                detail = outcome.verified.detail if outcome.verified else "command failed"
                raise LiveProviderError(f"Bootstrap stage {stage.id} failed: {detail}")
            applied.append(stage.id)

        if name == "path-one":
            if config.source_url or config.history:
                raise LiveProviderError("the empty destination did not select the template")
            if "template will be" not in clone_source_detail:
                raise LiveProviderError("Bootstrap did not explain the empty destination path")
            if applied.count("first-push") != 1:
                raise LiveProviderError("the empty destination did not perform one first push")
        else:
            expected_source = f"{fixture.destination_namespace}/{fixture.destination_project}"
            if config.source_url != expected_source or config.history != "keep":
                raise LiveProviderError("the populated destination did not select option 1")
            if "Option 1 selected automatically" not in clone_source_detail:
                raise LiveProviderError("Bootstrap did not report automatic option 1")
            if "first-push" in applied:
                raise LiveProviderError("the populated destination attempted another push")

        # A second pass must not propose any work through the publication
        # boundary. This proves idempotence rather than merely checking that a
        # second push is absent.
        for stage in STAGES:
            if stage.id == "site":
                break
            forget_contacts(context)
            result = check_with_post_push_retry(
                stage.id,
                partial(stage.check, context),
                lambda: forget_contacts(context),
            )
            if result.needs_work:
                raise LiveProviderError(
                    f"the repeated {name} run still needs stage {stage.id}: {result.detail}"
                )
        commands = {
            "commit": ["rev-parse", "HEAD"],
            "tree": ["rev-parse", "HEAD^{tree}"],
            "branch": ["branch", "--show-current"],
            "main": ["rev-parse", "refs/heads/main"],
            "origin_main": ["rev-parse", "refs/remotes/origin/main"],
            "origin": ["remote", "get-url", "origin"],
            "push_origin": ["remote", "get-url", "--push", "origin"],
            "file_mode": ["config", "--get", "core.fileMode"],
            "user_name": ["config", "--local", "--get", "user.name"],
            "user_email": ["config", "--local", "--get", "user.email"],
            "status": ["status", "--short"],
        }
        observed = {
            key: run(
                ["git", "-C", str(project), *arguments],
                cwd=home,
                environment=environment,
            ).stdout.strip()
            for key, arguments in commands.items()
        }
        commit = observed["commit"]
        if observed["status"]:
            raise LiveProviderError(f"the {name} checkout is not clean")
        if any(observed[key] != commit for key in ("main", "origin_main")):
            raise LiveProviderError(f"the {name} local and remote-tracking main differ")
        if observed["branch"] != "main":
            raise LiveProviderError(f"the {name} checkout is not on main")
        if (
            observed["origin"] != fixture.destination_remote
            or observed["push_origin"] != fixture.destination_remote
        ):
            raise LiveProviderError(f"the {name} origin differs from the destination")
        if observed["file_mode"].casefold() != "false":
            raise LiveProviderError(f"the {name} checkout did not disable core.fileMode")
        if observed["user_name"] != "Prodockit live-provider test" or observed[
            "user_email"
        ] != expected_email(fixture):
            raise LiveProviderError(f"the {name} local commit identity differs")
        backup = setup / f".{fixture.destination_project}.git.pdk-template-backup"
        if name == "path-two" and backup.exists():
            raise LiveProviderError("the populated destination archived its existing history")
        return PathResult(
            name=name,
            configured_source=config.source_url,
            configured_history=config.history,
            applied_stages=tuple(applied),
            commit=commit,
            tree=observed["tree"],
            clean_tree=True,
        )


def verify_template_marker(
    fixture: Fixture,
    *,
    root: Path,
    environment: dict[str, str],
    git_executable: str,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    checkout = root / "reviewed-template"
    run(
        [git_executable, "clone", "--no-tags", fixture.source_remote, str(checkout)],
        cwd=root,
        environment=environment,
    )
    head = run(
        [git_executable, "-C", str(checkout), "rev-parse", "HEAD"],
        cwd=root,
        environment=environment,
    ).stdout.strip()
    if head != fixture.source_head:
        raise LiveProviderError("the reviewed template main commit changed")
    marker = checkout / fixture.template_marker_path
    if not marker.is_file() or sha256_file(marker) != fixture.template_marker_sha256:
        raise LiveProviderError("the reviewed template marker is missing or changed")


def verify_destination(
    fixture: Fixture,
    *,
    root: Path,
    environment: dict[str, str],
    git_executable: str,
    expected_commit: str,
    expected_tree: str,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    checkout = root / "independent-destination"
    run(
        [
            git_executable,
            "clone",
            "--branch",
            "main",
            fixture.destination_remote,
            str(checkout),
        ],
        cwd=root,
        environment=environment,
    )
    values = {
        "head": ["rev-parse", "HEAD"],
        "root_count": ["rev-list", "--max-parents=0", "--count", "HEAD"],
        "subject": ["show", "-s", "--format=%s", "HEAD"],
        "author_name": ["show", "-s", "--format=%an", "HEAD"],
        "author_email": ["show", "-s", "--format=%ae", "HEAD"],
        "committer_name": ["show", "-s", "--format=%cn", "HEAD"],
        "committer_email": ["show", "-s", "--format=%ce", "HEAD"],
        "tree": ["rev-parse", "HEAD^{tree}"],
        "parents": ["show", "-s", "--format=%P", "HEAD"],
        "origin": ["remote", "get-url", "origin"],
        "push_origin": ["remote", "get-url", "--push", "origin"],
        "status": ["status", "--short"],
    }
    observed = {
        name: run(
            [git_executable, "-C", str(checkout), *arguments],
            cwd=root,
            environment=environment,
        ).stdout.strip()
        for name, arguments in values.items()
    }
    if observed["head"] != expected_commit:
        raise LiveProviderError("the independently cloned destination commit differs")
    if observed["root_count"] != "1" or observed["parents"]:
        raise LiveProviderError("the destination does not contain one root history")
    if observed["subject"] != INITIAL_COMMIT_SUBJECT:
        raise LiveProviderError("the destination root commit has an unexpected subject")
    if observed["tree"] != expected_tree:
        raise LiveProviderError("the destination tree differs from the candidate checkout")
    if any(
        observed[name] != "Prodockit live-provider test"
        for name in ("author_name", "committer_name")
    ) or any(
        observed[name] != expected_email(fixture) for name in ("author_email", "committer_email")
    ):
        raise LiveProviderError("the destination commit identity differs from the fixture")
    if (
        observed["origin"] != fixture.destination_remote
        or observed["push_origin"] != fixture.destination_remote
    ):
        raise LiveProviderError("the destination origin differs from its allowlist")
    if observed["status"]:
        raise LiveProviderError("the independently cloned destination is not clean")
    marker = checkout / fixture.template_marker_path
    if not marker.is_file() or sha256_file(marker) != fixture.template_marker_sha256:
        raise LiveProviderError("the destination template marker is missing or changed")


def validate_worker_report(
    value: object,
    fixture: Fixture,
    candidate_version: str,
    *,
    temporary_root: Path | None = None,
) -> dict[str, Any]:
    serialised = json.dumps(value, sort_keys=True)
    if temporary_root is not None and str(temporary_root) in serialised:
        raise LiveProviderError("the Phase 2 worker report contains a temporary path")
    if any(name in serialised for name in ("SSH_AUTH_SOCK", "PRIVATE KEY")):
        raise LiveProviderError("the Phase 2 worker report contains credential material")
    if not isinstance(value, dict) or set(value) != REPORT_KEYS:
        raise LiveProviderError("the Phase 2 worker returned an invalid report schema")
    if value.get("provider") != fixture.provider:
        raise LiveProviderError("the Phase 2 worker returned another provider")
    if value.get("repository") != (
        f"{fixture.destination_namespace}/{fixture.destination_project}"
    ):
        raise LiveProviderError("the Phase 2 worker returned another repository")
    if value.get("candidate_version") != candidate_version:
        raise LiveProviderError("the Phase 2 worker returned another candidate version")
    for name in ("path_one", "path_two"):
        path = value.get(name)
        if not isinstance(path, dict) or set(path) != {
            "name",
            "configured_source",
            "configured_history",
            "applied_stages",
            "commit",
            "tree",
            "clean_tree",
        }:
            raise LiveProviderError(f"the Phase 2 worker returned an invalid {name}")
        if (
            not path.get("clean_tree")
            or not OBJECT_ID_RE.fullmatch(str(path.get("commit", "")))
            or not OBJECT_ID_RE.fullmatch(str(path.get("tree", "")))
        ):
            raise LiveProviderError(f"the Phase 2 worker did not finish {name} cleanly")
    if value["path_one"]["commit"] != value["path_two"]["commit"]:
        raise LiveProviderError("the two Phase 2 paths observed different commits")
    if value["path_one"]["tree"] != value["path_two"]["tree"]:
        raise LiveProviderError("the two Phase 2 paths observed different trees")
    return dict(value)


def run_candidate_worker(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int,
) -> None:
    """Run the candidate in its own process group and account for descendants."""

    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise LiveProviderError("the candidate worker exceeded its time limit") from error
    if process.returncode:
        message = stderr.strip() or stdout.strip() or f"status {process.returncode}"
        raise LiveProviderError(f"the candidate worker failed: {message}")
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise LiveProviderError("the candidate process group could not be accounted for") from error
    os.killpg(process.pid, signal.SIGKILL)
    raise LiveProviderError("the candidate left a process running after Bootstrap finished")


def classify_destination_after_failure(
    fixture: Fixture,
    *,
    root: Path,
    environment: dict[str, str],
    git_executable: str,
) -> str:
    """Classify an ambiguous write without retrying any candidate command."""
    try:
        refs = query_refs(
            fixture.destination_remote,
            cwd=root,
            environment=environment,
            git_executable=git_executable,
        )
    except (LiveProviderError, OSError, subprocess.SubprocessError):
        return "inconclusive"
    if not refs:
        return "not pushed"
    project = root / "path-one" / "setup" / fixture.destination_project
    if not project.is_dir() or "refs/heads/main" not in refs:
        return "inconclusive"
    try:
        commit = run(
            [git_executable, "-C", str(project), "rev-parse", "HEAD"],
            cwd=root,
            environment=environment,
        ).stdout.strip()
        tree = run(
            [git_executable, "-C", str(project), "rev-parse", "HEAD^{tree}"],
            cwd=root,
            environment=environment,
        ).stdout.strip()
        validate_destination_refs(refs, fixture=fixture, expected_commit=commit)
        verify_destination(
            fixture,
            root=root / "failure-verification",
            environment=environment,
            git_executable=git_executable,
            expected_commit=commit,
            expected_tree=tree,
        )
    except (LiveProviderError, OSError, subprocess.SubprocessError):
        return "inconclusive"
    return "pushed and verified"


def worker(args: argparse.Namespace) -> None:
    from importlib.metadata import version

    fixture = Fixture.read(args.fixture)
    root = args.root
    path_one_home = root / "path-one"
    path_two_home = root / "path-two"
    environment_one = json.loads(args.environment_one.read_text(encoding="utf-8"))
    environment_two = json.loads(args.environment_two.read_text(encoding="utf-8"))
    path_one = apply_repository_path(
        python=Path(sys.executable),
        fixture=fixture,
        home=path_one_home,
        ssh_shim=args.ssh_shim_one,
        environment=environment_one,
        allow_push=True,
        name="path-one",
    )
    path_two = apply_repository_path(
        python=Path(sys.executable),
        fixture=fixture,
        home=path_two_home,
        ssh_shim=args.ssh_shim_two,
        environment=environment_two,
        allow_push=False,
        name="path-two",
    )
    report = {
        "provider": fixture.provider,
        "repository": f"{fixture.destination_namespace}/{fixture.destination_project}",
        "candidate_version": version("prodockit"),
        "path_one": asdict(path_one),
        "path_two": asdict(path_two),
    }
    args.worker_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def controller(args: argparse.Namespace) -> None:
    if platform.system() != "Darwin":
        raise LiveProviderError("Phase 2 is deliberately restricted to a controlled macOS run")
    if not args.confirm_read_write:
        raise LiveProviderError("pass --confirm-read-write after reviewing the fixture and key")
    source_checkout = Path(__file__).resolve().parents[1]
    fixture_path = private_metadata_path(
        args.fixture,
        label="Phase 2 fixture",
        checkout=source_checkout,
        must_exist=True,
    )
    fixture = Fixture.read(fixture_path)
    if fixture.provider != args.provider:
        raise LiveProviderError("--provider does not match the Phase 2 fixture")
    wheel = inspect_wheel(args.wheel, args.expected_wheel_sha256)
    fingerprint = args.key_fingerprint.strip()
    if not AGENT_FINGERPRINT_RE.fullmatch(fingerprint):
        raise LiveProviderError("--key-fingerprint must be a complete SHA-256 fingerprint")
    agent = validate_exclusive_agent(args.agent_socket, fingerprint)
    known_hosts = private_metadata_path(
        args.known_hosts,
        label="known-hosts allowlist",
        checkout=source_checkout,
        must_exist=True,
    )
    validate_known_hosts(known_hosts, fixture.hostname)
    report_path = private_metadata_path(
        args.report,
        label="retained Phase 2 report",
        checkout=source_checkout,
        must_exist=False,
    )
    system_git_name = shutil.which("git")
    system_ssh_name = shutil.which("ssh")
    if system_git_name is None or system_ssh_name is None:
        raise LiveProviderError("the controlled machine needs system Git and OpenSSH")
    system_git = str(Path(system_git_name).resolve())
    system_ssh = Path(system_ssh_name).resolve()
    controller_commit = validate_controller_checkout(
        source_checkout,
        environment=dict(os.environ),
        git_executable=system_git,
        expected_release_commit=args.release_commit,
    )
    handoff: ResetHandoff | None = None
    if args.reset_handoff is not None:
        handoff_path = private_metadata_path(
            args.reset_handoff,
            label="provider reset handoff",
            checkout=source_checkout,
            must_exist=True,
        )
        try:
            handoff = ResetHandoff.read(handoff_path)
        except StateError as error:
            raise LiveProviderError(str(error)) from error
        if handoff.wheel_contents_sha256 is not None:
            try:
                canonical_identity = inspect_canonical_wheel(args.wheel)
            except WheelIdentityError as error:
                raise LiveProviderError(str(error)) from error
            if canonical_identity.wheel_contents_sha256 != handoff.wheel_contents_sha256:
                raise LiveProviderError(
                    "the candidate wheel contents differ from the provider reset handoff"
                )
        if (
            handoff.provider != fixture.provider
            or handoff.path_with_namespace
            != f"{fixture.destination_namespace}/{fixture.destination_project}"
            or handoff.source_commit != fixture.source_head
            or handoff.candidate_version != wheel.version
            or (handoff.schema == 1 and handoff.wheel_sha256 != wheel.sha256)
            or handoff.controller_commit != controller_commit
            or handoff.deploy_key_fingerprint != fingerprint
        ):
            raise LiveProviderError("the provider reset handoff differs from this candidate run")
    started = utc_now()
    host_home = Path.home().resolve()

    print("Prodockit Bootstrap live-provider Phase 2 — read and one write")
    print(f"  Provider:    {fixture.hostname}")
    print(f"  READ ONLY:   {fixture.source_remote} @ {fixture.source_head}")
    print(f"  READ/WRITE:  {fixture.destination_remote} (must be empty)")
    print(f"  Candidate:   prodockit {wheel.version} ({wheel.sha256})")
    print(f"  Deploy key:  {fingerprint} (dedicated one-identity agent)")
    print(f"  Controller:  {controller_commit} (clean reviewed origin/main)")
    print("  Boundary:    one ordinary push to destination main; no project lifecycle")

    summary: dict[str, Any] | None = None
    failure = "Phase 2 did not produce a result"
    write_outcome = "not attempted"
    source_refs_after_failure: bool | None = None
    source_before: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="prodockit-live-provider-rw-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        bin_dir = root / "bin"
        bin_dir.mkdir(mode=0o700)
        copied_fixture = root / "fixture.json"
        copied_fixture.write_text(json.dumps(asdict(fixture), indent=2) + "\n", encoding="utf-8")
        copied_wheel = root / wheel.path.name
        shutil.copyfile(wheel.path, copied_wheel)
        copied_fixture.chmod(0o400)
        copied_wheel.chmod(0o400)
        if Fixture.read(copied_fixture) != fixture or sha256_file(copied_wheel) != wheel.sha256:
            raise LiveProviderError("the copied Phase 2 inputs changed")
        try:
            environments: list[dict[str, str]] = []
            shims: list[Path] = []
            for path_name in ("path-one", "path-two"):
                home = root / path_name
                home.mkdir(mode=0o700)
                shim = prepare_home(
                    home,
                    fixture=fixture,
                    known_hosts=known_hosts,
                    agent=agent,
                    system_ssh=system_ssh,
                    host_home=host_home,
                )
                shims.append(shim)
                environments.append(
                    isolated_environment(
                        home=home,
                        bin_dir=shim.parent,
                        git_config=home / ".gitconfig",
                        agent=agent,
                        ssh_shim=shim,
                    )
                )

            source_before = query_refs(
                fixture.source_remote,
                cwd=root,
                environment=environments[0],
                git_executable=system_git,
            )
            if source_before.get("refs/heads/main") != fixture.source_head:
                raise LiveProviderError("the source main ref differs from the fixture")
            source_digest = refs_digest(source_before)
            if handoff is not None and source_digest != handoff.source_refs_digest:
                raise LiveProviderError("the source refs differ from the provider reset handoff")
            destination_before = query_refs(
                fixture.destination_remote,
                cwd=root,
                environment=environments[0],
                git_executable=system_git,
            )
            if destination_before:
                raise LiveProviderError("the Phase 2 destination is not empty")
            verify_template_marker(
                fixture,
                root=root,
                environment=environments[0],
                git_executable=system_git,
            )

            candidate_environment = root / "candidate"
            venv.EnvBuilder(with_pip=True).create(candidate_environment)
            python = environment_python(candidate_environment)
            run(
                [str(python), "-m", "pip", "install", str(copied_wheel)],
                cwd=root,
                environment=environments[0],
                timeout=900,
            )
            installed = run(
                [
                    str(python),
                    "-c",
                    "from importlib.metadata import version; print(version('prodockit'))",
                ],
                cwd=root,
                environment=environments[0],
            ).stdout.strip()
            if installed != wheel.version:
                raise LiveProviderError("the installed candidate version differs from the wheel")

            # Recheck immediately before the candidate receives the identity.
            if (
                query_refs(
                    fixture.source_remote,
                    cwd=root,
                    environment=environments[0],
                    git_executable=system_git,
                )
                != source_before
            ):
                raise LiveProviderError("the template refs changed during preflight")
            if query_refs(
                fixture.destination_remote,
                cwd=root,
                environment=environments[0],
                git_executable=system_git,
            ):
                raise LiveProviderError("the destination changed during preflight")

            environment_files = []
            for number, environment in enumerate(environments, start=1):
                path = root / f"environment-{number}.json"
                path.write_text(json.dumps(environment), encoding="utf-8")
                path.chmod(0o600)
                environment_files.append(path)
            worker_report = root / "worker-report.json"
            run_candidate_worker(
                [
                    str(python),
                    str(Path(__file__).resolve()),
                    "--worker",
                    "--fixture",
                    str(copied_fixture),
                    "--root",
                    str(root),
                    "--ssh-shim-one",
                    str(shims[0]),
                    "--ssh-shim-two",
                    str(shims[1]),
                    "--environment-one",
                    str(environment_files[0]),
                    "--environment-two",
                    str(environment_files[1]),
                    "--worker-report",
                    str(worker_report),
                ],
                cwd=root,
                environment=environments[0],
                timeout=1800,
            )
            raw = json.loads(worker_report.read_text(encoding="utf-8"))
            summary = validate_worker_report(raw, fixture, wheel.version, temporary_root=root)
            commit = summary["path_one"]["commit"]
            destination_after = query_refs(
                fixture.destination_remote,
                cwd=root,
                environment=environments[0],
                git_executable=system_git,
            )
            provider_refs = validate_destination_refs(
                destination_after,
                fixture=fixture,
                expected_commit=commit,
            )
            source_after = query_refs(
                fixture.source_remote,
                cwd=root,
                environment=environments[0],
                git_executable=system_git,
            )
            if source_after != source_before:
                raise LiveProviderError("the source refs changed during Phase 2")
            verify_destination(
                fixture,
                root=root,
                environment=environments[0],
                git_executable=system_git,
                expected_commit=commit,
                expected_tree=summary["path_one"]["tree"],
            )
            final_destination = query_refs(
                fixture.destination_remote,
                cwd=root,
                environment=environments[0],
                git_executable=system_git,
            )
            validate_destination_refs(
                final_destination,
                fixture=fixture,
                expected_commit=commit,
            )
            validate_exclusive_agent(args.agent_socket, fingerprint)
            summary.update(
                {
                    "passed": True,
                    "wheel_sha256": wheel.sha256,
                    "source_refs_digest": source_digest,
                    "source_refs_unchanged": True,
                    "destination_transition": "empty -> refs/heads/main",
                    "provider_created_refs": list(provider_refs),
                    "operating_system": platform.platform(),
                    "architecture": platform.machine(),
                    "started_at_utc": started,
                    "finished_at_utc": utc_now(),
                    "manual_provider_review_required": handoff is None,
                }
            )
        except (LiveProviderError, OSError, ValueError, subprocess.SubprocessError) as error:
            failure = str(error).replace(str(root), "<temporary-home>")
            if environments:
                write_outcome = classify_destination_after_failure(
                    fixture,
                    root=root,
                    environment=environments[0],
                    git_executable=system_git,
                )
                try:
                    source_refs_after_failure = (
                        query_refs(
                            fixture.source_remote,
                            cwd=root,
                            environment=environments[0],
                            git_executable=system_git,
                        )
                        == source_before
                    )
                except (LiveProviderError, OSError, subprocess.SubprocessError):
                    source_refs_after_failure = None
            summary = None

    if summary is None:
        summary = {
            "passed": False,
            "provider": fixture.provider,
            "repository": f"{fixture.destination_namespace}/{fixture.destination_project}",
            "candidate_version": wheel.version,
            "wheel_sha256": wheel.sha256,
            "source_refs_digest": refs_digest(source_before) if source_before else None,
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "failure": failure,
            "write_outcome": write_outcome,
            "source_refs_unchanged": source_refs_after_failure,
            "manual_provider_review_required": True,
        }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    report_path.chmod(0o600)
    if not summary["passed"]:
        raise LiveProviderError(summary["failure"])
    print(f"Phase 2 passed; revoke the deploy key and review provider activity: {report_path}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run both Bootstrap repository paths with one bounded provider write"
    )
    result.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--ssh-shim-one", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--ssh-shim-two", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--environment-one", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--environment-two", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--worker-report", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--wheel", type=Path)
    result.add_argument("--provider", choices=sorted(PROVIDER_HOSTS))
    result.add_argument("--fixture", required=True, type=Path)
    result.add_argument("--agent-socket", type=Path)
    result.add_argument("--key-fingerprint", default="")
    result.add_argument("--known-hosts", type=Path)
    result.add_argument("--expected-wheel-sha256", default="")
    result.add_argument("--report", type=Path)
    result.add_argument("--reset-handoff", type=Path)
    result.add_argument("--release-commit")
    result.add_argument("--confirm-read-write", action="store_true")
    return result


def fail(message: str) -> NoReturn:
    print(f"live-provider Phase 2 failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    args = parser().parse_args()
    try:
        if args.worker:
            worker_required = (
                args.root,
                args.ssh_shim_one,
                args.ssh_shim_two,
                args.environment_one,
                args.environment_two,
                args.worker_report,
            )
            if any(value is None for value in worker_required):
                raise LiveProviderError("incomplete Phase 2 worker arguments")
            worker(args)
            return
        controller_required = (
            args.wheel,
            args.provider,
            args.agent_socket,
            args.key_fingerprint,
            args.known_hosts,
            args.report,
        )
        if any(value is None or value == "" for value in controller_required):
            raise LiveProviderError(
                "--wheel, --provider, --agent-socket, "
                "--key-fingerprint, --known-hosts and --report are required"
            )
        controller(args)
    except LiveProviderError as error:
        fail(str(error))


if __name__ == "__main__":
    main()
