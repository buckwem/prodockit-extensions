# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Composable diagnostics and explicitly requested, narrowly scoped repairs."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import io
import json
import ntpath
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import uuid
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from packaging.version import InvalidVersion, Version

import prodockit
from prodockit.config_diagnostics import inspect_config
from prodockit.init_tools import COMPONENT_FILES, init_tools
from prodockit.mathjax import MathJaxError, install_mathjax
from prodockit.pins import (
    DEFAULT_PACKAGES,
    TESTED_VERSIONS,
    PinError,
    apply_version,
    discover,
    resolve_latest,
)
from prodockit.project_config import ProjectConfig, ProjectConfigError, load_project_config
from prodockit.project_integrity import renderer_requirements
from prodockit.renderer_health import find_browser, probe_mathjax, probe_mermaid
from prodockit.renderer_resilience import RetryReporter, run_npm_with_retries
from prodockit.shared_files import SharedFileError
from prodockit.shared_files import apply as apply_shared_files
from prodockit.shared_files import inspect as inspect_shared_files

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by Python 3.10 CI
    import tomli as tomllib

Status = Literal["pass", "warn", "fail"]
RepairDisposition = Literal[
    "confirmable", "online", "manual", "ambiguous", "prohibited", "not-applicable"
]
DryRunStatus = Literal["available", "manual", "refused", "not-needed"]
NODE_AUDIT_LEVEL = "moderate"
REPAIRABLE_DISTRIBUTIONS = ("prodockit", "zensical")

DIAGNOSTIC_IDS = frozenset(
    {
        "environment.python",
        "environment.virtual-env",
        "environment.inspection",
        "installation.commands",
        "installation.dependencies",
        "installation.metadata",
        "installation.inspection",
        "project.configuration",
        "dependencies.pins",
        "dependencies.shared-files",
        "dependencies.inspection",
        "renderer.pandoc",
        "renderer.weasyprint",
        "renderer.node",
        "renderer.npm",
        "renderer.mermaid",
        "renderer.browser",
        "renderer.mathjax",
        "renderer.mermaid-security",
        "renderer.inspection",
        "renderer.security-inspection",
        "repository.git",
        "repository.template-metadata",
        "repository.template-update",
        "repository.inspection",
    }
)


@dataclass(frozen=True)
class RepairPolicy:
    """The permanent repair boundary for one stable diagnostic check."""

    disposition: RepairDisposition
    reason: str
    remediation: str

    def as_dict(self) -> dict[str, str]:
        return {
            "disposition": self.disposition,
            "reason": self.reason,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class RepairChoice:
    """One bounded option a dry run can present without selecting it."""

    id: str
    label: str
    default: bool = False
    command_argv: tuple[str, ...] | None = None
    internal_operation: str | None = None
    affected_paths: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    warning: str | None = None
    warning_severity: Literal["warning", "danger"] | None = None
    network: bool = False
    rollback: str = "not-applicable"

    def __post_init__(self) -> None:
        if (self.command_argv is None) == (self.internal_operation is None):
            raise ValueError("a repair choice needs exactly one command or internal operation")
        if (self.warning is None) != (self.warning_severity is None):
            raise ValueError("repair warning text and severity must be provided together")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "default": self.default,
            "command_argv": list(self.command_argv) if self.command_argv is not None else None,
            "internal_operation": self.internal_operation,
            "affected_paths": list(self.affected_paths),
            "prerequisites": list(self.prerequisites),
            "warning": self.warning,
            "warning_severity": self.warning_severity,
            "network": self.network,
            "rollback": self.rollback,
        }


@dataclass(frozen=True)
class RepairCandidate:
    """Dry-run result for one diagnostic problem or bounded decision."""

    id: str
    check_id: str
    disposition: RepairDisposition
    status: DryRunStatus
    summary: str
    reason: str
    remediation: str
    choices: tuple[RepairChoice, ...] = ()

    def __post_init__(self) -> None:
        defaults = sum(choice.default for choice in self.choices)
        if self.choices and defaults != 1:
            raise ValueError("repair choices need exactly one default")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "check_id": self.check_id,
            "disposition": self.disposition,
            "status": self.status,
            "summary": self.summary,
            "reason": self.reason,
            "remediation": self.remediation,
            "choices": [choice.as_dict() for choice in self.choices],
        }


@dataclass(frozen=True)
class RepairDryRun:
    """Every possible repair for one immutable diagnostic report."""

    candidates: tuple[RepairCandidate, ...]
    selected_checks: tuple[str, ...] = ()

    @property
    def counts(self) -> dict[str, int]:
        return {
            status: sum(candidate.status == status for candidate in self.candidates)
            for status in ("available", "manual", "refused", "not-needed")
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": "dry-run",
            "mutated": False,
            "selected_checks": list(self.selected_checks),
            "summary": self.counts,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


REPAIR_REGISTRY: dict[str, RepairPolicy] = {
    "environment.python": RepairPolicy(
        "manual",
        "Prodockit cannot replace or reselect the Python process that is running it.",
        "Repair or select Python outside Prodockit, then rerun diagnostics.",
    ),
    "environment.virtual-env": RepairPolicy(
        "prohibited",
        "Changing the caller's active shell or editor interpreter is outside the process.",
        "Activate the intended environment and reopen the shell or editor.",
    ),
    "environment.inspection": RepairPolicy(
        "manual",
        "The environment must be inspectable before a safe repair can be planned.",
        "Correct the reported path or permission problem and rerun diagnostics.",
    ),
    "installation.commands": RepairPolicy(
        "prohibited",
        "PATH selection and package reinstallation can affect software outside the project.",
        "Activate the intended environment and compare the reported command locations.",
    ),
    "installation.dependencies": RepairPolicy(
        "prohibited",
        "Resolving package conflicts requires choosing a compatible dependency set.",
        "Run the active Python's `pip check`, then install the project's reviewed pins.",
    ),
    "installation.metadata": RepairPolicy(
        "confirmable",
        "Only metadata proved stale by the active package can be quarantined safely.",
        "Use the scoped metadata quarantine repair from issue #697.",
    ),
    "installation.inspection": RepairPolicy(
        "manual",
        "Installation discovery must succeed before mutation can be bounded.",
        "Correct the reported installation error and rerun diagnostics.",
    ),
    "project.configuration": RepairPolicy(
        "ambiguous",
        "Configuration findings may have several author-valid remediations.",
        "Use `pdk config --check`; prefer Adoption for independent Prodockit integration repairs.",
    ),
    "dependencies.pins": RepairPolicy(
        "ambiguous",
        "A version must be selected before declarations can be aligned.",
        "Choose a detected version and apply it with `pdk pins --set`.",
    ),
    "dependencies.shared-files": RepairPolicy(
        "confirmable",
        "Declared managed files have one installed Prodockit source of truth.",
        "Review, back up, and apply them with `pdk shared-files --apply`.",
    ),
    "dependencies.inspection": RepairPolicy(
        "manual",
        "Unreadable declarations cannot be rewritten safely.",
        "Correct the reported path, encoding, syntax, or permission problem.",
    ),
    "renderer.pandoc": RepairPolicy(
        "prohibited",
        "Pandoc is system software and its installer is platform-dependent.",
        "Install the project's pinned Pandoc version outside diagnostics.",
    ),
    "renderer.weasyprint": RepairPolicy(
        "prohibited",
        "WeasyPrint failures may require native system libraries or architecture changes.",
        "Repair the active Python package and platform libraries outside diagnostics.",
    ),
    "renderer.node": RepairPolicy(
        "prohibited",
        "Node is system software and cannot be replaced as a project-local repair.",
        "Install the supported Node version, then rerun diagnostics.",
    ),
    "renderer.npm": RepairPolicy(
        "prohibited",
        "npm belongs to the system Node installation.",
        "Repair or reinstall the selected Node distribution.",
    ),
    "renderer.mermaid": RepairPolicy(
        "online",
        "A valid project lockfile permits a bounded project-local reinstall.",
        "Prefer Adoption or `pdk init-tools --mermaid`; no template is required.",
    ),
    "renderer.browser": RepairPolicy(
        "prohibited",
        "Browser installation and executable selection affect the host environment.",
        "Install or select Chrome/Chromium outside diagnostics.",
    ),
    "renderer.mathjax": RepairPolicy(
        "online",
        "Committed project inputs can rebuild project-local MathJax tooling and assets.",
        "Prefer Adoption, `pdk init-tools --mathjax`, or `pdk init-mathjax`; "
        "no template is required.",
    ),
    "renderer.mermaid-security": RepairPolicy(
        "prohibited",
        "Security upgrades require advisory and rendered-output review.",
        "Review `npm audit --omit=dev` and update the lockfile explicitly.",
    ),
    "renderer.inspection": RepairPolicy(
        "manual",
        "The renderer must be inspectable before a safe repair can be planned.",
        "Correct the reported path or permission problem and rerun diagnostics.",
    ),
    "renderer.security-inspection": RepairPolicy(
        "manual",
        "An unavailable advisory inspection cannot justify dependency mutation.",
        "Make `npm audit --omit=dev --json` work, then rerun online diagnostics.",
    ),
    "repository.git": RepairPolicy(
        "prohibited",
        "Repository creation and remote selection require author intent.",
        "Install or configure Git and remotes explicitly.",
    ),
    "repository.template-metadata": RepairPolicy(
        "prohibited",
        "A diagnostic repair must not depend on or infer state from prodockit-template.",
        "Recover exact template metadata from this project's version control history.",
    ),
    "repository.template-update": RepairPolicy(
        "manual",
        "A template update is a separately reviewed repository-wide change.",
        "Run `pdk template-sync` to preview it before applying it.",
    ),
    "repository.inspection": RepairPolicy(
        "manual",
        "Repository state must be inspectable before a repair can be bounded.",
        "Correct the reported Git or metadata error and rerun diagnostics.",
    ),
}


@dataclass(frozen=True)
class DiagnosticResult:
    """One stable diagnostic check and the evidence behind its status."""

    id: str
    section: str
    status: Status
    summary: str
    details: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.id not in DIAGNOSTIC_IDS:
            raise ValueError(f"diagnostic {self.id!r} has no registered repair disposition")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "section": self.section,
            "status": self.status,
            "summary": self.summary,
            "details": list(self.details),
            "data": self.data,
            "repair": REPAIR_REGISTRY[self.id].as_dict(),
        }


@dataclass(frozen=True)
class DiagnosticReport:
    """The complete deterministic result returned by :func:`inspect`."""

    config_file: str
    project_root: str
    online: bool
    checks: tuple[DiagnosticResult, ...]

    @property
    def status(self) -> Status:
        statuses = {check.status for check in self.checks}
        if "fail" in statuses:
            return "fail"
        if "warn" in statuses:
            return "warn"
        return "pass"

    @property
    def counts(self) -> dict[str, int]:
        return {
            status: sum(check.status == status for check in self.checks)
            for status in ("pass", "warn", "fail")
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "prodockit_version": prodockit.__version__,
            "status": self.status,
            "config_file": self.config_file,
            "project_root": self.project_root,
            "online": self.online,
            "summary": self.counts,
            "checks": [check.as_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)


@dataclass(frozen=True)
class CommandInfo:
    """A command resolved from PATH and the version it reports."""

    name: str
    path: str | None
    version: str | None
    error: str | None = None


@dataclass(frozen=True)
class DistributionMetadataEntry:
    """One repair-relevant metadata path found in active site-packages."""

    distribution: str
    version: str | None
    path: Path
    valid: bool


@dataclass(frozen=True)
class MetadataRepairResult:
    """Outcome of the opt-in duplicate metadata repair."""

    status: Literal["not-needed", "repaired"]
    moved: tuple[str, ...] = ()
    quarantine: str | None = None
    manifest: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "moved": list(self.moved),
            "quarantine": self.quarantine,
            "manifest": self.manifest,
        }


@dataclass(frozen=True)
class RepairApplyResult:
    """Outcome shared by project-local diagnostic repair adapters."""

    status: Literal["not-needed", "applied"]
    changed: tuple[str, ...] = ()
    quarantine: str | None = None
    manifest: str | None = None


class RepairTransactionError(RuntimeError):
    """A diagnostic repair transaction violated its safety contract."""


class MetadataRepairError(RepairTransactionError):
    """The requested repair cannot be proved safe."""


class RepairRollbackError(RepairTransactionError):
    """A repair failed and its quarantined content could not be restored."""


def _content_sha256(path: Path) -> str:
    """Hash a file or directory tree without following symlinks."""
    digest = hashlib.sha256()
    if path.is_symlink():
        raise RepairTransactionError(f"refusing symlinked repair target: {path}")
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    if not path.is_dir():
        raise RepairTransactionError(f"repair target is not a file or directory: {path}")
    for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        if child.is_symlink():
            raise RepairTransactionError(f"refusing symlink inside repair target: {child}")
        relative = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        if child.is_file():
            digest.update(child.read_bytes())
    return digest.hexdigest()


class RepairTransaction:
    """One confirmed, independently recoverable diagnostic repair.

    The transaction is deliberately filesystem-only. Repair adapters retain
    responsibility for deciding what is safe and for verifying their own
    postcondition; this class supplies containment, quarantine, a durable
    credential-safe manifest, and rollback.
    """

    def __init__(
        self,
        boundary: Path,
        *,
        action_id: str,
        check_id: str,
        choice_id: str,
        timestamp: str | None = None,
    ) -> None:
        self.boundary = boundary.resolve()
        self.action_id = action_id
        self.check_id = check_id
        self.choice_id = choice_id
        self.created = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", self.created):
            raise RepairTransactionError("invalid diagnostic transaction timestamp")
        self.quarantine = self.boundary / ".prodockit-quarantine" / "diagnostics" / self.created
        self.manifest_path = self.quarantine / "manifest.json"
        self._entries: list[dict[str, Any]] = []
        self._restores: list[tuple[str, Path, Path | None]] = []
        self._status = "confirmed"
        self._begun = False

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.boundary).as_posix()
        except ValueError as error:
            raise RepairTransactionError(
                f"refusing repair target outside the permitted boundary: {path}"
            ) from error

    def _write_manifest(self) -> None:
        self.quarantine.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "created": self.created,
            "prodockit_version": prodockit.__version__,
            "status": self._status,
            "action": {
                "id": self.action_id,
                "check_id": self.check_id,
                "choice_id": self.choice_id,
                "confirmation": "y",
            },
            "entries": self._entries,
        }
        temporary = self.quarantine / f".manifest-{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self.manifest_path)
        finally:
            with suppress(FileNotFoundError):
                temporary.unlink()

    def begin(self) -> None:
        """Durably record confirmation before the first mutation."""
        if self._begun or self.manifest_path.exists():
            raise RepairTransactionError(
                f"diagnostic transaction already exists: {self.quarantine}"
            )
        self._begun = True
        self._write_manifest()

    def quarantine_path(
        self,
        path: Path,
        *,
        backup_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Move one contained non-symlink target into this transaction."""
        original = path.absolute()
        self._relative(original)
        if original.is_symlink():
            raise RepairTransactionError(f"refusing symlinked repair target: {original}")
        try:
            resolved = original.resolve(strict=True)
        except OSError as error:
            raise RepairTransactionError(
                f"cannot resolve repair target {original}: {error}"
            ) from error
        self._relative(resolved)
        before_hash = _content_sha256(original)
        backup = Path(os.path.abspath(self.quarantine / "files" / backup_name))
        try:
            backup.relative_to(self.quarantine)
        except ValueError as error:
            raise RepairTransactionError(
                f"refusing quarantine path outside the transaction: {backup}"
            ) from error
        if backup.exists() or backup.is_symlink():
            raise RepairTransactionError(f"duplicate quarantine destination: {backup}")
        backup.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "original": self._relative(original),
            "backup": backup.relative_to(self.quarantine).as_posix(),
            "sha256": before_hash,
            "kind": "directory" if original.is_dir() else "file",
            **(metadata or {}),
        }
        self._entries.append(entry)
        self._write_manifest()
        shutil.move(str(original), str(backup))
        self._restores.append(("move", original, backup))
        self._status = "applying"
        self._write_manifest()

    def backup_path(self, path: Path, *, backup_name: str) -> None:
        """Copy one existing target so a later typed service can edit it."""
        original = path.absolute()
        self._relative(original)
        if original.is_symlink():
            raise RepairTransactionError(f"refusing symlinked repair target: {original}")
        resolved = original.resolve(strict=True)
        self._relative(resolved)
        before_hash = _content_sha256(original)
        backup = Path(os.path.abspath(self.quarantine / "files" / backup_name))
        try:
            backup.relative_to(self.quarantine)
        except ValueError as error:
            raise RepairTransactionError(
                f"refusing quarantine path outside the transaction: {backup}"
            ) from error
        if backup.exists() or backup.is_symlink():
            raise RepairTransactionError(f"duplicate quarantine destination: {backup}")
        backup.parent.mkdir(parents=True, exist_ok=True)
        if original.is_dir():
            shutil.copytree(original, backup)
            kind = "directory"
        else:
            shutil.copy2(original, backup)
            kind = "file"
        self._entries.append(
            {
                "original": self._relative(original),
                "backup": backup.relative_to(self.quarantine).as_posix(),
                "sha256": before_hash,
                "kind": kind,
                "operation": "backup",
            }
        )
        self._restores.append(("copy", original, backup))
        self._status = "applying"
        self._write_manifest()

    def record_creation(self, path: Path) -> None:
        """Record a contained missing path that the repair is about to create."""
        original = path.absolute()
        self._relative(original)
        if original.exists() or original.is_symlink():
            raise RepairTransactionError(f"creation target already exists: {original}")
        ancestor = original.parent
        while not ancestor.exists() and not ancestor.is_symlink():
            if ancestor == self.boundary:
                break
            ancestor = ancestor.parent
        if ancestor.is_symlink():
            raise RepairTransactionError(f"refusing symlinked repair parent: {ancestor}")
        self._relative(ancestor.resolve(strict=True))
        self._entries.append(
            {
                "original": self._relative(original),
                "backup": None,
                "sha256": None,
                "kind": "missing",
                "operation": "create",
            }
        )
        self._restores.append(("create", original, None))
        self._status = "applying"
        self._write_manifest()

    def commit(self) -> None:
        self._status = "applied"
        self._write_manifest()

    def rollback(self, reason: str) -> None:
        failures: list[str] = []
        for operation, original, backup in reversed(self._restores):
            try:
                if operation == "create":
                    if original.is_dir() and not original.is_symlink():
                        shutil.rmtree(original)
                    elif original.exists() or original.is_symlink():
                        original.unlink()
                    parent = original.parent
                    while parent != self.boundary:
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
                    continue
                assert backup is not None
                if operation == "copy" and (original.exists() or original.is_symlink()):
                    if original.is_dir() and not original.is_symlink():
                        shutil.rmtree(original)
                    else:
                        original.unlink()
                elif original.exists() or original.is_symlink():
                    failures.append(f"original path already exists: {original}")
                    continue
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup), str(original))
            except OSError as error:
                failures.append(f"{backup} -> {original}: {error}")
        self._status = "rollback-failed" if failures else "rolled-back"
        try:
            self._write_manifest()
        except OSError as error:
            failures.append(f"could not update {self.manifest_path}: {error}")
        if failures:
            detail = "; ".join(failures)
            raise RepairRollbackError(
                f"repair failed ({reason}) and rollback also failed: {detail}. "
                f"Recover the original paths from {self.quarantine / 'files'} "
                f"using {self.manifest_path}"
            )


if set(REPAIR_REGISTRY) != DIAGNOSTIC_IDS:
    missing = sorted(DIAGNOSTIC_IDS - set(REPAIR_REGISTRY))
    unexpected = sorted(set(REPAIR_REGISTRY) - DIAGNOSTIC_IDS)
    raise RuntimeError(
        f"repair registry does not cover every diagnostic; missing={missing}, "
        f"unexpected={unexpected}"
    )


def _leave_unchanged() -> RepairChoice:
    return RepairChoice(
        "leave-unchanged",
        "Leave unchanged",
        default=True,
        internal_operation="no-op",
    )


def _generic_candidate(check: DiagnosticResult) -> RepairCandidate:
    policy = REPAIR_REGISTRY[check.id]
    status: DryRunStatus = "refused" if policy.disposition == "prohibited" else "manual"
    choices: tuple[RepairChoice, ...] = ()
    return RepairCandidate(
        f"{check.id}.remediation",
        check.id,
        policy.disposition,
        status,
        check.summary,
        policy.reason,
        policy.remediation,
        choices,
    )


def _metadata_candidate(check: DiagnosticResult) -> RepairCandidate:
    policy = REPAIR_REGISTRY[check.id]
    candidates = tuple(str(item) for item in check.data.get("fix_candidates", ()))
    repair_error = check.data.get("repair_error")
    if repair_error:
        return RepairCandidate(
            "installation.metadata.refused",
            check.id,
            "prohibited",
            "refused",
            check.summary,
            str(repair_error),
            policy.remediation,
        )
    if not candidates:
        return RepairCandidate(
            "installation.metadata.manual",
            check.id,
            "manual",
            "manual",
            check.summary,
            "No supported distribution was proved to be a repair candidate.",
            policy.remediation,
        )
    repair_paths = tuple(str(path) for path in check.data.get("repair_paths", ()))
    if not repair_paths:
        return RepairCandidate(
            "installation.metadata.manual",
            check.id,
            "manual",
            "manual",
            check.summary,
            "No obsolete metadata path was proved safe to quarantine.",
            policy.remediation,
        )
    return RepairCandidate(
        "installation.metadata.quarantine-stale",
        check.id,
        policy.disposition,
        "available",
        check.summary,
        policy.reason,
        policy.remediation,
        (
            RepairChoice(
                "quarantine-stale-metadata",
                "Quarantine provably stale Prodockit or Zensical metadata",
                internal_operation="installation.metadata.quarantine-stale",
                affected_paths=repair_paths,
                warning=(
                    "Distribution metadata will move inside the active virtual "
                    "environment; ambiguous entries are refused."
                ),
                warning_severity="warning",
                rollback="restore paths using the quarantine manifest",
            ),
            _leave_unchanged(),
        ),
    )


def _shared_files_candidates(check: DiagnosticResult) -> list[RepairCandidate]:
    policy = REPAIR_REGISTRY[check.id]
    raw_files = check.data.get("drifted_files", ())
    candidates: list[RepairCandidate] = []
    for item in raw_files:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = str(item["path"])
        status = str(item.get("status"))
        path_id = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
        choices: tuple[RepairChoice, ...]
        if status == "different":
            choices = (
                RepairChoice(
                    "review-difference",
                    "Review the installed and project file hashes",
                    command_argv=("pdk", "shared-files", "--verbose"),
                    affected_paths=(path,),
                    rollback="read-only",
                ),
                RepairChoice(
                    "replace-installed-shared-file",
                    "Replace this file from the installed Prodockit release",
                    internal_operation="dependencies.shared-files.apply",
                    affected_paths=(path,),
                    warning=(
                        "This replaces existing managed file bytes and can change "
                        "website or PDF output; review local changes first."
                    ),
                    warning_severity="warning",
                    rollback="restore the original file from the diagnostic quarantine",
                ),
                _leave_unchanged(),
            )
        else:
            choices = (
                RepairChoice(
                    "create-installed-shared-file",
                    "Create this file from the installed Prodockit release",
                    internal_operation="dependencies.shared-files.apply",
                    affected_paths=(path,),
                    warning="This creates a managed file and can change rendered output.",
                    warning_severity="warning",
                    rollback="remove the created file using the diagnostic manifest",
                ),
                _leave_unchanged(),
            )
        candidates.append(
            RepairCandidate(
                f"dependencies.shared-files.{path_id}",
                check.id,
                policy.disposition,
                "available",
                f"Managed shared file is {status}: {path}",
                policy.reason,
                policy.remediation,
                choices,
            )
        )
    return candidates or [_generic_candidate(check)]


def _pin_candidates(check: DiagnosticResult) -> list[RepairCandidate]:
    policy = REPAIR_REGISTRY[check.id]
    candidates: list[RepairCandidate] = []
    supported_mismatches = check.data.get("supported_mismatches", ())
    if supported_mismatches:
        candidates.append(
            RepairCandidate(
                "dependencies.pins.restore-supported-combination",
                check.id,
                "manual",
                "manual",
                (
                    "Declared versions do not match the installed Prodockit "
                    "release's supported combination"
                ),
                (
                    "Selecting and applying a complete dependency combination is a "
                    "dedicated pins workflow, not a diagnostic repair."
                ),
                "Run `pdk pins`, review the declarations, and accept each tested default.",
            )
        )
    packages = check.data.get("packages", ())
    for package_data in packages:
        if not isinstance(package_data, dict):
            continue
        package = str(package_data.get("package", ""))
        versions = tuple(str(item) for item in package_data.get("versions", ()))
        latest = package_data.get("latest")
        exact_versions = tuple(
            dict.fromkeys(
                str(site.get("version"))
                for site in package_data.get("sites", ())
                if isinstance(site, dict) and site.get("operator") == "==" and site.get("version")
            )
        )
        paths = tuple(
            dict.fromkeys(
                str(site.get("path"))
                for site in package_data.get("sites", ())
                if isinstance(site, dict) and site.get("path")
            )
        )
        if len(versions) > 1:
            bounded_versions = exact_versions if len(exact_versions) == 1 else versions
            choices = (
                *(
                    RepairChoice(
                        f"align-{package}-{version}",
                        f"Align every {package} declaration to {version}",
                        command_argv=("pdk", "pins", "--set", f"{package}={version}"),
                        affected_paths=paths,
                        warning=(
                            "Changing version declarations can change website "
                            "and PDF output; rebuild and review both artifacts."
                        ),
                        warning_severity="warning",
                        rollback=(
                            "restore changed declaration files from the diagnostic quarantine"
                        ),
                    )
                    for version in bounded_versions
                ),
                _leave_unchanged(),
            )
            candidates.append(
                RepairCandidate(
                    f"dependencies.pins.align-{package}",
                    check.id,
                    "confirmable" if len(exact_versions) == 1 else "ambiguous",
                    "available",
                    (
                        f"Align inconsistent {package} declarations to the unique "
                        f"exact-build version {bounded_versions[0]}"
                        if len(exact_versions) == 1
                        else f"Choose a version for inconsistent {package} declarations"
                    ),
                    policy.reason,
                    policy.remediation,
                    choices,
                )
            )
        elif (
            latest
            and versions
            and str(latest) != versions[0]
            and package not in supported_mismatches
        ):
            candidates.append(
                RepairCandidate(
                    f"dependencies.pins.review-{package}-update",
                    check.id,
                    "manual",
                    "manual",
                    f"Review {package} {versions[0]} -> {latest}",
                    "A newer version is an author decision, not a diagnostic repair.",
                    f"Review output before running `pdk pins --set {package}={latest}`.",
                )
            )
    return candidates or [_generic_candidate(check)]


def _configuration_candidates(check: DiagnosticResult) -> list[RepairCandidate]:
    """Expose only configuration edits already proved lossless by inspection."""
    policy = REPAIR_REGISTRY[check.id]
    candidates: list[RepairCandidate] = []
    for problem in check.data.get("repairable_problems", ()):
        if not isinstance(problem, dict):
            continue
        operation = str(problem.get("operation", ""))
        problem_id = str(problem.get("id", ""))
        label = str(problem.get("label", ""))
        path = str(check.data.get("config_file", "zensical.toml"))
        if not operation or not problem_id or not label:
            continue
        candidates.append(
            RepairCandidate(
                f"project.configuration.{problem_id}",
                check.id,
                "confirmable",
                "available",
                label,
                policy.reason,
                policy.remediation,
                (
                    RepairChoice(
                        problem_id,
                        label,
                        internal_operation=f"project.configuration.{operation}",
                        affected_paths=(path,),
                        warning=(
                            "This edits only the identified TOML construct and preserves "
                            "comments and unrelated formatting. Rebuild and review the output."
                        ),
                        warning_severity="warning",
                        rollback=(
                            "restore the original configuration from the diagnostic quarantine"
                        ),
                    ),
                    _leave_unchanged(),
                ),
            )
        )
    return candidates or [_generic_candidate(check)]


def _renderer_candidate(check: DiagnosticResult, report: DiagnosticReport) -> RepairCandidate:
    policy = REPAIR_REGISTRY[check.id]
    component = "mermaid" if check.id == "renderer.mermaid" else "mathjax"
    if not report.online:
        return RepairCandidate(
            f"{check.id}.online-required",
            check.id,
            "online",
            "manual",
            check.summary,
            "Renderer installation is disabled unless --online is explicitly supplied.",
            f"Rerun `pdk diag --online --fix --fix-check {check.id}`.",
        )
    node = next((item for item in report.checks if item.id == "renderer.node"), None)
    npm = next((item for item in report.checks if item.id == "renderer.npm"), None)
    refusal = check.data.get("repair_refusal")
    if refusal or node is None or npm is None or node.status != "pass" or npm.status != "pass":
        reason = str(refusal or "Node and npm must both pass their health checks.")
        return RepairCandidate(
            f"{check.id}.refused",
            check.id,
            "prohibited",
            "refused",
            check.summary,
            reason,
            policy.remediation,
        )
    paths = (
        ("tools/mermaid",)
        if component == "mermaid"
        else ("tools/mathjax", "docs/javascripts/mathjax.js", "docs/javascripts/vendor/mathjax")
    )
    return RepairCandidate(
        f"{check.id}.install-locked",
        check.id,
        policy.disposition,
        "available",
        check.summary,
        policy.reason,
        policy.remediation,
        (
            RepairChoice(
                f"install-locked-{component}",
                f"Rebuild project-local {component} support from its lockfile",
                internal_operation=f"{check.id}.install-locked",
                affected_paths=paths,
                prerequisites=(
                    "Node and npm passed diagnostics",
                    "package.json and package-lock.json are valid and mutually consistent",
                    "no author package lifecycle scripts are present",
                ),
                warning=(
                    "npm ci can download and execute locked third-party package install "
                    "scripts. Existing generated files are quarantined before replacement."
                ),
                warning_severity="warning",
                network=True,
                rollback="restore project files and the quarantined generated directory",
            ),
            _leave_unchanged(),
        ),
    )


def build_repair_dry_run(
    report: DiagnosticReport, *, check_ids: tuple[str, ...] = ()
) -> RepairDryRun:
    """Describe every possible repair without selecting or executing one."""
    requested = tuple(dict.fromkeys(check_ids))
    unknown = sorted(set(requested) - DIAGNOSTIC_IDS)
    if unknown:
        raise ValueError(f"unknown diagnostic check ID(s): {', '.join(unknown)}")
    selected = set(requested)
    candidates: list[RepairCandidate] = []
    seen: set[str] = set()
    for check in report.checks:
        if selected and check.id not in selected:
            continue
        seen.add(check.id)
        policy = REPAIR_REGISTRY[check.id]
        if check.status == "pass":
            candidates.append(
                RepairCandidate(
                    f"{check.id}.not-needed",
                    check.id,
                    "not-applicable",
                    "not-needed",
                    check.summary,
                    "The diagnostic passed, so no repair is applicable.",
                    policy.remediation,
                )
            )
        elif check.id == "installation.metadata":
            candidates.append(_metadata_candidate(check))
        elif check.id == "dependencies.shared-files" and check.data.get("drifted"):
            candidates.extend(_shared_files_candidates(check))
        elif check.id == "dependencies.pins":
            candidates.extend(_pin_candidates(check))
        elif check.id in {"renderer.mermaid", "renderer.mathjax"}:
            candidates.append(_renderer_candidate(check, report))
        elif check.id == "project.configuration" and check.data.get("repairable_problems"):
            candidates.extend(_configuration_candidates(check))
        else:
            candidates.append(_generic_candidate(check))
    for check_id in sorted(selected - seen):
        policy = REPAIR_REGISTRY[check_id]
        candidates.append(
            RepairCandidate(
                f"{check_id}.not-emitted",
                check_id,
                "not-applicable",
                "not-needed",
                "The selected check is not applicable to this diagnostic run",
                "The check was not emitted in the current offline or project context.",
                policy.remediation,
            )
        )
    return RepairDryRun(tuple(candidates), requested)


def _normalise_path(value: str, *, platform: str | None = None) -> str:
    """Normalize native or Windows paths without requiring that they exist."""
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return ntpath.normcase(ntpath.normpath(value))
    return os.path.normcase(os.path.abspath(os.path.expanduser(value)))


def same_path(left: str, right: str, *, platform: str | None = None) -> bool:
    """Cross-platform path equality used by environment diagnostics and tests.

    Existing paths are compared by filesystem identity on the running host so
    Windows 8.3 and long-name spellings of one virtual environment are equal.
    Lexical normalisation remains the fallback for missing paths and simulated
    platforms in unit tests.
    """
    selected_platform = sys.platform if platform is None else platform
    if selected_platform == sys.platform:
        try:
            if os.path.samefile(os.path.expanduser(left), os.path.expanduser(right)):
                return True
        except OSError:
            pass
    return _normalise_path(left, platform=selected_platform) == _normalise_path(
        right, platform=selected_platform
    )


def command_in_environment(
    command: str,
    prefix: str,
    scripts: str,
    *,
    platform: str | None = None,
) -> bool:
    """Return whether a command belongs to the active Python environment.

    Resolve native filesystem aliases so pipx shims and equivalent Windows path
    spellings are accepted when they point into the active prefix. Lexical
    normalisation remains available for simulated platforms and missing paths.
    """
    platform = sys.platform if platform is None else platform
    path_module = ntpath if platform == "win32" else os.path
    candidates = [command]
    if platform != "win32":
        candidates.append(str(Path(command).resolve()))
    normalised_prefix = _normalise_path(prefix, platform=platform)
    for candidate in candidates:
        normalised = _normalise_path(candidate, platform=platform)
        parent = path_module.dirname(candidate)
        if same_path(parent, scripts, platform=platform):
            return True
        try:
            if path_module.commonpath((normalised, normalised_prefix)) == normalised_prefix:
                return True
        except ValueError:
            continue
    return False


def _display_path(value: str | Path, root: Path) -> str:
    path = Path(value).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    try:
        relative = resolved.relative_to(root.resolve())
        return "." if not relative.parts else relative.as_posix()
    except ValueError:
        pass
    try:
        relative = resolved.relative_to(Path.home().resolve())
        return "~" if not relative.parts else f"~/{relative.as_posix()}"
    except (OSError, ValueError):
        return str(resolved)


def _sanitise_text(value: str, root: Path) -> str:
    """Make subprocess and metadata evidence safe to attach to support."""
    text = re.sub(r"(https?://)[^/@\s]+@", r"\1", value)
    replacements = ((str(root.resolve()), "."), (str(Path.home().resolve()), "~"))
    for original, replacement in replacements:
        if len(original) > 1:
            text = text.replace(original, replacement)
    return text


def _run(
    command: list[str], *, cwd: Path | None = None, timeout: float = 10.0
) -> subprocess.CompletedProcess[str]:
    """Run one read-only probe with consistent text decoding and no prompts."""
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=environment,
    )


def _first_version(text: str) -> str | None:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)+(?:[A-Za-z0-9.+-]*))", text)
    return match.group(1) if match else None


def _command(name: str) -> CommandInfo:
    path = shutil.which(name)
    if path is None:
        return CommandInfo(name, None, None, "not found on PATH")
    try:
        completed = _run([path, "--version"])
    except (OSError, subprocess.SubprocessError) as error:
        return CommandInfo(name, path, None, str(error))
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    if completed.returncode:
        return CommandInfo(name, path, None, output or f"exited {completed.returncode}")
    version = _first_version(output)
    return CommandInfo(name, path, version, None if version else "reported no version")


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _normalise_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _metadata_filename(path: Path) -> tuple[str | None, str | None, bool]:
    """Return a repairable name/version hinted by a dist-info filename."""
    suffix = ".dist-info"
    if not path.name.casefold().endswith(suffix):
        return None, None, False
    stem = path.name[: -len(suffix)].casefold().replace("_", "-")
    for distribution in REPAIRABLE_DISTRIBUTIONS:
        ordinary = f"{distribution}-"
        remnant = f"~{distribution[1:]}-"
        if stem.startswith(ordinary):
            return distribution, stem[len(ordinary) :] or None, False
        if stem.startswith(remnant):
            return distribution, stem[len(remnant) :] or None, True
    return None, None, False


def _metadata_headers(path: Path) -> tuple[str | None, str | None]:
    try:
        source = (path / "METADATA").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, None
    name: str | None = None
    version: str | None = None
    for line in source.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        if key.casefold() == "name":
            name = value.strip() or None
        elif key.casefold() == "version":
            version = value.strip() or None
        if name is not None and version is not None:
            break
    return name, version


def _known_distribution_version(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        Version(value)
    except InvalidVersion:
        return None
    return value


def _repair_metadata_entries(site_packages: tuple[Path, ...]) -> list[DistributionMetadataEntry]:
    """Scan only direct children of the active environment's library roots."""
    entries: list[DistributionMetadataEntry] = []
    seen: set[Path] = set()
    for library in site_packages:
        try:
            children = tuple(library.iterdir())
        except OSError as error:
            raise MetadataRepairError(
                f"cannot inspect active site-packages {library}: {error}"
            ) from error
        for path in children:
            filename_name, filename_version, remnant = _metadata_filename(path)
            metadata_name, metadata_version = _metadata_headers(path)
            normalized = (
                _normalise_distribution_name(metadata_name) if metadata_name is not None else None
            )
            distribution = normalized if normalized in REPAIRABLE_DISTRIBUTIONS else filename_name
            if distribution is None:
                continue
            try:
                identity = path.resolve()
            except OSError:
                identity = path.absolute()
            if identity in seen:
                continue
            seen.add(identity)
            versions_disagree = bool(
                metadata_version and filename_version and metadata_version != filename_version
            )
            version = _known_distribution_version(
                None if versions_disagree else metadata_version or filename_version
            )
            entries.append(
                DistributionMetadataEntry(
                    distribution,
                    version,
                    path,
                    bool(
                        not remnant
                        and normalized == distribution
                        and metadata_version
                        and not versions_disagree
                    ),
                )
            )
    return entries


def _running_repair_versions() -> dict[str, str]:
    versions = {"prodockit": prodockit.__version__}
    zensical = _command("zensical")
    scripts = sysconfig.get_path("scripts")
    if (
        zensical.path is not None
        and zensical.version is not None
        and zensical.error is None
        and command_in_environment(zensical.path, sys.prefix, scripts)
    ):
        versions["zensical"] = zensical.version
    return versions


def _classify_metadata_repair(
    entries: list[DistributionMetadataEntry], versions: dict[str, str]
) -> tuple[list[DistributionMetadataEntry], set[str], list[str]]:
    """Separate provably stale entries from ambiguous metadata groups."""
    stale: list[DistributionMetadataEntry] = []
    ambiguous: list[str] = []
    affected: set[str] = set()
    for distribution in REPAIRABLE_DISTRIBUTIONS:
        group = [entry for entry in entries if entry.distribution == distribution]
        if len(group) <= 1 and all(entry.valid for entry in group):
            continue
        if not group:
            continue
        affected.add(distribution)
        current = versions.get(distribution)
        matching = [entry for entry in group if entry.valid and entry.version == current]
        obsolete = [
            entry for entry in group if entry.version is not None and entry.version != current
        ]
        if current is None or len(matching) != 1 or len(obsolete) != len(group) - 1:
            found = ", ".join(
                f"{entry.path.name} ({entry.version or 'unknown version'})" for entry in group
            )
            ambiguous.append(f"{distribution}: {found}")
        else:
            stale.extend(obsolete)
    return stale, affected, ambiguous


def _metadata_repair_fingerprint(entries: list[DistributionMetadataEntry]) -> str:
    """Bind a repair plan to exact metadata paths and their current bytes."""
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: str(item.path)):
        digest.update(str(entry.path.resolve()).encode("utf-8"))
        digest.update(b"\0")
        digest.update(_content_sha256(entry.path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _active_site_packages(prefix: Path) -> tuple[Path, ...]:
    paths = sysconfig.get_paths()
    libraries: list[Path] = []
    for key in ("purelib", "platlib"):
        value = paths.get(key)
        if not value:
            continue
        library = Path(value).resolve()
        try:
            library.relative_to(prefix)
        except ValueError as error:
            raise MetadataRepairError(
                f"active {key} path is outside the running environment: {library}"
            ) from error
        if library not in libraries:
            libraries.append(library)
    if not libraries:
        raise MetadataRepairError("the running environment has no site-packages directory")
    return tuple(libraries)


def distribution_metadata_problems() -> tuple[str, ...]:
    """Describe supported metadata ambiguity in the active virtualenv.

    System and externally managed installations remain the responsibility of
    their package manager. This preflight exists for workflows that must not
    continue with ambiguous Prodockit or Zensical versions.
    """
    prefix = Path(sys.prefix).resolve()
    if prefix == Path(sys.base_prefix).resolve():
        return ()
    entries = _repair_metadata_entries(_active_site_packages(prefix))
    problems: list[str] = []
    for distribution in REPAIRABLE_DISTRIBUTIONS:
        group = [entry for entry in entries if entry.distribution == distribution]
        if len(group) > 1 or any(not entry.valid for entry in group):
            found = ", ".join(
                f"{entry.path.name} ({entry.version or 'unknown version'})" for entry in group
            )
            problems.append(f"{distribution}: {found}")
    return tuple(problems)


def repair_distribution_metadata(
    root: Path,
    *,
    prefix: Path | None = None,
    base_prefix: Path | None = None,
    site_packages: tuple[Path, ...] | None = None,
    current_versions: dict[str, str] | None = None,
    timestamp: str | None = None,
    expected_fingerprint: str | None = None,
) -> MetadataRepairResult:
    """Quarantine only provably stale Prodockit or Zensical metadata.

    Optional arguments make the filesystem safety rules directly testable;
    the CLI always uses the running interpreter's own environment.
    """
    active_prefix = (prefix or Path(sys.prefix)).resolve()
    running_base = (base_prefix or Path(sys.base_prefix)).resolve()
    if active_prefix == running_base:
        raise MetadataRepairError(
            "metadata repair is only available inside an active virtual environment; "
            "no system or externally managed Python files were changed"
        )
    declared = os.environ.get("VIRTUAL_ENV")
    if prefix is None and declared and not same_path(declared, str(active_prefix)):
        raise MetadataRepairError(
            "VIRTUAL_ENV does not match the Python running Prodockit; activate the intended "
            "environment before using `pdk diag --fix`"
        )

    libraries = site_packages or _active_site_packages(active_prefix)
    resolved_libraries: list[Path] = []
    for library in libraries:
        resolved = library.resolve()
        try:
            resolved.relative_to(active_prefix)
        except ValueError as error:
            raise MetadataRepairError(
                f"refusing metadata outside the active environment: {resolved}"
            ) from error
        if resolved not in resolved_libraries:
            resolved_libraries.append(resolved)
    entries = _repair_metadata_entries(tuple(resolved_libraries))
    versions = current_versions or _running_repair_versions()
    stale, affected, ambiguous = _classify_metadata_repair(entries, versions)
    if ambiguous:
        detail = "; ".join(ambiguous)
        raise MetadataRepairError(
            "cannot prove which metadata is stale: "
            f"{detail}. Rebuild the active virtual environment at {active_prefix}, "
            "reinstall the project requirements, then rerun `pdk diag`"
        )
    if not stale:
        return MetadataRepairResult("not-needed")
    if expected_fingerprint is not None:
        current_fingerprint = _metadata_repair_fingerprint(entries)
        if current_fingerprint != expected_fingerprint:
            raise MetadataRepairError(
                "the metadata repair plan became stale after inspection; rerun `pdk diag --fix`"
            )

    transaction = RepairTransaction(
        active_prefix,
        action_id="installation.metadata.quarantine-stale",
        check_id="installation.metadata",
        choice_id="quarantine-stale-metadata",
        timestamp=timestamp,
    )
    moved: list[DistributionMetadataEntry] = []
    try:
        transaction.begin()
        for entry_index, entry in enumerate(stale):
            library_index = resolved_libraries.index(entry.path.parent.resolve())
            transaction.quarantine_path(
                entry.path,
                backup_name=f"site-{library_index}/{entry_index}-{entry.path.name}",
                metadata={
                    "distribution": entry.distribution,
                    "version": entry.version,
                },
            )
            moved.append(entry)

        importlib.invalidate_caches()
        remaining = _repair_metadata_entries(tuple(resolved_libraries))
        for distribution in affected:
            group = [entry for entry in remaining if entry.distribution == distribution]
            current = versions.get(distribution)
            if len(group) != 1 or not group[0].valid or group[0].version != current:
                raise MetadataRepairError(
                    f"verification still found ambiguous {distribution} metadata"
                )
        transaction.commit()
    except (RepairTransactionError, OSError) as error:
        try:
            transaction.rollback(str(error))
        finally:
            importlib.invalidate_caches()
        raise MetadataRepairError(f"metadata repair failed and was rolled back: {error}") from error

    return MetadataRepairResult(
        "repaired",
        tuple(_display_path(entry.path, root) for entry in moved),
        _display_path(transaction.quarantine, root),
        _display_path(transaction.manifest_path, root),
    )


def repair_shared_file(
    root: Path,
    target: str,
    *,
    expected_status: str,
    expected_actual_sha256: str | None,
    expected_sha256: str,
    timestamp: str | None = None,
) -> RepairApplyResult:
    """Apply one declared installed shared file through a transaction."""
    project = root.resolve()
    try:
        states = list(inspect_shared_files(project))
    except SharedFileError as error:
        raise RepairTransactionError(str(error)) from error
    matches = [state for state in states if state.file.target == target]
    if len(matches) != 1:
        raise RepairTransactionError(
            f"shared-file repair plan became stale for {target}; rerun `pdk diag --fix`"
        )
    state = matches[0]
    if (
        state.status != expected_status
        or state.actual_sha256 != expected_actual_sha256
        or state.expected_sha256 != expected_sha256
    ):
        raise RepairTransactionError(
            f"shared-file repair plan became stale for {target}; rerun `pdk diag --fix`"
        )
    if state.status == "current":
        return RepairApplyResult("not-needed")
    destination = project / target
    transaction = RepairTransaction(
        project,
        action_id=f"dependencies.shared-files.{hashlib.sha256(target.encode()).hexdigest()[:12]}",
        check_id="dependencies.shared-files",
        choice_id=(
            "create-installed-shared-file"
            if state.status == "missing"
            else "replace-installed-shared-file"
        ),
        timestamp=timestamp,
    )
    try:
        transaction.begin()
        if state.status == "missing":
            transaction.record_creation(destination)
        else:
            transaction.backup_path(destination, backup_name=target)
        changed = apply_shared_files(project, [state])
        verified = next(
            (item for item in inspect_shared_files(project) if item.file.target == target),
            None,
        )
        if changed != [target] or verified is None or verified.status != "current":
            raise RepairTransactionError(f"verification still found shared-file drift at {target}")
        transaction.commit()
    except (RepairTransactionError, SharedFileError, OSError) as error:
        try:
            transaction.rollback(str(error))
        except RepairRollbackError:
            raise
        raise RepairTransactionError(
            f"shared-file repair failed and was rolled back: {error}"
        ) from error
    return RepairApplyResult(
        "applied",
        (target,),
        _display_path(transaction.quarantine, project),
        _display_path(transaction.manifest_path, project),
    )


def _pin_state_fingerprint(root: Path, package: str) -> str:
    """Bind one package plan to every declaration file's current bytes."""
    state = discover(str(root), (package,))[package]
    digest = hashlib.sha256()
    for path in sorted({site.path for site in state.sites}):
        candidate = (root / path).absolute()
        try:
            candidate.resolve(strict=True).relative_to(root.resolve())
        except (OSError, ValueError) as error:
            raise RepairTransactionError(
                f"pin declaration must stay inside the project: {path}"
            ) from error
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_content_sha256(candidate).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def repair_pin_declarations(
    root: Path,
    package: str,
    version: str,
    *,
    expected_fingerprint: str,
    timestamp: str | None = None,
) -> RepairApplyResult:
    """Align one package to one already-detected version transactionally."""
    project = root.resolve()
    states = discover(str(project), (package,))
    state = states[package]
    if version not in state.versions:
        raise RepairTransactionError(f"{version} is not a bounded detected choice for {package}")
    if _pin_state_fingerprint(project, package) != expected_fingerprint:
        raise RepairTransactionError(
            f"pin repair plan became stale for {package}; rerun `pdk diag --fix`"
        )
    changed_paths = tuple(
        dict.fromkeys(site.path for site in state.sites if site.version != version)
    )
    if not changed_paths:
        return RepairApplyResult("not-needed")
    transaction = RepairTransaction(
        project,
        action_id=f"dependencies.pins.align-{package}",
        check_id="dependencies.pins",
        choice_id=f"align-{package}-{version}",
        timestamp=timestamp,
    )
    try:
        transaction.begin()
        for path in changed_paths:
            transaction.backup_path(project / path, backup_name=path)
        changed = apply_version(str(project), state, version)
        verified = discover(str(project), (package,))[package]
        if not changed or verified.versions != [version]:
            raise RepairTransactionError(
                f"verification still found inconsistent {package} declarations"
            )
        transaction.commit()
    except (RepairTransactionError, PinError, OSError) as error:
        try:
            transaction.rollback(str(error))
        except RepairRollbackError:
            raise
        raise RepairTransactionError(f"pin repair failed and was rolled back: {error}") from error
    return RepairApplyResult(
        "applied",
        changed_paths,
        _display_path(transaction.quarantine, project),
        _display_path(transaction.manifest_path, project),
    )


def _renderer_plan_fingerprint(root: Path, component: str) -> str:
    digest = hashlib.sha256()
    tool_root = root / "tools" / component
    for filename in COMPONENT_FILES[component]:
        path = tool_root / filename
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_content_sha256(path).encode("ascii") if path.exists() else b"missing")
        digest.update(b"\0")
    return digest.hexdigest()


def repair_locked_renderer(
    root: Path,
    component: Literal["mermaid", "mathjax"],
    *,
    expected_fingerprint: str,
    timestamp: str | None = None,
    retry_reporter: RetryReporter | None = None,
) -> RepairApplyResult:
    """Rebuild one project-local renderer from a validated lockfile."""
    project = root.resolve()
    try:
        config_path = next(
            path
            for name in (
                "zensical.toml",
                "zensical.yml",
                "zensical.yaml",
                "mkdocs.yml",
                "mkdocs.yaml",
            )
            if (path := project / name).is_file()
        )
        config = load_project_config(config_path)
    except (StopIteration, ProjectConfigError) as error:
        raise RepairTransactionError(f"cannot load project configuration: {error}") from error
    refusal = _locked_renderer_refusal(project, config, component)
    if refusal:
        raise RepairTransactionError(f"renderer repair refused: {refusal}")
    if _renderer_plan_fingerprint(project, component) != expected_fingerprint:
        raise RepairTransactionError(
            f"{component} repair plan became stale; rerun `pdk diag --online --fix`"
        )
    npm = shutil.which("npm")
    node = shutil.which("node")
    if npm is None or node is None:
        raise RepairTransactionError("Node and npm must both be available on PATH")
    for command_name in ("node", "npm"):
        command = _command(command_name)
        if command.path is None or command.error is not None:
            raise RepairTransactionError(
                f"{command_name} health check failed: {command.error or 'not found'}"
            )

    tool_root = project / "tools" / component
    transaction = RepairTransaction(
        project,
        action_id=f"renderer.{component}.install-locked",
        check_id=f"renderer.{component}",
        choice_id=f"install-locked-{component}",
        timestamp=timestamp,
    )
    changed: list[str] = []
    try:
        transaction.begin()
        if not tool_root.exists():
            transaction.record_creation(tool_root)
        else:
            if tool_root.is_symlink():
                raise RepairTransactionError(f"refusing symlinked repair target: {tool_root}")
            for filename in COMPONENT_FILES[component]:
                path = tool_root / filename
                if not path.exists():
                    transaction.record_creation(path)
        modules = tool_root / "node_modules"
        if modules.exists() or modules.is_symlink():
            transaction.quarantine_path(modules, backup_name=f"tools/{component}/node_modules")
        elif tool_root.exists():
            transaction.record_creation(modules)

        scaffold = init_tools(project / "tools", components=(component,))
        changed.extend(_display_path(path, project) for path in scaffold.written)
        refusal = _locked_renderer_refusal(project, config, component)
        if refusal:
            raise RepairTransactionError(f"renderer scaffold verification failed: {refusal}")
        environment = dict(os.environ)
        environment["PUPPETEER_SKIP_DOWNLOAD"] = "true"
        npm_result = run_npm_with_retries(
            [
                npm,
                "ci",
                "--legacy-peer-deps",
                "--no-audit",
                "--no-fund",
                "--prefer-offline",
            ],
            cwd=tool_root,
            timeout=600,
            environment=environment,
            reporter=retry_reporter,
        )
        completed = npm_result.completed
        if completed.returncode:
            detail = npm_result.failure_detail
            raise RepairTransactionError(
                f"npm ci failed: {_sanitise_text(detail, project)}"
            )
        changed.append(_display_path(modules, project))

        if component == "mermaid":
            binary = _project_tool(
                project,
                None,
                ("tools/mermaid/node_modules/.bin/mmdc",),
            )
            probe = (
                (
                    probe_mermaid(binary, reporter=retry_reporter)
                    if retry_reporter is not None
                    else probe_mermaid(binary)
                )
                if binary
                else None
            )
            if probe is None or not probe.ok:
                raise RepairTransactionError(
                    f"Mermaid verification failed: {probe.error if probe else 'mmdc is missing'}"
                )
        else:
            asset_paths = (
                project / "docs" / "javascripts" / "mathjax.js",
                project / "docs" / "javascripts" / "vendor" / "mathjax" / "tex-svg-full.js",
                project / "docs" / "javascripts" / "vendor" / "mathjax" / "LICENSE",
            )
            for path in asset_paths:
                if path.exists() or path.is_symlink():
                    transaction.backup_path(path, backup_name=_display_path(path, project))
                else:
                    transaction.record_creation(path)
            try:
                installed = install_mathjax(project, update_gitignore=False)
            except MathJaxError as error:
                raise RepairTransactionError(str(error)) from error
            changed.extend(
                _display_path(path, project)
                for path in (installed.config, installed.bundle, installed.license)
            )
            probe = probe_mathjax(node, tool_root / "tex2svg.js")
            if not probe.ok:
                raise RepairTransactionError(f"MathJax verification failed: {probe.error}")
        transaction.commit()
    except (OSError, subprocess.SubprocessError, RepairTransactionError) as error:
        try:
            transaction.rollback(str(error))
        except RepairRollbackError:
            raise
        raise RepairTransactionError(
            f"{component} repair failed and was rolled back: {error}"
        ) from error
    return RepairApplyResult(
        "applied",
        tuple(dict.fromkeys(changed)),
        _display_path(transaction.quarantine, project),
        _display_path(transaction.manifest_path, project),
    )


def _toml_section(source: str, table: str) -> tuple[int, int] | None:
    header = re.search(rf"(?m)^\[{re.escape(table)}\][ \t]*(?:#.*)?\r?$", source)
    if header is None:
        return None
    following = re.search(r"(?m)^\[", source[header.end() :])
    return header.start(), header.end() + (
        following.start() if following else len(source[header.end() :])
    )


def _line_ending(source: str) -> str:
    return "\r\n" if "\r\n" in source and "\n" not in source.replace("\r\n", "") else "\n"


def _toml_add_array_value(source: str, key: str, value: str) -> str:
    section = _toml_section(source, "project")
    if section is None:
        raise RepairTransactionError("zensical.toml has no [project] table")
    start, end = section
    region = source[start:end]
    assignment = re.search(rf"(?m)^{re.escape(key)}\s*=\s*\[", region)
    rendered = json.dumps(value)
    newline = _line_ending(source)
    if assignment is None:
        header_end = source.find("\n", start) + 1
        return source[:header_end] + f"{key} = [{rendered}]{newline}" + source[header_end:]
    array_start = start + assignment.end() - 1
    depth = 0
    quote = ""
    escaped = False
    array_end = -1
    for position in range(array_start, len(source)):
        char = source[position]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                array_end = position
                break
    if array_end < 0:
        raise RepairTransactionError(f"cannot find the end of project.{key}")
    if value in (tomllib.loads(source).get("project", {}).get(key) or []):
        return source
    body = source[array_start + 1 : array_end]
    separator = "" if not body.strip() or body.rstrip().endswith(",") else ","
    return source[:array_end] + f"{separator}{newline}  {rendered},{newline}" + source[array_end:]


def _plan_configuration_source(source: str, problem: dict[str, str]) -> str:
    operation = problem["operation"]
    if operation == "rename":
        old, new = problem["old"], problem["new"]
        if problem["kind"] == "rename-extension":
            pattern = re.compile(
                rf'(?m)^\[project\.markdown_extensions\."{re.escape(old)}"\]([ \t]*(?:#.*)?)$'
            )
            replacement = rf'[project.markdown_extensions."{new}"]\1'
        elif problem["path"].startswith("project.extra."):
            section_name = "project.extra"
            located = _toml_section(source, section_name)
            if located is None:
                raise RepairTransactionError(f"cannot find [{section_name}]")
            start, end = located
            region = source[start:end]
            pattern = re.compile(rf"(?m)^{re.escape(old)}([ \t]*=)")
            if pattern.search(region) is None or re.search(rf"(?m)^{re.escape(new)}\s*=", region):
                raise RepairTransactionError("the proposed setting rename is no longer unique")
            return source[:start] + pattern.sub(rf"{new}\1", region, count=1) + source[end:]
        else:
            extension = problem["path"].split('"', 2)[1]
            section_name = f'project.markdown_extensions."{extension}"'
            located = _toml_section(source, section_name)
            if located is None:
                raise RepairTransactionError(f"cannot find [{section_name}]")
            start, end = located
            region = source[start:end]
            pattern = re.compile(rf"(?m)^{re.escape(old)}([ \t]*=)")
            if pattern.search(region) is None or re.search(rf"(?m)^{re.escape(new)}\s*=", region):
                raise RepairTransactionError("the proposed option rename is no longer unique")
            return source[:start] + pattern.sub(rf"{new}\1", region, count=1) + source[end:]
        if len(pattern.findall(source)) != 1 or f'project.markdown_extensions."{new}"' in source:
            raise RepairTransactionError("the proposed extension rename is no longer unique")
        return pattern.sub(replacement, source, count=1)
    if operation == "move-index-setting":
        old, new = problem["old"], problem["new"]
        extra = _toml_section(source, "project.extra")
        if extra is None:
            raise RepairTransactionError("cannot find [project.extra]")
        start, end = extra
        region = source[start:end]
        match = re.search(rf"(?m)^{re.escape(old)}\s*=\s*(.+)$", region)
        if match is None:
            raise RepairTransactionError(f"cannot find project.extra.{old}")
        assignment = f"{new} = {match.group(1)}"
        region = region[: match.start()] + region[match.end() :]
        source = source[:start] + region + source[end:]
        table = 'project.markdown_extensions."prodockit.index"'
        newline = _line_ending(source)
        target = _toml_section(source, table)
        if target is None:
            lead = "" if source.endswith(("\n", "\r")) else newline
            return f"{source}{lead}{newline}[{table}]{newline}{assignment}{newline}"
        target_start, target_end = target
        target_region = source[target_start:target_end]
        if re.search(rf"(?m)^{re.escape(new)}\s*=", target_region):
            raise RepairTransactionError(f"{table}.{new} already exists")
        header_end = source.find("\n", target_start) + 1
        return source[:header_end] + assignment + newline + source[header_end:]
    if operation == "enable-extension":
        table = f'project.markdown_extensions."{problem["new"]}"'
        if _toml_section(source, table) is not None:
            return source
        newline = _line_ending(source)
        lead = "" if source.endswith(("\n", "\r")) else newline
        return f"{source}{lead}{newline}[{table}]{newline}"
    if operation == "add-asset":
        current = tomllib.loads(source).get("project", {}).get(problem["setting"])
        if current is not None and not isinstance(current, list):
            raise RepairTransactionError(
                f"project.{problem['setting']} is not a list; author intent is required"
            )
        return _toml_add_array_value(source, problem["setting"], problem["new"])
    raise RepairTransactionError(f"unknown configuration repair operation: {operation}")


def repair_project_configuration(
    root: Path,
    problem: dict[str, str],
    *,
    expected_fingerprint: str,
    timestamp: str | None = None,
) -> RepairApplyResult:
    """Apply one lossless TOML edit and verify the configuration remains valid."""
    project = root.resolve()
    config_path = project / "zensical.toml"
    if not config_path.is_file() or config_path.is_symlink():
        raise RepairTransactionError("configuration repair supports a regular zensical.toml only")
    if _content_sha256(config_path) != expected_fingerprint:
        raise RepairTransactionError(
            "configuration repair plan became stale; rerun `pdk diag --fix`"
        )
    try:
        source = config_path.read_bytes().decode("utf-8")
    except UnicodeError as error:
        raise RepairTransactionError("zensical.toml is not valid UTF-8") from error
    planned = _plan_configuration_source(source, problem)
    if planned == source:
        return RepairApplyResult("not-needed")
    try:
        tomllib.loads(planned)
    except tomllib.TOMLDecodeError as error:
        raise RepairTransactionError(f"planned configuration would be invalid: {error}") from error
    transaction = RepairTransaction(
        project,
        action_id=f"project.configuration.{problem['id']}",
        check_id="project.configuration",
        choice_id=problem["id"],
        timestamp=timestamp,
    )
    try:
        transaction.begin()
        transaction.backup_path(config_path, backup_name="zensical.toml")
        temporary = config_path.with_name(f".{config_path.name}-{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(planned.encode("utf-8"))
        os.replace(temporary, config_path)
        verified = load_project_config(config_path)
        remaining = _configuration_repairable_problems(
            verified, inspect_config(verified).diagnostics
        )
        if any(item.get("id") == problem["id"] for item in remaining):
            raise RepairTransactionError(
                "verification still found the selected configuration problem"
            )
        transaction.commit()
    except (OSError, UnicodeError, ProjectConfigError, RepairTransactionError) as error:
        try:
            transaction.rollback(str(error))
        except RepairRollbackError:
            raise
        raise RepairTransactionError(
            f"configuration repair failed and was rolled back: {error}"
        ) from error
    return RepairApplyResult(
        "applied",
        ("zensical.toml",),
        _display_path(transaction.quarantine, project),
        _display_path(transaction.manifest_path, project),
    )


def _environment_checks(root: Path) -> list[DiagnosticResult]:
    executable = _display_path(sys.executable, root)
    prefix = _display_path(sys.prefix, root)
    base_prefix = _display_path(sys.base_prefix, root)
    active = sys.prefix != sys.base_prefix
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks = [
        DiagnosticResult(
            "environment.python",
            "Environment and installation",
            "pass",
            f"Python {python_version}",
            (f"executable: {executable}", f"prefix: {prefix}", f"base prefix: {base_prefix}"),
            {
                "version": python_version,
                "executable": executable,
                "prefix": prefix,
                "base_prefix": base_prefix,
                "isolated_environment": active,
            },
        )
    ]

    declared = os.environ.get("VIRTUAL_ENV")
    if declared and not same_path(declared, sys.prefix):
        checks.append(
            DiagnosticResult(
                "environment.virtual-env",
                "Environment and installation",
                "fail",
                "VIRTUAL_ENV does not match the Python running Prodockit",
                (
                    f"VIRTUAL_ENV: {_display_path(declared, root)}",
                    f"running prefix: {prefix}",
                    "activate the intended environment or select its interpreter, "
                    "then reopen the shell",
                ),
                {"declared": _display_path(declared, root), "running_prefix": prefix},
            )
        )
    elif declared:
        checks.append(
            DiagnosticResult(
                "environment.virtual-env",
                "Environment and installation",
                "pass",
                "VIRTUAL_ENV matches the running interpreter",
                (f"VIRTUAL_ENV: {_display_path(declared, root)}",),
            )
        )
    else:
        checks.append(
            DiagnosticResult(
                "environment.virtual-env",
                "Environment and installation",
                "pass",
                "No VIRTUAL_ENV is declared",
                ("this is valid for pipx, Conda, system Python and clean CI installations",),
            )
        )
    return checks


def _installation_checks(root: Path) -> list[DiagnosticResult]:
    expected = {
        "pdk": prodockit.__version__,
        "prodockit": prodockit.__version__,
        "zensical": _distribution_version("zensical"),
    }
    commands = [_command(name) for name in expected]
    active_scripts = sysconfig.get_path("scripts")
    details: list[str] = []
    failures: list[str] = []
    for command in commands:
        location = _display_path(command.path, root) if command.path else "missing"
        reported = command.version or "unknown"
        details.append(f"{command.name}: {reported} at {location}")
        wanted = expected[command.name]
        if command.path is None or command.error:
            failures.append(f"{command.name}: {_sanitise_text(command.error or 'missing', root)}")
        elif wanted is None:
            failures.append(f"{command.name}: installed distribution metadata is missing")
        elif command.version != wanted:
            failures.append(
                f"{command.name}: command reports {command.version}, active Python loads {wanted}"
            )
        elif not command_in_environment(command.path, sys.prefix, active_scripts):
            failures.append(
                f"{command.name}: command resolves outside the active Python environment"
            )

    script_dir = _display_path(active_scripts, root)
    details.append(f"active scripts directory: {script_dir}")
    checks = [
        DiagnosticResult(
            "installation.commands",
            "Environment and installation",
            "fail" if failures else "pass",
            "Command locations and loaded distributions disagree"
            if failures
            else "Prodockit and Zensical commands match the active Python",
            tuple(details + failures),
            {
                "commands": [
                    {
                        "name": item.name,
                        "path": _display_path(item.path, root) if item.path else None,
                        "version": item.version,
                        "error": _sanitise_text(item.error, root) if item.error else None,
                    }
                    for item in commands
                ],
                "active_scripts_directory": script_dir,
            },
        )
    ]

    try:
        pip_check = _run([sys.executable, "-m", "pip", "check"], timeout=30)
        pip_text = _sanitise_text(
            "\n".join(
                part.strip() for part in (pip_check.stdout, pip_check.stderr) if part.strip()
            ),
            root,
        )
        checks.append(
            DiagnosticResult(
                "installation.dependencies",
                "Environment and installation",
                "pass" if pip_check.returncode == 0 else "fail",
                "Installed dependencies are compatible"
                if pip_check.returncode == 0
                else "Installed dependencies are incompatible or missing",
                tuple(pip_text.splitlines()),
                {"returncode": pip_check.returncode},
            )
        )
    except (OSError, subprocess.SubprocessError) as error:
        checks.append(
            DiagnosticResult(
                "installation.dependencies",
                "Environment and installation",
                "fail",
                "Could not run the active Python's pip check",
                (_sanitise_text(str(error), root),),
            )
        )

    locations: dict[str, set[str]] = {}
    invalid: list[str] = []
    for distribution in importlib.metadata.distributions():
        try:
            name = distribution.metadata["Name"]
            version = distribution.version
            if not name or not version:
                invalid.append(str(getattr(distribution, "_path", "unknown metadata")))
                continue
            normalized = _normalise_distribution_name(name)
            locations.setdefault(normalized, set()).add(
                str(getattr(distribution, "_path", distribution.locate_file("")))
            )
        except (KeyError, OSError, UnicodeError, ValueError) as error:
            invalid.append(str(error))
    duplicates = {name: sorted(paths) for name, paths in locations.items() if len(paths) > 1}
    metadata_details = [
        f"invalid metadata: {_sanitise_text(item, root)}" for item in sorted(invalid)
    ]
    metadata_details.extend(
        f"duplicate {name}: {', '.join(_display_path(path, root) for path in paths)}"
        for name, paths in sorted(duplicates.items())
    )
    repair_candidates = set(duplicates).intersection(REPAIRABLE_DISTRIBUTIONS)
    for item in invalid:
        repair_distribution, _version, _remnant = _metadata_filename(Path(item))
        if repair_distribution is not None:
            repair_candidates.add(repair_distribution)
    repair_paths: list[str] = []
    repair_fingerprint: str | None = None
    repair_error: str | None = None
    if repair_candidates:
        try:
            prefix = Path(sys.prefix).resolve()
            if prefix == Path(sys.base_prefix).resolve():
                raise MetadataRepairError("metadata repair requires an active virtual environment")
            repair_entries = _repair_metadata_entries(_active_site_packages(prefix))
            stale, _affected, ambiguous = _classify_metadata_repair(
                repair_entries, _running_repair_versions()
            )
            if ambiguous:
                raise MetadataRepairError(
                    "cannot prove which metadata is stale: " + "; ".join(ambiguous)
                )
            repair_paths = [_display_path(entry.path, root) for entry in stale]
            if stale:
                repair_fingerprint = _metadata_repair_fingerprint(repair_entries)
        except (RepairTransactionError, OSError) as error:
            repair_error = _sanitise_text(str(error), root)
    if repair_candidates:
        metadata_details.append(
            "run `pdk diag --fix` to quarantine stale Prodockit or Zensical metadata "
            "when exactly one entry matches the loaded package"
        )
    checks.append(
        DiagnosticResult(
            "installation.metadata",
            "Environment and installation",
            "warn" if metadata_details else "pass",
            "Duplicate or invalid distribution metadata found"
            if metadata_details
            else "Distribution metadata is readable and unique",
            tuple(metadata_details),
            {
                "invalid_count": len(invalid),
                "duplicate_names": sorted(duplicates),
                "fix_candidates": sorted(repair_candidates),
                "repair_paths": sorted(dict.fromkeys(repair_paths)),
                "repair_fingerprint": repair_fingerprint,
                "repair_error": repair_error,
            },
        )
    )
    return checks


def _configuration_check(config_file: Path) -> tuple[ProjectConfig | None, DiagnosticResult]:
    try:
        config = load_project_config(config_file)
        report = inspect_config(config)
    except ProjectConfigError as error:
        return None, DiagnosticResult(
            "project.configuration",
            "Project configuration and inputs",
            "fail",
            "Project configuration could not be loaded",
            (str(error), "run `pdk config --check` for the detailed configuration report"),
        )
    details = tuple(f"{item.path}: {item.message}" for item in report.diagnostics)
    repairable = _configuration_repairable_problems(config, report.diagnostics)
    return config, DiagnosticResult(
        "project.configuration",
        "Project configuration and inputs",
        "fail" if details else "pass",
        f"Configuration has {len(details)} actionable problem(s)"
        if details
        else "Configuration and local project inputs pass",
        details + (("run `pdk config --check` for the complete report",) if details else ()),
        {
            "config_file": _display_path(report.path, config.root),
            "problem_count": len(details),
            "repair_fingerprint": _content_sha256(report.path),
            "repairable_problems": repairable,
        },
    )


def _configuration_repairable_problems(
    config: ProjectConfig, problems: tuple[Any, ...]
) -> list[dict[str, str]]:
    """Classify exact TOML-only fixes; every other finding remains manual."""
    if config.path.suffix.casefold() != ".toml":
        return []
    found: list[dict[str, str]] = []
    for problem in problems:
        path = str(problem.path)
        message = str(problem.message)
        suggestion = re.search(r"did you mean '([^']+)'\?", message)
        if suggestion and (
            path.startswith("project.extra.") or path.startswith("project.markdown_extensions.")
        ):
            new = suggestion.group(1)
            kind = (
                "rename-extension"
                if message.startswith("unknown Prodockit extension")
                else "rename-key"
            )
            old = (
                path.removeprefix("project.markdown_extensions.")
                if kind == "rename-extension"
                else path.rsplit(".", 1)[-1].strip('"')
            )
            found.append(
                {
                    "id": f"rename-{hashlib.sha256(path.encode()).hexdigest()[:10]}",
                    "operation": "rename",
                    "kind": kind,
                    "path": path,
                    "old": old,
                    "new": new,
                    "label": f"Rename {old!r} to the unique supported name {new!r}",
                }
            )
            continue
        obsolete = {
            "project.extra.pdf_include_index": (
                "include",
                "Move pdf_include_index to prodockit.index.include",
            ),
            "project.extra.pdf_index_title": (
                "title",
                "Move pdf_index_title to prodockit.index.title",
            ),
        }.get(path)
        if obsolete:
            target, label = obsolete
            found.append(
                {
                    "id": f"move-{path.rsplit('.', 1)[-1]}",
                    "operation": "move-index-setting",
                    "path": path,
                    "old": path.rsplit(".", 1)[-1],
                    "new": target,
                    "label": label,
                }
            )
            continue
        extension = re.search(r"uses .+ syntax but (prodockit\.[a-z_-]+) is not enabled$", message)
        if extension:
            name = extension.group(1)
            found.append(
                {
                    "id": f"enable-{name.replace('.', '-')}",
                    "operation": "enable-extension",
                    "path": path,
                    "new": name,
                    "label": f"Enable {name}, uniquely required by detected author syntax",
                }
            )
            continue
        missing_stylesheet = (
            "local stylesheet is not configured in project.extra_css or project.extra.pdf_extra_css"
        )
        if message == missing_stylesheet and path.endswith("/stylesheets/pdk.css"):
            found.append(
                {
                    "id": "configure-pdk-css",
                    "operation": "add-asset",
                    "path": path,
                    "new": "stylesheets/pdk.css",
                    "setting": "extra_css",
                    "label": "Add the existing Prodockit stylesheet to project.extra_css",
                }
            )
        elif message == "local JavaScript file is not configured in project.extra_javascript" and (
            path.endswith("/javascripts/mathjax.js")
            or path.endswith("/javascripts/vendor/mathjax/tex-svg-full.js")
        ):
            marker = path.split("/javascripts/", 1)[1]
            found.append(
                {
                    "id": f"configure-{hashlib.sha256(path.encode()).hexdigest()[:10]}",
                    "operation": "add-asset",
                    "path": path,
                    "new": f"javascripts/{marker}",
                    "setting": "extra_javascript",
                    "label": f"Add the existing Prodockit MathJax asset {marker}",
                }
            )
    return found


def _pin_checks(root: Path, online: bool) -> list[DiagnosticResult]:
    states = discover(str(root), DEFAULT_PACKAGES)
    resolve_latest(states, offline=not online)
    inconsistent = [state for state in states.values() if not state.is_consistent]
    unsupported = [
        state
        for state in states.values()
        if state.sites
        and state.is_consistent
        and state.current != TESTED_VERSIONS.get(state.package)
    ]
    behind = [state for state in states.values() if state.is_behind]
    lookup_errors = [
        f"{state.package}: {state.latest_error}"
        for state in states.values()
        if online and state.on_pypi and state.latest is None and state.latest_error
    ]
    details = [f"{state.package}: {', '.join(state.versions)}" for state in inconsistent]
    details.extend(
        (
            f"{state.package}: declared {state.current}; supported with installed "
            f"prodockit {prodockit.__version__}: {TESTED_VERSIONS[state.package]}; "
            "run `pdk pins` and accept the tested default"
        )
        for state in unsupported
    )
    details.extend(
        f"{state.package}: {state.current} -> {state.latest} available" for state in behind
    )
    details.extend(lookup_errors)
    status: Status = (
        "fail" if inconsistent else ("warn" if unsupported or behind or lookup_errors else "pass")
    )
    summary = (
        f"{len(inconsistent)} package declaration(s) are inconsistent"
        if inconsistent
        else f"{len(unsupported)} declared version(s) are outside the supported combination"
        if unsupported
        else f"{len(behind)} package update(s) are available"
        if behind
        else "Package declarations are consistent"
    )
    checks = [
        DiagnosticResult(
            "dependencies.pins",
            "Dependency and managed-file consistency",
            status,
            summary,
            tuple(details),
            {
                "online": online,
                "inconsistent": [state.package for state in inconsistent],
                "supported_mismatches": [state.package for state in unsupported],
                "updates": [state.package for state in behind],
                "packages": [
                    {
                        "package": state.package,
                        "versions": state.versions,
                        "latest": state.latest,
                        "tested": TESTED_VERSIONS.get(state.package),
                        "fingerprint": _pin_state_fingerprint(root, state.package)
                        if len(state.versions) > 1
                        else None,
                        "sites": [
                            {
                                "path": site.path,
                                "line": site.line,
                                "operator": site.op,
                                "version": site.version,
                                "kind": site.kind,
                            }
                            for site in state.sites
                        ],
                    }
                    for state in states.values()
                    if state.sites
                ],
            },
        )
    ]
    try:
        shared = list(inspect_shared_files(root))
        drift = [state for state in shared if state.status != "current"]
        checks.append(
            DiagnosticResult(
                "dependencies.shared-files",
                "Dependency and managed-file consistency",
                "fail" if drift else "pass",
                f"{len(drift)} managed shared file(s) have drifted"
                if drift
                else "Managed shared files match the installed release",
                tuple(f"{state.file.target}: {state.status}" for state in drift),
                {
                    "declared": len(shared),
                    "drifted": len(drift),
                    "drifted_files": [
                        {
                            "path": state.file.target,
                            "status": state.status,
                            "expected_sha256": state.expected_sha256,
                            "actual_sha256": state.actual_sha256,
                        }
                        for state in drift
                    ],
                },
            )
        )
    except SharedFileError as error:
        checks.append(
            DiagnosticResult(
                "dependencies.shared-files",
                "Dependency and managed-file consistency",
                "fail",
                "Managed shared files could not be inspected",
                (str(error),),
            )
        )
    return checks


def _project_tool(root: Path, configured: object, defaults: tuple[str, ...]) -> Path | None:
    if configured:
        candidate = Path(str(configured))
        candidate = candidate if candidate.is_absolute() else root / candidate
        return candidate if candidate.is_file() else None
    for default in defaults:
        candidate = root / default
        for spelling in (candidate, Path(f"{candidate}.cmd"), Path(f"{candidate}.exe")):
            if spelling.is_file():
                return spelling
    return None


def _locked_renderer_refusal(
    root: Path, config: ProjectConfig | None, component: str
) -> str | None:
    """Return why a renderer cannot be rebuilt without resolving author intent."""
    if config is None:
        return "Project configuration is not readable."
    custom_key = "pdf_mmdc_bin" if component == "mermaid" else "pdf_tex2svg_script"
    if config.extra.get(custom_key):
        return f"project.extra.{custom_key} selects a custom executable path"
    tool_root = root / "tools" / component
    manifest = tool_root / "package.json"
    lockfile = tool_root / "package-lock.json"
    if manifest.exists() != lockfile.exists():
        return "package.json and package-lock.json must either both exist or both be absent"
    if not manifest.exists():
        return None
    if manifest.is_symlink() or lockfile.is_symlink():
        return "renderer manifests must not be symlinks"
    try:
        package = json.loads(manifest.read_text(encoding="utf-8"))
        lock = json.loads(lockfile.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return f"renderer manifest is not valid UTF-8 JSON: {error}"
    if not isinstance(package, dict) or not isinstance(lock, dict):
        return "renderer manifests must contain JSON objects"
    if package.get("scripts"):
        return "package.json contains author lifecycle scripts"
    dependencies = package.get("dependencies")
    root_package = (
        (lock.get("packages") or {}).get("") if isinstance(lock.get("packages"), dict) else None
    )
    if not isinstance(dependencies, dict) or not isinstance(root_package, dict):
        return "renderer manifests do not declare a locked dependency graph"
    if root_package.get("dependencies") != dependencies:
        return "package.json and package-lock.json dependency declarations do not match"
    package_name = "@mermaid-js/mermaid-cli" if component == "mermaid" else "mathjax-full"
    locked = (lock.get("packages") or {}).get(f"node_modules/{package_name}")
    if not isinstance(locked, dict) or not locked.get("version") or not locked.get("integrity"):
        return f"package-lock.json does not pin {package_name} with an integrity hash"
    for filename in COMPONENT_FILES[component]:
        candidate = tool_root / filename
        if candidate.exists() and candidate.is_symlink():
            return f"{candidate.relative_to(root)} must not be a symlink"
    return None


def _tool_result(
    check_id: str,
    name: str,
    command: str,
    *,
    root: Path,
    required: bool,
) -> DiagnosticResult:
    info = _command(command)
    if info.path and not info.error:
        return DiagnosticResult(
            check_id,
            "Rendering toolchain",
            "pass",
            f"{name} {info.version or 'is available'}",
            (f"path: {_display_path(info.path, root)}",),
            {"required": required, "path": _display_path(info.path, root), "version": info.version},
        )
    return DiagnosticResult(
        check_id,
        "Rendering toolchain",
        "fail" if required else "warn",
        f"{name} is missing" + (" but required by this project" if required else " (optional)"),
        ((info.error or "not found"),),
        {"required": required, "path": None, "version": None},
    )


def _renderer_checks(
    config: ProjectConfig | None,
    root: Path,
    *,
    retry_reporter: RetryReporter | None = None,
) -> list[DiagnosticResult]:
    pdf_required = bool(
        config
        and any(
            config.extra.get(key)
            for key in ("pdf_output", "pdf_source_bundle_output", "pdf_extra_css")
        )
    )
    mermaid_required, maths_required = renderer_requirements(config) if config else (False, False)
    node_required = mermaid_required or maths_required
    checks = [_tool_result("renderer.pandoc", "Pandoc", "pandoc", root=root, required=pdf_required)]

    try:
        # WeasyPrint prints a multi-line native-library help banner as an import
        # side effect before raising. That corrupts `pdk diag --json` and
        # `--dry-run --json`, whose stdout must contain one JSON document.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module = importlib.import_module("weasyprint")
        version = str(getattr(module, "__version__", "unknown"))
        checks.append(
            DiagnosticResult(
                "renderer.weasyprint",
                "Rendering toolchain",
                "pass",
                f"WeasyPrint {version} imports with its native libraries",
                (),
                {"required": pdf_required, "version": version},
            )
        )
    except Exception as error:  # native-loader failures are not ImportError
        safe_error = _sanitise_text(f"{type(error).__name__}: {error}", root)
        checks.append(
            DiagnosticResult(
                "renderer.weasyprint",
                "Rendering toolchain",
                "fail" if pdf_required else "warn",
                "WeasyPrint cannot import"
                + (" but is required by this project" if pdf_required else " (optional)"),
                (safe_error,),
                {"required": pdf_required},
            )
        )

    checks.extend(
        (
            _tool_result("renderer.node", "Node", "node", root=root, required=node_required),
            _tool_result("renderer.npm", "npm", "npm", root=root, required=node_required),
        )
    )

    mmdc = None
    tex2svg = None
    if config:
        mmdc = _project_tool(
            root,
            config.extra.get("pdf_mmdc_bin"),
            ("tools/mermaid/node_modules/.bin/mmdc", "node_modules/.bin/mmdc"),
        ) or (Path(found) if (found := shutil.which("mmdc")) else None)
        tex2svg = _project_tool(
            root,
            config.extra.get("pdf_tex2svg_script"),
            ("tools/mathjax/tex2svg.js",),
        )
    mmdc_probe = (
        (
            probe_mermaid(mmdc, reporter=retry_reporter)
            if retry_reporter is not None
            else probe_mermaid(mmdc)
        )
        if mmdc
        else None
    )
    mmdc_ok = bool(mmdc_probe and mmdc_probe.ok)
    mmdc_retried = bool(
        mmdc_ok and mmdc_probe and getattr(mmdc_probe, "attempts", 1) > 1
    )
    mmdc_error = _sanitise_text(mmdc_probe.error, root) if mmdc_probe and mmdc_probe.error else None
    checks.append(
        DiagnosticResult(
            "renderer.mermaid",
            "Rendering toolchain",
            "warn" if mmdc_retried else (
                "pass" if mmdc_ok else ("fail" if mermaid_required else "warn")
            ),
            "Mermaid CLI recovered after a transient failure"
            if mmdc_retried
            else "Mermaid CLI is available"
            if mmdc_ok
            else ("Mermaid CLI is unusable" if mmdc else "Mermaid CLI is missing")
            + (" but required by this project" if mermaid_required else " (optional)"),
            tuple(
                detail
                for detail in (
                    f"path: {_display_path(mmdc, root)}" if mmdc else None,
                    (
                        f"health probe: recovered after {mmdc_probe.attempts} attempts"
                        if mmdc_retried and mmdc_probe
                        else None
                    ),
                    f"health probe: {mmdc_error}" if mmdc_error else None,
                )
                if detail
            ),
            {
                "required": mermaid_required,
                "path": _display_path(mmdc, root) if mmdc else None,
                "version": mmdc_probe.version if mmdc_probe else None,
                "error": mmdc_error,
                "repair_refusal": _locked_renderer_refusal(root, config, "mermaid"),
                "repair_fingerprint": _renderer_plan_fingerprint(root, "mermaid"),
            },
        )
    )

    browser = find_browser()
    browser_error = None
    if browser:
        # Do not execute a desktop browser merely to ask for its version.
        # Microsoft Edge can open a visible window for ``--version`` on
        # Windows and return no text. The Mermaid health probe above already
        # exercises the browser when the project needs it (#712, #713).
        try:
            if not Path(browser).is_file():
                browser_error = "path does not name a file"
        except OSError as error:
            browser_error = _sanitise_text(str(error), root)
    browser_ok = bool(browser and not browser_error)
    browser_status: Status = (
        "pass" if browser_ok else ("fail" if browser and mermaid_required else "warn")
    )
    checks.append(
        DiagnosticResult(
            "renderer.browser",
            "Rendering toolchain",
            browser_status,
            "Browser executable found"
            if browser_ok
            else (
                "Browser executable is unusable"
                if browser
                else "No explicit Chrome/Chromium executable found"
            )
            + (
                "; Mermaid CLI may use its bundled browser"
                if not browser and mermaid_required
                else " (optional)"
                if not mermaid_required
                else ""
            ),
            tuple(
                detail
                for detail in (
                    f"path: {_display_path(browser, root)}" if browser else None,
                    f"health probe: {browser_error}" if browser_error else None,
                )
                if detail
            ),
            {
                "required": mermaid_required,
                "path": _display_path(browser, root) if browser else None,
                "version": None,
                "error": browser_error,
            },
        )
    )

    mathjax_modules = root / "tools" / "mathjax" / "node_modules" / "mathjax-full"
    node = shutil.which("node")
    mathjax_probe = probe_mathjax(node, tex2svg) if node and tex2svg else None
    mathjax_ok = bool(mathjax_modules.is_dir() and mathjax_probe and mathjax_probe.ok)
    mathjax_error = (
        _sanitise_text(mathjax_probe.error, root) if mathjax_probe and mathjax_probe.error else None
    )
    math_details = []
    if tex2svg:
        math_details.append(f"script: {_display_path(tex2svg, root)}")
    if mathjax_modules.is_dir():
        math_details.append(f"inputs: {_display_path(mathjax_modules, root)}")
    if tex2svg and node is None:
        math_details.append("health probe: node is not found on PATH")
    elif mathjax_error:
        math_details.append(f"health probe: {mathjax_error}")
    checks.append(
        DiagnosticResult(
            "renderer.mathjax",
            "Rendering toolchain",
            "pass" if mathjax_ok else ("fail" if maths_required else "warn"),
            "MathJax can render an expression"
            if mathjax_ok
            else "MathJax PDF renderer is incomplete"
            + (" but required by this project" if maths_required else " (optional)"),
            tuple(math_details),
            {
                "required": maths_required,
                "script": _display_path(tex2svg, root) if tex2svg else None,
                "inputs": _display_path(mathjax_modules, root)
                if mathjax_modules.is_dir()
                else None,
                "error": (
                    mathjax_error
                    if mathjax_probe
                    else "node is not found on PATH"
                    if tex2svg
                    else None
                ),
                "repair_refusal": _locked_renderer_refusal(root, config, "mathjax"),
                "repair_fingerprint": _renderer_plan_fingerprint(root, "mathjax"),
            },
        )
    )
    return checks


def _node_security_checks(root: Path, online: bool) -> list[DiagnosticResult]:
    """Audit the Mermaid production graph only when network checks are requested."""
    tool_root = root / "tools" / "mermaid"
    lockfile = tool_root / "package-lock.json"
    if not lockfile.is_file():
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "pass",
                "Mermaid security audit is not applicable",
                ("tools/mermaid/package-lock.json is not present",),
                {"checked": False, "reason": "not-configured"},
            )
        ]
    if not online:
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "pass",
                "Mermaid security audit skipped in offline mode",
                ("run `pdk diag --online` to query the npm advisory service",),
                {"checked": False, "reason": "offline", "level": NODE_AUDIT_LEVEL},
            )
        ]
    npm = shutil.which("npm")
    if npm is None:
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "warn",
                "Mermaid security audit could not run because npm is missing",
                ("install npm, then rerun `pdk diag --online`",),
                {"checked": False, "reason": "npm-missing", "level": NODE_AUDIT_LEVEL},
            )
        ]
    command = [npm, "audit", "--omit=dev", f"--audit-level={NODE_AUDIT_LEVEL}", "--json"]
    completed = _run(command, cwd=tool_root, timeout=60)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {}
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    raw_counts = metadata.get("vulnerabilities", {}) if isinstance(metadata, dict) else {}
    counts = {
        severity: int(raw_counts.get(severity, 0)) if isinstance(raw_counts, dict) else 0
        for severity in ("low", "moderate", "high", "critical")
    }
    affected = sum(counts[severity] for severity in ("moderate", "high", "critical"))
    data = {
        "checked": True,
        "level": NODE_AUDIT_LEVEL,
        "vulnerabilities": counts,
    }
    if affected:
        details = (
            *(f"{severity}: {count}" for severity, count in counts.items() if count),
            "run `npm audit --omit=dev` in tools/mermaid for remediation detail",
        )
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "warn",
                f"Mermaid dependencies have {affected} moderate-or-higher advisories",
                details,
                data,
            )
        ]
    if completed.returncode:
        evidence = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or f"npm audit exited {completed.returncode}"
        )
        return [
            DiagnosticResult(
                "renderer.mermaid-security",
                "Rendering toolchain",
                "warn",
                "Mermaid security audit was unavailable",
                (_sanitise_text(evidence, root),),
                {**data, "checked": False, "reason": "audit-error"},
            )
        ]
    return [
        DiagnosticResult(
            "renderer.mermaid-security",
            "Rendering toolchain",
            "pass",
            "Mermaid dependencies have no moderate-or-higher advisories",
            (),
            data,
        )
    ]


def _repository_checks(root: Path, online: bool) -> list[DiagnosticResult]:
    git = shutil.which("git")
    if git is None:
        return [
            DiagnosticResult(
                "repository.git",
                "Repository and template maintenance",
                "warn",
                "Git is not available; repository macros and publishing metadata cannot be checked",
            )
        ]
    try:
        top = _run([git, "-C", str(root), "rev-parse", "--show-toplevel"])
    except (OSError, subprocess.SubprocessError) as error:
        return [
            DiagnosticResult(
                "repository.git",
                "Repository and template maintenance",
                "warn",
                "Git repository could not be inspected",
                (str(error),),
            )
        ]
    if top.returncode:
        return [
            DiagnosticResult(
                "repository.git",
                "Repository and template maintenance",
                "warn",
                "Project is not inside a Git repository",
                (top.stderr.strip(),) if top.stderr.strip() else (),
            )
        ]
    git_root = Path(top.stdout.strip()).resolve()
    remotes = _run([git, "-C", str(git_root), "remote", "-v"])
    remote_lines = tuple(
        dict.fromkeys(line for line in remotes.stdout.splitlines() if line.strip())
    )
    checks = [
        DiagnosticResult(
            "repository.git",
            "Repository and template maintenance",
            "pass",
            f"Git repository found at {_display_path(git_root, root)}",
            tuple(_sanitise_text(line, root) for line in remote_lines)
            or ("no remotes configured",),
            {
                "root": _display_path(git_root, root),
                "remotes": [_sanitise_text(line, root) for line in remote_lines],
            },
        )
    ]

    from prodockit.template_sync import (
        MANIFEST_FILE,
        STAMP_FILE,
        TemplateSyncError,
        load_manifest,
        read_template_stamp,
        resolve_template,
    )

    metadata_details: list[str] = []
    metadata_failures: list[str] = []
    manifest_path = root / MANIFEST_FILE
    if manifest_path.is_file():
        try:
            manifest = load_manifest(manifest_path.read_text(encoding="utf-8"))
            ownership_rules = sum(
                map(
                    len,
                    (
                        manifest.template_owns,
                        manifest.project_owns,
                        manifest.shared,
                        manifest.excluded,
                    ),
                )
            )
            metadata_details.append(f"{MANIFEST_FILE}: {ownership_rules} ownership rule(s)")
        except (OSError, UnicodeError, TemplateSyncError) as error:
            metadata_failures.append(str(error))
    try:
        stamp_record = read_template_stamp(root)
    except OSError as error:
        stamp_record = None
        metadata_failures.append(f"{STAMP_FILE}: {error}")
    stamp = stamp_record.revision if stamp_record else None
    applied_release = stamp_record.applied_release if stamp_record else None
    if stamp:
        metadata_details.append(f"{STAMP_FILE} revision: {stamp}")
        if applied_release:
            metadata_details.append(f"Successfully applied template release: {applied_release}")
        else:
            metadata_details.append("Successfully applied template release: not recorded")
    elif (root / STAMP_FILE).exists():
        metadata_failures.append(f"{STAMP_FILE} is empty")
    checks.append(
        DiagnosticResult(
            "repository.template-metadata",
            "Repository and template maintenance",
            "fail" if metadata_failures else "pass",
            "Local template metadata is invalid"
            if metadata_failures
            else "Local template metadata is valid or not present",
            tuple(metadata_details + metadata_failures),
            {
                "stamp": stamp,
                "applied_release": applied_release,
                "manifest_present": manifest_path.is_file(),
            },
        )
    )

    if online and stamp:
        origin = None
        for line in remote_lines:
            fields = line.split()
            if len(fields) >= 2 and fields[0] == "origin" and fields[-1] == "(fetch)":
                origin = fields[1]
                break
        try:
            remote = resolve_template(origin)
            latest = _run([git, "ls-remote", remote, "HEAD"], timeout=15)
            head = (
                latest.stdout.split()[0]
                if latest.returncode == 0 and latest.stdout.split()
                else None
            )
            if head is None:
                raise TemplateSyncError(latest.stderr.strip() or "template host returned no HEAD")
            update = not head.startswith(stamp) and not stamp.startswith(head)
            checks.append(
                DiagnosticResult(
                    "repository.template-update",
                    "Repository and template maintenance",
                    "warn" if update else "pass",
                    "A newer template revision may be available"
                    if update
                    else "Recorded template revision matches the template HEAD",
                    (f"recorded: {stamp}", f"template HEAD: {head}"),
                    {
                        "recorded": stamp,
                        "latest": head,
                        "remote": _sanitise_text(remote, root),
                    },
                )
            )
        except (OSError, subprocess.SubprocessError, TemplateSyncError) as error:
            checks.append(
                DiagnosticResult(
                    "repository.template-update",
                    "Repository and template maintenance",
                    "warn",
                    "Online template comparison was unavailable",
                    (_sanitise_text(str(error), root),),
                )
            )
    return checks


def inspect(
    config_file: str | Path = "zensical.toml",
    *,
    online: bool = False,
    retry_reporter: RetryReporter | None = None,
) -> DiagnosticReport:
    """Inspect the active environment and project without changing either."""
    requested = Path(config_file).expanduser().resolve()
    root = requested.parent
    try:
        config, config_check = _configuration_check(requested)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as error:
        config = None
        config_check = DiagnosticResult(
            "project.configuration",
            "Project configuration and inputs",
            "fail",
            "Project configuration could not be inspected",
            (_sanitise_text(str(error), root),),
        )
    if config is not None:
        root = config.root
    checks: list[DiagnosticResult] = []

    def collect(
        check_id: str,
        section: str,
        name: str,
        probe: Callable[[], list[DiagnosticResult]],
    ) -> None:
        try:
            checks.extend(probe())
        except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as error:
            checks.append(
                DiagnosticResult(
                    check_id,
                    section,
                    "fail",
                    f"{name} could not be inspected",
                    (_sanitise_text(str(error), root),),
                )
            )

    collect(
        "environment.inspection",
        "Environment and installation",
        "The Python environment",
        lambda: _environment_checks(root),
    )
    collect(
        "installation.inspection",
        "Environment and installation",
        "The active installation",
        lambda: _installation_checks(root),
    )
    checks.append(config_check)
    collect(
        "dependencies.inspection",
        "Dependency and managed-file consistency",
        "Dependency and managed-file consistency",
        lambda: _pin_checks(root, online),
    )
    collect(
        "renderer.inspection",
        "Rendering toolchain",
        "The rendering toolchain",
        lambda: (
            _renderer_checks(config, root, retry_reporter=retry_reporter)
            if retry_reporter is not None
            else _renderer_checks(config, root)
        ),
    )
    collect(
        "renderer.security-inspection",
        "Rendering toolchain",
        "The Mermaid security audit",
        lambda: _node_security_checks(root, online),
    )
    collect(
        "repository.inspection",
        "Repository and template maintenance",
        "Repository and template metadata",
        lambda: _repository_checks(root, online),
    )
    return DiagnosticReport(
        config_file=_display_path(requested, root),
        project_root=_display_path(root, Path.cwd()),
        online=online,
        checks=tuple(checks),
    )


__all__ = [
    "DIAGNOSTIC_IDS",
    "REPAIR_REGISTRY",
    "CommandInfo",
    "DiagnosticReport",
    "DiagnosticResult",
    "RepairApplyResult",
    "RepairCandidate",
    "RepairChoice",
    "RepairDryRun",
    "RepairPolicy",
    "RepairRollbackError",
    "RepairTransaction",
    "RepairTransactionError",
    "build_repair_dry_run",
    "command_in_environment",
    "inspect",
    "repair_locked_renderer",
    "repair_pin_declarations",
    "repair_project_configuration",
    "repair_shared_file",
    "same_path",
]
