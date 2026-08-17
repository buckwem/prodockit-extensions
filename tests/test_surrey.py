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


def test_assessed_work_goes_to_a_group_per_course_and_attempt() -> None:
    """One place per course and attempt, so an examiner finds every
    submission together rather than in fifty personal namespaces."""
    first = surrey.Assessment.at_stage("1")
    sra = surrey.Assessment.at_stage("2")
    lsa = surrey.Assessment.at_stage("3")

    assert surrey.namespace_for("comm058", "ab1234", first) == "assessment-comm058"
    assert surrey.namespace_for("comm058", "ab1234", sra) == "assessment-comm058-sra"
    assert surrey.namespace_for("comm058", "ab1234", lsa) == "assessment-comm058-lsa"


def test_unassessed_work_stays_in_the_students_own_namespace() -> None:
    """Nobody else needs it, and a coursework group is for coursework."""
    assert (
        surrey.namespace_for("comm058", "ab1234", surrey.Assessment.not_assessed())
        == "ab1234"
    )


def test_a_stage_that_was_not_offered_is_refused() -> None:
    """Silently treating an unknown answer as "first attempt" would put a
    resit in the wrong group, which is not a thing to guess at."""
    for typed in ("4", "", "sra", "0"):
        with pytest.raises(ValueError, match="not one of the offered stages"):
            surrey.Assessment.at_stage(typed)


def test_the_project_is_named_for_its_course_and_its_owner() -> None:
    """Course first so a group of submissions sorts together; the ID last
    so a marker reading a list finds a name where they expect one."""
    assert surrey.project_name_for("comm058", "ab1234") == "report-comm058-ab1234"
    assert surrey.project_name_for("COMM058", "AB1234@surrey.ac.uk") == (
        "report-comm058-ab1234"
    ), "one course however it is capitalised"
