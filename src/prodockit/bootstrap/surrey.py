# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""What a University of Surrey setup can work out for itself.

The general configuration asks eight questions because it cannot know
anything about the host. Surrey's GitLab is not general: a student's
email, their GitLab username, the group their work belongs in and what
the repository is called all follow from two facts - their login ID and
their course code - plus whether the work is assessed
(prodockit-extensions#420).

Asking for what can be derived is not neutral. Every free-text answer is
a chance to type a namespace that does not exist, and the reader finds
out several stages later, from a host that says only "not found". Three
questions with known shapes replace five with none.

Nothing here is imposed on other hosts: `github.com` and `gitlab.com`
keep the general path, because for them these rules are simply untrue.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The hosts this applies to. A list rather than a constant because a
#: university runs more than one name at its own instance over time, and
#: the derivation is about the institution rather than the hostname.
SURREY_HOSTS = frozenset({"gitlab.surrey.ac.uk"})

#: What a Surrey login ID becomes.
EMAIL_DOMAIN = "surrey.ac.uk"

#: The assessment stages, in the order they are offered. The first is the
#: ordinary case; the other two are resits, and each has a group of its
#: own on the host.
STAGES: tuple[tuple[str, str, str], ...] = (
    ("1", "First", ""),
    ("2", "SRA", "-sra"),
    ("3", "LSA", "-lsa"),
)


def applies_to(host: str) -> bool:
    """Whether this host is one these rules are true of."""
    return host.strip().lower() in SURREY_HOSTS


def login_id(typed: str) -> str:
    """The six-character ID, however it was typed.

    A reader told to enter `ab1234` will sometimes enter
    `ab1234@surrey.ac.uk`, because that is what they type to log in.
    Taking the part before the `@` is kinder than refusing it, and the
    result is identical.
    """
    return typed.strip().split("@", 1)[0].strip().lower()


def email_for(login: str) -> str:
    """`ab1234` -> `ab1234@surrey.ac.uk`."""
    return f"{login_id(login)}@{EMAIL_DOMAIN}"


def course_code(typed: str) -> str:
    """The module code, lowercased - `COMM058` and `comm058` are one course."""
    return typed.strip().lower()


@dataclass(frozen=True)
class Assessment:
    """Whether the work is assessed, and at which attempt."""

    assessed: bool
    stage_suffix: str = ""

    @classmethod
    def not_assessed(cls) -> Assessment:
        return cls(assessed=False)

    @classmethod
    def at_stage(cls, choice: str) -> Assessment:
        """From `1`, `2` or `3` as offered at the prompt."""
        for number, _name, suffix in STAGES:
            if choice.strip() == number:
                return cls(assessed=True, stage_suffix=suffix)
        raise ValueError(f"not one of the offered stages: {choice!r}")


def namespace_for(course: str, login: str, assessment: Assessment) -> str:
    """The group or user the repository lives under.

    Assessed work goes to a group per course and attempt, so an examiner
    finds every submission in one place. Unassessed work goes to the
    student's own namespace, where nobody else needs it.
    """
    if not assessment.assessed:
        return login_id(login)
    return f"assessment-{course_code(course)}{assessment.stage_suffix}"


def project_name_for(course: str, login: str) -> str:
    """`report-comm058-ab1234` - the course and whose it is, in that order.

    The course first so a group of submissions sorts together, and the ID
    last so a marker reading a list finds a name where they expect one.
    """
    return f"report-{course_code(course)}-{login_id(login)}"
