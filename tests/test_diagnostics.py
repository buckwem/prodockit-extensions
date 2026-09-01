# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import subprocess
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
    assert payload["schema_version"] == 1
    assert payload["status"] == "fail"
    assert payload["summary"] == {"fail": 1, "pass": 0, "warn": 0}


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
        "repository.git",
        "repository.template-metadata",
        "repository.template-update",
        "repository.inspection",
    }

    assert not {check_id for check_id in check_ids if f"`{check_id}`" not in guide}
