# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Cross-platform acceptance fixtures for the complete diagnostic repair flow."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from prodockit import diagnostics
from prodockit.cli import main
from prodockit.diagnostics import DiagnosticReport

diagnostics_acceptance = importlib.import_module("tools.diagnostics_repair_acceptance")
diagnostics_acceptance_driver = importlib.import_module(
    "tools._diagnostics_repair_acceptance_driver"
)
ROOT = Path(__file__).parents[1]


def _report(config: Path) -> DiagnosticReport:
    _loaded, configuration = diagnostics._configuration_check(config)
    return DiagnosticReport(config.name, str(config.parent), False, (configuration,))


@pytest.mark.parametrize(
    ("scenario", "body", "page", "expected_status", "expected_operations"),
    (
        (
            "fully-repairable",
            '[project]\nsite_name = "Résumé"\n\n[project.extra]\npdf_magin_left = "3cm"\n',
            "# Home\n",
            "available",
            {"project.configuration.rename"},
        ),
        (
            "mixed",
            '[project]\nsite_name = "Mixed"\n\n'
            '[project.markdown_extensions."prodockit.index"]\n'
            'include = "not-a-boolean"\n',
            "See \\ref{target}.\n",
            "available",
            {"project.configuration.enable-extension"},
        ),
        (
            "ambiguous",
            '[project]\nsite_name = "Ambiguous"\n\n[project.extra]\npdf_unrelated = true\n',
            "# Home\n",
            "manual",
            set(),
        ),
    ),
)
def test_cross_platform_dry_run_fixtures_are_deterministic_and_read_only(
    tmp_path: Path,
    scenario: str,
    body: str,
    page: str,
    expected_status: str,
    expected_operations: set[str],
) -> None:
    project = tmp_path / f"diagnostic fixture {scenario}"
    docs = project / "docs"
    docs.mkdir(parents=True)
    config = project / "zensical.toml"
    config.write_text(body, encoding="utf-8")
    (docs / "index.md").write_text(page, encoding="utf-8")
    before = {
        path.relative_to(project): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }

    first = diagnostics.build_repair_dry_run(_report(config), check_ids=("project.configuration",))
    second = diagnostics.build_repair_dry_run(_report(config), check_ids=("project.configuration",))

    assert first.as_dict() == second.as_dict()
    assert {candidate.status for candidate in first.candidates} == {expected_status}
    operations = {
        choice.internal_operation
        for candidate in first.candidates
        for choice in candidate.choices
        if choice.internal_operation not in {None, "no-op"}
    }
    assert operations == expected_operations
    after = {
        path.relative_to(project): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not (project / ".prodockit-quarantine").exists()


def test_full_cli_configuration_repair_preserves_utf8_crlf_and_space_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project with spaces"
    project.mkdir()
    config = project / "zensical.toml"
    config.write_bytes(
        b'[project]\r\nsite_name = "R\xc3\xa9sum\xc3\xa9" # keep\r\n\r\n'
        b'[project.extra]\r\npdf_magin_left = "3cm" # keep\r\n'
    )

    monkeypatch.setattr(
        diagnostics,
        "inspect",
        lambda path, **_kwargs: _report(Path(path)),
    )
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)

    result = CliRunner().invoke(
        main,
        ["diag", "--config-file", str(config), "--fix", "--json"],
        input="1\ny\n",
    )

    payload = json.loads(result.stdout)
    assert payload["repair"]["actions"][0]["status"] == "applied"
    source = config.read_bytes()
    assert b'pdf_margin_left = "3cm" # keep\r\n' in source
    assert b'site_name = "R\xc3\xa9sum\xc3\xa9" # keep\r\n' in source
    assert b"\n" not in source.replace(b"\r\n", b"")
    assert result.stderr.count("Apply this repair? [y/N]:") == 1


def test_yaml_dry_run_reports_manual_and_never_rewrites(tmp_path: Path) -> None:
    config = tmp_path / "zensical.yml"
    source = b"site_name: Example\nextra:\n  pdf_magin_left: 3cm # keep\n"
    config.write_bytes(source)

    plan = diagnostics.build_repair_dry_run(_report(config), check_ids=("project.configuration",))

    assert plan.candidates[0].status == "manual"
    assert not plan.candidates[0].choices
    assert config.read_bytes() == source


def test_diagnostic_acceptance_resolves_one_wheel_and_checks_architecture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "prodockit-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    assert diagnostics_acceptance.resolve_wheel(wheel) == wheel.resolve()
    assert diagnostics_acceptance.resolve_wheel(tmp_path) == wheel.resolve()
    monkeypatch.setattr(diagnostics_acceptance.platform, "machine", lambda: "ARM64")
    assert diagnostics_acceptance.require_architecture(x64=False, arm64=True) == "arm64"
    with pytest.raises(diagnostics_acceptance.AcceptanceError, match="expected x64"):
        diagnostics_acceptance.require_architecture(x64=True, arm64=False)


def test_driver_timeout_is_configurable_and_positive() -> None:
    arguments = diagnostics_acceptance.parser().parse_args(
        [
            "--wheel",
            "dist",
            "--report",
            "report.json",
            "--driver-timeout-seconds",
            "1800",
        ]
    )

    assert arguments.driver_timeout_seconds == 1800
    with pytest.raises(SystemExit):
        diagnostics_acceptance.parser().parse_args(
            [
                "--wheel",
                "dist",
                "--report",
                "report.json",
                "--driver-timeout-seconds",
                "0",
            ]
        )


def test_driver_uses_file_backed_output_instead_of_windows_sensitive_pipes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout_path = tmp_path / "driver.stdout.log"
    stderr_path = tmp_path / "driver.stderr.log"

    def completed(command, **kwargs):
        assert "capture_output" not in kwargs
        kwargs["stdout"].write("driver passed\n")
        kwargs["stderr"].write("driver detail\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(diagnostics_acceptance.subprocess, "run", completed)

    result = diagnostics_acceptance.run_logged(
        ["python", "driver.py"],
        cwd=tmp_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )

    assert result.returncode == 0
    assert stdout_path.read_text(encoding="utf-8") == "driver passed\n"
    assert stderr_path.read_text(encoding="utf-8") == "driver detail\n"


def test_driver_timeout_reports_preserved_file_backed_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout_path = tmp_path / "driver.stdout.log"
    stderr_path = tmp_path / "driver.stderr.log"

    def timeout(command, **kwargs):
        kwargs["stdout"].write("last completed phase\n")
        kwargs["stdout"].flush()
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(diagnostics_acceptance.subprocess, "run", timeout)

    with pytest.raises(
        diagnostics_acceptance.AcceptanceError,
        match=r"(?s)timed out after 12 seconds.*last completed phase",
    ):
        diagnostics_acceptance.run_logged(
            ["python", "driver.py"],
            cwd=tmp_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout=12,
        )


def test_all_failures_fixture_contains_every_repair_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site_packages = tmp_path / "wheel-environment" / "site-packages"
    monkeypatch.setattr(diagnostics_acceptance_driver, "_site_packages", lambda: site_packages)
    project = tmp_path / "project with spaces"

    stale = diagnostics_acceptance_driver.write_fixture(project)

    assert stale == site_packages / "prodockit-0.0.1.dist-info"
    assert stale.is_dir()
    assert "\\ref{target}" in (project / "docs/index.md").read_text(encoding="utf-8")
    assert (project / "docs/stylesheets/pdk.css").is_file()
    assert not (project / "docs/stylesheets/pdk-pdf.css").exists()
    for component in ("mermaid", "mathjax"):
        assert (project / "tools" / component / "package.json").is_file()
        assert (project / "tools" / component / "package-lock.json").is_file()
        assert not (project / "tools" / component / "node_modules").exists()


def test_acceptance_resolves_project_absolute_and_home_report_paths(tmp_path: Path) -> None:
    home = Path.home()
    project = tmp_path / "project"

    assert diagnostics_acceptance_driver._reported_path("file", project) == project / "file"
    assert (
        diagnostics_acceptance_driver._reported_path(str(home / "file"), project) == home / "file"
    )
    assert diagnostics_acceptance_driver._reported_path("~/file", project) == home / "file"


def test_acceptance_cli_repair_is_scoped_to_the_seeded_failures(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    command = diagnostics_acceptance_driver._repair_command(config)

    selected = {
        command[index + 1] for index, argument in enumerate(command) if argument == "--fix-check"
    }
    assert selected == diagnostics_acceptance_driver.REPAIRABLE_CHECKS
    assert command.count("--fix-check") == len(diagnostics_acceptance_driver.REPAIRABLE_CHECKS)


def test_diagnostic_repair_workflow_has_six_repair_and_twelve_toolchain_environments() -> None:
    workflow = (ROOT / ".github/workflows/diag-repair.yml").read_text(encoding="utf-8")
    runners = {
        "ubuntu-24.04",
        "ubuntu-24.04-arm",
        "windows-2025",
        "windows-11-arm",
        "macos-15-intel",
        "macos-15",
    }

    assert sum(f"runner: {runner}" in workflow for runner in runners) == 6
    assert workflow.count("architecture_check:") == 12
    assert "scenario: [upgrade, downgrade]" in workflow
    assert "python -m build --wheel" in workflow
    assert "tools/diagnostics_repair_acceptance.py" in workflow
    assert "timeout-minutes: 35" in workflow
    assert "--driver-timeout-seconds 1800" in workflow
    assert 'pip install -e ".[dev]"' not in workflow


def test_acceptance_requires_all_six_repairable_checks_and_seven_confirmations() -> None:
    assert {
        "installation.metadata",
        "project.configuration",
        "dependencies.pins",
        "dependencies.shared-files",
        "renderer.mermaid",
        "renderer.mathjax",
    } == diagnostics_acceptance_driver.REPAIRABLE_CHECKS
    assert sum(diagnostics_acceptance_driver.EXPECTED_ACTIONS.values()) == 7
    assert diagnostics_acceptance_driver.EXPECTED_ACTIONS["dependencies.shared-files"] == 2
