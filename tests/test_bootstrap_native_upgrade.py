# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import gzip
import importlib
import io
import os
import stat
import subprocess
import urllib.error
import zipfile
from pathlib import Path

import pytest

native = importlib.import_module("tools.bootstrap_native_upgrade")


def _completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


def test_real_upgrade_routes_are_the_two_requested_paths() -> None:
    assert native.SCENARIOS == (
        ("surrey-existing-real-upgrade", "surrey", "existing"),
        ("github-new-real-upgrade", "github", "new"),
    )


def test_real_upgrade_routes_can_be_selected_independently() -> None:
    assert native.select_scenarios(["github-new-real-upgrade"]) == (
        ("github-new-real-upgrade", "github", "new"),
    )
    assert native.select_scenarios(None) == native.SCENARIOS
    assert native.select_scenarios(["all"]) == native.SCENARIOS


def test_all_cannot_be_combined_with_a_named_upgrade_route() -> None:
    with pytest.raises(native.NativeInstallError, match="cannot be combined"):
        native.select_scenarios(["all", "surrey-existing-real-upgrade"])


def test_old_extension_packages_are_below_every_supported_floor() -> None:
    for identifier, version in native.OLD_EXTENSIONS.items():
        minimum = native.VSCODE_EXTENSION_MIN_VERSIONS[identifier]
        assert native._parts(version) < native._parts(minimum)


def test_marketplace_download_names_the_exact_old_package(monkeypatch) -> None:
    monkeypatch.setattr(native, "current_platform", lambda: native.MACOS)
    monkeypatch.setattr(native, "_is_arm64", lambda: True)

    assert native._marketplace_url("example.extension", "1.2.3") == (
        "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
        "example/vsextensions/extension/1.2.3/vspackage?targetPlatform=darwin-arm64"
    )


def test_marketplace_gzip_response_is_decoded_to_the_vsix_bytes(
    monkeypatch, tmp_path: Path
) -> None:
    class Response(io.BytesIO):
        def __init__(self, content: bytes) -> None:
            super().__init__(content)
            self.headers = {"Content-Encoding": "gzip"}

    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("extension/package.json", "{}")
    expected = package.getvalue()
    monkeypatch.setattr(
        native.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(gzip.compress(expected)),
    )

    destination = native._download("https://example.invalid/extension", tmp_path / "x.vsix")

    assert destination.read_bytes() == expected


def test_universal_marketplace_extension_is_the_404_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    attempted: list[str] = []

    def download(url: str, destination: Path, **_kwargs: object) -> Path:
        attempted.append(url)
        if "targetPlatform=" in url:
            raise urllib.error.HTTPError(url, 404, "not platform-specific", {}, None)
        destination.write_bytes(b"universal")
        return destination

    monkeypatch.setattr(native, "current_platform", lambda: native.UBUNTU)
    monkeypatch.setattr(native, "_is_arm64", lambda: False)
    monkeypatch.setattr(native, "download", download)

    destination = native._download_marketplace(
        "zensical.zensical-studio", "0.2.11", tmp_path / "extension.vsix"
    )

    assert "targetPlatform=linux-x64" in attempted[0]
    assert "?" not in attempted[1]
    assert destination.read_bytes() == b"universal"


def test_download_sources_moves_to_the_next_compatible_source(
    monkeypatch, tmp_path: Path
) -> None:
    attempted: list[tuple[str, str | None]] = []

    def download(
        url: str, destination: Path, *, cache_key: str | None = None, **_kwargs: object
    ) -> Path:
        attempted.append((url, cache_key))
        if url.endswith("primary"):
            raise native.DownloadError("primary exhausted")
        destination.write_bytes(b"mirror")
        return destination

    monkeypatch.setattr(native, "download", download)
    result = native._download_sources(
        ("https://example.invalid/primary", "https://mirror.invalid/fallback"),
        tmp_path / "fixture.tar.gz",
    )

    assert result.read_bytes() == b"mirror"
    assert [url for url, _cache_key in attempted] == [
        "https://example.invalid/primary",
        "https://mirror.invalid/fallback",
    ]
    assert attempted[0][1] == attempted[1][1]


def test_executable_lookup_ignores_a_directory_with_the_same_name(
    tmp_path: Path,
) -> None:
    misleading = tmp_path / "include" / "node"
    misleading.mkdir(parents=True)
    executable = tmp_path / "distribution" / "bin" / "node"
    executable.parent.mkdir(parents=True)
    executable.write_text("fixture", encoding="utf-8")

    assert native._find(tmp_path, ("node",)) == executable


@pytest.mark.skipif(os.name == "nt", reason="Unix executable modes are not used on Windows")
def test_zip_extraction_preserves_an_executable_launcher(tmp_path: Path) -> None:
    archive = tmp_path / "application.zip"
    member = zipfile.ZipInfo("Application/bin/code")
    member.create_system = 3
    member.external_attr = 0o100755 << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(member, "#!/bin/sh\n")

    destination = tmp_path / "unpacked"
    native._extract_zip(archive, destination)

    assert (destination / member.filename).stat().st_mode & 0o111


@pytest.mark.skipif(os.name == "nt", reason="Unix symbolic links are not used on Windows")
def test_zip_extraction_preserves_a_framework_symbolic_link(tmp_path: Path) -> None:
    archive = tmp_path / "application.zip"
    link = zipfile.ZipInfo("Application/Frameworks/Current")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(link, "Versions/A/Framework")

    destination = tmp_path / "unpacked"
    native._extract_zip(archive, destination)

    extracted = destination / link.filename
    assert extracted.is_symlink()
    assert os.readlink(extracted) == "Versions/A/Framework"


def test_mac_path_proves_old_tools_before_homebrew_replaces_them(
    monkeypatch, tmp_path: Path
) -> None:
    manager = tmp_path / "homebrew" / "bin"
    old = tmp_path / "old" / "bin"
    monkeypatch.setenv("PATH", os.pathsep.join(("/usr/bin", str(manager))))
    monkeypatch.setattr(native, "_run", lambda *_args, **_kwargs: _completed("/brew\n"))

    environment = native._scenario_environment(
        recipe=native.MACOS,
        portable_bins=[old],
        home=tmp_path / "home",
    )

    assert environment["PATH"].split(os.pathsep)[:2] == [str(old), "/brew/bin"]


def test_ubuntu_path_proves_old_tools_before_apt_replaces_them(
    monkeypatch, tmp_path: Path
) -> None:
    old = tmp_path / "old" / "bin"
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")

    environment = native._scenario_environment(
        recipe=native.UBUNTU,
        portable_bins=[old],
        home=tmp_path / "home",
    )

    assert environment["PATH"].split(os.pathsep) == [
        str(old),
        "/usr/local/bin",
        "/usr/bin",
    ]


def test_version_resolves_against_the_controlled_path(monkeypatch, tmp_path: Path) -> None:
    old = tmp_path / "old" / "bin"
    old.mkdir(parents=True)
    executable = old / "node"
    executable.write_text("fixture", encoding="utf-8")
    executable.chmod(0o755)
    seen: list[list[str]] = []

    def run(command, **_kwargs):  # type: ignore[no-untyped-def]
        seen.append(command)
        return _completed("v18.20.0\n")

    monkeypatch.setattr(native, "_run", run)

    assert native._version(["node", "--version"], {"PATH": str(old)}) == "18.20.0"
    assert seen == [[str(executable), "--version"]]


def test_windows_path_starts_with_the_unregistered_old_tool(
    monkeypatch, tmp_path: Path
) -> None:
    old = tmp_path / "old" / "bin"
    monkeypatch.setenv("PATH", r"C:\Program Files\nodejs;C:\Windows")
    monkeypatch.setenv("USERPROFILE", r"C:\Users\runner")

    environment = native._scenario_environment(
        recipe=native.WINDOWS,
        portable_bins=[old],
        home=tmp_path / "home",
    )

    assert environment["PATH"].split(os.pathsep)[0] == str(old)
    assert environment["USERPROFILE"] == r"C:\Users\runner"
    assert environment["HOME"] == str(tmp_path / "home")


def test_old_winget_fixture_repairs_a_missing_source_catalogue(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def run(command, *, check=True, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append((command, check))
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                command,
                0x8A15000F,
                stdout="Data required by the source is missing",
                stderr="",
            )
        return _completed()

    monkeypatch.setattr(native, "_run", run)

    native._winget_old("Microsoft.VisualStudioCode", "1.80.2")

    assert calls[0][0][:4] == [
        "winget",
        "install",
        "--id",
        "Microsoft.VisualStudioCode",
    ]
    assert calls[0][1] is False
    assert calls[1] == (["winget", "source", "reset", "--force"], True)
    assert calls[2] == (["winget", "source", "update"], True)
    assert calls[3][0] == calls[0][0]
    assert calls[3][1] is True


def test_old_winget_fixture_does_not_repair_an_unrelated_failure(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(command, *, check=True, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 1, stdout="No applicable installer found", stderr=""
        )

    monkeypatch.setattr(native, "_run", run)

    with pytest.raises(native.NativeInstallError, match="No applicable installer"):
        native._winget_old("Microsoft.VisualStudioCode", "1.80.2")

    assert len(calls) == 1


def test_native_upgrade_refuses_a_developer_machine(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    with pytest.raises(native.NativeInstallError, match="disposable GitHub Actions"):
        native.run_native_upgrades(
            tmp_path / "prodockit.whl", tmp_path / "report.json"
        )


def test_windows_seed_requests_actual_old_package_versions(
    monkeypatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(native, "_ensure_windows_winget", lambda: None)
    monkeypatch.setattr(native, "refresh_windows_path", lambda: None)

    def record(command, **_kwargs):  # type: ignore[no-untyped-def]
        commands.append(list(command))
        return _completed()

    monkeypatch.setattr(native, "_run", record)

    node_installer = tmp_path / "node-18.msi"
    native._install_windows_old_software(node_installer)

    rendered = "\n".join(" ".join(command) for command in commands)
    assert f"Microsoft.VisualStudioCode --version {native.OLD_VSCODE}" in rendered
    assert f"Git.Git --version {native.OLD_GIT}" in rendered
    assert f"JohnMacFarlane.Pandoc --version {native.OLD_PANDOC}" in rendered
    assert "OpenJS.NodeJS.LTS" not in rendered
    assert "DisplayName -like 'Node.js*'" in rendered
    assert "@('/x', $product, '/qn', '/norestart')" in rendered
    assert f"msiexec.exe /i {node_installer} /qn /norestart" in rendered


def test_windows_old_node_comes_from_the_signed_machine_installer(
    monkeypatch, tmp_path: Path
) -> None:
    seen: list[tuple[str, Path]] = []

    def download(url: str, destination: Path) -> Path:
        seen.append((url, destination))
        return destination

    monkeypatch.setattr(native, "_download", download)

    installer = native._windows_old_node_installer(tmp_path)

    assert seen == [
        (
            f"https://nodejs.org/dist/v{native.OLD_NODE}/"
            f"node-v{native.OLD_NODE}-x64.msi",
            tmp_path / f"node-v{native.OLD_NODE}-x64.msi",
        )
    ]
    assert installer.suffix == ".msi"
