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
from collections.abc import Sequence
from pathlib import Path

import pytest

from prodockit.bootstrap import (
    HOSTS,
    STAGES,
    BootstrapConfig,
    BootstrapConfigError,
    CommandResult,
    Status,
    UnsupportedHostError,
    build_context,
    check_all,
    config_path,
    load,
    plan_all,
    save,
)
from prodockit.bootstrap.model import GITHUB_COM, MACOS, SURREY_GITLAB, UBUNTU, WINDOWS
from prodockit.bootstrap.stages import (
    DEFAULT_CSL_STYLE,
    MSYS2_BIN,
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
    (project / "harvard-cite-them-right.csl").write_text("<style/>", encoding="utf-8")
    (project / ".vscode").mkdir(exist_ok=True)
    (project / ".vscode" / "settings.json").write_text(
        '{"files.associations": {"*.md": "python-markdown"}}', encoding="utf-8"
    )
    save(tmp_path / "b.toml", _config())
    return {
        "code --list-extensions": CommandResult(0, "\n".join(VSCODE_EXTENSIONS)),
        "code": CommandResult(0),
        "git --version": CommandResult(0, "git version 2.43.0"),
        "git config --global user.name": CommandResult(0, "Ada\n"),
        "git config --global user.email": CommandResult(0, "a@b.c\n"),
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
        "import weasyprint": CommandResult(0),
        **AGENT_RESPONSES,
    }


def _write_ssh_config(tmp_path: Path, key: str = "~/.ssh/id_ed25519_gitlab") -> None:
    """A ~/.ssh/config that points Surrey's GitLab at the key.

    Needed by any test that expects the SSH stages to be satisfied:
    without the stanza ssh never offers the key, which is the whole of
    prodockit-extensions#239.
    """
    (tmp_path / ".ssh").mkdir(exist_ok=True)
    (tmp_path / ".ssh" / "config").write_text(
        f"Host gitlab.surrey.ac.uk\n    HostName gitlab.surrey.ac.uk\n"
        f"    User git\n    IdentityFile {key}\n",
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


def _context(
    tmp_path: Path,
    *,
    platform: str = MACOS,
    runner: FakeRunner | None = None,
    vscode_app: bool = False,
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
        exists=lambda path: (
            vscode_app if _looks_like_vscode_app(path) else path.exists()
        ),
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
    """gitlab.com and github.com exist as records so the shape is right,
    but phase 1 has tested neither - refusing beats half-working."""
    for key in ("gitlab", "github"):
        with pytest.raises(UnsupportedHostError) as exc_info:
            build_context(_config(host=key))
        assert "not yet supported" in str(exc_info.value)


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
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert config_path(tmp_path) == tmp_path / ".config" / "prodockit" / "bootstrap.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_path(tmp_path).parent.parent == tmp_path / "xdg"


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


def test_ssh_success_is_read_from_the_greeting_not_the_exit_code(tmp_path: Path) -> None:
    """`ssh -T` against a git host exits non-zero even when the key works -
    there is no shell to give you. Reading the exit code would report every
    correctly configured machine as broken.
    """
    runner = FakeRunner(
        {"ssh": CommandResult(1, stderr="Welcome to GitLab, @al01234!")}
    )
    context = _context(tmp_path, runner=runner)
    result = next(s for s in STAGES if s.id == "ssh-upload").check(context)
    assert result.status is Status.OK


def test_a_rejected_key_is_missing_not_merely_unconfirmed(tmp_path: Path) -> None:
    runner = FakeRunner({"ssh": CommandResult(255, stderr="Permission denied (publickey).")})
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


def _write_keypair(tmp_path: Path, public: str = "ssh-ed25519 AAAAC3Nz-PUBLIC al@surrey.ac.uk") -> None:
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


@pytest.fixture()
def cli_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Invokes the real command against a fake machine.

    `build_context` is replaced rather than the checks themselves, so the
    genuine stage code runs - just against a runner that answers from a
    table instead of the network. A real check would `ssh -T` Surrey's
    GitLab, which a test suite has no business doing.
    """
    from click.testing import CliRunner

    from prodockit.cli import main

    def _invoke(
        *args: str,
        responses: dict[str, CommandResult] | None = None,
        input: str | None = None,
        platform: str = MACOS,
    ):
        monkeypatch.setattr(
            "prodockit.cli.build_bootstrap_context",
            lambda config: build_context(
                config,
                runner=FakeRunner(responses or {}),
                platform=platform,
                home=tmp_path,
            ),
        )
        return CliRunner().invoke(
            main, ["bootstrap", "--config", str(tmp_path / "b.toml"), *args], input=input
        )

    return _invoke


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


def test_bootstrap_exits_zero_when_everything_is_set_up(
    cli_bootstrap, tmp_path: Path
) -> None:
    """Usable as a script check, matching `sync-repo --check`."""
    result = cli_bootstrap(responses=_ready_machine(tmp_path))

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
    and side-effect-free. An earlier version probed the host to decide
    which repository to clone, which put a network call inside it."""
    runner = FakeRunner()
    context = _context(tmp_path, runner=runner)
    next(s for s in STAGES if s.id == "clone").plan(context)
    assert runner.calls == []


def test_apply_reruns_the_check_afterwards(tmp_path: Path) -> None:
    """A command exiting zero says the installer ran, not that the thing
    works - every failure this project has had exited zero while producing
    something broken."""
    from prodockit.bootstrap import apply_stage

    runner = FakeRunner({"brew": CommandResult(0), "code": CommandResult(127)})
    context = _context(tmp_path, runner=runner)
    outcome = apply_stage(context, next(s for s in STAGES if s.id == "vscode"))
    assert outcome.failed is None          # the install command "succeeded"
    assert not outcome.ok                  # but the check still fails
    assert outcome.verified is not None


def test_apply_stops_at_the_first_failing_command(tmp_path: Path) -> None:
    """Later commands in a plan depend on earlier ones, so pressing on
    turns one clear failure into several confusing ones."""
    from prodockit.bootstrap import apply_stage

    runner = FakeRunner({"git": CommandResult(1, stderr="boom")})
    context = _context(tmp_path, runner=runner)
    outcome = apply_stage(context, next(s for s in STAGES if s.id == "remote"))
    assert outcome.failed is not None
    assert len(outcome.ran) == 1           # set-url failed; sync-repo never ran


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
    assert result.status is Status.WRONG
    assert "not on PATH" in result.detail

    plan = stage.plan(context)
    # The fix is the Command Palette action, not an install that would fail.
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
        "code": CommandResult(0, "\n".join(VSCODE_EXTENSIONS)),
        "git --version": CommandResult(0, "git version 2.43.0"),
        "git config --global user.name": CommandResult(0, "Ada\n"),
        "git config --global user.email": CommandResult(0, "a@b.c\n"),
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
    result = cli_bootstrap("--apply", responses=responses, input="y\nn\n")

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
    runner = FakeRunner()
    context = _context(tmp_path, runner=runner)
    next(s for s in STAGES if s.id == "ssh-upload").check(context)

    probe = next(call for call in runner.calls if call[0] == "ssh")
    assert "BatchMode=yes" in probe
    assert "ConnectTimeout=10" in probe


def test_an_unknown_host_is_reported_not_silently_trusted(tmp_path: Path) -> None:
    """Accepting a host key is a trust decision, and a tool that makes it
    silently on a reader's behalf has taken something from them they did
    not know they had. With `BatchMode` the probe fails instead - so the
    failure has to carry the way out, or it is just a dead end.
    """
    runner = FakeRunner(
        {"ssh": CommandResult(255, stderr="Host key verification failed.")}
    )
    result = next(s for s in STAGES if s.id == "ssh-upload").check(
        _context(tmp_path, runner=runner)
    )
    assert result.status is Status.WRONG
    assert "not a known host" in result.detail
    assert "ssh -T git@gitlab.surrey.ac.uk" in result.detail


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

    script = "import os; print(os.environ.get('GIT_TERMINAL_PROMPT'), os.environ.get('GIT_SSH_COMMAND'))"
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
    return next(s for s in STAGES if s.id == "identity").check(
        _context(tmp_path, runner=runner)
    )


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
    """"Wrong" without saying what it is leaves the reader to go and find
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
    result = next(s for s in STAGES if s.id == "pandoc").check(
        _context(tmp_path, runner=runner)
    )
    assert result.status is Status.WRONG
    assert "too old" in result.detail


def test_pandoc_current_version_is_ok(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            "pandoc": CommandResult(0, "pandoc 3.10.1\n"),
            "fc-list": CommandResult(0, "Inter\nJetBrains Mono\n"),
        }
    )
    result = next(s for s in STAGES if s.id == "pandoc").check(
        _context(tmp_path, runner=runner)
    )
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
    # dpkg says amd64 where VS Code's URL says x64; arm64 agrees with
    # itself, which is what an Apple-silicon VM reports.
    assert "dpkg --print-architecture" in flat
    assert "amd64) arch=x64" in flat


def test_ubuntu_vscode_installs_the_file_it_just_downloaded(tmp_path: Path) -> None:
    """The download path and the install path have to be the same one -
    the previous plan's did not, which is the whole of #233."""
    plan = next(s for s in STAGES if s.id == "vscode").plan(_context(tmp_path, platform=UBUNTU))
    download = next(c for c in plan.commands if "curl -fsSL" in " ".join(c))
    script = " ".join(download)

    assert "-o /tmp/code.deb" in script
    assert "install -y /tmp/code.deb" in script


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
    result = next(s for s in STAGES if s.id == "extensions").check(_context(tmp_path, runner=runner))

    assert result.status is Status.MISSING
    assert f"0 of {len(VSCODE_EXTENSIONS)} installed" in result.detail


def test_some_extensions_installed_is_still_wrong(tmp_path: Path) -> None:
    """A partly-set-up VS Code is present but not right, which is what
    WRONG means - and asking before touching an existing setup is the
    behaviour that case was given deliberately."""
    present = "\n".join(VSCODE_EXTENSIONS[:1])
    runner = FakeRunner({"code --list-extensions": CommandResult(0, present)})
    result = next(s for s in STAGES if s.id == "extensions").check(_context(tmp_path, runner=runner))

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


def test_the_lock_wait_covers_apt_inside_a_shell_command(tmp_path: Path) -> None:
    """Two plans wrap a download and an install in one `bash -c`, so the
    apt call is inside a string rather than at the front of a list - the
    easiest place for an option to be forgotten."""
    context = _context(tmp_path, platform=UBUNTU)
    for stage_id in ("vscode", "pandoc"):
        plan = next(s for s in STAGES if s.id == stage_id).plan(context)
        script = next(c for c in plan.commands if c[0] == "bash")[-1]
        assert "DPkg::Lock::Timeout" in script, stage_id


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
    """Windows runs the agent as a service, and enabling it needs an
    Administrator window - a different shell, not just a different
    command."""
    runner = FakeRunner(_agent(2, "Could not open a connection to your agent."))
    plan = next(s for s in STAGES if s.id == "ssh-agent").plan(
        _context(tmp_path, runner=runner, platform=WINDOWS)
    )
    joined = "\n".join(plan.instructions)

    assert "Start-Service ssh-agent" in joined
    assert "Administrator" in joined
    assert "ssh-agent -s" not in joined, "that is the Unix route"


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

    still_template = FakeRunner({"remote get-url origin": CommandResult(0, SURREY_GITLAB.template_remote)})
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


def test_the_history_reset_says_it_cannot_be_undone(tmp_path: Path) -> None:
    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".git").mkdir(parents=True)
    runner = FakeRunner({"remote get-url origin": CommandResult(0, SURREY_GITLAB.template_remote)})
    plan = next(s for s in STAGES if s.id == "fresh-history").plan(_context(tmp_path, runner=runner))
    joined = "\n".join(plan.instructions)
    flat = " ".join(" ".join(c) for c in plan.commands)

    assert "cannot be undone" in joined
    assert str(project) in joined, "say which directory, before deleting it"
    assert "git init -b main" in flat
    # From the guide: cloud-sync clients rewrite the executable bit, so a
    # synced project shows every file as modified without a byte changing.
    assert "core.fileMode false" in flat


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


def test_the_settings_plan_survives_a_file_that_is_not_json(tmp_path: Path) -> None:
    """VS Code tolerates comments and trailing commas in settings.json;
    `json.loads` does not. Failing here would leave the reader with a
    traceback over an editor preference."""
    import subprocess

    project = tmp_path / "GitLab" / "report-al01234"
    (project / ".vscode").mkdir(parents=True)
    settings = project / ".vscode" / "settings.json"
    settings.write_text("{ // a comment VS Code allows\n}", encoding="utf-8")
    save(tmp_path / "b.toml", _config())

    plan = next(s for s in STAGES if s.id == "vscode-settings").plan(_context(tmp_path))
    subprocess.run(plan.commands[0], check=True)

    assert json.loads(settings.read_text(encoding="utf-8"))["files.associations"]


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
PLAN_EFFECTS: dict[str, tuple[str, ...] | None] = {
    "vscode": ("the `code` command",),
    "git": ("git itself", "the global identity"),
    "ssh-key": ("the keypair",),
    "ssh-config": ("the Host stanza",),
    "ssh-agent": ("the loaded key",),
    "ssh-upload": None,
    "clone": ("the clone",),
    "fresh-history": ("a history of its own", "core.fileMode"),
    "own-project": None,
    "remote": ("origin", "the synced config"),
    "identity": ("the project's identity",),
    "pandoc": ("pandoc", "the PDF fonts"),
    "project-env": ("the venv", "its dependencies"),
    "node": ("node", "the toolchains", "chromium and the exports"),
    "extensions": ("the extensions",),
    "vscode-settings": ("the settings file",),
    "csl-style": ("the style file",),
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
        {"pandoc": CommandResult(0, "pandoc 3.10.1\n"), "fc-list": CommandResult(0, "DejaVu Sans\n")}
    )
    result = next(s for s in STAGES if s.id == "pandoc").check(_context(tmp_path, runner=runner))

    assert result.needs_work
    assert "Inter" in result.detail and "JetBrains Mono" in result.detail


def test_a_machine_that_cannot_be_asked_about_fonts_is_not_accused(tmp_path: Path) -> None:
    """"I could not tell" must not read as "they are missing". A false
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
    plan = next(s for s in STAGES if s.id == "pandoc").plan(_context(tmp_path, platform=WINDOWS))
    flat = " ".join(" ".join(c) for c in plan.commands)

    assert "MSYS2.MSYS2" in flat
    assert "mingw-w64-x86_64-pango" in flat
    assert "--noconfirm" in flat, "pacman asks otherwise"
    assert "--needed" in flat, "a rerun should be a no-op, not a reinstall"
    assert "SetEnvironmentVariable" in flat and MSYS2_BIN in flat


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
        plan = stage.plan(context)
        assert plan.commands or plan.instructions or plan.follow_up, (
            f"{stage.id} has no Windows plan at all"
        )
