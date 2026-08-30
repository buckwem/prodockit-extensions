# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise Bootstrap's existing-repository path against a real Git provider.

This is a deliberately narrow, manually authorised phase-one harness.  It
installs an approved candidate wheel in a disposable environment, gives it a
repository-scoped read-only deploy key, and runs only Bootstrap stages that
cannot write to the provider.  Provider lifecycle and push testing belong to a
later phase with different credentials.

The retained report contains no key material or temporary paths.  The complete
temporary home, agent and clone are removed on every exit path.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import venv
import zipfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.parser import Parser
from pathlib import Path
from typing import Any, NoReturn

SURREY_NAMESPACE = "assessment-liveprovider-2026"
SURREY_PROJECT = "report-liveprovider-2026-mb0105"
SURREY_HOSTNAME = "gitlab.surrey.ac.uk"
SURREY_REMOTE = (
    "git@gitlab.surrey.ac.uk:"
    "assessment-liveprovider-2026/report-liveprovider-2026-mb0105.git"
)

PROVIDER_HOSTS = {
    "github": ("github.com", "github"),
    "surrey": (SURREY_HOSTNAME, "gitlab"),
}
SELECTED_STAGE_IDS = (
    "ssh-upload",
    "own-project",
    "clone-source",
    "clone",
    "fresh-history",
    "remote",
)
SECRET_ENVIRONMENT_NAMES = {
    "CI_JOB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
    "GLAB_TOKEN",
    "GIT_ASKPASS",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "SSH_ASKPASS",
    "SSH_AGENT_PID",
    "SSH_AUTH_SOCK",
}
WORKER_SUMMARY_KEYS = {
    "provider",
    "repository",
    "candidate_version",
    "expected_head",
    "observed_head",
    "clean_tree",
    "stages",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")
OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class LiveProviderError(RuntimeError):
    """The live-provider run crossed or could not prove its safety boundary."""


@dataclass(frozen=True)
class Fixture:
    """The exact non-secret repository the reviewer authorised."""

    provider: str
    hostname: str
    namespace: str
    project: str
    remote: str
    marker_path: str
    marker_sha256: str

    @classmethod
    def read(cls, path: Path) -> Fixture:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LiveProviderError(f"could not read the fixture allowlist: {error}") from error
        if not isinstance(value, dict):
            raise LiveProviderError("the fixture allowlist must be one JSON object")
        required = {
            "provider",
            "hostname",
            "namespace",
            "project",
            "remote",
            "marker_path",
            "marker_sha256",
        }
        unknown = set(value) - required
        missing = required - set(value)
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing {', '.join(sorted(missing))}")
            if unknown:
                details.append(f"unknown {', '.join(sorted(unknown))}")
            raise LiveProviderError("invalid fixture allowlist: " + "; ".join(details))
        if not all(isinstance(value[name], str) for name in required):
            raise LiveProviderError("every fixture allowlist value must be text")
        fixture = cls(**value)
        fixture.validate()
        return fixture

    def validate(self) -> None:
        if self.provider not in PROVIDER_HOSTS:
            raise LiveProviderError(f"unsupported provider {self.provider!r}")
        hostname, _key_suffix = PROVIDER_HOSTS[self.provider]
        if self.hostname != hostname:
            raise LiveProviderError(
                f"{self.provider} must use {hostname}, not {self.hostname or '<blank>'}"
            )
        expected_remote = f"git@{hostname}:{self.namespace}/{self.project}.git"
        if self.remote != expected_remote:
            raise LiveProviderError(
                f"fixture remote must be exactly {expected_remote}, not {self.remote}"
            )
        if self.provider == "surrey" and (
            self.namespace != SURREY_NAMESPACE
            or self.project != SURREY_PROJECT
            or self.remote != SURREY_REMOTE
        ):
            raise LiveProviderError(
                "the Surrey phase-one fixture must be derived from account mb0105, "
                "course liveprovider, First assessment, year 2026"
            )
        marker = Path(self.marker_path)
        if marker.is_absolute() or ".." in marker.parts or not marker.parts:
            raise LiveProviderError("marker_path must be a relative path within the fixture")
        if not SHA256_RE.fullmatch(self.marker_sha256):
            raise LiveProviderError("marker_sha256 must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True)
class WheelInfo:
    path: Path
    version: str
    sha256: str


@dataclass(frozen=True)
class Agent:
    socket: str
    pid: str


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str
    detail: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_wheel(path: Path, expected_sha256: str) -> WheelInfo:
    """Verify the candidate is exactly the approved Prodockit wheel."""
    path = path.expanduser().resolve()
    if not path.is_file() or path.suffix != ".whl":
        raise LiveProviderError(f"candidate is not a wheel file: {path}")
    expected = expected_sha256.strip().lower()
    if not SHA256_RE.fullmatch(expected):
        raise LiveProviderError("expected wheel SHA-256 must be 64 hexadecimal characters")
    actual = sha256_file(path)
    if not hmac.compare_digest(actual, expected):
        raise LiveProviderError(f"candidate wheel SHA-256 is {actual}, expected {expected}")
    try:
        with zipfile.ZipFile(path) as archive:
            metadata_names = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise LiveProviderError(
                    f"candidate wheel contains {len(metadata_names)} METADATA records"
                )
            metadata = Parser().parsestr(
                archive.read(metadata_names[0]).decode("utf-8", errors="strict")
            )
    except (OSError, UnicodeError, zipfile.BadZipFile) as error:
        raise LiveProviderError(f"could not inspect candidate wheel: {error}") from error
    name = metadata.get("Name", "")
    version = metadata.get("Version", "")
    if name.casefold() != "prodockit" or not version:
        raise LiveProviderError(f"candidate metadata is {name or '<blank>'} {version or '<blank>'}")
    filename_version = re.sub(r"[^A-Za-z0-9.]+", "_", version)
    if not path.name.startswith(f"prodockit-{filename_version}-"):
        raise LiveProviderError(
            f"wheel filename {path.name!r} does not match embedded version {version!r}"
        )
    return WheelInfo(path=path, version=version, sha256=actual)


def validate_private_key(path: Path, *, normal_home: Path, checkout: Path) -> tuple[Path, Path]:
    """Reject keys stored in the ordinary SSH home, source tree or OneDrive."""
    private = path.expanduser().resolve()
    public = (
        private.with_suffix(private.suffix + ".pub")
        if private.suffix
        else private.with_suffix(".pub")
    )
    if not private.is_file() or not private.stat().st_size:
        raise LiveProviderError("the private deploy key is missing or empty")
    if not public.is_file() or not public.stat().st_size:
        raise LiveProviderError(f"the public key beside {private.name} is missing")
    forbidden = (normal_home.expanduser().resolve() / ".ssh", checkout.resolve())
    if any(private.is_relative_to(root) for root in forbidden):
        raise LiveProviderError(
            "the deploy key must be outside the normal .ssh directory and source checkout"
        )
    if "onedrive" in str(private).casefold():
        raise LiveProviderError("the deploy key must not be stored in OneDrive")
    if private.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise LiveProviderError("the private deploy key must not be accessible by group or others")
    return private, public


def require_passphrase_protected_key(path: Path) -> None:
    """Reject an otherwise valid key that can be opened with no passphrase."""
    executable = shutil.which("ssh-keygen")
    if executable is None:
        raise LiveProviderError("ssh-keygen is required to inspect the deploy key")
    try:
        result = subprocess.run(
            [executable, "-y", "-P", "", "-f", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LiveProviderError("could not inspect the deploy key") from error
    if result.returncode == 0:
        raise LiveProviderError("the repository deploy key must be protected by a passphrase")


def validate_known_hosts(path: Path, hostname: str) -> Path:
    """Require a reviewed, provider-specific, non-wildcard host-key file."""
    path = path.expanduser().resolve()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise LiveProviderError(f"could not read known_hosts: {error}") from error
    records = [line.split() for line in lines if line.strip() and not line.lstrip().startswith("#")]
    if not records or any(len(record) < 3 for record in records):
        raise LiveProviderError("known_hosts must contain at least one complete host-key record")
    allowed_names = {hostname, f"[{hostname}]:22"}
    for record in records:
        names = set(record[0].split(","))
        if not names or not names.issubset(allowed_names):
            raise LiveProviderError(
                "known_hosts may contain only the exact selected provider hostname"
            )
    return path


def private_metadata_path(
    path: Path,
    *,
    label: str,
    checkout: Path,
    must_exist: bool,
) -> Path:
    """Keep provider allowlists and retained records out of synced source."""
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(checkout.resolve()) or "onedrive" in str(resolved).casefold():
        raise LiveProviderError(
            f"the {label} must be outside the source checkout and OneDrive"
        )
    if must_exist and not resolved.is_file():
        raise LiveProviderError(f"the {label} is missing")
    return resolved


def parse_refs(text: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 2 or not OBJECT_ID_RE.fullmatch(fields[0]) or not fields[1].startswith(
            "refs/"
        ):
            raise LiveProviderError(f"unexpected ls-remote output on line {number}")
        object_id, name = fields
        if name in refs:
            raise LiveProviderError(f"duplicate remote ref {name}")
        refs[name] = object_id
    return refs


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int = 300,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=environment,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        output = f"{result.stdout}\n{result.stderr}".strip() if capture else ""
        raise LiveProviderError(f"command failed: {Path(command[0]).name}: {output}")
    return result


def start_agent(environment: dict[str, str], socket: Path, cwd: Path) -> Agent:
    result = run(
        ["ssh-agent", "-a", str(socket), "-s"], cwd=cwd, environment=environment
    )
    socket_match = re.search(r"SSH_AUTH_SOCK=([^;\n]+)", result.stdout)
    pid_match = re.search(r"SSH_AGENT_PID=([0-9]+)", result.stdout)
    if socket_match is None or pid_match is None:
        raise LiveProviderError("ssh-agent did not return its socket and process ID")
    return Agent(socket=socket_match.group(1), pid=pid_match.group(1))


def stop_agent(agent: Agent | None, environment: dict[str, str], cwd: Path) -> str | None:
    """Terminate the isolated agent and return a redacted failure, if any."""
    if agent is None:
        return None
    cleanup = dict(environment)
    cleanup["SSH_AUTH_SOCK"] = agent.socket
    cleanup["SSH_AGENT_PID"] = agent.pid
    try:
        result = subprocess.run(
            ["ssh-agent", "-k"],
            cwd=cwd,
            env=cleanup,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "could not terminate the isolated SSH agent"
    if result.returncode:
        return "could not terminate the isolated SSH agent"
    return None


def make_ssh_shim(bin_dir: Path, system_ssh: Path, ssh_config: Path) -> Path:
    """Add the isolated config to direct production ``ssh -T`` checks."""
    shim = bin_dir / "ssh"
    shim.write_text(
        "#!/bin/sh\n"
        f"exec {shlex.quote(str(system_ssh))} -F {shlex.quote(str(ssh_config))} \"$@\"\n",
        encoding="utf-8",
    )
    shim.chmod(0o700)
    return shim


def isolated_environment(
    *, home: Path, bin_dir: Path, git_config: Path, agent: Agent, ssh_shim: Path
) -> dict[str, str]:
    """Build an environment that cannot inherit a user or CI credential."""
    environment = dict(os.environ)
    for name in SECRET_ENVIRONMENT_NAMES:
        environment.pop(name, None)
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": str(git_config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": os.pathsep.join((str(bin_dir), environment.get("PATH", ""))),
            "PYTHONUTF8": "1",
            "SSH_AGENT_PID": agent.pid,
            "SSH_AUTH_SOCK": agent.socket,
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


def environment_python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def authorised_plan(
    stage_id: str,
    commands: list[list[str]],
    cwd: str | None,
    fixture: Fixture,
    project: Path,
) -> None:
    """Reject any generated command outside phase one's read-only boundary."""
    if stage_id == "clone":
        allowed = [["git", "clone", fixture.remote, str(project)]]
        normalised = [[Path(command[0]).name, *command[1:]] for command in commands]
        if normalised == allowed and cwd is None:
            return
    elif stage_id == "fresh-history":
        allowed = [["git", "config", "core.fileMode", "false"]]
        normalised = [[Path(command[0]).name, *command[1:]] for command in commands]
        if normalised == allowed and cwd == str(project):
            return
    raise LiveProviderError(f"stage {stage_id} generated a command outside phase one")


def git_output(
    arguments: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    executable: str = "git",
) -> str:
    return run([executable, *arguments], cwd=cwd, environment=environment).stdout.strip()


def remote_refs(
    fixture: Fixture,
    *,
    cwd: Path,
    environment: dict[str, str],
    git_executable: str = "git",
) -> dict[str, str]:
    output = git_output(
        ["ls-remote", "--refs", fixture.remote],
        cwd=cwd,
        environment=environment,
        executable=git_executable,
    )
    refs = parse_refs(output)
    if not refs:
        raise LiveProviderError("the fixture repository advertises no branches or tags")
    return refs


@contextmanager
def unchanged_remote_refs(
    fixture: Fixture,
    *,
    expected_head: str,
    cwd: Path,
    environment: dict[str, str],
    git_executable: str = "git",
) -> Iterator[dict[str, str]]:
    """Prove the provider refs did not change, including after a failed stage."""
    before = remote_refs(
        fixture,
        cwd=cwd,
        environment=environment,
        git_executable=git_executable,
    )
    if before.get("refs/heads/main") != expected_head:
        raise LiveProviderError("remote main changed before Bootstrap started")
    try:
        yield before
    finally:
        try:
            after = remote_refs(
                fixture,
                cwd=cwd,
                environment=environment,
                git_executable=git_executable,
            )
        except Exception as error:
            raise LiveProviderError(
                "could not verify provider refs after the read-only run"
            ) from error
        if before != after:
            raise LiveProviderError("provider refs changed during the read-only run")


def verify_clone(
    *,
    project: Path,
    fixture: Fixture,
    expected_head: str,
    environment: dict[str, str],
    git_executable: str = "git",
) -> dict[str, Any]:
    observed: dict[str, Any] = {
        "head": git_output(
            ["rev-parse", "HEAD"],
            cwd=project,
            environment=environment,
            executable=git_executable,
        ),
        "main": git_output(
            ["rev-parse", "refs/heads/main"],
            cwd=project,
            environment=environment,
            executable=git_executable,
        ),
        "origin_main": git_output(
            ["rev-parse", "refs/remotes/origin/main"],
            cwd=project,
            environment=environment,
            executable=git_executable,
        ),
        "branch": git_output(
            ["branch", "--show-current"],
            cwd=project,
            environment=environment,
            executable=git_executable,
        ),
        "ahead_behind": git_output(
            ["rev-list", "--left-right", "--count", "main...origin/main"],
            cwd=project,
            environment=environment,
            executable=git_executable,
        ),
        "status": git_output(
            ["status", "--short"],
            cwd=project,
            environment=environment,
            executable=git_executable,
        ),
        "origin": git_output(
            ["remote", "get-url", "origin"],
            cwd=project,
            environment=environment,
            executable=git_executable,
        ),
        "push_urls": git_output(
            ["remote", "get-url", "--push", "--all", "origin"],
            cwd=project,
            environment=environment,
            executable=git_executable,
        ).splitlines(),
    }
    for name in ("head", "main", "origin_main"):
        if observed[name] != expected_head:
            raise LiveProviderError(f"cloned {name} does not match the approved main commit")
    if observed["branch"] != "main":
        raise LiveProviderError("the cloned fixture is not on main")
    if observed["ahead_behind"].split() != ["0", "0"]:
        raise LiveProviderError("the cloned main branch differs from origin/main")
    if observed["status"]:
        raise LiveProviderError("the cloned fixture has uncommitted changes")
    if observed["origin"] != fixture.remote or observed["push_urls"] != [fixture.remote]:
        raise LiveProviderError("the cloned origin or its push URL differs from the allowlist")
    marker = project / fixture.marker_path
    if not marker.is_file() or sha256_file(marker) != fixture.marker_sha256:
        raise LiveProviderError("the cloned fixture marker is missing or changed")
    return observed


def require_ok(result: Any, stage_id: str) -> StageResult:
    status = result.status.value
    recorded = StageResult(stage=stage_id, status=status, detail=result.detail)
    if result.needs_work:
        raise LiveProviderError(f"Bootstrap stage {stage_id} reported {status}: {result.detail}")
    return recorded


def redacted_stage(result: StageResult, temporary_root: Path) -> StageResult:
    """Keep disposable paths out of the retained report."""
    return StageResult(
        stage=result.stage,
        status=result.status,
        detail=result.detail.replace(str(temporary_root), "<temporary-home>"),
    )


def validate_worker_summary(
    value: object,
    *,
    fixture: Fixture,
    candidate_version: str,
    expected_head: str,
    temporary_root: Path,
) -> dict[str, Any]:
    """Accept only the small, expected report emitted by the trusted worker."""
    if not isinstance(value, dict) or set(value) != WORKER_SUMMARY_KEYS:
        raise LiveProviderError("the candidate worker returned an invalid report schema")
    expected_values = {
        "provider": fixture.provider,
        "repository": f"{fixture.namespace}/{fixture.project}",
        "candidate_version": candidate_version,
        "expected_head": expected_head,
        "observed_head": expected_head,
        "clean_tree": True,
    }
    for name, expected in expected_values.items():
        if value.get(name) != expected:
            raise LiveProviderError(f"the candidate worker returned an invalid {name}")
    stages = value.get("stages")
    if not isinstance(stages, list) or len(stages) != len(SELECTED_STAGE_IDS):
        raise LiveProviderError("the candidate worker returned an invalid stage list")
    for expected_id, stage in zip(SELECTED_STAGE_IDS, stages, strict=True):
        if not isinstance(stage, dict) or set(stage) != {"stage", "status", "detail"}:
            raise LiveProviderError("the candidate worker returned an invalid stage result")
        if stage.get("stage") != expected_id or stage.get("status") != "ok":
            raise LiveProviderError(
                f"the candidate worker did not verify Bootstrap stage {expected_id}"
            )
        detail = stage.get("detail")
        if not isinstance(detail, str) or str(temporary_root) in detail:
            raise LiveProviderError(
                f"the candidate worker returned unsafe detail for stage {expected_id}"
            )
    return dict(value)


def worker(args: argparse.Namespace) -> None:
    """Run with the candidate wheel's interpreter and imports."""
    from importlib.metadata import version

    from prodockit.bootstrap import (
        STAGES,
        BootstrapConfig,
        SubprocessRunner,
        apply_stage,
        build_context,
        forget_contacts,
        save,
    )

    fixture = Fixture.read(args.fixture)
    project = args.root / "checkout" / fixture.project
    setup = project.parent
    if project.exists() or any(setup.iterdir()):
        raise LiveProviderError("the target checkout directory is not empty")
    config = BootstrapConfig(
        full_name="Prodockit live-provider test",
        email="live-provider-test@example.invalid",
        username="mb0105" if fixture.provider == "surrey" else fixture.namespace,
        host=fixture.hostname,
        namespace=fixture.namespace,
        project_name=fixture.project,
        project_dir=str(project),
        source_url=fixture.remote,
        history="keep",
    )
    save(setup / ".pdkboot.toml", config)
    context = build_context(
        config,
        runner=SubprocessRunner(git_ssh_executable=str(args.ssh_shim)),
        home=args.root,
        guided=True,
    )
    stages = {stage.id: stage for stage in STAGES}
    missing = set(SELECTED_STAGE_IDS) - set(stages)
    if missing:
        raise LiveProviderError(
            "candidate wheel is missing required Bootstrap stages: " + ", ".join(sorted(missing))
        )

    environment = dict(os.environ)
    for stage_id in ("ssh-upload", "own-project", "clone-source"):
        require_ok(stages[stage_id].check(context), stage_id)

    clone = stages["clone"]
    initial_clone = clone.check(context)
    if not initial_clone.needs_work:
        raise LiveProviderError(
            "Bootstrap did not identify the empty checkout as needing a clone"
        )
    clone_plan = clone.plan(context)
    authorised_plan("clone", clone_plan.commands, clone_plan.cwd, fixture, project)
    applied_clone = apply_stage(context, clone, clone_plan)
    if not applied_clone.ok:
        detail = applied_clone.verified.detail if applied_clone.verified else "clone command failed"
        raise LiveProviderError(f"Bootstrap clone stage failed: {detail}")

    history = stages["fresh-history"]
    history_check = history.check(context)
    if history_check.needs_work:
        history_plan = history.plan(context)
        authorised_plan("fresh-history", history_plan.commands, history_plan.cwd, fixture, project)
        applied_history = apply_stage(context, history, history_plan)
        if not applied_history.ok:
            detail = (
                applied_history.verified.detail
                if applied_history.verified
                else "configuration failed"
            )
            raise LiveProviderError(f"Bootstrap history stage failed: {detail}")

    # A populated fixture cloned from its own remote must already pass this
    # check. Applying its normal sync-repo repair could edit tracked files,
    # which is intentionally outside phase one.
    require_ok(stages["remote"].check(context), "remote")

    # Re-run every selected production check after the local operations. Drop
    # host-contact memoisation first so these are final checks, not old answers.
    forget_contacts(context)
    stage_results = [
        require_ok(stages[stage_id].check(context), stage_id)
        for stage_id in SELECTED_STAGE_IDS
    ]
    observed = verify_clone(
        project=project,
        fixture=fixture,
        expected_head=args.expected_head,
        environment=environment,
    )

    summary = {
        "provider": fixture.provider,
        "repository": f"{fixture.namespace}/{fixture.project}",
        "candidate_version": version("prodockit"),
        "expected_head": args.expected_head,
        "observed_head": observed["head"],
        "clean_tree": True,
        "stages": [asdict(redacted_stage(result, args.root)) for result in stage_results],
    }
    args.worker_report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def controller(args: argparse.Namespace) -> None:
    if platform.system() != "Darwin":
        raise LiveProviderError("phase one is deliberately restricted to an ephemeral macOS run")
    if not args.confirm_read_only:
        raise LiveProviderError("pass --confirm-read-only after reviewing the fixture and command")
    source_checkout = Path(__file__).resolve().parents[1]
    fixture_path = private_metadata_path(
        args.fixture,
        label="fixture allowlist",
        checkout=source_checkout,
        must_exist=True,
    )
    fixture = Fixture.read(fixture_path)
    if fixture.provider != args.provider:
        raise LiveProviderError("--provider does not match the fixture allowlist")
    expected_head = args.expected_head.strip().lower()
    if not OBJECT_ID_RE.fullmatch(expected_head):
        raise LiveProviderError("expected head must be a complete hexadecimal Git object ID")
    wheel = inspect_wheel(args.wheel, args.expected_wheel_sha256)
    private, public = validate_private_key(
        args.private_key, normal_home=Path.home(), checkout=source_checkout
    )
    require_passphrase_protected_key(private)
    known_hosts_path = private_metadata_path(
        args.known_hosts,
        label="known-hosts allowlist",
        checkout=source_checkout,
        must_exist=True,
    )
    known_hosts = validate_known_hosts(known_hosts_path, fixture.hostname)
    system_ssh_name = shutil.which("ssh")
    if system_ssh_name is None:
        raise LiveProviderError("the system ssh client is not installed")
    system_ssh = Path(system_ssh_name).resolve()
    system_git_name = shutil.which("git")
    if system_git_name is None:
        raise LiveProviderError("the system Git client is not installed")
    system_git = str(Path(system_git_name).resolve())
    report = private_metadata_path(
        args.report,
        label="retained report",
        checkout=source_checkout,
        must_exist=False,
    )
    started = utc_now()
    print("Prodockit Bootstrap live-provider Phase 1 — read-only")
    print(f"  Provider:   {fixture.hostname}")
    print(f"  Repository: {fixture.namespace}/{fixture.project}")
    print(f"  Candidate:  prodockit {wheel.version} ({wheel.sha256})")
    print(f"  Remote main: {expected_head}")
    print("  Boundary:   authenticate, inspect and clone; no provider write credential")
    print("  Output:     one redacted private report; temporary home removed")
    inherited_agent = os.environ.get("SSH_AUTH_SOCK")
    agent: Agent | None = None
    summary: dict[str, Any] | None = None
    failure: str | None = None

    with tempfile.TemporaryDirectory(prefix="prodockit-live-provider-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        ssh_dir = root / ".ssh"
        bin_dir = root / "bin"
        checkout = root / "checkout"
        for directory in (ssh_dir, bin_dir, checkout):
            directory.mkdir(mode=0o700)
        try:
            copied_fixture = root / "fixture.json"
            copied_fixture.write_text(
                json.dumps(asdict(fixture), indent=2) + "\n", encoding="utf-8"
            )
            copied_fixture.chmod(0o400)
            if Fixture.read(copied_fixture) != fixture:
                raise LiveProviderError("the copied fixture allowlist changed")
            copied_wheel = root / wheel.path.name
            shutil.copyfile(wheel.path, copied_wheel)
            copied_wheel.chmod(0o400)
            if sha256_file(copied_wheel) != wheel.sha256:
                raise LiveProviderError("the copied candidate wheel changed")
            _hostname, key_suffix = PROVIDER_HOSTS[fixture.provider]
            copied_private = ssh_dir / f"id_ed25519_{key_suffix}"
            copied_public = copied_private.with_suffix(".pub")
            copied_known_hosts = ssh_dir / "known_hosts"
            shutil.copyfile(private, copied_private)
            shutil.copyfile(public, copied_public)
            shutil.copyfile(known_hosts, copied_known_hosts)
            copied_private.chmod(0o600)
            copied_public.chmod(0o600)
            copied_known_hosts.chmod(0o600)
        except OSError as error:
            raise LiveProviderError(
                "could not prepare the isolated candidate, fixture and SSH files"
            ) from error
        validate_known_hosts(copied_known_hosts, fixture.hostname)
        ssh_config = ssh_dir / "config"
        ssh_config.write_text(
            f"Host {fixture.hostname}\n"
            f"    HostName {fixture.hostname}\n"
            "    User git\n"
            f"    IdentityFile {copied_private}\n"
            "    IdentitiesOnly yes\n"
            "    BatchMode yes\n"
            "    StrictHostKeyChecking yes\n"
            f"    UserKnownHostsFile {copied_known_hosts}\n"
            "    GlobalKnownHostsFile /dev/null\n"
            "    ConnectTimeout 10\n",
            encoding="utf-8",
        )
        ssh_config.chmod(0o600)
        ssh_shim = make_ssh_shim(bin_dir, system_ssh, ssh_config)

        base_environment = dict(os.environ)
        for name in SECRET_ENVIRONMENT_NAMES:
            base_environment.pop(name, None)
        try:
            agent = start_agent(base_environment, root / "agent.sock", root)
            environment = isolated_environment(
                home=root,
                bin_dir=bin_dir,
                git_config=root / ".gitconfig",
                agent=agent,
                ssh_shim=ssh_shim,
            )
            if inherited_agent and environment["SSH_AUTH_SOCK"] == inherited_agent:
                raise LiveProviderError("the isolated run inherited the user's SSH agent")
            print("Load the repository-scoped read-only deploy key when prompted.")
            run(
                ["ssh-add", str(copied_private)],
                cwd=root,
                environment=environment,
                timeout=120,
                capture=False,
            )

            with unchanged_remote_refs(
                fixture,
                expected_head=expected_head,
                cwd=root,
                environment=environment,
                git_executable=system_git,
            ):
                candidate_environment = root / ".venv"
                venv.EnvBuilder(with_pip=True).create(candidate_environment)
                python = environment_python(candidate_environment)
                run(
                    [str(python), "-m", "pip", "install", str(copied_wheel)],
                    cwd=root,
                    environment=environment,
                    timeout=900,
                )
                installed = run(
                    [
                        str(python),
                        "-c",
                        "from importlib.metadata import version; print(version('prodockit'))",
                    ],
                    cwd=root,
                    environment=environment,
                ).stdout.strip()
                if installed != wheel.version:
                    raise LiveProviderError(
                        f"installed candidate is {installed}, approved wheel is {wheel.version}"
                    )

                worker_report = root / "worker-report.json"
                run(
                    [
                        str(python),
                        str(Path(__file__).resolve()),
                        "--worker",
                        "--fixture",
                        str(copied_fixture),
                        "--root",
                        str(root),
                        "--ssh-shim",
                        str(ssh_shim),
                        "--expected-head",
                        expected_head,
                        "--worker-report",
                        str(worker_report),
                    ],
                    cwd=root,
                    environment=environment,
                    timeout=600,
                )
                raw_summary = json.loads(worker_report.read_text(encoding="utf-8"))
                summary = validate_worker_summary(
                    raw_summary,
                    fixture=fixture,
                    candidate_version=wheel.version,
                    expected_head=expected_head,
                    temporary_root=root,
                )
                independently_observed = verify_clone(
                    project=root / "checkout" / fixture.project,
                    fixture=fixture,
                    expected_head=expected_head,
                    environment=environment,
                    git_executable=system_git,
                )
                if independently_observed["head"] != summary["observed_head"]:
                    raise LiveProviderError(
                        "the candidate and independent clone checks disagree"
                    )
            summary.update(
                {
                    "passed": True,
                    "wheel_sha256": wheel.sha256,
                    "unchanged_refs": True,
                    "operating_system": platform.platform(),
                    "architecture": platform.machine(),
                    "started_at_utc": started,
                    "finished_at_utc": utc_now(),
                }
            )
        except (LiveProviderError, OSError, ValueError, subprocess.SubprocessError) as error:
            summary = None
            failure = str(error).replace(str(root), "<temporary-home>")
        finally:
            cleanup_failure = stop_agent(agent, base_environment, root)
            if cleanup_failure is not None:
                summary = None
                failure = (
                    f"{failure}; {cleanup_failure}" if failure is not None else cleanup_failure
                )

    if summary is None:
        summary = {
            "passed": False,
            "provider": fixture.provider,
            "repository": f"{fixture.namespace}/{fixture.project}",
            "candidate_version": wheel.version,
            "wheel_sha256": wheel.sha256,
            "expected_head": expected_head,
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "failure": failure or "phase-one run did not produce a result",
        }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    report.chmod(0o600)
    if not summary["passed"]:
        raise LiveProviderError(summary["failure"])
    print(f"phase-one live-provider test passed; report: {report}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run Bootstrap's read-only existing-repository path against a live provider"
    )
    result.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--ssh-shim", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--worker-report", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--wheel", type=Path, help="approved candidate wheel")
    result.add_argument(
        "--provider", choices=sorted(PROVIDER_HOSTS), help="provider named by the fixture"
    )
    result.add_argument(
        "--fixture", type=Path, required=True, help="reviewed repository allowlist JSON"
    )
    result.add_argument(
        "--private-key", type=Path, help="repository-scoped read-only deploy key"
    )
    result.add_argument(
        "--known-hosts", type=Path, help="reviewed host-key file for this provider only"
    )
    result.add_argument(
        "--expected-wheel-sha256", default="", help="approved candidate wheel SHA-256"
    )
    result.add_argument(
        "--expected-head", default="", help="reviewed complete object ID for remote main"
    )
    result.add_argument("--report", type=Path, help="write the redacted JSON result here")
    result.add_argument(
        "--confirm-read-only",
        action="store_true",
        help="confirm the fixture and read-only operation were reviewed",
    )
    return result


def fail(message: str) -> NoReturn:
    print(f"live-provider test failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    args = parser().parse_args()
    try:
        if args.worker:
            worker_required = (args.root, args.ssh_shim, args.worker_report)
            if any(value is None for value in worker_required):
                raise LiveProviderError("incomplete internal worker arguments")
            worker(args)
            return
        controller_required = (
            args.wheel,
            args.provider,
            args.private_key,
            args.known_hosts,
            args.report,
        )
        if any(value is None for value in controller_required):
            raise LiveProviderError(
                "--wheel, --provider, --private-key, --known-hosts and --report are required"
            )
        controller(args)
    except LiveProviderError as error:
        fail(str(error))


if __name__ == "__main__":
    main()
