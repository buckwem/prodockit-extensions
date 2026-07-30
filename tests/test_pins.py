# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
from pathlib import Path

import pytest

from prodockit.pins import (
    PackageState,
    PinError,
    PinSite,
    apply_version,
    discover,
    version_key,
)


def _project(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_version_key_orders_numerically_not_lexically() -> None:
    """0.0.9 sorts below 0.0.52 - a plain string compare puts it above,
    which would report an up-to-date project as behind (and vice versa)."""
    assert version_key("0.0.9") < version_key("0.0.52")
    assert version_key("69.0") < version_key("70.0")
    assert version_key("1.2.10") > version_key("1.2.9")


def test_version_key_sorts_a_prerelease_below_its_release() -> None:
    assert version_key("1.0.0rc1") < version_key("1.0.0")


def test_discover_finds_every_declaration_across_both_ci_layouts(tmp_path: Path) -> None:
    """The same version is declared in several files at once - that is the
    whole problem this solves - and GitHub and GitLab keep their jobs in
    different places."""
    _project(
        tmp_path,
        {
            "pyproject.toml": 'dependencies = [\n  "zensical>=0.0.52",\n]\n',
            ".github/workflows/docs.yml": '    - run: pip install "zensical==0.0.52" "weasyprint==69.0"\n',
            ".gitlab-ci.yml": "  script:\n    - pip install zensical==0.0.52\n",
            "requirements.txt": "weasyprint==69.0\n",
        },
    )

    states = discover(str(tmp_path))

    assert [s.path for s in states["zensical"].sites] == [
        "pyproject.toml",
        ".gitlab-ci.yml",
        os.path.join(".github", "workflows", "docs.yml"),
    ]
    assert {s.path for s in states["weasyprint"].sites} == {
        "requirements.txt",
        os.path.join(".github", "workflows", "docs.yml"),
    }


def test_discover_records_the_operator_as_written(tmp_path: Path) -> None:
    """A floor and an exact pin are both correct in their own place - the
    library floor must not be flattened into a pin on rewrite."""
    _project(
        tmp_path,
        {
            "pyproject.toml": '  "zensical>=0.0.52",\n',
            ".gitlab-ci.yml": "    - pip install zensical==0.0.52\n",
        },
    )

    ops = {s.path: s.op for s in discover(str(tmp_path))["zensical"].sites}

    assert ops == {"pyproject.toml": ">=", ".gitlab-ci.yml": "=="}


def test_discover_ignores_a_package_whose_name_merely_contains_a_managed_one(
    tmp_path: Path,
) -> None:
    _project(tmp_path, {"requirements.txt": "my-zensical-fork==1.0\nzensical-extras==2.0\n"})

    assert discover(str(tmp_path))["zensical"].sites == []


def test_discover_skips_build_output_and_virtualenvs(tmp_path: Path) -> None:
    """A copy of a workflow inside site/ or .venv/ is a build artifact, not
    a declaration anyone edits."""
    _project(
        tmp_path,
        {
            ".github/workflows/docs.yml": '- run: pip install "zensical==0.0.52"\n',
            ".gitlab/ci/build.yml": "    - pip install zensical==0.0.52\n",
        },
    )
    stale = tmp_path / ".github" / "workflows" / "node_modules"
    stale.mkdir(parents=True)
    (stale / "copy.yml").write_text('pip install "zensical==9.9.9"\n', encoding="utf-8")

    versions = {s.version for s in discover(str(tmp_path))["zensical"].sites}

    assert versions == {"0.0.52"}


def test_discover_reports_a_package_that_is_not_declared_at_all(tmp_path: Path) -> None:
    """A project that has not pinned WeasyPrint yet should still see it
    listed, rather than silently omitted from the report."""
    _project(tmp_path, {"pyproject.toml": '  "zensical>=0.0.52",\n'})

    states = discover(str(tmp_path))

    assert states["weasyprint"].sites == []
    assert states["weasyprint"].current is None


def test_current_is_the_highest_when_files_disagree(tmp_path: Path) -> None:
    """Files disagreeing is itself the bug being surfaced; treat the
    highest as current so the fix moves everything forward."""
    _project(
        tmp_path,
        {
            "pyproject.toml": '  "zensical>=0.0.9",\n',
            ".gitlab-ci.yml": "    - pip install zensical==0.0.52\n",
        },
    )

    state = discover(str(tmp_path))["zensical"]

    assert state.is_consistent is False
    assert state.current == "0.0.52"


def test_apply_version_rewrites_every_site_and_keeps_each_operator(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {
            "pyproject.toml": 'dependencies = [\n  "zensical>=0.0.52",\n]\n',
            ".github/workflows/docs.yml": '    - run: pip install "zensical==0.0.52"\n',
            ".gitlab-ci.yml": "    - pip install zensical == 0.0.52\n",
        },
    )
    state = discover(str(tmp_path))["zensical"]

    changed = apply_version(str(tmp_path), state, "0.0.53")

    assert len(changed) == 3
    assert '"zensical>=0.0.53"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '"zensical==0.0.53"' in (
        tmp_path / ".github" / "workflows" / "docs.yml"
    ).read_text(encoding="utf-8")
    # Whitespace around the operator as written is tolerated.
    assert "zensical==0.0.53" in (tmp_path / ".gitlab-ci.yml").read_text(encoding="utf-8")


def test_apply_version_leaves_other_mentions_of_the_package_alone(tmp_path: Path) -> None:
    """A changelog line or a prose mention of the same version must not be
    rewritten - only the lines discovery identified as declarations."""
    workflow = (
        "# zensical 0.0.52 redrew an icon; see the changelog\n"
        '    - run: pip install "zensical==0.0.52"\n'
    )
    _project(tmp_path, {".github/workflows/docs.yml": workflow})
    state = discover(str(tmp_path))["zensical"]

    apply_version(str(tmp_path), state, "0.0.53")
    text = (tmp_path / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")

    assert "# zensical 0.0.52 redrew an icon" in text
    assert '"zensical==0.0.53"' in text


def test_apply_version_skips_sites_already_at_the_target(tmp_path: Path) -> None:
    _project(tmp_path, {"requirements.txt": "zensical==0.0.53\n"})
    state = discover(str(tmp_path))["zensical"]

    assert apply_version(str(tmp_path), state, "0.0.53") == []


def test_apply_version_refuses_to_guess_when_the_file_moved_under_it(tmp_path: Path) -> None:
    """Rewriting by line number is only safe while the file is unchanged.
    Fail loudly rather than corrupt an unrelated line."""
    _project(tmp_path, {"requirements.txt": "zensical==0.0.52\n"})
    state = discover(str(tmp_path))["zensical"]
    (tmp_path / "requirements.txt").write_text("something-else==1.0\n", encoding="utf-8")

    with pytest.raises(PinError, match="no longer contains"):
        apply_version(str(tmp_path), state, "0.0.53")


def test_is_behind_compares_numerically() -> None:
    state = PackageState(
        package="zensical",
        sites=[PinSite("pyproject.toml", 1, "zensical", ">=", "0.0.9")],
        latest="0.0.52",
    )

    assert state.is_behind is True


def test_is_behind_is_false_when_no_latest_is_known() -> None:
    """An unreachable PyPI must not read as "up to date" *or* as drift."""
    state = PackageState(
        package="zensical",
        sites=[PinSite("pyproject.toml", 1, "zensical", ">=", "0.0.52")],
        latest=None,
        latest_error="could not reach PyPI",
    )

    assert state.is_behind is False
