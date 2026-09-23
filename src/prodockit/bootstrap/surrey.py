# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""What a University of Surrey setup can work out for itself.

The general configuration asks eight questions because it cannot know
anything about the host. Surrey's GitLab is not general: a student's
email and GitLab username follow from their login ID, and for *assessed*
work so do the group it belongs in and what the repository is called -
from the course code, the year the module starts, and which attempt it
is (prodockit-extensions#420).

Unassessed work derives neither. There is no cohort group for it to go
to and no attempt to record, so the group and the name are asked for,
offered as the reader's own (#437).

Asking for what can be derived is not neutral. Every free-text answer is
a chance to type a namespace that does not exist, and the reader finds
out several stages later, from a host that says only "not found".

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
#: ordinary case; the other two are resits, and each has a year subgroup
#: of its own on the host.
STAGES: tuple[tuple[str, str, str], ...] = (
    ("1", "First", ""),
    ("2", "SRA", "-SRA"),
    ("3", "LSA", "-LSA"),
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
    """The year in which the current academic year started.

    Taken as an argument rather than read from the clock inside a check,
    so a test can say what day it is.
    """
    current = today or date.today()
    return str(current.year if current.month >= 9 else current.year - 1)


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

    Assessed work belongs under CSEE/module/academic-year, with SRA or
    LSA appended to the year subgroup. Unassessed work stays in the
    student's own namespace.
    """
    if not assessment.assessed:
        return login_id(login)
    start = module_year(year)
    if not start:
        raise ValueError("assessed Surrey work needs a four-digit academic-year start")
    following = str((int(start) + 1) % 100).zfill(2)
    return f"CSEE/{course_code(course).upper()}/{start}-{following}{assessment.stage_suffix}"


def project_name_for(
    course: str, login: str, year: str = "", assessment: Assessment | None = None
) -> str:
    """Use `comm058-ab1234` for assessed work in its year subgroup.

    Keep the previous report/year naming for explicit unassessed work;
    that path does not have a year subgroup to distinguish repositories.
    """
    if assessment is not None and assessment.assessed:
        return f"{course_code(course)}-{login_id(login)}"
    parts = ["report", course_code(course)]
    if year.strip():
        parts.append(year.strip())
    parts.append(login_id(login))
    return "-".join(parts)
