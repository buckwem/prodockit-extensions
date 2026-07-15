# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import stat
from pathlib import Path

import pytest

from zendoc.pdf.build import Page, PdfBuildError, build_pdf


def _fake_pandoc(tmp_path: Path, script: str) -> Path:
    """Writes a fake `pandoc` executable (a shell script) onto PATH so a
    test can exercise build_pdf() without a real Pandoc/WeasyPrint install.
    The real invocation shape is:
    pandoc <html> -o <output> --pdf-engine=weasyprint --pdf-engine-opt=-q
    --mathjax --lua-filter=<lua> -f html --resource-path=. --resource-path=<docs_dir>
    --css=<css>, so $1=<html> $3=<output> (after -o) ... - written to accept
    any args and just run `script`, which can inspect $@ itself if needed."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    pandoc_path = bin_dir / "pandoc"
    pandoc_path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    pandoc_path.chmod(pandoc_path.stat().st_mode | stat.S_IEXEC)
    return bin_dir


@pytest.fixture()
def fake_pandoc_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _install(script: str) -> None:
        bin_dir = _fake_pandoc(tmp_path, script)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    return _install


def test_writes_the_pdf_to_the_given_output_path(tmp_path: Path, fake_pandoc_on_path) -> None:
    output_path = tmp_path / "dist" / "report.pdf"
    output_path.parent.mkdir()
    # $1=<html> $2="-o" $3=<output path> - write a stub PDF at $3 to
    # simulate a real build.
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(output_path),
    )
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("%PDF")


def test_raises_pdf_build_error_when_pandoc_fails(tmp_path: Path, fake_pandoc_on_path) -> None:
    fake_pandoc_on_path('echo "boom" >&2; exit 1')
    with pytest.raises(PdfBuildError) as exc_info:
        build_pdf(
            [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
            str(tmp_path / "out.pdf"),
        )
    assert exc_info.value.returncode == 1
    assert "boom" in (exc_info.value.stderr or "")


def test_work_dir_is_cleaned_up_by_default(tmp_path: Path, fake_pandoc_on_path) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(tmp_path / "out.pdf"),
        work_dir=str(work_dir),
    )
    assert not work_dir.exists()


def test_keep_work_dir_leaves_intermediate_files_in_place(tmp_path: Path, fake_pandoc_on_path) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(tmp_path / "out.pdf"),
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    assert work_dir.exists()
    assert (work_dir / "_zendoc_pdf_compiled.html").exists()
    assert (work_dir / "_zendoc_pdf_filter.lua").exists()
    assert (work_dir / "_zendoc_pdf_compiled.css").exists()


def test_auto_created_temp_dir_is_always_cleaned_up_even_with_keep_work_dir(tmp_path: Path, fake_pandoc_on_path) -> None:
    """keep_work_dir only makes sense with an explicit work_dir - an
    auto-created temporary directory has no path the caller could go look
    at afterwards anyway, so it's always removed."""
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    # No assertion possible on the auto-created path itself (we never see
    # it) - this just confirms passing keep_work_dir=True without an
    # explicit work_dir doesn't raise or otherwise misbehave.
    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(tmp_path / "out.pdf"),
        keep_work_dir=True,
    )


def test_multiple_pages_are_concatenated_in_order(tmp_path: Path, fake_pandoc_on_path) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [
            Page(docs_rel_path="index.md", html="<h1>Cover</h1>", is_index=True),
            Page(docs_rel_path="chapter1.md", html="<h1>Chapter One</h1>"),
            Page(docs_rel_path="chapter2.md", html="<h1>Chapter Two</h1>"),
        ],
        str(tmp_path / "out.pdf"),
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    compiled = (work_dir / "_zendoc_pdf_compiled.html").read_text(encoding="utf-8")
    assert compiled.index("Cover") < compiled.index("Chapter One") < compiled.index("Chapter Two")


def test_extra_css_is_included_before_the_generated_css(tmp_path: Path, fake_pandoc_on_path) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(tmp_path / "out.pdf"),
        extra_css=".my-custom-class { color: red; }",
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    css = (work_dir / "_zendoc_pdf_compiled.css").read_text(encoding="utf-8")
    assert css.index(".my-custom-class") < css.index("@page")


def test_generated_css_reflects_the_given_typography_and_layout(tmp_path: Path, fake_pandoc_on_path) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(tmp_path / "out.pdf"),
        main_font="Georgia",
        page_size="Letter",
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    css = (work_dir / "_zendoc_pdf_compiled.css").read_text(encoding="utf-8")
    assert '"Georgia", sans-serif' in css
    assert "size: Letter;" in css
