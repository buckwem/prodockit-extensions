# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Low-level harness seams and platform edge cases used by ``pdk boot``."""

from __future__ import annotations

import io
import subprocess
import sys
import types
import urllib.error
from dataclasses import replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest

import prodockit.bootstrap.config as config_module
import prodockit.bootstrap.fetch as fetch_module
import prodockit.bootstrap.model as model_module
from prodockit.bootstrap import (
    BootstrapConfig,
    BootstrapConfigError,
    SubprocessRunner,
    UnsupportedHostError,
    authenticate_sudo,
    connection_problem,
    contacts_host,
    current_platform,
    forget_contacts,
    load,
    needs_sudo,
    refresh_windows_path,
    save,
)
from prodockit.bootstrap.fetch import Fetched
from prodockit.bootstrap.model import HOSTS, MACOS, UBUNTU, WINDOWS, CommandResult
from prodockit.bootstrap.surrey import Assessment, namespace_for, project_name_for


@pytest.mark.parametrize(
    ("reported", "expected"),
    [("darwin", MACOS), ("linux", UBUNTU), ("linux2", UBUNTU), ("win32", WINDOWS)],
)
def test_current_platform_covers_every_supported_runtime_name(
    monkeypatch: pytest.MonkeyPatch, reported: str, expected: str
) -> None:
    monkeypatch.setattr(sys, "platform", reported)

    assert current_platform() == expected


def test_current_platform_refuses_an_unknown_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "plan9")

    with pytest.raises(UnsupportedHostError, match="plan9"):
        current_platform()


def test_forget_contacts_is_a_no_op_without_a_counter() -> None:
    forget_contacts(SimpleNamespace(contacts=None))


def test_empty_command_does_not_contact_the_host() -> None:
    assert contacts_host([]) is False


@pytest.mark.parametrize(
    ("os_name", "environment", "suffix"),
    [
        ("posix", {"XDG_CONFIG_HOME": "/tmp/xdg"}, "/tmp/xdg/prodockit/bootstrap.toml"),
        ("posix", {}, "/home/ada/.config/prodockit/bootstrap.toml"),
        ("nt", {"APPDATA": "/tmp/roaming"}, "/tmp/roaming/prodockit/bootstrap.toml"),
        ("nt", {}, "/home/ada/AppData/Roaming/prodockit/bootstrap.toml"),
    ],
)
def test_legacy_config_path_covers_platform_defaults_and_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
    os_name: str,
    environment: dict[str, str],
    suffix: str,
) -> None:
    monkeypatch.setattr(config_module.os, "name", os_name)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    path_class = PureWindowsPath if os_name == "nt" else PurePosixPath
    monkeypatch.setattr(config_module, "Path", path_class)

    path = config_module.user_config_path(path_class("/home/ada"))

    assert str(path).replace("\\", "/") == suffix


def test_load_wraps_a_filesystem_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "answers.toml"
    path.touch()
    monkeypatch.setattr(
        Path, "read_text", lambda self, **kwargs: (_ for _ in ()).throw(OSError("denied"))
    )

    with pytest.raises(BootstrapConfigError, match=r"could not read.*denied"):
        load(path)


def test_save_wraps_a_filesystem_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "answers.toml"
    monkeypatch.setattr(
        Path, "write_text", lambda self, text, **kwargs: (_ for _ in ()).throw(OSError("full"))
    )

    with pytest.raises(BootstrapConfigError, match=r"could not write.*full"):
        save(path, BootstrapConfig())


class _Answer:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *ignored) -> None:  # type: ignore[no-untyped-def]
        return None

    def read(self) -> bytes:
        return self.body


def _opener(answer):  # type: ignore[no-untyped-def]
    return SimpleNamespace(open=lambda url, timeout: answer)


def test_fetch_returns_a_successful_response_and_replaces_bad_utf8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fetch_module.urllib.request,
        "build_opener",
        lambda handler: _opener(_Answer(200, b"ok\xff")),
    )

    assert fetch_module.fetch("https://example.test") == Fetched(200, "ok\ufffd")


def test_fetch_preserves_an_http_error_as_a_host_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = urllib.error.HTTPError(
        "https://example.test", 404, "missing", {}, io.BytesIO(b"not here")
    )

    def raise_refusal(url, timeout):  # type: ignore[no-untyped-def]
        raise refused

    monkeypatch.setattr(
        fetch_module.urllib.request,
        "build_opener",
        lambda handler: SimpleNamespace(open=raise_refusal),
    )

    assert fetch_module.fetch("https://example.test") == Fetched(404, "not here")


@pytest.mark.parametrize(
    "error", [urllib.error.URLError("offline"), OSError("down"), ValueError("bad")]
)
def test_fetch_returns_none_when_no_answer_was_obtained(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fail(url, timeout):  # type: ignore[no-untyped-def]
        raise error

    monkeypatch.setattr(
        fetch_module.urllib.request,
        "build_opener",
        lambda handler: SimpleNamespace(open=fail),
    )

    assert fetch_module.fetch("not a usable URL") is None


def test_redirect_handler_keeps_the_redirect_as_the_answer() -> None:
    assert fetch_module._KeepRedirects().redirect_request(None, None, 302, "", {}, "next") is None


def test_subprocess_runner_reports_a_missing_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        model_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    assert SubprocessRunner().run(["missing"]) == CommandResult(127, stderr="missing: not found")


def test_subprocess_runner_reports_a_timeout_in_reader_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        model_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(["slow"], 12.8)),
    )

    result = SubprocessRunner().run(["slow"], timeout=12.8)

    assert result.returncode == 1
    assert "within 12 seconds" in result.stderr


def test_subprocess_runner_reports_other_process_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        model_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("cannot execute")),
    )

    assert SubprocessRunner().run(["broken"]) == CommandResult(1, stderr="cannot execute")


def test_subprocess_runner_normalises_none_output(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = subprocess.CompletedProcess(["tool"], 0, stdout=None, stderr=None)
    monkeypatch.setattr(model_module.subprocess, "run", lambda *args, **kwargs: completed)

    assert SubprocessRunner().run(["tool"]) == CommandResult(0, stdout="", stderr="")


def test_windows_pdkboot_runner_uses_system_ssh_for_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def run(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")

    monkeypatch.setattr(model_module.subprocess, "run", run)
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)

    SubprocessRunner(git_ssh_executable="C:/Windows/System32/OpenSSH/ssh.exe").run(
        ["git", "ls-remote", "origin"]
    )

    environment = seen["env"]
    assert isinstance(environment, dict)
    assert environment["GIT_SSH_COMMAND"] == (
        "C:/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes -o ConnectTimeout=10"
    )


def test_pdkboot_windows_replaces_an_ssh_override_that_bypasses_its_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def run(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")

    monkeypatch.setattr(model_module.subprocess, "run", run)
    monkeypatch.setenv("GIT_SSH_COMMAND", "my-ssh-wrapper")

    SubprocessRunner(git_ssh_executable="C:/Windows/System32/OpenSSH/ssh.exe").run(
        ["git", "ls-remote", "origin"]
    )

    environment = seen["env"]
    assert isinstance(environment, dict)
    assert environment["GIT_SSH_COMMAND"] == (
        "C:/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes -o ConnectTimeout=10"
    )


def test_a_missing_working_directory_is_not_reported_as_a_missing_command(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "project-that-was-not-cloned"

    result = SubprocessRunner().run(["git", "status"], cwd=str(missing))

    assert result.returncode == 127
    assert str(missing) in result.stderr
    assert "working directory does not exist" in result.stderr
    assert "git: not found" not in result.stderr


@pytest.mark.parametrize(("returncode", "expected"), [(0, True), (1, False)])
def test_sudo_authentication_returns_the_process_outcome(
    monkeypatch: pytest.MonkeyPatch, returncode: int, expected: bool
) -> None:
    completed = subprocess.CompletedProcess(["sudo", "-v"], returncode)
    monkeypatch.setattr(model_module.subprocess, "run", lambda *args, **kwargs: completed)

    assert authenticate_sudo() is expected


def test_sudo_authentication_failure_to_start_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        model_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no sudo")),
    )

    assert authenticate_sudo() is False


def test_sudo_scan_ignores_empty_commands() -> None:
    assert needs_sudo([[], ["echo", "safe"]]) is False


def test_supported_hosts_message_handles_one_host(monkeypatch: pytest.MonkeyPatch) -> None:
    only = next(iter(HOSTS.values()))
    monkeypatch.setattr(model_module, "HOSTS", {only.key: only})

    assert model_module._supported_hosts() == (
        f"prodockit bootstrap currently implements {only.hostname}"
    )


def test_declared_but_unsupported_host_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    supported = next(iter(HOSTS.values()))
    unsupported = replace(
        supported,
        key="future",
        hostname="gitlab.future.test",
        supported=False,
    )
    monkeypatch.setattr(
        model_module,
        "HOSTS",
        {supported.key: supported, unsupported.key: unsupported},
    )

    assert model_module.host_problem(unsupported.hostname) == (
        "gitlab.future.test is declared but not yet supported - "
        f"prodockit bootstrap currently implements {supported.hostname} only"
    )


def test_default_socket_connector_is_exercised_and_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered: list[tuple[tuple[str, int], float]] = []
    closed: list[bool] = []

    class Connection:
        def __enter__(self):
            closed.append(False)
            return self

        def __exit__(self, *ignored) -> None:  # type: ignore[no-untyped-def]
            closed[-1] = True

    def connect(address, timeout):  # type: ignore[no-untyped-def]
        entered.append((address, timeout))
        return Connection()

    monkeypatch.setattr(model_module.socket, "create_connection", connect)

    assert connection_problem("github.com", timeout=0.25) is None
    assert entered == [(("github.com", 22), 0.25)]
    assert closed == [True]


def _fake_winreg(values: dict[str, str | OSError | dict[str, str | OSError]]):
    class Key:
        def __init__(self, subkey: str) -> None:
            self.subkey = subkey

        def __enter__(self):
            return self

        def __exit__(self, *ignored) -> None:  # type: ignore[no-untyped-def]
            return None

    def open_key(root, subkey):  # type: ignore[no-untyped-def]
        return Key(subkey)

    def query(key, name):  # type: ignore[no-untyped-def]
        value = values[key.subkey]
        if isinstance(value, dict):
            value = value.get(name, OSError("missing"))
        if isinstance(value, OSError):
            raise value
        return value, 1

    return types.SimpleNamespace(
        HKEY_LOCAL_MACHINE=object(),
        HKEY_CURRENT_USER=object(),
        OpenKey=open_key,
        QueryValueEx=query,
    )


def test_windows_path_refresh_returns_none_when_registry_has_no_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _fake_winreg(
        {
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment": OSError("missing"),
            "Environment": {"Path": ""},
        }
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", fake)

    assert refresh_windows_path() is None


def test_windows_path_refresh_merges_machine_and_user_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ``refresh_windows_path`` intentionally changes the process environment.
    # Register the existing value with monkeypatch so this platform simulation
    # cannot remove git, pandoc and the other tools from later tests' PATH.
    monkeypatch.setenv("PATH", model_module.os.environ.get("PATH", ""))
    fake = _fake_winreg(
        {
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment": r"C:\Tools",
            "Environment": {
                "Path": r"C:\Users\Ada\bin",
                "WEASYPRINT_DLL_DIRECTORIES": r"C:\msys64\ucrt64\bin",
            },
        }
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", fake)

    merged = refresh_windows_path()

    assert merged == r"C:\Tools:C:\Users\Ada\bin"
    assert model_module.os.environ["PATH"] == merged
    assert model_module.os.environ["WEASYPRINT_DLL_DIRECTORIES"] == r"C:\msys64\ucrt64\bin"


def test_invalid_surrey_stage_choice_is_rejected() -> None:
    with pytest.raises(ValueError, match="not one of the offered stages"):
        Assessment.at_stage("9")


def test_unassessed_surrey_namespace_ignores_course_and_year() -> None:
    assert namespace_for("COMM058", "AB1234", Assessment.not_assessed(), "2026") == "ab1234"


def test_assessed_surrey_names_work_without_an_optional_year() -> None:
    assessment = Assessment.at_stage("1")

    assert namespace_for("COMM058", "AB1234", assessment) == "assessment-comm058"
    assert project_name_for("COMM058", "AB1234", assessment=assessment) == "report-comm058-ab1234"
