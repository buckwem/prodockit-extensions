# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import json
import shutil
import subprocess

import pytest

from prodockit import adopt_browser as browser
from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS

REAL_CACHED_BROWSER = browser._cached_browser
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="real browser-path probe requires Node.js")
@pytest.mark.parametrize("asynchronous", [False, True])
def test_real_node_resolves_cached_browser_and_reuses_it_offline(
    tmp_path, monkeypatch, asynchronous
):
    package = tmp_path / "tools/mermaid/node_modules/puppeteer"
    package.mkdir(parents=True)
    executable = tmp_path / "browser cache/Google Chrome for Testing"
    executable.parent.mkdir()
    executable.write_text("browser fixture")
    value = json.dumps(str(executable))
    result = f"Promise.resolve({value})" if asynchronous else value
    (package / "index.js").write_text(f"exports.executablePath = () => {result};")
    monkeypatch.setattr(browser.shutil, "which", lambda name: NODE)
    monkeypatch.setattr(browser, "_cached_browser", REAL_CACHED_BROWSER)
    monkeypatch.setattr(browser, "current_platform", lambda: MACOS)
    monkeypatch.setattr(browser, "run_install_command", lambda *a, **k: pytest.fail("download"))
    assert browser._cached_browser(tmp_path) == str(executable)
    browser.complete(tmp_path, offline=True)
    executable.unlink()
    assert browser._cached_browser(tmp_path) is None


@pytest.mark.skipif(NODE is None, reason="real browser-path probe requires Node.js")
def test_rejected_browser_path_promise_is_not_a_cached_browser(tmp_path, monkeypatch):
    package = tmp_path / "tools/mermaid/node_modules/puppeteer"
    package.mkdir(parents=True)
    (package / "index.js").write_text(
        "exports.executablePath = () => Promise.reject(new Error('cache unavailable'));"
    )
    monkeypatch.setattr(browser.shutil, "which", lambda name: NODE)
    assert REAL_CACHED_BROWSER(tmp_path) is None


@pytest.fixture(autouse=True)
def no_host_browser(monkeypatch):
    monkeypatch.delenv("PUPPETEER_EXECUTABLE_PATH", raising=False)
    monkeypatch.setattr(browser, "_system_browser", lambda: None)
    monkeypatch.setattr(browser, "_cached_browser", lambda root: None)
    monkeypatch.setattr(browser.shutil, "which", lambda name: name)


def test_ubuntu_uses_native_chromium_before_npm(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "current_platform", lambda: UBUNTU)
    commands = []

    def install(root, planned, **kwargs):
        commands.extend(planned)
        monkeypatch.setattr(browser, "_system_browser", lambda: "/usr/bin/chromium")

    monkeypatch.setattr(browser, "run_commands", install)
    env = browser.prepare(tmp_path)
    assert "chromium-browser" in str(commands)
    assert "DPkg::Lock::Timeout=600" in str(commands)
    assert env["PUPPETEER_SKIP_DOWNLOAD"] == "true"
    assert env["PUPPETEER_EXECUTABLE_PATH"] == "/usr/bin/chromium"


def test_ubuntu_offline_without_browser_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "current_platform", lambda: UBUNTU)
    assert browser.plan(tmp_path, offline=True).blocked
    monkeypatch.setattr(browser, "run_commands", lambda *args, **kwargs: pytest.fail("install"))
    with pytest.raises(browser.ToolchainError, match="online run"):
        browser.prepare(tmp_path, offline=True)


@pytest.mark.parametrize("platform", [MACOS, WINDOWS])
def test_system_browser_is_reused_without_a_download(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(browser, "current_platform", lambda: platform)
    monkeypatch.setattr(browser, "_system_browser", lambda: "/test/browser")
    monkeypatch.setattr(
        browser, "run_install_command", lambda *args, **kwargs: pytest.fail("download")
    )
    assert not browser.plan(tmp_path).commands
    assert browser.prepare(tmp_path)["PUPPETEER_SKIP_DOWNLOAD"] == "true"
    browser.complete(tmp_path, offline=True)


def test_invalid_explicit_override_is_not_silently_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv("PUPPETEER_EXECUTABLE_PATH", "/missing/browser")
    assert "correct or unset" in browser.plan(tmp_path).blocked


def test_cached_browser_works_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "current_platform", lambda: MACOS)
    monkeypatch.setattr(browser, "_cached_browser", lambda root: "/cache/chrome")
    monkeypatch.setattr(
        browser, "run_install_command", lambda *args, **kwargs: pytest.fail("download")
    )
    browser.complete(tmp_path, offline=True)


def test_uncached_browser_cannot_download_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "current_platform", lambda: WINDOWS)
    monkeypatch.setattr(
        browser, "run_install_command", lambda *args, **kwargs: pytest.fail("download")
    )
    with pytest.raises(browser.ToolchainError, match="not cached"):
        browser.complete(tmp_path, offline=True)


def cli_file(root):
    lock = json.loads((browser.TEMPLATE_DIR / "mermaid/package-lock.json").read_text())
    path = (
        root
        / "tools/mermaid/node_modules/puppeteer"
        / lock["packages"]["node_modules/puppeteer"]["bin"]["puppeteer"]
    )
    path.parent.mkdir(parents=True)
    path.write_text("// fixture")
    return path


@pytest.mark.skipif(NODE is None, reason="real browser-path probe requires Node.js")
def test_new_browser_install_is_recognised_through_async_path(tmp_path, monkeypatch):
    cli_file(tmp_path)
    package = tmp_path / "tools/mermaid/node_modules/puppeteer"
    executable = tmp_path / "downloaded browser"
    (package / "index.js").write_text(
        "exports.executablePath = () => Promise.resolve("
        + json.dumps(str(executable))
        + ");"
    )
    monkeypatch.setattr(browser.shutil, "which", lambda name: NODE)
    monkeypatch.setattr(browser, "_cached_browser", REAL_CACHED_BROWSER)
    monkeypatch.setattr(browser, "current_platform", lambda: MACOS)
    installs = []

    def install(command, **kwargs):
        installs.append(command)
        executable.write_text("downloaded browser fixture")

    monkeypatch.setattr(browser, "run_install_command", install)
    browser.complete(tmp_path)
    browser.complete(tmp_path, offline=True)
    assert len(installs) == 1


@pytest.mark.parametrize("platform", [MACOS, WINDOWS])
def test_only_installed_locked_puppeteer_cli_can_download(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(browser, "current_platform", lambda: platform)
    cli = cli_file(tmp_path)
    calls = []

    def install(command, **kwargs):
        calls.append(command)
        monkeypatch.setattr(browser, "_cached_browser", lambda root: "/cache/chrome")

    monkeypatch.setattr(browser, "run_install_command", install)
    browser.complete(tmp_path)
    assert calls == [["node", str(cli), "browsers", "install"]]
    assert "npm" not in calls[0]


def test_success_without_cached_executable_is_not_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "current_platform", lambda: MACOS)
    cli_file(tmp_path)
    monkeypatch.setattr(browser, "run_install_command", lambda *args, **kwargs: None)
    with pytest.raises(browser.ToolchainError, match="without a usable cached"):
        browser.complete(tmp_path)


def test_partial_npm_install_does_not_fetch_an_unlocked_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "current_platform", lambda: MACOS)
    monkeypatch.setattr(
        browser, "run_install_command", lambda *args, **kwargs: pytest.fail("download")
    )
    with pytest.raises(browser.ToolchainError, match="Puppeteer installation is incomplete"):
        browser.complete(tmp_path)


def test_timed_out_download_is_not_restarted(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "current_platform", lambda: WINDOWS)
    cli_file(tmp_path)

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1800)

    monkeypatch.setattr(browser, "run_install_command", timeout)
    with pytest.raises(browser.ToolchainError, match="child processes have stopped"):
        browser.complete(tmp_path)
