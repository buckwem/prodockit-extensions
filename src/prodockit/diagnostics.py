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
from prodockit.pins import DEFAULT_PACKAGES, discover, resolve_latest
from prodockit.project_config import ProjectConfig, ProjectConfigError, load_project_config
from prodockit.project_integrity import renderer_requirements
from prodockit.renderer_health import find_browser, probe_mathjax, probe_mermaid
from prodockit.shared_files import SharedFileError
from prodockit.shared_files import inspect as inspect_shared_files

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
            raise ValueError(
                f"diagnostic {self.id!r} has no registered repair disposition"
            )

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
        self.created = timestamp or datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S.%fZ"
        )
        if not re.fullmatch(r"[A-Za-z0-9._-]+", self.created):
            raise RepairTransactionError("invalid diagnostic transaction timestamp")
        self.quarantine = (
            self.boundary
            / ".prodockit-quarantine"
            / "diagnostics"
            / self.created
        )
        self.manifest_path = self.quarantine / "manifest.json"
        self._entries: list[dict[str, Any]] = []
        self._moves: list[tuple[Path, Path]] = []
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
        self._moves.append((original, backup))
        self._status = "applying"
        self._write_manifest()

    def commit(self) -> None:
        self._status = "applied"
        self._write_manifest()

    def rollback(self, reason: str) -> None:
        failures: list[str] = []
        for original, backup in reversed(self._moves):
            try:
                if original.exists() or original.is_symlink():
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
    if check.id == "project.configuration":
        choices = (
            RepairChoice(
                "adopt-project-repair",
                "Use Adoption to repair independent Prodockit project integration",
                command_argv=("prodockit", "adopt", "--apply"),
                affected_paths=("zensical.toml", ".prodockit-components.toml"),
                warning=(
                    "Adoption can change project configuration and generated "
                    "tool files; it asks before each stage and does not use prodockit-template."
                ),
                warning_severity="warning",
                rollback="restore the changed project files from version control",
            ),
            RepairChoice(
                "inspect-configuration",
                "Show the detailed configuration findings",
                command_argv=("pdk", "config", "--check"),
                rollback="read-only",
            ),
            _leave_unchanged(),
        )
        status = "available"
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


def _shared_files_candidate(check: DiagnosticResult) -> RepairCandidate:
    policy = REPAIR_REGISTRY[check.id]
    raw_files = check.data.get("drifted_files", ())
    paths = tuple(
        str(item.get("path"))
        for item in raw_files
        if isinstance(item, dict) and item.get("path")
    )
    changed_existing = any(
        isinstance(item, dict) and item.get("status") == "different" for item in raw_files
    )
    return RepairCandidate(
        "dependencies.shared-files.apply",
        check.id,
        policy.disposition,
        "available",
        check.summary,
        policy.reason,
        policy.remediation,
        (
            RepairChoice(
                "apply-installed-shared-files",
                "Apply the installed Prodockit shared files",
                command_argv=("pdk", "shared-files", "--apply"),
                affected_paths=paths,
                warning=(
                    "This replaces existing managed file bytes; review local "
                    "changes first."
                    if changed_existing
                    else None
                ),
                warning_severity="warning" if changed_existing else None,
                rollback="restore replaced files from the diagnostic quarantine",
            ),
            _leave_unchanged(),
        ),
    )


def _pin_candidates(check: DiagnosticResult) -> list[RepairCandidate]:
    policy = REPAIR_REGISTRY[check.id]
    candidates: list[RepairCandidate] = []
    packages = check.data.get("packages", ())
    for package_data in packages:
        if not isinstance(package_data, dict):
            continue
        package = str(package_data.get("package", ""))
        versions = tuple(str(item) for item in package_data.get("versions", ()))
        latest = package_data.get("latest")
        paths = tuple(
            dict.fromkeys(
                str(site.get("path"))
                for site in package_data.get("sites", ())
                if isinstance(site, dict) and site.get("path")
            )
        )
        if len(versions) > 1:
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
                    for version in versions
                ),
                _leave_unchanged(),
            )
            candidates.append(
                RepairCandidate(
                    f"dependencies.pins.align-{package}",
                    check.id,
                    "ambiguous",
                    "available",
                    f"Choose a version for inconsistent {package} declarations",
                    policy.reason,
                    policy.remediation,
                    choices,
                )
            )
        elif latest and versions and str(latest) != versions[0]:
            candidates.append(
                RepairCandidate(
                    f"dependencies.pins.review-{package}-update",
                    check.id,
                    "manual",
                    "manual",
                    f"Review {package} {versions[0]} -> {latest}",
                    "A newer version is an author decision, not a diagnostic repair.",
                    f"Review output before running `pdk pins --set {package}={latest}`.",
                    (
                        RepairChoice(
                            f"review-{package}-{latest}",
                            f"Set every {package} declaration to {latest} after review",
                            command_argv=("pdk", "pins", "--set", f"{package}={latest}"),
                            affected_paths=paths,
                            warning=(
                                "This adopts an online version and can change "
                                "website and PDF output."
                            ),
                            warning_severity="warning",
                            network=True,
                            rollback="restore changed declaration files from version control",
                        ),
                        _leave_unchanged(),
                    ),
                )
            )
    return candidates or [_generic_candidate(check)]


def _renderer_candidate(check: DiagnosticResult) -> RepairCandidate:
    policy = REPAIR_REGISTRY[check.id]
    feature = "mermaid" if check.id == "renderer.mermaid" else "maths"
    paths = ("tools/mermaid",) if feature == "mermaid" else ("tools/mathjax", "docs/javascripts")
    return RepairCandidate(
        f"{check.id}.adopt-project-repair",
        check.id,
        policy.disposition,
        "available",
        check.summary,
        policy.reason,
        policy.remediation,
        (
            RepairChoice(
                "adopt-project-repair",
                f"Use Adoption to repair project-local {feature} support",
                command_argv=("prodockit", "adopt", "--apply", f"--{feature}"),
                affected_paths=paths,
                prerequisites=("Node and npm are healthy", "the project lockfile is valid"),
                warning=(
                    "This can download and execute locked third-party packages and "
                    "replace incomplete generated tooling; Adoption remains independent of "
                    "prodockit-template and asks before each stage."
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
            candidates.append(_shared_files_candidate(check))
        elif check.id == "dependencies.pins":
            candidates.extend(_pin_candidates(check))
        elif check.id in {"renderer.mermaid", "renderer.mathjax"}:
            candidates.append(_renderer_candidate(check))
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
    """Cross-platform path equality used by environment diagnostics and tests."""
    return _normalise_path(left, platform=platform) == _normalise_path(right, platform=platform)


def command_in_environment(
    command: str,
    prefix: str,
    scripts: str,
    *,
    platform: str | None = None,
) -> bool:
    """Return whether a command belongs to the active Python environment.

    Resolve POSIX symlinks so pipx shims are accepted when they point into the
    active prefix. Windows launchers are compared lexically because resolving a
    Windows path is not meaningful on a non-Windows test host.
    """
    platform = sys.platform if platform is None else platform
    path_module = ntpath if platform == "win32" else os.path
    candidates = [command]
    if platform != "win32":
        candidates.append(str(Path(command).resolve()))
    normalised_prefix = _normalise_path(prefix, platform=platform)
    normalised_scripts = _normalise_path(scripts, platform=platform)
    for candidate in candidates:
        normalised = _normalise_path(candidate, platform=platform)
        if _normalise_path(path_module.dirname(candidate), platform=platform) == normalised_scripts:
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
            distribution = (
                normalized if normalized in REPAIRABLE_DISTRIBUTIONS else filename_name
            )
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
                raise MetadataRepairError(
                    "metadata repair requires an active virtual environment"
                )
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
    return config, DiagnosticResult(
        "project.configuration",
        "Project configuration and inputs",
        "fail" if details else "pass",
        f"Configuration has {len(details)} actionable problem(s)"
        if details
        else "Configuration and local project inputs pass",
        details + (("run `pdk config --check` for the complete report",) if details else ()),
        {"config_file": _display_path(report.path, config.root), "problem_count": len(details)},
    )


def _pin_checks(root: Path, online: bool) -> list[DiagnosticResult]:
    states = discover(str(root), DEFAULT_PACKAGES)
    resolve_latest(states, offline=not online)
    inconsistent = [state for state in states.values() if not state.is_consistent]
    behind = [state for state in states.values() if state.is_behind]
    lookup_errors = [
        f"{state.package}: {state.latest_error}"
        for state in states.values()
        if online and state.on_pypi and state.latest is None and state.latest_error
    ]
    details = [f"{state.package}: {', '.join(state.versions)}" for state in inconsistent]
    details.extend(
        f"{state.package}: {state.current} -> {state.latest} available" for state in behind
    )
    details.extend(lookup_errors)
    status: Status = "fail" if inconsistent else ("warn" if behind or lookup_errors else "pass")
    summary = (
        f"{len(inconsistent)} package declaration(s) are inconsistent"
        if inconsistent
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
                "updates": [state.package for state in behind],
                "packages": [
                    {
                        "package": state.package,
                        "versions": state.versions,
                        "latest": state.latest,
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
                        {"path": state.file.target, "status": state.status}
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


def _renderer_checks(config: ProjectConfig | None, root: Path) -> list[DiagnosticResult]:
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
    mmdc_probe = probe_mermaid(mmdc) if mmdc else None
    mmdc_ok = bool(mmdc_probe and mmdc_probe.ok)
    mmdc_error = (
        _sanitise_text(mmdc_probe.error, root)
        if mmdc_probe and mmdc_probe.error
        else None
    )
    checks.append(
        DiagnosticResult(
            "renderer.mermaid",
            "Rendering toolchain",
            "pass" if mmdc_ok else ("fail" if mermaid_required else "warn"),
            "Mermaid CLI is available"
            if mmdc_ok
            else ("Mermaid CLI is unusable" if mmdc else "Mermaid CLI is missing")
            + (" but required by this project" if mermaid_required else " (optional)"),
            tuple(
                detail
                for detail in (
                    f"path: {_display_path(mmdc, root)}" if mmdc else None,
                    f"health probe: {mmdc_error}" if mmdc_error else None,
                )
                if detail
            ),
            {
                "required": mermaid_required,
                "path": _display_path(mmdc, root) if mmdc else None,
                "version": mmdc_probe.version if mmdc_probe else None,
                "error": mmdc_error,
            },
        )
    )

    browser = find_browser()
    browser_version = None
    browser_error = None
    if browser:
        try:
            browser_result = _run([browser, "--version"])
            browser_output = "\n".join(
                part.strip()
                for part in (browser_result.stdout, browser_result.stderr)
                if part.strip()
            )
            if browser_result.returncode:
                browser_error = _sanitise_text(
                    browser_output or f"exited {browser_result.returncode}", root
                )
            else:
                browser_version = _first_version(browser_output)
                if browser_version is None:
                    browser_error = "reported no version"
        except (OSError, subprocess.SubprocessError) as error:
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
            "Browser executable can run"
            if browser_ok
            else (
                "Browser executable is unusable"
                if browser
                else "No explicit Chrome/Chromium executable found"
            )
            + (
                "; Mermaid CLI may use its bundled browser"
                if not browser and mermaid_required
                else " (optional)" if not mermaid_required else ""
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
                "version": browser_version,
                "error": browser_error,
            },
        )
    )

    mathjax_modules = root / "tools" / "mathjax" / "node_modules" / "mathjax-full"
    node = shutil.which("node")
    mathjax_probe = probe_mathjax(node, tex2svg) if node and tex2svg else None
    mathjax_ok = bool(mathjax_modules.is_dir() and mathjax_probe and mathjax_probe.ok)
    mathjax_error = (
        _sanitise_text(mathjax_probe.error, root)
        if mathjax_probe and mathjax_probe.error
        else None
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
                    else "node is not found on PATH" if tex2svg else None
                ),
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
            metadata_details.append(
                f"Successfully applied template release: {applied_release}"
            )
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


def inspect(config_file: str | Path = "zensical.toml", *, online: bool = False) -> DiagnosticReport:
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
        lambda: _renderer_checks(config, root),
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
    "same_path",
]
