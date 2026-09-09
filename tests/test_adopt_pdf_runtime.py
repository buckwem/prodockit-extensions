# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from types import SimpleNamespace

import pytest

from prodockit import adopt_pdf_runtime as runtime
from prodockit.bootstrap import stages
from prodockit.bootstrap.config import BootstrapConfig
from prodockit.bootstrap.model import GITHUB_COM, MACOS, UBUNTU, WINDOWS, CommandResult, Context

REAL_PROBE = runtime._probe


def context(tmp_path, platform):
    runner = SimpleNamespace(run=lambda *args, **kwargs: CommandResult(returncode=1))
    return Context(BootstrapConfig(), GITHUB_COM, platform, runner, tmp_path, guided=True)


@pytest.mark.parametrize("platform", [MACOS, UBUNTU, WINDOWS])
def test_native_recipe_does_not_install_system_pandoc(tmp_path, monkeypatch, platform):
    ctx = context(tmp_path, platform)
    monkeypatch.setattr(stages, "_windows_python_is_arm64", lambda ctx: False)
    commands = stages._plan_pandoc(ctx, native_only=True).commands
    assert commands
    assert "jgm/pandoc" not in str(commands)
    assert "JohnMacFarlane.Pandoc" not in str(commands)
    assert not any(arg == "pandoc" for command in commands for arg in command)
    assert "pango" in str(commands).lower()


def test_healthy_native_runtime_requires_no_download(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "_context", lambda: context(tmp_path, UBUNTU))
    monkeypatch.setattr(
        runtime.shutil, "which", lambda name: pytest.fail("package manager checked")
    )
    assert not runtime.plan(offline=True).needs_work


def test_offline_missing_native_dependency_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "_context", lambda: context(tmp_path, UBUNTU))
    monkeypatch.setattr(runtime, "_probe", lambda *args, **kwargs: "Inter is missing")
    assert "online run" in runtime.plan(offline=True).blocked


@pytest.mark.parametrize("offline", [False, True])
def test_windows_assessment_refreshes_persisted_paths_before_probe(tmp_path, monkeypatch, offline):
    monkeypatch.setattr(runtime, "_context", lambda: context(tmp_path, WINDOWS))
    monkeypatch.delenv("WEASYPRINT_DLL_DIRECTORIES", raising=False)
    monkeypatch.setenv("PATH", "session-tools")

    def refresh():
        monkeypatch.setenv("WEASYPRINT_DLL_DIRECTORIES", "installed-pdf-libraries")
        monkeypatch.setenv("PATH", "session-tools;installed-font-tools")

    def probe(ctx):
        assert runtime.os.environ["WEASYPRINT_DLL_DIRECTORIES"] == "installed-pdf-libraries"
        assert "installed-font-tools" in runtime.os.environ["PATH"]
        return ""

    monkeypatch.setattr(runtime, "refresh_windows_path", refresh)
    monkeypatch.setattr(runtime, "_probe", probe)
    monkeypatch.setattr(runtime.shutil, "which", lambda name: pytest.fail("unexpected install"))
    assert not runtime.plan(offline=offline).needs_work


def test_pending_python_package_is_not_mistaken_for_native_install_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "_context", lambda: context(tmp_path, UBUNTU))
    monkeypatch.setattr(
        runtime, "_probe", lambda *args, **kwargs: "WeasyPrint Python package is pending"
    )
    plan = runtime.plan(offline=True)
    assert plan.needs_work
    assert not plan.commands
    assert not plan.blocked


def test_loader_repair_can_run_offline_without_package_install(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "_context", lambda: context(tmp_path, MACOS))
    monkeypatch.setattr(runtime, "_loader_missing", lambda ctx: True)
    plan = runtime.plan(offline=True)
    assert plan.environment_repair
    assert not plan.commands
    assert not plan.blocked


def test_macos_loader_updates_are_idempotent_and_preserve_activation(tmp_path, monkeypatch):
    ctx = context(tmp_path, MACOS)
    monkeypatch.setattr(runtime.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(
        runtime, "_macos_loader_line", lambda ctx: "export DYLD_FALLBACK_LIBRARY_PATH=/test/lib"
    )
    activate = tmp_path / "bin/activate"
    activate.parent.mkdir()
    activate.write_text("# user activation\nexport VIRTUAL_ENV=/example\n")
    runtime._persist_loader(ctx)
    before = activate.read_bytes()
    runtime._persist_loader(ctx)
    assert activate.read_bytes() == before
    assert b"# user activation" in before
    assert before.count(b"DYLD_FALLBACK_LIBRARY_PATH") == 1


def test_post_install_probe_must_succeed(tmp_path, monkeypatch):
    ctx = context(tmp_path, UBUNTU)
    monkeypatch.setattr(runtime, "_context", lambda: ctx)
    monkeypatch.setattr(runtime, "plan", lambda **kwargs: runtime.NativePlan((("installer",),)))
    monkeypatch.setattr(runtime, "run_commands", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime.shutil, "which", lambda name: None)
    monkeypatch.setattr(runtime, "_probe", lambda *args, **kwargs: "Pango cannot load")
    with pytest.raises(runtime.ToolchainError, match="verification failed"):
        runtime.apply(tmp_path)


@pytest.mark.parametrize("family", ["Inter", "JetBrains Mono"])
def test_fallback_font_is_not_accepted(tmp_path, monkeypatch, family):
    def run(command, **kwargs):
        if command[0] == runtime.sys.executable:
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(
            returncode=0, stdout="DejaVu Sans" if command[-1] == family else command[-1]
        )

    monkeypatch.setattr(runtime.subprocess, "run", run)
    assert family in REAL_PROBE(context(tmp_path, UBUNTU))


def test_verification_generates_pdf_not_just_import(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(
            returncode=0, stdout="" if command[0] == runtime.sys.executable else command[-1]
        )

    monkeypatch.setattr(runtime.subprocess, "run", run)
    assert not REAL_PROBE(context(tmp_path, UBUNTU), render=True)
    assert "write_pdf()" in calls[0][2]
    assert "b'%PDF'" in calls[0][2]


def test_probe_reports_the_actual_library_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr="Traceback\nOSError: libpango is missing\n"
        ),
    )
    assert "OSError: libpango is missing" in REAL_PROBE(context(tmp_path, UBUNTU))


def test_missing_python_dependency_is_not_a_native_library_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr="ModuleNotFoundError: No module named 'cssselect2'"
        ),
    )
    assert REAL_PROBE(context(tmp_path, UBUNTU)) == "WeasyPrint Python package is pending"


def test_apply_rechecks_native_runtime_after_package_upgrade(tmp_path, monkeypatch):
    from prodockit import adopt

    done = set()

    def assess(*args, **kwargs):
        native_needed = "dependency" in done and "pdf-runtime" not in done
        return [
            adopt.Step(
                "dependency",
                "Integrate",
                "Python packages",
                "ok" if "dependency" in done else "missing",
                "upgrade",
            ),
            adopt.Step(
                "pdf-runtime",
                "Integrate",
                "Native libraries",
                "missing" if native_needed else "ok",
                "verify",
            ),
        ]

    def apply_step(root, options, step_id, **kwargs):
        done.add(step_id)
        return []

    monkeypatch.setattr(adopt, "assess", assess)
    monkeypatch.setattr(adopt, "apply_step", apply_step)
    adopt.apply(tmp_path, adopt.AdoptOptions())
    assert done == {"dependency", "pdf-runtime"}
