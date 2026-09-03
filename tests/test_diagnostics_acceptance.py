# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Cross-platform acceptance fixtures for the complete diagnostic repair flow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from prodockit import diagnostics
from prodockit.cli import main
from prodockit.diagnostics import DiagnosticReport


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
