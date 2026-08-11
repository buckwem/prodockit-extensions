# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Counting and reusing the connections bootstrap makes (#304)."""

from __future__ import annotations

import pytest

from prodockit.bootstrap import CommandResult, CountingRunner, HostContacts, contacts_host


class Recorder:
    """A runner that counts what it was actually asked to run."""

    def __init__(self, result: CommandResult | None = None) -> None:
        self.calls: list[list[str]] = []
        self.result = result or CommandResult(0, "out")

    def run(self, command, cwd=None, timeout=None, capture=True):  # type: ignore[no-untyped-def]
        self.calls.append(list(command))
        return self.result


SSH = ["ssh", "-T", "git@gitlab.surrey.ac.uk"]


@pytest.mark.parametrize(
    "command",
    [
        ["ssh", "-T", "git@gitlab.surrey.ac.uk"],
        ["/usr/bin/ssh", "-T", "git@gitlab.surrey.ac.uk"],
        ["ssh.exe", "-T", "git@gitlab.surrey.ac.uk"],
        ["git", "ls-remote", "git@gitlab.surrey.ac.uk:g/p.git"],
        ["git", "clone", "git@gitlab.surrey.ac.uk:g/p.git", "/tmp/p"],
        ["git", "push", "origin", "main"],
    ],
)
def test_these_reach_the_host(command: list[str]) -> None:
    assert contacts_host(command)


@pytest.mark.parametrize(
    "command",
    [
        ["git", "config", "--global", "user.email", "al01234@surrey.ac.uk"],
        ["git", "-C", "/p", "remote", "get-url", "origin"],
        ["ssh-add", "-l"],
        ["ssh-keygen", "-lf", "/home/a/.ssh/id_ed25519_gitlab.pub"],
        ["git", "--version"],
        [],
    ],
)
def test_these_do_not(command: list[str]) -> None:
    """`git config --global user.email al01234@surrey.ac.uk` carries the
    host's name and connects to nothing - so the rule matches on the
    subcommand, never on a hostname appearing in the arguments.

    `ssh-add` and `ssh-keygen` start with the same four letters as `ssh`
    and talk only to the local agent and disk.
    """
    assert not contacts_host(command)


def test_a_repeat_within_a_pass_does_not_reconnect() -> None:
    """Three stages ask the same `ssh -T`, seconds apart, and cannot get
    different answers - so asking three times buys nothing and costs the
    two logins that provoke the refusal."""
    inner = Recorder()
    contacts = HostContacts()
    runner = CountingRunner(inner, contacts)

    for _ in range(3):
        runner.run(SSH)

    assert inner.calls == [SSH], "connected once"
    assert contacts.made == 1
    assert contacts.reused == 2
    assert contacts.asked == 3, "what it would have cost without the memo"


def test_the_reused_answer_is_the_real_one() -> None:
    """A memo that returned something subtly different would be worse
    than no memo."""
    inner = Recorder(CommandResult(1, "out", "Welcome to GitLab, @al01234!"))
    runner = CountingRunner(inner, HostContacts())

    first = runner.run(SSH)
    second = runner.run(SSH)

    assert first == second
    assert "Welcome to GitLab" in second.stderr


def test_local_commands_are_neither_counted_nor_memoised() -> None:
    """Counting `git --version` would make the measurement meaningless,
    and memoising a local check would hide a change on disk."""
    inner = Recorder()
    contacts = HostContacts()
    runner = CountingRunner(inner, contacts)

    runner.run(["git", "--version"])
    runner.run(["git", "--version"])

    assert len(inner.calls) == 2, "asked every time"
    assert contacts.asked == 0


def test_applying_is_never_served_from_the_memo() -> None:
    """`capture=False` is an apply - a `git clone` or a `git push`. Those
    do something, and answering a second one from the first would skip
    the work entirely."""
    inner = Recorder()
    contacts = HostContacts()
    runner = CountingRunner(inner, contacts)
    clone = ["git", "clone", "git@gitlab.surrey.ac.uk:g/p.git", "/tmp/p"]

    runner.run(clone, capture=False)
    runner.run(clone, capture=False)

    assert len(inner.calls) == 2, "an apply always runs"
    assert contacts.made == 2
    assert contacts.reused == 0


def test_an_apply_is_not_remembered_for_a_later_check() -> None:
    """The clone's own result must not become the answer to a later
    question about the host."""
    inner = Recorder()
    contacts = HostContacts()
    runner = CountingRunner(inner, contacts)

    runner.run(SSH, capture=False)
    runner.run(SSH)

    assert len(inner.calls) == 2


def test_forgetting_drops_answers_but_keeps_the_count() -> None:
    """The count measures what the run cost the host, so it must survive
    the memo being cleared between passes."""
    inner = Recorder()
    contacts = HostContacts()
    runner = CountingRunner(inner, contacts)

    runner.run(SSH)
    contacts.forget()
    runner.run(SSH)

    assert len(inner.calls) == 2, "asked again after forgetting"
    assert contacts.made == 2
    assert contacts.reused == 0


def test_the_memo_distinguishes_working_directories() -> None:
    """The same command in two directories is two questions - `git
    ls-remote` in different clones can legitimately differ."""
    inner = Recorder()
    runner = CountingRunner(inner, HostContacts())
    command = ["git", "ls-remote", "git@gitlab.surrey.ac.uk:g/p.git"]

    runner.run(command, cwd="/a")
    runner.run(command, cwd="/b")

    assert len(inner.calls) == 2


def test_a_check_pass_on_a_finished_machine_costs_two_logins(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The measurement #304 asked for, on the real stage list.

    One `ssh -T` and one `git ls-remote`, both genuinely different
    questions - so there is nothing here for the memo to save, and the
    number is the honest floor for a pass.
    """
    from test_bootstrap import FakeRunner, _context, _ready_machine

    from prodockit.bootstrap import check_all

    context = _context(tmp_path, runner=FakeRunner(_ready_machine(tmp_path)))
    check_all(context)

    assert context.contacts.made == 2
    assert context.contacts.reused == 0, "two different questions"


def test_planning_a_broken_ssh_stage_reuses_the_probe(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Where the saving actually is. When the SSH stage needs work,
    `plan_all` asks `ssh -T` for the check and again to decide whether
    the plan needs the terminal - the same command, moments apart, on a
    machine nothing has touched in between.

    This is the case that matters, because a refused host is exactly when
    bootstrap is rerun most often.
    """
    from test_bootstrap import FakeRunner, _context, _ready_machine

    from prodockit.bootstrap import plan_all

    machine = _ready_machine(tmp_path)
    machine["ssh"] = CommandResult(255, stderr="Permission denied (publickey).")
    context = _context(tmp_path, runner=FakeRunner(machine))
    plan_all(context)

    probes = [c for c in context.contacts.answers if c[0] == "ssh"]
    assert len(probes) == 1, "one remembered answer, however often it was asked"
    assert context.contacts.reused >= 1, "the repeat cost no connection"


def test_verification_after_a_stage_never_reads_a_stale_answer(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`ApplyResult.verified` is the only claim bootstrap makes that is
    worth anything. Answering it from a memo taken before the stage ran
    would turn it into a statement about the past."""
    from test_bootstrap import FakeRunner, _context, _ready_machine

    from prodockit.bootstrap import apply_stage
    from prodockit.bootstrap.stages import STAGES

    runner = FakeRunner(_ready_machine(tmp_path))
    context = _context(tmp_path, runner=runner)
    stage = next(s for s in STAGES if s.id == "ssh-upload")

    context.runner.run(["ssh", "-T", "git@gitlab.surrey.ac.uk"])
    before = context.contacts.made
    apply_stage(context, stage)

    assert context.contacts.made > before, "the re-check connected for itself"
