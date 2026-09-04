# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exact, template-independent toolchain alignment used by Adopt."""

from __future__ import annotations

import subprocess
import sys
import urllib.error
import zipfile
from pathlib import Path

import pytest

from prodockit import toolchain
from prodockit.pins import DEFAULT_PACKAGES, TESTED_VERSIONS, discover


def _supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(toolchain, "installed_python_version", lambda: TESTED_VERSIONS["python"])
    monkeypatch.setattr(
        toolchain,
        "installed_distribution_version",
        lambda package: TESTED_VERSIONS[package],
    )
    monkeypatch.setattr(toolchain, "installed_pandoc_version", lambda: TESTED_VERSIONS["pandoc"])


def test_python_mismatch_blocks_before_inventory_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "requirements.txt").write_text("untouched\n", encoding="utf-8")
    monkeypatch.setattr(toolchain, "installed_python_version", lambda: "3.13")
    monkeypatch.setattr(
        toolchain,
        "installed_distribution_version",
        lambda _package: pytest.fail("packages must not be inventoried after Python blocks"),
    )

    planned = toolchain.plan(tmp_path)

    assert "Python 3.13 is active" in planned.blocked
    assert "Python 3.14 virtual environment" in planned.blocked
    assert planned.commands == ()
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == "untouched\n"


@pytest.mark.parametrize(
    ("installed", "expected"),
    (("0.0.1", "upgrade"), ("999.0.0", "downgrade"), (None, "install")),
)
def test_plan_names_upgrade_downgrade_and_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    installed: str | None,
    expected: str,
) -> None:
    _supported(monkeypatch)
    monkeypatch.setattr(
        toolchain,
        "installed_distribution_version",
        lambda package: installed if package == "zensical" else TESTED_VERSIONS[package],
    )

    planned = toolchain.plan(tmp_path)

    action = next(item for item in planned.actions if item.package == "zensical")
    assert action.action == expected
    assert expected in planned.detail
    assert any("zensical==0.0.59" in command for command in planned.commands)


def test_pip_plan_uses_cache_friendly_retries_and_an_explicit_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(toolchain.PYPI_MIRROR_ENV, "https://mirror.example/simple")

    command = toolchain.pip_install_command(("zensical",))

    assert command[0] == toolchain.sys.executable
    assert command[command.index("--retries") + 1] == "5"
    assert command[command.index("--timeout") + 1] == "30"
    assert "--prefer-binary" in command
    assert command[command.index("--extra-index-url") + 1] == "https://mirror.example/simple"
    assert command[-1] == f"zensical=={TESTED_VERSIONS['zensical']}"


def test_offline_pip_plan_requires_only_the_configured_wheelhouse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(toolchain.WHEELHOUSE_ENV, "/cache/wheels")

    command = toolchain.pip_install_command(("markdown",), offline=True)

    assert "--no-index" in command
    assert command[command.index("--find-links") + 1] == "/cache/wheels"
    assert "--extra-index-url" not in command


def test_plan_does_not_resolve_dependencies_again_for_installed_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _supported(monkeypatch)
    monkeypatch.setattr(
        toolchain,
        "installed_distribution_version",
        lambda package: "0.0.1" if package == "weasyprint" else TESTED_VERSIONS[package],
    )

    planned = toolchain.plan(tmp_path)

    command = next(command for command in planned.commands if "weasyprint==69.0" in command)
    assert "--no-deps" in command


def test_plan_resolves_dependencies_for_missing_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _supported(monkeypatch)
    monkeypatch.setattr(
        toolchain,
        "installed_distribution_version",
        lambda package: None if package == "weasyprint" else TESTED_VERSIONS[package],
    )

    planned = toolchain.plan(tmp_path)

    command = next(command for command in planned.commands if "weasyprint==69.0" in command)
    assert "--no-deps" not in command


def test_declarations_are_complete_and_preserve_operators_extras_and_unrelated_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _supported(monkeypatch)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "sphinx==8.0\nprodockit[index]>=0.1  # keep extras\nzensical~=0.0.1\n",
        encoding="utf-8",
    )

    written = toolchain.write_declarations(tmp_path)

    source = requirements.read_text(encoding="utf-8")
    assert "sphinx==8.0" in source
    assert f"prodockit[index]>={TESTED_VERSIONS['prodockit']}  # keep extras" in source
    assert f"zensical~={TESTED_VERSIONS['zensical']}" in source
    assert f"weasyprint=={TESTED_VERSIONS['weasyprint']}" in source
    assert f"markdown=={TESTED_VERSIONS['markdown']}" in source
    assert f"pymdown-extensions=={TESTED_VERSIONS['pymdown-extensions']}" in source
    assert (tmp_path / ".python-version").read_text(encoding="utf-8") == "3.14\n"
    assert tmp_path / toolchain.TOOLCHAIN_MANIFEST in written

    states = discover(str(tmp_path))
    assert set(states) == set(DEFAULT_PACKAGES)
    assert all(state.versions == [TESTED_VERSIONS[name]] for name, state in states.items())


def test_failed_install_does_not_write_supported_declarations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _supported(monkeypatch)
    monkeypatch.setattr(
        toolchain,
        "installed_distribution_version",
        lambda package: "0.0.1" if package == "zensical" else TESTED_VERSIONS[package],
    )
    monkeypatch.setattr(
        toolchain,
        "_run_resilient",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(toolchain.ToolchainError("failed")),
    )

    with pytest.raises(toolchain.ToolchainError, match="failed"):
        toolchain.apply(tmp_path)

    assert not (tmp_path / "requirements.txt").exists()
    assert not (tmp_path / toolchain.TOOLCHAIN_MANIFEST).exists()


def test_apply_verifies_versions_then_becomes_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions = dict(TESTED_VERSIONS)
    versions["zensical"] = "0.0.1"
    pandoc = "2.19"
    monkeypatch.setattr(toolchain, "installed_python_version", lambda: TESTED_VERSIONS["python"])
    monkeypatch.setattr(
        toolchain, "installed_distribution_version", lambda package: versions[package]
    )
    monkeypatch.setattr(
        toolchain,
        "_fresh_distribution_versions",
        lambda packages: {package: versions[package] for package in packages},
    )
    monkeypatch.setattr(toolchain, "installed_pandoc_version", lambda: pandoc)

    def run(command, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal pandoc
        if "pip" in command:
            versions["zensical"] = TESTED_VERSIONS["zensical"]
        else:
            pandoc = TESTED_VERSIONS["pandoc"]

    monkeypatch.setattr(toolchain, "_run_resilient", run)

    assert toolchain.apply(tmp_path)
    assert not toolchain.plan(tmp_path).needs_work
    assert toolchain.apply(tmp_path) == []


def test_pandoc_download_tries_configured_mirror_then_official_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(toolchain, "_cache_root", lambda: tmp_path / "cache")
    monkeypatch.setattr(toolchain, "_pandoc_asset", lambda _version: "pandoc.zip")
    monkeypatch.setenv(toolchain.PANDOC_MIRROR_ENV, "https://mirror.example")
    monkeypatch.setattr(toolchain, "DEFAULT_RETRY_DELAYS", (0.0, 0.0))
    calls: list[str] = []

    def download(url: str, destination: Path) -> None:
        calls.append(url)
        if "mirror.example" in url:
            raise urllib.error.URLError("mirror unavailable")
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("pandoc/bin/pandoc", "fixture")

    monkeypatch.setattr(toolchain, "_download", download)

    result = toolchain._download_pandoc("3.10.1", tmp_path / "pandoc.zip", offline=False)

    assert result.is_file()
    assert calls[:3] == ["https://mirror.example/3.10.1/pandoc.zip"] * 3
    assert calls[-1].startswith("https://github.com/jgm/pandoc/releases/download/")
    assert (tmp_path / "cache" / "pandoc.zip").is_file()


@pytest.mark.parametrize(
    ("system", "machine", "asset"),
    (
        ("darwin", "x86_64", "pandoc-3.10.1-x86_64-macOS.zip"),
        ("darwin", "arm64", "pandoc-3.10.1-arm64-macOS.zip"),
        ("linux", "x86_64", "pandoc-3.10.1-linux-amd64.tar.gz"),
        ("linux", "aarch64", "pandoc-3.10.1-linux-arm64.tar.gz"),
        ("win32", "amd64", "pandoc-3.10.1-windows-x86_64.zip"),
        ("win32", "arm64", "pandoc-3.10.1-windows-x86_64.zip"),
    ),
)
def test_pandoc_assets_cover_all_six_wheel_environments(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    machine: str,
    asset: str,
) -> None:
    monkeypatch.setattr(sys, "platform", system)
    monkeypatch.setattr(toolchain.platform, "machine", lambda: machine)

    assert toolchain._pandoc_asset("3.10.1") == asset


def test_pandoc_download_moves_immediately_to_fallback_after_permanent_http_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(toolchain, "_cache_root", lambda: tmp_path / "cache")
    monkeypatch.setattr(toolchain, "_pandoc_asset", lambda _version: "pandoc.zip")
    monkeypatch.setenv(toolchain.PANDOC_MIRROR_ENV, "https://mirror.example")
    calls: list[str] = []

    def download(url: str, destination: Path) -> None:
        calls.append(url)
        if "mirror.example" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("pandoc/bin/pandoc", "fixture")

    monkeypatch.setattr(toolchain, "_download", download)

    toolchain._download_pandoc("3.10.1", tmp_path / "pandoc.zip", offline=False)

    assert len([url for url in calls if "mirror.example" in url]) == 1
    assert calls[-1].startswith("https://github.com/jgm/pandoc/releases/download/")


def test_offline_pandoc_download_reuses_validated_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    with zipfile.ZipFile(cache / "pandoc.zip", "w") as archive:
        archive.writestr("pandoc/bin/pandoc", "fixture")
    monkeypatch.setattr(toolchain, "_cache_root", lambda: cache)
    monkeypatch.setattr(toolchain, "_pandoc_asset", lambda _version: "pandoc.zip")
    monkeypatch.setattr(
        toolchain, "_download", lambda *_args: pytest.fail("offline cache must avoid network")
    )

    destination = toolchain._download_pandoc(
        "3.10.1", tmp_path / "copy" / "pandoc.zip", offline=True
    )

    assert destination.is_file()


def test_toolchain_subprocess_failure_includes_command_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        toolchain.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["pip"], 2, stdout="", stderr="permanent resolver failure"
        ),
    )

    with pytest.raises(toolchain.ToolchainError, match="permanent resolver failure"):
        toolchain._run_resilient(("pip", "install"), root=tmp_path, reporter=None, offline=False)
