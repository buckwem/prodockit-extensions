# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import stat
import subprocess
from pathlib import Path

import pytest

from prodockit.pdf.source_bundle import (
    SourceBundleError,
    build_source_bundle,
    discover_source_files,
    is_probably_text,
)


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def _fake_weasyprint(tmp_path: Path, script: str) -> Path:
    """Writes a fake `weasyprint` executable (a shell script) onto PATH so a
    test can exercise build_source_bundle() without a real WeasyPrint
    install. The real invocation shape is: weasyprint <html> <output> - no
    flags - so $1=<html> $2=<output>."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    weasyprint_path = bin_dir / "weasyprint"
    weasyprint_path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    weasyprint_path.chmod(weasyprint_path.stat().st_mode | stat.S_IEXEC)
    return bin_dir


@pytest.fixture()
def fake_weasyprint_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _install(script: str) -> None:
        bin_dir = _fake_weasyprint(tmp_path, script)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    return _install


# ---------------------------------------------------------------------------
# is_probably_text
# ---------------------------------------------------------------------------


def test_is_probably_text_true_for_a_real_text_file(tmp_path: Path) -> None:
    path = tmp_path / "hello.py"
    path.write_text("print('hello')\n", encoding="utf-8")
    assert is_probably_text(str(path)) is True


def test_is_probably_text_false_for_a_null_byte_containing_file(tmp_path: Path) -> None:
    path = tmp_path / "binary.bin"
    path.write_bytes(b"\x89PNG\x00\x01\x02\x03")
    assert is_probably_text(str(path)) is False


def test_is_probably_text_false_for_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "invalid.bin"
    path.write_bytes(b"\xff\xfe\xfd")
    assert is_probably_text(str(path)) is False


def test_is_probably_text_false_for_a_missing_file(tmp_path: Path) -> None:
    assert is_probably_text(str(tmp_path / "does-not-exist.txt")) is False


# ---------------------------------------------------------------------------
# discover_source_files
# ---------------------------------------------------------------------------


def test_discover_source_files_lists_tracked_files_sorted(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "b.py").write_text("b\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py", "b.py"], cwd=tmp_path, check=True)

    assert discover_source_files(str(tmp_path)) == ["a.py", "b.py"]


def test_discover_source_files_excludes_gitignored_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("secret\n", encoding="utf-8")
    (tmp_path / "kept.txt").write_text("keep me\n", encoding="utf-8")
    subprocess.run(["git", "add", "kept.txt", ".gitignore"], cwd=tmp_path, check=True)

    files = discover_source_files(str(tmp_path))
    assert "kept.txt" in files
    assert ".gitignore" in files
    assert "ignored.txt" not in files


def test_discover_source_files_includes_untracked_but_not_ignored_files(tmp_path: Path) -> None:
    """A brand new file nobody's run `git add` on yet still counts as
    "not excluded by .gitignore" - matches the issue's own instruction to
    use .gitignore, not the git index, as the inclusion/exclusion rule."""
    _init_git_repo(tmp_path)
    (tmp_path / "new_file.py").write_text("new\n", encoding="utf-8")

    assert discover_source_files(str(tmp_path)) == ["new_file.py"]


def test_discover_source_files_raises_for_a_non_git_directory(tmp_path: Path) -> None:
    with pytest.raises(SourceBundleError):
        discover_source_files(str(tmp_path))


# ---------------------------------------------------------------------------
# build_source_bundle
# ---------------------------------------------------------------------------


def _make_sample_repo(root: Path) -> None:
    _init_git_repo(root)
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("print('a')\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("print('b')\n", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\x00\x01\x02\x03")
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (root / "ignored.txt").write_text("should not appear\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "src/a.py", "src/b.py", "logo.png", ".gitignore"],
        cwd=root,
        check=True,
    )


def test_builds_the_pdf_to_the_given_output_path(tmp_path: Path, fake_weasyprint_on_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_sample_repo(repo)
    fake_weasyprint_on_path('echo "%PDF-1.4 stub" > "$2"')

    output_path = tmp_path / "source_bundle.pdf"
    count = build_source_bundle(str(output_path), root=str(repo))

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("%PDF")
    # src/a.py, src/b.py, .gitignore itself - logo.png (binary) and
    # ignored.txt (gitignored) excluded
    assert count == 3


def test_relative_output_path_resolves_against_root(tmp_path: Path, fake_weasyprint_on_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_sample_repo(repo)
    fake_weasyprint_on_path('echo "%PDF-1.4 stub" > "$2"')

    build_source_bundle("source_bundle.pdf", root=str(repo))

    assert (repo / "source_bundle.pdf").exists()


def test_raises_source_bundle_error_when_weasyprint_fails(
    tmp_path: Path, fake_weasyprint_on_path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_sample_repo(repo)
    fake_weasyprint_on_path('echo "boom" >&2; exit 1')

    with pytest.raises(SourceBundleError) as exc_info:
        build_source_bundle(str(tmp_path / "out.pdf"), root=str(repo))
    assert exc_info.value.returncode == 1
    assert "boom" in (exc_info.value.stderr or "")


def test_generated_html_has_one_page_break_pre_per_text_file_with_a_file_marker(
    tmp_path: Path, fake_weasyprint_on_path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_sample_repo(repo)
    fake_weasyprint_on_path('echo "%PDF-1.4 stub" > "$2"')
    work_dir = tmp_path / "work"

    build_source_bundle(
        str(tmp_path / "out.pdf"),
        root=str(repo),
        report_name="My Report",
        work_dir=str(work_dir),
        keep_work_dir=True,
    )

    html = (work_dir / "_prodockit_source_bundle.html").read_text(encoding="utf-8")
    assert 'class="file-marker">src/a.py<' in html
    assert 'class="file-marker">src/b.py<' in html
    assert "print(&#x27;a&#x27;)" in html
    assert "logo.png" not in html
    assert "should not appear" not in html
    assert "font-family: Courier" in html
    assert "font-size: 8pt" in html
    assert "white-space: pre-wrap" in html
    assert "break-before: page" in html
    assert 'content: "My Report"' in html
    assert "content: string(current-file)" in html
    assert 'content: "Page " counter(page) " of " counter(pages)' in html


def test_work_dir_is_cleaned_up_by_default(tmp_path: Path, fake_weasyprint_on_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_sample_repo(repo)
    fake_weasyprint_on_path('echo "%PDF-1.4 stub" > "$2"')
    work_dir = tmp_path / "work"

    build_source_bundle(str(tmp_path / "out.pdf"), root=str(repo), work_dir=str(work_dir))

    assert not work_dir.exists()
