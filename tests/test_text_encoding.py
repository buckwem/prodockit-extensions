# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest

from prodockit.text_encoding import (
    inspect_project_text_encoding,
    inspect_utf8_file,
    project_text_files,
)


def test_reports_every_invalid_sequence_with_crlf_locations(tmp_path: Path) -> None:
    page = tmp_path / "docs" / "bad.md"
    page.parent.mkdir()
    page.write_bytes(b"valid \xe2\x98\x83\r\nsecond \xff value \xfe\r\n")

    problems = inspect_utf8_file(page)

    assert [(item.line, item.column, item.offset) for item in problems] == [
        (2, 8, 18),
        (2, 16, 26),
    ]
    assert {item.message for item in problems} == {"invalid UTF-8 byte sequence"}


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_lf_and_crlf_have_the_same_logical_line_numbers(
    tmp_path: Path, newline: bytes
) -> None:
    page = tmp_path / "page.md"
    page.write_bytes(b"first" + newline + b"second \xff" + newline + b"third \xfe")

    assert [problem.line for problem in inspect_utf8_file(page)] == [2, 3]


def test_inventory_covers_supported_inputs_and_excludes_generated_trees(
    tmp_path: Path,
) -> None:
    wanted = (
        "zensical.toml",
        "pyproject.toml",
        ".python-version",
        ".prodockit-components.toml",
        "requirements/docs.txt",
        ".github/workflows/docs.yml",
        ".gitlab/pipelines/docs.yaml",
        ".gitlab-ci.yml",
        "tools/mathjax/package-lock.json",
        "docs/index.md",
    )
    unwanted = (
        "site/generated.md",
        "public/generated.md",
        ".venv/generated.md",
        "tools/mathjax/node_modules/generated.md",
        ".prodockit-adopt-backups/generated.md",
    )
    for relative in wanted + unwanted:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("valid Unicode: café 雪\n", encoding="utf-8")

    found = {
        str(path.relative_to(tmp_path))
        for path in project_text_files(
            tmp_path, tmp_path / "zensical.toml", tmp_path / "docs"
        )
    }

    assert set(wanted) <= found
    assert not (set(unwanted) & found)


def test_project_scan_continues_across_files(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Valid"\n', encoding="utf-8")
    first = tmp_path / "docs" / "first.md"
    second = tmp_path / "docs" / "second.md"
    first.parent.mkdir()
    first.write_bytes(b"first \xff\n")
    second.write_bytes(b"second \xfe\n")

    problems = inspect_project_text_encoding(tmp_path, config, tmp_path / "docs")

    assert [problem.location(tmp_path) for problem in problems] == [
        "docs/first.md:1:7",
        "docs/second.md:1:8",
    ]


@pytest.mark.parametrize(
    "relative",
    [
        "docs/page.md",
        "zensical.toml",
        ".prodockit-adopt.toml",
        "pyproject.toml",
        ".python-version",
        "requirements-dev.txt",
        "requirements/docs.txt",
        "tools/mathjax/package-lock.json",
        ".github/workflows/docs.yml",
        ".gitlab-ci.yml",
        ".gitlab/pipelines/docs.yaml",
    ],
)
def test_each_supported_file_category_is_validated(
    tmp_path: Path, relative: str
) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Valid"\n', encoding="utf-8")
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"invalid \xff\n")

    problems = inspect_project_text_encoding(tmp_path, config, tmp_path / "docs")

    assert any(problem.path == target and problem.line == 1 for problem in problems)


def test_valid_non_ascii_utf8_passes(tmp_path: Path) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Café ☕"\n', encoding="utf-8")
    page = tmp_path / "docs" / "page.md"
    page.parent.mkdir()
    page.write_text("Résumé, snowman ☃ and emoji 🧭\n", encoding="utf-8")

    assert inspect_project_text_encoding(tmp_path, config, page.parent) == ()


def test_unreadable_input_does_not_stop_the_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Valid"\n', encoding="utf-8")
    unreadable = tmp_path / "docs" / "unreadable.md"
    invalid = tmp_path / "docs" / "invalid.md"
    unreadable.parent.mkdir()
    unreadable.write_text("valid before permissions fail\n", encoding="utf-8")
    invalid.write_bytes(b"invalid \xff\n")
    original = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path == unreadable:
            raise PermissionError("permission denied")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    problems = inspect_project_text_encoding(tmp_path, config, tmp_path / "docs")
    unreadable_problem = next(problem for problem in problems if problem.path == unreadable)

    assert unreadable_problem.line is None
    assert unreadable_problem.message == "cannot read file: permission denied"
    assert any(problem.path == invalid and problem.line == 1 for problem in problems)
