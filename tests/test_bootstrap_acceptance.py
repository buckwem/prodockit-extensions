# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Safety checks for the installed-wheel bootstrap acceptance harness."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
bootstrap_acceptance = importlib.import_module("tools.bootstrap_acceptance")
bootstrap_acceptance_driver = importlib.import_module("tools._bootstrap_acceptance_driver")


def test_all_host_and_repository_routes_are_declared() -> None:
    assert bootstrap_acceptance.SCENARIOS == (
        ("surrey-new", "surrey", "new", False),
        ("surrey-existing", "surrey", "existing", False),
        ("surrey-existing-old-software", "surrey", "existing", True),
        ("github-new-old-software", "github", "new", True),
        ("github-existing", "github", "existing", False),
    )


@pytest.mark.parametrize(
    ("host", "route", "supported"),
    [
        ("surrey", "new", False),
        ("surrey", "existing", True),
        ("github", "new", True),
        ("github", "existing", False),
    ],
)
def test_old_software_runs_only_on_the_two_deliberate_routes(
    host: str, route: str, supported: bool
) -> None:
    assert bootstrap_acceptance_driver.supports_old_software_route(host, route) is supported


def test_real_software_keeps_the_same_machine_and_repository_scope() -> None:
    stages = {
        stage.id: stage
        for stage in bootstrap_acceptance_driver.acceptance_stages(real_software=True)
    }

    for stage_id in ("vscode", "git", "pandoc", "node", "extensions"):
        assert stages[stage_id].check.__module__ != bootstrap_acceptance_driver.__name__


def test_real_software_repository_fixture_has_actual_toolchain_locks(
    tmp_path: Path,
) -> None:
    bootstrap_acceptance_driver.write_project(
        tmp_path, marker="Native upgrade", real_toolchains=True
    )

    assert (tmp_path / "tools" / "mermaid" / "package.json").is_file()
    assert (tmp_path / "tools" / "mermaid" / "package-lock.json").is_file()
    assert (tmp_path / "tools" / "mathjax" / "package.json").is_file()
    assert (tmp_path / "tools" / "mathjax" / "package-lock.json").is_file()
    assert (tmp_path / "tools" / "mathjax" / "tex2svg.js").is_file()
    assert not (tmp_path / "tools" / "mermaid" / "node_modules").exists()


def test_real_windows_software_uses_the_native_user_application_home(tmp_path: Path) -> None:
    isolated = tmp_path / "scenario-home"
    native = tmp_path / "windows-user"
    environment = {"HOME": str(isolated), "USERPROFILE": str(native)}

    assert bootstrap_acceptance_driver.machine_home(
        environment, real_software=True, platform_name="windows"
    ) == native
    assert bootstrap_acceptance_driver.machine_home(
        environment, real_software=False, platform_name="windows"
    ) == isolated
    assert bootstrap_acceptance_driver.machine_home(
        environment, real_software=True, platform_name="macos"
    ) == isolated


def test_real_software_commands_cross_the_machine_boundary(monkeypatch, tmp_path: Path) -> None:
    runner = bootstrap_acceptance_driver.HarnessRunner(
        {},
        "git@example.invalid:group/project.git",
        home=tmp_path,
        real_software=True,
    )
    seen: list[list[str]] = []

    def execute(command, cwd=None, timeout=None, capture=True):  # type: ignore[no-untyped-def]
        del cwd, timeout, capture
        seen.append(list(command))
        return bootstrap_acceptance_driver.CommandResult(0, "pandoc 2.19.2\n")

    monkeypatch.setattr(runner.system, "run", execute)

    result = runner.run(["pandoc", "--version"])

    assert result.stdout == "pandoc 2.19.2\n"
    assert seen == [["pandoc", "--version"]]


def test_git_host_rewrites_are_attached_to_each_harness_command(
    monkeypatch, tmp_path: Path
) -> None:
    remote = "git@example.invalid:group/project.git"
    local = tmp_path / "project.git"
    environment = {"PATH": os.environ["PATH"]}
    runner = bootstrap_acceptance_driver.HarnessRunner(
        environment,
        remote,
        home=tmp_path,
        remote_rewrites={remote: local},
    )
    seen: list[list[str]] = []

    def execute(command, **_kwargs):  # type: ignore[no-untyped-def]
        seen.append(list(command))
        return bootstrap_acceptance_driver.subprocess.CompletedProcess(
            command, 0, "local refs\n", ""
        )

    monkeypatch.setattr(bootstrap_acceptance_driver, "run", execute)

    result = runner.run(["git", "ls-remote", remote])

    assert result.ok
    assert seen == [
        [
            "git",
            "-c",
            f"url.{local.resolve().as_uri()}.insteadOf={remote}",
            "ls-remote",
            remote,
        ]
    ]


@pytest.mark.parametrize(
    ("command", "revealed"),
    [
        (["winget", "install", "--id", "OpenJS.NodeJS.LTS"], "node"),
        (["sudo", "apt", "install", "-y", "/tmp/pandoc.deb"], "pandoc"),
        (["bash", "-c", "brew install git"], "git"),
    ],
)
def test_real_install_reveals_only_the_tool_just_replaced(
    monkeypatch, tmp_path: Path, command: list[str], revealed: str
) -> None:
    old = {name: str(tmp_path / name) for name in ("git", "pandoc", "node")}
    environment = {
        "PATH": os.pathsep.join([*old.values(), "/new/tools"]),
        "PDKBOOT_ACCEPTANCE_OLD_TOOL_BINS": json.dumps(old),
    }
    monkeypatch.setenv("PATH", environment["PATH"])
    runner = bootstrap_acceptance_driver.HarnessRunner(
        environment,
        "git@example.invalid:group/project.git",
        home=tmp_path,
        real_software=True,
    )
    monkeypatch.setattr(
        runner.system,
        "run",
        lambda *_args, **_kwargs: bootstrap_acceptance_driver.CommandResult(0),
    )

    runner.run(command)

    remaining = environment["PATH"].split(os.pathsep)
    assert old[revealed] not in remaining
    assert "/new/tools" in remaining
    for name, path in old.items():
        if name != revealed:
            assert path in remaining


def test_simulated_old_software_understands_resilient_homebrew_upgrades(
    tmp_path: Path,
) -> None:
    runner = bootstrap_acceptance_driver.HarnessRunner(
        {},
        "git@example.invalid:group/project.git",
        home=tmp_path,
        old_software=True,
    )

    runner.run(
        [
            "bash",
            "-c",
            "if brew list --cask visual-studio-code; then "
            "brew upgrade --cask visual-studio-code; else "
            "brew install --cask --force visual-studio-code; fi",
        ]
    )

    assert runner.versions["vscode"] == "1.100.0"


def test_a_wheel_file_or_single_wheel_directory_is_accepted(tmp_path: Path) -> None:
    wheel = tmp_path / "prodockit-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    assert bootstrap_acceptance.resolve_wheel(wheel) == wheel.resolve()
    assert bootstrap_acceptance.resolve_wheel(tmp_path) == wheel.resolve()


def test_an_ambiguous_wheel_directory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "prodockit-1-py3-none-any.whl").write_bytes(b"one")
    (tmp_path / "prodockit-2-py3-none-any.whl").write_bytes(b"two")

    with pytest.raises(bootstrap_acceptance.AcceptanceError, match="expected one"):
        bootstrap_acceptance.resolve_wheel(tmp_path)


def test_architecture_requirements_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        bootstrap_acceptance.parser().parse_args(
            [
                "--wheel",
                "candidate.whl",
                "--report",
                "report.json",
                "--require-x64",
                "--require-arm64",
            ]
        )


@pytest.mark.parametrize("machine", ["arm64", "aarch64"])
def test_arm64_architecture_names_are_accepted(monkeypatch, machine: str) -> None:
    monkeypatch.setattr(bootstrap_acceptance.platform, "machine", lambda: machine)

    assert bootstrap_acceptance.require_architecture(x64=False, arm64=True) == machine


def test_x64_is_rejected_when_arm64_is_required(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap_acceptance.platform, "machine", lambda: "x86_64")

    with pytest.raises(bootstrap_acceptance.AcceptanceError, match="expected ARM64"):
        bootstrap_acceptance.require_architecture(x64=False, arm64=True)


def test_driver_never_imports_the_source_bootstrap_test_harness() -> None:
    driver = (ROOT / "tools" / "_bootstrap_acceptance_driver.py").read_text(encoding="utf-8")

    assert "tests.bootstrap_cli_harness" not in driver
    assert "git clone" not in driver, "repository commands go through argument lists"
    assert "gitlab.surrey.ac.uk" not in driver, "host addresses come from the wheel"


def test_ubuntu_npm_commands_install_toolchains_before_resolving_chromium(
    tmp_path: Path,
) -> None:
    runner = bootstrap_acceptance_driver.HarnessRunner(
        {},
        "git@example.invalid:group/project.git",
        home=tmp_path,
        old_software=True,
    )
    prefix = tmp_path / "project" / "tools" / "mermaid"
    command = [
        "bash",
        "-c",
        (
            "export PUPPETEER_EXECUTABLE_PATH=$(which chromium-browser || "
            f"which chromium); cd {prefix} && npm ci"
        ),
    ]

    result = runner.run(command)

    assert result.returncode == 0
    assert (prefix / "node_modules" / ".bin" / "mmdc").is_file()
