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


@pytest.mark.parametrize("name", ["public", "build/web"])
def test_configured_site_directory_and_snapshot_exclusion(tmp_path, monkeypatch, name):
    output = tmp_path / name
    output.mkdir(parents=True)
    (output / "index.html").write_text("generated")
    (tmp_path / "zensical.toml").write_text("source")
    monkeypatch.setattr(
        adopt_acceptance,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout=str(output)),
    )
    found = adopt_acceptance.site_directory(Path("python"), tmp_path, tmp_path / "zensical.toml")
    assert found == output
    assert list(adopt_acceptance.snapshot(tmp_path, exclude=found)) == ["zensical.toml"]


@pytest.mark.parametrize("outside", [False, True])
def test_site_directory_rejects_unsafe_build_targets(tmp_path, monkeypatch, outside):
    output = tmp_path.parent if outside else tmp_path
    monkeypatch.setattr(
        adopt_acceptance,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout=str(output)),
    )
    with pytest.raises(adopt_acceptance.AcceptanceError, match="inside the disposable project"):
        adopt_acceptance.site_directory(Path("python"), tmp_path, tmp_path / "zensical.toml")


def test_windows_command_inherits_persisted_pdf_setting(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    registry = SimpleNamespace(
        HKEY_CURRENT_USER=1,
        OpenKey=lambda *args: nullcontext(1),
        QueryValueEx=lambda *args: (r"C:\msys64\clangarm64\bin", 1),
        ExpandEnvironmentStrings=lambda value: value,
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(adopt_acceptance.sys, "platform", "win32")
    calls = []

    def completed(command, **kwargs):
        calls.append(kwargs["env"])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(adopt_acceptance.subprocess, "run", completed)
    adopt_acceptance.run(["python", "-V"], cwd=tmp_path)
    assert calls[0]["WEASYPRINT_DLL_DIRECTORIES"] == r"C:\msys64\clangarm64\bin"


def test_macos_commands_source_the_disposable_environment(tmp_path, monkeypatch):
    executable = tmp_path / "bin/python"
    executable.parent.mkdir()
    (executable.parent / "activate").write_text("# fixture activation")
    monkeypatch.setattr(adopt_acceptance.sys, "platform", "darwin")
    calls = []

    def completed(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(adopt_acceptance.subprocess, "run", completed)
    adopt_acceptance.run([str(executable), "-V"], cwd=tmp_path)
    assert calls[0][:3] == ["/bin/bash", "-c", 'source "$1"; shift; exec "$@"']
    assert calls[0][-2:] == [str(executable), "-V"]


def test_a_wheel_file_or_single_wheel_directory_is_accepted(tmp_path: Path) -> None:
    wheel = tmp_path / "prodockit-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    assert adopt_acceptance.resolve_wheel(wheel) == wheel.resolve()
    assert adopt_acceptance.resolve_wheel(tmp_path) == wheel.resolve()


def test_deliverables_allow_only_expected_optional_warnings(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        name = command[3]
        if name == "diag":
            output = "  WARN Project is not inside a Git repository\nResult: WARN (1 passed)"
        else:
            filename = f"{name}.pdf"
            (tmp_path / filename).write_bytes(b"%PDF-1.7\n")
            output = f"Wrote {filename}" + (" in 1.2s" if name == "pdf" else "")
        return subprocess.CompletedProcess(command, 0, stdout=output)

    monkeypatch.setattr(adopt_acceptance, "run", run)
    adopt_acceptance.verify_deliverables(Path("python"), tmp_path, tmp_path / "zensical.toml")
    assert [call[3] for call in calls] == ["diag", "pdf", "source-bundle"]


@pytest.mark.parametrize("output", ["", "  WARN Broken package\nResult: WARN (1 warning)"])
def test_deliverables_reject_unexpected_diagnostics(tmp_path, monkeypatch, output):
    monkeypatch.setattr(
        adopt_acceptance,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout=output),
    )
    with pytest.raises(adopt_acceptance.AcceptanceError, match="diagnostics did not pass"):
        adopt_acceptance.verify_deliverables(Path("python"), tmp_path, tmp_path / "zensical.toml")


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


def test_default_choice_run_does_not_pass_renderer_overrides(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="done")

    monkeypatch.setattr(adopt_acceptance, "run", run)
    adopt_acceptance.adopt(
        Path("python"), tmp_path, mermaid=False, maths=False, apply=True, use_defaults=True
    )
    assert calls == [["python", "-m", "prodockit", "adopt", "--apply"]]


def test_authoring_gate_rejects_unrendered_directives(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/index.md").write_text("# Site\n")
    (tmp_path / "site").mkdir()
    (tmp_path / "site/index.html").write_text(
        "prodockit-steps prodockit-tree prodockit-table-caption acceptance-table /// tree"
    )
    monkeypatch.setattr(adopt_acceptance, "build", lambda *args, **kwargs: None)
    monkeypatch.setattr(adopt_acceptance, "site_directory", lambda *args: tmp_path / "site")
    with pytest.raises(adopt_acceptance.AcceptanceError, match="unrendered authoring directive"):
        adopt_acceptance.verify_authoring(Path("python"), tmp_path, tmp_path / "zensical.toml")


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
        ("Error: could not install mermaid: Command ['npm', 'ci'] timed out after 600 seconds"),
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


def test_a_failed_run_still_writes_an_acceptance_report(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setattr(adopt_acceptance, "install_tested_renderer", lambda *args: None)
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
        b'<script src="./javascripts/pdk.js"></script>'
        b'<script src="./javascripts/extra.js"></script>'
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


def test_baseline_renderer_uses_versions_declared_by_the_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def completed(command, **_kwargs):
        commands.append(command)
        output = (
            "zensical==0.0.59\nMarkdown==3.10.3\npymdown-extensions==11.0.2\n"
            if command[-2:] != ["pip", "install"]
            else ""
        )
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(adopt_acceptance, "run", completed)

    adopt_acceptance.install_tested_renderer(Path("python"), tmp_path)

    assert commands[-1] == [
        "python",
        "-m",
        "pip",
        "install",
        "zensical==0.0.59",
        "Markdown==3.10.3",
        "pymdown-extensions==11.0.2",
    ]
