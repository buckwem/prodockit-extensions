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
from datetime import date

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


#: A module year, sanity-bounded. Not a guess at what is reasonable so
#: much as a guard against a typed month or a two-digit year becoming a
#: namespace nobody can find.
_EARLIEST_YEAR, _LATEST_YEAR = 2000, 2100


def default_year(today: date | None = None) -> str:
    """The year to offer, which is this one.

    Taken as an argument rather than read from the clock inside a check,
    so a test can say what day it is.
    """
    return str((today or date.today()).year)


def module_year(typed: str) -> str:
    """A four-figure year, or "" when that is not what was typed.

    The empty string is the caller's cue to ask again. Guessing at `26`
    or `Jan 2026` would put the work in a group nobody can find, and the
    student would not know until the push failed.
    """
    year = typed.strip()
    if not (year.isdigit() and len(year) == 4):
        return ""
    return year if _EARLIEST_YEAR <= int(year) <= _LATEST_YEAR else ""


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


def namespace_for(course: str, login: str, assessment: Assessment, year: str = "") -> str:
    """The group or user the repository lives under.

    Assessed work goes to a group per course, *year* and attempt, so an
    examiner finds one cohort's submissions in one place and last year's
    are somewhere else. Unassessed work goes to the student's own
    namespace, where nobody else needs it and no year applies.

    The year is the one the module *starts* in - a semester 2 module
    belongs to the year after the Christmas break, and a resit belongs to
    the year the work was set rather than the year it is being marked.
    """
    if not assessment.assessed:
        return login_id(login)
    parts = ["assessment", course_code(course)]
    if year.strip():
        parts.append(year.strip())
    return "-".join(parts) + assessment.stage_suffix


def project_name_for(course: str, login: str, year: str = "") -> str:
    """`report-comm058-2026-ab1234` - course, cohort, and whose it is.

    In that order for the same reason the namespace is: the course first
    so a listing groups by module, the year next so one cohort sorts
    together within it, and the ID last so a marker reading down a column
    finds a name where they expect one.

    The name carries the year even for unassessed work, where the
    namespace does not. A student keeps their own repositories side by
    side in one namespace, and two years of the same module would
    otherwise be two repositories with one name between them.
    """
    parts = ["report", course_code(course)]
    if year.strip():
        parts.append(year.strip())
    return "-".join([*parts, login_id(login)])
