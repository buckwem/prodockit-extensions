# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "ci_scope", Path(__file__).parents[1] / "tools" / "ci_scope.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
Scope = _MODULE.Scope
all_scope = _MODULE.all_scope
classify = _MODULE.classify
output_lines = _MODULE.output_lines

ROOT = Path(__file__).parents[1]


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

    assert scope == Scope(python_compat=False, adopt=False, pdf=False)
    assert scope.python_matrix == ("3.14",)


def test_python_change_tests_oldest_and_newest_supported_versions() -> None:
    scope = classify(["src/prodockit/glossary.py"])

    assert scope.python_compat
    assert scope.python_matrix == ("3.10", "3.14")
    assert not scope.adopt
    assert not scope.pdf


def test_adopt_change_selects_only_its_installed_wheel_matrix() -> None:
    assert classify(["src/prodockit/adopt.py"]) == Scope(True, True, False)
    assert classify(["tools/adopt_acceptance.py"]) == Scope(True, True, False)


def test_pdf_change_selects_only_its_installed_wheel_matrix() -> None:
    assert classify(["src/prodockit/pdf/site.py"]) == Scope(True, False, True)
    assert classify(["tools/pdf_from_site_acceptance.py"]) == Scope(True, False, True)


def test_rendered_extension_change_selects_pdf_acceptance() -> None:
    for path in (
        "src/prodockit/headings.py",
        "src/prodockit/refs.py",
        "tests/test_zensical_integration.py",
    ):
        scope = classify([path])
        assert scope.pdf, path
        assert not scope.adopt, path


def test_shared_packaging_and_command_files_select_both_matrices() -> None:
    for path in (
        "pyproject.toml",
        "src/prodockit/cli.py",
        "src/prodockit/project_config.py",
        "docs/stylesheets/pdk.css",
        "docs/stylesheets/pdk-pdf.css",
    ):
        scope = classify([path])
        assert scope.adopt, path
        assert scope.pdf, path


def test_workflow_and_test_changes_cannot_skip_their_own_acceptance() -> None:
    assert classify([".github/workflows/adopt-install.yml"]).adopt
    assert classify([".github/workflows/pdf-built-site-wheel.yml"]).pdf
    assert classify(["tests/test_adopt_acceptance.py"]).adopt
    assert classify(["tests/test_pdf_site.py"]).pdf


def test_main_scope_emits_every_supported_python_and_acceptance_suite() -> None:
    assert output_lines(all_scope(), main=True) == (
        'python-matrix=["3.10","3.11","3.12","3.13","3.14"]',
        "adopt=true",
        "pdf=true",
    )


def test_pr_workflows_cancel_superseded_runs_and_include_deleted_paths() -> None:
    for name in ("ci.yml", "adopt-install.yml", "pdf-built-site-wheel.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
        assert "--diff-filter=ACDMR" in workflow


def test_installed_wheel_workflows_are_gated_but_main_forces_all_scopes() -> None:
    for name, output in (
        ("adopt-install.yml", "adopt"),
        ("pdf-built-site-wheel.yml", "pdf"),
    ):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert f"relevant: ${{{{ steps.scope.outputs.{output} }}}}" in workflow
        assert "if: needs.scope.outputs.relevant == 'true'" in workflow
        assert "python tools/ci_scope.py --all" in workflow


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
