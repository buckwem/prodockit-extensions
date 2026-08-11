# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Counting - and not repeating - the connections bootstrap makes.

Every SSH-related check logs in to the host: `ssh -T` twice and a
`git ls-remote` once, per pass. `plan_all` checks *and* plans, and the
`--apply` loop re-derives a plan and re-checks after every stage, so a
single run made dozens of logins within a few seconds.

A server that sees that stops answering. GitLab drops the connection
after accepting the key, which reads at the client as authentication
failing - so the tool blamed the reader's key for a refusal it had
provoked itself (prodockit-extensions#304).

The cheap half of the fix is here: ask once per pass and reuse the
answer. `ssh -T` cannot give a different answer between stage 6 and
stage 7 of the same `check_all()`, so asking twice buys nothing and
costs a login.

Nothing here waits, backs off, or retries. Those are worth adding only
once `HostContacts` has shown how many connections a real run actually
makes, which is what the counter is for.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from prodockit.bootstrap.model import CommandResult, Runner

__all__ = ["CountingRunner", "HostContacts", "contacts_host"]

#: The git subcommands that reach the network. Deliberately a list of
#: what *does* connect rather than what doesn't: `git config`,
#: `git remote get-url` and `git -C ... rev-parse` are all local, and a
#: rule that guessed from the presence of a URL would count them.
GIT_REMOTE_VERBS = frozenset(
    {"clone", "fetch", "ls-remote", "pull", "push"}
)


def contacts_host(command: Sequence[str]) -> bool:
    """Whether running this opens a connection to the host.

    Matched on the program name and subcommand rather than on the
    hostname appearing somewhere in the arguments: `git config --global
    user.email al01234@surrey.ac.uk` carries the host's name and connects
    to nothing.
    """
    if not command:
        return False
    # `ssh`, `/usr/bin/ssh` and `ssh.exe` are the same program. Windows
    # plans carry the full path often enough that matching the bare word
    # would miss them.
    name = Path(command[0]).name.lower().removesuffix(".exe")
    if name == "ssh":
        return True
    if name == "git":
        return any(word in GIT_REMOTE_VERBS for word in command[1:])
    return False


@dataclass
class HostContacts:
    """How many times a run has reached the host, and how many it saved.

    `made` is connections actually opened; `reused` is repeats answered
    from the first one. The pair is the measurement #304 asks for: tuning
    an interval or a backoff before knowing these numbers would be
    guesswork.
    """

    made: int = 0
    reused: int = 0
    answers: dict[tuple[str, ...], CommandResult] = field(default_factory=dict)

    @property
    def asked(self) -> int:
        """Connections a run *would* have made without the memo."""
        return self.made + self.reused

    def forget(self) -> None:
        """Drops the remembered answers, keeping the counts.

        Called whenever the machine may have changed underneath us -
        chiefly before `apply_stage` re-checks. That re-check is the only
        claim bootstrap makes that is worth anything, and answering it
        from a memo taken before the stage ran would turn it into a
        statement about the past.
        """
        self.answers.clear()


class CountingRunner:
    """Wraps a `Runner`, counting host contacts and reusing repeats.

    A decorator rather than something the stages know about, so every
    call site is covered by construction - a stage added later cannot
    forget to use it - and `FakeRunner` keeps working untouched.
    """

    def __init__(self, inner: Runner, contacts: HostContacts) -> None:
        self._inner = inner
        self._contacts = contacts

    def run(
        self,
        command: Sequence[str],
        cwd: str | None = None,
        timeout: float | None = None,
        capture: bool = True,
    ) -> CommandResult:
        if not contacts_host(command):
            return self._inner.run(command, cwd, timeout, capture)

        # `capture=False` means this is an *apply*, not a check - a
        # `git clone` or a `git push`. Those do something, so they are
        # neither served from the memo nor recorded in it; only the
        # read-only probes are worth remembering.
        key = (*command, cwd or "")
        if capture and key in self._contacts.answers:
            self._contacts.reused += 1
            return self._contacts.answers[key]

        result = self._inner.run(command, cwd, timeout, capture)
        self._contacts.made += 1
        if capture:
            self._contacts.answers[key] = result
        return result
