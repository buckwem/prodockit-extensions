# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Safety and normalisation checks for the installed-wheel acceptance driver."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
adopt_acceptance = importlib.import_module("tools.adopt_acceptance")


def test_a_wheel_file_or_single_wheel_directory_is_accepted(tmp_path: Path) -> None:
    wheel = tmp_path / "prodockit-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    assert adopt_acceptance.resolve_wheel(wheel) == wheel.resolve()
    assert adopt_acceptance.resolve_wheel(tmp_path) == wheel.resolve()


def test_an_ambiguous_wheel_directory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "prodockit-1-py3-none-any.whl").write_bytes(b"one")
    (tmp_path / "prodockit-2-py3-none-any.whl").write_bytes(b"two")

    with pytest.raises(adopt_acceptance.AcceptanceError, match="more than one"):
        adopt_acceptance.resolve_wheel(tmp_path)


@pytest.mark.parametrize("machine", ["arm64", "aarch64"])
def test_arm64_architecture_names_are_accepted(monkeypatch, machine: str) -> None:
    monkeypatch.setattr(adopt_acceptance.platform, "machine", lambda: machine)

    assert adopt_acceptance.assert_arm64() == machine


def test_x64_is_rejected_when_arm64_is_required(monkeypatch) -> None:
    monkeypatch.setattr(adopt_acceptance.platform, "machine", lambda: "x86_64")

    with pytest.raises(adopt_acceptance.AcceptanceError, match="must be ARM64"):
        adopt_acceptance.assert_arm64()


def test_architecture_requirements_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        adopt_acceptance.parser().parse_args(
            ["--wheel", "candidate.whl", "--require-x64", "--require-arm64"]
        )


def test_all_acceptance_scenarios_are_selected_by_default() -> None:
    assert adopt_acceptance.select_scenarios(None) == adopt_acceptance.SCENARIOS
    assert adopt_acceptance.select_scenarios(["all"]) == adopt_acceptance.SCENARIOS


def test_named_acceptance_scenarios_keep_the_declared_order() -> None:
    selected = adopt_acceptance.select_scenarios(["toml-both", "toml-core"])

    assert [item[0] for item in selected] == ["toml-core", "toml-both"]


def test_all_cannot_be_combined_with_named_scenarios() -> None:
    with pytest.raises(adopt_acceptance.AcceptanceError, match="cannot be combined"):
        adopt_acceptance.select_scenarios(["all", "toml-core"])


def test_scenario_workers_must_be_positive() -> None:
    assert adopt_acceptance.positive_integer("2") == 2
    with pytest.raises(adopt_acceptance.argparse.ArgumentTypeError, match="at least 1"):
        adopt_acceptance.positive_integer("0")


def test_only_external_renderer_failures_are_classified_as_transient() -> None:
    assert adopt_acceptance.transient_renderer_failure(
        "npm completed but Mermaid CLI timed out after 30 seconds"
    )
    assert adopt_acceptance.transient_renderer_failure("npm ERR! code ECONNRESET")
    assert adopt_acceptance.transient_renderer_failure(
        "Mermaid failed: Content snap GPU wrapper missing; ensure slot is connected"
    )
    assert not adopt_acceptance.transient_renderer_failure(
        "configuration changed beyond the selected assets"
    )


@pytest.mark.parametrize(
    "failure",
    [
        (
            "Error: could not install mermaid: Command "
            "['npm', 'ci'] timed out after 600 seconds"
        ),
        (
            "Error: npm completed but Mermaid CLI is unusable: Command "
            "['mmdc', '-i', 'health.mmd'] timed out after 30.0 seconds"
        ),
    ],
)
def test_each_failure_seen_on_pr_718_is_retried_once(
    tmp_path: Path, monkeypatch, failure: str
) -> None:
    attempts = []
    prepared = []

    def completed(command, **kwargs):
        attempts.append(command)
        if len(attempts) == 1:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr=failure,
            )
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    monkeypatch.setattr(adopt_acceptance.subprocess, "run", completed)
    monkeypatch.setattr(
        adopt_acceptance,
        "prepare_renderer_retry",
        lambda project, detail: prepared.append((project, detail)),
    )

    result = adopt_acceptance.run(
        ["prodockit", "adopt", "--apply"],
        cwd=tmp_path,
        transient_attempts=2,
    )

    assert result.stdout == "passed"
    assert len(attempts) == 2
    assert prepared == [(tmp_path, failure)]


def test_a_deterministic_failure_is_not_retried(tmp_path: Path, monkeypatch) -> None:
    attempts = []

    def completed(command, **kwargs):
        attempts.append(command)
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="configuration assertion failed",
        )

    monkeypatch.setattr(adopt_acceptance.subprocess, "run", completed)

    with pytest.raises(adopt_acceptance.AcceptanceError, match="assertion failed"):
        adopt_acceptance.run(
            ["prodockit", "adopt", "--apply"],
            cwd=tmp_path,
            transient_attempts=2,
        )

    assert len(attempts) == 1


def test_absolute_venv_python_activates_its_executable_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = tmp_path / "venv"
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    observed: dict[str, str] = {}

    def completed(command, **kwargs):
        observed.update(kwargs["env"])
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    monkeypatch.setattr(adopt_acceptance.subprocess, "run", completed)

    adopt_acceptance.run([str(python), "-V"], cwd=tmp_path)

    assert observed["VIRTUAL_ENV"] == str(environment.resolve())
    assert observed["PATH"].split(os.pathsep)[0] == str(scripts.resolve())


def test_a_failed_run_still_writes_an_acceptance_report(
    tmp_path: Path, monkeypatch
) -> None:
    wheel = tmp_path / "prodockit-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    work = tmp_path / "work"
    report = tmp_path / "failure.json"

    def make_work(*, prefix: str) -> str:
        assert prefix == "prodockit-adopt-acceptance-"
        work.mkdir()
        return str(work)

    class Environment:
        def create(self, path: Path) -> None:
            path.mkdir()

    monkeypatch.setattr(adopt_acceptance.tempfile, "mkdtemp", make_work)
    monkeypatch.setattr(
        adopt_acceptance.venv,
        "EnvBuilder",
        lambda **kwargs: Environment(),
    )
    monkeypatch.setattr(adopt_acceptance, "venv_python", lambda path: Path(sys.executable))
    monkeypatch.setattr(adopt_acceptance, "install_candidate", lambda *args: None)
    monkeypatch.setattr(
        adopt_acceptance,
        "exercise_fixture",
        lambda *args: (_ for _ in ()).throw(
            adopt_acceptance.AcceptanceError("Mermaid mmdc timed out after two attempts")
        ),
    )

    with pytest.raises(adopt_acceptance.AcceptanceError, match="timed out"):
        adopt_acceptance.main(["--wheel", str(wheel), "--report", str(report)])

    recorded = json.loads(report.read_text(encoding="utf-8"))
    assert recorded["passed"] is False
    assert "timed out after two attempts" in recorded["error"]
    assert recorded["results"] == []


def test_a_real_project_is_copied_without_generated_or_git_state(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    (source / "docs").mkdir(parents=True)
    (source / "docs" / "index.md").write_text("# Kept\n", encoding="utf-8")
    for ignored in (".git", ".venv", ".cache", "site", "node_modules"):
        path = source / ignored
        path.mkdir()
        (path / "ignored").write_text("ignored", encoding="utf-8")

    adopt_acceptance.copy_project(source, output)

    assert (output / "docs" / "index.md").is_file()
    for ignored in (".git", ".venv", ".cache", "site", "node_modules"):
        assert not (output / ignored).exists()


def test_copy_refuses_to_replace_or_nest_inside_the_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    existing = tmp_path / "existing"
    existing.mkdir()

    with pytest.raises(adopt_acceptance.AcceptanceError, match="separate"):
        adopt_acceptance.copy_project(source, source / "copy")
    with pytest.raises(adopt_acceptance.AcceptanceError, match="refusing to replace"):
        adopt_acceptance.copy_project(source, existing)


def test_site_snapshot_ignores_only_assets_added_by_adoption(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    original = b"<html><head></head><body><p>Same</p></body></html>"
    adopted = (
        b'<html><head><link rel="stylesheet" href="./stylesheets/pdk.css">'
        b"</head><body><p>Same</p>"
        b'<script src="./javascripts/mathjax.js"></script></body></html>'
    )
    (before / "index.html").write_bytes(original)
    (after / "index.html").write_bytes(adopted)
    for relative in adopt_acceptance.ADOPTED_SITE_FILES:
        asset = after / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(f"generated {relative}\n", encoding="utf-8")

    assert adopt_acceptance.snapshot(before, site=True) == adopt_acceptance.snapshot(
        after, site=True
    )

    (after / "index.html").write_bytes(adopted.replace(b"Same", b"Changed"))
    assert adopt_acceptance.snapshot(before, site=True) != adopt_acceptance.snapshot(
        after, site=True
    )
