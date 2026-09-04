# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Select CI work from a complete, validated Git change range.

The native installed-wheel suites are valuable precisely because they are
expensive: they exercise real path and architecture boundaries that unit tests
cannot. This module keeps those complete matrices, but only selects a matrix
when its component or acceptance boundary changed.

Selection fails closed. A missing Git object, a failed diff, an unrecognised
runtime file, malformed output, or an empty range that should contain a change
selects every scope. Documentation-only changes can therefore be quick
without allowing a broken classifier to make a risky change look irrelevant.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by Python 3.10 CI
    import tomli as tomllib

PYTHON_VERSIONS = ("3.10", "3.11", "3.12", "3.13", "3.14")


@dataclass(frozen=True)
class Scope:
    """The checks selected by a collection of repository paths."""

    python_compat: bool
    adopt: bool
    pdf: bool
    bootstrap: bool
    full_python: bool = False
    diagnostics: bool = False

    @property
    def python_matrix(self) -> tuple[str, ...]:
        """Return the smallest supported-version matrix safe for the change."""

        if self.full_python:
            return PYTHON_VERSIONS
        return (
            (PYTHON_VERSIONS[0], PYTHON_VERSIONS[-1])
            if self.python_compat
            else (PYTHON_VERSIONS[-1],)
        )


@dataclass(frozen=True)
class Classification:
    """A scope together with human-readable reasons for selecting it."""

    scope: Scope
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ChangedRange:
    """The validated paths from one Git event, or a reason to run everything."""

    paths: tuple[str, ...] = ()
    full: bool = False
    reason: str = ""


_ALL_COMPONENTS = frozenset({"adopt", "pdf", "bootstrap", "diagnostics"})

_ALL_RUNTIME_FILES = {
    "pyproject.toml",
    "src/prodockit/__init__.py",
    "src/prodockit/__main__.py",
    "src/prodockit/cli.py",
    "src/prodockit/diagnostics.py",
    "src/prodockit/renderer_health.py",
    "src/prodockit/renderer_resilience.py",
    "src/prodockit/shared_files.py",
    "src/prodockit/util.py",
    "src/prodockit/py.typed",
    "tools/ci_scope.py",
}

_ADOPT_RUNTIME_FILES = {
    "src/prodockit/_zensical_defaults.py",
    "src/prodockit/adopt.py",
    "src/prodockit/init_tools.py",
    "src/prodockit/mathjax.py",
}

_PDF_RUNTIME_FILES = {
    "src/prodockit/_markdown_toc.py",
    "src/prodockit/_zensical.py",
    "src/prodockit/_zensical_page_context.py",
    "src/prodockit/bibliography.py",
    "src/prodockit/citations.py",
    "src/prodockit/environment.py",
    "src/prodockit/glossary.py",
    "src/prodockit/headings.py",
    "src/prodockit/index.py",
    "src/prodockit/refs.py",
    "src/prodockit/revision_dates.py",
    "src/prodockit/settings.py",
    "src/prodockit/steps.py",
    "src/prodockit/tables.py",
    "src/prodockit/tree.py",
    "src/prodockit/zensical_macros.py",
}

_PYTHON_ONLY_RUNTIME_FILES = {
    "src/prodockit/config_diagnostics.py",
    "src/prodockit/pins.py",
    "src/prodockit/project_integrity.py",
    "src/prodockit/testing/__init__.py",
    "src/prodockit/testing/checks.py",
    "src/prodockit/testing/plugin.py",
    "src/prodockit/tools.py",
    "src/prodockit/wordcount.py",
}

_CI_ONLY_FILES = {
    "tools/canonical_site_config.py",
    "tools/render_documentation_diagrams.py",
}

_COMPONENT_FILES: dict[str, frozenset[str]] = {
    "docs/stylesheets/pdk.css": frozenset({"adopt", "pdf"}),
    "docs/stylesheets/pdk-pdf.css": frozenset({"pdf"}),
    "src/prodockit/project_config.py": frozenset({"adopt", "pdf", "diagnostics"}),
    "src/prodockit/config_diagnostics.py": frozenset({"diagnostics"}),
    "src/prodockit/init_tools.py": frozenset({"adopt", "bootstrap", "diagnostics"}),
    "src/prodockit/mathjax.py": frozenset({"adopt", "bootstrap", "diagnostics"}),
    "src/prodockit/pins.py": frozenset({"adopt", "diagnostics"}),
    "src/prodockit/toolchain.py": frozenset({"adopt", "diagnostics"}),
    "src/prodockit/template_sync.py": frozenset({"adopt"}),
    "src/prodockit/template_prerequisites.py": frozenset({"adopt"}),
    "src/prodockit/project_integrity.py": frozenset({"diagnostics"}),
    "src/prodockit/settings.py": frozenset({"pdf", "diagnostics"}),
    "src/prodockit/sync_repo.py": frozenset({"bootstrap", "pdf"}),
    "tools/adopt_acceptance.py": frozenset({"adopt"}),
    "tools/adopt_native_upgrade.py": frozenset({"adopt"}),
    "tools/template_sync_acceptance.py": frozenset({"adopt"}),
    "tools/_diagnostics_repair_acceptance_driver.py": frozenset({"diagnostics"}),
    "tools/diagnostics_repair_acceptance.py": frozenset({"diagnostics"}),
    "tools/adopt_toolchain_acceptance.py": frozenset({"diagnostics"}),
    "tools/_adopt_toolchain_acceptance_driver.py": frozenset({"diagnostics"}),
    "tools/check_shared_file_wheel.py": frozenset({"pdf"}),
    "tools/pdf_from_site_acceptance.py": frozenset({"pdf"}),
    "tools/bootstrap_acceptance.py": frozenset({"bootstrap"}),
    "tools/bootstrap_live_provider_read_only.py": frozenset({"bootstrap"}),
    "tools/bootstrap_live_provider_read_write.py": frozenset({"bootstrap"}),
    "tools/bootstrap_live_provider_lifecycle.py": frozenset({"bootstrap"}),
    "tools/bootstrap_live_provider_prerequisites.py": frozenset({"bootstrap"}),
    "tools/bootstrap_live_provider_github_fixture.py": frozenset({"bootstrap"}),
    "tools/bootstrap_live_provider_github_lifecycle.py": frozenset({"bootstrap"}),
    "tools/bootstrap_live_provider_ephemeral_key.py": frozenset({"bootstrap"}),
    "tools/bootstrap_live_provider_surrey_fixture.py": frozenset({"bootstrap"}),
    "tools/surrey_retained_state.py": frozenset({"bootstrap"}),
    "tools/canonical_wheel.py": frozenset({"bootstrap"}),
    "tools/live_provider_state.py": frozenset({"bootstrap"}),
    "tools/live_provider_resilience.py": frozenset({"bootstrap"}),
    "tools/release_gate.py": frozenset({"bootstrap"}),
    "tools/release_gate_provider_status.py": frozenset({"bootstrap"}),
    "tools/release_gate_state.py": frozenset({"bootstrap"}),
    "tools/_bootstrap_acceptance_driver.py": frozenset({"bootstrap"}),
    "tools/bootstrap_native_install.py": frozenset({"bootstrap"}),
    "tools/bootstrap_native_upgrade.py": frozenset({"bootstrap"}),
    "tools/native_download.py": frozenset({"bootstrap"}),
    ".github/workflows/adopt-install.yml": frozenset({"adopt"}),
    ".github/workflows/diag-repair.yml": frozenset({"diagnostics"}),
    ".github/workflows/pdf-built-site-wheel.yml": frozenset({"pdf"}),
    ".github/workflows/bootstrap-install.yml": frozenset({"bootstrap"}),
    ".github/workflows/bootstrap-live-provider-github.yml": frozenset({"bootstrap"}),
    ".github/workflows/bootstrap-live-provider-surrey.yml": frozenset({"bootstrap"}),
    ".github/workflows/bootstrap-live-provider-surrey-recovery.yml": frozenset({"bootstrap"}),
    ".github/workflows/bootstrap-live-provider-surrey-connectivity.yml": frozenset(
        {"bootstrap"}
    ),
    ".github/workflows/release-gate.yml": frozenset({"bootstrap"}),
    ".gitlab-ci.yml": frozenset({"bootstrap"}),
    ".gitlab/bootstrap-live-provider-surrey.yml": frozenset({"bootstrap"}),
}

_FULL_PYTHON_FILES = {
    "pyproject.toml",
    "tools/ci_scope.py",
    ".github/workflows/ci.yml",
}


def _normalise(path: str) -> str:
    """Return a validated repository-relative POSIX path."""

    value = path.strip().replace("\\", "/")
    candidate = PurePosixPath(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"invalid repository path: {path!r}")
    return candidate.as_posix()


def owners_for_path(path: str) -> frozenset[str] | None:
    """Return installed-wheel owners, or ``None`` for unknown implementation.

    An empty set is an explicit exemption: the path is still covered by normal
    CI, but no native acceptance matrix consumes it.
    """

    if path in _ALL_RUNTIME_FILES:
        return _ALL_COMPONENTS
    if path in _COMPONENT_FILES:
        return _COMPONENT_FILES[path]
    if path in _ADOPT_RUNTIME_FILES:
        return frozenset({"adopt", "bootstrap"})
    if path in _PDF_RUNTIME_FILES:
        return frozenset({"pdf"})
    if path in _PYTHON_ONLY_RUNTIME_FILES:
        return frozenset()
    if path in _CI_ONLY_FILES:
        return frozenset()
    if path.startswith("src/prodockit/bootstrap/"):
        return frozenset({"bootstrap"})
    if path.startswith("src/prodockit/pdf/"):
        return frozenset({"pdf"})
    if path.startswith("src/prodockit/_tools_template/"):
        return frozenset({"adopt", "bootstrap"})
    if path.startswith("requirements"):
        return _ALL_COMPONENTS
    if path.startswith(".github/workflows/"):
        return _ALL_COMPONENTS
    if path.startswith("src/prodockit/") or (path.startswith("tools/") and path.endswith(".py")):
        return None
    return frozenset()


def classify_details(paths: Sequence[str]) -> Classification:
    """Classify *paths*, widening on unknown implementation files."""

    changed = tuple(sorted({_normalise(path) for path in paths if path.strip()}))
    components: set[str] = set()
    reasons: list[str] = []
    unknown: list[str] = []
    for path in changed:
        owners = owners_for_path(path)
        if owners is None:
            unknown.append(path)
            components.update(_ALL_COMPONENTS)
            continue
        if owners:
            components.update(owners)
            reasons.append(f"{path}: {', '.join(sorted(owners))}")

    if unknown:
        reasons.append("unknown implementation path; selected all: " + ", ".join(unknown))

    python_compat = any(
        path.startswith(("src/", "tests/", "tools/", ".github/workflows/"))
        or path == "pyproject.toml"
        or path.startswith("requirements")
        for path in changed
    )
    full_python = any(
        path in _FULL_PYTHON_FILES
        or path.startswith("requirements")
        or (path.startswith(".github/workflows/") and path != ".github/workflows/docs.yml")
        for path in changed
    ) or bool(unknown)

    scope = Scope(
        python_compat=python_compat,
        adopt="adopt" in components,
        pdf="pdf" in components,
        bootstrap="bootstrap" in components,
        full_python=full_python,
        diagnostics="diagnostics" in components,
    )
    return Classification(scope, tuple(reasons or ("normal CI only",)))


def classify(paths: list[str] | tuple[str, ...]) -> Scope:
    """Compatibility wrapper returning only the selected scope."""

    return classify_details(paths).scope


def all_scope() -> Scope:
    """Return the comprehensive manual, scheduled, or fail-closed scope."""

    return Scope(True, True, True, True, True, True)


def output_lines(
    scope: Scope,
    *,
    main: bool = False,
    adopt_native: bool = False,
    bootstrap_native: bool = False,
) -> tuple[str, ...]:
    """Format values for ``GITHUB_OUTPUT``.

    ``main`` remains accepted for callers from older branches; it means a
    comprehensive matrix, not merely that the event happened on main.
    """

    versions = PYTHON_VERSIONS if main else scope.python_matrix
    return (
        f"python-matrix={json.dumps(versions, separators=(',', ':'))}",
        f"adopt={'true' if scope.adopt else 'false'}",
        f"pdf={'true' if scope.pdf else 'false'}",
        f"bootstrap={'true' if scope.bootstrap else 'false'}",
        f"diagnostics={'true' if scope.diagnostics else 'false'}",
        f"adopt-native={'true' if adopt_native else 'false'}",
        f"bootstrap-native={'true' if bootstrap_native else 'false'}",
    )


GitRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]]


def _run_git(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True, check=False)


_NATIVE_BOOTSTRAP_FILES = {
    ".github/workflows/bootstrap-install.yml",
    "tools/ci_scope.py",
    "tools/bootstrap_native_install.py",
    "tools/bootstrap_native_upgrade.py",
    "tools/native_download.py",
}

_NATIVE_ADOPT_FILES = {
    ".github/workflows/adopt-install.yml",
    "tools/adopt_native_upgrade.py",
    "tools/ci_scope.py",
}


def _project_version_at(ref: str, *, git: GitRunner = _run_git) -> str:
    """Read the package version from *ref* without changing the checkout."""

    result = git(("git", "show", f"{ref}:pyproject.toml"))
    if result.returncode != 0:
        raise RuntimeError(f"could not read pyproject.toml at {ref}")
    document = tomllib.loads(result.stdout.decode("utf-8", errors="strict"))
    version = document.get("project", {}).get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"pyproject.toml at {ref} has no project version")
    return version.strip()


def bootstrap_native_for_event(
    event_name: str,
    event: dict[str, Any],
    changes: ChangedRange,
    *,
    git: GitRunner = _run_git,
) -> bool:
    """Select real package installs for release candidates and their own code.

    Ordinary pull requests retain the fast hermetic Bootstrap matrix. A change
    to the native harness has to exercise itself before merge, while a package
    version change identifies the release pull request that must cross the
    real package-manager boundary. Manual dispatch remains an explicit way to
    repeat the expensive check. Detection fails closed for a pull request: an
    unreadable version selects the native matrix rather than silently skipping
    a release gate.
    """

    if event_name == "workflow_dispatch":
        return True
    if event_name != "pull_request":
        return False
    if changes.full:
        return True
    if any(path in _NATIVE_BOOTSTRAP_FILES for path in changes.paths):
        return True
    try:
        pull = event["pull_request"]
        base = _sha(pull["base"]["sha"])
        head = _sha(pull["head"]["sha"])
        return _project_version_at(base, git=git) != _project_version_at(head, git=git)
    except (KeyError, TypeError, UnicodeError, ValueError, RuntimeError, tomllib.TOMLDecodeError):
        return True


def adopt_native_for_event(
    event_name: str,
    event: dict[str, Any],
    changes: ChangedRange,
    *,
    git: GitRunner = _run_git,
) -> bool:
    """Select the real Adopt upgrade for releases and its own test code.

    The ordinary installed-wheel matrix exercises Adopt changes on every
    relevant pull request.  This slower gate downloads an older published
    Prodockit release, creates a fully adopted project, and upgrades it with
    the candidate wheel on all five architectures.  A package version change
    is therefore the normal boundary.  Changes to the native workflow, harness
    or selector also exercise the gate before those changes can be merged, and
    a manual dispatch provides an explicit diagnostic rerun.  It is not
    repeated for the resulting push, schedules, or ordinary Adopt work.

    If a pull request changes ``pyproject.toml`` but either version cannot be
    read, select the gate rather than risk mistaking a malformed release pull
    request for ordinary work.
    """

    if event_name == "workflow_dispatch":
        return True
    if event_name != "pull_request":
        return False
    if changes.full:
        return True
    if any(path in _NATIVE_ADOPT_FILES for path in changes.paths):
        return True
    if "pyproject.toml" not in changes.paths:
        return False
    try:
        pull = event["pull_request"]
        base = _sha(pull["base"]["sha"])
        head = _sha(pull["head"]["sha"])
        return _project_version_at(base, git=git) != _project_version_at(head, git=git)
    except (KeyError, TypeError, UnicodeError, ValueError, RuntimeError, tomllib.TOMLDecodeError):
        return True


def _sha(value: object) -> str:
    text = str(value or "").strip()
    if len(text) != 40 or any(character not in "0123456789abcdefABCDEF" for character in text):
        raise ValueError(f"invalid Git SHA: {text!r}")
    if set(text) == {"0"}:
        raise ValueError("zero Git SHA")
    return text


def _full_ci_label(event: dict[str, Any]) -> bool:
    labels = event.get("pull_request", {}).get("labels", [])
    return any(isinstance(label, dict) and label.get("name") == "full-ci" for label in labels)


def changed_range_for_event(
    event_name: str,
    event: dict[str, Any],
    *,
    force_all: bool = False,
    git: GitRunner = _run_git,
) -> ChangedRange:
    """Collect a complete event range, returning full scope on uncertainty."""

    if force_all or _full_ci_label(event):
        return ChangedRange(full=True, reason="full CI was requested")
    if event_name in {"workflow_dispatch", "schedule"}:
        return ChangedRange(full=True, reason=f"{event_name} runs the comprehensive backstop")
    try:
        if event_name == "pull_request":
            pull = event["pull_request"]
            base = _sha(pull["base"]["sha"])
            head = _sha(pull["head"]["sha"])
            merged = git(("git", "merge-base", base, head))
            if merged.returncode != 0:
                raise RuntimeError("git merge-base failed")
            start = _sha(merged.stdout.decode("ascii", errors="strict").strip())
            end = head
        elif event_name == "merge_group":
            group = event["merge_group"]
            start = _sha(group["base_sha"])
            end = _sha(group["head_sha"])
        elif event_name == "push":
            start = _sha(event["before"])
            end = _sha(event.get("after") or os.environ.get("GITHUB_SHA"))
        else:
            return ChangedRange(full=True, reason=f"unsupported event {event_name!r}")

        result = git(
            (
                "git",
                "diff",
                "--no-renames",
                "--name-only",
                "-z",
                "--diff-filter=ACDMR",
                start,
                end,
            )
        )
        if result.returncode != 0:
            raise RuntimeError("git diff failed")
        decoded = result.stdout.decode("utf-8", errors="strict")
        if decoded and not decoded.endswith("\0"):
            raise ValueError("malformed NUL-delimited Git output")
        paths = tuple(_normalise(path) for path in decoded.split("\0") if path)
        if not paths:
            return ChangedRange(full=True, reason="the event range unexpectedly contained no paths")
        return ChangedRange(paths=paths, reason=f"classified {start[:8]}..{end[:8]}")
    except (KeyError, TypeError, UnicodeError, ValueError, RuntimeError) as error:
        return ChangedRange(full=True, reason=f"scope collection failed closed: {error}")


def _event_from_environment() -> tuple[str, dict[str, Any]]:
    path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not path:
        raise ValueError("GITHUB_EVENT_PATH is not set")
    with open(path, encoding="utf-8") as stream:
        event = json.load(stream)
    if not isinstance(event, dict):
        raise ValueError("GitHub event payload is not an object")
    return os.environ.get("GITHUB_EVENT_NAME", ""), event


def _write_summary(
    changes: ChangedRange,
    classification: Classification,
    *,
    adopt_native: bool = False,
    bootstrap_native: bool = False,
) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    selected = [
        name
        for name, value in (
            ("Adopt installed wheel", classification.scope.adopt),
            ("PDF installed wheel", classification.scope.pdf),
            ("Bootstrap installed wheel", classification.scope.bootstrap),
            ("Diagnostic repair installed wheel", classification.scope.diagnostics),
        )
        if value
    ]
    lines = [
        "## CI scope",
        "",
        f"- Range: {changes.reason}",
        f"- Python: {', '.join(classification.scope.python_matrix)}",
        f"- Native matrices: {', '.join(selected) if selected else 'none'}",
        "- Real Adopt project upgrade: " + ("selected" if adopt_native else "not selected"),
        "- Real Bootstrap package installs: "
        + ("selected" if bootstrap_native else "not selected"),
        "",
        "### Reasons",
        "",
        *(f"- {reason}" for reason in classification.reasons),
    ]
    if changes.paths:
        lines += ["", "### Changed paths", "", *(f"- `{path}`" for path in changes.paths)]
    with open(path, "a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    """Collect and classify changes, then emit GitHub job outputs."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="select every scope")
    parser.add_argument(
        "--github-event",
        action="store_true",
        help="derive a fail-closed range from the GitHub event environment",
    )
    args = parser.parse_args(argv)

    event_name = ""
    event: dict[str, Any] = {}
    adopt_native = False
    bootstrap_native = False
    if args.all:
        changes = ChangedRange(full=True, reason="all scopes requested")
        classification = Classification(all_scope(), (changes.reason,))
    elif args.github_event:
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        try:
            event_name, event = _event_from_environment()
            changes = changed_range_for_event(
                event_name,
                event,
                force_all=os.environ.get("FULL_CI", "").lower() == "true",
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            changes = ChangedRange(full=True, reason=f"event loading failed closed: {error}")
        classification = (
            Classification(all_scope(), (changes.reason,))
            if changes.full
            else classify_details(changes.paths)
        )
        adopt_native = adopt_native_for_event(event_name, event, changes)
        bootstrap_native = bootstrap_native_for_event(event_name, event, changes)
    else:
        changes = ChangedRange(paths=tuple(sys.stdin.read().splitlines()), reason="stdin paths")
        classification = classify_details(changes.paths)

    print(
        "\n".join(
            output_lines(
                classification.scope,
                adopt_native=adopt_native,
                bootstrap_native=bootstrap_native,
            )
        )
    )
    _write_summary(
        changes,
        classification,
        adopt_native=adopt_native,
        bootstrap_native=bootstrap_native,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by workflows
    raise SystemExit(main())
