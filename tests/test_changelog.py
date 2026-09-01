# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Checks on the website-only release notes."""

from __future__ import annotations

import re
from pathlib import Path

from prodockit import __version__

CHANGELOG = Path(__file__).resolve().parents[1] / "docs" / "about" / "changelog.md"

#: `## 0.31.1 (2026-08-16)`, and the one heading with no version.
_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+) \(\d{4}-\d{2}-\d{2}\)$", flags=re.MULTILINE)
_UNRELEASED = re.compile(r"^## Unreleased$", flags=re.MULTILINE)


def test_release_notes_are_excluded_from_the_complete_pdf() -> None:
    introduction = CHANGELOG.read_text(encoding="utf-8").split("---", 2)[1]

    assert re.search(r"^pdf_include:\s*false$", introduction, flags=re.MULTILINE)


def test_there_is_at_most_one_unreleased_section() -> None:
    """Three of them reached `main` before anyone noticed.

    Each pull request adds its entry by inserting a new `## Unreleased`
    heading below the title, and a merge has no reason to object: the
    additions do not overlap, so both sides simply survive. The result
    reads as three separate sections, and the release that collapses them
    is done by hand under time pressure.

    Cheap to check, and the check is the only thing that has ever caught
    it.
    """
    headings = _UNRELEASED.findall(CHANGELOG.read_text(encoding="utf-8"))

    assert len(headings) <= 1, (
        f"{len(headings)} `## Unreleased` sections - add entries under the "
        "existing one rather than inserting another heading"
    )


def test_release_notes_explain_that_unreleased_can_be_absent() -> None:
    introduction = CHANGELOG.read_text(encoding="utf-8").split("\n## ", 1)[0]

    assert "Unreleased section when it is present" in " ".join(introduction.split())


def test_unreleased_comes_before_every_released_version() -> None:
    """Newest first, or a reader looking for what changed last reads
    something that shipped months ago."""
    text = CHANGELOG.read_text(encoding="utf-8")
    unreleased = _UNRELEASED.search(text)
    first_release = _RELEASE.search(text)

    assert first_release is not None, "there should be at least one released version"
    if unreleased is not None:
        assert unreleased.start() < first_release.start()


def test_released_entries_are_newest_first() -> None:
    """Keep the short user-facing entries in date order."""
    text = CHANGELOG.read_text(encoding="utf-8")
    dates = [
        tuple(int(part) for part in raw.split("-"))
        for raw in re.findall(
            r"^## \d+\.\d+\.\d+ \((\d{4}-\d{2}-\d{2})\)$", text, flags=re.MULTILINE
        )
    ]

    assert dates == sorted(dates, reverse=True), "an entry is out of order by date"


def test_package_version_matches_the_newest_release_notes() -> None:
    pyproject = (CHANGELOG.parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    metadata_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    newest_release = _RELEASE.search(CHANGELOG.read_text(encoding="utf-8"))

    assert metadata_version is not None
    assert newest_release is not None
    assert metadata_version.group(1) == __version__ == newest_release.group(1)
