# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Command-boundary paths for ``pdk boot``.

Stage behavior belongs in ``test_bootstrap.py``.  This module keeps the much
smaller option, routing, error and exit-code matrix visible in one place, using
the hermetic harness from ``bootstrap_cli_harness.py``.
"""

from pathlib import Path

import pytest

from prodockit import __version__
from prodockit.bootstrap import (
    BootstrapConfig,
    BootstrapConfigError,
    CheckResult,
    Stage,
    StageReport,
    Status,
    UnsupportedHostError,
    load,
    pdkboot_config_path,
    save,
)
from prodockit.cli import main as legacy_main
from prodockit.pdkboot import main
from prodockit.template_sync import read_config

from .harness import PdkbootCliHarness


def _complete_config() -> BootstrapConfig:
    return BootstrapConfig(
        full_name="Ada Lovelace",
        email="al01234@surrey.ac.uk",
        username="al01234",
        host="gitlab.surrey.ac.uk",
        namespace="comm058-2026",
        project_name="report-al01234",
        project_dir="~/GitLab/report-al01234",
    )


def _prepare_mode_test(
    bootstrap_cli: PdkbootCliHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    save(bootstrap_cli.tmp_path / "b.toml", _complete_config())
    called: list[str] = []
    monkeypatch.setattr("prodockit.cli.check_all", lambda context: called.append("check") or [])
    monkeypatch.setattr("prodockit.cli.plan_all", lambda context: called.append("plan") or [])
    monkeypatch.setattr(
        "prodockit.cli._apply_outstanding",
        lambda context, reports, path: called.append("apply"),
    )
    return called


def test_pdkboot_is_separate_from_the_legacy_bootstrap_command() -> None:
    assert main is not legacy_main.commands["bootstrap"]
    assert legacy_main.commands["boot"] is legacy_main.commands["bootstrap"]


def test_distribution_registers_the_standalone_command() -> None:
    project = Path(__file__).resolve().parents[2]
    metadata = read_config((project / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["scripts"]["pdkboot"] == "prodockit.pdkboot:main"
    assert metadata["project"]["scripts"]["prodockit"] == "prodockit.cli:main"


def test_pdkboot_exposes_the_complete_option_set(bootstrap_cli: PdkbootCliHarness) -> None:
    result = bootstrap_cli.invoke("--help")

    assert result.exit_code == 0
    for option in (
        "--version",
        "--check",
        "--dry-run",
        "--apply",
        "--configure",
        "--config",
    ):
        assert option in result.output
    assert ".pdkboot.toml is the default" in result.output
    assert ".pdk-bootstrap.toml" not in result.output
    assert "Phase 1 installs nothing" not in result.output


def test_pdkboot_reports_the_installable_package_version(
    bootstrap_cli: PdkbootCliHarness,
) -> None:
    result = bootstrap_cli.invoke("--version")

    assert result.exit_code == 0
    assert result.output.strip() == f"pdkboot, version {__version__}"


def test_pdkboot_default_config_never_falls_back_to_legacy_state(tmp_path: Path) -> None:
    (tmp_path / ".pdk-bootstrap.toml").write_text("legacy", encoding="utf-8")
    legacy_user = tmp_path / ".config" / "prodockit" / "bootstrap.toml"
    legacy_user.parent.mkdir(parents=True)
    legacy_user.write_text("legacy user", encoding="utf-8")

    assert pdkboot_config_path(cwd=tmp_path) == tmp_path / ".pdkboot.toml"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((), ["check"]),
        (("--check",), ["check"]),
        (("--dry-run",), ["plan"]),
        (("--apply",), ["plan", "apply"]),
    ],
)
def test_each_execution_mode_uses_only_its_own_path(
    bootstrap_cli: PdkbootCliHarness,
    monkeypatch: pytest.MonkeyPatch,
    args: tuple[str, ...],
    expected: list[str],
) -> None:
    called = _prepare_mode_test(bootstrap_cli, monkeypatch)

    result = bootstrap_cli.invoke(*args)

    assert result.exit_code == 0, result.output
    assert called == expected


@pytest.mark.parametrize(
    "args",
    [
        ("--check", "--dry-run"),
        ("--check", "--apply"),
        ("--check", "--configure"),
        ("--dry-run", "--apply"),
        ("--dry-run", "--configure"),
        ("--apply", "--configure"),
        ("--check", "--dry-run", "--apply", "--configure"),
    ],
)
def test_conflicting_modes_are_rejected_before_any_bootstrap_work(
    bootstrap_cli: PdkbootCliHarness,
    monkeypatch: pytest.MonkeyPatch,
    args: tuple[str, ...],
) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        "prodockit.cli.load_bootstrap_config",
        lambda path: called.append("load") or _complete_config(),
    )

    result = bootstrap_cli.invoke(*args)

    assert result.exit_code == 2
    assert "Choose only one operating mode" in result.output
    assert called == []


def test_a_malformed_config_is_a_clean_cli_error(
    bootstrap_cli: PdkbootCliHarness,
) -> None:
    path = bootstrap_cli.tmp_path / "broken.toml"
    path.write_text("this is not key-value syntax\n", encoding="utf-8")

    result = bootstrap_cli.invoke("--check", config_path=path)

    assert result.exit_code == 1
    assert f"Error: {path}:1:" in result.output
    assert 'expected `key = "value"`' in result.output
    assert result.exception is not None


def test_an_unreadable_config_is_a_clean_cli_error(
    bootstrap_cli: PdkbootCliHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = bootstrap_cli.tmp_path / "unreadable.toml"
    error = BootstrapConfigError(f"could not read {path}: permission denied")
    monkeypatch.setattr(
        "prodockit.cli.load_bootstrap_config", lambda ignored: (_ for _ in ()).throw(error)
    )

    result = bootstrap_cli.invoke("--check", config_path=path)

    assert result.exit_code == 1
    assert str(error) in result.output


def test_an_unsupported_host_is_a_clean_cli_error(
    bootstrap_cli: PdkbootCliHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save(bootstrap_cli.tmp_path / "b.toml", _complete_config())
    error = UnsupportedHostError("no install recipe for platform 'plan9'")
    monkeypatch.setattr(
        "prodockit.cli.build_bootstrap_context",
        lambda config: (_ for _ in ()).throw(error),
    )

    result = bootstrap_cli.invoke("--check", patch_context=False)

    assert result.exit_code == 1
    assert f"Error: {error}" in result.output


def test_configure_stops_before_any_stage_path(
    bootstrap_cli: PdkbootCliHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = _prepare_mode_test(bootstrap_cli, monkeypatch)
    monkeypatch.setattr("prodockit.cli._ask_for_configuration", lambda config: _complete_config())

    result = bootstrap_cli.invoke("--configure")

    assert result.exit_code == 0, result.output
    assert called == []
    assert load(bootstrap_cli.tmp_path / "b.toml").is_complete


def test_configure_keeps_a_project_local_config_out_of_git(
    bootstrap_cli: PdkbootCliHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (bootstrap_cli.tmp_path / ".git").mkdir()
    monkeypatch.setattr("prodockit.cli._ask_for_configuration", lambda config: _complete_config())

    result = bootstrap_cli.invoke("--configure")

    assert result.exit_code == 0, result.output
    ignored = (bootstrap_cli.tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "b.toml" in ignored.splitlines()
    assert "Added b.toml to .gitignore" in result.output


def test_check_mode_renders_every_stage_status_and_optional_detail(
    bootstrap_cli: PdkbootCliHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save(bootstrap_cli.tmp_path / "b.toml", _complete_config())
    reports = []
    for status in Status:
        stage = Stage(
            id=status.value,
            summary=f"{status.value} stage",
            check=lambda context, status=status: CheckResult(status),
            plan=lambda context: None,  # type: ignore[arg-type,return-value]
        )
        reports.append(StageReport(stage, CheckResult(status, f"{status.value} detail"), None))
    monkeypatch.setattr("prodockit.cli.check_all", lambda context: reports)

    result = bootstrap_cli.invoke("--check")

    assert result.exit_code == 1
    for status in Status:
        assert f"{status.value} stage - {status.value} detail" in result.output


def test_unknown_option_fails_before_loading_configuration(
    bootstrap_cli: PdkbootCliHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[Path] = []
    monkeypatch.setattr(
        "prodockit.cli.load_bootstrap_config",
        lambda path: loaded.append(path) or _complete_config(),
    )

    result = bootstrap_cli.invoke("--not-an-option")

    assert result.exit_code == 2
    assert "No such option" in result.output
    assert "--not-an-option" in result.output
    assert loaded == []
