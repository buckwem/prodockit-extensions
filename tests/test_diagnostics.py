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
import prodockit.renderer_resilience as renderer_resilience
from prodockit import diagnostics
from prodockit import shared_files as shared_file_module
from prodockit.cli import main
from prodockit.diagnostics import DiagnosticReport, DiagnosticResult
from prodockit.project_config import ProjectConfig


def test_path_comparison_handles_posix_and_windows_spellings() -> None:
    assert diagnostics.same_path("/opt/pdk", "/opt/pdk/", platform="linux")
    assert diagnostics.same_path(
        r"C:\Users\Writer\.venv", r"c:/users/writer/.venv", platform="win32"
    )


def test_path_comparison_uses_filesystem_identity_for_existing_aliases(tmp_path: Path) -> None:
    environment = tmp_path / "environment"
    environment.mkdir()
    alias = tmp_path / "environment-alias"
    alias.symlink_to(environment, target_is_directory=True)

    assert diagnostics.same_path(str(environment), str(alias))


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


def test_command_location_uses_filesystem_identity_for_script_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = "/alias/bin"
    scripts = "/environment/bin"
    monkeypatch.setattr(
        diagnostics,
        "same_path",
        lambda left, right, *, platform=None: (left, right) == (alias, scripts),
    )

    assert diagnostics.command_in_environment(
        f"{alias}/pdk",
        "/environment",
        scripts,
        platform="linux",
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
    quarantine = prefix / ".prodockit-quarantine/diagnostics/20260903T120000.000000Z"
    manifest = json.loads((quarantine / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "applied"
    assert manifest["action"] == {
        "check_id": "installation.metadata",
        "choice_id": "quarantine-stale-metadata",
        "confirmation": "y",
        "id": "installation.metadata.quarantine-stale",
    }
    assert {entry["distribution"] for entry in manifest["entries"]} == {
        "prodockit",
        "zensical",
    }
    assert all(len(entry["sha256"]) == 64 for entry in manifest["entries"])
    assert all(not Path(entry["original"]).is_absolute() for entry in manifest["entries"])


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


def test_metadata_repair_revalidates_the_inspected_fingerprint_before_mutation(
    tmp_path: Path,
) -> None:
    prefix = tmp_path / "venv"
    site_packages = prefix / "lib/site-packages"
    _dist_info(
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
    entries = diagnostics._repair_metadata_entries((site_packages,))
    fingerprint = diagnostics._metadata_repair_fingerprint(entries)
    (stale / "changed-after-plan.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(diagnostics.MetadataRepairError, match="plan became stale"):
        diagnostics.repair_distribution_metadata(
            tmp_path,
            prefix=prefix,
            base_prefix=tmp_path / "system-python",
            site_packages=(site_packages,),
            current_versions={"prodockit": "0.56.0"},
            expected_fingerprint=fingerprint,
        )

    assert stale.is_dir()
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


def test_repair_transaction_refuses_external_and_symlinked_targets(tmp_path: Path) -> None:
    boundary = tmp_path / "project"
    boundary.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = boundary / "link.txt"
    link.symlink_to(outside)
    transaction = diagnostics.RepairTransaction(
        boundary,
        action_id="example.apply",
        check_id="dependencies.shared-files",
        choice_id="replace",
        timestamp="contained",
    )

    with pytest.raises(diagnostics.RepairTransactionError, match="symlinked"):
        transaction.quarantine_path(link, backup_name="link.txt")
    with pytest.raises(diagnostics.RepairTransactionError, match="outside"):
        transaction.quarantine_path(outside, backup_name="outside.txt")
    ordinary = boundary / "ordinary.txt"
    ordinary.write_text("ordinary\n", encoding="utf-8")
    with pytest.raises(diagnostics.RepairTransactionError, match="quarantine path outside"):
        transaction.quarantine_path(ordinary, backup_name="../../../escape.txt")

    assert outside.read_text(encoding="utf-8") == "outside\n"
    assert ordinary.read_text(encoding="utf-8") == "ordinary\n"


def test_repair_transaction_rolls_back_one_action_and_records_recovery(
    tmp_path: Path,
) -> None:
    boundary = tmp_path / "project"
    target = boundary / "managed.txt"
    target.parent.mkdir()
    target.write_text("original\n", encoding="utf-8")
    transaction = diagnostics.RepairTransaction(
        boundary,
        action_id="example.apply",
        check_id="dependencies.shared-files",
        choice_id="replace",
        timestamp="rollback",
    )

    transaction.begin()
    transaction.quarantine_path(target, backup_name="managed.txt")
    transaction.rollback("verification failed")

    assert target.read_text(encoding="utf-8") == "original\n"
    manifest = json.loads(transaction.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "rolled-back"
    assert manifest["entries"][0]["original"] == "managed.txt"
    assert manifest["entries"][0]["backup"] == "files/managed.txt"


def test_repair_transaction_stops_and_reports_both_paths_when_rollback_fails(
    tmp_path: Path,
) -> None:
    boundary = tmp_path / "project"
    target = boundary / "managed.txt"
    target.parent.mkdir()
    target.write_text("original\n", encoding="utf-8")
    transaction = diagnostics.RepairTransaction(
        boundary,
        action_id="example.apply",
        check_id="dependencies.shared-files",
        choice_id="replace",
        timestamp="rollback-failure",
    )
    transaction.begin()
    transaction.quarantine_path(target, backup_name="managed.txt")
    target.write_text("conflicting replacement\n", encoding="utf-8")

    with pytest.raises(diagnostics.RepairRollbackError) as raised:
        transaction.rollback("verification failed")

    message = str(raised.value)
    assert str(target) in message
    assert str(transaction.quarantine / "files") in message
    manifest = json.loads(transaction.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "rollback-failed"


def test_stage3_shared_file_adapter_reuses_installed_bytes_transactionally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / shared_file_module.MANIFEST).write_text(
        'version = 1\n\n[[files]]\nsource = "pdk.css"\ntarget = "docs/stylesheets/pdk.css"\n',
        encoding="utf-8",
    )
    target = tmp_path / "docs/stylesheets/pdk.css"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"author copy\n")
    monkeypatch.setattr(shared_file_module, "resource_bytes", lambda _source: b"installed\n")
    state = shared_file_module.inspect(tmp_path)[0]

    result = diagnostics.repair_shared_file(
        tmp_path,
        state.file.target,
        expected_status=state.status,
        expected_actual_sha256=state.actual_sha256,
        expected_sha256=state.expected_sha256,
        timestamp="shared-file",
    )

    assert result.status == "applied"
    assert target.read_bytes() == b"installed\n"
    manifest = json.loads((tmp_path / result.manifest).read_text(encoding="utf-8"))
    assert manifest["status"] == "applied"
    assert manifest["entries"][0]["original"] == "docs/stylesheets/pdk.css"
    assert manifest["entries"][0]["operation"] == "backup"


def test_stage3_shared_file_adapter_refuses_a_stale_plan_without_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / shared_file_module.MANIFEST).write_text(
        'version = 1\n\n[[files]]\nsource = "pdk.css"\ntarget = "docs/stylesheets/pdk.css"\n',
        encoding="utf-8",
    )
    target = tmp_path / "docs/stylesheets/pdk.css"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"before\n")
    monkeypatch.setattr(shared_file_module, "resource_bytes", lambda _source: b"installed\n")
    state = shared_file_module.inspect(tmp_path)[0]
    target.write_bytes(b"changed after inspection\n")

    with pytest.raises(diagnostics.RepairTransactionError, match="became stale"):
        diagnostics.repair_shared_file(
            tmp_path,
            state.file.target,
            expected_status=state.status,
            expected_actual_sha256=state.actual_sha256,
            expected_sha256=state.expected_sha256,
        )

    assert target.read_bytes() == b"changed after inspection\n"
    assert not (tmp_path / ".prodockit-quarantine").exists()


def test_stage3_shared_file_adapter_can_create_and_roll_back_a_missing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / shared_file_module.MANIFEST).write_text(
        'version = 1\n\n[[files]]\nsource = "pdk.css"\ntarget = "new/path/pdk.css"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(shared_file_module, "resource_bytes", lambda _source: b"installed\n")
    state = shared_file_module.inspect(tmp_path)[0]
    real_inspect = diagnostics.inspect_shared_files
    calls = 0

    def never_verifies(root: Path) -> list[shared_file_module.SharedFileState]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_inspect(root)
        return [state]

    monkeypatch.setattr(diagnostics, "inspect_shared_files", never_verifies)

    with pytest.raises(diagnostics.RepairTransactionError, match="rolled back"):
        diagnostics.repair_shared_file(
            tmp_path,
            state.file.target,
            expected_status="missing",
            expected_actual_sha256=None,
            expected_sha256=state.expected_sha256,
            timestamp="missing-rollback",
        )

    assert not (tmp_path / state.file.target).exists()
    assert not (tmp_path / "new").exists()
    manifest = json.loads(
        (tmp_path / ".prodockit-quarantine/diagnostics/missing-rollback/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "rolled-back"


def test_stage3_pin_adapter_uses_a_detected_version_and_preserves_crlf(
    tmp_path: Path,
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_bytes(b'dependencies = [\r\n  "zensical>=0.0.57", # keep this comment\r\n]\r\n')
    workflow = tmp_path / ".github/workflows/docs.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_bytes(b'jobs:\r\n  docs:\r\n    run: pip install "zensical==0.0.58"\r\n')
    fingerprint = diagnostics._pin_state_fingerprint(tmp_path, "zensical")

    result = diagnostics.repair_pin_declarations(
        tmp_path,
        "zensical",
        "0.0.58",
        expected_fingerprint=fingerprint,
        timestamp="pin",
    )

    assert result.status == "applied"
    assert b'"zensical>=0.0.58", # keep this comment\r\n' in pyproject.read_bytes()
    assert workflow.read_bytes().count(b"\r\n") == 3
    manifest = json.loads((tmp_path / result.manifest).read_text(encoding="utf-8"))
    assert manifest["entries"][0]["original"] == "pyproject.toml"


def test_stage3_pin_adapter_refuses_an_undetected_or_stale_version(tmp_path: Path) -> None:
    requirement = tmp_path / "requirements.txt"
    requirement.write_text("zensical==0.0.57\nzensical==0.0.58\n", encoding="utf-8")
    fingerprint = diagnostics._pin_state_fingerprint(tmp_path, "zensical")

    with pytest.raises(diagnostics.RepairTransactionError, match="not a bounded"):
        diagnostics.repair_pin_declarations(
            tmp_path,
            "zensical",
            "9.9.9",
            expected_fingerprint=fingerprint,
        )
    requirement.write_text("zensical==0.0.57\n", encoding="utf-8")
    with pytest.raises(diagnostics.RepairTransactionError, match="became stale"):
        diagnostics.repair_pin_declarations(
            tmp_path,
            "zensical",
            "0.0.57",
            expected_fingerprint=fingerprint,
        )
    assert not (tmp_path / ".prodockit-quarantine").exists()


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


def test_mermaid_diagnostic_warns_when_a_transient_probe_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _project(tmp_path, required=True)
    binary = tmp_path / "tools" / "mermaid" / "node_modules" / ".bin" / "mmdc"
    binary.parent.mkdir(parents=True)
    binary.write_text("installed", encoding="utf-8")
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, "/usr/bin/tool", "1.0"),
    )
    notices = []
    monkeypatch.setattr(
        "prodockit.diagnostics.probe_mermaid",
        lambda path, **_kwargs: SimpleNamespace(
            path=path,
            ok=True,
            version="11.12.0",
            error=None,
            attempts=2,
            transient_failures=("ensure slot is connected",),
        ),
    )

    check = next(
        item
        for item in diagnostics._renderer_checks(
            config, tmp_path, retry_reporter=notices.append
        )
        if item.id == "renderer.mermaid"
    )

    assert check.status == "warn"
    assert check.summary == "Mermaid CLI recovered after a transient failure"
    assert "health probe: recovered after 2 attempts" in check.details


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


def test_browser_diagnostic_rejects_a_configured_path_that_is_not_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUPPETEER_EXECUTABLE_PATH", "/broken/chromium")
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, None, None, "not found"),
    )
    monkeypatch.setattr("prodockit.diagnostics.shutil.which", lambda _name: None)
    monkeypatch.setattr(diagnostics, "_run", lambda *_args, **_kwargs: pytest.fail("ran browser"))

    check = next(
        item
        for item in diagnostics._renderer_checks(_project(tmp_path, required=True), tmp_path)
        if item.id == "renderer.browser"
    )

    assert check.status == "fail"
    assert check.summary == "Browser executable is unusable"
    assert check.data["error"] == "path does not name a file"


def test_browser_diagnostic_does_not_launch_a_configured_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser = tmp_path / "msedge.exe"
    browser.touch()
    monkeypatch.setenv("PUPPETEER_EXECUTABLE_PATH", str(browser))
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, None, None, "not found"),
    )
    monkeypatch.setattr("prodockit.diagnostics.shutil.which", lambda _name: None)
    monkeypatch.setattr(diagnostics, "_run", lambda *_args, **_kwargs: pytest.fail("ran browser"))

    check = next(
        item
        for item in diagnostics._renderer_checks(_project(tmp_path, required=True), tmp_path)
        if item.id == "renderer.browser"
    )

    assert check.status == "pass"
    assert check.summary == "Browser executable found"
    assert check.data == {
        "required": True,
        "path": "msedge.exe",
        "version": None,
        "error": None,
    }


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
                diagnostics.RepairChoice("one", "One", command_argv=("pdk", "pins", "--check")),
                diagnostics.RepairChoice("two", "Two", internal_operation="no-op"),
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
    assert candidate.disposition == "confirmable"
    assert [choice.id for choice in candidate.choices] == [
        "align-zensical-0.0.58",
        "leave-unchanged",
    ]
    assert candidate.choices[0].command_argv == (
        "pdk",
        "pins",
        "--set",
        "zensical=0.0.58",
    )
    assert candidate.choices[-1].default
    assert all(choice.id != "selected" for choice in candidate.choices)


def test_independent_project_repairs_never_use_template_sync() -> None:
    report = DiagnosticReport(
        "zensical.toml",
        ".",
        True,
        (
            DiagnosticResult(
                "project.configuration",
                "Project configuration and inputs",
                "fail",
                "Prodockit integration is incomplete",
            ),
            DiagnosticResult("renderer.node", "Rendering toolchain", "pass", "Node is available"),
            DiagnosticResult("renderer.npm", "Rendering toolchain", "pass", "npm is available"),
            DiagnosticResult(
                "renderer.mermaid",
                "Rendering toolchain",
                "fail",
                "Mermaid is required",
                data={"repair_refusal": None},
            ),
            DiagnosticResult(
                "renderer.mathjax",
                "Rendering toolchain",
                "fail",
                "MathJax is required",
                data={"repair_refusal": None},
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
    operations = [
        choice.internal_operation
        for candidate in dry_run.candidates
        for choice in candidate.choices
        if choice.internal_operation is not None
    ]

    assert "renderer.mermaid.install-locked" in operations
    assert "renderer.mathjax.install-locked" in operations
    assert not any(operation and "template-sync" in operation for operation in operations)
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
                    "drifted_files": [{"path": "docs/stylesheets/pdk.css", "status": "different"}],
                },
            ),
            DiagnosticResult("renderer.browser", "Rendering toolchain", "warn", "browser missing"),
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
        "--verbose",
    ]
    assert candidate["choices"][1]["internal_operation"] == ("dependencies.shared-files.apply")
    assert candidate["choices"][1]["warning_severity"] == "warning"
    assert "replaces existing managed file bytes" in candidate["choices"][1]["warning"]
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
    assert "--online --fix --fix-check renderer.mermaid" in result.output
    assert "MANUAL — online" in result.output
    assert "Apply this repair?" not in result.output


def test_diag_repair_output_uses_bootstrap_phases_stages_and_colours(
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

    result = CliRunner().invoke(main, ["diag", "--dry-run"], color=True)

    assert "Phase 1/2 — Inspect and plan" in result.output
    assert "Stage [1/1] renderer.mermaid" in result.output
    assert "Phase 2/2 — Summary" in result.output
    assert "\x1b[94m" in result.output  # bootstrap bright-blue phase boundary
    assert "\x1b[34m" in result.output  # bootstrap blue stage boundary
    assert "\x1b[93m" in result.output  # bootstrap yellow warning/action styling


def test_diag_rejects_incompatible_or_unknown_dry_run_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = DiagnosticReport("zensical.toml", ".", False, ())
    monkeypatch.setattr(diagnostics, "inspect", lambda *_args, **_kwargs: report)

    incompatible = CliRunner().invoke(main, ["diag", "--dry-run", "--fix"])
    unscoped = CliRunner().invoke(main, ["diag", "--fix-check", "installation.metadata"])
    unknown = CliRunner().invoke(main, ["diag", "--dry-run", "--fix-check", "future.unknown"])

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
    before = DiagnosticReport(
        config_file="zensical.toml",
        project_root=".",
        online=False,
        checks=(
            DiagnosticResult(
                "installation.metadata",
                "Environment and installation",
                "warn",
                "Duplicate distribution metadata found",
                data={
                    "fix_candidates": ["prodockit"],
                    "repair_paths": [".venv/lib/site-packages/prodockit-0.41.0.dist-info"],
                    "repair_fingerprint": "before-fingerprint",
                },
            ),
        ),
    )
    after = DiagnosticReport(
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
        return before if calls == 1 else after

    monkeypatch.setattr(diagnostics, "inspect", inspect)
    monkeypatch.setattr(
        diagnostics,
        "repair_distribution_metadata",
        lambda _root, **_kwargs: diagnostics.MetadataRepairResult(
            "repaired",
            (".venv/lib/site-packages/prodockit-0.41.0.dist-info",),
            ".venv/.prodockit-quarantine/diagnostics/run",
            ".venv/.prodockit-quarantine/diagnostics/run/manifest.json",
        ),
    )
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)

    result = CliRunner().invoke(main, ["diag", "--fix", "--json"], input="1\ny\n")

    assert result.exit_code == 0, result.output
    assert calls == 2
    payload = json.loads(result.stdout)
    assert payload["before"]["status"] == "warn"
    assert payload["after"]["status"] == "pass"
    assert payload["repair"]["status"] == "repaired"
    assert payload["repair"]["actions"][0]["status"] == "applied"
    assert payload["repair"]["actions"][0]["confirmation"] == "y"
    assert payload["repair"]["actions"][0]["changed"] == [
        ".venv/lib/site-packages/prodockit-0.41.0.dist-info"
    ]
    assert "Apply this repair? [y/N]:" in result.stderr
    assert "WARNING:" in result.stderr


@pytest.mark.parametrize("answer", ["", "n\n", "yes\n", "YEs\n", "x\n"])
def test_diag_fix_requires_an_exact_single_character_y_for_each_action(
    monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    report = DiagnosticReport(
        "zensical.toml",
        ".",
        False,
        (
            DiagnosticResult(
                "installation.metadata",
                "Environment and installation",
                "warn",
                "Duplicate distribution metadata found",
                data={
                    "fix_candidates": ["prodockit"],
                    "repair_paths": [".venv/lib/site-packages/prodockit-0.41.0.dist-info"],
                    "repair_fingerprint": "before-fingerprint",
                },
            ),
        ),
    )
    monkeypatch.setattr(diagnostics, "inspect", lambda *_args, **_kwargs: report)
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr(
        diagnostics,
        "repair_distribution_metadata",
        lambda _root, **_kwargs: pytest.fail("a declined repair mutated the environment"),
    )

    result = CliRunner().invoke(main, ["diag", "--fix", "--json"], input="1\n" + answer)

    payload = json.loads(result.stdout)
    assert payload["repair"]["status"] == "declined"
    assert payload["repair"]["actions"][0]["status"] == "declined"
    assert not Path(".prodockit-quarantine").exists()


def test_diag_fix_refuses_redirected_input_before_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        diagnostics,
        "inspect",
        lambda *_args, **_kwargs: pytest.fail("non-interactive fix inspected after refusal"),
    )

    result = CliRunner().invoke(main, ["diag", "--fix"])

    assert result.exit_code == 1
    assert "requires an interactive terminal" in result.output
    assert "--dry-run --json" in result.output


def test_stage3_choices_and_confirmations_are_separate_for_each_action(
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
                "one managed file differs",
                data={
                    "drifted": 1,
                    "drifted_files": [
                        {
                            "path": "docs/stylesheets/pdk.css",
                            "status": "different",
                            "actual_sha256": "old",
                            "expected_sha256": "new",
                        }
                    ],
                },
            ),
            DiagnosticResult(
                "dependencies.pins",
                "Dependency and managed-file consistency",
                "fail",
                "zensical declarations disagree",
                data={
                    "packages": [
                        {
                            "package": "zensical",
                            "versions": ["0.0.57", "0.0.58"],
                            "latest": None,
                            "fingerprint": "pins-before",
                            "sites": [
                                {
                                    "path": "pyproject.toml",
                                    "line": 1,
                                    "operator": ">=",
                                    "version": "0.0.57",
                                    "kind": "pip",
                                },
                                {
                                    "path": ".github/workflows/docs.yml",
                                    "line": 1,
                                    "operator": "==",
                                    "version": "0.0.58",
                                    "kind": "pip",
                                },
                            ],
                        }
                    ]
                },
            ),
        ),
    )
    monkeypatch.setattr(diagnostics, "inspect", lambda *_args, **_kwargs: report)
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr(
        diagnostics,
        "repair_shared_file",
        lambda *_args, **_kwargs: diagnostics.RepairApplyResult(
            "applied",
            ("docs/stylesheets/pdk.css",),
            ".prodockit-quarantine/diagnostics/shared",
            ".prodockit-quarantine/diagnostics/shared/manifest.json",
        ),
    )
    monkeypatch.setattr(
        diagnostics,
        "repair_pin_declarations",
        lambda *_args, **_kwargs: pytest.fail(
            "selecting a pin choice without confirming applied it"
        ),
    )

    result = CliRunner().invoke(
        main,
        ["diag", "--fix", "--json"],
        input="2\ny\n1\nn\n",
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    actions = [
        action for action in payload["repair"]["actions"] if action["status"] != "not-needed"
    ]
    assert [action["selected_choice"] for action in actions] == [
        "replace-installed-shared-file",
        "align-zensical-0.0.58",
    ]
    assert [action["status"] for action in actions] == ["applied", "declined"]
    assert result.stderr.count("Apply this repair? [y/N]:") == 2
    assert result.stderr.count("WARNING:") >= 2


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


def test_stage5_repairs_unique_setting_typo_without_losing_comments(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text(
        '[project]\nsite_name = "Example" # author comment\n\n'
        '[project.extra]\npdf_magin_left = "3cm" # retain me\n',
        encoding="utf-8",
    )
    _loaded, check = diagnostics._configuration_check(config)
    problem = check.data["repairable_problems"][0]

    result = diagnostics.repair_project_configuration(
        tmp_path,
        problem,
        expected_fingerprint=check.data["repair_fingerprint"],
        timestamp="stage5-rename",
    )

    source = config.read_text(encoding="utf-8")
    assert result.status == "applied"
    assert 'pdf_margin_left = "3cm" # retain me' in source
    assert 'site_name = "Example" # author comment' in source


def test_stage5_moves_obsolete_index_setting_losslessly(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text(
        '[project]\nsite_name = "Example"\n\n'
        "[project.extra]\npdf_include_index = true # retain me\n",
        encoding="utf-8",
    )
    _loaded, check = diagnostics._configuration_check(config)
    problem = check.data["repairable_problems"][0]

    diagnostics.repair_project_configuration(
        tmp_path,
        problem,
        expected_fingerprint=check.data["repair_fingerprint"],
        timestamp="stage5-obsolete",
    )

    source = config.read_text(encoding="utf-8")
    assert "pdf_include_index" not in source
    assert '[project.markdown_extensions."prodockit.index"]' in source
    assert "include = true # retain me" in source


def test_stage5_enables_only_extension_proved_by_author_syntax(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Example"\n', encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("See \\ref{target}.\n", encoding="utf-8")
    _loaded, check = diagnostics._configuration_check(config)
    problem = next(
        item
        for item in check.data["repairable_problems"]
        if item["operation"] == "enable-extension"
    )

    diagnostics.repair_project_configuration(
        tmp_path,
        problem,
        expected_fingerprint=check.data["repair_fingerprint"],
        timestamp="stage5-extension",
    )

    assert '[project.markdown_extensions."prodockit.refs"]' in config.read_text(encoding="utf-8")


def test_stage5_refuses_yaml_and_unknown_local_assets(tmp_path: Path) -> None:
    yaml_config = tmp_path / "zensical.yml"
    yaml_config.write_text("site_name: Example\n", encoding="utf-8")
    docs = tmp_path / "docs" / "stylesheets"
    docs.mkdir(parents=True)
    (docs / "author.css").write_text("/* mine */\n", encoding="utf-8")

    _loaded, check = diagnostics._configuration_check(yaml_config)

    assert check.data["repairable_problems"] == []


def test_stage4_requires_online_mode_and_rejects_custom_renderer_paths() -> None:
    base_checks = (
        DiagnosticResult("renderer.node", "Rendering toolchain", "pass", "Node available"),
        DiagnosticResult("renderer.npm", "Rendering toolchain", "pass", "npm available"),
        DiagnosticResult(
            "renderer.mermaid",
            "Rendering toolchain",
            "fail",
            "Mermaid missing",
            data={"repair_refusal": "project.extra.pdf_mmdc_bin selects a custom path"},
        ),
    )

    offline = diagnostics.build_repair_dry_run(
        DiagnosticReport("zensical.toml", ".", False, base_checks)
    )
    online = diagnostics.build_repair_dry_run(
        DiagnosticReport("zensical.toml", ".", True, base_checks)
    )

    assert (
        next(c for c in offline.candidates if c.check_id == "renderer.mermaid").status == "manual"
    )
    assert (
        next(c for c in online.candidates if c.check_id == "renderer.mermaid").status == "refused"
    )


def test_stage4_locked_mermaid_repair_uses_npm_ci_and_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Example"\n', encoding="utf-8")
    expected = diagnostics._renderer_plan_fingerprint(tmp_path, "mermaid")
    monkeypatch.setattr(
        "prodockit.diagnostics.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"node", "npm"} else None,
    )
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, f"/usr/bin/{name}", "1.0"),
    )
    commands: list[list[str]] = []

    def npm_ci(command: list[str], **kwargs):
        commands.append(command)
        binary = tmp_path / "tools/mermaid/node_modules/.bin/mmdc"
        binary.parent.mkdir(parents=True)
        binary.write_text("installed", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("prodockit.diagnostics.subprocess.run", npm_ci)
    monkeypatch.setattr(
        "prodockit.diagnostics.probe_mermaid",
        lambda path: SimpleNamespace(ok=True, error=None, version="11.0", path=path),
    )

    result = diagnostics.repair_locked_renderer(
        tmp_path,
        "mermaid",
        expected_fingerprint=expected,
        timestamp="stage4-mermaid",
    )

    assert result.status == "applied"
    assert commands[0][1] == "ci"
    assert (tmp_path / "tools/mermaid/package-lock.json").is_file()


def test_stage4_renderer_repair_retries_transient_npm_inside_one_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "zensical.toml").write_text(
        '[project]\nsite_name = "Example"\n', encoding="utf-8"
    )
    expected = diagnostics._renderer_plan_fingerprint(tmp_path, "mermaid")
    monkeypatch.setattr(
        "prodockit.diagnostics.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"node", "npm"} else None,
    )
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, f"/usr/bin/{name}", "1.0"),
    )
    attempts = []

    def npm_ci(command: list[str], **_kwargs):
        attempts.append(command)
        modules = tmp_path / "tools/mermaid/node_modules"
        if len(attempts) == 1:
            modules.mkdir(parents=True)
            (modules / "partial").write_text("partial", encoding="utf-8")
            return subprocess.CompletedProcess(command, 1, "", "npm ERR! code EAI_AGAIN")
        assert not modules.exists()
        binary = modules / ".bin/mmdc"
        binary.parent.mkdir(parents=True)
        binary.write_text("installed", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("prodockit.diagnostics.subprocess.run", npm_ci)
    monkeypatch.setattr(renderer_resilience.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        "prodockit.diagnostics.probe_mermaid",
        lambda path, **_kwargs: SimpleNamespace(
            ok=True, error=None, version="11.0", path=path
        ),
    )
    notices = []

    result = diagnostics.repair_locked_renderer(
        tmp_path,
        "mermaid",
        expected_fingerprint=expected,
        timestamp="stage4-mermaid-retry",
        retry_reporter=notices.append,
    )

    assert result.status == "applied"
    assert len(attempts) == 2
    assert len(notices) == 1
    manifest = json.loads(
        (
            tmp_path
            / ".prodockit-quarantine/diagnostics/stage4-mermaid-retry/manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["status"] == "applied"


def test_stage4_mathjax_repair_regenerates_browser_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "zensical.toml").write_text('[project]\nsite_name = "Example"\n', encoding="utf-8")
    expected = diagnostics._renderer_plan_fingerprint(tmp_path, "mathjax")
    monkeypatch.setattr(
        "prodockit.diagnostics.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"node", "npm"} else None,
    )
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, f"/usr/bin/{name}", "1.0"),
    )

    def npm_ci(command: list[str], **kwargs):
        package = tmp_path / "tools/mathjax/node_modules/mathjax-full"
        bundle = package / "es5/tex-svg-full.js"
        bundle.parent.mkdir(parents=True)
        bundle.write_text("locked browser bundle", encoding="utf-8")
        (package / "LICENSE").write_text("licence", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("prodockit.diagnostics.subprocess.run", npm_ci)
    monkeypatch.setattr(
        "prodockit.diagnostics.probe_mathjax",
        lambda node, path: SimpleNamespace(ok=True, error=None, path=path),
    )

    result = diagnostics.repair_locked_renderer(
        tmp_path,
        "mathjax",
        expected_fingerprint=expected,
        timestamp="stage4-mathjax",
    )

    assert result.status == "applied"
    assert (tmp_path / "docs/javascripts/mathjax.js").is_file()
    assert (tmp_path / "docs/javascripts/vendor/mathjax/tex-svg-full.js").read_text(
        encoding="utf-8"
    ) == "locked browser bundle"


def test_stage4_failed_install_restores_generated_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "zensical.toml").write_text('[project]\nsite_name = "Example"\n', encoding="utf-8")
    diagnostics.init_tools(tmp_path / "tools", components=("mermaid",))
    marker = tmp_path / "tools/mermaid/node_modules/author-marker"
    marker.parent.mkdir(parents=True)
    marker.write_text("restore me", encoding="utf-8")
    expected = diagnostics._renderer_plan_fingerprint(tmp_path, "mermaid")
    monkeypatch.setattr(
        "prodockit.diagnostics.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"node", "npm"} else None,
    )
    monkeypatch.setattr(
        diagnostics,
        "_command",
        lambda name: diagnostics.CommandInfo(name, f"/usr/bin/{name}", "1.0"),
    )
    monkeypatch.setattr(
        "prodockit.diagnostics.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, "", "registry unavailable"
        ),
    )

    with pytest.raises(diagnostics.RepairTransactionError, match="rolled back"):
        diagnostics.repair_locked_renderer(
            tmp_path,
            "mermaid",
            expected_fingerprint=expected,
            timestamp="stage4-rollback",
        )

    assert marker.read_text(encoding="utf-8") == "restore me"
    manifest = json.loads(
        (tmp_path / ".prodockit-quarantine/diagnostics/stage4-rollback/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "rolled-back"


def test_stage4_refuses_author_package_scripts(tmp_path: Path) -> None:
    config = ProjectConfig(
        path=tmp_path / "zensical.toml",
        project={},
        nav_pages=(),
        markdown_extensions={},
    )
    tools = tmp_path / "tools/mermaid"
    tools.mkdir(parents=True)
    (tools / "package.json").write_text(
        '{"scripts":{"postinstall":"do-something"},"dependencies":{}}',
        encoding="utf-8",
    )
    (tools / "package-lock.json").write_text(
        '{"packages":{"":{"dependencies":{}}}}', encoding="utf-8"
    )

    refusal = diagnostics._locked_renderer_refusal(tmp_path, config, "mermaid")

    assert refusal == "package.json contains author lifecycle scripts"


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


def test_pins_warn_when_declarations_are_outside_installed_supported_combination(
    tmp_path: Path,
) -> None:
    (tmp_path / "requirements.txt").write_text("zensical==0.0.58\n", encoding="utf-8")

    check = diagnostics._pin_checks(tmp_path, online=False)[0]

    assert check.id == "dependencies.pins"
    assert check.status == "warn"
    assert "outside the supported combination" in check.summary
    assert "supported with installed prodockit" in check.details[0]
    assert "run `pdk pins` and accept the tested default" in check.details[0]
    assert check.data["supported_mismatches"] == ["zensical"]


def test_supported_combination_warning_is_manual_not_a_diag_fix(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("weasyprint==68.0\n", encoding="utf-8")
    check = diagnostics._pin_checks(tmp_path, online=False)[0]

    dry_run = diagnostics.build_repair_dry_run(
        DiagnosticReport("zensical.toml", str(tmp_path), False, (check,))
    )

    candidate = next(
        item
        for item in dry_run.candidates
        if item.id == "dependencies.pins.restore-supported-combination"
    )
    assert candidate.status == "manual"
    assert candidate.choices == ()
    assert "Run `pdk pins`" in candidate.remediation


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
