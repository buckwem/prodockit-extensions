# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Opt-in tests that prove adoption does not visually alter existing sites."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from .harness import (
    RealSite,
    adopt,
    build,
    capture,
    chrome,
    clone,
    compare,
    load_sites,
    prepare,
    serve,
    site_root,
)

SITES = load_sites(Path(__file__).with_name("sites.toml"))
ENABLED = os.environ.get("PRODOCKIT_REAL_SITE_TESTS") == "1"


@pytest.mark.real_site
@pytest.mark.skipif(
    not ENABLED,
    reason="set PRODOCKIT_REAL_SITE_TESTS=1 to clone and compare public sites",
)
@pytest.mark.parametrize("site", SITES, ids=lambda site: site.name)
def test_adoption_builds_without_a_visible_change(site: RealSite, tmp_path: Path) -> None:
    executable = chrome()
    if executable is None:
        pytest.skip("Chrome or Chromium is required for real-site visual comparison")

    project = clone(site, tmp_path / site.name)
    before_profile = tmp_path / "chrome-profile-before"
    after_profile = tmp_path / "chrome-profile-after"
    environment = prepare(site, tmp_path / "python-packages", project)
    build(site, project, environment)
    with serve(site_root(site, project) / site.output) as base_url:
        before = capture(
            executable,
            base_url,
            site.pages,
            tmp_path / "before",
            label="before",
            profile=before_profile,
        )

        output = adopt(site, project)
        assert "Nothing has been committed or pushed" in output
        build(site, project, environment)
        after = capture(
            executable,
            base_url,
            site.pages,
            tmp_path / "after",
            label="after",
            profile=after_profile,
        )

    comparisons = compare(
        before,
        after,
        tmp_path / "difference",
        ignore_rectangles=site.ignore_rectangles,
    )
    failures = [
        f"{item.page}: {item.ratio:.4%} pixels changed ({item.diff})"
        for item in comparisons
        if item.ratio > site.max_changed_pixel_ratio
    ]
    assert not failures, "adoption visibly changed the rendered site:\n" + "\n".join(failures)

    status = _git(project, "status", "--short", "--untracked-files=all")
    for expected in site.expected_changes:
        assert expected in status
    assert _git(project, "log", "-1", "--format=%H").strip() == site.revision
    assert _git(project, "remote", "get-url", "--push", "origin").strip() == (
        "DISABLED_BY_REAL_SITE_HARNESS"
    )


def _git(project: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
