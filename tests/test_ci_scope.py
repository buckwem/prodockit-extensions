# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "ci_scope", Path(__file__).parents[1] / "tools" / "ci_scope.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
ChangedRange = _MODULE.ChangedRange
Scope = _MODULE.Scope
all_scope = _MODULE.all_scope
changed_range_for_event = _MODULE.changed_range_for_event
classify = _MODULE.classify
output_lines = _MODULE.output_lines
owners_for_path = _MODULE.owners_for_path

ROOT = Path(__file__).parents[1]
BASE = "1" * 40
HEAD = "2" * 40
MERGE_BASE = "3" * 40


def _completed(returncode: int = 0, stdout: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=b"")


def _setup_python_steps(workflow: str) -> list[str]:
    """Return each complete ``actions/setup-python`` step in a workflow."""
    lines = workflow.splitlines()
    steps: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("- uses: actions/setup-python@"):
            continue
        indent = len(line) - len(stripped)
        block = [line]
        for following in lines[index + 1 :]:
            following_stripped = following.lstrip()
            following_indent = len(following) - len(following_stripped)
            if following_indent == indent and following_stripped.startswith("- "):
                break
            block.append(following)
        steps.append("\n".join(block))
    return steps


def test_documentation_only_change_uses_the_fast_pr_scope() -> None:
    scope = classify(["docs/macros.md", "zensical.toml"])

    assert scope == Scope(False, False, False, False)
    assert scope.python_matrix == ("3.14",)


def test_unit_test_only_change_does_not_start_a_native_matrix() -> None:
    scope = classify(["tests/test_adopt.py", "tests/test_pdf_site.py"])

    assert scope == Scope(True, False, False, False)
    assert scope.python_matrix == ("3.10", "3.14")


def test_component_runtime_changes_select_only_their_native_matrix() -> None:
    assert classify(["src/prodockit/adopt.py"]) == Scope(True, True, False, True)
    assert classify(["src/prodockit/pdf/site.py"]) == Scope(True, False, True, False)
    assert classify(["src/prodockit/bootstrap/stages.py"]) == Scope(
        True, False, False, True
    )


def test_component_acceptance_and_workflow_files_select_their_own_matrix() -> None:
    for path, component in (
        ("tools/adopt_acceptance.py", "adopt"),
        ("tools/pdf_from_site_acceptance.py", "pdf"),
        ("tools/bootstrap_acceptance.py", "bootstrap"),
        (".github/workflows/adopt-install.yml", "adopt"),
        (".github/workflows/pdf-built-site-wheel.yml", "pdf"),
        (".github/workflows/bootstrap-install.yml", "bootstrap"),
    ):
        scope = classify([path])
        assert getattr(scope, component), path


def test_shared_packaging_and_command_files_select_every_matrix() -> None:
    for path in ("pyproject.toml", "src/prodockit/cli.py", "requirements.txt"):
        scope = classify([path])
        assert scope.adopt and scope.pdf and scope.bootstrap, path


def test_styles_and_project_configuration_have_narrow_explicit_owners() -> None:
    assert classify(["docs/stylesheets/pdk.css"]) == Scope(False, True, True, False)
    assert classify(["docs/stylesheets/pdk-pdf.css"]) == Scope(False, False, True, False)
    assert classify(["src/prodockit/project_config.py"]) == Scope(
        True, True, True, False
    )


def test_unknown_implementation_path_fails_closed_to_every_matrix() -> None:
    scope = classify(["src/prodockit/a_future_component.py"])

    assert scope == Scope(True, True, True, True, True)


def test_every_runtime_asset_and_ci_tool_has_an_explicit_owner_or_exemption() -> None:
    paths = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src" / "prodockit").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    paths.update(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tools").glob("*.py")
    )
    paths.update(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "docs" / "stylesheets").glob("pdk*.css")
    )

    unknown = [path for path in sorted(paths) if owners_for_path(path) is None]
    assert not unknown, f"CI ownership is missing for: {unknown}"


def test_pull_request_uses_merge_base_and_reports_both_sides_of_renames() -> None:
    calls: list[tuple[str, ...]] = []

    def git(command):  # type: ignore[no-untyped-def]
        calls.append(tuple(command))
        if command[1] == "merge-base":
            return _completed(stdout=f"{MERGE_BASE}\n".encode())
        return _completed(stdout=b"old.py\0new.py\0")

    changed = changed_range_for_event(
        "pull_request",
        {"pull_request": {"base": {"sha": BASE}, "head": {"sha": HEAD}}},
        git=git,
    )

    assert changed == ChangedRange(
        ("old.py", "new.py"), False, "classified 33333333..22222222"
    )
    assert calls[0] == ("git", "merge-base", BASE, HEAD)
    assert "--no-renames" in calls[1]
    assert "--diff-filter=ACDMR" in calls[1]


def test_push_uses_the_complete_before_after_range() -> None:
    calls: list[tuple[str, ...]] = []

    def git(command):  # type: ignore[no-untyped-def]
        calls.append(tuple(command))
        return _completed(stdout=b"src/prodockit/cli.py\0")

    changed = changed_range_for_event(
        "push", {"before": BASE, "after": HEAD}, git=git
    )

    assert changed.paths == ("src/prodockit/cli.py",)
    assert calls[0][-2:] == (BASE, HEAD)


def test_range_collection_fails_closed_on_every_uncertain_state() -> None:
    def failed(_command):  # type: ignore[no-untyped-def]
        return _completed(returncode=1)

    def empty(_command):  # type: ignore[no-untyped-def]
        return _completed()

    def malformed(_command):  # type: ignore[no-untyped-def]
        return _completed(stdout=b"not-nul-terminated")

    for changed in (
        changed_range_for_event("push", {"before": "0" * 40, "after": HEAD}),
        changed_range_for_event("push", {"before": BASE, "after": HEAD}, git=failed),
        changed_range_for_event("push", {"before": BASE, "after": HEAD}, git=empty),
        changed_range_for_event("push", {"before": BASE, "after": HEAD}, git=malformed),
        changed_range_for_event("unknown", {}),
    ):
        assert changed.full, changed
        assert changed.reason


def test_manual_schedule_and_full_ci_label_select_the_comprehensive_backstop() -> None:
    assert changed_range_for_event("workflow_dispatch", {}).full
    assert changed_range_for_event("schedule", {}).full
    assert changed_range_for_event(
        "pull_request", {"pull_request": {"labels": [{"name": "full-ci"}]}}
    ).full


def test_all_scope_emits_every_supported_python_and_acceptance_suite() -> None:
    assert output_lines(all_scope()) == (
        'python-matrix=["3.10","3.11","3.12","3.13","3.14"]',
        "adopt=true",
        "pdf=true",
        "bootstrap=true",
    )


def test_workflows_share_one_fail_closed_collector_and_stable_result_job() -> None:
    for name, result_name in (
        ("ci.yml", "CI result"),
        ("adopt-install.yml", "Adopt installed-wheel result"),
        ("pdf-built-site-wheel.yml", "PDF installed-wheel result"),
        ("bootstrap-install.yml", "Bootstrap installed-wheel result"),
    ):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "fetch-depth: 0" in workflow
        assert "python tools/ci_scope.py --github-event" in workflow
        assert "--all" not in workflow
        assert f"name: {result_name}" in workflow
        assert "merge_group:" in workflow
        assert "schedule:" in workflow


def test_ci_runs_static_render_and_coverage_work_once() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "fromJSON(needs.scope.outputs.python-matrix)" in workflow
    assert workflow.count("run: ruff check .") == 1
    assert workflow.count("run: mypy src") == 1
    assert workflow.count("run: pytest --cov=prodockit") == 1
    assert "if: matrix.python-version != '3.14'\n        run: pytest" in workflow


def test_every_artifact_workflow_uses_the_python_314_project_pin() -> None:
    """Only the compatibility matrix may choose more than one Python (#363)."""
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.14"

    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    steps = [
        (workflow.name, step)
        for workflow in workflows
        for step in _setup_python_steps(workflow.read_text(encoding="utf-8"))
    ]
    assert steps, "no actions/setup-python steps were inspected"

    unpinned = [
        name
        for name, step in steps
        if "python-version-file: .python-version" not in step
        and "python-version: ${{ matrix.python-version }}" not in step
    ]
    assert not unpinned, f"setup-python does not use the 3.14 project pin: {unpinned}"


def test_adopt_matrix_caches_node_packages_and_keeps_full_windows_architecture_coverage(
) -> None:
    workflow = (ROOT / ".github" / "workflows" / "adopt-install.yml").read_text(
        encoding="utf-8"
    )

    assert "cache: npm" in workflow
    assert "src/prodockit/_tools_template/mermaid/package-lock.json" in workflow
    assert "src/prodockit/_tools_template/mathjax/package-lock.json" in workflow
    assert workflow.count("scenario_args: --scenario toml-both") == 2
    assert "runner: windows-2025" in workflow
    assert "runner: windows-11-arm" in workflow
