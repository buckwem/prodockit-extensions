# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from prodockit.cli import main
from prodockit.shared_files import (
    MANIFEST,
    SharedFileError,
    apply,
    drift,
    inspect,
    load_manifest,
    resource_bytes,
)

ROOT = Path(__file__).resolve().parent.parent


def _manifest(root: Path, *, source: str = "pdk.css", target: str = "docs/stylesheets/pdk.css") -> None:
    (root / MANIFEST).write_text(
        f'version = 1\n\n[[files]]\nsource = "{source}"\ntarget = "{target}"\n',
        encoding="utf-8",
    )


@pytest.mark.parametrize("name", ["pdk.css", "pdk-pdf.css"])
def test_canonical_resources_are_the_extensions_stylesheets(name: str) -> None:
    assert resource_bytes(name) == (ROOT / "docs/stylesheets" / name).read_bytes()


def test_shared_website_stylesheet_has_no_project_specific_logo_dependency() -> None:
    stylesheet = resource_bytes("pdk.css").decode("utf-8")

    assert "logo_white.png" not in stylesheet
    assert "logo_black.png" not in stylesheet


def test_manifest_manages_only_prodockit_owned_stylesheets() -> None:
    declared = load_manifest(ROOT)

    assert [(item.source, item.target) for item in declared] == [
        ("pdk.css", "docs/stylesheets/pdk.css"),
        ("pdk-pdf.css", "docs/stylesheets/pdk-pdf.css"),
    ]
    assert (ROOT / "docs/stylesheets/extra.css").is_file()
    assert (ROOT / "docs/stylesheets/print.css").is_file()


def test_absent_manifest_opts_out() -> None:
    assert load_manifest(ROOT / "not-a-project") == []
    assert inspect(ROOT / "not-a-project") == []


def test_an_incoming_manifest_repairs_an_older_project_without_one(tmp_path: Path) -> None:
    template = tmp_path / "template"
    project = tmp_path / "project"
    template.mkdir()
    project.mkdir()
    _manifest(template)

    states = inspect(project, template)

    assert [state.status for state in states] == ["missing"]
    assert apply(project, states) == ["docs/stylesheets/pdk.css"]


def test_inspect_distinguishes_current_different_and_missing(tmp_path: Path) -> None:
    _manifest(tmp_path)
    target = tmp_path / "docs/stylesheets/pdk.css"

    assert inspect(tmp_path)[0].status == "missing"
    target.parent.mkdir(parents=True)
    target.write_text("old copy\n", encoding="utf-8")
    assert inspect(tmp_path)[0].status == "different"
    target.write_bytes(resource_bytes("pdk.css"))
    state = inspect(tmp_path)[0]
    assert state.status == "current"
    assert state.actual_sha256 == state.expected_sha256


def test_apply_replaces_only_drifted_files(tmp_path: Path) -> None:
    _manifest(tmp_path)
    states = inspect(tmp_path)

    assert apply(tmp_path, states) == ["docs/stylesheets/pdk.css"]
    assert (tmp_path / "docs/stylesheets/pdk.css").read_bytes() == resource_bytes("pdk.css")
    assert apply(tmp_path, inspect(tmp_path)) == []


@pytest.mark.parametrize("target", ["../outside.css", "/tmp/outside.css", "C:/outside.css"])
def test_manifest_rejects_a_target_outside_the_project(tmp_path: Path, target: str) -> None:
    _manifest(tmp_path, target=target)

    with pytest.raises(SharedFileError, match="must stay inside"):
        load_manifest(tmp_path)


def test_manifest_rejects_unknown_resources(tmp_path: Path) -> None:
    _manifest(tmp_path, source="anything.txt")

    with pytest.raises(SharedFileError, match="unknown source"):
        load_manifest(tmp_path)


def test_manifest_rejects_a_duplicated_destination(tmp_path: Path) -> None:
    (tmp_path / MANIFEST).write_text(
        """version = 1

[[files]]
source = "pdk.css"
target = "docs/stylesheets/pdk.css"

[[files]]
source = "pdk.css"
target = "docs/stylesheets/pdk.css"
""",
        encoding="utf-8",
    )

    with pytest.raises(SharedFileError, match=r"declares .* more than once"):
        load_manifest(tmp_path)


def test_inspect_rejects_a_symlinked_target_outside_the_project(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.css"
    outside.write_text("do not replace\n", encoding="utf-8")
    target = tmp_path / "docs/stylesheets/pdk.css"
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    _manifest(tmp_path)

    with pytest.raises(SharedFileError, match="must stay inside"):
        inspect(tmp_path)
    assert outside.read_text(encoding="utf-8") == "do not replace\n"


def test_shared_files_default_is_a_non_writing_preview(tmp_path: Path) -> None:
    _manifest(tmp_path)

    result = CliRunner().invoke(main, ["shared-files", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "MISS" in result.output
    assert "No changes made" in result.output
    assert not (tmp_path / "docs/stylesheets/pdk.css").exists()


def test_shared_files_check_fails_with_a_clear_recovery_command(tmp_path: Path) -> None:
    _manifest(tmp_path)

    result = CliRunner().invoke(main, ["shared-files", "--root", str(tmp_path), "--check"])

    assert result.exit_code == 1
    assert "Shared-file drift detected" in result.output
    assert "prodockit shared-files --apply" in result.output


def test_shared_files_apply_then_check_is_clean(tmp_path: Path) -> None:
    _manifest(tmp_path)
    runner = CliRunner()

    applied = runner.invoke(main, ["shared-files", "--root", str(tmp_path), "--apply"])
    checked = runner.invoke(main, ["shared-files", "--root", str(tmp_path), "--check"])

    assert applied.exit_code == 0, applied.output
    assert "Updated:" in applied.output
    assert checked.exit_code == 0, checked.output
    assert "matches the installed prodockit release" in checked.output


def test_shared_files_verbose_reports_hashes(tmp_path: Path) -> None:
    _manifest(tmp_path)

    result = CliRunner().invoke(
        main, ["shared-files", "--root", str(tmp_path), "--check", "--verbose"]
    )

    assert result.exit_code == 1
    assert "expected sha256" in result.output
    assert "actual   sha256 missing" in result.output


def test_pins_check_also_guards_declared_shared_files(tmp_path: Path) -> None:
    _manifest(tmp_path)
    (tmp_path / "requirements.txt").write_text("zensical==0.0.57\n", encoding="utf-8")

    failed = CliRunner().invoke(
        main, ["pins", "--root", str(tmp_path), "--check", "--offline"]
    )
    apply(tmp_path, inspect(tmp_path))
    passed = CliRunner().invoke(
        main, ["pins", "--root", str(tmp_path), "--check", "--offline"]
    )

    assert failed.exit_code == 1
    assert "docs/stylesheets/pdk.css is missing" in failed.output
    assert "prodockit shared-files --apply" in failed.output
    assert passed.exit_code == 0, passed.output
    assert "Every managed package and shared file is current and consistent" in passed.output


def test_pins_without_a_manifest_keeps_its_existing_behaviour(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("zensical==0.0.57\n", encoding="utf-8")

    result = CliRunner().invoke(
        main, ["pins", "--root", str(tmp_path), "--check", "--offline"]
    )

    assert result.exit_code == 0, result.output
    assert "Shared files" not in result.output
    assert "Every managed package is current and consistent" in result.output


def test_drift_returns_only_files_needing_work(tmp_path: Path) -> None:
    _manifest(tmp_path)
    assert [state.status for state in drift(inspect(tmp_path))] == ["missing"]
