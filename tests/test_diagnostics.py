# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import NoReturn

import pytest
from click.testing import CliRunner

import prodockit
from prodockit import diagnostics
from prodockit.cli import main
from prodockit.diagnostics import DiagnosticReport, DiagnosticResult
from prodockit.project_config import ProjectConfig


def test_path_comparison_handles_posix_and_windows_spellings() -> None:
    assert diagnostics.same_path("/opt/pdk", "/opt/pdk/", platform="linux")
    assert diagnostics.same_path(
        r"C:\Users\Writer\.venv", r"c:/users/writer/.venv", platform="win32"
    )


def test_command_location_handles_windows_and_rejects_stale_path() -> None:
    assert diagnostics.command_in_environment(
        r"C:\project\.venv\Scripts\pdk.exe",
        r"C:\project\.venv",
        r"C:\project\.venv\Scripts",
        platform="win32",
    )
    assert not diagnostics.command_in_environment(
        r"C:\old\.venv\Scripts\pdk.exe",
        r"C:\project\.venv",
        r"C:\project\.venv\Scripts",
        platform="win32",
    )


def test_command_location_accepts_a_pipx_style_symlink(tmp_path: Path) -> None:
    prefix = tmp_path / "pipx" / "venvs" / "prodockit"
    command = prefix / "bin" / "pdk"
    command.parent.mkdir(parents=True)
    command.touch()
    shim = tmp_path / "bin" / "pdk"
    shim.parent.mkdir()
    shim.symlink_to(command)

    assert diagnostics.command_in_environment(str(shim), str(prefix), str(prefix / "bin"))


def test_support_evidence_hides_home_paths_and_remote_credentials(tmp_path: Path) -> None:
    evidence = f"{Path.home()}/Library https://writer:secret@example.test/project"

    assert diagnostics._sanitise_text(evidence, tmp_path) == (
        "~/Library https://example.test/project"
    )


def test_environment_reports_only_a_real_virtual_environment_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = tmp_path / "active"
    monkeypatch.setattr("prodockit.diagnostics.sys.prefix", str(active))
    monkeypatch.setattr("prodockit.diagnostics.sys.base_prefix", "/usr")
    monkeypatch.setattr("prodockit.diagnostics.sys.executable", str(active / "bin" / "python"))
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "stale"))

    checks = diagnostics._environment_checks(tmp_path)

    assert next(check for check in checks if check.id == "environment.virtual-env").status == "fail"


def test_installation_detects_stale_path_and_dependency_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = prodockit.__version__
    monkeypatch.setattr(diagnostics, "_distribution_version", lambda _name: version)
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, str(tmp_path / "old" / "bin" / name), version),
    )
    monkeypatch.setattr("prodockit.diagnostics.sys.prefix", str(tmp_path / "active"))
    monkeypatch.setattr(
        "prodockit.diagnostics.sysconfig.get_path",
        lambda _name: str(tmp_path / "active" / "bin"),
    )
    monkeypatch.setattr(
        diagnostics,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 1, "broken-package requires missing-package\n", ""
        ),
    )
    monkeypatch.setattr("prodockit.diagnostics.importlib.metadata.distributions", lambda: [])

    checks = diagnostics._installation_checks(tmp_path)

    assert next(check for check in checks if check.id == "installation.commands").status == "fail"
    dependencies = next(check for check in checks if check.id == "installation.dependencies")
    assert dependencies.status == "fail"
    assert "broken-package" in dependencies.details[0]


def _dist_info(
    site_packages: Path,
    directory: str,
    *,
    name: str | None,
    version: str | None,
) -> Path:
    path = site_packages / directory
    path.mkdir(parents=True)
    fields = []
    if name is not None:
        fields.append(f"Name: {name}")
    if version is not None:
        fields.append(f"Version: {version}")
    if fields:
        (path / "METADATA").write_text("\n".join(fields) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "library_path",
    ("lib/python3.14/site-packages", "Lib/site-packages"),
)
def test_metadata_repair_quarantines_only_provably_stale_supported_distributions(
    tmp_path: Path,
    library_path: str,
) -> None:
    prefix = tmp_path / "environment"
    site_packages = prefix / library_path
    current_prodockit = _dist_info(
        site_packages,
        "prodockit-0.56.0.dist-info",
        name="Prodockit",
        version="0.56.0",
    )
    stale_prodockit = _dist_info(
        site_packages,
        "prodockit-0.41.0.dist-info",
        name="prodockit",
        version="0.41.0",
    )
    current_zensical = _dist_info(
        site_packages,
        "zensical-0.0.58.dist-info",
        name="Zensical",
        version="0.0.58",
    )
    stale_zensical = _dist_info(
        site_packages,
        "~ensical-0.0.55.dist-info",
        name=None,
        version=None,
    )
    unrelated = _dist_info(
        site_packages,
        "example-1.0.dist-info",
        name="example",
        version="1.0",
    )

    result = diagnostics.repair_distribution_metadata(
        tmp_path,
        prefix=prefix,
        base_prefix=tmp_path / "system-python",
        site_packages=(site_packages,),
        current_versions={"prodockit": "0.56.0", "zensical": "0.0.58"},
        timestamp="20260903T120000.000000Z",
    )

    assert result.status == "repaired"
    assert len(result.moved) == 2
    assert current_prodockit.is_dir()
    assert current_zensical.is_dir()
    assert unrelated.is_dir(), "--fix must leave every other distribution untouched"
    assert not stale_prodockit.exists()
    assert not stale_zensical.exists()
    quarantine = prefix / ".prodockit-quarantine/distribution-metadata/20260903T120000.000000Z"
    manifest = json.loads((quarantine / "manifest.json").read_text(encoding="utf-8"))
    assert {entry["distribution"] for entry in manifest["entries"]} == {
        "prodockit",
        "zensical",
    }


def test_metadata_repair_refuses_ambiguous_duplicates_without_moving_them(
    tmp_path: Path,
) -> None:
    prefix = tmp_path / "venv"
    site_packages = prefix / "lib/site-packages"
    first = _dist_info(
        site_packages,
        "prodockit-0.56.0.dist-info",
        name="prodockit",
        version="0.56.0",
    )
    second = _dist_info(
        site_packages,
        "prodockit-copy-0.56.0.dist-info",
        name="prodockit",
        version="0.56.0",
    )

    with pytest.raises(diagnostics.MetadataRepairError, match="cannot prove which metadata"):
        diagnostics.repair_distribution_metadata(
            tmp_path,
            prefix=prefix,
            base_prefix=tmp_path / "system-python",
            site_packages=(site_packages,),
            current_versions={"prodockit": "0.56.0"},
        )

    assert first.is_dir()
    assert second.is_dir()
    assert not (prefix / ".prodockit-quarantine").exists()


def test_metadata_repair_refuses_system_python_and_paths_outside_the_environment(
    tmp_path: Path,
) -> None:
    prefix = tmp_path / "python"
    with pytest.raises(diagnostics.MetadataRepairError, match="active virtual environment"):
        diagnostics.repair_distribution_metadata(
            tmp_path,
            prefix=prefix,
            base_prefix=prefix,
            site_packages=(prefix / "lib/site-packages",),
        )

    outside = tmp_path / "elsewhere/site-packages"
    outside.mkdir(parents=True)
    with pytest.raises(diagnostics.MetadataRepairError, match="outside the active environment"):
        diagnostics.repair_distribution_metadata(
            tmp_path,
            prefix=prefix,
            base_prefix=tmp_path / "system-python",
            site_packages=(outside,),
        )


def test_metadata_repair_rolls_back_when_rediscovery_is_not_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix = tmp_path / "venv"
    site_packages = prefix / "lib/site-packages"
    current = _dist_info(
        site_packages,
        "prodockit-0.56.0.dist-info",
        name="prodockit",
        version="0.56.0",
    )
    stale = _dist_info(
        site_packages,
        "prodockit-0.41.0.dist-info",
        name="prodockit",
        version="0.41.0",
    )
    discovered = diagnostics._repair_metadata_entries((site_packages,))
    monkeypatch.setattr(diagnostics, "_repair_metadata_entries", lambda _roots: discovered)

    with pytest.raises(diagnostics.MetadataRepairError, match="verification still found"):
        diagnostics.repair_distribution_metadata(
            tmp_path,
            prefix=prefix,
            base_prefix=tmp_path / "system-python",
            site_packages=(site_packages,),
            current_versions={"prodockit": "0.56.0"},
            timestamp="failed-verification",
        )

    assert current.is_dir()
    assert stale.is_dir(), "a failed verification must restore quarantined metadata"


def _project(tmp_path: Path, *, required: bool) -> ProjectConfig:
    extensions = (
        {
            "pymdownx.superfences": {"custom_fences": [{"name": "mermaid"}]},
            "pymdownx.arithmatex": {},
        }
        if required
        else {}
    )
    if required:
        docs = tmp_path / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "index.md").write_text(
            "```mermaid\ngraph LR\n  A --> B\n```\n\nThe area is $a^2$.\n",
            encoding="utf-8",
        )
    return ProjectConfig(
        path=tmp_path / "zensical.toml",
        project={"extra": {"pdf_output": "site/document.pdf"} if required else {}},
        nav_pages=(),
        markdown_extensions=extensions,
    )


def test_missing_renderers_warn_when_unused_and_fail_when_content_uses_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, None, None, "not found"),
    )
    monkeypatch.setattr("prodockit.diagnostics.shutil.which", lambda _name: None)

    def unavailable(_name: str) -> NoReturn:
        raise ImportError("not found")

    monkeypatch.setattr("prodockit.diagnostics.importlib.import_module", unavailable)

    optional = diagnostics._renderer_checks(_project(tmp_path, required=False), tmp_path)
    required = diagnostics._renderer_checks(_project(tmp_path, required=True), tmp_path)

    assert not [check for check in optional if check.status == "fail"]
    optional_by_id = {check.id: check for check in optional}
    for check_id in (
        "renderer.node",
        "renderer.npm",
        "renderer.mermaid",
        "renderer.mathjax",
    ):
        assert optional_by_id[check_id].status == "warn"
        assert optional_by_id[check_id].data["required"] is False
    assert {check.id for check in required if check.status == "fail"} >= {
        "renderer.pandoc",
        "renderer.weasyprint",
        "renderer.node",
        "renderer.npm",
        "renderer.mermaid",
        "renderer.mathjax",
    }


def test_mermaid_diagnostic_rejects_an_unusable_local_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _project(tmp_path, required=True)
    binary = tmp_path / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"
    binary.parent.mkdir(parents=True)
    binary.write_text("incomplete", encoding="utf-8")
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, "/usr/bin/tool", "1.0"),
    )
    monkeypatch.setattr(
        "prodockit.diagnostics.probe_mermaid",
        lambda path: SimpleNamespace(
            path=path,
            ok=False,
            version=None,
            error="ERR_MODULE_NOT_FOUND",
        ),
    )

    check = next(
        item
        for item in diagnostics._renderer_checks(config, tmp_path)
        if item.id == "renderer.mermaid"
    )

    assert check.status == "fail"
    assert check.summary == "Mermaid CLI is unusable but required by this project"
    assert "health probe: ERR_MODULE_NOT_FOUND" in check.details
    assert check.data["error"] == "ERR_MODULE_NOT_FOUND"


def test_mathjax_diagnostic_rejects_inputs_that_cannot_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _project(tmp_path, required=True)
    script = tmp_path / "tools" / "mathjax" / "tex2svg.js"
    script.parent.mkdir(parents=True)
    script.touch()
    (script.parent / "node_modules" / "mathjax-full").mkdir(parents=True)
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, "/usr/bin/tool", "1.0"),
    )
    monkeypatch.setattr(
        "prodockit.diagnostics.shutil.which",
        lambda name: "/usr/bin/node" if name == "node" else None,
    )
    monkeypatch.setattr(
        "prodockit.diagnostics.probe_mathjax",
        lambda node, path: SimpleNamespace(path=path, ok=False, error="Cannot find module"),
    )

    check = next(
        item
        for item in diagnostics._renderer_checks(config, tmp_path)
        if item.id == "renderer.mathjax"
    )

    assert check.status == "fail"
    assert "health probe: Cannot find module" in check.details
    assert check.data["error"] == "Cannot find module"


def test_browser_diagnostic_executes_the_configured_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUPPETEER_EXECUTABLE_PATH", "/broken/chromium")
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, None, None, "not found"),
    )
    monkeypatch.setattr("prodockit.diagnostics.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        diagnostics,
        "_run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, "", "loader error"
        ),
    )

    check = next(
        item
        for item in diagnostics._renderer_checks(_project(tmp_path, required=True), tmp_path)
        if item.id == "renderer.browser"
    )

    assert check.status == "fail"
    assert check.summary == "Browser executable is unusable"
    assert check.data["error"] == "loader error"


def test_mermaid_security_audit_is_explicitly_skipped_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lockfile = tmp_path / "tools" / "mermaid" / "package-lock.json"
    lockfile.parent.mkdir(parents=True)
    lockfile.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        diagnostics,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("offline diagnostics ran npm audit"),
    )

    check = diagnostics._node_security_checks(tmp_path, online=False)[0]

    assert check.status == "pass"
    assert check.summary == "Mermaid security audit skipped in offline mode"
    assert check.data == {"checked": False, "reason": "offline", "level": "moderate"}


def test_online_mermaid_security_audit_reports_advisories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_root = tmp_path / "tools" / "mermaid"
    tool_root.mkdir(parents=True)
    (tool_root / "package-lock.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("prodockit.diagnostics.shutil.which", lambda name: f"/bin/{name}")

    def audit(
        command: list[str], *, cwd: Path | None = None, timeout: float = 10.0
    ) -> subprocess.CompletedProcess[str]:
        assert command == [
            "/bin/npm",
            "audit",
            "--omit=dev",
            "--audit-level=moderate",
            "--json",
        ]
        assert cwd == tool_root
        assert timeout == 60
        payload = {
            "metadata": {
                "vulnerabilities": {
                    "low": 1,
                    "moderate": 2,
                    "high": 1,
                    "critical": 0,
                }
            }
        }
        return subprocess.CompletedProcess(command, 1, json.dumps(payload), "")

    monkeypatch.setattr(diagnostics, "_run", audit)

    check = diagnostics._node_security_checks(tmp_path, online=True)[0]

    assert check.status == "warn"
    assert check.summary == "Mermaid dependencies have 3 moderate-or-higher advisories"
    assert check.details == (
        "low: 1",
        "moderate: 2",
        "high: 1",
        "run `npm audit --omit=dev` in tools/mermaid for remediation detail",
    )


def test_diag_json_is_stable_and_failures_set_the_exit_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = DiagnosticReport(
        config_file="zensical.toml",
        project_root=".",
        online=False,
        checks=(
            DiagnosticResult(
                "project.configuration", "Project configuration and inputs", "fail", "broken"
            ),
        ),
    )
    monkeypatch.setattr(diagnostics, "inspect", lambda *_args, **_kwargs: report)

    result = CliRunner().invoke(main, ["diag", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == 2
    assert payload["status"] == "fail"
    assert payload["summary"] == {"fail": 1, "pass": 0, "warn": 0}
    assert payload["checks"][0]["repair"]["disposition"] == "ambiguous"


def test_every_diagnostic_has_one_registered_repair_disposition() -> None:
    assert set(diagnostics.REPAIR_REGISTRY) == diagnostics.DIAGNOSTIC_IDS
    with pytest.raises(ValueError, match="no registered repair disposition"):
        DiagnosticResult("future.unclassified", "Future", "warn", "not registered")


def test_repair_choice_requires_one_operation_and_one_default() -> None:
    with pytest.raises(ValueError, match="exactly one command or internal operation"):
        diagnostics.RepairChoice("broken", "Broken")
    with pytest.raises(ValueError, match="exactly one default"):
        diagnostics.RepairCandidate(
            "example",
            "dependencies.pins",
            "ambiguous",
            "available",
            "Example",
            "Example",
            "Example",
            (
                diagnostics.RepairChoice(
                    "one", "One", command_argv=("pdk", "pins", "--check")
                ),
                diagnostics.RepairChoice(
                    "two", "Two", internal_operation="no-op"
                ),
            ),
        )


def test_dry_run_lists_each_pin_choice_without_selecting_one() -> None:
    report = DiagnosticReport(
        "zensical.toml",
        ".",
        False,
        (
            DiagnosticResult(
                "dependencies.pins",
                "Dependency and managed-file consistency",
                "fail",
                "zensical declarations disagree",
                data={
                    "inconsistent": ["zensical"],
                    "updates": [],
                    "packages": [
                        {
                            "package": "zensical",
                            "versions": ["0.0.57", "0.0.58"],
                            "latest": None,
                            "sites": [
                                {
                                    "path": "pyproject.toml",
                                    "line": 10,
                                    "operator": ">=",
                                    "version": "0.0.57",
                                    "kind": "pip",
                                },
                                {
                                    "path": ".github/workflows/docs.yml",
                                    "line": 20,
                                    "operator": "==",
                                    "version": "0.0.58",
                                    "kind": "pip",
                                },
                            ],
                        }
                    ],
                },
            ),
        ),
    )

    dry_run = diagnostics.build_repair_dry_run(report)

    candidate = dry_run.candidates[0]
    assert candidate.status == "available"
    assert candidate.disposition == "ambiguous"
    assert [choice.id for choice in candidate.choices] == [
        "align-zensical-0.0.57",
        "align-zensical-0.0.58",
        "leave-unchanged",
    ]
    assert candidate.choices[0].command_argv == (
        "pdk",
        "pins",
        "--set",
        "zensical=0.0.57",
    )
    assert candidate.choices[-1].default
    assert all(choice.id != "selected" for choice in candidate.choices)


def test_independent_project_repairs_prefer_adoption_not_template_sync() -> None:
    report = DiagnosticReport(
        "zensical.toml",
        ".",
        False,
        (
            DiagnosticResult(
                "project.configuration",
                "Project configuration and inputs",
                "fail",
                "Prodockit integration is incomplete",
            ),
            DiagnosticResult(
                "renderer.mermaid",
                "Rendering toolchain",
                "fail",
                "Mermaid is required",
            ),
            DiagnosticResult(
                "renderer.mathjax",
                "Rendering toolchain",
                "fail",
                "MathJax is required",
            ),
            DiagnosticResult(
                "repository.template-metadata",
                "Repository and template maintenance",
                "fail",
                "Template metadata is invalid",
            ),
        ),
    )

    dry_run = diagnostics.build_repair_dry_run(report)
    commands = [
        choice.command_argv
        for candidate in dry_run.candidates
        for choice in candidate.choices
        if choice.command_argv is not None
    ]

    assert ("prodockit", "adopt", "--apply") in commands
    assert ("prodockit", "adopt", "--apply", "--mermaid") in commands
    assert ("prodockit", "adopt", "--apply", "--maths") in commands
    assert not any("template-sync" in command for command in commands)
    template = next(
        candidate
        for candidate in dry_run.candidates
        if candidate.check_id == "repository.template-metadata"
    )
    assert template.status == "refused"
    assert template.disposition == "prohibited"
    assert not template.choices


def test_weasyprint_import_banner_never_corrupts_diagnostic_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def noisy_import(name: str) -> NoReturn:
        assert name == "weasyprint"
        print("third-party stdout banner")
        print("third-party stderr banner", file=sys.stderr)
        raise OSError("native library unavailable")

    monkeypatch.setattr(diagnostics.importlib, "import_module", noisy_import)
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, None, None, "not found"),
    )
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)

    checks = diagnostics._renderer_checks(None, tmp_path)

    assert next(check for check in checks if check.id == "renderer.weasyprint").status == "warn"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_diag_dry_run_is_structured_read_only_and_filterable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = DiagnosticReport(
        "zensical.toml",
        ".",
        False,
        (
            DiagnosticResult(
                "dependencies.shared-files",
                "Dependency and managed-file consistency",
                "fail",
                "one managed file has drifted",
                data={
                    "declared": 1,
                    "drifted": 1,
                    "drifted_files": [
                        {"path": "docs/stylesheets/pdk.css", "status": "different"}
                    ],
                },
            ),
            DiagnosticResult(
                "renderer.browser", "Rendering toolchain", "warn", "browser missing"
            ),
        ),
    )
    monkeypatch.setattr(diagnostics, "inspect", lambda *_args, **_kwargs: report)
    monkeypatch.setattr(
        diagnostics,
        "repair_distribution_metadata",
        lambda _root: pytest.fail("dry-run invoked a mutating repair"),
    )

    result = CliRunner().invoke(
        main,
        ["diag", "--dry-run", "--fix-check", "dependencies.shared-files", "--json"],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == 2
    assert payload["dry_run"]["mutated"] is False
    assert payload["dry_run"]["selected_checks"] == ["dependencies.shared-files"]
    assert len(payload["dry_run"]["candidates"]) == 1
    candidate = payload["dry_run"]["candidates"][0]
    assert candidate["status"] == "available"
    assert candidate["choices"][0]["command_argv"] == [
        "pdk",
        "shared-files",
        "--apply",
    ]
    assert candidate["choices"][0]["warning_severity"] == "warning"
    assert "replaces existing managed file bytes" in candidate["choices"][0]["warning"]
    assert "Apply this repair?" not in result.output


def test_diag_dry_run_text_says_commands_could_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = DiagnosticReport(
        "zensical.toml",
        ".",
        False,
        (
            DiagnosticResult(
                "renderer.mermaid",
                "Rendering toolchain",
                "fail",
                "Mermaid is required",
            ),
        ),
    )
    monkeypatch.setattr(diagnostics, "inspect", lambda *_args, **_kwargs: report)

    result = CliRunner().invoke(main, ["diag", "--dry-run"])

    assert result.exit_code == 1
    assert "nothing will be changed" in result.output
    assert "Could run: prodockit adopt --apply --mermaid" in result.output
    assert "Option leave-unchanged (default): Leave unchanged" in result.output
    assert "WARNING:" in result.output
    assert "prodockit-template" in result.output
    assert "Apply this repair?" not in result.output


def test_diag_rejects_incompatible_or_unknown_dry_run_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = DiagnosticReport("zensical.toml", ".", False, ())
    monkeypatch.setattr(diagnostics, "inspect", lambda *_args, **_kwargs: report)

    incompatible = CliRunner().invoke(main, ["diag", "--dry-run", "--fix"])
    unscoped = CliRunner().invoke(
        main, ["diag", "--fix-check", "installation.metadata"]
    )
    unknown = CliRunner().invoke(
        main, ["diag", "--dry-run", "--fix-check", "future.unknown"]
    )

    assert incompatible.exit_code == 2
    assert "mutually exclusive" in incompatible.output
    assert unscoped.exit_code == 2
    assert "requires --dry-run or --fix" in unscoped.output
    assert unknown.exit_code == 2
    assert "unknown diagnostic check ID" in unknown.output


def test_diag_warnings_do_not_set_a_failure_exit_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = DiagnosticReport(
        config_file="zensical.toml",
        project_root=".",
        online=False,
        checks=(
            DiagnosticResult(
                "renderer.browser", "Rendering toolchain", "warn", "optional browser missing"
            ),
        ),
    )
    monkeypatch.setattr(diagnostics, "inspect", lambda *_args, **_kwargs: report)

    result = CliRunner().invoke(main, ["diag"])

    assert result.exit_code == 0
    assert "Result: WARN" in result.output


def test_diag_fix_reports_the_scoped_repair_and_reruns_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = DiagnosticReport(
        config_file="zensical.toml",
        project_root=".",
        online=False,
        checks=(
            DiagnosticResult(
                "installation.metadata",
                "Environment and installation",
                "pass",
                "Distribution metadata is readable and unique",
            ),
        ),
    )
    calls = 0

    def inspect(*_args: object, **_kwargs: object) -> DiagnosticReport:
        nonlocal calls
        calls += 1
        return report

    monkeypatch.setattr(diagnostics, "inspect", inspect)
    monkeypatch.setattr(
        diagnostics,
        "repair_distribution_metadata",
        lambda _root: diagnostics.MetadataRepairResult(
            "repaired",
            (".venv/lib/site-packages/prodockit-0.41.0.dist-info",),
            ".venv/.prodockit-quarantine/distribution-metadata/run",
        ),
    )

    result = CliRunner().invoke(main, ["diag", "--fix", "--json"])

    assert result.exit_code == 0, result.output
    assert calls == 1
    payload = json.loads(result.output)
    assert payload["repair"]["status"] == "repaired"
    assert payload["repair"]["moved"] == [
        ".venv/lib/site-packages/prodockit-0.41.0.dist-info"
    ]
    assert payload["checks"][0]["status"] == "pass"


def test_diag_without_fix_never_invokes_the_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = DiagnosticReport("zensical.toml", ".", False, ())
    monkeypatch.setattr(diagnostics, "inspect", lambda *_args, **_kwargs: report)
    monkeypatch.setattr(
        diagnostics,
        "repair_distribution_metadata",
        lambda _root: pytest.fail("read-only diagnostics invoked the repair"),
    )

    result = CliRunner().invoke(main, ["diag"])

    assert result.exit_code == 0, result.output


def test_diag_does_not_change_project_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "zensical.toml"
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("# Example\n", encoding="utf-8")
    config.write_text(
        '[project]\nsite_name = "Example"\ndocs_dir = "docs"\nnav = [{Home = "index.md"}]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(diagnostics, "_environment_checks", lambda _root: [])
    monkeypatch.setattr(diagnostics, "_installation_checks", lambda _root: [])
    monkeypatch.setattr(diagnostics, "_pin_checks", lambda _root, _online: [])
    monkeypatch.setattr(diagnostics, "_renderer_checks", lambda _config, _root: [])
    monkeypatch.setattr(diagnostics, "_node_security_checks", lambda _root, _online: [])
    monkeypatch.setattr(diagnostics, "_repository_checks", lambda _root, _online: [])
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    diagnostics.inspect(config)

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_pdk_diag_reports_local_assets_omitted_from_zensical_toml(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Example"\n', encoding="utf-8")
    stylesheet = tmp_path / "docs/stylesheets/unused.css"
    script = tmp_path / "docs/javascripts/unused.js"
    stylesheet.parent.mkdir(parents=True)
    script.parent.mkdir(parents=True)
    stylesheet.write_text("", encoding="utf-8")
    script.write_text("", encoding="utf-8")

    _loaded, check = diagnostics._configuration_check(config)

    assert check.status == "fail"
    assert any("docs/stylesheets/unused.css" in detail for detail in check.details)
    assert any("docs/javascripts/unused.js" in detail for detail in check.details)


def test_one_unreadable_area_does_not_prevent_the_remaining_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Example"\n', encoding="utf-8")
    reached_repository = False
    monkeypatch.setattr(diagnostics, "_environment_checks", lambda _root: [])
    monkeypatch.setattr(diagnostics, "_installation_checks", lambda _root: [])
    monkeypatch.setattr(
        diagnostics,
        "_pin_checks",
        lambda _root, _online: (_ for _ in ()).throw(OSError("cannot read pins")),
    )
    monkeypatch.setattr(diagnostics, "_renderer_checks", lambda _config, _root: [])
    monkeypatch.setattr(diagnostics, "_node_security_checks", lambda _root, _online: [])

    def repository(_root: Path, _online: bool) -> list[DiagnosticResult]:
        nonlocal reached_repository
        reached_repository = True
        return []

    monkeypatch.setattr(diagnostics, "_repository_checks", repository)

    report = diagnostics.inspect(config)

    assert reached_repository
    failure = next(check for check in report.checks if check.id == "dependencies.inspection")
    assert failure.status == "fail"
    assert failure.details == ("cannot read pins",)


def test_author_guide_documents_every_stable_check_id() -> None:
    guide = (
        Path(__file__).resolve().parent.parent / "docs" / "devcons" / "diagnostics.md"
    ).read_text(encoding="utf-8")
    check_ids = {
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
        "renderer.inspection",
        "renderer.mermaid-security",
        "renderer.security-inspection",
        "repository.git",
        "repository.template-metadata",
        "repository.template-update",
        "repository.inspection",
    }

    assert not {check_id for check_id in check_ids if f"`{check_id}`" not in guide}
