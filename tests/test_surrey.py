# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The Surrey configure path (prodockit-extensions#420).

What a student's email, GitLab username, group and repository name follow
from - and, just as important, that nothing here reaches any other host.
"""

from __future__ import annotations

import pytest

from prodockit.bootstrap import surrey


def test_only_surreys_own_instance_takes_this_path() -> None:
    """These rules are facts about one institution, not about GitLab.

    Applying them to gitlab.com would invent a namespace nobody has.
    """
    assert surrey.applies_to("gitlab.surrey.ac.uk")
    assert surrey.applies_to("  GitLab.Surrey.AC.UK  "), "typed as it is spoken"
    for other in ("github.com", "gitlab.com", "gitlab.example.edu", ""):
        assert not surrey.applies_to(other), other


def test_a_login_id_is_taken_however_it_is_typed() -> None:
    """A reader told to enter `ab1234` will sometimes enter what they
    actually log in with, which is the whole address."""
    assert surrey.login_id("ab1234") == "ab1234"
    assert surrey.login_id("ab1234@surrey.ac.uk") == "ab1234"
    assert surrey.login_id("  AB1234  ") == "ab1234"


def test_the_email_follows_the_login_id() -> None:
    assert surrey.email_for("ab1234") == "ab1234@surrey.ac.uk"
    assert surrey.email_for("ab1234@surrey.ac.uk") == "ab1234@surrey.ac.uk", (
        "entering the address twice over should not double the domain"
    )


def test_assessed_work_goes_to_a_group_per_course_year_and_attempt() -> None:
    """One place per cohort, so an examiner finds this year's submissions
    together and last year's somewhere else entirely."""
    first = surrey.Assessment.at_stage("1")
    sra = surrey.Assessment.at_stage("2")
    lsa = surrey.Assessment.at_stage("3")
    named = ("comm058", "ab1234")

    assert surrey.namespace_for(*named, first, "2026") == "assessment-comm058-2026"
    assert surrey.namespace_for(*named, sra, "2026") == "assessment-comm058-2026-sra"
    assert surrey.namespace_for(*named, lsa, "2026") == "assessment-comm058-2026-lsa"
    # The attempt comes last, after the year, so a group sorts by cohort.
    assert surrey.namespace_for(*named, sra, "2025") < surrey.namespace_for(*named, sra, "2026")


def test_a_year_has_to_look_like_one() -> None:
    """A namespace built from `26` or `Jan 2026` is one nobody can find,
    and the student would not know until the push failed."""
    assert surrey.module_year("2026") == "2026"
    assert surrey.module_year("  2026 ") == "2026"
    for wrong in ("26", "Jan 2026", "", "20266", "1999", "2101"):
        assert surrey.module_year(wrong) == "", wrong


def test_the_year_offered_is_the_current_one() -> None:
    """Taken as an argument rather than read from the clock inside a
    check, so a test can say what day it is."""
    from datetime import date

    assert surrey.default_year(date(2026, 8, 17)) == "2026"
    assert surrey.default_year(date(2027, 1, 3)) == "2027"


def test_unassessed_work_stays_in_the_students_own_namespace() -> None:
    """Nobody else needs it, and a coursework group is for coursework."""
    assert (
        surrey.namespace_for("comm058", "ab1234", surrey.Assessment.not_assessed(), "2026")
        == "ab1234"
    ), "no group and no year - nobody else needs it"


def test_a_stage_that_was_not_offered_is_refused() -> None:
    """Silently treating an unknown answer as "first attempt" would put a
    resit in the wrong group, which is not a thing to guess at."""
    for typed in ("4", "", "sra", "0"):
        with pytest.raises(ValueError, match="not one of the offered stages"):
            surrey.Assessment.at_stage(typed)


def test_the_project_is_named_for_its_course_cohort_and_owner() -> None:
    """Course first so a listing groups by module, the year next so one
    cohort sorts together within it, and the ID last so a marker reading
    down a column finds a name where they expect one."""
    assert (
        surrey.project_name_for("comm058", "ab1234", "2026")
        == "report-comm058-2026-ab1234"
    )
    assert surrey.project_name_for("COMM058", "AB1234@surrey.ac.uk", "2026") == (
        "report-comm058-2026-ab1234"
    ), "one course however it is capitalised"


def test_the_name_carries_the_year_where_the_namespace_does_not() -> None:
    """Unassessed work lives in the student's own namespace, so the year
    has nowhere else to go - and two years of one module would be two
    repositories with one name between them."""
    unassessed = surrey.Assessment.not_assessed()

    assert surrey.namespace_for("comm058", "ab1234", unassessed, "2026") == "ab1234"
    assert (
        surrey.project_name_for("comm058", "ab1234", "2026")
        == "report-comm058-2026-ab1234"
    )
