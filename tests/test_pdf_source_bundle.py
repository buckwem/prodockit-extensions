# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import shutil
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

real_weasyprint_required = pytest.mark.skipif(
    shutil.which("weasyprint") is None,
    reason="verifying the real per-page running header names the right "
    "file needs an actual weasyprint render - the fake-weasyprint stub "
    "every other test here uses ignores the real HTML/CSS entirely.",
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


def test_discover_source_files_excludes_a_tracked_icons_directory(tmp_path: Path) -> None:
    """A custom_icons directory (pymdownx.emoji's own convention - see
    zensical.toml's options.custom_icons) is typically *tracked*, not
    gitignored - it has to be, for the site/PDF to build at all - so
    .gitignore alone can't keep a vendored icon pack's hundreds/thousands
    of SVGs out of the bundle. Excluded unconditionally by directory name
    instead, regardless of where in the tree it lives."""
    _init_git_repo(tmp_path)
    (tmp_path / "overrides" / ".icons" / "bootstrap").mkdir(parents=True)
    (tmp_path / "overrides" / ".icons" / "bootstrap" / "icon.svg").write_text(
        "<svg></svg>\n", encoding="utf-8"
    )
    (tmp_path / "kept.txt").write_text("keep me\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "overrides/.icons/bootstrap/icon.svg", "kept.txt"],
        cwd=tmp_path,
        check=True,
    )

    files = discover_source_files(str(tmp_path))
    assert "kept.txt" in files
    assert not any(".icons" in f for f in files)


def test_discover_source_files_excludes_a_top_level_icons_directory(tmp_path: Path) -> None:
    """Same exclusion, regardless of which directory a project's own
    custom_dir points .icons at - here at the repository root rather than
    nested under a custom_dir like "overrides"."""
    _init_git_repo(tmp_path)
    (tmp_path / ".icons" / "gitlab").mkdir(parents=True)
    (tmp_path / ".icons" / "gitlab" / "branch.svg").write_text("<svg></svg>\n", encoding="utf-8")
    subprocess.run(["git", "add", ".icons/gitlab/branch.svg"], cwd=tmp_path, check=True)

    assert discover_source_files(str(tmp_path)) == []


def test_discover_source_files_excluding_icons_is_not_configurable_via_gitignore(
    tmp_path: Path,
) -> None:
    """The exclusion applies even if a project's own .gitignore doesn't
    mention .icons at all - it's not something a project (or a student
    editing its config) can opt back into by omission."""
    _init_git_repo(tmp_path)
    (tmp_path / "overrides" / ".icons").mkdir(parents=True)
    (tmp_path / "overrides" / ".icons" / "icon.svg").write_text("<svg></svg>\n", encoding="utf-8")
    subprocess.run(["git", "add", "overrides/.icons/icon.svg"], cwd=tmp_path, check=True)

    assert discover_source_files(str(tmp_path)) == []


def test_discover_source_files_excludes_a_tracked_styles_directory(tmp_path: Path) -> None:
    """A Vale StylesPath (conventionally named "styles") holds downloaded
    rule packs (Microsoft/proselint/Readability-style .yml files) that are
    typically *tracked* for offline/CI builds, not gitignored - same
    reasoning as the .icons exclusion above."""
    _init_git_repo(tmp_path)
    (tmp_path / "styles" / "Microsoft").mkdir(parents=True)
    (tmp_path / "styles" / "Microsoft" / "Passive.yml").write_text(
        "extends: existence\n", encoding="utf-8"
    )
    (tmp_path / "kept.txt").write_text("keep me\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "styles/Microsoft/Passive.yml", "kept.txt"], cwd=tmp_path, check=True
    )

    files = discover_source_files(str(tmp_path))
    assert "kept.txt" in files
    assert not any("styles" in f for f in files)


def test_discover_source_files_excludes_common_lockfiles(tmp_path: Path) -> None:
    """Dependency lockfiles are machine-generated by a package manager,
    never hand-written by a student, and can run to thousands of lines -
    excluded by exact file name regardless of which directory holds them."""
    _init_git_repo(tmp_path)
    (tmp_path / "tools" / "mermaid").mkdir(parents=True)
    lockfile_names = [
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Pipfile.lock",
        "poetry.lock",
        "Cargo.lock",
    ]
    for name in lockfile_names:
        (tmp_path / "tools" / "mermaid" / name).write_text("{}\n", encoding="utf-8")
    (tmp_path / "kept.txt").write_text("keep me\n", encoding="utf-8")
    subprocess.run(
        ["git", "add"] + [f"tools/mermaid/{name}" for name in lockfile_names] + ["kept.txt"],
        cwd=tmp_path,
        check=True,
    )

    files = discover_source_files(str(tmp_path))
    assert files == ["kept.txt"]


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


def test_a_file_invalid_past_the_8kib_sniff_window_is_skipped_not_crashed(
    tmp_path: Path, fake_weasyprint_on_path
) -> None:
    """Regression test: is_probably_text() only sniffs the first 8 KiB, so
    a file that's valid UTF-8 there but has an invalid byte further in
    used to crash the whole bundle build with an uncaught
    UnicodeDecodeError when it was fully read - it should be skipped the
    same way a binary file already is."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "valid.py").write_text("print('ok')\n", encoding="utf-8")
    # First 8192 bytes are plain ASCII (passes the sniff), followed by a
    # byte sequence that isn't valid UTF-8 - only found once the whole
    # file is actually read.
    (repo / "mostly_text.dat").write_bytes(b"a" * 8200 + b"\xff\xfe")
    subprocess.run(["git", "add", "valid.py", "mostly_text.dat"], cwd=repo, check=True)
    fake_weasyprint_on_path('echo "%PDF-1.4 stub" > "$2"')

    count = build_source_bundle(str(tmp_path / "out.pdf"), root=str(repo))

    assert count == 1


def test_an_empty_repository_builds_a_zero_file_pdf(
    tmp_path: Path, fake_weasyprint_on_path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    fake_weasyprint_on_path('echo "%PDF-1.4 stub" > "$2"')

    output_path = tmp_path / "out.pdf"
    count = build_source_bundle(str(output_path), root=str(repo))

    assert count == 0
    assert output_path.exists()


def test_a_vendored_icons_directory_is_excluded_from_the_built_bundle(
    tmp_path: Path, fake_weasyprint_on_path
) -> None:
    """End-to-end version of the discover_source_files() exclusion tests
    above - confirms a vendored icon pack never reaches the generated
    HTML/page count, not just discover_source_files()'s own return value."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_sample_repo(repo)
    (repo / "overrides" / ".icons" / "bootstrap").mkdir(parents=True)
    (repo / "overrides" / ".icons" / "bootstrap" / "icon.svg").write_text(
        "<svg></svg>\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "overrides/.icons/bootstrap/icon.svg"], cwd=repo, check=True
    )
    fake_weasyprint_on_path('echo "%PDF-1.4 stub" > "$2"')
    work_dir = tmp_path / "work"

    count = build_source_bundle(
        str(tmp_path / "out.pdf"), root=str(repo), work_dir=str(work_dir), keep_work_dir=True
    )

    # src/a.py, src/b.py, .gitignore - the vendored icon isn't counted
    assert count == 3
    html = (work_dir / "_prodockit_source_bundle.html").read_text(encoding="utf-8")
    assert ".icons" not in html


@real_weasyprint_required
def test_running_header_names_the_file_actually_on_that_page(tmp_path: Path) -> None:
    """Regression test: the running header (`string(current-file)`, see
    the CSS's own `.file-marker` rule) used to show the *next* file's
    name on a file's own last page. `.file-marker` (which sets that CSS
    string) had no page-break of its own - only the following `<pre>`
    did - so a multi-line file's own marker rendered on the *previous*
    file's last page, right at the tail end just before the break, and
    that page's header showed the wrong (upcoming) file's name instead
    of the one whose content actually filled it.

    Confirmed directly with a real weasyprint render (the fake-weasyprint
    stub every other test in this file uses ignores the real HTML/CSS
    entirely, so it can't catch this): a_first.py is long enough to span
    several pages on its own, followed by two single-line files."""
    from pypdf import PdfReader

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "a_first.py").write_text(
        "\n".join(f"print({i})" for i in range(400)) + "\n", encoding="utf-8"
    )
    (repo / "b_second.py").write_text("print(1)\n", encoding="utf-8")
    (repo / "c_third.py").write_text("print(1)\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "a_first.py", "b_second.py", "c_third.py"], cwd=repo, check=True
    )
    output_path = tmp_path / "out.pdf"

    build_source_bundle(str(output_path), root=str(repo), report_name="Test Report")

    reader = PdfReader(str(output_path))
    # Find a_first.py's own *last* page by its content - the unambiguous
    # boundary where the original bug showed the wrong file's name: its
    # very last line ("print(399)") pins down exactly which page holds
    # a_first.py's tail end, independent of any header text.
    last_page_text = None
    for page in reader.pages:
        text = page.extract_text()
        if "print(399)" in text:
            last_page_text = text
            break
    assert last_page_text is not None, "a_first.py's last line not found in any page"

    assert "a_first.py" in last_page_text
    assert "b_second.py" not in last_page_text


def test_work_dir_is_cleaned_up_by_default(tmp_path: Path, fake_weasyprint_on_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_sample_repo(repo)
    fake_weasyprint_on_path('echo "%PDF-1.4 stub" > "$2"')
    work_dir = tmp_path / "work"

    build_source_bundle(str(tmp_path / "out.pdf"), root=str(repo), work_dir=str(work_dir))

    assert not work_dir.exists()
