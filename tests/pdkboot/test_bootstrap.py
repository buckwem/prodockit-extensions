# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for `prodockit bootstrap`'s stage model, config and hosts.

The point of the design is that none of this needs anything installed: a
stage returns the commands that *would* set something up, so a test
asserts on those commands. That is what lets all three platforms' logic
be checked from whichever one the suite happens to run on
(prodockit-extensions#217).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path, PurePath

import pytest

import prodockit as prodockit_module
from prodockit import __version__
from prodockit.bootstrap import (
    HOSTS,
    PROMPTS,
    STAGES,
    BootstrapConfig,
    BootstrapConfigError,
    CheckResult,
    CommandResult,
    Plan,
    Status,
    UnsupportedHostError,
    build_context,
    check_all,
    config_path,
    default_for,
    load,
    missing_keys,
    plan_all,
    save,
)
from prodockit.bootstrap.model import GITHUB_COM, MACOS, SURREY_GITLAB, UBUNTU, WINDOWS
from prodockit.bootstrap.stages import (
    DEFAULT_CSL_STYLE,
    PANDOC_VERSION,
    PDF_FONT_CASKS,
    PDF_FONT_PACKAGES,
    PUBLIC_KEY_MARKER,
    PUPPETEER_SKIP_VAR,
    VSCODE_EXTENSIONS,
)


class FakeRunner:
    """A runner that answers from a table instead of running anything.

    Keyed on the whole command joined, any distinctive fragment of it, or
    the first word - so a test can be as specific as it needs. The
    fragment case exists because some commands carry a `tmp_path` no test
    can spell out in advance (`git -C /tmp/.../project config --local
    user.email`); the longest matching key wins, so a specific fragment
    always beats a general one. Records every command it was asked to
    run, which is what the plan assertions check.
    """

    def __init__(self, responses: dict[str, CommandResult] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[list[str]] = []
        self.cwds: list[str | None] = []
        self.timeouts: list[float | None] = []
        self.captures: list[bool] = []

    def run(
        self,
        command: Sequence[str],
        cwd: str | None = None,
        timeout: float | None = None,
        capture: bool = True,
    ) -> CommandResult:
        self.timeouts.append(timeout)
        self.captures.append(capture)
        self.calls.append(list(command))
        self.cwds.append(cwd)
        joined = " ".join(command)
        if joined in self.responses:
            return self.responses[joined]
        fragments = [key for key in self.responses if key in joined]
        if fragments:
            return self.responses[max(fragments, key=len)]
        if command[0] in self.responses:
            return self.responses[command[0]]
        return CommandResult(returncode=127, stderr="not found")


#: What `ssh-add -l` prints for a loaded key, and what `ssh-keygen -lf`
#: prints for the same one - the fingerprint has to match between them.
LOADED_FINGERPRINT = "SHA256:AAAAfingerprintAAAA"
AGENT_RESPONSES = {
    "ssh-add -l": CommandResult(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)"),
    "ssh-keygen -lf": CommandResult(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)"),
}


def _before_the_clone(machine: dict[str, CommandResult]) -> dict[str, CommandResult]:
    """`_ready_machine`, wound back to where the clone decision is live.

    The clone-source stage settles itself once `origin` names the
    reader's own project (prodockit-extensions#368), so a fixture that
    wants the *question* has to sit before that is true: nothing cloned
    yet, and so no origin to read.
    """
    return machine | {"remote get-url origin": CommandResult(2, stderr="No such remote")}


def _ready_machine(tmp_path: Path) -> dict[str, CommandResult]:
    """A machine on which every stage is satisfied.

    One place rather than per-test, so adding a stage breaks this once
    and visibly instead of leaving tests passing against a machine the
    stage list no longer describes.
    """
    (tmp_path / ".ssh").mkdir(exist_ok=True)
    for suffix in ("", ".pub"):
        (tmp_path / ".ssh" / f"id_ed25519_gitlab{suffix}").write_text("k", encoding="utf-8")
    _write_ssh_config(tmp_path)
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True, exist_ok=True)
    for toolchain in ("mermaid", "mathjax"):
        (project / "tools" / toolchain / "node_modules").mkdir(parents=True, exist_ok=True)
    (project / "requirements.txt").write_text("zensical\n", encoding="utf-8")
    venv_python = project / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("", encoding="utf-8")
    (venv_python.parent / "activate").write_text(
        "# Added by pdkboot for WeasyPrint\n", encoding="utf-8"
    )
    (project / "harvard-cite-them-right.csl").write_text("<style/>", encoding="utf-8")
    pinned = project / "tools" / "mathjax" / "node_modules" / "mathjax-full" / "es5"
    pinned.mkdir(parents=True, exist_ok=True)
    (pinned / "tex-svg-full.js").write_text("BUNDLE", encoding="utf-8")
    vendor = project / "docs" / "javascripts" / "vendor" / "mathjax"
    vendor.mkdir(parents=True, exist_ok=True)
    (vendor / "tex-svg-full.js").write_text("BUNDLE", encoding="utf-8")
    (project / "docs" / "javascripts" / "mathjax.js").write_text(
        "window.MathJax={}", encoding="utf-8"
    )
    (project / ".vscode").mkdir(exist_ok=True)
    (project / ".vscode" / "settings.json").write_text(
        '{"files.associations": {"*.md": "python-markdown"}}', encoding="utf-8"
    )
    save(tmp_path / "b.toml", _config())
    return {
        # Pushed means the commit here is the commit there - the same
        # sha from both sides, which is what the stage compares (#423).
        "rev-parse HEAD": CommandResult(0, "abc123\n"),
        # prodockit is running from an environment of its own, and that
        # environment can build another - stage 1 (#381).
        "sys.base_prefix": CommandResult(0, "True"),
        "import ensurepip, venv": CommandResult(0),
        "code --list-extensions": CommandResult(0, "\n".join(VSCODE_EXTENSIONS)),
        "code": CommandResult(0),
        "git --version": CommandResult(0, "git version 2.43.0"),
        "git config --global user.name": CommandResult(0, "Ada\n"),
        "git config --global user.email": CommandResult(0, "a@b.c\n"),
        "config --global core.sshCommand": CommandResult(
            0, "C:/Windows/System32/OpenSSH/ssh.exe\n"
        ),
        "ssh": CommandResult(1, stderr="Welcome to GitLab, @al01234!"),
        "git": CommandResult(0, "git@gitlab.surrey.ac.uk:comm058-2026/report-al01234.git\n"),
        "prodockit sync-repo --check": CommandResult(0),
        "config --local user.name": CommandResult(0, "Ada Lovelace\n"),
        "config --local user.email": CommandResult(0, "al01234@surrey.ac.uk\n"),
        "pandoc": CommandResult(0, "pandoc 3.10.1"),
        "node": CommandResult(0, "v22.14.0\n"),
        "npm": CommandResult(0, "10.9.2\n"),
        "import zensical": CommandResult(0),
        "fc-list": CommandResult(0, "Inter\nJetBrains Mono\nDejaVu Sans\n"),
        "config core.fileMode": CommandResult(0, "false\n"),
        # A finished project has nothing uncommitted and something on the
        # remote - without both, the first-push stage is rightly not done.
        "glab --version": CommandResult(0, "glab 1.0.0"),
        "glab auth status": CommandResult(0, "Logged in"),
        "gh --version": CommandResult(0, "gh version 2.0.0"),
        "gh auth status": CommandResult(0, "Logged in"),
        "status --porcelain": CommandResult(0, ""),
        "ls-remote origin HEAD": CommandResult(0, "abc123\tHEAD\n"),
        "import weasyprint": CommandResult(0),
        **AGENT_RESPONSES,
    }


def _write_ssh_config(
    tmp_path: Path,
    key: str = "~/.ssh/id_ed25519_gitlab",
    *,
    persist: bool = True,
) -> None:
    """A ~/.ssh/config that points Surrey's GitLab at the key.

    Needed by any test that expects the SSH stages to be satisfied:
    without the stanza ssh never offers the key, which is the whole of
    prodockit-extensions#239.

    `persist` writes the directives that keep the key in the agent past
    this session. On by default because a machine missing them is not a
    finished one - it works today and fails after the next reboot
    (prodockit-extensions#303) - so a test wanting that state says so.
    """
    keeps_loaded = "    AddKeysToAgent yes\n    UseKeychain yes\n" if persist else ""
    (tmp_path / ".ssh").mkdir(exist_ok=True)
    (tmp_path / ".ssh" / "config").write_text(
        f"Host gitlab.surrey.ac.uk\n    HostName gitlab.surrey.ac.uk\n"
        f"    User git\n    IdentityFile {key}\n{keeps_loaded}",
        encoding="utf-8",
    )


def _config(**overrides: str) -> BootstrapConfig:
    base = {
        "full_name": "Ada Lovelace",
        "email": "al01234@surrey.ac.uk",
        "username": "al01234",
        "host": "surrey",
        "namespace": "comm058-2026",
        "project_name": "report-al01234",
        "project_dir": "~/GitLab/report-al01234",
    }
    base.update(overrides)
    return BootstrapConfig(**base)  # type: ignore[arg-type]


def _looks_like_vscode_app(path: Path) -> bool:
    text = str(path)
    return "Visual Studio Code" in text or text.endswith(("/usr/share/code", "/snap/code"))


def _answers(status: int, body: str = ""):
    """A `fetch` that answers every URL the same way.

    The probes ask a URL rather than run `curl` (prodockit-extensions#449),
    so this is the seam a test describes a host through - the same role
    `FakeRunner` plays for commands.
    """
    from prodockit.bootstrap.fetch import Fetched

    return lambda url, timeout=20.0: Fetched(status, body)


def _answers_by_url(**routes):
    """A `fetch` keyed on a fragment of the URL.

    The Pages stage asks two different things - the repository's metadata
    and the published site - and they answer differently on a private
    repository, which is the whole of #374.
    """
    from prodockit.bootstrap.fetch import Fetched

    def answer(url, timeout=20.0):
        for fragment, (status, body) in routes.items():
            if fragment.replace("_", ".") in url or fragment in url:
                return Fetched(status, body)
        return None

    return answer


def _ready_fetch():
    """The network half of `_ready_machine`: everything answers.

    A machine on which every stage is satisfied includes a site that is
    published, and since #449 that is not something a runner can say -
    the probe asks a URL. Kept beside `_ready_machine` so the two halves
    of "ready" are changed together (#476).
    """
    return _answers(200, '{"has_pages": true}')


def _unreachable(url, timeout=20.0):
    """A `fetch` that could not ask at all - no route, no name, no listener.

    `None` is not a status. It is the default here for the same reason
    `FakeRunner` answers `127 not found`: a test that has not said what a
    host does should not be quietly given a working one.
    """
    return None


def _context(
    tmp_path: Path,
    *,
    platform: str = MACOS,
    runner: FakeRunner | None = None,
    vscode_app: bool = False,
    fetch=None,
    **cfg,
):
    """A context describing a machine, never reading this one.

    `vscode_app` says whether the VS Code *application* is installed -
    separate from whether the `code` command is on PATH, which the runner
    answers. Defaults to absent so a test states it when it matters.
    """
    return build_context(
        _config(**cfg),
        runner=runner or FakeRunner(),
        platform=platform,
        home=tmp_path,
        # Only the VS Code application paths are described; everything
        # else is a real path under tmp_path and answers for itself.
        exists=lambda path: vscode_app if _looks_like_vscode_app(path) else path.exists(),
        fetch=fetch or _unreachable,
        pdkboot=True,
    )


# ---------------------------------------------------------------------------
# Hosts
# ---------------------------------------------------------------------------


def test_key_suffix_matches_the_documented_filename() -> None:
    """Regression: the key file is named for the *kind* of host, not the
    instance. The User Guide's own `ssh-keygen -f` line writes
    `id_ed25519_gitlab` for Surrey's instance, so keying the filename on
    `host.key` ("surrey") reported a missing key on a machine that had a
    working one - and would then have created a second key beside it.
    Found by running `--check` against a real machine.
    """
    assert SURREY_GITLAB.key == "surrey"
    assert SURREY_GITLAB.key_suffix == "gitlab"
    assert HOSTS["gitlab"].key_suffix == "gitlab"
    assert GITHUB_COM.key_suffix == "github"


def test_the_keypair_check_looks_where_the_guide_says_to_create_it(tmp_path: Path) -> None:
    """The other half of the regression above: the record being right is
    no use if the check reads the wrong field off it. A key created by
    following the User Guide verbatim must be found."""
    (tmp_path / ".ssh").mkdir()
    for suffix in ("", ".pub"):
        (tmp_path / ".ssh" / f"id_ed25519_gitlab{suffix}").write_text("k", encoding="utf-8")
    context = _context(tmp_path)
    result = next(s for s in STAGES if s.id == "ssh-key").check(context)
    assert result.status is Status.OK
    assert result.detail.endswith("id_ed25519_gitlab")


def test_declared_but_unsupported_hosts_are_refused_clearly() -> None:
    """Every declared host is supported now. What is still refused is a
    host with no record at all - a self-hosted instance of either family
    - and that is the case worth keeping a message for (#361)."""
    with pytest.raises(UnsupportedHostError) as exc_info:
        build_context(_config(host="gitlab.example.edu"))
    assert "self-hosted" in str(exc_info.value)


def test_an_unknown_host_names_the_ones_that_exist() -> None:
    with pytest.raises(UnsupportedHostError) as exc_info:
        build_context(_config(host="bitbucket"))
    assert "surrey" in str(exc_info.value)


def test_remote_url_shape_is_the_same_for_every_host() -> None:
    for host in HOSTS.values():
        assert host.remote_url("group", "proj") == f"git@{host.hostname}:group/proj.git"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap.toml"
    save(path, _config())
    assert load(path) == _config()


def test_a_missing_config_is_defaults_not_an_error(tmp_path: Path) -> None:
    assert load(tmp_path / "absent.toml") == BootstrapConfig()


def test_a_malformed_line_names_the_file_and_line(tmp_path: Path) -> None:
    """A hand-edited config that silently reverted to defaults would
    re-prompt for everything with no explanation - the exact silent
    failure this project keeps finding elsewhere."""
    path = tmp_path / "bootstrap.toml"
    path.write_text('full_name = "Ada"\nemail = no-quotes-here\n', encoding="utf-8")
    with pytest.raises(BootstrapConfigError) as exc_info:
        load(path)
    assert "bootstrap.toml:2" in str(exc_info.value)


def test_an_unknown_key_is_ignored_rather_than_fatal(tmp_path: Path) -> None:
    """A config written by a newer prodockit should still start on an
    older one."""
    path = tmp_path / "bootstrap.toml"
    path.write_text('full_name = "Ada"\nfuture_setting = "x"\n', encoding="utf-8")
    assert load(path).full_name == "Ada"


def test_the_saved_file_warns_against_putting_secrets_in_it(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap.toml"
    save(path, _config())
    assert "Never put a password, token or passphrase" in path.read_text(encoding="utf-8")


def test_config_path_follows_each_platform_convention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prodockit.bootstrap.config import user_config_path

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert user_config_path(tmp_path) == tmp_path / ".config" / "prodockit" / "bootstrap.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert user_config_path(tmp_path).parent.parent == tmp_path / "xdg"


def test_a_config_belongs_to_the_directory_it_was_answered_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#373: one config per user meant one project.

    Setting up a second one overwrote the answers for the first - the
    namespace, the project name, the directory it lives in - so the
    original could not be re-checked without answering everything again.
    """
    from prodockit.bootstrap import LOCAL_CONFIG_NAME

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    first, second = tmp_path / "one", tmp_path / "two"
    for directory in (first, second):
        directory.mkdir()

    assert config_path(tmp_path, cwd=first) == first / LOCAL_CONFIG_NAME
    assert config_path(tmp_path, cwd=second) == second / LOCAL_CONFIG_NAME, (
        "two directories, two configs - neither reaches into the other"
    )


def test_the_local_config_is_kept_out_of_the_reader_s_repository(tmp_path: Path) -> None:
    """The first-push stage commits with `git add -A`, on the reasoning
    that everything in the project was put there by bootstrap.

    #373 puts the reader's own name, email and username in that same
    directory, so that reasoning stopped holding - and the repository it
    would be committed to is one a student submits.
    """
    from prodockit.bootstrap.config import keep_out_of_git

    project = tmp_path / "report"
    (project / ".git").mkdir(parents=True)
    config = project / ".pdk-bootstrap.toml"
    config.write_text("", encoding="utf-8")

    assert keep_out_of_git(config) is True
    ignore = (project / ".gitignore").read_text(encoding="utf-8")
    assert ".pdk-bootstrap.toml" in ignore
    assert "your own answers" in ignore.lower(), "say why, for whoever reads it later"

    # Idempotent: a second run adds nothing.
    assert keep_out_of_git(config) is False
    assert (project / ".gitignore").read_text(encoding="utf-8") == ignore


def test_no_gitignore_is_written_where_there_is_no_repository(tmp_path: Path) -> None:
    """Nothing there can be swept into a commit, and writing a
    `.gitignore` into somebody's home directory to solve a problem they
    do not have would be worse than the problem."""
    from prodockit.bootstrap.config import keep_out_of_git

    config = tmp_path / ".pdk-bootstrap.toml"
    config.write_text("", encoding="utf-8")

    assert keep_out_of_git(config) is False
    assert not (tmp_path / ".gitignore").exists()


def test_an_existing_user_config_is_still_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing has to be moved. A setup already answered keeps working,
    and only a directory that has its own file stops consulting it."""
    from prodockit.bootstrap import LOCAL_CONFIG_NAME
    from prodockit.bootstrap.config import user_config_path

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    legacy = user_config_path(tmp_path)
    legacy.parent.mkdir(parents=True)
    legacy.write_text("", encoding="utf-8")
    here = tmp_path / "project"
    here.mkdir()

    assert config_path(tmp_path, cwd=here) == legacy, "read where it already is"

    # ...until this directory has one of its own, which then wins.
    local = here / LOCAL_CONFIG_NAME
    local.write_text("", encoding="utf-8")
    assert config_path(tmp_path, cwd=here) == local


def test_project_dir_expands_a_leading_tilde(tmp_path: Path) -> None:
    config = _config(project_dir="~/GitLab/report")
    assert config.resolved_project_dir(tmp_path) == tmp_path / "GitLab" / "report"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def test_git_installed_but_unconfigured_is_wrong_not_missing(tmp_path: Path) -> None:
    """Telling a reader to install git they already have sends them the
    wrong way entirely - that is why `WRONG` exists separately."""
    runner = FakeRunner(
        {
            "git --version": CommandResult(0, "git version 2.43.0"),
            "git config --global user.name": CommandResult(0, "Ada\n"),
            "git config --global user.email": CommandResult(1, ""),
        }
    )
    context = _context(tmp_path, runner=runner)
    result = next(s for s in STAGES if s.id == "git").check(context)
    assert result.status is Status.WRONG
    assert "user.email" in result.detail


def test_windows_git_uses_the_agent_backed_system_ssh(tmp_path: Path) -> None:
    """Git for Windows bundles another ssh.exe which cannot use the
    Windows service agent configured by pdkboot."""
    machine = _ready_machine(tmp_path)
    machine["config --global core.sshCommand"] = CommandResult(1)
    stage = next(s for s in STAGES if s.id == "git")
    context = _context(tmp_path, platform=WINDOWS, runner=FakeRunner(machine))

    result = stage.check(context)
    commands = [" ".join(command) for command in stage.plan(context).commands]

    assert result.status is Status.WRONG
    assert "Windows OpenSSH" in result.detail
    assert any(
        "core.sshCommand C:/Windows/System32/OpenSSH/ssh.exe" in command for command in commands
    )


def test_ssh_success_is_read_from_the_greeting_not_the_exit_code(tmp_path: Path) -> None:
    """`ssh -T` against a git host exits non-zero even when the key works -
    there is no shell to give you. Reading the exit code would report every
    correctly configured machine as broken.
    """
    _write_keypair(tmp_path)
    runner = FakeRunner(
        _agent(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)")
        | {"ssh": CommandResult(1, stderr="Welcome to GitLab, @al01234!")}
    )
    context = _context(tmp_path, runner=runner)
    result = next(s for s in STAGES if s.id == "ssh-upload").check(context)
    assert result.status is Status.OK


def test_a_rejected_key_is_missing_not_merely_unconfirmed(tmp_path: Path) -> None:
    _write_keypair(tmp_path)
    runner = FakeRunner(
        _agent(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)")
        | {"ssh": CommandResult(255, stderr="Permission denied (publickey).")}
    )
    context = _context(tmp_path, runner=runner)
    assert next(s for s in STAGES if s.id == "ssh-upload").check(context).status is Status.MISSING


def test_half_a_keypair_is_wrong(tmp_path: Path) -> None:
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "id_ed25519_gitlab").write_text("private", encoding="utf-8")
    context = _context(tmp_path)
    result = next(s for s in STAGES if s.id == "ssh-key").check(context)
    assert result.status is Status.WRONG


def test_node_without_npm_is_wrong(tmp_path: Path) -> None:
    """The signature of Ubuntu's own nodejs package, or a NodeSource install
    whose `curl` line failed - a real failure this family has already hit."""
    runner = FakeRunner({"node": CommandResult(0, "v22.14.0\n")})
    context = _context(tmp_path, runner=runner)
    result = next(s for s in STAGES if s.id == "node").check(context)
    assert result.status is Status.WRONG
    assert "npm" in result.detail


def test_node_older_than_the_builds_use_is_wrong(tmp_path: Path) -> None:
    runner = FakeRunner(
        {"node": CommandResult(0, "v18.19.0\n"), "npm": CommandResult(0, "10.2.3\n")}
    )
    context = _context(tmp_path, runner=runner)
    assert next(s for s in STAGES if s.id == "node").check(context).status is Status.WRONG


def test_stages_needing_project_details_report_unknown_not_missing(tmp_path: Path) -> None:
    """Regression: with no config these built a URL out of empty strings and
    reported `git@gitlab.surrey.ac.uk:/.git is not reachable`, which tells a
    first-time reader nothing except that something is broken - and nothing
    is. Found by running `--check` on a machine with no config.
    """
    context = _context(tmp_path, namespace="", project_name="", project_dir="")
    reports = {r.stage.id: r.result for r in check_all(context)}
    for stage_id in ("clone", "own-project", "remote"):
        assert reports[stage_id].status is Status.UNKNOWN, stage_id
        assert "needs" in reports[stage_id].detail


def test_extensions_reports_which_are_missing(tmp_path: Path) -> None:
    present = "\n".join(VSCODE_EXTENSIONS[:-1])
    runner = FakeRunner({"code --list-extensions": CommandResult(0, present)})
    context = _context(tmp_path, runner=runner)
    result = next(s for s in STAGES if s.id == "extensions").check(context)
    assert result.status is Status.WRONG
    assert VSCODE_EXTENSIONS[-1] in result.detail


# ---------------------------------------------------------------------------
# Plans - the whole point: every platform, from any platform
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "platform,expected",
    [
        (MACOS, "brew"),
        (UBUNTU, "apt"),
        (WINDOWS, "winget"),
    ],
)
def test_every_platforms_install_plan_is_generated_from_any_platform(
    tmp_path: Path, platform: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason the runner is injected: this asserts on Ubuntu's and
    Windows' commands while running on whatever the suite runs on, with
    nothing installed and no network.

    `_vscode_app_installed` is pinned false because it reads the real
    filesystem rather than going through the runner - so without this the
    result depends on whether the machine running the tests happens to
    have VS Code, which is precisely the coupling the injected runner
    exists to remove. It caught this test out once already.
    """
    context = _context(tmp_path, platform=platform, vscode_app=False)
    plan = next(s for s in STAGES if s.id == "vscode").plan(context)
    flat = " ".join(" ".join(command) for command in plan.commands)
    assert expected in flat


def test_git_plan_skips_reinstalling_an_already_installed_git(tmp_path: Path) -> None:
    """A rerun repairing unset identity must not reinstall git underneath a
    working one."""
    runner = FakeRunner({"git": CommandResult(0, "git version 2.43.0")})
    context = _context(tmp_path, runner=runner)
    plan = next(s for s in STAGES if s.id == "git").plan(context)
    flat = " ".join(" ".join(command) for command in plan.commands)
    assert "brew" not in flat
    assert "user.email" in flat


def test_git_plan_skips_winget_when_git_is_installed_but_off_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prodockit.bootstrap import stages as stage_module

    installed = tmp_path / "Program Files" / "Git" / "cmd" / "git.exe"
    installed.parent.mkdir(parents=True)
    installed.write_text("", encoding="utf-8")
    monkeypatch.setattr(stage_module, "_GIT_APP_PATHS", {WINDOWS: (str(installed),)})
    context = _context(
        tmp_path,
        platform=WINDOWS,
        runner=FakeRunner({"git --version": CommandResult(127, stderr="not found")}),
    )

    plan = next(s for s in STAGES if s.id == "git").plan(context)

    assert not any(command[0] == "winget" for command in plan.commands)
    assert all(command[0] == str(installed) for command in plan.commands)


def test_pdkboot_winget_installs_never_upgrade_or_prompt_implicitly(tmp_path: Path) -> None:
    plan = next(s for s in STAGES if s.id == "vscode").plan(_context(tmp_path, platform=WINDOWS))
    command = plan.commands[0]

    assert command[:4] == ["winget", "install", "--id", "Microsoft.VisualStudioCode"]
    assert "--no-upgrade" in command
    assert "--silent" in command
    assert "--disable-interactivity" in command


def test_the_two_browser_stages_guide_and_leave_verifying_to_the_check(
    tmp_path: Path,
) -> None:
    """Guide-and-verify: the instructions are what a human does, and the
    stage's own *check* is how bootstrap confirms it worked.

    The verification must not also be a plan command. Applying a stage
    re-runs its check anyway, so a probe in `commands` buys nothing - and
    it costs the run, because a command is judged by its exit code. `ssh
    -T` against a git host exits non-zero even on success, so the probe
    read as a failed command and stopped the run on a machine whose key
    had simply not been uploaded yet (#234)."""
    context = _context(tmp_path)
    for stage_id in ("ssh-upload", "own-project"):
        plan = next(s for s in STAGES if s.id == stage_id).plan(context)
        assert plan.instructions, stage_id
        assert not plan.commands, (
            f"{stage_id} must not run its own verification as a command - "
            f"applying re-checks the stage, and a non-zero probe ends the run"
        )
        assert plan.is_manual, stage_id


def test_no_ssh_config_at_all_is_missing(tmp_path: Path) -> None:
    """prodockit-extensions#239: with no stanza, ssh offers its own
    defaults (`id_rsa`, `id_ed25519`), never tries `id_ed25519_gitlab`,
    and falls back to asking for a password - which reads exactly like a
    key the host has rejected, sending the reader to re-upload a key
    that was never the problem."""
    stage = next(s for s in STAGES if s.id == "ssh-config")
    result = stage.check(_context(tmp_path))

    assert result.status is Status.MISSING
    assert "does not exist" in result.detail


def test_a_config_without_this_host_is_missing(tmp_path: Path) -> None:
    """Somebody else's GitHub stanza does not help Surrey's GitLab."""
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "config").write_text(
        "Host github.com\n    IdentityFile ~/.ssh/id_ed25519_github\n", encoding="utf-8"
    )
    result = next(s for s in STAGES if s.id == "ssh-config").check(_context(tmp_path))

    assert result.status is Status.MISSING
    assert "no Host entry" in result.detail


def test_a_host_entry_pointing_at_the_wrong_key_is_wrong_not_missing(tmp_path: Path) -> None:
    """Present but unusable is exactly what WRONG is for - and telling
    somebody to add an entry they already have would send them to write
    a second one that ssh, which takes the first match, would ignore."""
    _write_ssh_config(tmp_path, key="~/.ssh/id_rsa")
    result = next(s for s in STAGES if s.id == "ssh-config").check(_context(tmp_path))

    assert result.status is Status.WRONG
    assert "does not point at" in result.detail


def test_a_hostname_in_a_comment_does_not_count(tmp_path: Path) -> None:
    """The stanza is parsed, not string-matched. "Is the hostname
    anywhere in the file?" is satisfied by the comment above somebody
    else's entry, and would report a config that does nothing as done."""
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "config").write_text(
        "# gitlab.surrey.ac.uk id_ed25519_gitlab - notes to self\n"
        "Host github.com\n    IdentityFile ~/.ssh/id_ed25519_github\n",
        encoding="utf-8",
    )
    result = next(s for s in STAGES if s.id == "ssh-config").check(_context(tmp_path))

    assert result.status is Status.MISSING


def test_a_stanza_ends_at_the_next_host_line(tmp_path: Path) -> None:
    """`Host` blocks run until the next `Host`/`Match`, so a key named
    under a *later* entry must not satisfy this one."""
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "config").write_text(
        "Host gitlab.surrey.ac.uk\n    User git\n"
        "Host other.example\n    IdentityFile ~/.ssh/id_ed25519_gitlab\n",
        encoding="utf-8",
    )
    result = next(s for s in STAGES if s.id == "ssh-config").check(_context(tmp_path))

    assert result.status is Status.WRONG, "the key belongs to the next host, not this one"


def test_a_matching_stanza_is_ok(tmp_path: Path) -> None:
    _write_ssh_config(tmp_path)
    result = next(s for s in STAGES if s.id == "ssh-config").check(_context(tmp_path))

    assert result.status is Status.OK
    assert "id_ed25519_gitlab" in result.detail


def test_the_config_stage_comes_before_the_upload(tmp_path: Path) -> None:
    """Ordering is the whole point. The upload stage checks itself with
    `ssh -T`, which cannot work until ssh knows which key to offer - so
    running the config stage afterwards would leave the reader staring at
    a rejected key with the fix two stages further down the list."""
    ids = [s.id for s in STAGES]

    assert ids.index("ssh-config") > ids.index("ssh-key"), "there must be a key to point at"
    assert ids.index("ssh-config") < ids.index("ssh-upload")


def test_the_plan_appends_and_never_rewrites(tmp_path: Path) -> None:
    """An ssh config is the reader's own file and may hold entries for
    hosts bootstrap knows nothing about, so the stanza is added to the
    end rather than the file being written."""
    plan = next(s for s in STAGES if s.id == "ssh-config").plan(_context(tmp_path))
    script = " ".join(" ".join(command) for command in plan.commands)

    assert ">>" in script, "appended"
    assert " > " not in script, "never truncated"
    assert "Host gitlab.surrey.ac.uk" in script
    assert "IdentityFile ~/.ssh/id_ed25519_gitlab" in script


def test_the_plan_tightens_permissions_on_the_key_and_config(tmp_path: Path) -> None:
    """ssh ignores a private key others can read - "Permissions 0644 are
    too open ... this private key will be ignored" - and then falls back
    to a password, which is the same symptom as having no config at
    all."""
    plan = next(s for s in STAGES if s.id == "ssh-config").plan(_context(tmp_path))
    chmods = [c for c in plan.commands if c[0] == "chmod"]

    assert len(chmods) == 2
    assert all(c[1] == "600" for c in chmods)
    assert any(c[2].endswith("config") for c in chmods)
    assert any(c[2].endswith("id_ed25519_gitlab") for c in chmods)


def test_an_existing_wrong_entry_is_explained_rather_than_edited(tmp_path: Path) -> None:
    """Rewriting somebody's ssh config underneath them is not something
    an installer should do unasked - and appending would be pointless
    anyway, since ssh takes the first match."""
    _write_ssh_config(tmp_path, key="~/.ssh/id_rsa")
    plan = next(s for s in STAGES if s.id == "ssh-config").plan(_context(tmp_path))

    assert not plan.commands, "an existing entry is for a human to edit"
    joined = "\n".join(plan.instructions)
    assert "already has a Host entry" in joined
    assert "IdentityFile ~/.ssh/id_ed25519_gitlab" in joined, "show what it should say"


def test_the_stanza_keeps_the_key_loaded_past_this_session(tmp_path: Path) -> None:
    """`IdentityFile` names the key; it does not put it in the agent.
    Without these two the machine works until the agent is next emptied
    and then fails blaming the key (#303)."""
    plan = next(s for s in STAGES if s.id == "ssh-config").plan(_context(tmp_path))
    script = " ".join(" ".join(command) for command in plan.commands)

    assert "AddKeysToAgent yes" in script, "load the key on first use"
    assert "UseKeychain yes" in script, "take the passphrase from the login keychain"


@pytest.mark.parametrize("platform", [UBUNTU, WINDOWS])
def test_usekeychain_is_never_written_off_macos(tmp_path: Path, platform: str) -> None:
    """Not a cosmetic difference. An OpenSSH that does not know the
    keyword rejects the entire config file rather than skipping the line,
    which would break every other host in it too."""
    plan = next(s for s in STAGES if s.id == "ssh-config").plan(
        _context(tmp_path, platform=platform)
    )
    script = " ".join(" ".join(command) for command in plan.commands)

    assert "UseKeychain" not in script, "Apple-only, and fatal elsewhere"
    assert "AddKeysToAgent yes" in script, "this one is ordinary OpenSSH"


def test_a_stanza_that_will_not_survive_a_reboot_is_reported(tmp_path: Path) -> None:
    """The state this laptop was found in: right key, no way to reload
    it. Reporting it OK is how it goes unnoticed until the agent empties."""
    _write_ssh_config(tmp_path, persist=False)
    result = next(s for s in STAGES if s.id == "ssh-config").check(_context(tmp_path))

    assert result.status is Status.WRONG
    assert "keep it loaded" in result.detail
    assert "AddKeysToAgent" in result.detail


def test_ubuntu_does_not_want_usekeychain_in_an_existing_stanza(tmp_path: Path) -> None:
    """The check must ask for exactly what the plan writes, or a machine
    bootstrap set up would report itself unfinished for ever."""
    (tmp_path / ".ssh").mkdir(exist_ok=True)
    (tmp_path / ".ssh" / "config").write_text(
        "Host gitlab.surrey.ac.uk\n    HostName gitlab.surrey.ac.uk\n"
        "    User git\n    IdentityFile ~/.ssh/id_ed25519_gitlab\n"
        "    AddKeysToAgent yes\n",
        encoding="utf-8",
    )
    result = next(s for s in STAGES if s.id == "ssh-config").check(
        _context(tmp_path, platform=UBUNTU)
    )

    assert result.status is Status.OK


def test_windows_writes_the_config_without_chmod(tmp_path: Path) -> None:
    """Windows has no chmod, and restricts a profile file to its owner
    already - which is what the User Guide says too."""
    plan = next(s for s in STAGES if s.id == "ssh-config").plan(
        _context(tmp_path, platform=WINDOWS)
    )
    script = " ".join(" ".join(command) for command in plan.commands)

    assert "chmod" not in script
    assert "powershell" in script
    assert "Add-Content" in script, "appended, not overwritten"


def _write_keypair(
    tmp_path: Path, public: str = "ssh-ed25519 AAAAC3Nz-PUBLIC al@surrey.ac.uk"
) -> None:
    """A keypair on disk, with halves that cannot be mistaken for each other."""
    (tmp_path / ".ssh").mkdir(exist_ok=True)
    (tmp_path / ".ssh" / "id_ed25519_gitlab.pub").write_text(public + "\n", encoding="utf-8")
    (tmp_path / ".ssh" / "id_ed25519_gitlab").write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nSECRET-DO-NOT-PRINT\n", encoding="utf-8"
    )


def test_the_public_key_is_printed_between_markers(tmp_path: Path) -> None:
    """#238: the instruction named a path and left the reader to find a
    dotfile, open it in something, and copy the right one of two files
    whose names differ by four characters.

    The markers matter as much as the key: it is one long line that wraps
    in a terminal, and a key pasted with a character missing is rejected
    exactly like one never uploaded at all."""
    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))
    joined = "\n".join(plan.instructions)

    assert "ssh-ed25519 AAAAC3Nz-PUBLIC al@surrey.ac.uk" in joined
    assert joined.count(PUBLIC_KEY_MARKER) == 2, "the key needs a start and an end"
    between = joined.split(PUBLIC_KEY_MARKER)[1]
    assert between.strip() == "ssh-ed25519 AAAAC3Nz-PUBLIC al@surrey.ac.uk", (
        "only the key belongs between the markers"
    )


def test_the_private_key_is_never_read_or_printed(tmp_path: Path) -> None:
    """The two files differ by the four characters `.pub`, and uploading
    the wrong one hands over the secret half. Printing the public key is
    what removes that hazard - so it must not reintroduce it."""
    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))
    joined = "\n".join(plan.instructions)

    assert "SECRET-DO-NOT-PRINT" not in joined
    assert "PRIVATE KEY" not in joined


def test_no_key_yet_falls_back_to_naming_the_file(tmp_path: Path) -> None:
    """`--dry-run` builds every plan, including this one on a machine
    where the keypair stage has not run - so reading the key has to be
    allowed to fail without taking the plan down with it."""
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))
    joined = "\n".join(plan.instructions)

    assert PUBLIC_KEY_MARKER not in joined
    assert "id_ed25519_gitlab.pub" in joined
    assert "never the one without it" in joined, "the warning matters most when guessing"


def test_an_empty_key_file_is_treated_as_no_key(tmp_path: Path) -> None:
    """An interrupted `ssh-keygen` leaves a file behind. Printing nothing
    between two markers would read as "there is your key"."""
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "id_ed25519_gitlab.pub").write_text("\n", encoding="utf-8")
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))

    assert PUBLIC_KEY_MARKER not in "\n".join(plan.instructions)


def test_a_multi_line_step_hangs_under_its_own_text(tmp_path: Path) -> None:
    """The key block is part of step 3, not steps 4, 5 and 6 - so its
    continuation lines align under the step's text rather than under the
    numbers, which would renumber the list by eye."""
    from click.testing import CliRunner

    from prodockit.cli import _show_steps

    runner = CliRunner()
    with runner.isolation() as (out, _err, _):
        _show_steps("  What you need to do:", ["first", "second\nCONTINUED\nAGAIN"])
        rendered = out.getvalue().decode()

    assert "    1. first" in rendered
    assert "    2. second" in rendered
    assert "       CONTINUED" in rendered, "aligned under the text, not the number"
    assert "    3. CONTINUED" not in rendered, "a continuation is not a new step"


def test_the_key_page_is_reached_by_menu_not_only_by_url(tmp_path: Path) -> None:
    """#238: the only route given was a pasted URL. That is the faster
    route for somebody who knows where they are going and the worse one
    for somebody who does not - it offers no way to tell you have landed
    in the right place, and no way back if you have not.

    The menu path is the User Guide's own wording, and the URL survives
    as a shortcut rather than as the only way in."""
    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))
    joined = "\n".join(plan.instructions)

    assert "Edit profile" in joined
    assert "Access > SSH Keys" in joined
    assert SURREY_GITLAB.ssh_keys_url in joined, "the shortcut is kept, not replaced"
    assert joined.index("Edit profile") < joined.index(SURREY_GITLAB.ssh_keys_url)


def test_the_gitlab_expiry_trap_is_spelled_out(tmp_path: Path) -> None:
    """GitLab requires an expiry date and fills it in a year ahead, so a
    reader who accepts the default is locked out mid-course - and the
    failure arrives months later as a permission error indistinguishable
    from a misconfigured key. The User Guide warns about this; bootstrap
    did not mention the field at all."""
    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))
    joined = "\n".join(plan.instructions)

    assert "Expiration date" in joined
    assert "year ahead" in joined


def test_the_form_is_one_step_with_its_fields_beneath(tmp_path: Path) -> None:
    """Title, Key and Expiration date are three boxes on one screen, not
    three things to go and do - numbering them separately would say the
    latter."""
    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))
    form = next(step for step in plan.instructions if "Title:" in step)

    assert "Key:" in form, "the key belongs to the same step as the title"
    assert "Expiration date" in form
    assert form.startswith("Click 'Add new key'")


def test_each_host_names_its_own_buttons_and_menus() -> None:
    """Host differences stay values rather than branches in the stage, so
    GitHub - which calls the buttons something else and has no expiry
    field at all - is a filled-in record rather than a rewrite."""
    assert GITHUB_COM.ssh_key_new_label == "New SSH key"
    assert GITHUB_COM.ssh_key_save_label == "Add SSH key"
    assert "SSH and GPG keys" in " ".join(GITHUB_COM.ssh_keys_steps)
    assert GITHUB_COM.ssh_key_form_extra == (), "a GitHub key has no expiry to set"

    assert SURREY_GITLAB.ssh_key_new_label == "Add new key"
    assert SURREY_GITLAB.ssh_key_save_label == "Add key"
    assert SURREY_GITLAB.ssh_key_form_extra, "GitLab's expiry field needs saying"


def test_browser_instructions_use_the_hosts_own_vocabulary(tmp_path: Path) -> None:
    """A GitHub user should read "repository", not GitLab's "project"."""
    context = _context(tmp_path)
    plan = next(s for s in STAGES if s.id == "own-project").plan(context)
    joined = " ".join(plan.instructions)
    assert "project" in joined
    assert SURREY_GITLAB.new_project_url in joined


def test_remote_plan_repoints_and_then_syncs(tmp_path: Path) -> None:
    """`git remote set-url` alone leaves the clone advertising the
    template's own repository in zensical.toml and the README badges."""
    runner = FakeRunner({"remote get-url origin": CommandResult(0, "git@old.example:x/y.git")})
    context = _context(tmp_path, runner=runner)
    plan = next(s for s in STAGES if s.id == "remote").plan(context)
    flat = [" ".join(command) for command in plan.commands]
    assert any("remote set-url" in c for c in flat)
    # Both commands run in the project: sync-repo reads its config from the
    # working directory and has no path flag.
    assert plan.cwd is not None and plan.cwd.endswith("report-al01234")
    assert any("sync-repo" in c for c in flat)


def test_plan_all_leaves_satisfied_stages_without_a_plan(tmp_path: Path) -> None:
    """The point of a rerun is to repair what is broken, not reinstall what
    works."""
    runner = FakeRunner(
        {
            "git --version": CommandResult(0, "git version 2.43.0"),
            "git config --global user.name": CommandResult(0, "Ada\n"),
            "git config --global user.email": CommandResult(0, "a@b.c\n"),
        }
    )
    context = _context(tmp_path, runner=runner)
    reports = {r.stage.id: r for r in plan_all(context)}
    assert reports["git"].result.status is Status.OK
    assert reports["git"].plan is None
    assert reports["vscode"].plan is not None


def test_every_stage_has_a_check_and_a_plan_for_every_platform(tmp_path: Path) -> None:
    """A stage that raises on one platform would only be found when
    somebody ran it there - which for Windows means a student, since this
    family has no Windows CI at all."""
    for platform in (MACOS, UBUNTU, WINDOWS):
        context = _context(tmp_path, platform=platform)
        for stage in STAGES:
            assert stage.check(context) is not None, (stage.id, platform)
            assert stage.plan(context) is not None, (stage.id, platform)


def test_unknown_stages_get_no_plan(tmp_path: Path) -> None:
    """Regression: a plan built from unanswered configuration rendered as
    `create a blank project named '' in the group ''` and
    `git ls-remote git@gitlab.surrey.ac.uk:/.git` - which reads as an
    instruction to follow rather than as the missing answer it is. Found
    by running `--dry-run` on a machine with no config.
    """
    context = _context(tmp_path, namespace="", project_name="", project_dir="")
    reports = {r.stage.id: r for r in plan_all(context)}
    for stage_id in ("clone", "own-project", "remote"):
        assert reports[stage_id].result.status is Status.UNKNOWN, stage_id
        assert reports[stage_id].plan is None, stage_id
    # Stages that need no configuration still plan normally.
    assert reports["vscode"].plan is not None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_bare_bootstrap_defaults_to_checking(cli_bootstrap) -> None:
    """Running it with no options must report rather than refuse - and,
    once applying exists, must not start installing software because
    somebody typed the command to see what it did."""
    result = cli_bootstrap()
    assert "Visual Studio Code" in result.output
    assert "stages need work" in result.output
    # The old behaviour: a usage error telling you to pass a flag.
    assert result.exit_code == 1
    assert "supports --check and --dry-run only" not in result.output


def test_bare_bootstrap_prints_no_commands(cli_bootstrap) -> None:
    """Checking is read-only, so it must not print a plan - that is what
    --dry-run is for, and showing commands implies something ran them."""
    result = cli_bootstrap()
    assert "run:" not in result.output
    assert "--dry-run" in result.output


def test_dry_run_prints_the_commands(cli_bootstrap, monkeypatch: pytest.MonkeyPatch) -> None:
    # Same host-state coupling as above: pinned to "no VS Code installed"
    # so the assertion describes a machine rather than this one.
    import prodockit.bootstrap.stages as stages_module

    monkeypatch.setattr(stages_module, "_vscode_app_installed", lambda context: False)
    result = cli_bootstrap("--dry-run")
    assert "run: brew install --cask visual-studio-code" in result.output


def test_bootstrap_exits_zero_when_everything_is_set_up(cli_bootstrap, tmp_path: Path) -> None:
    """Usable as a script check, matching `sync-repo --check`."""
    result = cli_bootstrap(responses=_ready_machine(tmp_path), fetch=_ready_fetch())

    # Against the list, not a number typed in: a count in prose drifts
    # the moment a stage is added, which is how "ten stages" shipped.
    assert f"All {len(STAGES)} stages are set up." in result.output
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Phase 2: template source, and applying
# ---------------------------------------------------------------------------


def test_surrey_clones_the_template_from_surrey_not_github(tmp_path: Path) -> None:
    """Regression: phase 1 hardcoded the GitHub URL. Surrey mirrors the
    template onto its own GitLab, and a student there has no GitHub
    account - cloning the original would ask them for credentials they
    have not got.
    """
    context = _context(tmp_path, source_url="")
    plan = next(s for s in STAGES if s.id == "clone").plan(context)
    assert plan.commands[0][2] == "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git"


def test_source_url_overrides_the_template(tmp_path: Path) -> None:
    """A reader given their own repository clones that instead - the
    template would be a detour through work the host already did."""
    own = "git@gitlab.surrey.ac.uk:comm058-2026/report-al01234.git"
    context = _context(tmp_path, source_url=own)
    plan = next(s for s in STAGES if s.id == "clone").plan(context)
    assert plan.commands[0][2] == own


def test_building_a_plan_makes_no_network_call(tmp_path: Path) -> None:
    """`--dry-run` builds every plan, so plan-building has to stay cheap
    and side-effect-free.

    This rule was relaxed for a while, to let the clone stage detect an
    existing project. Moving that decision into `--configure` (#332) won
    it back: the stage reads a recorded answer instead of asking the
    host, and nothing here connects at all.
    """
    runner = FakeRunner()
    context = _context(tmp_path, runner=runner)
    next(s for s in STAGES if s.id == "clone").plan(context)
    # `git --version` is how git is located when PATH cannot see it yet
    # (#390) - local, and not what this test is guarding against.
    assert [c for c in runner.calls if "--version" not in c] == []


def test_apply_reruns_the_check_afterwards(tmp_path: Path) -> None:
    """A command exiting zero says the installer ran, not that the thing
    works - every failure this project has had exited zero while producing
    something broken."""
    from prodockit.bootstrap import apply_stage

    runner = FakeRunner({"brew": CommandResult(0), "code": CommandResult(127)})
    context = _context(tmp_path, runner=runner)
    outcome = apply_stage(context, next(s for s in STAGES if s.id == "vscode"))
    assert outcome.failed is None  # the install command "succeeded"
    assert not outcome.ok  # but the check still fails
    assert outcome.verified is not None


def test_apply_stops_at_the_first_failing_command(tmp_path: Path) -> None:
    """Later commands in a plan depend on earlier ones, so pressing on
    turns one clear failure into several confusing ones."""
    from prodockit.bootstrap import apply_stage

    runner = FakeRunner({"git": CommandResult(1, stderr="boom")})
    context = _context(tmp_path, runner=runner)
    outcome = apply_stage(context, next(s for s in STAGES if s.id == "remote"))
    assert outcome.failed is not None
    assert len(outcome.ran) == 1  # set-url failed; sync-repo never ran


def test_the_runner_never_inherits_stdin() -> None:
    """Regression: `subprocess` inherits stdin by default, so `ssh -T`
    during a check consumed the answers typed for bootstrap's own prompts
    and every later prompt aborted on end-of-input. Found by running
    `--apply` with piped answers.
    """
    import inspect
    import subprocess as sp

    from prodockit.bootstrap.model import SubprocessRunner

    source = inspect.getsource(SubprocessRunner.run)
    assert "stdin=subprocess.DEVNULL" in source
    assert sp.DEVNULL is not None


def test_missing_keys_ignores_the_optional_override() -> None:
    """A blank `source_url` means "use the template" - the common answer,
    so treating it as missing would ask everyone a question most people
    should skip."""
    from prodockit.bootstrap import missing_keys

    assert missing_keys(_config(source_url="")) == []
    assert "project_name" in missing_keys(_config(project_name=""))


def test_gaps_are_offered_as_prompts_not_a_file_to_edit(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Telling a first-time reader a value is "not set in your bootstrap
    config" points them at a file they may not know how to edit - which is
    the kind of step this command exists to remove.

    Only the blank fields are asked for: filling one gap must not mean
    walking the whole list again.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    save(tmp_path / "b.toml", _config(project_name="", project_dir=""))
    result = cli_bootstrap(input="y\nreport-al01234\n~/GitLab/report-al01234\n")
    assert "Answer them now?" in result.output
    # Asked for the two blanks, not for the five already answered.
    assert "Your full name" not in result.output
    assert "Your project name" in result.output
    assert load(tmp_path / "b.toml").project_name == "report-al01234"


def test_declining_the_offer_carries_on(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    save(tmp_path / "b.toml", _config(project_name=""))
    result = cli_bootstrap(input="n\n")
    assert "Carrying on" in result.output
    assert load(tmp_path / "b.toml").project_name == ""


def test_a_piped_run_reports_instead_of_prompting(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scripted or piped run must report and exit rather than block on a
    prompt nobody is there to answer."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: False)
    save(tmp_path / "b.toml", _config(project_name=""))
    result = cli_bootstrap()
    assert "Answer them now?" not in result.output
    assert "--configure" in result.output


def test_vscode_installed_without_the_shell_command_is_wrong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression, reported from real use: the app and the `code` command
    are separate installs, and on macOS the cask gives you only the first.
    Treating a missing `code` as a missing VS Code reported "not
    installed" on a machine that plainly had it, then tried to reinstall,
    which fails outright:

        Error: It seems there is already an App at
        '/Applications/Visual Studio Code.app'.
    """
    context = _context(tmp_path, vscode_app=True)  # FakeRunner: `code` not on PATH
    stage = next(s for s in STAGES if s.id == "vscode")

    result = stage.check(context)
    # Satisfied since #424: the CLI lives inside the application on macOS,
    # so bootstrap can drive VS Code without `code` being on PATH at all.
    # The reader is still told how to get it for their own terminal.
    assert result.status is Status.OK
    assert "not on PATH" in result.detail
    assert "Command Palette" in result.detail

    plan = stage.plan(context)
    # The thing this was reported for: never an install that would fail
    # against an app already sitting in /Applications.
    assert plan.commands == []
    assert any("Shell Command" in i for i in plan.instructions)


def test_vscode_genuinely_absent_still_installs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, vscode_app=False)
    stage = next(s for s in STAGES if s.id == "vscode")
    assert stage.check(context).status is Status.MISSING
    assert stage.plan(context).commands[0][0] == "brew"


def test_a_relative_project_dir_resolves_against_the_current_directory(
    tmp_path: Path,
) -> None:
    """Reported from real use: a bare name landed in the home directory.
    The User Guide's flow is "navigate to your GitLab folder, then clone",
    so it belongs where the command was run from."""
    config = _config(project_dir="report-al01234")
    here = tmp_path / "GitLab"
    assert config.resolved_project_dir(tmp_path, cwd=here) == here / "report-al01234"


def test_an_absolute_project_dir_is_left_alone(tmp_path: Path) -> None:
    config = _config(project_dir=str(tmp_path / "elsewhere"))
    assert config.resolved_project_dir(tmp_path, cwd=tmp_path / "GitLab") == (
        tmp_path / "elsewhere"
    )


def test_the_project_dir_default_is_offered_as_here(tmp_path: Path) -> None:
    """Offered as `./<name>` even when a value is stored - the one field
    where the stored answer does not win.

    A stored path that was wrong is otherwise the one thing a reader
    cannot correct by pressing Enter, which is how the same clone landed
    in a home directory twice. It also means a project that has been
    *moved* self-heals: re-running --configure from its new location
    offers here, rather than the path it used to be at.
    """
    from prodockit.bootstrap import default_for

    assert default_for(_config(project_dir=""), "project_dir") == "./report-al01234"
    # Even with a stale absolute value stored.
    stale = _config(project_dir=str(tmp_path / "somewhere" / "else"))
    assert default_for(stale, "project_dir") == "./report-al01234"


def test_every_other_field_still_keeps_its_stored_answer() -> None:
    """The project_dir exception has to stay an exception - a rerun that
    silently discarded your name and email would be worse than the
    problem it solves."""
    from prodockit.bootstrap import default_for

    config = _config(full_name="Ada Lovelace", namespace="comm058-2026")
    assert default_for(config, "full_name") == "Ada Lovelace"
    assert default_for(config, "namespace") == "comm058-2026"


def test_extensions_plan_installs_only_what_is_missing(tmp_path: Path) -> None:
    """Reported from real use: with one extension absent the plan listed
    an install for all three, which reads as though the check had not
    been consulted at all."""
    present = "\n".join(VSCODE_EXTENSIONS[:-1])
    runner = FakeRunner({"code --list-extensions": CommandResult(0, present)})
    context = _context(tmp_path, runner=runner)
    stage = next(s for s in STAGES if s.id == "extensions")

    plan = stage.plan(context)
    assert len(plan.commands) == 1
    assert plan.commands[0][-1] == VSCODE_EXTENSIONS[-1]

    # And the check names what is already there, not only what is not.
    detail = stage.check(context).detail
    assert f"{len(VSCODE_EXTENSIONS) - 1} of {len(VSCODE_EXTENSIONS)} installed" in detail
    assert VSCODE_EXTENSIONS[-1] in detail


def test_a_manual_step_is_retried_not_failed(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reported from real use: pressing Enter before creating the project
    on the website failed the run and exited, throwing away every stage
    already completed.

    Checking too early is the normal case, not an error - you cannot
    create a project on a website and have it exist before you have done
    it. So it says "not there yet" and asks again.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    save(tmp_path / "b.toml", _config())
    # `git ls-remote` always fails: the project is never created, so the
    # only way out is declining the retry.
    result = cli_bootstrap(
        "--apply",
        responses={"code": CommandResult(0, "\n".join(VSCODE_EXTENSIONS))},
        input="n\n" * 20,
    )
    assert "not there yet" in result.output or "skipped" in result.output
    # The old behaviour: a hard exit on the first failed verification.
    assert "Stopping - later stages depend on this one." not in result.output


def _machine_ready_except_ssh(tmp_path: Path) -> dict[str, CommandResult]:
    """Every stage satisfied but the SSH key, which the host rejects."""
    (tmp_path / ".ssh").mkdir(exist_ok=True)
    for suffix in ("", ".pub"):
        (tmp_path / ".ssh" / f"id_ed25519_gitlab{suffix}").write_text("k", encoding="utf-8")
    _write_ssh_config(tmp_path)
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True, exist_ok=True)
    (project / "tools").mkdir(exist_ok=True)
    save(tmp_path / "b.toml", _config())
    return {
        # Satisfied here too: this fixture is about the SSH stage, and a
        # second finding would change what the run stops at (#381).
        "sys.base_prefix": CommandResult(0, "True"),
        "import ensurepip, venv": CommandResult(0),
        "code": CommandResult(0, "\n".join(VSCODE_EXTENSIONS)),
        "git --version": CommandResult(0, "git version 2.43.0"),
        "git config --global user.name": CommandResult(0, "Ada\n"),
        "git config --global user.email": CommandResult(0, "a@b.c\n"),
        # Named in the docstring above and previously missing, which left
        # the history stage with work to do and made this helper describe
        # a machine it does not claim to.
        "config core.fileMode": CommandResult(0, "false\n"),
        # Same reason: without these the host-CLI stage plans an install.
        "glab --version": CommandResult(0, "glab 1.0.0"),
        "glab auth status": CommandResult(0, "Logged in"),
        # The reported machine: the key exists locally, the host has
        # never seen it.
        "BatchMode": CommandResult(
            255,
            stderr=(
                "git@gitlab.surrey.ac.uk: Permission denied "
                "(publickey,gssapi-keyex,gssapi-with-mic,password)."
            ),
        ),
        "git": CommandResult(0, "git@gitlab.surrey.ac.uk:comm058-2026/report-al01234.git\n"),
        **AGENT_RESPONSES,
        "prodockit sync-repo --check": CommandResult(0),
        "config --local user.name": CommandResult(0, "Ada Lovelace\n"),
        "config --local user.email": CommandResult(0, "al01234@surrey.ac.uk\n"),
        "pandoc": CommandResult(0, "pandoc 3.10.1"),
        "node": CommandResult(0, "v22.14.0\n"),
        "npm": CommandResult(0, "10.9.2\n"),
    }


def test_git_installed_a_moment_ago_is_not_reported_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#390, reported from Windows.

        [2/22] Git, installed and configured
                git is not installed
        ...
        Found an existing package already installed.

    The installer adds git to the *machine's* PATH, and PATH is read when
    a process starts - so a shell not reopened since cannot see it. Every
    stage that runs git was failing for the same reason, not only this
    one, which is why the resolution is shared rather than local to the
    check.
    """
    from prodockit.bootstrap import stages as stage_module

    installed = tmp_path / "Program Files" / "Git" / "cmd" / "git.exe"
    installed.parent.mkdir(parents=True)
    installed.write_text("", encoding="utf-8")
    monkeypatch.setattr(stage_module, "_GIT_APP_PATHS", {WINDOWS: (str(installed),)})

    # PATH cannot see it: `git --version` fails.
    machine = _ready_machine(tmp_path) | {"git --version": CommandResult(127, stderr="not found")}
    context = _context(tmp_path, platform=WINDOWS, runner=FakeRunner(machine))

    assert stage_module.git_command(context) == str(installed), (
        "found where the installer puts it, and used by its full path"
    )
    said = next(s for s in STAGES if s.id == "git").check(context)
    assert said.status is not Status.MISSING, "it is installed - PATH just cannot see it yet"
    assert "new terminal" in said.detail, "and says why it looked odd"

    # Not only the git stage: every stage that runs git uses the same
    # answer, or the run fails a dozen stages further down instead.
    commands = next(s for s in STAGES if s.id == "identity").plan(context).commands
    assert commands and all(c[0] == str(installed) for c in commands), commands


def test_the_closing_line_says_how_to_act_not_only_how_to_look(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path
) -> None:
    """prodockit-extensions#376.

        Run with --dry-run to see the exact commands that would fix them.

    was the whole of it. A reader just told that fourteen stages need
    work is being shown how to look and not how to act - and `--apply` is
    what they came for. Both ends of the run had the same gap: after a
    dry run, nothing said how to run what had just been printed.
    """
    save(tmp_path / "b.toml", _config())

    checked = cli_bootstrap()
    assert "--apply" in checked.output, "the one they came for"
    assert "--dry-run" in checked.output, "and the careful route, as before"

    dry = cli_bootstrap("--dry-run")
    assert "--apply" in dry.output, "having read the commands, say how to run them"


def test_the_run_says_which_prodockit_it_is(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#399.

    A report arrived headed 0.32.0 whose "Will run:" lines were ones
    0.32.0 had not contained since the release before - an older install
    doing the work, in a window that had never been reopened. The version
    in the header could not show that. The path can, and it is the first
    thing to check when a run does something the source says it cannot.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    save(tmp_path / "b.toml", _config())

    result = cli_bootstrap("--apply", input="n\n" * 40)

    assert "Running:" in result.output
    assert str(Path(prodockit_module.__file__).parent) in result.output, (
        "where this prodockit actually is, not only what it calls itself"
    )
    assert __version__ in result.output, "and the version, as before"


#: Command names that need no resolving because the machine already has
#: them: they are never what a plan installs.
_ALWAYS_PRESENT = frozenset({"powershell", "cmd", "bash", "sh", "sudo", "apt", "brew", "winget"})


def test_no_plan_installs_a_tool_and_then_runs_it_by_a_bare_name(tmp_path: Path) -> None:
    """The shape behind prodockit-extensions#405, across every stage.

    A plan is written before any of it runs, so a name resolved while
    writing it cannot account for what the plan itself installs. Only the
    node stage does both in one plan today - and `npm` is now resolved as
    it is about to run - but the next stage to install something and use
    it would land in exactly the same place.

    Stages *after* the installing one are safe for a different reason:
    `apply_stage` re-plans when it reaches each stage, so an earlier
    stage's install has already happened. That is what makes this test
    about single plans rather than about the run.
    """
    from prodockit.bootstrap.stages import _RESOLVE_BEFORE_RUNNING

    installers = {"winget", "apt", "brew", "sudo", "pacman"}
    offenders: list[str] = []
    for platform in (WINDOWS, MACOS, UBUNTU):
        context = _context(tmp_path, platform=platform, runner=FakeRunner(_ready_machine(tmp_path)))
        for stage in STAGES:
            names = [c[0] for c in stage.plan(context).commands if c]
            if not (found := [i for i, n in enumerate(names) if n in installers]):
                continue
            for name in names[max(found) + 1 :]:
                if Path(name).is_absolute() or name in _ALWAYS_PRESENT or name in installers:
                    continue
                if name in _RESOLVE_BEFORE_RUNNING:
                    continue  # resolved as it is about to run
                offenders.append(f"{platform}/{stage.id}: {name}")

    assert not offenders, (
        "installed in the same plan, then run by a name fixed before the install: "
        f"{offenders} - add it to _RESOLVE_BEFORE_RUNNING"
    )


def test_extensions_are_listed_with_the_command_that_installs_them(tmp_path: Path) -> None:
    """prodockit-extensions#410, reported from Windows.

        Extension 'ms-python.python' v2026.4.0 was successfully installed.
        ...
        ran, but still not right: could not list extensions - is VS Code
        installed?

    said of the VS Code it had just driven successfully, four times, by
    full path. The plan resolved `code.cmd`; the check asked for a bare
    `code`, which on Windows cannot run at all - so the stage could never
    pass there, and the run stops on it because later stages depend on
    it.
    """
    from prodockit.bootstrap import stages as stage_module

    code = tmp_path / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd"
    code.parent.mkdir(parents=True)
    code.write_text("", encoding="utf-8")
    # PATH cannot see it, which is the whole of the Windows case.
    machine = {
        "code --list-extensions": CommandResult(127, stderr="not found"),
        f"{code} --list-extensions": CommandResult(0, "\n".join(VSCODE_EXTENSIONS)),
    }
    context = _context(tmp_path, platform=WINDOWS, runner=FakeRunner(machine))
    original = stage_module._VSCODE_CLI_PATHS
    stage_module._VSCODE_CLI_PATHS = {WINDOWS: (str(code),)}
    try:
        result = next(s for s in STAGES if s.id == "extensions").check(context)
    finally:
        stage_module._VSCODE_CLI_PATHS = original

    assert result.status is Status.OK, result.detail
    assert "is VS Code installed?" not in result.detail


def test_no_check_asks_for_a_tool_by_a_name_it_knows_how_to_resolve() -> None:
    """Third instance of one shape: #390 (git), #405 (npm), #410 (code).

    Each time, a check asked the machine a question its own plan already
    knew the answer to - and on Windows the bare name could not run at
    all, so the stage was unfinishable rather than merely wrong.
    """
    from prodockit.bootstrap import stages as stage_module

    source = Path(stage_module.__file__).read_text(encoding="utf-8")
    bare = [name for name in ("code", "npm", "git") if f'["{name}",' in source]

    assert not bare, (
        f"invoked by bare name: {bare} - use the resolver, or the check and its "
        "plan will disagree about the same machine"
    )


def test_a_repository_created_with_a_readme_is_not_reported_as_pushed(
    tmp_path: Path,
) -> None:
    """prodockit-extensions#423.

    A student who ticks "initialize this repository with a README" gets a
    commit their project's history does not contain. The check asked only
    whether the remote had *anything* on it - so it answered `ok, pushed`
    about a project that had never been pushed, and the site stage then
    found nothing published with no way to see why.

    Silent success on a broken setup is worse than the failed push it was
    hiding.
    """
    machine = _ready_machine(tmp_path)
    machine["rev-parse HEAD"] = CommandResult(0, "ffffff\n")  # ours
    machine["ls-remote origin HEAD"] = CommandResult(0, "aaaaaa\tHEAD\n")  # theirs
    machine["ls-tree"] = CommandResult(0, "README.md\n")
    machine["rev-list"] = CommandResult(0, "1\n")
    result = next(s for s in STAGES if s.id == "first-push").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    assert result.status is Status.MISSING
    assert "only the README" in result.detail
    assert "not pushed yet" in result.detail


def _first_push_plan(tmp_path: Path) -> Plan:
    """The stage 22 plan against a repository holding only its README."""
    machine = _ready_machine(tmp_path)
    machine["rev-parse HEAD"] = CommandResult(0, "ffffff\n")
    machine["ls-remote origin HEAD"] = CommandResult(0, "aaaaaa\tHEAD\n")
    machine["ls-tree"] = CommandResult(0, "README.md\n")
    machine["rev-list"] = CommandResult(0, "1\n")
    return next(s for s in STAGES if s.id == "first-push").plan(
        _context(tmp_path, runner=FakeRunner(machine))
    )


def test_the_hosts_readme_commit_is_merged_rather_than_forced_over(
    tmp_path: Path,
) -> None:
    """prodockit-extensions#442.

    The README commit has to be dealt with somehow - an ordinary push is
    rejected as non-fast-forward while it is not in this history (#423).
    Forcing was the first answer and it does not survive contact with a
    protected branch:

        remote: GitLab: You are not allowed to force push code to a
        protected branch on this project.

    Taking the commit into the history instead makes the push a
    fast-forward, and `-s ours` keeps this project's tree entire - the
    same end, reached by an operation nobody has a rule against.
    """
    plan = _first_push_plan(tmp_path)
    merge = next((c for c in plan.commands if "merge" in c), None)

    assert merge is not None, plan.commands
    assert "--allow-unrelated-histories" in merge
    assert merge[merge.index("-s") : merge.index("-s") + 2] == ["-s", "ours"]
    # Fetched first, or FETCH_HEAD is whatever some earlier command left.
    fetched = next(c for c in plan.commands if "fetch" in c)
    assert plan.commands.index(fetched) < plan.commands.index(merge)
    assert any("nothing is forced" in step for step in plan.instructions)


def test_the_push_is_never_forced(tmp_path: Path) -> None:
    """Whatever the remote turns out to hold.

    A forced push is the one command here that can destroy work that was
    never this project's, and the case it was reached for is now handled
    by merging. Nothing is left that needs it - so any reappearance is a
    regression, not a decision.
    """
    for plan in (_first_push_plan(tmp_path), _plan_for_an_empty_remote(tmp_path)):
        for command in plan.commands:
            flags = " ".join(command)
            assert "--force" not in flags, flags
            assert "-f" not in command, command


def _plan_for_an_empty_remote(tmp_path: Path) -> Plan:
    """The ordinary case: a repository created with nothing in it."""
    machine = _ready_machine(tmp_path)
    machine["rev-parse HEAD"] = CommandResult(0, "ffffff\n")
    machine["ls-remote origin HEAD"] = CommandResult(0, "")
    return next(s for s in STAGES if s.id == "first-push").plan(
        _context(tmp_path, runner=FakeRunner(machine))
    )


def test_an_empty_remote_is_pushed_to_without_merging_anything(
    tmp_path: Path,
) -> None:
    """There is no commit to adopt, and a merge against nothing would
    fail - so the fetch and merge appear only where they are needed."""
    plan = _plan_for_an_empty_remote(tmp_path)

    assert not [c for c in plan.commands if "merge" in c], plan.commands
    assert any("push" in c for c in plan.commands)


def test_work_that_is_not_a_readme_is_never_pushed_over(tmp_path: Path) -> None:
    """The exactness is the safety. Two files, or two commits, and this
    is somebody's work rather than a tick-box - so the stage says to go
    and look rather than offering to overwrite it."""
    machine = _ready_machine(tmp_path)
    machine["rev-parse HEAD"] = CommandResult(0, "ffffff\n")
    machine["ls-remote origin HEAD"] = CommandResult(0, "aaaaaa\tHEAD\n")
    machine["ls-tree"] = CommandResult(0, "README.md\nnotes.md\n")
    machine["rev-list"] = CommandResult(0, "1\n")
    context = _context(tmp_path, runner=FakeRunner(machine))

    result = next(s for s in STAGES if s.id == "first-push").check(context)
    assert result.status is Status.WRONG
    assert "commits this project does not" in result.detail

    push = next(
        c
        for c in next(s for s in STAGES if s.id == "first-push").plan(context).commands
        if "push" in c
    )
    assert not any(part.startswith("--force") for part in push), push


def test_a_retry_after_a_refused_push_pushes(tmp_path: Path) -> None:
    """prodockit-extensions#414, reported from Windows.

        [main (root-commit) 5e98636] Initial commit
        ...
        remote: You are not allowed to push code to this project.

    The commit was made and the push declined, which leaves the project
    committed here and empty there. On the next run `git status` is clean,
    so `git commit` would exit 1 with nothing to commit - and the run
    would stop *before* the push, failing for a reason that is neither
    true nor the obstacle.
    """
    machine = _ready_machine(tmp_path)
    machine["status --porcelain"] = CommandResult(0, "")  # nothing left to commit
    stage = next(s for s in STAGES if s.id == "first-push")
    commands = stage.plan(_context(tmp_path, runner=FakeRunner(machine))).commands
    names = [" ".join(c) for c in commands]

    assert not any("commit" in n for n in names), f"nothing to commit: {names}"
    assert any("push" in n for n in names), "the push is the whole point of the retry"

    # ...and a first run, with work to commit, still commits it.
    fresh = _ready_machine(tmp_path)
    fresh["status --porcelain"] = CommandResult(0, " M docs/index.md\n")
    first = stage.plan(_context(tmp_path, runner=FakeRunner(fresh))).commands
    assert any("commit" in " ".join(c) for c in first)


def test_the_first_push_lists_every_change_it_will_commit(tmp_path: Path) -> None:
    machine = _ready_machine(tmp_path)
    machine["status --porcelain"] = CommandResult(0, " M docs/index.md\n?? notes with spaces.md\n")

    plan = next(s for s in STAGES if s.id == "first-push").plan(
        _context(tmp_path, runner=FakeRunner(machine))
    )
    shown = "\n".join(plan.instructions)

    assert "exact uncommitted changes" in shown
    assert " M docs/index.md" in shown
    assert "?? notes with spaces.md" in shown
    assert ["git", "add", "-A"] in plan.commands


def test_a_push_the_host_refuses_is_named_not_numbered(tmp_path: Path) -> None:
    """`failed: exit status 128` scrolled past sixty-eight `create mode`
    lines, and the one sentence that mattered was the hardest to find.

    The commands run with the terminal attached rather than captured, so
    their output never reaches bootstrap - the check afterwards is where
    the refusal can be read back (#414).
    """
    machine = _ready_machine(tmp_path)
    machine["status --porcelain"] = CommandResult(0, "")
    machine["ls-remote origin HEAD"] = CommandResult(0, "")  # empty on the host
    machine["push --dry-run"] = CommandResult(
        128, stderr="remote: You are not allowed to push code to this project."
    )
    result = next(s for s in STAGES if s.id == "first-push").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    assert result.status is Status.WRONG
    assert "not allowed to write here" in result.detail
    assert "the key is fine" in result.detail, "not another key hunt"
    assert "protected branch" in result.detail, "and what to check"


def test_a_first_run_does_not_pay_for_that_question(tmp_path: Path) -> None:
    """The dry-run push costs a host connection, so it is asked only from
    the one state that cannot explain itself. A first run has work to
    commit and never reaches it (#304)."""
    machine = _ready_machine(tmp_path)
    machine["status --porcelain"] = CommandResult(0, " M docs/index.md\n")
    runner = FakeRunner(machine)
    next(s for s in STAGES if s.id == "first-push").check(_context(tmp_path, runner=runner))

    assert not any("--dry-run" in " ".join(c) for c in runner.calls), runner.calls


def test_npm_is_found_after_the_command_that_installed_it(tmp_path: Path) -> None:
    """prodockit-extensions#405, reported from Windows on ARM.

        Successfully installed
        ...
        failed: npm: not found

    Two things are true at once. The plan is written before any of it
    runs, so `npm_command` resolves npm while Node is still absent and
    falls back to the bare name - and a bare `npm` can never run on
    Windows, because `CreateProcess` appends `.exe` and npm is a `.cmd`.

    `refresh_windows_path()` cannot help: the problem is the name, not
    PATH. So the name is resolved when the command is about to run, which
    is the only point at which the answer can be right.
    """
    from prodockit.bootstrap.stages import resolve_for_execution

    npm = tmp_path / "Program Files" / "nodejs" / "npm.cmd"
    npm.parent.mkdir(parents=True)
    npm.write_text("", encoding="utf-8")
    monkey = {"npm": CommandResult(127, stderr="not found")}
    context = _context(tmp_path, platform=WINDOWS, runner=FakeRunner(monkey))

    from prodockit.bootstrap import stages as stage_module

    original = stage_module._NPM_PATHS
    stage_module._NPM_PATHS = (str(npm.parent),)
    try:
        resolved = resolve_for_execution(context, ["npm", "ci", "--prefix", "x"])
    finally:
        stage_module._NPM_PATHS = original

    assert resolved == [str(npm), "ci", "--prefix", "x"], "the shim, by its full path"
    # Everything else is passed through untouched, including the winget
    # line that precedes it in the very same plan.
    winget = ["winget", "install", "--id", "OpenJS.NodeJS.LTS"]
    assert resolve_for_execution(context, winget) == winget
    assert resolve_for_execution(context, []) == []


def test_the_apply_loop_resolves_before_it_runs(tmp_path: Path) -> None:
    """The resolution has to happen in the loop, not in the plan - a plan
    is written once, before the install it depends on has run."""
    import inspect

    from prodockit.bootstrap import apply_stage

    source = inspect.getsource(apply_stage)
    assert "resolve_for_execution" in source, (
        "resolved as each command is about to run, not when the plan was written"
    )


#: `| 7 | SSH key on the host | **guide and verify** |`
_STAGE_ROW = re.compile(r"^\| (\d+) \| (.+?) \| (.+?) \|$", flags=re.MULTILINE)
BOOTSTRAP_PAGE = Path(__file__).resolve().parents[2] / "docs" / "devcons" / "bootstrap.md"


def test_the_documented_stages_are_the_stages() -> None:
    """The page described eighteen stages for five releases after there
    were twenty-three (prodockit-extensions#413).

    Nothing failed, because prose cannot fail. A reader on a finished
    setup was told "All 23 stages are set up" by a page listing eighteen,
    and had no way to tell which of the two was wrong.
    """
    page = BOOTSTRAP_PAGE.read_text(encoding="utf-8")
    table = page[page.index("| # | Stage | Automated? |") :]
    rows = _STAGE_ROW.findall(table[: table.index("\n\n")])

    assert len(rows) == len(STAGES), (
        f"the table lists {len(rows)} stages, the tool has {len(STAGES)}"
    )
    for (number, described, _automated), (position, stage) in zip(
        rows, enumerate(STAGES, start=1), strict=True
    ):
        assert int(number) == position, f"row {number} is in position {position}"
        # Bold and code markers are the page's own emphasis rather than
        # part of the name: "Git, installed **and** configured" is one
        # stage, however it is set.
        plain = described.replace("**", "").replace("`", "")
        assert plain == stage.summary, f"row {number}: {plain!r} != {stage.summary!r}"


def test_the_bootstrap_page_does_not_hard_code_a_stage_count() -> None:
    """A number written in prose goes stale silently, which is how #413
    happened - five releases of it. The tool reports the count at the end
    of a run; the page names the stages instead of counting them."""
    page = BOOTSTRAP_PAGE.read_text(encoding="utf-8").lower()

    for stale in ("eighteen stages", "nineteen stages", "twenty stages", "22 stages"):
        assert stale not in page, stale


def test_a_service_that_is_running_by_the_time_we_look_carries_on(
    tmp_path: Path,
) -> None:
    """prodockit-extensions#435.

    The run used to end the moment the reader said they had started the
    ssh-agent service, on the reasoning that this process could not see
    it. Usually it can: `ssh-add` opens the agent's pipe afresh every
    time it runs, so the next check is a new process asking a question
    whose answer has just changed.

    Ending a run that could have carried on is a worse outcome than the
    loop it was fixing.
    """
    from click.testing import CliRunner

    from prodockit.bootstrap import Plan
    from prodockit.cli import _verify_until_done

    started: list[bool] = []

    class ServiceStarts(FakeRunner):
        """No agent until the reader says they started one."""

        def run(self, command, cwd=None, timeout=None, capture=True):  # type: ignore[no-untyped-def]
            if " ".join(command).startswith("ssh-add -l"):
                if started:
                    return CommandResult(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)")
                return CommandResult(2, stderr="Error connecting to agent")
            return super().run(command, cwd, timeout, capture)

    machine = _ready_machine(tmp_path)
    context = _context(tmp_path, platform=WINDOWS, runner=ServiceStarts(machine))
    stage = next(s for s in STAGES if s.id == "ssh-agent")
    plan = Plan(confirm="Have you started the ssh-agent service?", needs_a_new_run=True)

    assert stage.check(context).needs_work, "no agent yet - the state under test"
    with CliRunner().isolation(input="yes\n"):
        started.append(True)  # they go and start it, then answer
        done = _verify_until_done(context, stage, plan)

    assert done, "the check could see it - the run should carry on"


def test_a_step_still_unseen_after_answering_ends_the_run(tmp_path: Path) -> None:
    """And when it genuinely cannot be seen, the run ends rather than
    putting the same question to the same unchanged answer (#397)."""
    from click.testing import CliRunner

    from prodockit.bootstrap import Plan
    from prodockit.cli import _StartAgain, _verify_until_done

    machine = _ready_machine(tmp_path) | {"ssh-add -l": CommandResult(2)}
    context = _context(tmp_path, platform=WINDOWS, runner=FakeRunner(machine))
    stage = next(s for s in STAGES if s.id == "ssh-agent")
    plan = Plan(confirm="Have you started the ssh-agent service?", needs_a_new_run=True)

    with CliRunner().isolation(input="yes\n"), pytest.raises(_StartAgain):
        _verify_until_done(context, stage, plan)


def test_windows_agent_setup_continues_in_the_same_run(tmp_path: Path) -> None:
    """pdkboot requests elevation itself, then loads the key in the
    original terminal instead of telling the reader to restart it."""
    stage = next(s for s in STAGES if s.id == "ssh-agent")
    machine = {"ssh-add -l": CommandResult(2)}
    windows = stage.plan(_context(tmp_path, platform=WINDOWS, runner=FakeRunner(machine)))

    assert not windows.needs_a_new_run
    assert windows.needs_terminal
    assert len(windows.commands) == 2
    elevated = " ".join(windows.commands[0])
    assert "Start-Process powershell.exe" in elevated
    assert "-Verb RunAs" in elevated
    assert "Set-Service ssh-agent -StartupType Automatic" in elevated
    assert "Start-Service ssh-agent" in elevated
    assert windows.commands[1][0] == "ssh-add"


def test_a_browser_step_cannot_be_answered_with_the_enter_key(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`[Y/n]` is answered by pressing Enter (prodockit-extensions#374).

    A reader twelve stages into twenty-three presses it in rhythm, and for
    a browser step that means claiming to have done something they have
    not. The word has to be typed - `y` is not it, and neither is Enter.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    responses = _machine_ready_except_ssh(tmp_path)

    # Enter, then `y`, then the word. The first two are refused.
    result = cli_bootstrap("--apply", responses=responses, input="\ny\nyes\nn\n")

    assert result.output.count("type 'yes' once it is done") == 2, (
        "both the bare Enter and the `y` were turned away"
    )
    assert "(yes/no)" in result.output, "the prompt says what it wants"
    assert "[Y/n]" not in result.output.split("What you need to do:")[-1].split("Try again?")[0], (
        "no default to press past"
    )


def test_saying_no_to_a_browser_step_leaves_it_outstanding(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "no" is a real answer, not a way of getting past the prompt.

    It has to be, or the only way out of a step a reader cannot do yet is
    to claim they did it - which is the habit #374 is about.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    responses = _machine_ready_except_ssh(tmp_path)

    result = cli_bootstrap("--apply", responses=responses, input="no\n")

    assert "confirmed" not in result.output
    assert "Try again?" not in result.output, "declined, not retried"


def test_a_key_not_yet_uploaded_is_guided_not_treated_as_a_failed_command(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#234, reported against 0.24.0.

    Stage 4 carried `ssh -T` as a plan *command*. On a machine whose key
    was not yet on the host - the one state the stage exists to fix -
    `--apply` ran the probe before saying a word about uploading
    anything, read its non-zero exit as a failed command, and ended the
    run:

        failed: git@gitlab.surrey.ac.uk: Permission denied (publickey...).
        Stopping - later stages depend on this one.

    The probe could never have passed: `ssh -T` against a git host exits
    non-zero even on success. The greeting is the signal, and reading it
    is the *check's* job - which is why the plan is now instructions
    only, and the re-check after applying does the verifying.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    responses = _machine_ready_except_ssh(tmp_path)

    # "yes, I have done it" - then decline the retry, so the loop ends.
    result = cli_bootstrap("--apply", responses=responses, input="yes\nn\n")

    assert "Stopping - later stages depend on this one." not in result.output
    assert "failed:" not in result.output
    # Guided first: the upload is a browser step, so the reader is told
    # where to go before anything is run on their behalf.
    assert "What you need to do:" in result.output
    assert SURREY_GITLAB.ssh_keys_url in result.output
    assert "Run 1 command?" not in result.output
    # And "not yet" is answered by asking again, not by exiting.
    assert "not there yet" in result.output


def test_a_git_banner_is_reduced_to_its_one_useful_line() -> None:
    """Git wraps remote errors in `=====` banners and empty `remote:`
    markers, so printing the lot buries the sentence that matters."""
    from prodockit.cli import _first_meaningful_line

    stderr = (
        "remote: \n"
        "remote: ========================================================\n"
        "remote: \n"
        "remote: The project you were looking for could not be found.\n"
        "remote: ========================================================\n"
    )
    assert _first_meaningful_line(stderr) == (
        "The project you were looking for could not be found."
    )


def test_repoint_is_not_done_until_the_config_is_synced_too(tmp_path: Path) -> None:
    """Reported from real use: `git remote set-url` succeeded, sync-repo
    did not run, and the stage then reported itself done - leaving a clone
    that pushed to the right place while every page still advertised the
    template's repository.
    """
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    wanted = "git@gitlab.surrey.ac.uk:comm058-2026/report-al01234.git"
    runner = FakeRunner(
        {
            "git": CommandResult(0, wanted + "\n"),
            "prodockit sync-repo --check": CommandResult(1, stderr="would update: repo_url"),
        }
    )
    context = _context(tmp_path, runner=runner, project_dir=str(project))
    result = next(s for s in STAGES if s.id == "remote").check(context)
    assert result.status is Status.WRONG
    assert "needs syncing" in result.detail

    # And once sync-repo is happy, so is the stage.
    runner.responses["prodockit sync-repo --check"] = CommandResult(0)
    assert next(s for s in STAGES if s.id == "remote").check(context).status is Status.OK


# ---------------------------------------------------------------------------
# A command that can stop for a human is a broken check
# (prodockit-extensions#225)
# ---------------------------------------------------------------------------


def test_the_ssh_probe_cannot_stop_for_a_human(tmp_path: Path) -> None:
    """Regression: `stdin=DEVNULL` is necessary but not sufficient.

    ssh reads passwords from `/dev/tty` directly, bypassing stdin
    entirely, so a check on a machine whose key was not yet uploaded fell
    back to password authentication and sat there:

        git@gitlab.surrey.ac.uk's password:

    Testing stopped. `BatchMode=yes` is what makes ssh fail instead of
    ask; nothing else in the invocation does.
    """
    _write_keypair(tmp_path)
    runner = FakeRunner(_agent(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)"))
    context = _context(tmp_path, runner=runner)
    next(s for s in STAGES if s.id == "ssh-upload").check(context)

    probe = next(call for call in runner.calls if call[0] == "ssh")
    assert "BatchMode=yes" in probe
    assert "ConnectTimeout=10" in probe


def test_the_host_probe_waits_for_the_key_and_agent(tmp_path: Path) -> None:
    """A host result before its signing prerequisites exist is noise, not
    a useful diagnosis, and must not make a network call."""
    runner = FakeRunner({"ssh": CommandResult(255, stderr="Host key verification failed.")})

    result = next(s for s in STAGES if s.id == "ssh-upload").check(
        _context(tmp_path, runner=runner)
    )

    assert result.status is Status.BLOCKED
    assert "keypair" in result.detail
    assert not any(call[0] == "ssh" for call in runner.calls)


def test_an_unknown_host_is_reported_not_silently_trusted(tmp_path: Path) -> None:
    """Accepting a host key is a trust decision, and a tool that makes it
    silently on a reader's behalf has taken something from them they did
    not know they had. With `BatchMode` the probe fails instead - so the
    failure has to carry the way out, or it is just a dead end.
    """
    _write_keypair(tmp_path)
    runner = FakeRunner(
        _agent(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)")
        | {"ssh": CommandResult(255, stderr="Host key verification failed.")}
    )
    result = next(s for s in STAGES if s.id == "ssh-upload").check(
        _context(tmp_path, runner=runner)
    )
    assert result.status is Status.WRONG
    assert "not a known host" in result.detail
    # The point of this test is that the fingerprint is never accepted
    # silently - not that the reader is told to go and do it elsewhere.
    # Bootstrap now offers to run `ssh -T` with the terminal handed over,
    # so ssh asks its own question and the reader still answers it.
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path, runner=runner))
    assert plan.needs_terminal
    assert "-o BatchMode=yes" not in " ".join(plan.commands[0])
    assert "yes" not in " ".join(plan.commands[0]), "nothing answers it on their behalf"


def test_every_ssh_command_any_stage_runs_is_non_interactive(tmp_path: Path) -> None:
    """The invariant, rather than the two instances of it.

    `ssh -T` was fixed once already and `git ls-remote` - which runs ssh
    underneath - had exactly the same hang waiting in stage 6. Asserting
    per-command would have caught the first and missed the second.
    """
    context = _context(tmp_path, runner=FakeRunner())
    for stage in STAGES:
        for command in stage.plan(context).commands:
            if command[0] == "ssh":
                assert "BatchMode=yes" in command, f"{stage.id}: {command}"


def test_the_real_runner_tells_git_not_to_ask_either(tmp_path: Path) -> None:
    """git prompts for HTTPS credentials on its own and runs ssh for
    everything else, so `git ls-remote` and `git clone` inherit the same
    hang. Checked against the real runner and a real child process: the
    environment is the only thing carrying this, and a fake runner would
    never notice it had been dropped.
    """
    import sys

    from prodockit.bootstrap.model import SubprocessRunner

    script = (
        "import os; print(os.environ.get('GIT_TERMINAL_PROMPT'), os.environ.get('GIT_SSH_COMMAND'))"
    )
    result = SubprocessRunner().run([sys.executable, "-c", script])
    assert result.ok
    assert result.stdout.startswith("0 ssh ")
    assert "BatchMode=yes" in result.stdout


def test_a_readers_own_ssh_wrapper_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Someone who has configured `GIT_SSH_COMMAND` has a reason. Silently
    replacing it would break a working setup to fix a hypothetical one."""
    import sys

    from prodockit.bootstrap.model import SubprocessRunner

    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -i /keys/mine")
    result = SubprocessRunner().run(
        [sys.executable, "-c", "import os; print(os.environ['GIT_SSH_COMMAND'])"]
    )
    assert result.stdout.strip() == "ssh -i /keys/mine"


# ---------------------------------------------------------------------------
# The clone commits under the identity the reader gave
# (prodockit-extensions#222)
# ---------------------------------------------------------------------------


def _clone(tmp_path: Path) -> Path:
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    return project


def _identity_check(tmp_path: Path, runner: FakeRunner) -> object:
    return next(s for s in STAGES if s.id == "identity").check(_context(tmp_path, runner=runner))


def test_a_global_identity_does_not_satisfy_the_project_identity(tmp_path: Path) -> None:
    """Regression: bootstrap asked for an email, stored it, and never
    applied it.

    `git config user.email` inside a repository falls back to the global
    value, so a check written that way passes on any machine with any
    identity at all. Every stage reported `ok` while commits went out
    under a GitHub noreply address - and on Surrey's GitLab an author
    address that matches no account is not linked to one, so coursework
    can show as authored by an unrecognised user.

    `--local` is what makes the question the right question.
    """
    _clone(tmp_path)
    runner = FakeRunner({"config --local": CommandResult(0, "\n")})
    result = _identity_check(tmp_path, runner)
    assert result.status is Status.MISSING

    asked = [call for call in runner.calls if "config" in call]
    assert asked, "the stage never asked git anything"
    for call in asked:
        assert "--local" in call, f"a global lookup cannot answer this: {call}"


def test_a_different_identity_names_both_values(tmp_path: Path) -> None:
    """ "Wrong" without saying what it is leaves the reader to go and find
    out with a command they would have to know already."""
    _clone(tmp_path)
    runner = FakeRunner(
        {
            "config --local user.name": CommandResult(0, "Ada Lovelace\n"),
            "config --local user.email": CommandResult(
                0, "53193258+someone@users.noreply.github.com\n"
            ),
        }
    )
    result = _identity_check(tmp_path, runner)
    assert result.status is Status.WRONG
    assert "53193258+someone@users.noreply.github.com" in result.detail
    assert "al01234@surrey.ac.uk" in result.detail


def test_the_matching_identity_is_ok(tmp_path: Path) -> None:
    _clone(tmp_path)
    runner = FakeRunner(
        {
            "config --local user.name": CommandResult(0, "Ada Lovelace\n"),
            "config --local user.email": CommandResult(0, "al01234@surrey.ac.uk\n"),
        }
    )
    assert _identity_check(tmp_path, runner).status is Status.OK


def test_the_identity_is_set_on_the_clone_never_globally(tmp_path: Path) -> None:
    """A global `user.email` is a legitimate personal preference, and a
    tool that sets up one university project has no business rewriting
    the identity someone uses for everything else."""
    project = _clone(tmp_path)
    plan = next(s for s in STAGES if s.id == "identity").plan(
        _context(tmp_path, runner=FakeRunner())
    )
    assert plan.cwd == str(project)
    assert plan.commands == [
        ["git", "config", "--local", "user.name", "Ada Lovelace"],
        ["git", "config", "--local", "user.email", "al01234@surrey.ac.uk"],
    ]
    for command in plan.commands:
        assert "--global" not in command


def test_the_identity_stage_waits_for_a_clone(tmp_path: Path) -> None:
    """It runs *in* the project, so before one exists there is nothing to
    report but its absence - not a failure."""
    result = _identity_check(tmp_path, FakeRunner())
    assert result.status is Status.MISSING
    assert "no clone" in result.detail


def test_the_help_text_does_not_claim_a_stale_stage_count(cli_bootstrap) -> None:
    """0.23.0 shipped with `--help` still saying "ten stages" a release
    after there were eleven, found by reading the help of a real install
    rather than by anything in this suite. A number written in prose
    drifts the moment the list behind it changes, so it is asserted
    against the list."""
    result = cli_bootstrap("--help")
    assert f"all {len(STAGES)} stages" in result.output


# ---------------------------------------------------------------------------
# Ubuntu automation (prodockit-extensions#229)
# ---------------------------------------------------------------------------


def test_ubuntu_pandoc_is_downloaded_not_apt_installed(tmp_path: Path) -> None:
    """Ubuntu's own pandoc package is several major versions behind -
    far enough to change how the PDF renders (#207). The CI workflows
    and the User Guide both download the pinned release from GitHub
    releases, and bootstrap must do the same.

    `apt install pandoc` would give you 2.x on some LTS releases, which
    renders code blocks as justified prose."""
    context = _context(tmp_path, platform=UBUNTU)
    plan = next(s for s in STAGES if s.id == "pandoc").plan(context)
    joined = " ".join(" ".join(cmd) for cmd in plan.commands)
    assert "github.com/jgm/pandoc/releases" in joined
    # The architecture-detection command, so arm64 and amd64 both work.
    assert "dpkg --print-architecture" in joined
    # Should NOT install pandoc from apt.
    assert "apt install" not in joined or "pandoc.deb" in joined


def test_ubuntu_pandoc_version_is_pinned(tmp_path: Path) -> None:
    """The version in the download URL must match the constant, which
    tracks the CI pin."""
    from prodockit.bootstrap.stages import PANDOC_VERSION

    context = _context(tmp_path, platform=UBUNTU)
    plan = next(s for s in STAGES if s.id == "pandoc").plan(context)
    joined = " ".join(" ".join(cmd) for cmd in plan.commands)
    assert PANDOC_VERSION in joined


def test_pandoc_too_old_is_wrong_not_ok(tmp_path: Path) -> None:
    """Ubuntu's apt pandoc is often 2.x. A check that only asks "is
    pandoc installed?" passes on those, and the first `prodockit pdf`
    fails with justified prose where code blocks should be (#207)."""
    runner = FakeRunner({"pandoc": CommandResult(0, "pandoc 2.17.1.1\n")})
    result = next(s for s in STAGES if s.id == "pandoc").check(_context(tmp_path, runner=runner))
    assert result.status is Status.WRONG
    assert "too old" in result.detail


def test_old_windows_pandoc_is_an_explicit_pinned_upgrade(tmp_path: Path) -> None:
    runner = FakeRunner({"pandoc --version": CommandResult(0, "pandoc 2.19.2\n")})

    plan = next(s for s in STAGES if s.id == "pandoc").plan(
        _context(tmp_path, platform=WINDOWS, runner=runner)
    )
    command = plan.commands[0]

    assert command[:4] == ["winget", "upgrade", "--id", "JohnMacFarlane.Pandoc"]
    assert command[command.index("--version") + 1] == PANDOC_VERSION
    assert plan.destructive
    assert plan.describe.startswith("Upgrade Pandoc")


def test_pandoc_current_version_is_ok(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            "pandoc": CommandResult(0, "pandoc 3.10.1\n"),
            "fc-list": CommandResult(0, "Inter\nJetBrains Mono\n"),
        }
    )
    result = next(s for s in STAGES if s.id == "pandoc").check(_context(tmp_path, runner=runner))
    assert result.status is Status.OK
    assert "3.10.1" in result.detail


def test_ubuntu_pango_libraries_are_still_installed(tmp_path: Path) -> None:
    """WeasyPrint needs Pango et al. These are separate from pandoc -
    pandoc doesn't depend on them, and neither does the .deb from GitHub
    releases. They must still be installed."""
    context = _context(tmp_path, platform=UBUNTU)
    plan = next(s for s in STAGES if s.id == "pandoc").plan(context)
    joined = " ".join(" ".join(cmd) for cmd in plan.commands)
    assert "libpango-1.0-0" in joined
    assert "libpangoft2-1.0-0" in joined
    assert "libharfbuzz-subset0" in joined


def test_ubuntu_git_plan_runs_apt_update_first(tmp_path: Path) -> None:
    """A clean Ubuntu install's package index may be empty. `apt install`
    without a prior `apt update` can fail to find the package."""
    context = _context(tmp_path, platform=UBUNTU)
    plan = next(s for s in STAGES if s.id == "git").plan(context)
    # First command must be the update.
    assert plan.commands[0][:2] == ["sudo", "apt"]
    assert plan.commands[0][-1] == "update"


def test_ubuntu_node_installs_curl_first(tmp_path: Path) -> None:
    """A clean Ubuntu install does not necessarily have `curl`. Without
    it the NodeSource setup command fails, and the `apt install nodejs`
    on the next line still succeeds - quietly fitting Ubuntu's own older
    Node.js instead of NodeSource's. You then have node without npm and
    the toolchains fail for an apparently unrelated reason."""
    context = _context(tmp_path, platform=UBUNTU)
    plan = next(s for s in STAGES if s.id == "node").plan(context)
    first_install = plan.commands[0]
    assert "curl" in first_install


def test_current_node_is_not_reinstalled_when_only_toolchains_are_missing(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        {
            "node --version": CommandResult(0, "v22.14.0\n"),
            "npm --version": CommandResult(0, "10.9.2\n"),
        }
    )

    plan = next(s for s in STAGES if s.id == "node").plan(
        _context(tmp_path, platform=WINDOWS, runner=runner)
    )

    assert not any(command[0] == "winget" for command in plan.commands)
    assert len([command for command in plan.commands if "ci" in command]) == 2


def test_old_windows_node_is_an_explicit_upgrade_not_an_install(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            "node --version": CommandResult(0, "v18.20.0\n"),
            "npm --version": CommandResult(0, "10.9.2\n"),
        }
    )

    plan = next(s for s in STAGES if s.id == "node").plan(
        _context(tmp_path, platform=WINDOWS, runner=runner)
    )

    assert plan.commands[0][:4] == ["winget", "upgrade", "--id", "OpenJS.NodeJS.LTS"]
    assert plan.destructive, "the upgrade must default to No until explicitly approved"
    assert plan.describe.startswith("Upgrade Node")


def test_windows_node_without_npm_uses_repair_not_reinstall(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            "node --version": CommandResult(0, "v22.14.0\n"),
            "npm --version": CommandResult(127, stderr="not found"),
        }
    )

    plan = next(s for s in STAGES if s.id == "node").plan(
        _context(tmp_path, platform=WINDOWS, runner=runner)
    )

    assert plan.commands[0][:4] == ["winget", "repair", "--id", "OpenJS.NodeJS.LTS"]
    assert plan.destructive, "repairing an existing runtime needs explicit approval"
    assert plan.describe.startswith("Repair the existing Node")


# ---------------------------------------------------------------------------
# A plan with both commands and instructions must run the commands
# (prodockit-extensions#230)
# ---------------------------------------------------------------------------


def test_vscode_plan_runs_brew_before_showing_shell_command_instruction(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: when a plan had both commands and instructions, only
    the instructions were shown and the commands were skipped entirely.
    The VS Code stage on macOS is the canonical case: `brew install` is
    automated, but the shell-command install that follows needs a human
    in the application. Showing only the instruction left VS Code not
    installed at all (#230).
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.bootstrap.stages._vscode_app_installed", lambda ctx: False)
    save(tmp_path / "b.toml", _config())
    # `brew install` succeeds but `code` is still not on PATH — the
    # shell-command step is the remaining manual part. The key is
    # `code --version` not bare `code`, because "code" is a substring
    # of "visual-studio-code" and the fragment matcher would pick it
    # as a match for the brew command.
    result = cli_bootstrap(
        "--apply",
        responses={
            "code --version": CommandResult(127, stderr="not found"),
            "brew": CommandResult(0),
        },
        input="y\n" * 3 + "n\n" * 20,
    )
    assert "Will run:" in result.output
    # The old bug: only the instruction appeared, no commands at all.
    assert "brew install --cask visual-studio-code" in result.output
    assert "Shell Command" in result.output
    # Asserted as an *order*, not as two separate appearances: the point
    # of a follow-up is that it comes after the install it depends on,
    # and "both strings are present somewhere" would hold either way.
    assert result.output.index("brew install --cask") < result.output.index("Shell Command"), (
        "the Command Palette step must come after the install that provides it"
    )
    assert "commands ran" in result.output


def test_a_preparing_instruction_is_shown_before_the_command_that_needs_it(
    tmp_path: Path,
) -> None:
    """The mirror image of the VS Code case above, and the half that #234
    broke: some manual steps *precede* their commands.

    The keypair stage is the remaining example - it warns about the
    passphrase prompt before running the `ssh-keygen` that raises it, so
    a reader who has already been asked for a passphrase has missed the
    only advice about choosing one.
    """
    keypair = next(s for s in STAGES if s.id == "ssh-key").plan(_context(tmp_path))
    assert "passphrase" in " ".join(keypair.instructions)
    assert any("ssh-keygen" in " ".join(command) for command in keypair.commands)
    assert not keypair.follow_up, "the warning precedes the prompt, so it is not a follow-up"
    assert keypair.needs_terminal, "the passphrase prompt must not be hidden by a spinner"


def test_dry_run_lists_manual_steps_in_the_order_they_happen(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--dry-run` is how a plan is reviewed before it is trusted, so it
    has to show a follow-up *after* the commands rather than lumping
    every manual step at the top regardless of when it happens."""
    monkeypatch.setattr("prodockit.bootstrap.stages._vscode_app_installed", lambda ctx: False)
    save(tmp_path / "b.toml", _config())

    result = cli_bootstrap("--dry-run", responses={"code --version": CommandResult(127)})

    assert "run: brew install --cask visual-studio-code" in result.output
    assert result.output.index("run: brew install --cask") < result.output.index(
        "you: In VS Code, open the Command Palette"
    ), "a follow-up must be listed after the command it follows"


def test_ubuntu_vscode_is_downloaded_rather_than_asked_for(tmp_path: Path) -> None:
    """#233: the Ubuntu plan told the reader to fetch a .deb from the
    website and then ran `sudo apt install -y ./code.deb`.

    No such file exists under that name. The download is called
    `code_1.132.0-…_arm64.deb` and it lands in ~/Downloads, not the
    working directory - so the command failed on every machine, whether
    or not the reader had done their half.
    """
    plan = next(s for s in STAGES if s.id == "vscode").plan(_context(tmp_path, platform=UBUNTU))
    flat = " ".join(" ".join(command) for command in plan.commands)

    assert "./code.deb" not in flat, "the file was never there to install"
    assert not plan.instructions and not plan.follow_up, "nothing here needs a human now"
    assert "update.code.visualstudio.com" in flat
    # curl is not on a minimal Ubuntu, and the download is the whole step.
    assert flat.index("install -y curl") < flat.index("curl -fsSL")
    # The architecture is resolved when the plan is built, so the command
    # names it outright rather than working it out in a shell (#287).
    assert "dpkg --print-architecture" not in flat
    assert "linux-deb-x64/stable" in flat


def test_ubuntu_vscode_installs_the_file_it_just_downloaded(tmp_path: Path) -> None:
    """The download path and the install path have to be the same one -
    the previous plan's did not, which is the whole of #233."""
    plan = next(s for s in STAGES if s.id == "vscode").plan(_context(tmp_path, platform=UBUNTU))
    download = next(c for c in plan.commands if c[0] == "curl")
    install = next(c for c in plan.commands if c[-1] == "/tmp/code.deb")

    assert "/tmp/code.deb" in download
    assert install[:2] == ["sudo", "apt"]
    # The install must come after the download that produces the file.
    assert plan.commands.index(download) < plan.commands.index(install)


def test_a_warning_is_not_reported_as_the_reason_a_command_failed() -> None:
    """#233: apt opens with a warning every time it is run from a script,
    so the failure was reported as

        failed: WARNING: apt does not have a stable CLI interface.

    which describes nothing that went wrong and points the reader at
    their own scripting rather than at the missing file."""
    from prodockit.cli import _first_meaningful_line

    stderr = (
        "WARNING: apt does not have a stable CLI interface. "
        "Use with caution in scripts.\n"
        "\n"
        "E: Unsupported file ./code.deb given on commandline\n"
    )
    assert _first_meaningful_line(stderr) == "E: Unsupported file ./code.deb given on commandline"


def test_a_warning_is_still_reported_when_it_is_all_there_is() -> None:
    """Skipping warnings must not turn a warning-only failure into
    silence - "no output" would be worse than the warning."""
    from prodockit.cli import _first_meaningful_line

    assert _first_meaningful_line("WARNING: something odd\n") == "WARNING: something odd"


# ---------------------------------------------------------------------------
# What a real Ubuntu run found: #242, #243, #244
# ---------------------------------------------------------------------------


def test_no_extensions_installed_is_missing_not_wrong(tmp_path: Path) -> None:
    """prodockit-extensions#242: with none of the three installed, the
    prompt read `Run 3 commands? [y/N]` - pressing Enter declined the
    install the reader ran bootstrap to get.

    The default follows the status, and WRONG defaults to no because
    reapplying over something can destroy work. With nothing installed
    there is nothing to destroy, so this is MISSING."""
    runner = FakeRunner({"code --list-extensions": CommandResult(0, "")})
    result = next(s for s in STAGES if s.id == "extensions").check(
        _context(tmp_path, runner=runner)
    )

    assert result.status is Status.MISSING
    assert f"0 of {len(VSCODE_EXTENSIONS)} installed" in result.detail


def test_some_extensions_installed_is_still_wrong(tmp_path: Path) -> None:
    """A partly-set-up VS Code is present but not right, which is what
    WRONG means - and asking before touching an existing setup is the
    behaviour that case was given deliberately."""
    present = "\n".join(VSCODE_EXTENSIONS[:1])
    runner = FakeRunner({"code --list-extensions": CommandResult(0, present)})
    result = next(s for s in STAGES if s.id == "extensions").check(
        _context(tmp_path, runner=runner)
    )

    assert result.status is Status.WRONG
    assert f"1 of {len(VSCODE_EXTENSIONS)} installed" in result.detail


def test_the_extensions_prompt_defaults_to_yes_on_a_bare_machine(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end of #242 as the reader met it: the prompt itself."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    # Everything else already set up, so the extensions stage is the one
    # doing the asking. An earlier version of this test asserted against
    # `Run 3 commands?` on a bare machine and was in fact reading the
    # *git* stage's prompt, which happened to have three commands too.
    responses = _ready_machine(tmp_path)
    responses["code --list-extensions"] = CommandResult(0, "")

    result = cli_bootstrap("--apply", responses=responses, input="\n" * 40)

    assert "VS Code extensions" in result.output
    count = len(VSCODE_EXTENSIONS)
    assert f"Run {count} commands? [Y/n]" in result.output
    assert f"Run {count} commands? [y/N]" not in result.output


def test_every_apt_command_waits_for_the_dpkg_lock(tmp_path: Path) -> None:
    """prodockit-extensions#244: apt fails rather than waits when another
    process holds the dpkg lock, and on a fresh Ubuntu that is usually
    `unattended-upgrades` running on boot. The reader got

        Error: Unable to acquire the dpkg frontend lock

    which reads as a broken machine rather than "wait a moment"."""
    context = _context(tmp_path, platform=UBUNTU)
    seen = 0
    for stage in STAGES:
        for command in stage.plan(context).commands:
            # The apt *executable*, not the string "apt" anywhere - a
            # tmp_path carries the test's own name, which contains it.
            if list(command[:2]) != ["sudo", "apt"]:
                continue
            seen += 1
            assert "DPkg::Lock::Timeout" in " ".join(command), f"{stage.id}: {command}"
    assert seen >= 4, "the Ubuntu plans should have several apt commands between them"


def test_pdkboot_keeps_privileged_apt_out_of_download_shells(tmp_path: Path) -> None:
    """A download failure and a privileged install have separate outcomes.

    This also keeps sudo at the front of its own command, where pdkboot can
    authenticate before the timed, captured installer starts.
    """
    context = _context(tmp_path, platform=UBUNTU)
    for stage_id in ("pandoc",):
        plan = next(s for s in STAGES if s.id == stage_id).plan(context)
        script = next(c for c in plan.commands if c[0] == "bash")[-1]
        assert "sudo" not in script, stage_id
        install = next(c for c in plan.commands if c[-1] == "/tmp/pandoc.deb")
        assert install[:2] == ["sudo", "apt"]
        assert "DPkg::Lock::Timeout" in " ".join(install)


def test_an_install_gets_longer_than_a_check(tmp_path: Path) -> None:
    """prodockit-extensions#243: VS Code's .deb is around 100 MB, and the
    download plus `apt install` behind it ran past the 300 second limit a
    *check* is held to. The run was killed and reported as failed while
    the install it started went on to succeed - "failed" printed next to
    a working VS Code."""
    from prodockit.bootstrap import INSTALL_TIMEOUT_SECONDS, apply_stage
    from prodockit.bootstrap.model import CHECK_TIMEOUT_SECONDS

    assert INSTALL_TIMEOUT_SECONDS > CHECK_TIMEOUT_SECONDS

    runner = FakeRunner({"brew": CommandResult(0), "code": CommandResult(0)})
    context = _context(tmp_path, runner=runner)
    apply_stage(context, next(s for s in STAGES if s.id == "vscode"))

    ran = [t for t in runner.timeouts if t is not None]
    assert ran, "an applied command must carry a timeout"
    assert all(t == INSTALL_TIMEOUT_SECONDS for t in ran)


def test_a_timeout_is_reported_in_the_readers_terms() -> None:
    """The default rendering is the whole command list repr with the one
    useful fact at the end of it. What the reader needs to know is that
    it may still be running and a rerun is safe."""
    import subprocess

    from prodockit.bootstrap.model import SubprocessRunner

    runner = SubprocessRunner()
    original = subprocess.run

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["sudo", "apt", "install"], timeout=1800)

    subprocess.run = _timeout
    try:
        result = runner.run(["sudo", "apt", "install", "-y", "git"])
    finally:
        subprocess.run = original

    assert not result.ok
    assert "1800 seconds" in result.stderr
    assert "again" in result.stderr
    assert "TimeoutExpired" not in result.stderr


def test_sudo_is_recognised_at_the_front_and_inside_a_shell_string() -> None:
    """The privileged call is at the head of the list in most plans and
    buried in a `bash -c` script in two of them - both have to count, or
    the password prompt lands back inside the timed subprocess."""
    from prodockit.bootstrap import needs_sudo

    assert needs_sudo([["sudo", "apt", "install", "-y", "git"]])
    assert needs_sudo([["bash", "-c", "curl ... && sudo apt install -y /tmp/code.deb"]])
    assert not needs_sudo([["brew", "install", "--cask", "visual-studio-code"]])
    assert not needs_sudo([])


def test_sudo_is_asked_for_before_the_commands_run(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asked here, where there is a terminal, rather than inside a
    captured subprocess whose clock is running (#243)."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    asked: list[bool] = []
    monkeypatch.setattr("prodockit.cli.authenticate_sudo", lambda: (asked.append(True), True)[1])
    monkeypatch.setattr("prodockit.bootstrap.stages._vscode_app_installed", lambda ctx: False)
    save(tmp_path / "b.toml", _config())

    result = cli_bootstrap(
        "--apply",
        responses={"code --version": CommandResult(127)},
        input="\n" * 40,
        platform=UBUNTU,
    )

    assert asked, "the privileged plan must authenticate before running"
    # After the reader has agreed to run the commands, and before they
    # run: the whole point is that the password question happens outside
    # the subprocess being timed.
    assert result.output.index("Will run:") < result.output.index("administrator rights")


def test_a_plan_that_needs_no_sudo_is_not_asked_for_a_password(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """macOS installs VS Code with brew, which needs no privileges -
    prompting for a password regardless would train the reader to type
    one whenever bootstrap asks."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    asked: list[bool] = []
    monkeypatch.setattr("prodockit.cli.authenticate_sudo", lambda: (asked.append(True), True)[1])
    monkeypatch.setattr("prodockit.bootstrap.stages._vscode_app_installed", lambda ctx: False)
    save(tmp_path / "b.toml", _config())

    result = cli_bootstrap(
        "--apply",
        responses={"code --version": CommandResult(127), "brew": CommandResult(0)},
        input="\n" * 40,
    )

    assert asked == []
    assert "administrator rights" not in result.output


# ---------------------------------------------------------------------------
# The key has to be usable, not just present: #246
# ---------------------------------------------------------------------------


def _agent(returncode: int, listing: str = "") -> dict[str, CommandResult]:
    """An `ssh-add -l` answer, plus a fingerprint for the key on disk."""
    return {
        "ssh-add -l": CommandResult(returncode, listing),
        "ssh-keygen -lf": CommandResult(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)"),
    }


def test_no_agent_running_is_missing(tmp_path: Path) -> None:
    """prodockit-extensions#246: stage 3 tells the reader to give the key
    a passphrase, and every ssh command carries `BatchMode=yes`, which
    forbids prompting. Those two are only compatible if an agent holds
    the decrypted key - otherwise `ssh -T` offers the public half quite
    happily and then cannot sign the challenge, and the upload stage
    reports a key that is fine and uploaded as *rejected*."""
    runner = FakeRunner(_agent(2, "Could not open a connection to your agent."))
    result = next(s for s in STAGES if s.id == "ssh-agent").check(_context(tmp_path, runner=runner))

    assert result.status is Status.MISSING
    assert "no ssh agent is running" in result.detail


def test_an_empty_agent_is_missing(tmp_path: Path) -> None:
    runner = FakeRunner(_agent(1, "The agent has no identities."))
    result = next(s for s in STAGES if s.id == "ssh-agent").check(_context(tmp_path, runner=runner))

    assert result.status is Status.MISSING
    assert "not loaded" in result.detail


def test_somebody_elses_key_in_the_agent_does_not_count(tmp_path: Path) -> None:
    """An agent holding a *different* key authenticates nothing here, and
    "the agent has keys" would report it as done."""
    runner = FakeRunner(_agent(0, "256 SHA256:SomeOtherKeyEntirely me@elsewhere (ED25519)"))
    result = next(s for s in STAGES if s.id == "ssh-agent").check(_context(tmp_path, runner=runner))

    assert result.status is Status.MISSING


def test_the_loaded_key_is_ok(tmp_path: Path) -> None:
    runner = FakeRunner(_agent(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)"))
    result = next(s for s in STAGES if s.id == "ssh-agent").check(_context(tmp_path, runner=runner))

    assert result.status is Status.OK
    assert "id_ed25519_gitlab" in result.detail


def test_no_key_yet_is_not_a_crash(tmp_path: Path) -> None:
    """`--dry-run` builds every plan, including on a machine where the
    keypair stage has not run - so a missing key must be a finding."""
    runner = FakeRunner({"ssh-add -l": CommandResult(1, "The agent has no identities.")})
    result = next(s for s in STAGES if s.id == "ssh-agent").check(_context(tmp_path, runner=runner))

    assert result.status is Status.MISSING
    assert "no key" in result.detail


def test_the_agent_stage_runs_before_the_upload(tmp_path: Path) -> None:
    """Same reasoning as the config stage: the upload stage checks itself
    with `ssh -T`, which cannot sign anything until the key is loaded."""
    ids = [s.id for s in STAGES]

    assert ids.index("ssh-agent") > ids.index("ssh-key"), "there must be a key to load"
    assert ids.index("ssh-agent") < ids.index("ssh-upload")


def test_loading_the_key_takes_the_terminal(tmp_path: Path) -> None:
    """`ssh-add` asks for the passphrase and reads it from /dev/tty. Run
    with its output captured it would wait, unanswerable, until the
    timeout - which is exactly what sudo did in #243."""
    runner = FakeRunner(_agent(1, "The agent has no identities."))
    plan = next(s for s in STAGES if s.id == "ssh-agent").plan(_context(tmp_path, runner=runner))

    assert plan.needs_terminal, "the passphrase prompt needs somewhere to appear"
    assert plan.commands == [
        ["ssh-add", "--apple-use-keychain", str(tmp_path / ".ssh" / "id_ed25519_gitlab")]
    ]


def test_macos_stores_the_passphrase_in_the_keychain(tmp_path: Path) -> None:
    """Without the flag `ssh-add` loads the key for this session only, so
    the agent is empty again after the next reboot and bootstrap has to
    repair something it already reported as done (#303)."""
    runner = FakeRunner(_agent(1, "The agent has no identities."))
    plan = next(s for s in STAGES if s.id == "ssh-agent").plan(_context(tmp_path, runner=runner))

    assert plan.commands[0][:2] == ["ssh-add", "--apple-use-keychain"]


@pytest.mark.parametrize("platform", [UBUNTU, WINDOWS])
def test_the_keychain_flag_is_macos_only(tmp_path: Path, platform: str) -> None:
    """No other platform has an equivalent, and `ssh-add` rejects the
    unknown option rather than ignoring it - which would turn a working
    stage into a failing one."""
    runner = FakeRunner(_agent(1, "The agent has no identities."))
    plan = next(s for s in STAGES if s.id == "ssh-agent").plan(
        _context(tmp_path, platform=platform, runner=runner)
    )

    assert plan.commands == [["ssh-add", str(tmp_path / ".ssh" / "id_ed25519_gitlab")]]


def test_apply_hands_the_terminal_over_for_that_plan(tmp_path: Path) -> None:
    """The flag is no use unless the runner is actually told."""
    from prodockit.bootstrap import apply_stage

    runner = FakeRunner(_agent(1, "The agent has no identities."))
    context = _context(tmp_path, runner=runner)
    apply_stage(context, next(s for s in STAGES if s.id == "ssh-agent"))

    assert False in runner.captures, "ssh-add must be run uncaptured"


def test_starting_an_agent_is_explained_rather_than_attempted(tmp_path: Path) -> None:
    """The one thing here that genuinely cannot be automated. `eval
    "$(ssh-agent -s)"` works by exporting SSH_AUTH_SOCK into the shell
    that runs it, and a subprocess cannot export into its parent - so
    running it would start an agent, set the variable in a shell that
    then exits, and change nothing."""
    runner = FakeRunner(_agent(2, "Could not open a connection to your agent."))
    plan = next(s for s in STAGES if s.id == "ssh-agent").plan(_context(tmp_path, runner=runner))

    assert not plan.commands, "bootstrap cannot start an agent for its own parent shell"
    joined = "\n".join(plan.instructions)
    assert 'eval "$(ssh-agent -s)"' in joined
    assert "same terminal" in joined


def test_windows_is_told_about_the_service_instead(tmp_path: Path) -> None:
    """Windows service elevation is visible and remains inside pdkboot."""
    runner = FakeRunner(_agent(2, "Could not open a connection to your agent."))
    plan = next(s for s in STAGES if s.id == "ssh-agent").plan(
        _context(tmp_path, runner=runner, platform=WINDOWS)
    )
    joined = "\n".join(plan.instructions)
    commands = "\n".join(" ".join(command) for command in plan.commands)

    assert "UAC" in joined
    assert "Start-Service ssh-agent" in commands
    assert "-Verb RunAs" in commands
    assert "ssh-agent -s" not in commands, "that is the Unix route"


# ---------------------------------------------------------------------------
# Closing the gaps against the User Guide: #248
# ---------------------------------------------------------------------------


def test_the_extensions_are_the_ones_the_install_guide_requires() -> None:
    """#248: the list had Code Spell Checker - which comes from the
    *optional* tooling page, opening "You don't need any of this" - in
    place of two the install guide does require."""
    assert VSCODE_EXTENSIONS == (
        "ms-python.python",
        "zensical.zensical-studio",
        "tamasfe.even-better-toml",
        "ltex-plus.vscode-ltex-plus",
    )
    assert "streetsidesoftware.code-spell-checker" not in VSCODE_EXTENSIONS
    # LTeX was renamed: `valentjn.vscode-ltex` 404s, the maintained fork
    # is published under `ltex-plus`. Checked against the marketplace.
    assert "valentjn.vscode-ltex" not in VSCODE_EXTENSIONS


def test_the_template_history_is_reset_only_while_origin_is_the_template(
    tmp_path: Path,
) -> None:
    """The dangerous mistake this stage could make is telling a reader
    who has been working for weeks that their history needs deleting.

    Judging by `origin` makes that impossible: the state is one the
    template clone starts in and can never return to, because resetting
    removes the remote and repointing replaces it."""
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    stage = next(s for s in STAGES if s.id == "fresh-history")

    still_template = FakeRunner(
        {"remote get-url origin": CommandResult(0, SURREY_GITLAB.template_remote)}
    )
    assert stage.check(_context(tmp_path, runner=still_template)).status is Status.WRONG

    their_own = FakeRunner(
        {
            "remote get-url origin": CommandResult(0, "git@gitlab.surrey.ac.uk:x/report.git"),
            "config core.fileMode": CommandResult(0, "false\n"),
        }
    )
    assert stage.check(_context(tmp_path, runner=their_own)).status is Status.OK

    already_reset = FakeRunner({"remote get-url origin": CommandResult(2, stderr="No such remote")})
    assert stage.check(_context(tmp_path, runner=already_reset)).status is Status.OK


def test_deleting_history_is_wrong_not_missing_so_enter_declines(tmp_path: Path) -> None:
    """`--apply` offers MISSING as [Y/n] and WRONG as [y/N]. Deleting a
    repository's history is the last thing that should happen by pressing
    Enter, so the status is chosen for the prompt it produces."""
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    runner = FakeRunner({"remote get-url origin": CommandResult(0, SURREY_GITLAB.template_remote)})
    result = next(s for s in STAGES if s.id == "fresh-history").check(
        _context(tmp_path, runner=runner)
    )

    assert result.status is Status.WRONG, "MISSING would default the prompt to yes"


def test_the_history_reset_preserves_a_recovery_copy(tmp_path: Path) -> None:
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    runner = FakeRunner({"remote get-url origin": CommandResult(0, SURREY_GITLAB.template_remote)})
    plan = next(s for s in STAGES if s.id == "fresh-history").plan(
        _context(tmp_path, runner=runner)
    )
    joined = "\n".join(plan.instructions)
    flat = " ".join(" ".join(c) for c in plan.commands)

    backup = project.parent / ".report-al01234.git.pdk-template-backup"
    assert str(backup) in joined
    assert "recovered" in joined
    assert plan.commands[0] == ["mv", str(project / ".git"), str(backup)]
    assert "git init -b main" in flat
    # From the guide: cloud-sync clients rewrite the executable bit, so a
    # synced project shows every file as modified without a byte changing.
    assert "core.fileMode false" in flat


def test_the_history_reset_never_overwrites_an_existing_recovery_copy(
    tmp_path: Path,
) -> None:
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    (project.parent / ".report-al01234.git.pdk-template-backup").mkdir()
    (project.parent / ".report-al01234.git.pdk-template-backup-2").mkdir()
    runner = FakeRunner({"remote get-url origin": CommandResult(0, SURREY_GITLAB.template_remote)})

    plan = next(s for s in STAGES if s.id == "fresh-history").plan(
        _context(tmp_path, runner=runner)
    )

    assert plan.commands[0][-1] == str(project.parent / ".report-al01234.git.pdk-template-backup-3")


def test_the_windows_history_reset_uses_literal_escaped_paths(tmp_path: Path) -> None:
    project = tmp_path / "GitLab" / "reader's-report"
    (project / ".git").mkdir(parents=True)
    runner = FakeRunner({"remote get-url origin": CommandResult(0, SURREY_GITLAB.template_remote)})

    plan = next(s for s in STAGES if s.id == "fresh-history").plan(
        _context(
            tmp_path,
            platform=WINDOWS,
            runner=runner,
            project_dir=str(project),
        )
    )
    command = plan.commands[0]

    assert command[:3] == ["powershell", "-NoProfile", "-Command"]
    assert "Move-Item -LiteralPath" in command[3]
    assert "reader''s-report" in command[3]
    assert "Remove-Item" not in command[3]


def test_the_history_reset_runs_before_the_remote_is_set() -> None:
    """Resetting deletes .git, remotes included - so doing it after the
    repoint would throw the repoint away."""
    ids = [s.id for s in STAGES]

    assert ids.index("fresh-history") > ids.index("clone")
    assert ids.index("fresh-history") < ids.index("remote")


def test_the_remote_is_added_when_the_reset_left_none(tmp_path: Path) -> None:
    """`git remote set-url` fails with "No such remote 'origin'" on a
    repository `git init` has just created, so the repoint has to add
    rather than set (#248)."""
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    runner = FakeRunner({"remote get-url origin": CommandResult(2, stderr="No such remote")})
    plan = next(s for s in STAGES if s.id == "remote").plan(_context(tmp_path, runner=runner))
    flat = [" ".join(c) for c in plan.commands]

    assert any("remote add origin" in c for c in flat)
    assert not any("set-url" in c for c in flat)


def test_the_project_venv_is_the_one_inside_the_project(tmp_path: Path) -> None:
    """#248: bootstrap runs from a venv that predates the project. The
    guide's is a second one, inside the clone, which is what the VS Code
    Python extension finds and activates."""
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    (project / "requirements.txt").write_text("zensical\n", encoding="utf-8")
    plan = next(s for s in STAGES if s.id == "project-env").plan(_context(tmp_path))
    flat = " ".join(" ".join(c) for c in plan.commands)

    assert str(project / ".venv") in flat
    assert "-m venv" in flat


def test_requirements_are_installed_by_the_projects_own_interpreter(tmp_path: Path) -> None:
    """The trap: a bare `pip install -r requirements.txt` finds whichever
    pip is on PATH - bootstrap's own - installs the project's
    dependencies into bootstrap's environment, exits zero, and leaves the
    project venv empty. Naming the interpreter makes that impossible."""
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    (project / "requirements.txt").write_text("zensical\n", encoding="utf-8")
    plan = next(s for s in STAGES if s.id == "project-env").plan(_context(tmp_path))
    install = next(c for c in plan.commands if "install" in c)

    assert install[0] == str(project / ".venv" / "bin" / "python")
    assert install[1:4] == ["-m", "pip", "install"]
    assert install[-1] == str(project / "requirements.txt")


def test_weasyprint_is_verified_from_the_projects_venv(tmp_path: Path) -> None:
    """#248 gap 1: the pandoc stage was *named* for WeasyPrint's
    libraries and only ever checked pandoc, so it reported ok on a
    machine whose PDF build would fail at `cannot load library`.

    Importing WeasyPrint is the guide's own test, and a strict one: it
    loads Pango through the system linker, so a successful import proves
    both the package and the native libraries."""
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    (project / "requirements.txt").write_text("zensical\n", encoding="utf-8")
    venv_python = project / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    save(tmp_path / "b.toml", _config())

    runner = FakeRunner(
        {
            "import zensical": CommandResult(0),
            "import weasyprint": CommandResult(1, stderr="cannot load library 'libgobject-2.0-0'"),
        }
    )
    result = next(s for s in STAGES if s.id == "project-env").check(
        _context(tmp_path, runner=runner)
    )

    assert result.status is Status.WRONG, "installed but unusable is not missing"
    assert "graphics libraries" in result.detail
    assert "pandoc stage" in result.detail, "point at the fix, not at pip"


def test_windows_weasyprint_failure_names_msys2_not_homebrew(tmp_path: Path) -> None:
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    (project / "requirements.txt").write_text("zensical\n", encoding="utf-8")
    python = project / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    runner = FakeRunner(
        {
            "import zensical": CommandResult(0),
            "import weasyprint": CommandResult(1, stderr="cannot load library"),
        }
    )

    result = next(s for s in STAGES if s.id == "project-env").check(
        _context(tmp_path, platform=WINDOWS, runner=runner)
    )

    assert "MSYS2" in result.detail
    assert "Python's architecture" in result.detail
    assert "Homebrew" not in result.detail


def test_the_pandoc_stage_no_longer_claims_what_it_cannot_check() -> None:
    """It installs the libraries and cannot verify them - importing
    WeasyPrint does that, one stage later. The summary should not promise
    otherwise."""
    pandoc = next(s for s in STAGES if s.id == "pandoc")

    assert "libraries WeasyPrint needs" in pandoc.summary


def test_the_editor_settings_associate_markdown_for_zensical_studio(tmp_path: Path) -> None:
    """#248 gap 5. Zensical Studio needs Markdown handed to its own
    language mode, and the guide has the reader paste this in by hand."""
    project = tmp_path / "GitLab" / "report-al01234"
    project.mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    stage = next(s for s in STAGES if s.id == "vscode-settings")

    assert stage.check(_context(tmp_path)).status is Status.MISSING

    (project / ".vscode").mkdir()
    (project / ".vscode" / "settings.json").write_text(
        '{"files.associations": {"*.md": "python-markdown"}}', encoding="utf-8"
    )
    assert stage.check(_context(tmp_path)).status is Status.OK


def test_the_settings_merge_keeps_what_is_already_there(tmp_path: Path) -> None:
    """`.vscode/settings.json` is the reader's own file, and VS Code
    rewrites it whenever a setting is changed in the UI - so the plan
    merges rather than writes."""
    import subprocess

    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".vscode").mkdir(parents=True)
    settings = project / ".vscode" / "settings.json"
    settings.write_text(
        '{"editor.wordWrap": "on", "files.associations": {"*.foo": "bar"}}', encoding="utf-8"
    )
    save(tmp_path / "b.toml", _config())

    plan = next(s for s in STAGES if s.id == "vscode-settings").plan(_context(tmp_path))
    subprocess.run(plan.commands[0], check=True)

    written = json.loads(settings.read_text(encoding="utf-8"))
    assert written["editor.wordWrap"] == "on", "an unrelated setting must survive"
    assert written["files.associations"]["*.foo"] == "bar", "so must another association"
    assert written["files.associations"]["*.md"] == "python-markdown"


def test_the_settings_plan_preserves_a_file_that_is_not_json(tmp_path: Path) -> None:
    """VS Code tolerates comments and trailing commas in settings.json;
    `json.loads` does not. Failing here would leave the reader with a
    traceback over an editor preference."""
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".vscode").mkdir(parents=True)
    settings = project / ".vscode" / "settings.json"
    settings.write_text("{ // a comment VS Code allows\n}", encoding="utf-8")
    save(tmp_path / "b.toml", _config())

    plan = next(s for s in STAGES if s.id == "vscode-settings").plan(_context(tmp_path))

    assert plan.commands == []
    assert "left unchanged" in " ".join(plan.instructions)
    assert settings.read_text(encoding="utf-8") == "{ // a comment VS Code allows\n}"


def test_the_settings_plan_preserves_a_non_object_document(tmp_path: Path) -> None:
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".vscode").mkdir(parents=True)
    settings = project / ".vscode" / "settings.json"
    settings.write_text('["do", "not", "discard"]', encoding="utf-8")
    save(tmp_path / "b.toml", _config())

    plan = next(s for s in STAGES if s.id == "vscode-settings").plan(_context(tmp_path))

    assert plan.commands == []
    assert "must be a JSON object" in " ".join(plan.instructions)
    assert settings.read_text(encoding="utf-8") == '["do", "not", "discard"]'


def test_the_checker_language_follows_the_machine_not_the_guide(tmp_path: Path) -> None:
    """#248 gap 6: the guide says `en-GB` because that is right for its
    own readers. Bootstrap runs on other people's computers, and a
    document checked against the wrong variety of a language is worse
    than one not checked - the corrections are confident and wrong."""
    project = tmp_path / "GitLab" / "report-al01234"
    project.mkdir(parents=True)
    save(tmp_path / "b.toml", _config())

    american = FakeRunner({"AppleLocale": CommandResult(0, "en_US\n")})
    plan = next(s for s in STAGES if s.id == "vscode-settings").plan(
        _context(tmp_path, runner=american)
    )
    assert '"ltex.language": "en-US"' in plan.commands[0][-1]

    british = FakeRunner({"AppleLocale": CommandResult(0, "en_GB.UTF-8\n")})
    plan = next(s for s in STAGES if s.id == "vscode-settings").plan(
        _context(tmp_path, runner=british)
    )
    assert '"ltex.language": "en-GB"' in plan.commands[0][-1]


def test_an_unreadable_locale_leaves_the_language_unset(tmp_path: Path) -> None:
    """Better than guessing: LTeX+ has a default of its own, and an
    absent value is at least honest about not knowing."""
    project = tmp_path / "GitLab" / "report-al01234"
    project.mkdir(parents=True)
    save(tmp_path / "b.toml", _config())

    for listing in (CommandResult(127, stderr="not found"), CommandResult(0, "C\n")):
        runner = FakeRunner({"AppleLocale": listing})
        plan = next(s for s in STAGES if s.id == "vscode-settings").plan(
            _context(tmp_path, runner=runner)
        )
        assert "ltex.language" not in plan.commands[0][-1]


def test_ubuntu_reads_the_language_from_the_locale_command(tmp_path: Path) -> None:
    """`defaults` is macOS-only; Ubuntu's `locale` prints a block of
    KEY=value lines, of which LANG is the one naming the language."""
    project = tmp_path / "GitLab" / "report-al01234"
    project.mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    runner = FakeRunner(
        {"locale": CommandResult(0, 'LANG=en_GB.UTF-8\nLC_NUMERIC="en_GB.UTF-8"\nLC_ALL=\n')}
    )

    plan = next(s for s in STAGES if s.id == "vscode-settings").plan(
        _context(tmp_path, runner=runner, platform=UBUNTU)
    )

    assert '"ltex.language": "en-GB"' in plan.commands[0][-1]


# ---------------------------------------------------------------------------
# What the User Guide learned on ARM64, carried over: #249
# ---------------------------------------------------------------------------


def test_npm_ci_is_told_not_to_fetch_its_own_chrome(tmp_path: Path) -> None:
    """prodockit-userguide#102: `npm ci` in tools/mermaid triggers
    Puppeteer's postinstall download, and that download is not guaranteed
    to match the CPU it lands on. On ARM64 it fetches an x86_64 Chrome
    that can never run - and nothing fails at install time, so the
    symptom is a diagram that will not render, a long way from the
    command that caused it."""
    context = _context(tmp_path, platform=UBUNTU)
    plan = next(s for s in STAGES if s.id == "node").plan(context)
    flat = [" ".join(c) for c in plan.commands]

    npm = [c for c in flat if "npm ci" in c]
    assert npm, "the toolchains still have to be installed"
    for command in npm:
        assert "PUPPETEER_SKIP_DOWNLOAD=true" in command
        assert "PUPPETEER_EXECUTABLE_PATH=" in command


def test_chromium_is_installed_before_npm_ci_runs(tmp_path: Path) -> None:
    """Ordering is the whole of the fix. Installing Chromium after
    `npm ci` leaves the wasted download already done."""
    context = _context(tmp_path, platform=UBUNTU)
    flat = [" ".join(c) for c in next(s for s in STAGES if s.id == "node").plan(context).commands]

    chromium = next(i for i, c in enumerate(flat) if "chromium-browser" in c)
    first_npm = next(i for i, c in enumerate(flat) if "npm ci" in c)
    assert chromium < first_npm


def test_the_puppeteer_exports_are_appended_only_once(tmp_path: Path) -> None:
    """Bootstrap is rerunnable, and a profile carrying the same two
    exports four times over is the mark of a tool that assumed it was
    not."""
    context = _context(tmp_path, platform=UBUNTU)
    flat = " ".join(
        " ".join(c) for c in next(s for s in STAGES if s.id == "node").plan(context).commands
    )

    assert ".bashrc" in flat, "later sessions need them too, not just this run"
    assert "grep -q" in flat, "appended only when not already there"


def test_other_platforms_are_left_alone(tmp_path: Path) -> None:
    """Puppeteer's own download works on macOS and Windows. Installing a
    system Chromium there would be solving somebody else's problem."""
    for platform in (MACOS, WINDOWS):
        plan = next(s for s in STAGES if s.id == "node").plan(_context(tmp_path, platform=platform))
        flat = " ".join(" ".join(c) for c in plan.commands)
        assert "chromium" not in flat, platform
        assert "PUPPETEER" not in flat, platform


def test_the_pdf_fonts_are_installed_with_the_graphics_stack(tmp_path: Path) -> None:
    """prodockit-userguide#101: the website loads these from a CDN at
    view time, but a PDF has to embed the files - and WeasyPrint
    substitutes a fallback *silently* when they are absent. The build
    succeeds, the PDF looks plausible, and the only symptom is a test
    reporting `No 'Inter' font found`."""
    ubuntu = next(s for s in STAGES if s.id == "pandoc").plan(_context(tmp_path, platform=UBUNTU))
    flat = " ".join(" ".join(c) for c in ubuntu.commands)
    for package in PDF_FONT_PACKAGES:
        assert package in flat

    macos = next(s for s in STAGES if s.id == "pandoc").plan(_context(tmp_path, platform=MACOS))
    flat = " ".join(" ".join(c) for c in macos.commands)
    for cask in PDF_FONT_CASKS:
        assert cask in flat


def test_windows_is_told_to_install_the_fonts_by_hand(tmp_path: Path) -> None:
    """There is no cask or apt on Windows, and the guide has the reader
    download and right-click them - so it is an instruction, not a
    silently missing step."""
    plan = next(s for s in STAGES if s.id == "pandoc").plan(_context(tmp_path, platform=WINDOWS))
    joined = "\n".join(plan.follow_up)

    assert "Inter" in joined and "JetBrains Mono" in joined


def test_the_citation_style_is_fetched_because_the_first_build_needs_it(tmp_path: Path) -> None:
    """prodockit-userguide#103: `prodockit.bibliography` is enabled by
    default and points at a file the clone does not contain, so
    `zensical serve`, `zensical build` and `prodockit pdf` all fail
    outright until it is fetched."""
    project = tmp_path / "GitLab" / "report-al01234"
    project.mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    stage = next(s for s in STAGES if s.id == "csl-style")

    assert stage.check(_context(tmp_path)).status is Status.MISSING

    flat = " ".join(" ".join(c) for c in stage.plan(_context(tmp_path)).commands)
    assert "zotero.org/styles/harvard-cite-them-right" in flat
    assert DEFAULT_CSL_STYLE in flat

    (project / DEFAULT_CSL_STYLE).write_text("<style/>", encoding="utf-8")
    assert stage.check(_context(tmp_path)).status is Status.OK


def test_an_empty_style_file_is_wrong_not_done(tmp_path: Path) -> None:
    """A failed download leaves an empty file behind, and anything asking
    only whether the path exists would call that finished."""
    project = tmp_path / "GitLab" / "report-al01234"
    project.mkdir(parents=True)
    (project / DEFAULT_CSL_STYLE).write_text("", encoding="utf-8")
    save(tmp_path / "b.toml", _config())

    result = next(s for s in STAGES if s.id == "csl-style").check(_context(tmp_path))

    assert result.status is Status.WRONG
    assert "did not complete" in result.detail


def test_a_project_asking_for_another_style_is_not_given_this_one(tmp_path: Path) -> None:
    """`csl_style` is configurable, and fetching Harvard over somebody's
    chosen IEEE would be worse than saying so."""
    project = tmp_path / "GitLab" / "report-al01234"
    project.mkdir(parents=True)
    (project / "zensical.toml").write_text('csl_style = "ieee.csl"\n', encoding="utf-8")
    save(tmp_path / "b.toml", _config())
    context = _context(tmp_path)

    assert "ieee.csl" in next(s for s in STAGES if s.id == "csl-style").check(context).detail
    plan = next(s for s in STAGES if s.id == "csl-style").plan(context)
    assert not plan.commands, "bootstrap only knows where the default one lives"
    assert "ieee.csl" in "\n".join(plan.instructions)


# ---------------------------------------------------------------------------
# The invariant itself: #224
# ---------------------------------------------------------------------------


#: What each stage's plan produces, and how to describe a machine that is
#: missing exactly that one thing.
#:
#: The entry is the point. Writing one forces the question "can this
#: stage's check see this?", which is the question nobody asked when
#: fonts were added to a plan with no font check, and Chromium and the
#: `~/.bashrc` exports were added with neither (#224).
#:
#: `None` means the stage's plan produces nothing a check could observe -
#: the two browser steps, where a human does the work elsewhere. Stated
#: rather than omitted, so silence is never the reason a stage escapes.
def test_a_python_that_cannot_build_environments_is_found_before_it_matters(
    tmp_path: Path,
) -> None:
    """prodockit-extensions#381.

    The project's environment is created with `sys.executable -m venv`,
    so the interpreter running bootstrap has to be able to make one.
    Debian and Ubuntu ship `venv` without `ensurepip`, in a package of
    their own - and the failure used to arrive at stage 16, worded as
    though something were wrong with the project rather than with the
    Python that was about to build it.
    """
    stage = next(s for s in STAGES if s.id == "own-venv")
    assert STAGES[0].id == "own-venv", (
        "first of all - it is the prerequisite for the run, not a step in it"
    )

    inside = {"sys.base_prefix": CommandResult(0, "True")}
    able = _context(
        tmp_path, runner=FakeRunner(inside | {"import ensurepip, venv": CommandResult(0)})
    )
    assert stage.check(able).status is Status.OK

    # In an environment, but one that cannot make another.
    unable = _context(
        tmp_path,
        runner=FakeRunner(
            inside | {"import ensurepip, venv": CommandResult(1, stderr="No module")}
        ),
    )
    result = stage.check(unable)
    assert result.status is Status.MISSING
    assert "cannot build the project's environment" in result.detail

    # Not in one at all - the case #381 was raised for. Nothing this run
    # does can change it, so it says so rather than asking again.
    outside = _context(tmp_path, runner=FakeRunner({"sys.base_prefix": CommandResult(0, "False")}))
    system = stage.check(outside)
    assert system.status is Status.MISSING
    assert "not a virtual environment" in system.detail
    assert not system.verifiable, "a new environment needs a new process"


def test_the_venv_steps_are_the_exact_commands_for_the_platform(tmp_path: Path) -> None:
    """Written out per platform rather than described.

    The reader who needs them is at a shell that has just refused to
    install something, and a paraphrase is one more thing to get right.
    """
    stage = next(s for s in STAGES if s.id == "own-venv")
    installers = {
        UBUNTU: "python3-venv",
        MACOS: "python@3.13",
        WINDOWS: "Python.Python.3.13",
    }
    for platform, package in installers.items():
        plan = stage.plan(_context(tmp_path, platform=platform))
        assert len(plan.commands) == 1
        assert package in " ".join(plan.commands[0]), platform
        said = "\n".join(plan.instructions)
        assert "pip install prodockit" in said, platform
        if platform is WINDOWS:
            assert r"%USERPROFILE%\.venvs\prodockit\Scripts" in said
            assert "~/.venvs" not in said, "no POSIX paths in a Windows recipe"
        else:
            assert "~/.venvs/prodockit/bin" in said
            assert "%USERPROFILE%" not in said
        if platform is MACOS:
            # Homebrew does not relink `python3` for a versioned formula,
            # so after installing python@3.13 the recipe has to name it -
            # `python3` would be the interpreter just worked around.
            assert "python3.13 -m venv" in said


PLAN_EFFECTS: dict[str, tuple[str, ...] | None] = {
    "vscode": ("the `code` command",),
    "git": ("git itself", "the global identity"),
    "ssh-key": ("the keypair",),
    "ssh-config": ("the Host stanza",),
    "ssh-agent": ("the loaded key",),
    "ssh-upload": None,
    # A recorded answer, not a command: what it produces is the setting
    # the clone stage then reads.
    "clone-source": None,
    "clone": ("the clone",),
    "fresh-history": ("a history of its own", "core.fileMode"),
    "first-push": ("the commit", "the push"),
    # Guide and verify: the browser does the work, `gh` confirms it.
    "pages": None,
    "own-project": None,
    # Nothing to run: the workflow publishes the site, and this only
    # asks whether it did (#333).
    "site": None,
    "remote": ("origin", "the synced config"),
    "identity": ("the project's identity",),
    "pandoc": ("pandoc", "the PDF fonts"),
    # Ubuntu installs the missing package; everywhere else `venv` comes
    # with Python, so a failure there is guided rather than repaired.
    "own-venv": ("the venv machinery",),
    "project-env": ("the venv", "its dependencies"),
    "node": ("node", "the toolchains", "chromium and the exports"),
    "extensions": ("the extensions",),
    "vscode-settings": ("the settings file",),
    "csl-style": ("the style file",),
    "mathjax": ("the bundle", "its config", "the gitignore entries"),
}


def test_every_stage_declares_what_its_plan_produces() -> None:
    """The gate. A stage added without an entry fails here, which is the
    only part of this that survives contact with a future stage.

    Four bugs were traced to a check narrower than its own plan, and
    three more were introduced after that was known - each time by adding
    something to a plan and nothing to a check, with the whole suite
    passing throughout."""
    declared, actual = set(PLAN_EFFECTS), {stage.id for stage in STAGES}

    assert actual - declared == set(), (
        f"stages with no entry in PLAN_EFFECTS: {sorted(actual - declared)} - "
        f"say what the plan produces, and check the stage can see it"
    )
    assert declared - actual == set(), (
        f"entries for stages that no longer exist: {sorted(declared - actual)}"
    )


def test_a_stage_with_commands_is_never_satisfied_by_an_empty_machine(
    tmp_path: Path,
) -> None:
    """The invariant, as far as a fixed fake can carry it: a stage whose
    plan installs something must not report `ok` about a machine where
    nothing is installed.

    This is what caught nothing when `npm ci`, Chromium and the fonts
    were added: `node --version` answered, so the stage said `ok` while
    its plan had four more commands the check never looked at."""
    empty = FakeRunner({})
    for platform in (MACOS, UBUNTU, WINDOWS):
        context = _context(tmp_path, runner=empty, platform=platform)
        for stage in STAGES:
            result = stage.check(context)
            if result.status is Status.UNKNOWN:
                continue  # waiting on configuration, not on the machine
            if stage.id == "clone-source":
                # Nothing to decide on a machine with no project on the
                # host - and "the template" is the honest answer, not a
                # silent pass.
                assert "template" in result.detail or result.needs_work
                continue
            if stage.id == "pages" and not context.host.pages_setup_steps:
                # GitLab configures its own Pages from the CI job, so
                # there is nothing here for a reader to switch on.
                assert "configures Pages from its CI job" in result.detail
                continue
            if stage.id == "site" and not context.host.pages_url:
                # The one honest exception. A self-hosted GitLab publishes
                # at no address bootstrap can work out, so this stage
                # cannot be checked there at all - and it says exactly
                # that in its detail rather than claiming a site was
                # found. Leaving every Surrey run permanently one stage
                # short would be worse than the gap it reports (#333).
                assert "not checked" in result.detail
                continue
            assert result.needs_work, (
                f"{stage.id} reports {result.status.value} on {platform} with "
                f"nothing installed: {result.detail}"
            )


def test_a_stage_that_installs_toolchains_notices_they_are_absent(tmp_path: Path) -> None:
    """The regression that prompted the review: node present, toolchains
    not. The stage said `ok` and the reader found out at a diagram."""
    project = tmp_path / "GitLab" / "report-al01234"
    project.mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    runner = FakeRunner(
        {"node": CommandResult(0, "v22.14.0\n"), "npm": CommandResult(0, "10.9.2\n")}
    )

    result = next(s for s in STAGES if s.id == "node").check(_context(tmp_path, runner=runner))

    assert result.needs_work
    assert "mermaid" in result.detail and "mathjax" in result.detail


def test_ubuntu_notices_puppeteer_has_no_browser_to_point_at(tmp_path: Path) -> None:
    """Chromium installed but never pointed at leaves Puppeteer
    downloading its own; the exports without a Chromium point at
    nothing. Both halves are the stage's own plan, so both are checked."""
    project = tmp_path / "GitLab" / "report-al01234"
    for toolchain in ("mermaid", "mathjax"):
        (project / "tools" / toolchain / "node_modules").mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    stage = next(s for s in STAGES if s.id == "node")
    base = {"node": CommandResult(0, "v22.14.0\n"), "npm": CommandResult(0, "10.9.2\n")}

    no_chromium = FakeRunner({**base, "which chromium": CommandResult(1)})
    result = stage.check(_context(tmp_path, runner=no_chromium, platform=UBUNTU))
    assert result.needs_work and "Chromium" in result.detail

    both = FakeRunner(
        {
            **base,
            "which chromium-browser": CommandResult(0, "/usr/bin/chromium\n"),
            f"grep -q {PUPPETEER_SKIP_VAR}": CommandResult(0),
        }
    )
    assert stage.check(_context(tmp_path, runner=both, platform=UBUNTU)).status is Status.OK


def test_the_pandoc_stage_notices_its_own_fonts_are_missing(tmp_path: Path) -> None:
    """Added to the plan in #249 with nothing checking them."""
    runner = FakeRunner(
        {
            "pandoc": CommandResult(0, "pandoc 3.10.1\n"),
            "fc-list": CommandResult(0, "DejaVu Sans\n"),
        }
    )
    result = next(s for s in STAGES if s.id == "pandoc").check(_context(tmp_path, runner=runner))

    assert result.needs_work
    assert "Inter" in result.detail and "JetBrains Mono" in result.detail


def test_a_machine_that_cannot_be_asked_about_fonts_is_not_accused(tmp_path: Path) -> None:
    """ "I could not tell" must not read as "they are missing". A false
    alarm sends the reader to reinstall fonts they already have, which is
    worse than the silence this replaced."""
    runner = FakeRunner({"pandoc": CommandResult(0, "pandoc 3.10.1\n")})  # no fc-list

    result = next(s for s in STAGES if s.id == "pandoc").check(_context(tmp_path, runner=runner))

    assert result.status is Status.OK


def test_the_history_stage_notices_core_filemode(tmp_path: Path) -> None:
    """Set by the plan, and per-repository - so a fresh clone loses it
    again and the check has to be able to say so."""
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    runner = FakeRunner(
        {"remote get-url origin": CommandResult(0, "git@gitlab.surrey.ac.uk:x/report.git")}
    )

    result = next(s for s in STAGES if s.id == "fresh-history").check(
        _context(tmp_path, runner=runner)
    )

    assert result.needs_work
    assert "core.fileMode" in result.detail


# ---------------------------------------------------------------------------
# Windows: #217 phase 4
# ---------------------------------------------------------------------------


def test_no_winget_call_can_stop_for_a_human(tmp_path: Path) -> None:
    """winget asks for agreement to its source terms the first time it
    is used, and to a package's terms when one carries them - on the
    terminal, so a captured, timed subprocess simply waits.

    That is #243's `sudo` failure reached by a different route, and it
    would have met every Windows reader on their very first stage."""
    context = _context(tmp_path, platform=WINDOWS)
    seen = 0
    for stage in STAGES:
        for command in stage.plan(context).commands:
            if command[0] != "winget":
                continue
            seen += 1
            joined = " ".join(command)
            assert "--accept-source-agreements" in joined, joined
            assert "--accept-package-agreements" in joined, joined
            assert " -e " in f" {joined} ", "an ambiguous id is another question"
    assert seen >= 4, "vscode, git, pandoc, MSYS2 and node between them"


def test_windows_installs_pango_rather_than_describing_it(tmp_path: Path) -> None:
    """WeasyPrint draws text through Pango, which on Windows comes from
    MSYS2. The guide walks the reader through a MINGW64 shell and the
    Environment Variables dialog; all three steps run unattended."""
    runner = FakeRunner({"int.from_bytes": CommandResult(0, "0x8664\n")})
    plan = next(s for s in STAGES if s.id == "pandoc").plan(
        _context(tmp_path, platform=WINDOWS, runner=runner)
    )
    flat = " ".join(" ".join(c) for c in plan.commands)

    assert "MSYS2.MSYS2" in flat
    assert "--noconfirm" in flat, "pacman asks otherwise"
    assert "--needed" in flat, "a rerun should be a no-op, not a reinstall"
    assert "SetEnvironmentVariable" in flat
    assert "WEASYPRINT_DLL_DIRECTORIES" in flat
    assert "mingw-w64-ucrt-x86_64-pango" in flat
    assert "mingw-w64-clang-aarch64-pango" not in flat
    assert "PROCESSOR_ARCHITECTURE" not in flat
    assert "PROCESSOR_ARCHITEW6432" not in flat


def test_windows_native_arm64_python_installs_arm64_pango(tmp_path: Path) -> None:
    runner = FakeRunner({"int.from_bytes": CommandResult(0, "0xaa64\n")})
    plan = next(s for s in STAGES if s.id == "pandoc").plan(
        _context(tmp_path, platform=WINDOWS, runner=runner)
    )
    flat = " ".join(" ".join(command) for command in plan.commands)

    assert "mingw-w64-clang-aarch64-pango" in flat
    assert "$msysEnv = 'clangarm64'" in flat
    assert 'Join-Path $root "$msysEnv\\bin"' in flat
    assert "mingw-w64-ucrt-x86_64-pango" not in flat


def test_the_msys2_path_entry_is_added_only_once(tmp_path: Path) -> None:
    """A PATH carrying the same directory four times is what a tool that
    assumed a single run looks like."""
    plan = next(s for s in STAGES if s.id == "pandoc").plan(_context(tmp_path, platform=WINDOWS))
    path_command = next(c for c in plan.commands if "SetEnvironmentVariable" in " ".join(c))

    assert "-notlike" in " ".join(path_command)


def test_windows_pango_is_still_verified_somewhere(tmp_path: Path) -> None:
    """#224's rule. The pandoc stage installs Pango and cannot check it;
    importing WeasyPrint at stage 13 can, and does - so the hand-off is
    deliberate rather than a gap."""
    ids = [s.id for s in STAGES]

    assert ids.index("pandoc") < ids.index("project-env")


def test_windows_fonts_are_checked_even_though_they_are_installed_by_hand(
    tmp_path: Path,
) -> None:
    """Windows has no package manager for these, which is a reason to
    check rather than a reason not to - an instruction nobody verifies is
    how a font goes missing silently."""
    fonts = tmp_path / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"
    fonts.mkdir(parents=True)
    (fonts / "DejaVuSans.ttf").write_text("", encoding="utf-8")
    runner = FakeRunner({"pandoc": CommandResult(0, "pandoc 3.10.1\n")})

    result = next(s for s in STAGES if s.id == "pandoc").check(
        _context(tmp_path, runner=runner, platform=WINDOWS)
    )
    assert result.needs_work and "Inter" in result.detail

    for name in ("Inter-Regular.ttf", "JetBrainsMono-Regular.ttf"):
        (fonts / name).write_text("", encoding="utf-8")
    result = next(s for s in STAGES if s.id == "pandoc").check(
        _context(tmp_path, runner=runner, platform=WINDOWS)
    )
    assert result.status is Status.OK


def test_a_windows_machine_with_no_font_directory_is_not_accused(tmp_path: Path) -> None:
    """Same rule as elsewhere: "I could not tell" must not read as "they
    are missing"."""
    runner = FakeRunner({"pandoc": CommandResult(0, "pandoc 3.10.1\n")})

    result = next(s for s in STAGES if s.id == "pandoc").check(
        _context(tmp_path, runner=runner, platform=WINDOWS)
    )

    assert result.status is Status.OK


def test_every_windows_stage_produces_something_to_do(tmp_path: Path) -> None:
    """Phase 4's own acceptance test: no stage may be silently empty on
    Windows. A stage with neither commands nor instructions there would
    be one nobody had thought about, and would report `nothing to do`."""
    context = _context(tmp_path, platform=WINDOWS)
    for stage in STAGES:
        if stage.id == "pages" and not context.host.pages_setup_steps:
            # Nothing for a GitLab reader to switch on, and the check
            # reports the stage satisfied - so this plan is never built
            # in a real run. Empty is the correct answer, not an
            # oversight (#360).
            assert not stage.check(context).needs_work
            continue
        plan = stage.plan(context)
        assert plan.commands or plan.instructions or plan.follow_up, (
            f"{stage.id} has no Windows plan at all"
        )


# ---------------------------------------------------------------------------
# The host is the first question: #255
# ---------------------------------------------------------------------------


def test_the_host_is_the_first_thing_asked() -> None:
    """#255. Everything else is shaped by it - which URLs the browser
    steps send you to, which key file is looked for, whether you are
    creating a project or a repository - so answering it sixth means
    five questions about a setup that may not be buildable."""
    assert PROMPTS[0][0] == "host"


def test_the_host_is_a_numbered_menu_with_surrey_as_the_default(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#534. The three implemented services are visible choices, while
    Enter keeps the established Surrey default."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    result = cli_bootstrap(
        "--configure",
        input="\nAda Lovelace\nab1234\nn\n\n\n",
    )

    output = result.output
    choices = (
        "1. gitlab.surrey.ac.uk",
        "2. github.com",
        "3. gitlab.com",
    )
    assert all(choice in output for choice in choices)
    assert [output.index(choice) for choice in choices] == sorted(
        output.index(choice) for choice in choices
    )
    assert "Select a git service [1]" in output
    assert load(tmp_path / "b.toml").host == "gitlab.surrey.ac.uk"


def test_the_host_is_a_hostname_not_a_nickname() -> None:
    """Asked as the thing the reader can see in their address bar. A key
    like `surrey` means nothing to somebody typing it for the first
    time, and means nothing at all once a second self-hosted GitLab
    exists."""
    assert BootstrapConfig().host == "gitlab.surrey.ac.uk"
    assert default_for(BootstrapConfig(), "host") == "gitlab.surrey.ac.uk"


def test_a_host_that_is_neither_gitlab_nor_github_is_refused() -> None:
    """The stages are written around those two. A hostname naming
    something else is a different kind of service, not a typo to guess
    at."""
    from prodockit.bootstrap import host_problem

    problem = host_problem("bitbucket.org") or ""
    assert "does not look like a GitLab or GitHub host" in problem
    assert "gitlab.surrey.ac.uk" in problem, "say what one looks like"
    assert "github.com" in problem
    assert host_problem("") is not None


def test_github_is_usable_and_gitlab_com_still_is_not() -> None:
    """github.com was enabled when Surrey's GitLab became unreachable for
    long enough to block testing entirely - a tool whose every stage runs
    against one server cannot be developed while that server is down.

    gitlab.com stays refused, so this is a host being turned on
    deliberately rather than the check being loosened.
    """
    from prodockit.bootstrap import host_problem

    assert host_problem("github.com") is None
    assert host_problem("gitlab.surrey.ac.uk") is None
    assert host_problem("gitlab.com") is None, "flipped on in #361"
    assert "self-hosted" in (host_problem("gitlab.example.edu") or "")


def test_an_unknown_self_hosted_gitlab_is_told_apart_from_a_typo() -> None:
    """`gitlab.example.edu` is what this is groundwork for, so it gets a
    different answer from `bitbucket.org` - not supported yet, rather
    than not a GitLab at all."""
    from prodockit.bootstrap import host_problem

    problem = host_problem("gitlab.example.edu") or ""
    assert "self-hosted" in problem
    assert "does not look like" not in problem


def test_a_pasted_url_is_reduced_to_its_hostname() -> None:
    """Readers paste what is in the address bar."""
    from prodockit.bootstrap import normalise_host

    for typed in (
        "https://gitlab.surrey.ac.uk/",
        "GitLab.Surrey.AC.UK",
        "git@gitlab.surrey.ac.uk",
        "  gitlab.surrey.ac.uk/mb0105/x  ",
    ):
        assert normalise_host(typed) == "gitlab.surrey.ac.uk", typed


def test_a_config_written_before_this_still_works(tmp_path: Path) -> None:
    """`host = "surrey"` is in configuration files on real machines. They
    keep working; the prompt stores a hostname from now on."""
    from prodockit.bootstrap import resolve_host

    assert resolve_host("surrey") is SURREY_GITLAB
    context = build_context(_config(host="surrey"), home=tmp_path)
    assert context.host.hostname == "gitlab.surrey.ac.uk"


def test_the_prompt_and_the_run_ask_the_same_question(tmp_path: Path) -> None:
    """`build_context` refuses through the same helper the prompt uses,
    so a host the prompt accepted cannot be one the run then rejects."""
    from prodockit.bootstrap import host_problem

    for value in ("gitlab.example.edu", "bitbucket.org"):
        with pytest.raises(UnsupportedHostError) as exc_info:
            build_context(_config(host=value))
        assert str(exc_info.value) == host_problem(value)


def test_a_host_that_does_not_answer_is_reported_as_unreachable() -> None:
    """Asked at the prompt because the alternative is finding out at
    stage 6, after a key has been made and uploaded - and "could not
    reach it" looks nothing like "it rejected your key", which is a
    confusion these stages have already produced three times."""
    from prodockit.bootstrap import connection_problem

    def refuse(hostname: str, port: int, timeout: float) -> None:
        raise OSError(61, "Connection refused")

    problem = connection_problem("gitlab.surrey.ac.uk", connect=refuse) or ""
    assert "could not reach gitlab.surrey.ac.uk" in problem
    assert "port 22" in problem, "name the port, since it is ssh not https"
    assert "Connection refused" in problem

    assert connection_problem("gitlab.surrey.ac.uk", connect=lambda h, p, t: None) is None


def test_an_unreachable_host_is_re_asked_with_the_vpn_named(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A university GitLab is often reachable only over a VPN, so
    re-asking with the same answer is a real retry rather than a loop -
    connect it, press Enter, and the second attempt succeeds."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    attempts: list[str] = []

    def flaky(value: str) -> str | None:
        attempts.append(value)
        if len(attempts) == 1:
            return "could not reach gitlab.surrey.ac.uk on port 22 - timed out"
        return None

    monkeypatch.setattr("prodockit.cli.connection_problem", flaky)

    result = cli_bootstrap(
        "--configure",
        input=("1\n1\nAda Lovelace\nal01234\nn\n\n\n"),
    )

    assert "could not reach gitlab.surrey.ac.uk" in result.output
    assert "connect the VPN" in result.output
    assert len(attempts) == 2, "the second attempt is the retry"
    assert load(tmp_path / "b.toml").host == "gitlab.surrey.ac.uk"


def test_an_invalid_host_menu_choice_is_re_asked_rather_than_stored(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the three implemented hosts can leave the menu. An invalid
    number is rejected at the prompt rather than stored for a later
    stage to fail on."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    result = cli_bootstrap(
        "--configure",
        input=("4\n1\nAda Lovelace\nal01234\nn\n\n\n"),
    )

    assert "not one of '1', '2', '3'" in result.output
    assert load(tmp_path / "b.toml").host == "gitlab.surrey.ac.uk"


def test_a_reachable_host_is_never_asked_about_twice(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The connection is tested once, for the host being stored - not
    once per remaining question."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    tested: list[str] = []
    monkeypatch.setattr(
        "prodockit.cli.connection_problem", lambda value: tested.append(value) or None
    )

    cli_bootstrap(
        "--configure",
        input=("1\nAda Lovelace\nal01234\nn\n\n\n"),
    )

    assert tested == ["gitlab.surrey.ac.uk"]


def test_surrey_derives_five_answers_from_four_questions(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#420, end to end through the real prompts.

    Login ID, course code, module year and "is it assessed" are enough:
    the email, the GitLab username, the group and the repository name all
    follow. Every free-text answer removed is one fewer chance to type a
    namespace that does not exist and find out six stages later.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    # host, name, login, assessed? -> yes, course, stage 2 (SRA), year
    result = cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\ny\ncomm058\n2\n2026\n",
    )

    stored = load(tmp_path / "b.toml")
    assert stored.host == "gitlab.surrey.ac.uk"
    assert stored.full_name == "Ada Lovelace"
    assert stored.email == "ab1234@surrey.ac.uk"
    assert stored.username == "ab1234"
    assert stored.namespace == "assessment-comm058-2026-sra"
    assert stored.project_name == "report-comm058-2026-ab1234-sra"
    assert stored.project_dir.endswith("report-comm058-2026-ab1234-sra")

    # None of the five derived questions was put to the reader.
    for never_asked in ("email address used", "username", "group, organisation"):
        assert never_asked not in result.output, never_asked
    # ...and what was derived is shown, because a student has to find the
    # repository on a website afterwards.
    assert "assessment-comm058-2026-sra" in result.output
    assert "report-comm058-2026-ab1234-sra" in result.output


def test_a_first_run_stops_before_the_stage_list(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#433.

    The run has just told the reader the group and repository name to
    note down - the two things they have to take to a website - and
    twenty-three stage lines printed after it scrolled both off the
    screen. `--configure` already stopped there; a first `pdk boot`
    answered the same questions and then carried on.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    result = cli_bootstrap(input="y\n1\nAda Lovelace\nab1234\nn\n\n\n")

    assert "Note these down:" in result.output
    assert "report-ab1234" in result.output
    assert "MISS" not in result.output, "the stage list would scroll the note away"
    assert "Run `pdkboot` to see what is set up." in result.output


def test_a_first_run_takes_the_surrey_path_too(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#430, reported from Windows on 0.35.0.

        Some details are not set yet: host, full_name, email, ...
        1/8 The git host your project lives on
          1. gitlab.surrey.ac.uk
        3/8 The email address used for your gitlab.surrey.ac.uk login []:

    The shorter path was chosen only when `--configure` asked for
    everything. A first run does not arrive that way: nothing is set, so
    bootstrap offers to fill the gaps and names the fields - which took
    the general eight questions, and asked for the email #420 exists to
    derive.

    Nothing set at all is the configure arriving by a different door, not
    a repair.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    # "yes, ask me now", then Surrey's own five answers.
    result = cli_bootstrap(input="y\n1\nAda Lovelace\nab1234\nn\n\n\n")

    stored = load(tmp_path / "b.toml")
    assert stored.email == "ab1234@surrey.ac.uk", "derived, not asked for"
    assert stored.project_name == "report-ab1234"
    assert "2/7" in result.output, "the short path, on a first run"
    assert "The email address used for" not in result.output


def test_filling_one_later_gap_still_asks_for_that_field(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Somebody coming back to correct one value wants that value asked
    for, not a derivation walked through again - which is why the two
    cases are told apart rather than merged."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)
    save(tmp_path / "b.toml", _config(project_name=""))

    result = cli_bootstrap(input="y\nreport-x\n\n")

    assert "project name" in result.output.lower()
    assert "course code" not in result.output.lower(), "not the whole derivation again"
    assert load(tmp_path / "b.toml").project_name == "report-x"


def test_the_module_year_is_asked_for_and_defaults_to_this_one(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cohort's work belongs in that cohort's group.

    Which year that is takes explaining twice over - a semester 2 module
    should be the year after the Christmas break, and for SRA and LSA the
    year should be the year prior to the year the retake is being assessed
    - so both sentences are in the question rather than in a handbook.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    # Enter accepts the offered year, so the year is never typed here.
    result = cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\ny\ncomm058\n1\n\n",
    )

    from prodockit.bootstrap import surrey

    stored = load(tmp_path / "b.toml")
    assert stored.namespace == f"assessment-comm058-{surrey.default_year()}"
    assert "semester 2" in result.output, "why it is not simply this year"
    assert "prior to the year the retake is being assessed" in result.output


def test_a_year_that_is_not_a_year_is_asked_again(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`26` or `Jan 2026` would make a group nobody can find, and the
    student would not know until the push failed."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    result = cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\ny\ncomm058\n1\n26\n2026\n",
    )

    assert "Four figures" in result.output
    assert load(tmp_path / "b.toml").namespace == "assessment-comm058-2026"


def test_the_stage_menu_comes_before_the_year_that_names_it(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#437.

    The year question says what SRA and LSA should be, and nothing before
    it had said what they are. Asking whether the work is assessed - and
    listing the three stages - introduces them first, so the year
    question refers back to something already on screen.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    result = cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\ny\ncomm058\n2\n2026\n",
    )
    output = result.output

    assert output.index("2. SRA") < output.index("For SRA and LSA the year"), output
    assert load(tmp_path / "b.toml").namespace == "assessment-comm058-2026-sra"


def test_unassessed_work_is_asked_for_its_namespace_and_nothing_else(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No cohort group to go to and no attempt to record, so neither the
    year nor the stage is asked for - and the namespace is offered as the
    reader's own, to be typed over only by somebody who wants another."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    result = cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\nn\n\n\n",
    )

    stored = load(tmp_path / "b.toml")
    assert stored.namespace == "ab1234", "offered as theirs, taken as offered"
    assert stored.project_name == "report-ab1234"
    assert "What year does the module start in" not in result.output
    assert "2. SRA" not in result.output


def test_both_paths_ask_the_same_number_of_questions(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every question numbered, and against the right total.

    The stage question used to arrive unnumbered after "is this
    assessed?", so a reader counting down from six met a question that
    was not in the count (#437).

    The two paths agree up to and including "is this assessed?" - both
    numbered against seven, since which path applies is not known until
    it is answered. After that they diverge: assessed work asks three
    more questions (course, stage, year) and stays on seven; unassessed
    work never asks for a course code (#458), so its two remaining
    questions (namespace, repository name) count against six instead.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    assessed = cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\ny\ncomm058\n2\n2026\n",
    ).output
    (tmp_path / "b.toml").unlink()
    unassessed = cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\nn\n\n\n",
    ).output

    for number in range(2, 8):
        assert f"{number}/7" in assessed, f"{number}/7 missing from the assessed path:\n{assessed}"
    for number in range(2, 5):
        assert f"{number}/7" in unassessed, f"{number}/7 missing before the split:\n{unassessed}"
    for number in range(5, 7):
        assert f"{number}/6" in unassessed, f"{number}/6 missing after the split:\n{unassessed}"
    assert "questions rather than 7" in unassessed, "the drop from 7 to 6 is announced"


def test_the_offered_repository_name_can_be_typed_over(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unassessed work is named by its owner, not derived - so the offer
    is `report-<login>` and anything else they type is kept."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\nn\n\nnotes\n",
    )

    stored = load(tmp_path / "b.toml")
    assert stored.project_name == "notes"
    assert stored.project_dir.endswith("notes"), "the folder follows the name"


def test_a_namespace_typed_over_the_default_is_kept(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unassessed work is not always personal - a project group is a
    perfectly ordinary answer, and the default is only an offer."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\nn\ndocs-team\n\n",
    )

    assert load(tmp_path / "b.toml").namespace == "docs-team"


def test_unassessed_surrey_work_goes_to_the_students_own_namespace(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And the stage question is not asked at all - there is no attempt
    to record for work nobody is marking."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    result = cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\nn\n\n\n",
    )

    stored = load(tmp_path / "b.toml")
    assert stored.namespace == "ab1234", "no year, and no group - it is their own"
    # Neither a year nor a course code was asked for, so the offered name
    # carries neither.
    assert stored.project_name == "report-ab1234"
    # The stage *menu*, not the word: the year guidance above mentions
    # SRA and LSA, because which year a resit belongs to is exactly what
    # it is there to explain.
    assert "2. SRA" not in result.output, "not offered when nothing is being assessed"
    assert "Which stage" not in result.output


def test_the_short_path_says_why_it_is_shorter(  # type: ignore[no-untyped-def]
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The host question counts against eight, because the shorter list
    is not known to apply until it is answered. A reader who saw `1/8`
    and is then asked `2/5` is owed the reason."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    result = cli_bootstrap(
        "--configure",
        input="1\nAda Lovelace\nab1234\nn\n\n\n",
    )

    assert "1/8 The git host" in result.output
    assert "fills in the rest" in result.output
    assert "2/7" in result.output


@pytest.mark.parametrize(("choice", "hostname"), [("2", "github.com"), ("3", "gitlab.com")])
def test_answering_the_host_does_not_disturb_the_other_questions(
    cli_bootstrap,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    choice: str,
    hostname: str,
) -> None:
    """A new first prompt shifts every answer by one, which is exactly
    the kind of change that silently reassigns a name to an email.

    Asked of both general-path hosts. Surrey's own path is shorter and
    derives most of these (#420), so it cannot stand in for the ordering
    this is about.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)

    cli_bootstrap(
        "--configure",
        input=(
            f"{choice}\nAda Lovelace\nal01234@surrey.ac.uk\nal01234\ncomm058-2026\nreport-x\n\n\n"
        ),
    )

    stored = load(tmp_path / "b.toml")
    assert stored.host == hostname
    assert stored.full_name == "Ada Lovelace"
    assert stored.email == "al01234@surrey.ac.uk"
    assert stored.username == "al01234"
    assert stored.namespace == "comm058-2026"
    assert stored.project_name == "report-x"


def test_the_host_is_never_reported_missing() -> None:
    """It always has an answer, so listing it among "not set yet" would
    ask an existing reader to re-confirm something they never chose."""
    assert "host" not in missing_keys(BootstrapConfig())


def test_the_key_is_entered_before_the_title(tmp_path: Path) -> None:
    """prodockit-extensions#257. GitLab fills the Title in from the key's
    own comment the moment a key is pasted, so a title typed first is
    silently replaced - and the reader ends up with a list of keys all
    named after their email address."""
    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))
    form = next(step for step in plan.instructions if "Title:" in step)

    assert form.index("Key:") < form.index("Title:")
    assert "in this order" in form


def test_the_title_is_suggested_as_this_machines_name(tmp_path: Path) -> None:
    """A key title answers "which machine is this?", and the address the
    key was made with does not - every key a reader creates carries the
    same one."""
    import socket

    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))
    form = next(step for step in plan.instructions if "Title:" in step)

    assert "filled in for you" in form
    assert socket.gethostname().split(".")[0] in form


def test_the_public_key_is_still_shown_in_the_form(tmp_path: Path) -> None:
    """The first half of #257, delivered in #238 - kept asserted here so
    the reordering above cannot quietly drop it."""
    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path))
    form = next(step for step in plan.instructions if "Title:" in step)

    assert form.count(PUBLIC_KEY_MARKER) == 2
    assert "ssh-ed25519 AAAAC3Nz-PUBLIC" in form


def test_apply_says_what_it_is_doing_before_it_starts(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#258: `--apply` opened straight into
    `[1/11] Visual Studio Code`, which says which step you are on and
    nothing about what you have started or where it will land."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    save(tmp_path / "b.toml", _config())

    result = cli_bootstrap("--apply", input="n\n" * 40)

    assert f"prodockit {__version__}" in result.output
    assert "setting up your development environment" in result.output
    assert "gitlab.surrey.ac.uk" in result.output, "which host it will use"
    assert "report-al01234" in result.output, "and where the project will land"
    assert f"of {len(STAGES)} stages" in result.output
    assert "prodockit itself is installed in" in result.output
    # Before the first stage that has anything to do, or it is not an
    # announcement. Not "[1/" - stage 1 is the environment prodockit is
    # already running in, so on this machine it has nothing to do (#381).
    first_stage = re.search(rf"\[\d+/{len(STAGES)}\]", result.output)
    assert first_stage is not None
    assert result.output.index("setting up your") < first_stage.start()


def test_the_heading_is_not_printed_when_there_is_nothing_to_do(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Announcing a setup and then doing nothing reads as a failure."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)

    result = cli_bootstrap("--apply", responses=_ready_machine(tmp_path), fetch=_ready_fetch())

    assert "setting up your development environment" not in result.output
    assert "Nothing to do" in result.output


def test_every_prompt_defaults_to_yes_except_the_destructive_one(tmp_path: Path) -> None:
    """prodockit-extensions#259: the default came from the check's status
    - MISSING meant yes, WRONG meant no - which is a rule the reader
    cannot see, so the same key press meant different things at different
    stages.

    One visible rule now: yes, unless applying it cannot be undone."""
    save(tmp_path / "b.toml", _config())
    # A clone still pointing at the template - the one state in which the
    # history reset applies at all. Anywhere else its plan is a one-line
    # `core.fileMode` setting and destroys nothing (#332), so asking this
    # question of a machine without that state would prove nothing.
    machine = _ready_machine(tmp_path)
    machine["remote get-url origin"] = CommandResult(
        0, "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git\n"
    )
    context = _context(tmp_path, runner=FakeRunner(machine))
    destructive = [s.id for s in STAGES if s.plan(context).destructive]

    assert destructive == [], (
        "nothing left destroys anything the reader owns: the history reset "
        "only ever deletes the template's commits, and a clone carrying "
        "the reader's own history is never offered it (#356). If a plan "
        "starts destroying something again, it must say so - the prompt "
        "default is the only thing standing in front of it"
    )


def test_pressing_enter_takes_the_history_reset(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reversed deliberately (#356).

    This prompt defaulted to No because it cannot be undone. What it
    deletes is only ever the *template's* history: a clone carrying the
    reader's own is never offered it, and the stage is blocked while the
    decision is unmade. So the answer is always yes, and defaulting to No
    left students who pressed Enter with the template's commits behind
    their project.
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    responses = _ready_machine(tmp_path)
    responses["remote get-url origin"] = CommandResult(0, SURREY_GITLAB.template_remote)

    result = cli_bootstrap("--apply", responses=responses, input="\n" * 40)

    assert "A history of your own" in result.output
    assert "[Y/n]" in result.output, "the template's history is meant to go"


def test_an_ordinary_install_is_the_enter_answer(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other seventeen. A reader who typed `--apply` has already said
    what they want."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    responses = _ready_machine(tmp_path)
    responses["code --list-extensions"] = CommandResult(0, "")

    result = cli_bootstrap("--apply", responses=responses, input="\n" * 40)

    assert f"Run {len(VSCODE_EXTENSIONS)} commands? [Y/n]" in result.output


def test_no_manual_step_is_left_asking_the_generic_question(tmp_path: Path) -> None:
    """prodockit-extensions#260. "Tell me when that is done" was asked
    after every manual step, including the one whose whole content is
    "this deletes your history and cannot be undone" - where there is
    nothing to have done, and the honest question is whether to go ahead
    at all.

    The gate: a stage that asks a person to do something must ask about
    the thing it asked for."""
    save(tmp_path / "b.toml", _config())
    for platform in (MACOS, UBUNTU, WINDOWS):
        context = _context(tmp_path, platform=platform)
        for stage in STAGES:
            plan = stage.plan(context)
            if not (plan.instructions or plan.follow_up):
                continue
            assert plan.confirm != "Tell me when that is done", (
                f"{stage.id} on {platform} still asks the generic question"
            )
            if plan.choices:
                # A numbered choice, not a yes/no. "Select 1, 2 or 3" is
                # the right prompt for it, and a question mark would
                # invite Enter - which is exactly what a choice with no
                # default must not accept (#348).
                assert plan.confirm.startswith("Select "), f"{stage.id}: {plan.confirm!r}"
                continue
            assert plan.confirm.endswith("?"), f"{stage.id}: {plan.confirm!r}"


def test_the_history_prompt_asks_whether_to_archive_it_not_whether_it_is_done(
    tmp_path: Path,
) -> None:
    """The case from the issue. Nothing is being asked *of* the reader
    here - the step is bootstrap's to run - so "tell me when that is
    done" asks about something that has not been offered yet."""
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    runner = FakeRunner({"remote get-url origin": CommandResult(0, SURREY_GITLAB.template_remote)})

    plan = next(s for s in STAGES if s.id == "fresh-history").plan(
        _context(tmp_path, runner=runner)
    )

    assert plan.confirm == "Archive the template's history and start a new repository?"


def test_the_browser_steps_name_the_host_they_are_about(tmp_path: Path) -> None:
    """ "Have you loaded the SSH key into your online Git repo?" was the
    issue's own suggestion; naming the host makes it checkable."""
    _write_keypair(tmp_path)
    save(tmp_path / "b.toml", _config())
    context = _context(tmp_path)

    upload = next(s for s in STAGES if s.id == "ssh-upload").plan(context)
    assert upload.confirm == "Have you added the key to your gitlab.surrey.ac.uk account?"

    project = next(s for s in STAGES if s.id == "own-project").plan(context)
    assert project.confirm == "Have you created the project on gitlab.surrey.ac.uk?"


def test_the_question_asked_is_the_one_the_plan_carries(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The field is no use unless the prompt uses it."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    responses = _machine_ready_except_ssh(tmp_path)

    result = cli_bootstrap("--apply", responses=responses, input="y\nn\n")

    assert "Have you added the key to your gitlab.surrey.ac.uk account?" in result.output
    assert "Tell me when that is done" not in result.output


def test_stage_16_says_what_it_does_not_how(tmp_path: Path) -> None:
    """prodockit-extensions#261: the plan carried an entire Python script
    as one argument, so `--apply` printed a wall of source and asked the
    reader to approve it."""
    project = tmp_path / "GitLab" / "report-al01234"
    project.mkdir(parents=True)
    save(tmp_path / "b.toml", _config())
    runner = FakeRunner({"AppleLocale": CommandResult(0, "en_GB.UTF-8\n")})

    plan = next(s for s in STAGES if s.id == "vscode-settings").plan(
        _context(tmp_path, runner=runner)
    )

    assert plan.describe
    assert "settings.json" in plan.describe
    assert "Zensical Studio" in plan.describe
    assert "en-GB" in plan.describe
    assert "import json" not in plan.describe, "that is the how, not the what"


def test_apply_shows_the_description_rather_than_the_script(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    responses = _ready_machine(tmp_path)
    (tmp_path / "GitLab" / "report-al01234" / ".vscode" / "settings.json").unlink()

    result = cli_bootstrap("--apply", responses=responses, input="n\n" * 20)

    assert "Will do:" in result.output
    assert "import json, sys, pathlib" not in result.output, "no script on screen"


def test_a_command_carrying_a_script_is_never_printed_whole() -> None:
    """The general guard. Any command with a newline in an argument is a
    script being handed to an interpreter, and printing it verbatim is
    always the wrong choice for a prompt."""
    from prodockit.cli import _readable_command

    rendered = _readable_command(
        ["python", "-c", "import json\nfor line in open('x'):\n    print(line)"]
    )

    assert "\n" not in rendered
    assert "<script:" in rendered
    assert len(rendered) <= 110


def test_dry_run_does_not_print_commands_for_waiting_stages(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plans below missing prerequisites are not yet executable and must
    not be presented as though pdkboot could run them now."""
    monkeypatch.setattr("prodockit.bootstrap.stages._vscode_app_installed", lambda ctx: False)
    save(tmp_path / "b.toml", _config())

    result = cli_bootstrap("--dry-run", responses={"code --version": CommandResult(127)})

    assert "WAIT" in result.output
    assert "import json, sys, pathlib" not in result.output
    assert "git remote add origin" not in result.output
    assert "code --install-extension" not in result.output


def test_the_email_prompt_names_the_host_not_a_university() -> None:
    """prodockit-extensions#265: "Your university email address" is wrong
    for anybody outside a university, and wrong inside one for a reader
    whose GitLab login is not their university address."""
    from prodockit.bootstrap import question_for

    email_question = dict(PROMPTS)["email"]
    assert "university" not in email_question

    asked = question_for(_config(host="gitlab.surrey.ac.uk"), "email", email_question)
    assert asked == "The email address used for your gitlab.surrey.ac.uk login"


def test_no_prompt_names_a_host_of_its_own(tmp_path: Path) -> None:
    """prodockit-extensions#370, reported from `pdk boot --configure`.

        5/8 The group, organisation or user the project lives under
            (e.g. comm058-2026, or your own username on github.com) []

    asked of a reader setting up against gitlab.surrey.ac.uk. The host is
    the first question precisely so the rest can be phrased in terms of
    the answer, and a question naming a different service reads as being
    about a different account somewhere else.

    Written against every prompt rather than that one, because the
    substitution already existed and was simply not used here - so the
    thing worth holding is that no prompt names a host on its own.
    """
    named = ("github.com", "gitlab.com", "gitlab.surrey.ac.uk", "GitHub", "GitLab")
    offenders = [(key, name) for key, question in PROMPTS for name in named if name in question]

    assert not offenders, f"say {{host}} instead: {offenders}"


def test_the_namespace_prompt_follows_the_host_just_answered() -> None:
    """The specific question from #370, in both directions."""
    from prodockit.bootstrap import question_for

    question = dict(PROMPTS)["namespace"]

    surrey = question_for(_config(host="gitlab.surrey.ac.uk"), "namespace", question)
    assert "your own gitlab.surrey.ac.uk username" in surrey
    assert "github" not in surrey.lower()
    assert "your own github.com username" in question_for(
        _config(host="github.com"), "namespace", question
    )


def test_the_email_prompt_follows_the_host_just_answered() -> None:
    """It reads the answer rather than a constant, so it says whatever
    was typed a moment ago - which is the point of asking the host
    first."""
    from prodockit.bootstrap import question_for

    email_question = dict(PROMPTS)["email"]
    assert "gitlab.example.edu" in question_for(
        _config(host="gitlab.example.edu"), "email", email_question
    )
    # And says something sensible if the host is somehow blank.
    assert "your git host" in question_for(_config(host=""), "email", email_question)


def test_the_host_is_asked_before_the_prompt_that_needs_it() -> None:
    """The email question interpolates the host, so a run that asked it
    later would show a placeholder or a stale answer."""
    keys = [key for key, _ in PROMPTS]

    assert keys.index("host") < keys.index("email")


# ---------------------------------------------------------------------------
# MathJax installed, not committed: #263
# ---------------------------------------------------------------------------


def _mathjax_project(tmp_path: Path) -> Path:
    project = tmp_path / "GitLab" / "report-al01234"
    (project / "docs").mkdir(parents=True)
    pinned = project / "tools" / "mathjax" / "node_modules" / "mathjax-full" / "es5"
    pinned.mkdir(parents=True)
    (pinned / "tex-svg-full.js").write_text("BUNDLE", encoding="utf-8")
    save(tmp_path / "b.toml", _config())
    return project


def test_the_website_needs_both_the_config_and_the_bundle(tmp_path: Path) -> None:
    """prodockit-extensions#263: the equation showed as raw TeX because
    MathJax was loaded with no configuration.

    Both halves fail differently and neither is visible: without the
    config the bundle loads and does nothing, without the bundle the
    config configures nothing."""
    _mathjax_project(tmp_path)
    stage = next(s for s in STAGES if s.id == "mathjax")

    result = stage.check(_context(tmp_path))
    assert result.status is Status.MISSING
    assert "config" in result.detail and "bundle" in result.detail


def test_the_mathjax_stage_calls_the_one_installer(tmp_path: Path) -> None:
    """prodockit-extensions#276. The configuration lived here *and* in a
    template's CI, which never runs bootstrap - two copies of a thing
    whose whole failure mode is being subtly wrong, since both produce a
    valid file and the site simply typesets one way locally and another
    when published.

    The stage calls `prodockit init-mathjax` now, the same arrangement
    the repoint stage has with `prodockit sync-repo`."""
    _mathjax_project(tmp_path)
    plan = next(s for s in STAGES if s.id == "mathjax").plan(_context(tmp_path))

    assert plan.commands == [[sys.executable, "-m", "prodockit", "init-mathjax"]], (
        "the prodockit already running, not whichever one PATH finds (#371)"
    )
    assert plan.cwd is not None and plan.cwd.endswith("report-al01234")
    # The config itself is no longer here to drift from.
    from prodockit.bootstrap import stages

    assert not hasattr(stages, "MATHJAX_CONFIG_SOURCE")


def test_the_mathjax_stage_runs_after_the_toolchains(tmp_path: Path) -> None:
    """The bundle is copied out of what `npm ci` put there."""
    ids = [s.id for s in STAGES]

    assert ids.index("mathjax") > ids.index("node")


def test_the_stage_says_what_it_does_rather_than_showing_the_script(tmp_path: Path) -> None:
    """#261's rule, applied to a stage written after it."""
    _mathjax_project(tmp_path)
    plan = next(s for s in STAGES if s.id == "mathjax").plan(_context(tmp_path))

    assert plan.describe
    assert "import pathlib" not in plan.describe


def test_a_stages_instructions_describe_the_machine_as_it_is_now(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#281: on a fresh machine the SSH upload step
    said "paste the contents of ~/.ssh/id_ed25519_gitlab.pub" about a key
    that existed by the time the step was reached.

    `plan_all` builds every plan before anything is applied, so a plan
    depending on what an earlier stage creates was describing a machine
    that no longer existed. Here the keypair appears *after* the plans are
    built, exactly as `ssh-keygen` would create it mid-run."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    responses = _machine_ready_except_ssh(tmp_path)
    public = tmp_path / ".ssh" / "id_ed25519_gitlab.pub"
    public.unlink()  # no key when the plans are built

    real_plan_all = __import__("prodockit.bootstrap", fromlist=["plan_all"]).plan_all

    def plan_then_create_the_key(context, *args, **kwargs):
        reports = real_plan_all(context, *args, **kwargs)
        public.write_text("ssh-ed25519 AAAAC3Nz-CREATED-MIDRUN al@surrey.ac.uk\n", encoding="utf-8")
        return reports

    monkeypatch.setattr("prodockit.cli.plan_all", plan_then_create_the_key)

    result = cli_bootstrap("--apply", responses=responses, input="y\nn\n")

    assert "AAAAC3Nz-CREATED-MIDRUN" in result.output, (
        "the step must show the key that exists when it is reached"
    )
    assert "paste the contents of" not in result.output, "that is the no-key fallback"


def test_a_first_run_asks_the_host_even_without_configure(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#279: reaching configuration through the
    "Some details are not set yet" offer skipped the host entirely.

    `host` has a default, so it is never *empty* and `missing_keys` never
    reports it - which is right for somebody with a stored answer, and
    wrong for somebody who has never been asked. This route is precisely
    the one a first-time reader takes."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)
    assert not (tmp_path / "b.toml").exists()

    result = cli_bootstrap(
        input="y\n1\nAda Lovelace\nal01234\nn\n\n\n",
    )

    assert "The git host your project lives on" in result.output
    # And first, as #255 requires - the email question names it.
    assert result.output.index("git host") < result.output.index("full name")
    assert load(tmp_path / "b.toml").host == "gitlab.surrey.ac.uk"


def test_an_existing_config_is_not_re_asked_for_its_host(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half. Somebody who answered once should not be asked
    again just because a different field went blank - that is what
    `--configure` is for."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)
    save(tmp_path / "b.toml", _config(project_name=""))

    result = cli_bootstrap(input="y\nreport-x\n\n\n")

    assert "The git host your project lives on" not in result.output
    # Left exactly as stored - including a legacy key, which still
    # resolves and must not be silently rewritten.
    assert load(tmp_path / "b.toml").host == "surrey"


def test_the_non_interactive_message_names_the_host_too(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scripted first run reports what is unanswered rather than
    prompting, so the host belongs in that list as well."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: False)

    result = cli_bootstrap()

    assert "Not configured yet (host," in result.output


def test_a_repository_named_rather_than_url_ed_is_still_cloned(tmp_path: Path) -> None:
    """prodockit-extensions#283. The prompt asks for "an existing
    repository to clone instead of the template", and a repository is
    called `report-az1234`, not
    `git@gitlab.surrey.ac.uk:comm058-2026/report-az1234.git`.

    That answer went to `git clone` verbatim and failed with `repository
    'report-az1234' does not exist` - which reads as though the
    repository were missing rather than the address incomplete."""
    context = _context(tmp_path, source_url="report-mb0105-v13", namespace="docs-as-code-test-team")
    plan = next(s for s in STAGES if s.id == "clone").plan(context)

    assert plan.commands[0][:2] == ["git", "clone"]
    assert plan.commands[0][2] == (
        "git@gitlab.surrey.ac.uk:docs-as-code-test-team/report-mb0105-v13.git"
    )


def test_a_group_and_name_only_needs_the_host_filling_in(tmp_path: Path) -> None:
    context = _context(tmp_path, source_url="other-group/report-x")
    plan = next(s for s in STAGES if s.id == "clone").plan(context)

    assert plan.commands[0][2] == "git@gitlab.surrey.ac.uk:other-group/report-x.git"


def test_a_url_is_used_exactly_as_given(tmp_path: Path) -> None:
    """Somebody who pasted a URL means it - including an https one, which
    a reader without a key set up may deliberately want."""
    for url in (
        "git@gitlab.surrey.ac.uk:g/r.git",
        "https://gitlab.surrey.ac.uk/g/r",
        "ssh://git@gitlab.surrey.ac.uk/g/r.git",
    ):
        context = _context(tmp_path, source_url=url)
        plan = next(s for s in STAGES if s.id == "clone").plan(context)
        assert plan.commands[0][2] == url, url


def test_a_blank_source_still_clones_the_template(tmp_path: Path) -> None:
    """The common case, and the default."""
    context = _context(tmp_path, source_url="")
    plan = next(s for s in STAGES if s.id == "clone").plan(context)

    assert plan.commands[0][2] == SURREY_GITLAB.template_remote


def test_a_bare_name_with_no_namespace_is_left_alone(tmp_path: Path) -> None:
    """Nothing to expand it with, so it is not expanded into a URL built
    from a blank - the failure stays git's own rather than an address
    bootstrap invented."""
    context = _context(tmp_path, source_url="report-x", namespace="")
    plan = next(s for s in STAGES if s.id == "clone").plan(context)

    assert plan.commands[0][2] == "report-x"
    assert "::" not in plan.commands[0][2] and ":/" not in plan.commands[0][2]


def test_a_trailing_git_suffix_is_not_doubled(tmp_path: Path) -> None:
    context = _context(tmp_path, source_url="report-x.git", namespace="grp")
    plan = next(s for s in STAGES if s.id == "clone").plan(context)

    assert plan.commands[0][2] == "git@gitlab.surrey.ac.uk:grp/report-x.git"


def _unknown_host_runner() -> FakeRunner:
    return FakeRunner(
        {
            "BatchMode": CommandResult(
                255, stderr="The authenticity of host 'x' can't be established."
            )
        }
    )


def test_an_unknown_host_is_accepted_here_not_in_another_terminal(tmp_path: Path) -> None:
    """The fingerprint question is the reader's to answer - that has not
    changed - but sending them to a second terminal to answer it is a
    step where people lose their place.

    `needs_terminal` hands over the real terminal, as it does for
    `ssh-add`'s passphrase, so ssh asks its own question in place."""
    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(
        _context(tmp_path, runner=_unknown_host_runner())
    )

    assert plan.needs_terminal, "ssh cannot ask without the terminal"
    command = " ".join(plan.commands[0])
    assert "ssh -T" in command
    assert "fingerprint" in plan.confirm


def test_accepting_a_fingerprint_drops_batchmode_but_keeps_the_timeout(tmp_path: Path) -> None:
    """`BatchMode=yes` is what makes a *check* safe (#225) - and exactly
    what stops ssh offering its fingerprint question. It is dropped only
    here, only after the reader has agreed to connect. `ConnectTimeout`
    stays, so an unreachable host still fails rather than hanging."""
    _write_keypair(tmp_path)
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(
        _context(tmp_path, runner=_unknown_host_runner())
    )
    command = " ".join(plan.commands[0])

    assert "BatchMode" not in command
    assert "ConnectTimeout=10" in command


def test_the_checking_probe_is_still_unable_to_ask_anything(tmp_path: Path) -> None:
    """The half that must not change. A check that can block is a broken
    check whatever it reports (#225)."""
    from prodockit.bootstrap.stages import _ssh_probe

    context = _context(tmp_path)
    assert "BatchMode=yes" in " ".join(_ssh_probe(context))
    assert "BatchMode" not in " ".join(_ssh_probe(context, interactive=True))


def test_a_known_host_is_still_guide_and_verify(tmp_path: Path) -> None:
    """Nothing to accept, so nothing to run - the stage stays instructions
    only, and its verification stays the stage's own check (#234)."""
    _write_keypair(tmp_path)
    runner = FakeRunner({"BatchMode": CommandResult(255, stderr="Permission denied (publickey).")})
    plan = next(s for s in STAGES if s.id == "ssh-upload").plan(_context(tmp_path, runner=runner))

    assert not plan.commands
    assert not plan.needs_terminal
    assert plan.confirm.startswith("Have you added the key")


def test_the_check_no_longer_tells_the_reader_to_run_it_themselves(tmp_path: Path) -> None:
    """The detail said "run `ssh -T ...` once and accept the fingerprint".
    Bootstrap does that now, so saying it would be instructing a reader to
    duplicate a step it is about to offer."""
    _write_keypair(tmp_path)
    runner = _unknown_host_runner()
    runner.responses.update(_agent(0, f"256 {LOADED_FINGERPRINT} al@surrey (ED25519)"))
    result = next(s for s in STAGES if s.id == "ssh-upload").check(
        _context(tmp_path, runner=runner)
    )

    assert result.status is Status.WRONG
    assert "not a known host on this machine yet" in result.detail
    assert "run `ssh" not in result.detail


def test_apply_shows_the_stages_that_are_already_done(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prodockit-extensions#284: `--apply` skipped satisfied stages in
    silence, so a reader could not tell whether they had been checked or
    simply forgotten."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    responses = _ready_machine(tmp_path)
    responses["code --list-extensions"] = CommandResult(0, "")

    result = cli_bootstrap("--apply", responses=responses, input="n\n" * 40)

    assert "ok    Visual Studio Code" in result.output
    assert "ok    Project cloned" in result.output


def test_apply_numbers_stages_absolutely_not_by_position_in_the_queue(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second half of #284. Numbering the outstanding stages 1..N
    meant the numbers agreed with nothing - `[1/17] Git` while actually
    standing at stage 2 of eighteen, and never matching what `prodockit
    bootstrap` had just listed."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    responses = _ready_machine(tmp_path)
    responses["code --list-extensions"] = CommandResult(0, "")

    result = cli_bootstrap("--apply", responses=responses, input="n\n" * 40)

    extensions = next(s for s in STAGES if s.id == "extensions")
    position = [s.id for s in STAGES].index("extensions") + 1
    assert f"[{position}/{len(STAGES)}] {extensions.summary}" in result.output


def test_a_stage_waiting_on_configuration_is_named_not_skipped(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An UNKNOWN stage has nothing to offer, but skipping it silently
    makes a stage disappear from the run entirely."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    save(tmp_path / "b.toml", _config(project_name=""))
    # `--apply` on an incomplete config asks the questions first, which
    # would consume the input below - the state under test here is the
    # apply loop meeting a stage that cannot be judged yet.
    monkeypatch.setattr("prodockit.cli._ask_for_configuration", lambda config, **kw: config)
    monkeypatch.setattr("prodockit.cli._offer_to_fill_gaps", lambda config, path: (config, False))

    result = cli_bootstrap("--apply", input="n\n" * 40)

    assert "?     Project cloned" in result.output
    assert "needs project_name" in result.output


def _windows_context(tmp_path: Path, *, cli: bool, app: bool = True, runner=None):
    """A Windows machine described rather than built.

    Windows install paths are backslash strings, which are a single
    filename on POSIX - so they cannot be created on disk here, and
    `exists` answers for them instead. That is what `Context.exists` is
    for.
    """
    return build_context(
        _config(),
        runner=runner or FakeRunner(),
        platform=WINDOWS,
        home=tmp_path,
        exists=lambda path: (
            cli if str(path).endswith("code.cmd") else (app and "Microsoft VS Code" in str(path))
        ),
        pdkboot=True,
    )


def test_windows_finds_code_where_the_installer_put_it(tmp_path: Path) -> None:
    """prodockit-extensions#292. VS Code's Windows installer adds `code`
    to PATH itself - but PATH is read when a process starts, so the shell
    that just ran `winget install` cannot see it. The stage reported a
    machine with VS Code installed as broken, and offered a Command
    Palette action that does not exist on Windows."""
    from prodockit.bootstrap.stages import vscode_command

    context = _windows_context(tmp_path, cli=True)

    found = vscode_command(context)
    assert found is not None and found.endswith("code.cmd")
    assert next(s for s in STAGES if s.id == "vscode").check(context).status is Status.OK


def test_the_extensions_stage_uses_the_path_it_found(tmp_path: Path) -> None:
    """Otherwise the session that just installed VS Code still cannot
    install extensions, and the reader is sent away to open a new
    terminal after all."""
    runner = FakeRunner({"--list-extensions": CommandResult(0, "")})
    context = _windows_context(tmp_path, cli=True, runner=runner)

    plan = next(s for s in STAGES if s.id == "extensions").plan(context)

    assert plan.commands[0][0].endswith("code.cmd")


def test_a_machine_without_vs_code_is_still_reported_missing(tmp_path: Path) -> None:
    """The fallbacks must survive: nothing installed is still MISSING,
    and an application with no CLI anywhere is still WRONG."""
    from prodockit.bootstrap.stages import vscode_command

    bare = _windows_context(tmp_path, cli=False, app=False)
    assert vscode_command(bare) is None
    assert next(s for s in STAGES if s.id == "vscode").check(bare).status is Status.MISSING

    app_only = _windows_context(tmp_path, cli=False, app=True)
    assert next(s for s in STAGES if s.id == "vscode").check(app_only).status is Status.WRONG


def test_macos_finds_the_cli_inside_the_application(tmp_path: Path) -> None:
    """prodockit-extensions#424.

    macOS installs the application without the command: `code` arrives
    only when somebody runs the Command Palette action, which readers
    routinely have not - and the binary was inside the app bundle the
    whole time. Every later stage that drives VS Code can use it.

    This replaces a test asserting the opposite. That was a deliberate
    decision, and #424 reverses it: doing the work is better than asking
    for permission to be able to.
    """
    from prodockit.bootstrap.stages import vscode_command

    context = _context(tmp_path, platform=MACOS, vscode_app=True)
    found = vscode_command(context)

    assert found is not None
    assert found.endswith("Contents/Resources/app/bin/code"), found
    result = next(s for s in STAGES if s.id == "vscode").check(context)
    assert result.status is Status.OK
    # ...and it does not borrow the Windows wording, which would be a lie
    # here: an app bundle is not on PATH and a new terminal will not help.
    assert "new terminal" not in result.detail
    assert "not on PATH" in result.detail


def test_a_machine_without_vs_code_still_reports_it_missing(tmp_path: Path) -> None:
    """The point of #424 is finding an install that is there, not
    inventing one that is not."""
    from prodockit.bootstrap.stages import vscode_command

    context = _context(tmp_path, platform=MACOS, vscode_app=False)

    assert vscode_command(context) is None
    assert next(s for s in STAGES if s.id == "vscode").check(context).status is Status.MISSING


def test_windows_finds_npm_by_path_when_the_bare_name_will_not_run(tmp_path: Path) -> None:
    """prodockit-extensions#295, the same trap as #292. `npm` on Windows
    is `npm.cmd`, and Python's subprocess uses CreateProcess, which does
    not apply PATHEXT - so a bare `npm` is "not found" on a machine where
    Node is installed correctly, and neither toolchain installs."""
    from prodockit.bootstrap.stages import npm_command

    context = build_context(
        _config(),
        runner=FakeRunner(),
        platform=WINDOWS,
        home=tmp_path,
        exists=lambda path: str(path).endswith("npm.cmd"),
    )

    assert npm_command(context).endswith("npm.cmd")
    plan = next(s for s in STAGES if s.id == "node").plan(context)
    installs = [c for c in plan.commands if "ci" in c]
    assert installs and all(c[0].endswith("npm.cmd") for c in installs)


def test_npm_is_left_alone_where_it_works(tmp_path: Path) -> None:
    """Everywhere else, and on a Windows machine where the bare name runs
    - a command that fails as `npm` should fail under the name the reader
    knows, not a path bootstrap guessed."""
    from prodockit.bootstrap.stages import npm_command

    assert npm_command(_context(tmp_path, platform=MACOS)) == "npm"
    assert npm_command(_context(tmp_path, platform=UBUNTU)) == "npm"
    working = FakeRunner({"npm": CommandResult(0, "10.9.2")})
    assert npm_command(_context(tmp_path, platform=WINDOWS, runner=working)) == "npm"
    # Nothing found anywhere: still `npm`, not a path that does not exist.
    assert npm_command(_context(tmp_path, platform=WINDOWS)) == "npm"


def test_msys2_says_where_it_looked_rather_than_failing_on_a_guess(tmp_path: Path) -> None:
    """`C:\\msys64` is winget's default, not a guarantee - and on an arm64
    Windows winget installs a different build again
    (prodockit-extensions#393).

        MSYS2 is not at C:\\msys64 - install it there, or run ...

    was said of a machine that had just installed MSYS2 successfully. So
    the script looks in several places, names all of them when it finds
    none, and picks the environment from the architecture rather than
    from an assumption: an arm64 install has no MINGW64 at all.
    """
    from prodockit.bootstrap.stages import _MSYS2_ROOTS

    runner = FakeRunner({"int.from_bytes": CommandResult(0, "0xaa64\n")})
    plan = next(s for s in STAGES if s.id == "pandoc").plan(
        _context(tmp_path, platform=WINDOWS, runner=runner)
    )
    pacman = next(c for c in plan.commands if "pacman" in " ".join(c))
    script = " ".join(pacman)

    assert len(_MSYS2_ROOTS) > 1
    for root in _MSYS2_ROOTS:
        assert root in script, root
    assert "was not found" in script
    assert "Looked in:" in script, "say where, not just that it failed"
    assert "exit 1" in script, "and fail, rather than carrying on without Pango"

    # The PATH entry follows the same environment, or WeasyPrint is
    # pointed at a directory that does not exist on this machine.
    path_command = next(c for c in plan.commands if "SetEnvironmentVariable" in " ".join(c))
    entry = " ".join(path_command)
    assert "clangarm64" in entry
    assert "ucrt64" not in entry
    assert "Join-Path" in entry


def test_the_csl_download_turns_powershells_progress_bar_off(tmp_path: Path) -> None:
    """On PowerShell 5.1 - still the Windows default - Invoke-WebRequest's
    progress bar makes a download dramatically slower, which reads as a
    hang (#244)."""
    plan = next(s for s in STAGES if s.id == "csl-style").plan(_context(tmp_path, platform=WINDOWS))
    script = " ".join(plan.commands[0])

    assert "$ProgressPreference = 'SilentlyContinue'" in script
    assert script.index("ProgressPreference") < script.index("Invoke-WebRequest")


def test_an_install_is_never_run_with_its_output_swallowed(tmp_path: Path) -> None:
    """prodockit-extensions#244: `apt update`, a 100 MB download and
    `apt install` behind it produced minutes of silence, because applying
    captured everything. A silent terminal is indistinguishable from a
    hung one, and readers interrupted installs that were working."""
    from prodockit.bootstrap import apply_stage

    runner = FakeRunner({"brew": CommandResult(0), "code": CommandResult(0)})
    apply_stage(_context(tmp_path, runner=runner), next(s for s in STAGES if s.id == "vscode"))

    installs = [
        capture
        for command, capture in zip(runner.calls, runner.captures, strict=False)
        if command[0] == "brew"
    ]
    assert installs, "the install should have run"
    assert not any(installs), "an installer's own output has to reach the terminal"
    # And the re-check that follows it stays captured, since it reads
    # what the command printed rather than showing it.
    assert runner.captures[-1] is True


def test_checks_are_still_captured(tmp_path: Path) -> None:
    """The other half. A check *reads* what a command printed - `pandoc
    --version`, `ssh -T`'s greeting - and there are dozens per run, so
    they must not spill onto the screen."""
    runner = FakeRunner(
        {
            "pandoc": CommandResult(0, "pandoc 3.10.1"),
            "fc-list": CommandResult(0, "Inter\nJetBrains Mono"),
        }
    )
    next(s for s in STAGES if s.id == "pandoc").check(_context(tmp_path, runner=runner))

    assert all(runner.captures), "a check that printed its own output would bury the report"


def test_a_failure_with_nothing_captured_points_at_the_screen() -> None:
    """With the output streaming past, there is usually no stderr left to
    summarise - so it says where to look rather than inventing a
    sentence."""
    from prodockit.cli import _first_meaningful_line

    # The summary function still works for the captured cases that remain.
    assert _first_meaningful_line("E: broken") == "E: broken"
    assert _first_meaningful_line("") == "no output"


def test_the_architecture_is_named_rather_than_worked_out_in_a_shell(tmp_path: Path) -> None:
    """prodockit-extensions#287. The command carried
    `case "$arch" in amd64) arch=x64 ;; esac`, which reads as a hardcoded
    target even though it only maps dpkg's name onto VS Code's - and a
    reader is being asked to approve it.

    Resolved when the plan is built, so it names the machine they are
    on."""
    for reported, expected in (("arm64", "arm64"), ("amd64", "x64")):
        runner = FakeRunner({"dpkg --print-architecture": CommandResult(0, reported)})
        plan = next(s for s in STAGES if s.id == "vscode").plan(
            _context(tmp_path, runner=runner, platform=UBUNTU)
        )
        url = next(c for c in plan.commands if c[0] == "curl")[-1]
        assert url.endswith(f"linux-deb-{expected}/stable"), reported
        assert "$arch" not in " ".join(" ".join(c) for c in plan.commands)


def test_an_unaskable_dpkg_falls_back_to_the_common_architecture(tmp_path: Path) -> None:
    """Better than an empty URL, and x64 is what most machines are."""
    plan = next(s for s in STAGES if s.id == "vscode").plan(_context(tmp_path, platform=UBUNTU))

    assert next(c for c in plan.commands if c[0] == "curl")[-1].endswith("linux-deb-x64/stable")


def test_the_privileged_half_of_the_install_is_its_own_command(tmp_path: Path) -> None:
    """The download needs no privileges and the install does. Splitting
    them keeps `sudo` at the front of a command where it can be seen -
    and where a timestamp expiring mid-run prompts visibly rather than
    inside a shell nobody is watching (#287, #244)."""
    plan = next(s for s in STAGES if s.id == "vscode").plan(_context(tmp_path, platform=UBUNTU))

    assert not any(c[0] == "bash" for c in plan.commands), "no shell wrapper left"
    assert next(c for c in plan.commands if c[0] == "curl")[0] != "sudo"
    assert any(c[0] == "sudo" and c[-1] == "/tmp/code.deb" for c in plan.commands)


def test_the_path_is_refreshed_between_a_stages_commands(tmp_path: Path) -> None:
    """prodockit-extensions#300: `winget install Git.Git` succeeded and
    the `git config` on the next line reported "git: not found".

    A Windows installer adds itself to PATH by writing the registry; a
    running process never sees that, because its environment was copied
    when it started. Reading the registry back is what a new terminal
    does, and doing it here is why the reader does not have to open
    one."""
    import prodockit.bootstrap as bootstrap
    from prodockit.bootstrap import apply_stage

    refreshed: list[int] = []
    original = bootstrap.refresh_windows_path
    bootstrap.refresh_windows_path = lambda: refreshed.append(1)  # type: ignore[assignment]
    try:
        runner = FakeRunner({"brew": CommandResult(0), "code": CommandResult(0)})
        apply_stage(_context(tmp_path, runner=runner), next(s for s in STAGES if s.id == "vscode"))
    finally:
        bootstrap.refresh_windows_path = original  # type: ignore[assignment]

    assert refreshed, "a command that may have changed PATH must be followed by a refresh"


def test_refreshing_is_a_no_op_off_windows() -> None:
    """It reads the Windows registry, so everywhere else there is
    nothing to read and nothing to change."""
    from prodockit.bootstrap import refresh_windows_path

    before = os.environ.get("PATH")
    assert refresh_windows_path() is None
    assert os.environ.get("PATH") == before, "another platform's PATH must be left alone"


def test_a_dropped_connection_does_not_blame_the_key(tmp_path: Path) -> None:
    """The host accepts the connection, then closes it mid-authentication
    without a verdict. That used to fall through to "could not confirm
    authentication", which tells a reader nothing they can act on - and
    the natural reading of a failing auth step is that the key was
    refused, which cost an afternoon to disprove (#304)."""
    machine = _ready_machine(tmp_path)
    machine["ssh"] = CommandResult(255, stderr="Connection closed by 131.227.81.118 port 22")
    result = next(s for s in STAGES if s.id == "ssh-upload").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    assert result.status is Status.WRONG
    assert "closed it" in result.detail
    assert "key is probably fine" in result.detail
    assert "rejected the key" not in result.detail


def test_a_real_rejection_still_says_so(tmp_path: Path) -> None:
    """`Permission denied` is a clean answer from a working server - the
    key really is wrong, or really is not uploaded. Reading it as a
    refusal would tell the reader to wait when the fix is in their
    hands."""
    machine = _ready_machine(tmp_path)
    machine["ssh"] = CommandResult(
        255, stderr="git@gitlab.surrey.ac.uk: Permission denied (publickey)."
    )
    result = next(s for s in STAGES if s.id == "ssh-upload").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    assert result.status is Status.MISSING
    assert "rejected the key" in result.detail


def test_a_dropped_connection_is_not_read_as_a_missing_project(tmp_path: Path) -> None:
    """`git ls-remote` failing normally means "you have not created it in
    the browser yet", which is the wrong instruction when the host is
    simply refusing to talk."""
    machine = _ready_machine(tmp_path)
    machine["git ls-remote"] = CommandResult(
        128, stderr="Connection closed by 131.227.81.118 port 22"
    )
    result = next(s for s in STAGES if s.id == "own-project").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    assert result.status is Status.WRONG
    assert "closed it" in result.detail
    assert "not reachable" not in result.detail


def test_only_surrey_clones_from_surrey() -> None:
    """Surrey mirrors the template onto its own GitLab so a student never
    needs a GitHub account to start. Every other host has no such mirror,
    so it clones the GitHub original - which is also what makes testing
    possible while Surrey is unreachable."""
    from prodockit.bootstrap import HOSTS

    assert HOSTS["surrey"].template_remote.startswith("git@gitlab.surrey.ac.uk:")
    for key in ("github", "gitlab"):
        assert HOSTS[key].template_remote == "git@github.com:buckwem/prodockit-template.git"


def test_github_clones_the_template_from_github(tmp_path: Path) -> None:
    """The end of the chain that matters: a run configured for github.com
    must actually build its clone command against GitHub, not merely
    carry the right string in a record."""
    context = _context(tmp_path, host="github.com", namespace="buckwem")
    plan = next(s for s in STAGES if s.id == "clone").plan(context)
    script = " ".join(" ".join(command) for command in plan.commands)

    assert "git@github.com:buckwem/prodockit-template.git" in script
    assert "gitlab.surrey.ac.uk" not in script


def test_github_uses_its_own_key_rather_than_the_gitlab_one(tmp_path: Path) -> None:
    """`key_suffix` differs per family, so a reader with both hosts set up
    has two keys and each stanza points at its own. Sharing one would
    make removing a key from one host break the other."""
    context = _context(tmp_path, host="github.com")
    plan = next(s for s in STAGES if s.id == "ssh-config").plan(context)
    script = " ".join(" ".join(command) for command in plan.commands)

    assert "id_ed25519_github" in script
    assert "Host github.com" in script
    assert "id_ed25519_gitlab" not in script


def test_githubs_own_greeting_is_what_proves_authentication(tmp_path: Path) -> None:
    """`ssh -T` exits non-zero on success against both hosts, so the
    greeting is the only signal - and GitHub's differs from GitLab's.
    Matching GitLab's string would report a working GitHub key as
    broken."""
    machine = _ready_machine(tmp_path)
    github_key = tmp_path / ".ssh" / "id_ed25519_github"
    github_key.write_text("private", encoding="utf-8")
    github_key.with_suffix(".pub").write_text("public", encoding="utf-8")
    machine["ssh"] = CommandResult(
        1,
        stderr="Hi buckwem! You've successfully authenticated, but GitHub does not provide shell access.",
    )
    result = next(s for s in STAGES if s.id == "ssh-upload").check(
        _context(tmp_path, host="github.com", runner=FakeRunner(machine))
    )

    assert result.status is Status.OK


def test_the_username_question_names_the_host_that_was_answered() -> None:
    """ "Your GitLab username" is simply wrong once the answer was
    github.com."""
    from prodockit.bootstrap import PROMPTS, question_for

    question = dict(PROMPTS)["username"]
    assert "GitLab" not in question
    assert "github.com" in question_for(_config(host="github.com"), "username", question)


WINGET_NO_UPGRADE = 2316632107  # 0x8A15002B, as Windows reports it


def test_winget_saying_already_installed_is_not_a_failure() -> None:
    """The exact code seen on Windows when git was already present:
    `No available upgrade found` followed by exit 2316632107 (#309)."""
    from prodockit.bootstrap import benign_outcome

    outcome = CommandResult(WINGET_NO_UPGRADE, stdout="No available upgrade found.")
    assert benign_outcome(["winget", "install", "--id", "Git.Git", "-e"], outcome)
    assert benign_outcome(["winget.exe", "install", "--id", "Git.Git"], outcome)


def test_the_same_code_from_anything_else_is_still_a_failure() -> None:
    """Narrow on purpose: the code means "already installed" for winget
    and nothing at all for git, so excusing it everywhere would swallow a
    genuine failure."""
    from prodockit.bootstrap import benign_outcome

    outcome = CommandResult(WINGET_NO_UPGRADE)
    assert not benign_outcome(["git", "config", "--global", "user.name", "Ada"], outcome)
    assert not benign_outcome([], outcome)


def test_a_real_winget_failure_still_stops_the_run() -> None:
    """A package that genuinely could not be installed must not be waved
    through - the set holds only codes seen to mean "already done"."""
    from prodockit.bootstrap import benign_outcome

    assert not benign_outcome(["winget", "install", "--id", "Git.Git"], CommandResult(1))
    assert not benign_outcome(["winget", "install", "--id", "Git.Git"], CommandResult(0x8A150044))


def test_the_rest_of_the_plan_runs_after_a_no_op_install(tmp_path: Path) -> None:
    """The fault this fixes. Stopping at the winget line abandoned the
    two `git config` commands behind it, so git was left installed and
    unconfigured while the run reported an install failure."""
    from prodockit.bootstrap import apply_stage

    machine = _ready_machine(tmp_path)
    # The state that produces this: git is not on *this process's* PATH,
    # so the stage plans an install - and winget then reports the package
    # as already present, because it is.
    machine["git --version"] = CommandResult(1, stderr="git: not found")
    machine["winget"] = CommandResult(WINGET_NO_UPGRADE, stdout="No available upgrade found.")
    runner = FakeRunner(machine)
    context = _context(tmp_path, platform=WINDOWS, runner=runner)

    result = apply_stage(context, next(s for s in STAGES if s.id == "git"))

    ran = [" ".join(c) for c in result.ran]
    assert any("winget" in c for c in ran)
    assert any("user.name" in c for c in ran), "the plan carried on"
    assert any("user.email" in c for c in ran)
    assert result.failed is None


def test_pdkboot_retries_a_temporary_remote_service_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Marketplace 503 is not a machine fault and usually clears before
    asking the reader to restart the whole run is useful."""
    from prodockit.bootstrap import Stage, apply_stage

    class Recovers(FakeRunner):
        attempts = 0

        def run(self, command, cwd=None, timeout=None, capture=True):  # type: ignore[no-untyped-def]
            if "--install-extension" in command:
                self.attempts += 1
                if self.attempts == 1:
                    return CommandResult(1, stderr="Server returned 503")
                return CommandResult(0)
            return super().run(command, cwd, timeout, capture)

    delays: list[int] = []
    monkeypatch.setattr("prodockit.bootstrap.time.sleep", delays.append)
    runner = Recovers()
    context = _context(tmp_path, runner=runner)
    stage = Stage(
        "extensions",
        "VS Code extensions",
        lambda context: CheckResult(Status.OK),
        lambda context: Plan(commands=[["code", "--install-extension", "ms-python.python"]]),
    )

    result = apply_stage(context, stage)

    assert result.failed is None
    assert runner.attempts == 2
    assert delays == [2]


@pytest.mark.parametrize(
    "message",
    [
        "Could not resolve host: registry.npmjs.org",
        "npm ERR! code ECONNRESET",
        "operation timed out",
    ],
)
def test_pdkboot_retries_safe_downloads_after_transient_network_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    from prodockit.bootstrap import Stage, apply_stage

    class Recovers(FakeRunner):
        attempts = 0

        def run(self, command, cwd=None, timeout=None, capture=True):  # type: ignore[no-untyped-def]
            self.attempts += 1
            if self.attempts == 1:
                return CommandResult(1, stderr=message)
            return CommandResult(0)

    monkeypatch.setattr("prodockit.bootstrap.time.sleep", lambda _delay: None)
    runner = Recovers()
    context = _context(tmp_path, runner=runner)
    stage = Stage(
        "node",
        "Node",
        lambda context: CheckResult(Status.OK),
        lambda context: Plan(commands=[["npm", "ci"]]),
    )

    result = apply_stage(context, stage)

    assert result.ok
    assert runner.attempts == 2


def test_pdkboot_does_not_retry_a_command_that_can_duplicate_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prodockit.bootstrap import Stage, apply_stage

    runner = FakeRunner({"git push": CommandResult(1, stderr="connection reset")})
    delays: list[int] = []
    monkeypatch.setattr("prodockit.bootstrap.time.sleep", delays.append)
    context = _context(tmp_path, runner=runner)
    stage = Stage(
        "first-push",
        "Push",
        lambda context: CheckResult(Status.MISSING),
        lambda context: Plan(commands=[["git", "push"]]),
    )

    result = apply_stage(context, stage)

    assert result.failed is not None
    assert len(runner.calls) == 1
    assert delays == []


TEMPLATE_ORIGIN = "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git"


def _clone_pointing_at(tmp_path: Path, origin: str) -> FakeRunner:
    machine = _ready_machine(tmp_path)
    machine["remote get-url origin"] = CommandResult(0, f"{origin}\n")
    return FakeRunner(machine)


def test_creating_the_project_is_not_blocked_by_the_history_reset(tmp_path: Path) -> None:
    """It was, and that was wrong. The repository lives on the *host*, and
    `rm -rf .git` is local - so nothing about creating it is thrown away
    by the reset, unlike the repoint in the stage below.

    Blocking it made the retry loop unescapable: the reader created the
    repository, answered yes, and was told the clone still points at the
    template - a fact about their machine that creating a repository
    cannot change (#336).
    """
    result = next(s for s in STAGES if s.id == "own-project").check(
        _context(tmp_path, runner=_clone_pointing_at(tmp_path, TEMPLATE_ORIGIN))
    )

    assert result.status is not Status.BLOCKED


def test_the_remote_stage_never_reports_the_template_as_ok(tmp_path: Path) -> None:
    """The rule this exists to enforce. A run must not be able to finish
    with origin pointing at the template: for a student that fails at the
    first push, and for anyone with write access to the template it
    pushes their coursework into it."""
    result = next(s for s in STAGES if s.id == "remote").check(
        _context(tmp_path, runner=_clone_pointing_at(tmp_path, TEMPLATE_ORIGIN))
    )

    assert result.status is Status.BLOCKED
    assert result.needs_work, "never reads as finished"
    assert "still the template" in result.detail


def test_a_blocked_stage_gets_no_plan(tmp_path: Path) -> None:
    """The whole point: `rm -rf .git` deletes every remote, so a repoint
    and its `sync-repo` run now would be thrown away by the reset that
    has to come first."""
    reports = plan_all(_context(tmp_path, runner=_clone_pointing_at(tmp_path, TEMPLATE_ORIGIN)))
    blocked = [r for r in reports if r.result.status is Status.BLOCKED]

    assert {r.stage.id for r in blocked} == {"remote"}, (
        "only the repoint is undone by the reset; the repository on the host is not"
    )
    assert all(r.plan is None for r in blocked), "no commands to be undone"


def test_applying_never_runs_a_blocked_stage(tmp_path: Path) -> None:
    """A blocked stage has no plan, and the apply loop selects on that -
    so this holds by construction rather than by a second rule that could
    drift out of step."""
    reports = plan_all(_context(tmp_path, runner=_clone_pointing_at(tmp_path, TEMPLATE_ORIGIN)))
    would_apply = [r.stage.id for r in reports if r.needs_work and r.plan is not None]

    assert "remote" not in would_apply
    assert "own-project" not in would_apply


def test_the_reset_unblocks_both_stages(tmp_path: Path) -> None:
    """After `rm -rf .git && git init` there is no origin at all, which
    is the state the two stages exist for - so blocking must not outlast
    the thing it waits on."""
    machine = _ready_machine(tmp_path)
    machine["remote get-url origin"] = CommandResult(128, stderr="No such remote 'origin'")
    context = _context(tmp_path, runner=FakeRunner(machine))

    for stage_id in ("own-project", "remote"):
        result = next(s for s in STAGES if s.id == stage_id).check(context)
        assert result.status is not Status.BLOCKED, stage_id


def test_a_clone_of_your_own_repository_is_never_blocked(tmp_path: Path) -> None:
    """`source_url` clones already belong to the reader, so there is no
    template history to separate from and nothing to wait for."""
    own = "git@gitlab.surrey.ac.uk:comm058-2026/report-al01234.git"
    context = _context(
        tmp_path, runner=_clone_pointing_at(tmp_path, own), source_url="report-al01234"
    )

    for stage_id in ("own-project", "remote"):
        result = next(s for s in STAGES if s.id == stage_id).check(context)
        assert result.status is Status.OK, stage_id


def test_a_successful_ssh_probe_is_never_a_failed_command() -> None:
    """`ssh -T` against a git host exits non-zero even when it works -
    there is no shell to give you. A reader who accepted the fingerprint
    and authenticated was told `failed: exit status 1` (#316)."""
    from prodockit.bootstrap import benign_outcome

    greeted = CommandResult(
        1,
        stderr="Hi buckwem! You've successfully authenticated, but GitHub does not provide shell access.",
    )
    assert benign_outcome(["ssh", "-T", "-o", "ConnectTimeout=10", "git@github.com"], greeted)


def test_a_rejected_ssh_probe_is_also_not_fatal_here(tmp_path: Path) -> None:
    """Deliberate: the exit code cannot tell success from failure, so
    neither case may stop the run. The stage's own check re-runs the
    probe and reads the greeting, which is the one thing that can."""
    from prodockit.bootstrap import benign_outcome

    denied = CommandResult(255, stderr="git@github.com: Permission denied (publickey).")
    assert benign_outcome(["ssh", "-T", "git@github.com"], denied)

    machine = _ready_machine(tmp_path)
    machine["ssh"] = denied
    result = next(s for s in STAGES if s.id == "ssh-upload").check(
        _context(tmp_path, host="github.com", runner=FakeRunner(machine))
    )
    assert result.needs_work, "the check still catches it"


def test_other_ssh_commands_are_not_excused() -> None:
    """Only the `-T` probe has a meaningless exit code. An `ssh` doing
    anything else is a normal command."""
    from prodockit.bootstrap import benign_outcome

    assert not benign_outcome(["ssh", "git@github.com", "some-command"], CommandResult(255))
    assert not benign_outcome(["ssh-add", "-l"], CommandResult(1))


def test_accepting_the_host_key_lets_the_run_continue(tmp_path: Path) -> None:
    """End to end: the stage only *plans* the probe when the host is
    unknown, which is the state a reader accepting a fingerprint is in -
    so the machine has to be described that way, or the plan carries no
    commands and this tests nothing.

    The assertion is that the run is not stopped by the probe's exit
    code. What the probe then proves is the verification's business, and
    it is left to say so.
    """
    from prodockit.bootstrap import apply_stage

    machine = _ready_machine(tmp_path)
    machine["ssh"] = CommandResult(
        1, stderr="The authenticity of host 'github.com' can't be established."
    )
    context = _context(tmp_path, host="github.com", runner=FakeRunner(machine))

    result = apply_stage(context, next(s for s in STAGES if s.id == "ssh-upload"))

    assert any("ssh" in c[0] for c in result.ran), "the probe really ran"
    assert result.failed is None, "its exit code must not stop the run"


def test_the_key_plan_creates_the_ssh_directory_first(tmp_path: Path) -> None:
    """`ssh-keygen` does not create the directory it writes into, and
    fails naming the key rather than the missing folder (#318)."""
    plan = next(s for s in STAGES if s.id == "ssh-key").plan(_context(tmp_path))
    script = [" ".join(c) for c in plan.commands]

    assert any("mkdir" in c for c in script), "the directory has to exist first"
    assert script.index(next(c for c in script if "mkdir" in c)) < script.index(
        next(c for c in script if "ssh-keygen" in c)
    ), "and be made before the key is written"


def test_a_fresh_posix_machine_gets_a_private_ssh_directory(tmp_path: Path) -> None:
    """ssh refuses to use a key others can read, and the same reasoning
    applies to the directory holding it."""
    plan = next(s for s in STAGES if s.id == "ssh-key").plan(_context(tmp_path))
    chmods = [c for c in plan.commands if c[0] == "chmod"]

    assert [c[1] for c in chmods] == ["700"]
    assert chmods[0][2].endswith(".ssh")


def test_windows_makes_the_directory_without_chmod(tmp_path: Path) -> None:
    """No chmod on Windows, and PowerShell rather than mkdir - the same
    shape the ssh-config stage already uses."""
    plan = next(s for s in STAGES if s.id == "ssh-key").plan(_context(tmp_path, platform=WINDOWS))
    script = " ".join(" ".join(c) for c in plan.commands)

    assert "New-Item -ItemType Directory" in script
    assert "chmod" not in script
    assert script.index("New-Item") < script.index("ssh-keygen")


def test_an_existing_ssh_directory_is_left_alone(tmp_path: Path) -> None:
    """Only created when absent, so a reader's existing directory keeps
    whatever permissions they chose for it."""
    (tmp_path / ".ssh").mkdir(exist_ok=True)
    plan = next(s for s in STAGES if s.id == "ssh-key").plan(_context(tmp_path))
    script = " ".join(" ".join(c) for c in plan.commands)

    assert "mkdir" not in script
    assert "chmod" not in script
    assert "ssh-keygen" in script


def test_nobody_is_told_to_switch_pages_on_any_more(tmp_path: Path) -> None:
    """The template's workflow enables Pages itself now
    (prodockit-template#169), so the instruction describes work already
    done - and a step that does nothing is one more thing to skim past in
    a list where the others matter (#336).

    Nothing is taken on trust by dropping it: stage 19 still checks the
    published site actually answers. What has gone is the instruction,
    not the verification.
    """
    plan = next(s for s in STAGES if s.id == "own-project").plan(
        _context(tmp_path, host="github.com")
    )
    said = " ".join("\n".join(plan.instructions).split())

    assert "Pages in the left sidebar" not in said
    assert "Build and deployment" not in said
    assert "Set visibility" in said, "the other steps are untouched"
    assert any(s.id == "site" for s in STAGES), "still verified, one stage later"


def test_github_warns_that_a_private_repo_still_publishes_publicly(tmp_path: Path) -> None:
    """The repository stays private and the site does not - which is what
    GitHub itself warns when Pages is switched on, and the thing a reader
    putting drafts in docs/ needs to know (#324).

    Private is still the advice: Pages publishes from a private
    repository, verified against a real one.
    """
    plan = next(s for s in STAGES if s.id == "own-project").plan(
        _context(tmp_path, host="github.com")
    )
    said = "\n".join(plan.instructions)

    assert "Set visibility to Private." in said, "private is still right"
    assert "the published site will be public" in said
    assert "docs/" in said, "say where the risk actually is"


def test_gitlab_still_simply_says_private(tmp_path: Path) -> None:
    """GitLab publishes Pages from a private project, so Private is
    better advice there and the extra steps do not apply - the difference
    is a value on the host, not a branch in the stage."""
    plan = next(s for s in STAGES if s.id == "own-project").plan(_context(tmp_path))
    said = "\n".join(plan.instructions)

    assert "Set visibility to Private." in said
    assert "GitHub Actions" not in said
    assert "Pro, Team" not in said


def test_the_extra_steps_come_after_the_project_is_created(tmp_path: Path) -> None:
    """They are things to do *to* the new repository, so they cannot
    sensibly be read before the step that creates it."""
    plan = next(s for s in STAGES if s.id == "own-project").plan(
        _context(tmp_path, host="github.com")
    )
    creating = next(i for i, s in enumerate(plan.instructions) if "create a blank" in s.lower())
    pages = next(i for i, s in enumerate(plan.instructions) if "Pages" in s)

    assert pages > creating


#: What the shallow probe finds in a repository that really is a project.
PROJECT_TREE = "zensical.toml\nREADME.md\ndocs\nrequirements.txt\n"


def _host_with_project(tmp_path: Path, refs: str, tree: str = PROJECT_TREE) -> FakeRunner:
    """A host whose project answers `git ls-remote` with `refs`, and whose
    shallow probe finds `tree`.

    Both are needed: refs say the repository is not empty, and the tree
    says it holds a project rather than a stray file (#332).
    """
    machine = _ready_machine(tmp_path)
    machine["git ls-remote"] = CommandResult(0, refs)
    machine["ls-tree"] = CommandResult(0, tree)
    return FakeRunner(machine)


def test_a_recorded_choice_is_what_the_clone_stage_reads(tmp_path: Path) -> None:
    """Detection lives in `--configure`, which records the answer. The
    stage reads that rather than asking the host again, which is what
    keeps plan-building free of network calls (#332)."""
    machine = _ready_machine(tmp_path)
    machine["git ls-remote"] = CommandResult(0, "abc123\trefs/heads/main\n")
    machine["ls-tree"] = CommandResult(0, PROJECT_TREE)
    context = _context(
        tmp_path,
        host="github.com",
        namespace="buckwem",
        project_name="report-windows-v1",
        runner=FakeRunner(machine),
    )
    script = " ".join(next(s for s in STAGES if s.id == "clone").plan(context).commands[0])

    assert "prodockit-template" in script, "no source_url recorded, so the template"


def test_an_empty_project_still_gets_the_template(tmp_path: Path) -> None:
    """A repository created in the browser and never pushed to is the
    ordinary first run. Cloning it would leave nothing to work on, so the
    two cases are told apart on evidence: an empty repository answers
    successfully and lists no refs."""
    context = _context(
        tmp_path,
        host="github.com",
        namespace="buckwem",
        project_name="report-windows-v1",
        runner=_host_with_project(tmp_path, ""),
    )
    script = " ".join(next(s for s in STAGES if s.id == "clone").plan(context).commands[0])

    assert "prodockit-template" in script


def test_a_project_that_does_not_exist_gets_the_template(tmp_path: Path) -> None:
    machine = _ready_machine(tmp_path)
    machine["git ls-remote"] = CommandResult(128, stderr="repository not found")
    context = _context(tmp_path, host="github.com", runner=FakeRunner(machine))
    script = " ".join(next(s for s in STAGES if s.id == "clone").plan(context).commands[0])

    assert "prodockit-template" in script


def test_an_explicit_source_url_still_wins(tmp_path: Path) -> None:
    """Detection is a default, not an override. Someone who named a
    repository meant it."""
    context = _context(
        tmp_path,
        host="github.com",
        namespace="buckwem",
        project_name="report-windows-v1",
        source_url="some-other-repo",
        runner=_host_with_project(tmp_path, "abc123\trefs/heads/main\n"),
    )
    script = " ".join(next(s for s in STAGES if s.id == "clone").plan(context).commands[0])

    assert "some-other-repo.git" in script


def test_a_student_given_a_repo_is_never_offered_the_history_reset(tmp_path: Path) -> None:
    """The case this exists for: a taught module hands the student a
    repository that already holds their starting point. Deleting its
    history would throw that away, and there is no undo.

    It holds because `fresh-history` keys off `origin` still being the
    template, and a clone of the reader's own project never is - but it is
    the property that matters most here, so it is asserted rather than
    left to fall out (#311, #327).
    """
    own = "git@github.com:buckwem/report-windows-v1.git"
    machine = _ready_machine(tmp_path)
    machine["remote get-url origin"] = CommandResult(0, f"{own}\n")
    machine["git ls-remote"] = CommandResult(0, "abc123\trefs/heads/main\n")
    context = _context(
        tmp_path,
        host="github.com",
        namespace="buckwem",
        project_name="report-windows-v1",
        runner=FakeRunner(machine),
    )

    result = next(s for s in STAGES if s.id == "fresh-history").check(context)

    assert result.status is Status.OK
    assert "a history of its own" in result.detail


def test_saying_no_to_a_destructive_step_does_not_then_offer_it(
    cli_bootstrap, tmp_path: Path
) -> None:
    """Reported from real use. "Delete the template's history and start a
    new repository? [Y/n]: n" printed the commands anyway and asked again,
    which reads as the tool ignoring a refusal (#330).

    The answer was collected and discarded - it had been written as a bare
    acknowledgement, which is defensible for "have you uploaded the key?"
    and not for a deletion that cannot be undone.
    """
    machine = _ready_machine(tmp_path)
    project = tmp_path / "GitLab" / "report-al01234"
    machine["remote get-url origin"] = CommandResult(
        0, "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git\n"
    )
    (project / ".git").mkdir(parents=True, exist_ok=True)

    result = cli_bootstrap("--apply", responses=machine, input="n\n" * 30)

    assert "Archive the template's history" in result.output
    assert "Move-Item" not in result.output, "a refusal must not be followed by the commands"


def test_the_reset_only_ever_deletes_the_templates_history(tmp_path: Path) -> None:
    """What makes defaulting to yes safe: the plan that deletes history
    is reachable only while `origin` still points at the template, and a
    clone carrying the reader's own gets a one-line setting instead
    (#332, #356)."""
    machine = _ready_machine(tmp_path)
    machine["remote get-url origin"] = CommandResult(0, SURREY_GITLAB.template_remote)
    from_template = next(s for s in STAGES if s.id == "fresh-history").plan(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    own = dict(machine)
    own["remote get-url origin"] = CommandResult(0, "git@github.com:buckwem/report.git\n")
    own["config core.fileMode"] = CommandResult(0, "true\n")
    mine = next(s for s in STAGES if s.id == "fresh-history").plan(
        _context(tmp_path, host="github.com", runner=FakeRunner(own))
    )

    assert any("git.pdk-template-backup" in " ".join(c) for c in from_template.commands)
    assert not any("git.pdk-template-backup" in " ".join(c) for c in mine.commands), (
        "never archive the reader's own history"
    )
    assert mine.commands == [["git", "config", "core.fileMode", "false"]]


def test_there_is_nothing_to_reset_before_there_is_a_clone(tmp_path: Path) -> None:
    """It reported "no clone yet" and then offered to `rm -rf` a `.git`
    that does not exist, and `git init` in a directory that does not
    either (#330)."""
    # Deliberately not `_ready_machine`: that one creates the clone, which
    # is the whole state this is about not having.
    save(tmp_path / "b.toml", _config())
    reports = plan_all(_context(tmp_path))
    history = next(r for r in reports if r.stage.id == "fresh-history")

    assert history.result.status is Status.BLOCKED
    assert "no clone yet" in history.result.detail
    assert history.plan is None, "nothing to run on a directory that is not there"


def _own_project_machine(tmp_path: Path) -> dict[str, CommandResult]:
    machine = _ready_machine(tmp_path)
    machine["git ls-remote"] = CommandResult(0, "abc123\trefs/heads/main\n")
    machine["ls-tree"] = CommandResult(0, PROJECT_TREE)
    return machine


def test_the_template_and_a_named_repository_are_not_second_guessed(tmp_path: Path) -> None:
    """Neither is a surprise: one is the default, the other was typed by
    the reader. Only detection needs confirming."""
    template = next(s for s in STAGES if s.id == "clone").plan(_context(tmp_path))
    named = next(s for s in STAGES if s.id == "clone").plan(
        _context(
            tmp_path, source_url="some-repo", runner=FakeRunner(_own_project_machine(tmp_path))
        )
    )

    assert not template.instructions
    assert not named.instructions


def test_the_report_says_which_repository_was_used(tmp_path: Path) -> None:
    """The one place a reader can check what was decided, after the prompt
    has scrolled away."""
    machine = _ready_machine(tmp_path)
    machine["remote get-url origin"] = CommandResult(
        0, "git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git\n"
    )
    from_template = next(s for s in STAGES if s.id == "clone").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )
    own = next(s for s in STAGES if s.id == "clone").check(
        _context(tmp_path, runner=FakeRunner(_ready_machine(tmp_path)))
    )

    assert "from the template" in from_template.detail
    assert "your own project" in own.detail


def test_an_own_history_clone_is_never_offered_the_reset(tmp_path: Path) -> None:
    """It reported wrong only because `core.fileMode` was unset, and its
    plan was still `rm -rf .git` - offering to delete the reader's real
    history because a git option was off (#332)."""
    machine = _ready_machine(tmp_path)
    machine["remote get-url origin"] = CommandResult(
        0, "git@github.com:buckwem/report-windows-v1.git\n"
    )
    machine["config core.fileMode"] = CommandResult(0, "true\n")
    plan = next(s for s in STAGES if s.id == "fresh-history").plan(
        _context(tmp_path, host="github.com", runner=FakeRunner(machine))
    )

    assert plan.commands == [["git", "config", "core.fileMode", "false"]]
    assert not plan.destructive, "nothing here destroys anything"
    assert not any("rm -rf" in " ".join(c) for c in plan.commands)


def _configured(
    cli_bootstrap,
    monkeypatch,
    *,
    answer: str,
    exists: bool = True,
    has_content: bool = True,
    reachable: bool = True,
) -> object:
    """A `--configure` run against a described host.

    `exists` and `has_content` are separate because an *empty* issued
    repository is still a decision: its permissions are what decide who
    can read the work, and they belong to the repository rather than to
    its contents (#332).
    """
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)
    # Three-way, like the real thing: True there, False definitely not,
    # None cannot tell. `False` for unreachable would be the very
    # conflation this fixes.
    monkeypatch.setattr(
        "prodockit.cli.project_on_host", lambda context: exists if reachable else None
    )
    monkeypatch.setattr("prodockit.cli.own_project_exists", lambda context: exists)
    monkeypatch.setattr("prodockit.cli.own_project_has_content", lambda context: has_content)
    return cli_bootstrap(
        "--configure",
        input=f"2\nAda\na@b.c\nbuckwem\nbuckwem\nreport-windows-v1\n\n{answer}\n",
    )


def test_all_three_paths_are_named_in_the_question(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Including the template. It is what happens when nothing else is
    chosen, and a reader who cannot see it among the options has to infer
    it from the absence of anything else (#332)."""
    result = _configured(cli_bootstrap, monkeypatch, answer="1")
    # Compared with the line breaks flattened: the text is wrapped to the
    # terminal now, so where a phrase happens to break depends on how long
    # the project name is, and asserting on raw output would tie these to
    # one particular name.
    said = " ".join(result.output.split())

    assert "already exists on github.com and has content in it" in said
    assert "leave the existing git records" in said
    assert "delete the existing git records" in said
    assert "start from the template" in said


def test_keeping_the_history_is_recorded(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configured(cli_bootstrap, monkeypatch, answer="1")
    config = load(tmp_path / "b.toml")

    assert config.source_url == "buckwem/report-windows-v1", "qualified, as a clone needs"
    assert config.history == "keep"


def test_starting_again_still_clones_the_repository(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Somebody starting again still wants the contents that are already
    there - which is what "existing project or template" got wrong."""
    _configured(cli_bootstrap, monkeypatch, answer="2")
    config = load(tmp_path / "b.toml")

    assert config.source_url == "buckwem/report-windows-v1"
    assert config.history == "reset"


def test_choosing_the_template_records_neither(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configured(cli_bootstrap, monkeypatch, answer="3")
    config = load(tmp_path / "b.toml")

    assert config.source_url == ""
    assert config.history == ""


def test_the_question_has_no_default(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One answer deletes commits that cannot be recovered, and none of
    them is safe enough to be taken by pressing Enter."""
    result = _configured(cli_bootstrap, monkeypatch, answer="\n2")

    assert "Select 1, 2 or 3" in result.output
    assert result.output.count("Select 1, 2 or 3") > 1, "a blank answer asks again"


def test_an_empty_repository_gets_the_template_and_keeps_its_permissions(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cloning an empty repository would leave no zensical.toml, no
    requirements.txt and no tools/ - every later stage would fail on the
    absence. So the template supplies the contents.

    The permissions an issued repository carries are not lost by that:
    they belong to the repository on the host, and the remote stage points
    `origin` at it either way. Said out loud, because "the template will
    be used" alone reads as though the issued repository were being
    ignored (#332).
    """
    result = _configured(cli_bootstrap, monkeypatch, answer="", exists=True, has_content=False)

    assert "is empty on github.com" in result.output
    assert "keeps" in result.output and "permissions" in result.output
    assert "Select 1, 2 or 3" not in result.output, "nothing to decide between"
    assert load(tmp_path / "b.toml").source_url == ""


def test_a_repository_that_is_not_there_says_so_differently(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Does not exist yet" and "is empty" are different states, and a
    reader checking whether they created the thing needs to be told
    which."""
    result = _configured(cli_bootstrap, monkeypatch, answer="", exists=False, has_content=False)

    assert "does not exist yet on github.com" in result.output
    assert load(tmp_path / "b.toml").source_url == ""


def test_a_recorded_decision_means_no_prompt_during_the_run(tmp_path: Path) -> None:
    """The point of moving it. Once `source_url` is set the clone stage
    has nothing to ask, so the run has one less thing to interrupt for."""
    machine = _ready_machine(tmp_path)
    machine["git ls-remote"] = CommandResult(0, "abc123\trefs/heads/main\n")
    machine["ls-tree"] = CommandResult(0, PROJECT_TREE)
    plan = next(s for s in STAGES if s.id == "clone").plan(
        _context(
            tmp_path,
            host="github.com",
            namespace="buckwem",
            project_name="report-windows-v1",
            source_url="report-windows-v1",
            runner=FakeRunner(machine),
        )
    )

    assert not plan.instructions, "the decision was already made"
    assert "report-windows-v1.git" in " ".join(plan.commands[0])


def test_the_question_wraps_whatever_the_project_is_called(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It was written with the line breaks typed in, which only line up
    for one length of name - a longer one overflowed the first line and
    left the rest short."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)
    monkeypatch.setattr("prodockit.cli.own_project_exists", lambda context: True)
    monkeypatch.setattr("prodockit.cli.own_project_has_content", lambda context: True)
    long_name = "a-considerably-longer-project-name-for-testing-wrapping"

    result = cli_bootstrap(
        "--configure",
        input=f"2\nAda\na@b.c\nbuckwem\nbuckwem\n{long_name}\n\n1\n",
    )
    lines = [line for line in result.output.splitlines() if line.startswith("  ")]

    assert lines, "the question printed"
    assert max(len(line) for line in lines) <= 79, "nothing runs past the width"
    assert long_name in result.output, "and the name is not broken across lines"


def test_the_questions_say_how_many_there_are(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eight unnumbered questions read as an open-ended interrogation."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    monkeypatch.setattr("prodockit.cli.connection_problem", lambda value: None)
    monkeypatch.setattr("prodockit.cli.own_project_exists", lambda context: False)
    monkeypatch.setattr("prodockit.cli.own_project_has_content", lambda context: False)

    result = cli_bootstrap("--configure", input="2\nAda\na@b.c\nbuckwem\nbuckwem\nreport\n\n\n")

    assert "1/8 The git host" in result.output
    assert "6/8 Your project name" in result.output


def test_the_project_is_committed_and_pushed(tmp_path: Path) -> None:
    """Everything before this left a working project on one machine and
    an empty repository on the host. The push is what makes it real -
    it builds the site, and it is what the next machine clones (#339)."""
    machine = _ready_machine(tmp_path)
    machine["status --porcelain"] = CommandResult(0, " M docs/index.md\n")
    plan = next(s for s in STAGES if s.id == "first-push").plan(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    assert [c[-2:] if c[0].endswith("zensical") else c[:2] for c in plan.commands] == [
        ["build", "--clean"],
        ["git", "add"],
        ["git", "commit"],
        ["git", "push"],
    ]
    assert plan.commands[-1] == ["git", "push", "-u", "origin", "main"]
    assert plan.confirm.endswith("?")


def test_uncommitted_work_is_what_makes_it_outstanding(tmp_path: Path) -> None:
    machine = _ready_machine(tmp_path)
    machine["status --porcelain"] = CommandResult(0, " M zensical.toml\n")
    result = next(s for s in STAGES if s.id == "first-push").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    assert result.status is Status.MISSING
    assert "never been committed" in result.detail


def test_an_empty_remote_is_reported_even_with_a_clean_tree(tmp_path: Path) -> None:
    """A reset history leaves a clean tree and nothing on the host - the
    state that had a reader publishing by hand from VS Code."""
    machine = _ready_machine(tmp_path)
    machine["ls-remote origin HEAD"] = CommandResult(0, "")
    result = next(s for s in STAGES if s.id == "first-push").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    assert result.status is Status.MISSING
    assert "still empty" in result.detail


def test_pushing_waits_for_a_clone_and_a_remote(tmp_path: Path) -> None:
    """Committing into a directory that is not a repository, or pushing
    to a remote that was never set, cannot be a plan worth running."""
    save(tmp_path / "b.toml", _config())
    no_clone = next(s for s in STAGES if s.id == "first-push").check(_context(tmp_path))
    assert no_clone.status is Status.BLOCKED
    assert "no clone yet" in no_clone.detail

    machine = _ready_machine(tmp_path)
    machine["remote get-url origin"] = CommandResult(128, stderr="No such remote")
    no_origin = next(s for s in STAGES if s.id == "first-push").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )
    assert no_origin.status is Status.BLOCKED
    assert "no origin yet" in no_origin.detail


def test_the_push_comes_before_the_site_is_checked() -> None:
    """The push is what builds the site, so checking the site first would
    report a fault that the very next stage fixes."""
    ids = [s.id for s in STAGES]
    assert ids.index("first-push") < ids.index("site")
    assert ids.index("first-push") > ids.index("remote"), "there must be an origin to push to"


def test_pages_is_its_own_stage_right_after_the_project(tmp_path: Path) -> None:
    """It was a trailing item on stage 9's list and was missed twice, at
    a cost of a red first build whose error names the site rather than
    the setting (#341)."""
    ids = [s.id for s in STAGES]

    assert ids.index("pages") == ids.index("own-project") + 1, "still in the browser"
    assert ids.index("pages") < ids.index("first-push"), "before the push it would break"


def test_a_host_it_cannot_reach_is_not_called_missing(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reported from a fresh machine. There is no SSH key until stage 3,
    so `git ls-remote` fails on authentication - and reading that as "the
    repository does not exist" told a reader their project was missing
    when it was sitting on the host in front of them (#344)."""
    result = _configured(
        cli_bootstrap, monkeypatch, answer="", exists=True, has_content=True, reachable=False
    )

    assert "Could not check whether" in result.output
    assert "cannot reach it yet" in result.output
    assert "does not exist yet" not in result.output, "never claim that without looking"
    assert "Select 1, 2 or 3" not in result.output, "nothing to choose between blind"


def test_only_the_host_saying_so_counts_as_absent(tmp_path: Path) -> None:
    """A refused key, an unreachable network and a name that will not
    resolve are all failures, and none of them is evidence about whether
    the repository exists."""
    from prodockit.bootstrap import project_on_host

    for stderr, expected in (
        ("ERROR: Repository not found.", False),
        ("git@github.com: Permission denied (publickey).", None),
        ("ssh: Could not resolve hostname github.com", None),
        ("Connection closed by 131.227.81.118 port 22", None),
    ):
        machine = _ready_machine(tmp_path)
        machine["git ls-remote"] = CommandResult(128, stderr=stderr)
        answer = project_on_host(_context(tmp_path, host="github.com", runner=FakeRunner(machine)))
        assert answer is expected, stderr


def test_the_decision_stage_sits_between_the_key_and_the_clone(tmp_path: Path) -> None:
    """After the SSH stages because that is the first point the question
    can be *answered* - `--configure` runs before any key exists, so it
    can only say it could not look. Before the clone because that is the
    last point the answer still matters (#348)."""
    ids = [s.id for s in STAGES]

    assert ids.index("clone-source") > ids.index("ssh-upload")
    assert ids.index("clone-source") < ids.index("clone")


def test_nothing_to_decide_is_not_a_question(tmp_path: Path) -> None:
    """A reader whose project does not exist, or exists and is empty,
    gets the template - the only workable answer - and is not asked to
    choose between one thing."""
    result = next(s for s in STAGES if s.id == "clone-source").check(
        _context(tmp_path, runner=FakeRunner(_before_the_clone(_ready_machine(tmp_path))))
    )

    assert result.status is Status.OK
    assert "template" in result.detail


def test_a_project_with_work_in_it_is_put_to_the_reader(tmp_path: Path) -> None:
    machine = _before_the_clone(_ready_machine(tmp_path))
    machine["git ls-remote"] = CommandResult(0, "abc123\trefs/heads/main\n")
    machine["ls-tree"] = CommandResult(0, PROJECT_TREE)
    stage = next(s for s in STAGES if s.id == "clone-source")
    context = _context(
        tmp_path,
        host="github.com",
        namespace="buckwem",
        project_name="report-linux-v4",
        runner=FakeRunner(machine),
    )

    assert stage.check(context).status is Status.MISSING
    plan = stage.plan(context)
    assert len(plan.choices) == 3, "three paths, not three yes/no questions"
    assert plan.confirm == "Select 1, 2 or 3"
    assert "delete the existing git records" in plan.choices[1]


def test_an_answer_already_recorded_is_not_asked_again(tmp_path: Path) -> None:
    machine = _before_the_clone(_ready_machine(tmp_path))
    machine["git ls-remote"] = CommandResult(0, "abc123\trefs/heads/main\n")
    machine["ls-tree"] = CommandResult(0, PROJECT_TREE)
    result = next(s for s in STAGES if s.id == "clone-source").check(
        _context(tmp_path, source_url="buckwem/report-linux-v4", runner=FakeRunner(machine))
    )

    assert result.status is Status.OK
    assert "buckwem/report-linux-v4" in result.detail


def test_the_choice_is_written_down(tmp_path: Path) -> None:
    """So a rerun reads the answer rather than asking again - which is
    the whole reason this is a stage and not a prompt."""
    from prodockit.cli import _record_clone_source

    for picked, source, history in (
        ("1", "buckwem/report", "keep"),
        ("2", "buckwem/report", "reset"),
        ("3", "", ""),
    ):
        config = _config(namespace="buckwem", project_name="report")
        _record_clone_source(config, picked, None)
        assert config.source_url == source, picked
        assert config.history == history, picked


def test_no_stage_asks_the_machine_to_find_prodockit_again(tmp_path: Path) -> None:
    """A Windows setup stopped at stage 12 (prodockit-extensions#371).

        Commands finished, checking the result...
        failed: prodockit: not found
        Stopping - later stages depend on this one.

    On a machine where prodockit was installed and running the very
    bootstrap that said so. A virtual environment's scripts are reachable
    when it launches one; they are not necessarily on the `PATH` that a
    child process inherits, and bootstrap had asked the machine to go and
    find prodockit a second time.

    Every prodockit command a stage runs goes through the interpreter
    already running it. That also settles *which* prodockit: the one
    doing the work, never a different install earlier on PATH.
    """
    machine = _ready_machine(tmp_path)
    runner = FakeRunner(machine)
    context = _context(tmp_path, runner=runner)
    plans = [
        stage.plan(context)
        for stage in STAGES
        if stage.plan is not None and stage.id in {"remote", "mathjax"}
    ]
    commands = [command for plan in plans for command in plan.commands]
    commands += runner.calls

    with_prodockit = [c for c in commands if "prodockit" in c or "sync-repo" in c]
    assert with_prodockit, "nothing collected - the test would pass on any code"
    named_bare = [c for c in commands if c and c[0] in {"prodockit", "pdk"}]
    assert not named_bare, f"PATH cannot be trusted to find these: {named_bare}"
    for command in commands:
        if "prodockit" in command:
            assert command[:3] == [sys.executable, "-m", "prodockit"], command


def test_the_module_entry_point_prodockit_calls_itself_through_exists() -> None:
    """`python -m prodockit` has to be real for #371's fix to work.

    The console scripts are generated by the installer; the module form
    is not, and nothing else in the codebase uses it - so it would break
    silently, and only on the machines the fix was written for.
    """
    finished = subprocess.run(
        [sys.executable, "-m", "prodockit", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert finished.returncode == 0, finished.stderr
    assert __version__ in finished.stdout


def test_a_finished_machine_is_not_asked_where_its_project_came_from(
    tmp_path: Path,
) -> None:
    """Reported after four clean runs (prodockit-extensions#368).

    Every stage done, `prodockit boot` run once more to confirm - and the
    stage put three choices to a reader whose project was already cloned,
    pushed and published. Answering could not have changed where the
    contents came from: they were on disk, with an origin naming them.

    A `MISS` on a finished setup is worse than useless to a student. It
    reads as a fault, in the one run whose whole purpose is to say there
    is none.
    """
    machine = _ready_machine(tmp_path)
    machine["git ls-remote"] = CommandResult(0, "abc123\trefs/heads/main\n")
    machine["ls-tree"] = CommandResult(0, PROJECT_TREE)
    runner = FakeRunner(machine)
    result = next(s for s in STAGES if s.id == "clone-source").check(
        _context(tmp_path, runner=runner)
    )

    assert result.status is Status.OK
    assert "report-al01234" in result.detail, "say where it did come from"
    assert not any("ls-remote" in " ".join(call) for call in runner.calls), (
        "a decision already settled should not cost a host connection"
    )


def test_each_stage_is_checked_when_the_loop_reaches_it(tmp_path: Path) -> None:
    """Earlier stages change the machine the later ones are about.

    Reported from a real run: "where the project comes from" was decided
    before there was an SSH key, found nothing on the host, and reported
    `ok` - so the question was skipped on the very run that had just made
    the host reachable (#351).

    Checked at the level the fault lives at: the up-front pass and a
    later check of the same stage must be able to disagree.
    """
    from prodockit.bootstrap import forget_contacts, plan_all

    machine = _before_the_clone(_ready_machine(tmp_path))
    seen: list[int] = []

    class Reachable(FakeRunner):
        """A host that becomes readable part-way through, as one does
        once the SSH stages have been applied."""

        def run(self, command, cwd=None, timeout=None, capture=True):  # type: ignore[no-untyped-def]
            joined = " ".join(command)
            if "ls-remote" in joined and "origin" not in joined:
                seen.append(1)
                if len(seen) > 1:
                    return CommandResult(0, "abc123\trefs/heads/main\n")
                return CommandResult(128, stderr="Permission denied (publickey).")
            if "ls-tree" in joined:
                return CommandResult(0, PROJECT_TREE)
            return super().run(command, cwd, timeout, capture)

    context = _context(
        tmp_path,
        host="github.com",
        namespace="buckwem",
        project_name="report-linux-v4",
        runner=Reachable(machine),
    )
    stage = next(s for s in STAGES if s.id == "clone-source")

    first = next(r for r in plan_all(context) if r.stage.id == "clone-source").result
    forget_contacts(context)
    later = stage.check(context)

    # Said with what was actually seen: this failed once in CI and
    # nowhere else, and "assert False" gave nothing to work from.
    context_note = f"ls-remote calls: {len(seen)}"
    assert first.status is Status.BLOCKED, (
        f"unreachable host, so the decision must wait; got "
        f"{first.status.value}: {first.detail!r} ({context_note})"
    )
    assert later.needs_work, (
        f"reachable now, so the question is live; got "
        f"{later.status.value}: {later.detail!r} ({context_note})"
    )
    assert "choose what to do with it" in later.detail, later.detail


def test_the_apply_loop_asks_again_rather_than_trusting_the_first_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fix for #351 lives in the loop, so it is pinned there.

    The stage-level test above proves the two checks *can* disagree; this
    one proves the loop notices. Without it the run reports `ok` from a
    pass taken before the SSH stages ran.
    """
    from contextlib import suppress

    from click.testing import CliRunner

    from prodockit.bootstrap import plan_all
    from prodockit.cli import _apply_outstanding

    machine = _before_the_clone(_ready_machine(tmp_path))
    seen: list[int] = []

    class Reachable(FakeRunner):
        def run(self, command, cwd=None, timeout=None, capture=True):  # type: ignore[no-untyped-def]
            joined = " ".join(command)
            if "ls-remote" in joined and "origin" not in joined:
                seen.append(1)
                if len(seen) > 1:
                    return CommandResult(0, "abc123\trefs/heads/main\n")
                return CommandResult(128, stderr="Permission denied (publickey).")
            if "ls-tree" in joined:
                return CommandResult(0, PROJECT_TREE)
            return super().run(command, cwd, timeout, capture)

    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)
    context = _context(
        tmp_path,
        host="github.com",
        namespace="buckwem",
        project_name="report-linux-v4",
        runner=Reachable(machine),
    )
    reports = plan_all(context)
    initial = next(r for r in reports if r.stage.id == "clone-source")
    assert initial.result.status is Status.BLOCKED
    assert initial.plan is None, "there is no safe clone plan before SSH works"

    runner = CliRunner()
    # Whatever the run does after the question is not this test's
    # business - it may exit or run out of answers, and either is fine.
    with runner.isolation(input="1\n" + "n\n" * 60) as (out, _err, _):
        with suppress(SystemExit, RuntimeError):
            _apply_outstanding(context, reports)
        printed = out.getvalue().decode()

    assert "Select 1, 2 or 3" in printed, "the question was put once the host answered"


def test_pages_is_read_without_a_token_where_that_is_possible(tmp_path: Path) -> None:
    """A public repository says so in its own API object, to any
    anonymous caller - no tool to install, nothing to sign in to (#357)."""
    for has_pages, expected in ((True, Status.OK), (False, Status.MISSING)):
        body = f'{{"name":"r","has_pages":{str(has_pages).lower()}}}'
        result = next(s for s in STAGES if s.id == "pages").check(
            _context(tmp_path, host="github.com", fetch=_answers(200, body))
        )
        assert result.status is expected, has_pages


def test_a_probe_that_did_not_run_is_not_an_answer(tmp_path: Path) -> None:
    """A question that was never put must not be reported as an answer.

    Originally `curl: not found` - curl arrived with the Pandoc stage,
    three stages below Pages, so on a machine part-way through a setup
    the probe was simply missing. What reached the reader was "cannot be
    seen from outside a private repository" for the Pages stage and "is
    not answering yet" for the site. Both name a cause nobody
    established.

    The probe asks a URL now rather than launching curl (#449), so the
    unreachable host is described through `fetch`. Setting a runner key
    would assert nothing: the stage stopped reading one, which is how
    this test went quiet without failing (#476).
    """
    context = _context(
        tmp_path,
        host="github.com",
        runner=FakeRunner(_ready_machine(tmp_path)),
        fetch=_unreachable,
    )

    pages = next(s for s in STAGES if s.id == "pages").check(context)
    site = next(s for s in STAGES if s.id == "site").check(context)

    for result in (pages, site):
        assert result.status is Status.MISSING
        assert "the probe did not run" in result.detail
        assert "private repository" not in result.detail
        assert "not answering yet" not in result.detail


def test_the_host_s_own_refusal_is_quoted(tmp_path: Path) -> None:
    """prodockit-extensions#439, reported from a real run.

        not there yet - nothing visible at git@gitlab.surrey.ac.uk:...
        Try again? [Y/n]:
        not there yet - nothing visible at git@gitlab.surrey.ac.uk:...

    Twice, identically, with nothing new either time - because the host
    had said something specific and it was thrown away. "Could not be
    found or you don't have permission" and "Permission denied
    (publickey)" need different things from the reader: check the group,
    ask for access, or fix the key.
    """
    stage = next(s for s in STAGES if s.id == "own-project")
    refusals = {
        "could not be found or you don't have permission to view it": (
            "remote: The project you were looking for could not be found or you "
            "don't have permission to view it.\nfatal: Could not read from remote "
            "repository."
        ),
        "Permission denied (publickey)": (
            "git@gitlab.surrey.ac.uk: Permission denied (publickey).\n"
            "fatal: Could not read from remote repository."
        ),
    }
    for expected, stderr in refusals.items():
        machine = _ready_machine(tmp_path) | {"git ls-remote": CommandResult(128, stderr=stderr)}
        result = stage.check(_context(tmp_path, runner=FakeRunner(machine)))

        assert result.status is Status.MISSING
        assert expected in result.detail, result.detail
        # Still not claiming to know which it is - that is #377's point.
        assert "nothing visible at" in result.detail
        # And not the wrapper lines, which say nothing to act on.
        assert "Could not read from remote repository" not in result.detail


def test_a_silent_refusal_says_only_what_is_known(tmp_path: Path) -> None:
    """A host that says nothing gets no words put in its mouth."""
    machine = _ready_machine(tmp_path) | {"git ls-remote": CommandResult(128)}
    result = next(s for s in STAGES if s.id == "own-project").check(
        _context(tmp_path, runner=FakeRunner(machine))
    )

    assert result.detail.endswith(".git"), result.detail
    assert "said:" not in result.detail


def test_being_unable_to_see_a_repository_is_not_permission_to_make_one(
    tmp_path: Path,
) -> None:
    """github.com says `Repository not found.` for a repository that is
    missing *and* for one your key cannot see.

    The stage cannot tell those apart, and the expensive mistake is only
    in one direction: an issued repository carries the permissions that
    decide who can read the work, and a second one will not have them
    (#332). So the report says what was seen, and the steps say to look
    before creating anything.
    """
    machine = _ready_machine(tmp_path)
    github_key = tmp_path / ".ssh" / "id_ed25519_github"
    github_key.write_text("private", encoding="utf-8")
    github_key.with_suffix(".pub").write_text("public", encoding="utf-8")
    machine["ssh"] = CommandResult(
        1,
        stderr="Hi ada! You've successfully authenticated, but GitHub does not provide shell access.",
    )
    machine["git ls-remote"] = CommandResult(128, stderr="ERROR: Repository not found.")
    stage = next(s for s in STAGES if s.id == "own-project")
    context = _context(tmp_path, host="github.com", runner=FakeRunner(machine))

    result = stage.check(context)
    assert result.status is Status.MISSING
    assert "nothing visible at" in result.detail
    assert "not reachable" not in result.detail, "the host did not say that"

    steps = stage.plan(context).instructions
    checking = next(i for i, s in enumerate(steps) if "already there" in s)
    creating = next(i for i, s in enumerate(steps) if "create a blank" in s.lower())
    assert checking < creating, "look before making a second one"
    assert any("do not create another" in s for s in steps)


def test_a_site_behind_a_login_is_published(tmp_path: Path) -> None:
    """A university instance publishes behind its own sign-in (#392).

    An anonymous probe is sent to a login page rather than refused, and
    "is not answering yet" of a site that is plainly up would leave every
    Surrey run one stage short of finished, for ever.
    """
    stage = next(s for s in STAGES if s.id == "site")
    for code in ("401", "403", "302"):
        result = stage.check(_context(tmp_path, fetch=_answers(int(code))))

        assert result.status is Status.OK, code
        assert "pages.surrey.ac.uk" in result.detail
        assert "login" in result.detail, "and says who can read it"

    # 404 is the server answering, and answering "no such page" - which
    # is a finding, unlike a probe that never ran. Said through `fetch`:
    # the runner key this used to set has not been read since #449, so
    # the assertion was passing on an unreachable host instead (#476).
    assert stage.check(_context(tmp_path, fetch=_answers(404))).needs_work


def test_a_private_repository_is_shown_the_steps_and_taken_on_trust(
    tmp_path: Path,
) -> None:
    """Reported from Ubuntu against GitHub (prodockit-extensions#374).

        11  ok    Pages switched on - cannot be seen from outside a
                  private repository

    Pages had never been switched on. A private repository answers 404 to
    everything anonymous, and "cannot be seen" was being printed as
    though it meant "is set up" - so the one stage on the one host that
    has to be done by hand was skipped in silence.

    It is a finding now, and the steps are shown. What it must not do is
    claim to have looked: `verifiable` is False, so the run stops asking
    a question this repository will never answer and leaves the proof to
    the site check.
    """
    # The API says 404 to an anonymous caller, and nothing is published
    # either - or the site would answer for it.
    not_found = '{"message":"Not Found","status":"404"}'
    probe = _answers_by_url(**{"api_github_com": (404, not_found), "github_io": (404, "")})
    result = next(s for s in STAGES if s.id == "pages").check(
        _context(tmp_path, host="github.com", fetch=probe)
    )

    assert result.status is Status.MISSING
    assert not result.verifiable, "404 is all it will ever say - do not ask again"
    assert "cannot be seen from outside a private repository" in result.detail
    assert "the site check at the end of the run proves it" in result.detail


def test_a_private_repository_that_has_published_says_so(tmp_path: Path) -> None:
    """The site is readable without a token even when its repository is not.

    Without this, a private project that had published carried a finding
    it could never clear - shown the browser steps on every run, for
    something already done.
    """
    not_found = '{"message":"Not Found","status":"404"}'
    probe = _answers_by_url(**{"api_github_com": (404, not_found), "github_io": (200, "")})
    result = next(s for s in STAGES if s.id == "pages").check(
        _context(tmp_path, host="github.com", fetch=probe)
    )

    assert result.status is Status.OK
    assert "Pages is enabled" in result.detail


def test_nothing_asks_for_a_command_line_tool_any_more(tmp_path: Path) -> None:
    """Installing a tool, authenticating it in a browser, from the right
    directory, on every machine - four ways to go wrong for a check the
    site stage already makes for free."""
    assert not any(s.id == "host-cli" for s in STAGES)
    for stage in STAGES:
        plan = stage.plan(_context(tmp_path, host="github.com"))
        script = " ".join(" ".join(c) for c in plan.commands)
        assert "gh auth" not in script and "glab auth" not in script, stage.id


def test_the_front_page_link_is_told_not_done(tmp_path: Path) -> None:
    """Setting it needs an authenticated API call, and asking a reader to
    install and sign into a command line for one field was four ways to
    go wrong for a link they can paste in ten seconds (#357)."""
    machine = _ready_machine(tmp_path)
    machine["curl -sS"] = CommandResult(0, "200")
    plan = next(s for s in STAGES if s.id == "site").plan(
        _context(tmp_path, host="github.com", runner=FakeRunner(machine))
    )
    said = " ".join(" ".join(plan.instructions).split())

    assert "About" in said and "GitHub Pages website" in said
    assert not plan.commands, "nothing to run for it"


def test_a_site_that_answers_is_finished(tmp_path: Path) -> None:
    """The published site is the whole test now - no token, no tool, and
    it works for a private repository because the site is public."""
    result = next(s for s in STAGES if s.id == "site").check(
        _context(tmp_path, host="github.com", fetch=_answers(200))
    )

    assert result.status is Status.OK
    assert "public" in result.detail


def test_ok_says_which_reason_it_is(tmp_path: Path) -> None:
    """ "ok" with nothing after it read the same whether the host had been
    searched and found empty or never reached at all - and that ambiguity
    is the fault chased through #344 and #351 (#356)."""
    machine = _before_the_clone(_ready_machine(tmp_path))
    machine["git ls-remote"] = CommandResult(128, stderr="ERROR: Repository not found.")
    absent = next(s for s in STAGES if s.id == "clone-source").check(
        _context(tmp_path, host="github.com", runner=FakeRunner(machine))
    )

    unreachable = dict(machine)
    unreachable["git ls-remote"] = CommandResult(255, stderr="Permission denied (publickey).")
    blind = next(s for s in STAGES if s.id == "clone-source").check(
        _context(tmp_path, host="github.com", runner=FakeRunner(unreachable))
    )

    assert absent.status is Status.OK and blind.status is Status.BLOCKED
    assert "nothing visible at" in absent.detail, (
        "not 'no repository found' - both hosts answer a private repository the "
        "key cannot see with the words they use for one that is absent (#377)"
    )
    assert "the template will be cloned" in absent.detail
    assert "could not yet ask" in blind.detail, "not the same sentence as having looked"
    assert absent.detail != blind.detail
    # Which address was asked about, in both. A reader whose project
    # plainly exists needs to see that a different one was probed - the
    # namespace is shared across hosts, so it travels between them (#377).
    probed = "git@github.com:comm058-2026/report-al01234.git"
    assert probed in absent.detail and probed in blind.detail


def test_applying_prints_why_a_stage_is_already_ok(
    cli_bootstrap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The apply loop printed the summary and threw the detail away, so a
    reader watching a run could not see what a green line meant."""
    monkeypatch.setattr("prodockit.cli._is_interactive", lambda: True)

    machine = _ready_machine(tmp_path)
    machine["code --list-extensions"] = CommandResult(0, "")  # one stage left to do
    result = cli_bootstrap("--apply", responses=machine, input="n\n" * 40)

    assert "ok    Git, installed and configured - " in result.output


def test_only_github_is_asked_to_switch_pages_on(tmp_path: Path) -> None:
    """GitLab configures its own Pages from the CI job, so printing
    GitHub's steps to a GitLab reader would be an instruction to do
    nothing - and the API those steps are checked against is GitHub's
    alone (#360)."""
    stage = next(s for s in STAGES if s.id == "pages")

    gitlab = stage.check(_context(tmp_path, runner=FakeRunner(_ready_machine(tmp_path))))
    assert gitlab.status is Status.OK
    assert "configures Pages from its CI job" in gitlab.detail

    machine = _ready_machine(tmp_path)
    machine["curl -sS"] = CommandResult(0, '{"has_pages":false}')
    github = stage.check(_context(tmp_path, host="github.com", runner=FakeRunner(machine)))
    assert github.status is Status.MISSING
    said = " ".join(stage.plan(_context(tmp_path, host="github.com")).instructions)
    assert "Build and deployment" in said


def _site_words(tmp_path: Path, host: str) -> str:
    """Everything stage 23 says, for one host."""
    return " ".join(
        next(s for s in STAGES if s.id == "site")
        .plan(_context(tmp_path, host=host, namespace="ns", project_name="p"))
        .instructions
    )


def test_no_reader_is_shown_another_hosts_interface(tmp_path: Path) -> None:
    """prodockit-extensions#444.

    Every instruction on this stage was a literal describing GitHub, so a
    GitLab reader was sent looking for a gear beside 'About', a
    'Use your GitHub Pages website' tick-box and a Settings > Pages, none
    of which exist there.

    Written against the names rather than the whole sentences: the
    wording will be edited, and what must not come back is one host's
    interface appearing in another's instructions.
    """
    github_only = ("GitHub Pages website", "beside 'About'", "GitHub Enterprise")
    gitlab_only = ("Build > Pipelines", "Deploy > Pages", "README.md")

    for host in ("gitlab.surrey.ac.uk", "gitlab.com"):
        said = _site_words(tmp_path, host)
        for phrase in github_only:
            assert phrase not in said, f"{host} was shown GitHub's {phrase!r}"

    said = _site_words(tmp_path, "github.com")
    for phrase in gitlab_only:
        assert phrase not in said, f"github.com was shown GitLab's {phrase!r}"


def test_the_site_is_not_called_public_where_it_is_not(tmp_path: Path) -> None:
    """The half of #444 that was worse than merely wrong.

    GitLab keeps a private project's site behind its own sign-in - an
    anonymous request to a published Surrey site answers 302 to GitLab's
    OAuth consent page, which is exactly what the check reads as
    "published, behind a login". Telling that reader the site "will be
    public" contradicts what the project stage told them about the same
    project, and both cannot be true.

    So this asserts the *claim*, not the phrasing: nowhere on a GitLab
    host may the stage promise a publicly readable site.
    """
    for host in ("gitlab.surrey.ac.uk", "gitlab.com"):
        said = _site_words(tmp_path, host)
        assert "site will be public" not in said, host
        assert "readable by anyone with the link" not in said, host

    surrey = _site_words(tmp_path, "gitlab.surrey.ac.uk")
    assert "university login" in surrey, "say who can actually read it"

    # And GitHub, where it *is* true, must go on saying so - the fix is
    # per-host wording, not the removal of a warning that matters.
    assert "site will be public" in _site_words(tmp_path, "github.com")


def test_every_host_says_something_about_its_own_site(tmp_path: Path) -> None:
    """A host declaring none of these would silently drop the guidance
    rather than show the wrong host's, which is the failure this fix
    could plausibly introduce."""
    from prodockit.bootstrap import HOSTS

    for key, host in HOSTS.items():
        if not host.pages_url:
            continue  # no address to publish at - the stage does not apply
        assert host.site_link_steps, key
        assert host.site_visibility_note, key
        assert host.site_missing_note, key


def test_pandoc_and_node_are_not_reported_missing_when_PATH_is_stale(
    tmp_path: Path,
) -> None:
    """prodockit-extensions#450.

    A `winget install` sets the machine's PATH; a process already
    running never receives it. So `pandoc --version` failed on the
    machine that had just installed pandoc, and the stage said "pandoc
    is not installed" about software that was there - while git and VS
    Code, in the same listing, reported themselves found by full path.

    Driven through the stage's own check rather than the resolver:
    a resolver nothing calls would pass a test written against the
    resolver, and that is precisely the bug - the helper existed for
    git and these two checks did not use one.
    """
    pandoc_exe = r"C:\Program Files\Pandoc\pandoc.exe"
    node_exe = r"C:\Program Files\nodejs\node.exe"
    installed = {Path(pandoc_exe), Path(node_exe)}

    machine = _ready_machine(tmp_path)
    # Bare names answer as they do on a machine whose PATH is stale:
    # not found. Only the full paths work.
    machine["pandoc --version"] = CommandResult(127, stderr="not found")
    machine["node --version"] = CommandResult(127, stderr="not found")
    machine[pandoc_exe] = CommandResult(0, "pandoc 3.10.1\n")
    machine[node_exe] = CommandResult(0, "v22.0.0\n")

    context = build_context(
        _config(project_name="p", namespace="ns"),
        runner=FakeRunner(machine),
        platform=WINDOWS,
        home=tmp_path,
        exists=lambda path: path in installed or path.exists(),
    )

    pandoc = next(s for s in STAGES if s.id == "pandoc").check(context)
    assert "not installed" not in pandoc.detail, pandoc.detail
    assert "3.10.1" in pandoc.detail, pandoc.detail


def test_a_program_on_PATH_is_used_by_its_bare_name(tmp_path: Path) -> None:
    """The resolver must not prefer a guessed location over the copy
    PATH already resolves - that would pin a machine to whichever
    install this list happened to name."""
    machine = _ready_machine(tmp_path)
    machine["pandoc"] = CommandResult(0, "pandoc 3.10.1\n")
    machine["node"] = CommandResult(0, "v22.0.0\n")
    from prodockit.bootstrap import stages as stage_module

    context = _context(tmp_path, platform=WINDOWS, runner=FakeRunner(machine))

    assert stage_module.pandoc_command(context) == "pandoc"
    assert stage_module.node_command(context) == "node"


def test_the_names_are_resolved_when_the_plan_runs_not_when_it_is_built(
    tmp_path: Path,
) -> None:
    """The pandoc and node stages install the program and then use it,
    in one plan. Resolved at build time the answer is always "not there
    yet" - which is #405, and the reason this table exists."""
    from prodockit.bootstrap import stages as stage_module

    for name in ("pandoc", "node", "npm"):
        assert name in stage_module._RESOLVE_BEFORE_RUNNING, name


def test_a_sync_check_that_could_not_run_is_not_called_a_difference(
    tmp_path: Path,
) -> None:
    """prodockit-extensions#451.

    `sync-repo --check` exits non-zero both for "there is a difference"
    and for "I could not look". Saying "the project config still needs
    syncing" to both named a cause nobody had established, and sent the
    reader to run something that would not have fixed it.

    The real one, from a Windows machine where PATH could not see git:

        Error: could not run git: [WinError 2] The system cannot find
        the file specified
    """
    stage = next(s for s in STAGES if s.id == "remote")
    wanted = "git@gitlab.surrey.ac.uk:ns/p.git"

    def machine_saying(check: CommandResult) -> FakeRunner:
        table = _ready_machine(tmp_path)
        table["remote get-url origin"] = CommandResult(0, f"{wanted}\n")
        table["prodockit sync-repo --check"] = check
        return FakeRunner(table)

    broke = stage.check(
        _context(
            tmp_path,
            namespace="ns",
            project_name="p",
            runner=machine_saying(
                CommandResult(1, stderr="Error: could not run git: [WinError 2] ...")
            ),
        )
    )
    assert "could not check" in broke.detail, broke.detail
    assert "could not run git" in broke.detail, "say what actually stopped it"
    assert "still needs syncing" not in broke.detail

    # A check that ran and found a real difference is unchanged.
    differs = stage.check(
        _context(
            tmp_path,
            namespace="ns",
            project_name="p",
            runner=machine_saying(CommandResult(1, "repo_url differs\n")),
        )
    )
    assert "still needs syncing" in differs.detail, differs.detail


def _pandoc_saying(tmp_path: Path, version: str, **kw) -> CheckResult:
    """The pandoc stage's verdict on a machine running `version`."""
    machine = _ready_machine(tmp_path)
    machine["pandoc --version"] = CommandResult(0, f"pandoc {version}\n")
    return next(s for s in STAGES if s.id == "pandoc").check(
        _context(tmp_path, runner=FakeRunner(machine), **kw)
    )


def test_a_pandoc_that_differs_from_the_pin_is_named(tmp_path: Path) -> None:
    """prodockit-extensions#454.

    Pandoc decides how the PDF renders - #207 was code blocks coming out
    as justified prose on an older major, and limitations.md records
    3.1.3 accepting markup that 3.10 does not. So a student writing on
    one pandoc while CI publishes on another gets a PDF they never
    checked, and nothing says so: both builds succeed.
    """
    exact = _pandoc_saying(tmp_path, PANDOC_VERSION)
    assert exact.status is Status.OK
    assert "the builds pin" not in exact.detail, "nothing to say when it matches"

    differs = _pandoc_saying(tmp_path, "3.10.2")
    assert "3.10.2" in differs.detail
    assert f"the builds pin {PANDOC_VERSION}" in differs.detail, differs.detail


def test_a_pandoc_that_differs_is_told_not_failed(tmp_path: Path) -> None:
    """The deviation from #454's own suggestion, and the reason for it.

    Homebrew cannot install an old pandoc, so a failing status would be
    one no macOS reader could ever clear - a stage stuck for good, which
    is precisely the failure this project has had to undo twice already
    (#443, #451). A note they can act on beats a red mark they cannot.

    A pandoc too old to render correctly is still a failure: that one is
    fixable, and #207 is what happens when it is ignored.
    """
    assert _pandoc_saying(tmp_path, "3.10.2").status is Status.OK
    assert _pandoc_saying(tmp_path, "2.9.2").status is Status.WRONG


def test_windows_installs_the_pandoc_the_builds_pin(tmp_path: Path) -> None:
    """Ubuntu has always downloaded an exact release; Windows took
    whatever winget was serving, which is how a machine bootstrap had
    just set up came to run 3.10.2 against builds pinning 3.10.1."""
    plan = next(s for s in STAGES if s.id == "pandoc").plan(_context(tmp_path, platform=WINDOWS))
    pandoc = next(c for c in plan.commands if "JohnMacFarlane.Pandoc" in c)

    assert pandoc[pandoc.index("--version") + 1] == PANDOC_VERSION, pandoc


def test_only_pandoc_is_pinned_at_the_winget_line(tmp_path: Path) -> None:
    """MSYS2 and the rest are machine plumbing - pinning them would buy
    nothing and break whenever winget pruned an old build. The version
    argument exists for inputs that change this project's *output*."""
    plan = next(s for s in STAGES if s.id == "pandoc").plan(_context(tmp_path, platform=WINDOWS))
    msys2 = next(c for c in plan.commands if "MSYS2.MSYS2" in c)

    assert "--version" not in msys2, msys2


def _ubuntu_vscode_commands(tmp_path: Path) -> list[list[str]]:
    """What a clean Ubuntu run would be asked to approve for VS Code."""
    machine = _ready_machine(tmp_path)
    machine["dpkg --print-architecture"] = CommandResult(0, "amd64\n")
    machine["code"] = CommandResult(127, stderr="not found")
    return (
        next(s for s in STAGES if s.id == "vscode")
        .plan(_context(tmp_path, platform=UBUNTU, runner=FakeRunner(machine)))
        .commands
    )


def test_the_vs_code_package_is_answered_before_it_asks(tmp_path: Path) -> None:
    """prodockit-extensions#428.

    The VS Code `.deb` stops mid-install for a debconf question:

        Add Microsoft apt repository for Visual Studio Code?  <Yes> <No>

    `apt install -y` does not answer it - `-y` agrees to apt's own
    questions, not a package's debconf ones. Bootstrap captures its
    subprocesses, so the dialog was invisible: the run simply stopped,
    looking no different from slow work, until somebody thought to look.

    Preseeded rather than suppressed, and preseeded *before* the install,
    so the answer is part of what the reader approves.
    """
    commands = _ubuntu_vscode_commands(tmp_path)
    flat = [" ".join(c) for c in commands]

    preseed = next((i for i, c in enumerate(flat) if "debconf-set-selections" in c), None)
    install = next(i for i, c in enumerate(flat) if "/tmp/code.deb" in c and "install" in c)

    assert preseed is not None, f"nothing answers the debconf question: {flat}"
    assert "code/add-microsoft-repo boolean true" in " ".join(flat)
    assert preseed < install, "the answer has to be set before the package asks"
    # And not by piping into sudo: that puts `sudo` inside a shell, which
    # is the arrangement #244/#287 removed - a timestamp expiring there
    # prompts where nobody is watching, which is the same invisible wait
    # this fix exists to end.
    assert commands[preseed][0] == "sudo", commands[preseed]
    assert not any(c[0] == "bash" for c in commands), "no shell wrapper"


def _own_project_steps(tmp_path: Path, host: str, namespace: str) -> str:
    """Everything stage 11 tells a reader, as one string."""
    return "\n".join(
        next(s for s in STAGES if s.id == "own-project")
        .plan(_context(tmp_path, host=host, namespace=namespace, project_name="p"))
        .instructions
    )


def test_the_address_the_url_was_built_from_is_named(tmp_path: Path) -> None:
    """prodockit-extensions#441.

    A GitLab group renamed after creation keeps its old URL, so a group
    reading `assessment-commtest-2026` in the breadcrumb went on serving
    git at `comm058-2026`. Every derived URL missed, and the host said
    only "could not be found or you don't have permission to view it" -
    the same sentence it uses for a project that does not exist and for
    one you cannot see.

    Reported, not repaired: the real path cannot be read from here
    without credentials, and guessing a second address would replace a
    visible failure with a silent wrong answer. So the stage names the
    address it is using and says where the true one is shown.
    """
    said = _own_project_steps(tmp_path, "gitlab.surrey.ac.uk", "assessment-commtest-2026")

    assert "assessment-commtest-2026" in said, "name the address being used"
    assert "address bar" in said, "say where the real one is visible"
    assert "breadcrumb" in said, "and which one not to trust"
    # A worked example of the two disagreeing, not just an assertion that
    # they can - the difference is the thing that is hard to believe.
    assert "comm058-2026" in said


def test_the_namespace_note_is_the_hosts_own(tmp_path: Path) -> None:
    """GitHub has the same split under different names - an organisation's
    display name against its URL - so a GitLab reader must not be told
    about breadcrumbs on github.com, or the reverse."""
    gitlab = _own_project_steps(tmp_path, "gitlab.surrey.ac.uk", "ns")
    github = _own_project_steps(tmp_path, "github.com", "ns")

    assert "breadcrumb" in gitlab and "organisation" not in gitlab
    assert "organisation" in github and "breadcrumb" not in github
    assert "personal account has no such split" in github


def test_nothing_is_said_about_the_address_where_it_cannot_differ(
    tmp_path: Path,
) -> None:
    """A host that declares no note says nothing - the guidance is a
    per-host value, so a host added later starts silent rather than
    inheriting somebody else's interface."""
    from prodockit.bootstrap.model import Host

    quiet = Host(
        key="q",
        template_remote="git@q:t.git",
        key_suffix="q",
        hostname="q",
        ssh_success="ok",
        ssh_keys_url="https://q/keys",
        new_project_url="https://q/new",
    )
    assert quiet.namespace_note == ""


def test_the_metadata_url_comes_from_the_host(tmp_path: Path) -> None:
    """It was `api.github.com` written into the stage, so a gitlab.com
    project would have been asked about against GitHub's API."""
    from prodockit.bootstrap import HOSTS

    assert "api.github.com" in HOSTS["github"].repo_api
    assert HOSTS["surrey"].repo_api == "", "no anonymous equivalent"
    assert HOSTS["gitlab"].repo_api == ""


def test_gitlab_com_is_selectable(tmp_path: Path) -> None:
    """Flipped on in #361. Covered by tests rather than by a machine -
    Surrey's instance has been unreachable, so no GitLab path has been
    run end to end."""
    from prodockit.bootstrap import HOSTS, host_problem

    assert host_problem("gitlab.com") is None
    assert HOSTS["gitlab"].supported
    context = _context(tmp_path, host="gitlab.com")
    assert context.host.key == "gitlab"


def test_gitlab_com_gets_gitlabs_own_everything(tmp_path: Path) -> None:
    """The point of the record: no GitHub wording, URLs or API reach a
    GitLab reader."""
    context = _context(tmp_path, host="gitlab.com", namespace="ns", project_name="proj")
    host = context.host

    assert host.pages_url.format(namespace="ns", project="proj") == "https://ns.gitlab.io/proj/"
    assert host.repo_api == "", "GitLab has no anonymous metadata to read"
    assert not host.pages_setup_steps, "its CI job configures Pages"
    assert host.ssh_success == "Welcome to GitLab"
    assert host.remote_url("ns", "proj") == "git@gitlab.com:ns/proj.git"


def test_a_self_hosted_instance_is_still_refused() -> None:
    """`github.ibm.com` and `gitlab.example.edu` resolve to no record, so
    there is nothing to fill in the two things that cannot be guessed:
    where it publishes, and where its API lives."""
    from prodockit.bootstrap import host_problem

    for unknown in ("github.ibm.com", "gitlab.example.edu"):
        assert "self-hosted" in (host_problem(unknown) or ""), unknown


def test_the_site_is_built_clean_before_the_first_commit(tmp_path: Path) -> None:
    """`prodockit sync-repo` rewrites the brand icon in `zensical.toml`,
    and a build served from `.cache/` keeps showing the template's logo
    until something clears it - which readers were doing by running
    `zensical serve` and wondering why (#364)."""
    machine = _ready_machine(tmp_path)
    machine["status --porcelain"] = CommandResult(0, " M docs/index.md\n")
    plan = next(s for s in STAGES if s.id == "first-push").plan(
        _context(tmp_path, runner=FakeRunner(machine))
    )
    first = plan.commands[0]

    assert first[0].endswith("zensical"), "the project's own, not whichever is on PATH"
    assert first[1:] == ["build", "--clean"], "--clean is what drops the stale cache"
    assert plan.commands.index(first) < next(
        i for i, c in enumerate(plan.commands) if c[:2] == ["git", "commit"]
    ), "built before it is committed"


def test_the_build_uses_the_projects_own_zensical(tmp_path: Path) -> None:
    """Its version is pinned in the project's requirements.txt. A
    different one from PATH would build the site differently from CI."""
    machine = _ready_machine(tmp_path)
    machine["status --porcelain"] = CommandResult(0, " M x\n")
    # Compared as path parts, not as a string: a Windows path built on
    # POSIX renders with forward slashes, so `endswith("Scripts\\...")`
    # fails for a reason that has nothing to do with the code.
    for platform, parts in ((MACOS, ("bin", "zensical")), (WINDOWS, ("Scripts", "zensical.exe"))):
        plan = next(s for s in STAGES if s.id == "first-push").plan(
            _context(tmp_path, platform=platform, runner=FakeRunner(machine))
        )
        built = PurePath(plan.commands[0][0])
        assert built.parts[-2:] == parts, platform
        assert ".venv" in built.parts


def test_unassessed_work_is_never_asked_for_a_course_code() -> None:
    """#458: the course code was asked before "is this assessed", so an
    unassessed run answered it and the answer was then thrown away -
    neither `namespace_for` nor `project_name_for` runs on this path,
    because the namespace/project questions below are answered directly.
    Asking it only inside the assessed branch means an unassessed run is
    never asked it at all, and the running total drops from 7 to 6 to
    match."""
    from click.testing import CliRunner

    from prodockit.cli import _ask_surrey

    config = BootstrapConfig()
    runner = CliRunner()
    # login, "is this assessed?" (no), then Enter through both defaults.
    responses = "ab1234\nn\n\n\n"
    with runner.isolation(input=responses) as (out, _err, _):
        _ask_surrey(config)
        rendered = out.getvalue().decode()

    assert "course code" not in rendered.lower()
    assert "4/7 Is this an assessed assignment?" in rendered
    assert "5/6 The group or namespace" in rendered
    assert "6/6 The name of the repository" in rendered
    assert config.username == "ab1234"
    assert config.namespace == "ab1234", "offered as the default, and accepted"
    assert config.project_name == "report-ab1234"


def test_assessed_work_is_still_asked_for_a_course_code() -> None:
    """The other side of #458's fix: an assessed run still asks for the
    course code - just after "is this assessed" rather than before - and
    the total stays at 7 throughout, since this path is the longer one."""
    from click.testing import CliRunner

    from prodockit.cli import _ask_surrey

    config = BootstrapConfig()
    runner = CliRunner()
    # login, "is this assessed?" (yes), course code, stage, year.
    responses = "ab1234\ny\ncomm058\n1\n2026\n"
    with runner.isolation(input=responses) as (out, _err, _):
        _ask_surrey(config)
        rendered = out.getvalue().decode()

    assert "5/7 Your course code" in rendered
    assert "6/7 Which stage" in rendered
    assert "7/7 What year" in rendered
    assert "questions rather than" not in rendered, (
        "no count-drop notice on the path that matches the initial count"
    )
    assert config.namespace == "assessment-comm058-2026"
    assert config.project_name == "report-comm058-2026-ab1234"
