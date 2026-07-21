# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import shutil
import stat
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

from prodockit.pdf.build import Page, PdfBuildError, build_pdf

real_pandoc_and_weasyprint_required = pytest.mark.skipif(
    shutil.which("pandoc") is None or shutil.which("weasyprint") is None,
    reason="verifying real page placement (e.g. double_sided's recto rule) "
    "needs an actual pandoc+weasyprint render, not the fake-pandoc stub "
    "every other test here uses.",
)


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


def test_raises_pdf_build_error_when_pandoc_hangs_past_the_timeout(
    tmp_path: Path, fake_pandoc_on_path
) -> None:
    """Regression test: run_pandoc() had no timeout= at all, so a hung
    pandoc/WeasyPrint invocation (e.g. a pathological CSS layout) used to
    block the whole build indefinitely with no way to recover."""
    fake_pandoc_on_path("sleep 5")
    with pytest.raises(PdfBuildError, match="timed out"):
        build_pdf(
            [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
            str(tmp_path / "out.pdf"),
            pandoc_timeout=1,
        )


def test_rotates_landscape_pages_after_a_successful_build(
    tmp_path: Path, fake_pandoc_on_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """build_pdf() must always run the prodockit-table-rotated /Rotate
    post-process once pandoc/WeasyPrint succeeds - it's a no-op on a
    document with no rotated table, so there's no reason it should ever be
    skipped."""
    import prodockit.pdf.build as build_module

    output_path = tmp_path / "out.pdf"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    captured = {}
    monkeypatch.setattr(
        build_module,
        "rotate_landscape_pages",
        lambda path, **kwargs: captured.setdefault("path", path),
    )
    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(output_path),
    )
    assert captured["path"] == str(output_path)


def test_does_not_rotate_pages_when_pandoc_fails(
    tmp_path: Path, fake_pandoc_on_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import prodockit.pdf.build as build_module

    fake_pandoc_on_path('echo "boom" >&2; exit 1')
    called = []
    monkeypatch.setattr(
        build_module, "rotate_landscape_pages", lambda path, **kwargs: called.append(path)
    )
    with pytest.raises(PdfBuildError):
        build_pdf(
            [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
            str(tmp_path / "out.pdf"),
        )
    assert called == []


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
    assert (work_dir / "_prodockit_pdf_compiled.html").exists()
    assert (work_dir / "_prodockit_pdf_filter.lua").exists()
    assert (work_dir / "_prodockit_pdf_compiled.css").exists()


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
    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert compiled.index("Cover") < compiled.index("Chapter One") < compiled.index("Chapter Two")


def test_table_of_contents_is_inserted_after_the_cover_page_by_default(tmp_path: Path, fake_pandoc_on_path) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [
            Page(docs_rel_path="index.md", html="<h1>Cover</h1>", is_index=True),
            Page(docs_rel_path="chapter1.md", html="<h1>Chapter One</h1>"),
        ],
        str(tmp_path / "out.pdf"),
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert "Table of Contents" in compiled
    assert compiled.index("Cover") < compiled.index("Table of Contents") < compiled.index("Chapter One")


def test_table_of_contents_is_inserted_first_without_a_cover_page(tmp_path: Path, fake_pandoc_on_path) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [Page(docs_rel_path="chapter1.md", html="<h1>Chapter One</h1>")],
        str(tmp_path / "out.pdf"),
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert compiled.index("Table of Contents") < compiled.index("Chapter One")


def test_table_of_contents_can_be_disabled(tmp_path: Path, fake_pandoc_on_path) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [Page(docs_rel_path="chapter1.md", html="<h1>Chapter One</h1>")],
        str(tmp_path / "out.pdf"),
        include_table_of_contents=False,
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert "Table of Contents" not in compiled


def test_table_of_contents_title_is_configurable(tmp_path: Path, fake_pandoc_on_path) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [Page(docs_rel_path="chapter1.md", html="<h1>Chapter One</h1>")],
        str(tmp_path / "out.pdf"),
        table_of_contents_title="Contents",
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert "<h1 class=\"unnumbered unlisted\">Contents</h1>" in compiled


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
    css = (work_dir / "_prodockit_pdf_compiled.css").read_text(encoding="utf-8")
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
    css = (work_dir / "_prodockit_pdf_compiled.css").read_text(encoding="utf-8")
    assert '"Georgia", sans-serif' in css
    assert "size: Letter;" in css


def test_double_sided_is_passed_through_to_the_generated_css(
    tmp_path: Path, fake_pandoc_on_path
) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(tmp_path / "out.pdf"),
        double_sided=True,
        margin_inner="2.5cm",
        margin_outer="1.5cm",
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    css = (work_dir / "_prodockit_pdf_compiled.css").read_text(encoding="utf-8")
    assert "@page :right {" in css
    assert "@page :left {" in css
    assert "break-before: recto !important;" in css


def test_recto_title_is_passed_through_to_the_fixed_up_page_html(
    tmp_path: Path, fake_pandoc_on_path
) -> None:
    work_dir = tmp_path / "work"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [
            Page(
                docs_rel_path="chapter1.md",
                html="<h1>A Rather Long Chapter Title</h1>",
                recto_title="Short Title",
            )
        ],
        str(tmp_path / "out.pdf"),
        work_dir=str(work_dir),
        keep_work_dir=True,
    )
    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert 'class="prodockit-recto-title"' in compiled
    assert "Short Title" in compiled


def test_double_sided_flag_is_passed_through_to_rotate_landscape_pages(
    tmp_path: Path, fake_pandoc_on_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """build_pdf() must pass its own double_sided flag through to
    rotate_landscape_pages() - confirmed at the rotate.py unit-test level
    that this alternates 270/90 by final page position; here just confirm
    build_pdf() actually wires the flag through rather than dropping it."""
    import prodockit.pdf.build as build_module

    output_path = tmp_path / "out.pdf"
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    captured = {}
    monkeypatch.setattr(
        build_module,
        "rotate_landscape_pages",
        lambda path, **kwargs: captured.update(path=path, **kwargs),
    )
    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(output_path),
        double_sided=True,
    )
    assert captured == {"path": str(output_path), "double_sided": True}


# ---------------------------------------------------------------------------
# Back-of-book index (include_index) - see prodockit.pdf.index for the
# module doing the actual work; these tests exercise build_pdf()'s own
# two-pass orchestration around it.
# ---------------------------------------------------------------------------

pymupdf = pytest.importorskip("pymupdf")


def _fake_pandoc_building_a_real_pdf(tmp_path: Path) -> str:
    """Writes a fake `pandoc` (a shell script) that - unlike the plain
    "%PDF-1.4 stub" text file every other test here uses - builds a real,
    two-page PDF via pymupdf's own `insert_htmlbox()` (confirmed directly
    to support the non-ASCII bracket markers mark_index_terms() inserts,
    unlike its simpler insert_text()), with one marker on page 1 and two
    on page 2 - so build_pdf()'s own extract_term_pages() call has a real,
    searchable PDF to inspect after the first pass. Returns the script's
    own text, for the caller to pass to fake_pandoc_on_path."""
    helper_path = tmp_path / "_build_fake_pdf.py"
    helper_path.write_text(
        "import sys\n"
        "import pymupdf\n"
        "doc = pymupdf.open()\n"
        "p1 = doc.new_page()\n"
        "p1.insert_htmlbox(pymupdf.Rect(20, 20, 500, 200), "
        "'chapter one \\u27e6prodockit-index-1\\u27e7 text')\n"
        "p2 = doc.new_page()\n"
        "p2.insert_htmlbox(pymupdf.Rect(20, 20, 500, 200), "
        "'chapter two \\u27e6prodockit-index-2\\u27e7 and "
        "\\u27e6prodockit-index-3\\u27e7 text')\n"
        "doc.save(sys.argv[1])\n",
        encoding="utf-8",
    )
    return f'{sys.executable} "{helper_path}" "$3"\necho invoked >> "{tmp_path}/invocations.txt"\n'


def test_include_index_runs_a_second_pandoc_pass_with_real_entries(
    tmp_path: Path, fake_pandoc_on_path
) -> None:
    fake_pandoc_on_path(_fake_pandoc_building_a_real_pdf(tmp_path))
    work_dir = tmp_path / "work"

    build_pdf(
        [
            Page(docs_rel_path="chapter1.md", html='<span class="index">Widget</span>'),
            Page(
                docs_rel_path="chapter2.md",
                html=(
                    '<span class="index">widget</span>'
                    '<span class="index">Gadget</span>'
                ),
            ),
        ],
        str(tmp_path / "out.pdf"),
        include_index=True,
        work_dir=str(work_dir),
        keep_work_dir=True,
    )

    invocations = (tmp_path / "invocations.txt").read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 2  # first pass (extraction) + second (real content)

    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert '<div class="prodockit-index-entry prodockit-index-level-1">Gadget, 2</div>' in compiled
    # Pages 1 and 2 are consecutive - format_pages() collapses them into a
    # single en-dash range rather than "1, 2".
    assert '<div class="prodockit-index-entry prodockit-index-level-1">Widget, 1–2</div>' in compiled
    assert 'id="prodockit-index-content"' in compiled


def test_include_index_renders_a_code_styled_entry_in_code_tags(
    tmp_path: Path, fake_pandoc_on_path
) -> None:
    fake_pandoc_on_path(_fake_pandoc_building_a_real_pdf(tmp_path))
    work_dir = tmp_path / "work"

    build_pdf(
        [
            Page(
                docs_rel_path="chapter1.md",
                html=(
                    '<span class="index" data-index-code="true" '
                    'data-index-term="git commit"><code>git commit</code></span>'
                ),
            ),
        ],
        str(tmp_path / "out.pdf"),
        include_index=True,
        work_dir=str(work_dir),
        keep_work_dir=True,
    )

    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert (
        '<div class="prodockit-index-entry prodockit-index-level-1">'
        "<code>git commit</code>, 1</div>" in compiled
    )


def test_include_index_renders_a_hierarchical_entry_nested_under_its_parent(
    tmp_path: Path, fake_pandoc_on_path
) -> None:
    """Same real two-pass build as the flat/code-styled cases above, but
    for a hierarchical \\index{Parent!Child} marker - confirmed directly
    build.py's own index_terms/index_code_flags threading produces a real
    nested <div> pair through the whole pipeline, not just at the
    build_index_entries()/render_index_content() unit level."""
    fake_pandoc_on_path(_fake_pandoc_building_a_real_pdf(tmp_path))
    work_dir = tmp_path / "work"

    build_pdf(
        [
            Page(
                docs_rel_path="chapter1.md",
                html='<span class="index" data-index-term="Git!ssh keys">ssh keys</span>',
            ),
        ],
        str(tmp_path / "out.pdf"),
        include_index=True,
        work_dir=str(work_dir),
        keep_work_dir=True,
    )

    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    # "Git" is a pure grouping node here - no page of its own, no trailing
    # page list - since this is the only occurrence and it's a child path.
    assert '<div class="prodockit-index-entry prodockit-index-level-1">Git</div>' in compiled
    assert (
        '<div class="prodockit-index-entry prodockit-index-level-2">ssh keys, 1</div>'
        in compiled
    )


def test_include_index_off_by_default_runs_only_one_pandoc_pass(
    tmp_path: Path, fake_pandoc_on_path
) -> None:
    fake_pandoc_on_path(_fake_pandoc_building_a_real_pdf(tmp_path))

    build_pdf(
        [Page(docs_rel_path="chapter1.md", html='<span class="index">Widget</span>')],
        str(tmp_path / "out.pdf"),
    )

    invocations = (tmp_path / "invocations.txt").read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 1


def test_include_index_with_no_marked_terms_skips_the_second_pass(
    tmp_path: Path, fake_pandoc_on_path
) -> None:
    fake_pandoc_on_path(_fake_pandoc_building_a_real_pdf(tmp_path))

    build_pdf(
        [Page(docs_rel_path="chapter1.md", html="<p>No index terms here.</p>")],
        str(tmp_path / "out.pdf"),
        include_index=True,
    )

    invocations = (tmp_path / "invocations.txt").read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 1


def test_include_index_custom_title(tmp_path: Path, fake_pandoc_on_path) -> None:
    fake_pandoc_on_path(_fake_pandoc_building_a_real_pdf(tmp_path))
    work_dir = tmp_path / "work"

    build_pdf(
        [Page(docs_rel_path="chapter1.md", html='<span class="index">Widget</span>')],
        str(tmp_path / "out.pdf"),
        include_index=True,
        index_title="Glossary of Terms",
        work_dir=str(work_dir),
        keep_work_dir=True,
    )

    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert ">Glossary of Terms<" in compiled


@real_pandoc_and_weasyprint_required
def test_index_starts_on_a_recto_page_under_double_sided(tmp_path: Path) -> None:
    """The Index/TOC trigger heading build_pdf() inserts is `.unnumbered`
    (see prodockit.pdf.index's own module docstring) - a real concern is
    whether double_sided's `h1 { break-before: recto }` rule (see
    prodockit.pdf.css) still applies to it, since a *different* rule
    (`h1:not(.unnumbered) { string-set: chapter-title ... }`) deliberately
    does exclude unnumbered headings. Confirmed here with a real
    pandoc+weasyprint build (the fake-pandoc stub every other test in this
    file uses can't answer this - it ignores the real HTML/CSS entirely):
    every recto-forced heading, including the Index, lands on an odd
    page."""
    long_para = "<p>" + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 40) + "</p>"
    pages = [
        Page(docs_rel_path="index.md", html="<h1>Cover</h1>", is_index=True),
        Page(
            docs_rel_path="chapter1.md",
            html=f'<h1>Chapter One</h1>{long_para}<span class="index">Widget</span>{long_para}',
        ),
        Page(
            docs_rel_path="chapter2.md",
            html=f'<h1>Chapter Two</h1>{long_para}<span class="index">Gadget</span>{long_para}',
        ),
    ]
    output_path = tmp_path / "out.pdf"

    build_pdf(pages, str(output_path), double_sided=True, include_index=True)

    reader = PdfReader(str(output_path))
    index_page_numbers = [
        i for i, page in enumerate(reader.pages, start=1)
        if page.extract_text().strip().startswith("Index")
    ]
    assert index_page_numbers, "Index heading not found in the built PDF"
    assert index_page_numbers[0] % 2 == 1, (
        f"Index landed on page {index_page_numbers[0]}, an even (verso) page"
    )
