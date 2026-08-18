# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import re
import shutil
import stat
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

from prodockit.pdf.build import Page, PdfBuildError, build_pdf
from prodockit.pdf.index import INDEX_TITLE_CLASS

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
    --mathjax --wrap=none --lua-filter=<lua> -f html --resource-path=.
    --resource-path=<docs_dir> --css=<css>, so $1=<html> $3=<output> (after
    -o) ... - written to accept any args and just run `script`, which can
    inspect $@ itself if needed."""
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


# ---------------------------------------------------------------------------
# Back-of-book index (include_index) - see prodockit.pdf.index for the
# module doing the actual work; these tests exercise build_pdf()'s own
# two-pass orchestration around it.
# ---------------------------------------------------------------------------

pymupdf = pytest.importorskip("pymupdf")


def _fake_pandoc_building_a_real_pdf(tmp_path: Path) -> str:
    """Writes a fake `pandoc` (a shell script) that - unlike the plain
    "%PDF-1.4 stub" text file every other test here uses - builds a real,
    two-page PDF carrying the marker ids mark_index_terms() inserts as PDF
    named destinations (what WeasyPrint emits for an element `id`), one on
    page 1 and two on page 2 - so build_pdf()'s own extract_term_pages()
    call has a real destination tree to resolve after the first pass.
    Returns the script's own text, for the caller to pass to
    fake_pandoc_on_path."""
    helper_path = tmp_path / "_build_fake_pdf.py"
    helper_path.write_text(
        "import sys\n"
        "import pymupdf\n"
        "doc = pymupdf.open()\n"
        "doc.new_page()\n"
        "doc.new_page()\n"
        "items = []\n"
        "for name, pno in [('prodockit-index-mark-1', 0), "
        "('prodockit-index-mark-2', 1), ('prodockit-index-mark-3', 1)]:\n"
        "    xref = doc.get_new_xref()\n"
        "    doc.update_object(xref, "
        "'<< /D [ %s 0 R /XYZ 0 800 0 ] >>' % doc.page_xref(pno))\n"
        "    items.append('(%s) %s 0 R' % (name, xref))\n"
        "dests = doc.get_new_xref()\n"
        "doc.update_object(dests, '<< /Names [ ' + ' '.join(items) + ' ] >>')\n"
        "names = doc.get_new_xref()\n"
        "doc.update_object(names, '<< /Dests %s 0 R >>' % dests)\n"
        "doc.xref_set_key(doc.pdf_catalog(), 'Names', '%s 0 R' % names)\n"
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


@real_pandoc_and_weasyprint_required
def test_index_markers_leave_no_trace_in_the_pdf_text_layer(tmp_path: Path) -> None:
    """prodockit-extensions#133: the marker inserted after each
    \\index{Term} used to be real text (`⟦prodockit-index-N⟧` at
    0.1pt), invisible on the page but present in the finished PDF's text
    layer - so in copy and paste, the reader's own search, text extraction
    and screen readers, mid-sentence.

    Only a real pandoc+weasyprint build can answer this: it needs the
    actual text layer WeasyPrint produces, which the fake-pandoc stub
    elsewhere in this file cannot supply. Asserts both halves - that the
    markers are gone *and* that the index still resolves real page
    numbers, since deleting the markers outright would satisfy the first
    on its own while destroying the feature."""
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

    build_pdf(pages, str(output_path), include_index=True)

    reader = PdfReader(str(output_path))
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "prodockit-index" not in full_text, "index marker leaked into the PDF text layer"
    assert "⟦" not in full_text and "⟧" not in full_text

    # The index itself must still be real: an entry per term, each citing
    # the page that term actually appears on. Read from the index page
    # only - "Widget" also occurs in the prose it was marked in, so
    # scanning the whole document would match those lines too.
    index_text = next(
        (
            text
            for page in reader.pages
            if (text := page.extract_text()).strip().startswith("Index")
        ),
        "",
    )
    assert index_text, "no Index page found in the built PDF"
    entries = dict(re.findall(r"^(Widget|Gadget), (\d+)\s*$", index_text, re.MULTILINE))
    assert set(entries) == {"Widget", "Gadget"}, f"unexpected index entries: {index_text!r}"
    for term, cited_page in entries.items():
        assert term in reader.pages[int(cited_page) - 1].extract_text(), (
            f"index says {term!r} is on page {cited_page}, but that page doesn't contain it"
        )


@real_pandoc_and_weasyprint_required
def test_copyright_text_with_a_line_break_and_a_real_link_renders_correctly(
    tmp_path: Path,
) -> None:
    """copyright_text is a real HTML fragment (see prodockit.pdf.build's own
    docs, and prodockit.pdf.css's module docstring, for why): a real <br>
    forces a line break, and a real <a href="..."> renders as a real,
    clickable link in the PDF, on every page it appears on - not just the
    one page the source element itself physically sits on (CSS Paged
    Media's position: running()/content: element(), confirmed directly
    against real WeasyPrint output). Confirmed here with a real weasyprint
    build across two pages, since a CSS-string-level test can't tell the
    difference between "renders as a space"/"flattened to plain text" and
    a real line break/real link annotation - only a real render can."""
    pymupdf = pytest.importorskip("pymupdf")

    pages = [
        Page(docs_rel_path="chapter1.md", html="<h1>Chapter One</h1><p>Body</p>"),
        Page(docs_rel_path="chapter2.md", html="<h1>Chapter Two</h1><p>Body</p>"),
    ]
    output_path = tmp_path / "out.pdf"

    build_pdf(
        pages,
        str(output_path),
        copyright_text=(
            'Copyright test.<br>Made with <a href="https://zensical.org/">Zensical</a>'
            ' and <a href="https://buckwem.github.io/prodockit-extensions/">prodockit</a>.'
        ),
        site_name="Test Site",
    )

    # The very first page (the auto-generated Table of Contents, @page
    # :first) always suppresses the copyright footer regardless - only
    # real chapter pages (identified by their own "Body" text) are checked.
    doc = pymupdf.open(str(output_path))
    chapter_pages = [page for page in doc if "Body" in page.get_text()]
    assert len(chapter_pages) == 2
    for page in chapter_pages:
        footer_text = page.get_text()
        assert "Copyright test.\nMade with Zensical and prodockit." in footer_text
        links = {link.get("uri") for link in page.get_links()}
        assert "https://zensical.org/" in links
        assert "https://buckwem.github.io/prodockit-extensions/" in links
    doc.close()


@real_pandoc_and_weasyprint_required
@pytest.mark.parametrize(
    ("filler_html", "case"),
    [
        ("<p>An appendix page with no heading at all.</p>", "no h1"),
        (
            '<h1 class="unnumbered">Unnumbered</h1><p>Body.</p>',
            "unnumbered h1",
        ),
    ],
)
def test_an_appendix_page_without_a_numbered_h1_still_consumes_its_letter(
    tmp_path: Path, filler_html: str, case: str
) -> None:
    """Regression test (#104): appendix letters are assigned per *page* that
    sets is_appendix - the same rule the website's own lettering uses
    (prodockit._zensical.prescan_headings) - so a page contributing no
    numbered h1 still consumes its letter and later appendixes stay in step.

    The Lua filter used to count appendix headings itself, so such a page
    gave it nothing to count and every later appendix came out one letter
    early: reproduced against prodockit-template, the same Bibliography page
    rendered as "Appendix E" on the website but "Appendix D" in the PDF.
    Both triggers are covered - a page with no h1, and one whose h1 is
    explicitly unnumbered (which the filter skips outright)."""
    pymupdf = pytest.importorskip("pymupdf")

    pages = [
        Page(docs_rel_path="chapter1.md", html="<h1>Chapter One</h1><p>Body</p>"),
        Page(docs_rel_path="acronyms.md", html="<h1>Acronyms</h1>", is_appendix=True),
        Page(docs_rel_path="filler.md", html=filler_html, is_appendix=True),
        Page(docs_rel_path="references.md", html="<h1>References</h1>", is_appendix=True),
    ]
    output_path = tmp_path / "out.pdf"

    build_pdf(pages, str(output_path), site_name="Test Site")

    doc = pymupdf.open(str(output_path))
    try:
        text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()

    assert "Appendix A. Acronyms" in text
    # The filler page took B, whether or not it had a heading to show it on.
    assert "Appendix C. References" in text, (
        f"With an appendix page having {case}, References should still be "
        "lettered C - counting appendix headings rather than appendix pages "
        "brings it out as B and desynchronises the PDF from the website (#104)"
    )


def test_pandoc_is_invoked_with_wrap_none(tmp_path: Path, fake_pandoc_on_path) -> None:
    """Regression test (#101): pandoc's HTML writer hard-wraps its output at
    ~72 columns by default, inserting newlines inside elements. They're
    insignificant whitespace in HTML, but WeasyPrint's float: footnote width
    computation treats them as hard break opportunities when sizing the
    footnote area - collapsing a footnote's rendered text to roughly the
    longest source line instead of the page's content width. --wrap=none is
    what stops that; see the .pdf-footnote rule in prodockit.pdf.css.
    Asserted at the command level too (not just via the real-render test
    below) so the flag can't be dropped silently where pandoc isn't
    installed."""
    args_path = tmp_path / "args.txt"
    fake_pandoc_on_path(f'echo "$@" > "{args_path}"; echo "%PDF-1.4 stub" > "$3"')

    build_pdf(
        [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
        str(tmp_path / "out.pdf"),
    )

    assert "--wrap=none" in args_path.read_text(encoding="utf-8").split()


@real_pandoc_and_weasyprint_required
def test_footnote_text_renders_at_the_page_content_width(tmp_path: Path) -> None:
    """Regression test (#101): a footnote's own text must lay out across the
    page's full content width, not a narrow column. Before --wrap=none was
    passed to pandoc (see test_pandoc_is_invoked_with_wrap_none above), the
    newlines pandoc inserted inside the <span class="pdf-footnote"> collapsed
    the rendered text to ~304pt of the ~482pt content width, wrapping a
    footnote onto five short lines whose first held just two words.

    Only a real render catches this: the CSS is identical either way (the
    rule deliberately sets no width, and a width override is silently ignored
    for floated footnote content), so nothing short of measuring the laid-out
    text can tell the two apart."""
    pymupdf = pytest.importorskip("pymupdf")

    footnote_text = (
        "This is a deliberately long footnote whose rendered line width is "
        "measured against the page content width to prove it is not being "
        "collapsed into a narrow column by pandoc's own source wrapping."
    )
    output_path = tmp_path / "out.pdf"

    build_pdf(
        [
            Page(
                docs_rel_path="chapter1.md",
                html=(
                    "<h1>Chapter One</h1><p>Body with a footnote."
                    f'<span class="pdf-footnote">{footnote_text}</span></p>'
                ),
            )
        ],
        str(output_path),
        site_name="Test Site",
    )

    doc = pymupdf.open(str(output_path))
    try:
        # A4 at the default 2cm margins: 595pt - 2 * 56.7pt of margin.
        content_width = 595 - 2 * 56.7
        # The footnote is the only 9pt text in the document - the header/
        # footer margin boxes are 10pt, body text larger still.
        widest = 0.0
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        if span["text"].strip() and 8.5 < span["size"] < 9.5:
                            x0, _, x1, _ = span["bbox"]
                            widest = max(widest, x1 - x0)
        assert widest > 0, "Expected to find the 9pt footnote text in the PDF"
        assert widest > content_width * 0.9, (
            f"Footnote text laid out {widest:.0f}pt wide, well short of the "
            f"{content_width:.0f}pt content width - pandoc's source wrapping "
            "has most likely crept back in (see #101)"
        )
    finally:
        doc.close()


# --- Unrendered Mermaid/maths warnings -------------------------------------
#
# Both renderers are optional and both fall back to leaving the content
# untouched rather than failing the build. That silence is how raw
# `flowchart LR ...` source and literal LaTeX reached published PDFs in
# three separate projects, so the degradation is now announced.

_MERMAID_PAGE = Page(
    docs_rel_path="diagrams.md",
    html='<p>Before</p><pre class="mermaid">flowchart LR\n  A --&gt; B</pre>',
)
_MATHS_PAGE = Page(
    docs_rel_path="maths.md",
    html='<p>Before</p><div class="arithmatex">\\[ x^2 \\]</div>',
)


def test_warns_when_a_mermaid_diagram_has_no_renderer(
    tmp_path: Path, fake_pandoc_on_path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf([_MERMAID_PAGE], str(tmp_path / "out.pdf"))
    out = capsys.readouterr().out
    assert "contains Mermaid diagrams" in out
    assert "prodockit init-tools" in out, (
        "the warning should name the fix, not just the symptom"
    )


def test_warns_when_maths_has_no_renderer(
    tmp_path: Path, fake_pandoc_on_path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf([_MATHS_PAGE], str(tmp_path / "out.pdf"))
    out = capsys.readouterr().out
    assert "contains TeX maths" in out
    assert "prodockit init-tools" in out


def test_does_not_warn_when_the_renderers_are_available(
    tmp_path: Path, fake_pandoc_on_path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [_MERMAID_PAGE, _MATHS_PAGE],
        str(tmp_path / "out.pdf"),
        render_mermaid=lambda source: None,
        mathjax_available=True,
    )
    out = capsys.readouterr().out
    assert "⚠️" not in out


def test_does_not_warn_when_the_document_uses_neither(
    tmp_path: Path, fake_pandoc_on_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The common case - a project using neither feature must not be nagged
    about tooling it has no reason to install. Prose that merely mentions
    the words must not trigger it either."""
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [
            Page(
                docs_rel_path="index.md",
                html="<h1>Report</h1><p>We considered mermaid diagrams and "
                "arithmatex maths, but used neither.</p>",
                is_index=True,
            )
        ],
        str(tmp_path / "out.pdf"),
    )
    assert "⚠️" not in capsys.readouterr().out


#: A page documenting either renderer, as this project's own
#: `devcons/limitations.md` does: the markup is quoted in a code span, so
#: Python-Markdown has escaped `<` and `>` and left the attribute text
#: alone. Byte-for-byte the shape that reached the built site, not an
#: invented approximation - the escaped angle brackets are the whole point.
_DOCUMENTS_THE_RENDERERS_PAGE = Page(
    docs_rel_path="limitations.md",
    html=(
        '<p>Generic-mode math (<code>&lt;div class="arithmatex"&gt;</code>/'
        '<code>&lt;span class="arithmatex"&gt;</code>) has no native Math AST node.</p>'
        '<p>Each <code>&lt;pre class="mermaid"&gt;</code> fence is pre-rendered to SVG.</p>'
    ),
)


def test_does_not_warn_about_prose_quoting_the_renderers_own_markup(
    tmp_path: Path, fake_pandoc_on_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A page that *documents* Mermaid or maths handling must not be
    mistaken for one that *uses* it.

    Sharper than the "uses neither" case above, which only mentions the
    words in prose: here the page quotes the real markup, so the raw HTML
    genuinely contains `class="arithmatex"` and `class="mermaid"` - just
    inside a code span, with the `<` escaped to `&lt;`.

    This is a regression test with a real regression behind it (#176).
    `_ARITHMATEX_RE` matched the bare `class="..."` and so fired on this
    project's own `devcons/limitations.md`, warning that a document with no
    formulas in it would ship raw LaTeX. `_MERMAID_BLOCK_RE` was already
    anchored on `<pre` and never had the problem, which is why only maths
    is named in that issue - both are asserted here so the two cannot drift
    apart again.
    """
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf([_DOCUMENTS_THE_RENDERERS_PAGE], str(tmp_path / "out.pdf"))
    assert "⚠️" not in capsys.readouterr().out


def test_still_warns_when_real_maths_sits_beside_prose_quoting_the_markup(
    tmp_path: Path, fake_pandoc_on_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of the check above, and the one that makes it worth
    having: narrowing the pattern must not have disabled the warning.

    A page can legitimately be both - documenting the markup *and* using a
    formula - and the escaped prose must not mask the real thing. Without
    this, emptying `_ARITHMATEX_RE` entirely would leave the test above
    passing.
    """
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf([_DOCUMENTS_THE_RENDERERS_PAGE, _MATHS_PAGE], str(tmp_path / "out.pdf"))
    assert "contains TeX maths" in capsys.readouterr().out


def test_warns_about_inline_maths_not_only_display_maths(
    tmp_path: Path, fake_pandoc_on_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_MATHS_PAGE` above is a `<div>` (display maths). Inline maths is a
    `<span>`, and the pattern now names both elements explicitly rather
    than matching any tag, so the span case needs its own assertion -
    confirmed against real `pymdownx.arithmatex` generic-mode output, which
    emits exactly these two wrappers and no others.
    """
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [
            Page(
                docs_rel_path="inline.md",
                html='<p>Where <span class="arithmatex">\\(x^2\\)</span> holds.</p>',
            )
        ],
        str(tmp_path / "out.pdf"),
    )
    assert "contains TeX maths" in capsys.readouterr().out


def test_warns_about_both_independently(
    tmp_path: Path, fake_pandoc_on_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only the missing one is reported when the other is available."""
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    build_pdf(
        [_MERMAID_PAGE, _MATHS_PAGE],
        str(tmp_path / "out.pdf"),
        mathjax_available=True,
    )
    out = capsys.readouterr().out
    assert "contains Mermaid diagrams" in out
    assert "contains TeX maths" not in out


def test_index_title_heading_carries_the_running_header_class(
    tmp_path: Path, fake_pandoc_on_path
) -> None:
    """`unnumbered` keeps this heading out of the numbering, but it is also
    what stops it feeding the running header - hence the second class (see
    prodockit.pdf.index.INDEX_TITLE_CLASS).

    No `unlisted`: that class is what kept the index out of the Table of
    Contents, and it was dropped deliberately in #141. Asserted as an exact
    string so a change to either class has to be a decision rather than a
    side effect - which is how this test caught #141's change."""
    fake_pandoc_on_path(_fake_pandoc_building_a_real_pdf(tmp_path))
    work_dir = tmp_path / "work"

    build_pdf(
        [Page(docs_rel_path="c1.md", html='<h1>One</h1><span class="index">Widget</span>')],
        str(tmp_path / "out.pdf"),
        include_index=True,
        index_title="Index",
        work_dir=str(work_dir),
        keep_work_dir=True,
    )

    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")
    assert f'<h1 class="unnumbered {INDEX_TITLE_CLASS}">Index</h1>' in compiled


@real_pandoc_and_weasyprint_required
def test_the_index_pages_are_headed_by_the_index_title_not_the_last_chapter(
    tmp_path: Path,
) -> None:
    """The index is always the last thing in the document, so before
    INDEX_TITLE_CLASS existed the running header still held whatever
    chapter came last - this project's own PDF was headed "18. License"
    across its whole index. Only a real render answers this: the header is
    a CSS Paged Media margin box fed by `string-set`, which the
    fake-pandoc stub never evaluates."""
    long_para = "<p>" + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 40) + "</p>"
    pages = [
        Page(docs_rel_path="index.md", html="<h1>Cover</h1>", is_index=True),
        Page(
            docs_rel_path="chapter1.md",
            html=f'<h1>Chapter One</h1>{long_para}<span class="index">Widget</span>{long_para}',
        ),
        Page(
            docs_rel_path="lastchapter.md",
            html=f'<h1>Zebra Chapter</h1>{long_para}<span class="index">Gadget</span>{long_para}',
        ),
    ]
    output_path = tmp_path / "out.pdf"

    build_pdf(pages, str(output_path), include_index=True, index_title="Index")

    doc = pymupdf.open(str(output_path))
    try:
        index_pages = [
            i for i, page in enumerate(doc) if page.get_text().strip().startswith("Index")
        ]
        assert index_pages, "no Index page found in the built PDF"
        # The header is a margin box, so read it by position: everything
        # above the 2cm top margin is header, not body.
        top_margin_pt = 2 / 2.54 * 72
        for page_number in index_pages:
            header = " ".join(
                block[4]
                for block in doc[page_number].get_text("blocks")
                if block[3] < top_margin_pt
            )
            assert "Index" in header, (
                f"page {page_number + 1}'s running header is {header!r} - expected the index title"
            )
            assert "Zebra Chapter" not in header, (
                f"page {page_number + 1} is still headed by the last chapter: {header!r}"
            )
    finally:
        doc.close()


@real_pandoc_and_weasyprint_required
def test_a_long_index_term_stays_inside_its_own_column(tmp_path: Path) -> None:
    """A term with no space to wrap at used to overflow its column box
    rather than break: it ran over the column rule into the next column's
    entries, and off the page edge entirely from the right-hand column.
    Measured geometrically, because it renders as perfectly ordinary text
    either way - only its position gives it away.

    One entry, so the whole index sits in the left column; every glyph
    must therefore stay left of the column rule, which runs down the
    middle of the content box.
    """
    term = "assert_no_unrendered_mermaid_diagram_pages(page_texts)"
    pages = [
        Page(docs_rel_path="index.md", html="<h1>Cover</h1>", is_index=True),
        Page(
            docs_rel_path="chapter1.md",
            html=(
                "<h1>Chapter One</h1><p>see "
                '<span class="index" data-index-code="true" '
                f'data-index-term="prodockit.testing!checks!{term}"><code>{term}</code></span>'
                " here</p>"
            ),
        ),
    ]
    output_path = tmp_path / "out.pdf"

    build_pdf(pages, str(output_path), include_index=True)

    doc = pymupdf.open(str(output_path))
    try:
        index_page = next(
            i for i, page in enumerate(doc) if page.get_text().strip().startswith("Index")
        )
        page = doc[index_page]
        margin_pt = 2 / 2.54 * 72
        column_rule_x = margin_pt + (page.rect.width - 2 * margin_pt) / 2
        # Body only - the running header/footer legitimately span the full
        # content width.
        overflowing = [
            (word[4], round(word[2], 1))
            for word in page.get_text("words")
            if margin_pt < word[1] < page.rect.height - margin_pt and word[2] > column_rule_x
        ]
        assert not overflowing, (
            f"index entries crossed the column rule at x={column_rule_x:.1f}: {overflowing}"
        )
    finally:
        doc.close()


@real_pandoc_and_weasyprint_required
def test_a_two_line_footer_clears_the_paper_edge(tmp_path: Path) -> None:
    """prodockit-extensions#139: the running footer is top-aligned in the
    bottom margin and grows *downward* as it gains lines, so a second line
    eats into the space left before the paper edge rather than pushing the
    footer up.

    This project's own footer is two lines - a copyright line and a "Made
    with" credit - and at the old 2cm default it ended 6.1mm from the edge.
    Consumer and office printers commonly cannot print within 5-6.4mm, so
    the second line was at real risk of being cropped: the PDF was correct
    and the paper was not.

    Measured on a real render rather than asserted about the CSS, because
    the margin only reserves the space - whether the footer actually fits
    inside it depends on how the text lays out.
    """
    long_para = "<p>" + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 40) + "</p>"
    pages = [
        Page(docs_rel_path="index.md", html="<h1>Cover</h1>", is_index=True),
        Page(docs_rel_path="chapter1.md", html=f"<h1>Chapter One</h1>{long_para}"),
    ]
    output_path = tmp_path / "out.pdf"

    build_pdf(
        pages,
        str(output_path),
        copyright_text="Copyright © 2026 Example.<br>Made with Zensical and prodockit.",
    )

    doc = pymupdf.open(str(output_path))
    try:
        # A body page, not the cover - @page :first blanks the footer.
        page = doc[1]
        lowest = max(block[3] for block in page.get_text("blocks"))
        clearance_mm = (page.rect.height - lowest) / 72 * 25.4
        assert clearance_mm >= 8.0, (
            f"the two-line footer ends {clearance_mm:.1f}mm from the paper edge - "
            "inside the range many printers cannot print, so it risks being cropped"
        )
    finally:
        doc.close()


def test_index_title_is_listed_in_the_contents(tmp_path: Path, fake_pandoc_on_path) -> None:
    """prodockit-extensions#141: the index heading carried Pandoc's
    `unlisted` class, which is what
    `pandoc.structure.table_of_contents()` honours - so the generated
    index never appeared in the Table of Contents. An index is a section a
    reader goes looking for; it belongs there.

    Still `unnumbered`, so it takes no chapter number."""
    fake_pandoc_on_path(_fake_pandoc_building_a_real_pdf(tmp_path))
    work_dir = tmp_path / "work"

    build_pdf(
        [Page(docs_rel_path="c1.md", html='<h1>One</h1><span class="index">Widget</span>')],
        str(tmp_path / "out.pdf"),
        include_index=True,
        index_title="Index",
        work_dir=str(work_dir),
        keep_work_dir=True,
    )

    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")

    assert f'<h1 class="unnumbered {INDEX_TITLE_CLASS}">Index</h1>' in compiled
    assert "unlisted" not in compiled.split("Index</h1>")[0].split("<h1")[-1]


def test_the_contents_heading_itself_stays_unlisted(tmp_path: Path, fake_pandoc_on_path) -> None:
    """A contents listing itself is noise - only the index changed."""
    fake_pandoc_on_path('echo "%PDF-1.4 stub" > "$3"')
    work_dir = tmp_path / "work"

    build_pdf(
        [Page(docs_rel_path="c1.md", html="<h1>One</h1>")],
        str(tmp_path / "out.pdf"),
        table_of_contents_title="Table of Contents",
        work_dir=str(work_dir),
        keep_work_dir=True,
    )

    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")

    assert '<h1 class="unnumbered unlisted">Table of Contents</h1>' in compiled


def test_index_letter_headings_stay_unlisted(tmp_path: Path, fake_pandoc_on_path) -> None:
    """The A/B/C separators inside the index must not become contents
    entries, or the listing fills with single letters."""
    fake_pandoc_on_path(_fake_pandoc_building_a_real_pdf(tmp_path))
    work_dir = tmp_path / "work"

    build_pdf(
        [
            Page(docs_rel_path="c1.md", html='<h1>One</h1><span class="index">Widget</span>'),
            Page(docs_rel_path="c2.md", html='<span class="index">Gadget</span>'),
        ],
        str(tmp_path / "out.pdf"),
        include_index=True,
        work_dir=str(work_dir),
        keep_work_dir=True,
    )

    compiled = (work_dir / "_prodockit_pdf_compiled.html").read_text(encoding="utf-8")

    assert '<h2 class="prodockit-index-letter unnumbered unlisted">' in compiled


@real_pandoc_and_weasyprint_required
def test_autoref_renders_the_targets_real_page_number(tmp_path: Path) -> None:
    """prodockit-extensions#151: `\\ref{}` gives a section number, which is
    no help to someone holding a printout - there is nothing to turn to.
    `\\autoref{}` renders the heading's name and the PDF stylesheet appends
    its page number via CSS `target-counter()`.

    Only a real render can check this: the number does not exist until
    WeasyPrint has laid the document out, and the risk is not that the
    suffix is missing but that it resolves to nothing and prints "on page"
    followed by a blank - which is what an unresolvable anchor does.

    The target is deliberately *not* its page's first heading, whose id
    `fix_up_page_html()` replaces with the page's own anchor.
    """
    filler = "<p>" + ("Lorem ipsum dolor sit amet. " * 90) + "</p>"
    pages = [
        Page(
            docs_rel_path="chapter1.md",
            html=(
                '<h1>Chapter One</h1><p>See '
                '<a class="prodockit-autoref" href="#deep">Deep Section</a> here.</p>'
                f"{filler}"
            ),
        ),
        Page(
            docs_rel_path="chapter2.md",
            html=f'<h1>Chapter Two</h1>{filler}<h2 id="deep">Deep Section</h2><p>here</p>',
        ),
    ]
    output_path = tmp_path / "out.pdf"

    # No contents page: it lists "Deep Section" too, and would be found
    # before the heading itself when locating the target below.
    build_pdf(pages, str(output_path), include_table_of_contents=False)

    doc = pymupdf.open(str(output_path))
    try:
        reference = next(
            (line for page in doc for line in page.get_text().split("\n") if "See Deep" in line),
            "",
        )
        # The heading carries its section number by the time it is rendered
        # ("2.1 Deep Section"), so match on the text rather than the start of
        # the block, and exclude the block holding the reference itself.
        heading_page = next(
            i + 1
            for i, page in enumerate(doc)
            for block in page.get_text("blocks")
            if "Deep Section" in block[4] and "See Deep" not in block[4]
        )
        assert f"on page {heading_page}" in reference, (
            f"reference reads {reference.strip()!r} but the target heading is on "
            f"page {heading_page}"
        )
    finally:
        doc.close()


@real_pandoc_and_weasyprint_required
def test_a_reference_to_a_page_title_heading_resolves_in_the_pdf(tmp_path: Path) -> None:
    """prodockit-extensions#163: the page anchor used to replace the first
    heading's id, so a reference to a page's *title* heading pointed at an
    anchor that no longer existed.

    Asserted on the PDF's own named destinations and on the rendered page
    number, not on the text: the reference still rendered its text while
    broken, and `\\autoref` printed "on page" followed by a blank - so an
    assertion that the output *contains* "on page" would have passed
    against the bug.
    """
    filler = "<p>" + ("Lorem ipsum dolor sit amet. " * 90) + "</p>"
    pages = [
        Page(
            docs_rel_path="chapter1.md",
            html=(
                "<h1>Chapter One</h1>"
                '<p>Title: <a class="prodockit-autoref" href="#chapter-two">2 Chapter Two</a>.</p>'
                f"{filler}"
            ),
        ),
        Page(
            docs_rel_path="chapter2.md",
            html=f'<h1 id="chapter-two">Chapter Two</h1>{filler}<h2 id="deep">Deep</h2><p>x</p>',
        ),
    ]
    output_path = tmp_path / "out.pdf"

    build_pdf(pages, str(output_path), include_table_of_contents=False)

    doc = pymupdf.open(str(output_path))
    try:
        names = doc.resolve_names()
        # Both anchors: the heading's own, and the page's - a cross-page
        # link with no fragment still needs the latter.
        assert "chapter-two" in names, "the title heading's own anchor is missing from the PDF"
        assert "page-chapter2" in names, "the page's own anchor is missing from the PDF"

        target_page = names["chapter-two"]["page"] + 1
        reference = next(
            (line for page in doc for line in page.get_text().split("\n") if "Title:" in line),
            "",
        )
        assert f"on page {target_page}" in reference, (
            f"reference reads {reference.strip()!r} but the title heading's anchor "
            f"is on page {target_page}"
        )
    finally:
        doc.close()


@real_pandoc_and_weasyprint_required
def test_a_rotated_table_page_is_displayed_landscape(tmp_path: Path) -> None:
    """prodockit-extensions#469, measured on the finished PDF.

    The stub-level tests above only prove which post-process ran. This
    one asks what a reader would actually show, because that is the
    thing that was wrong: the page box was landscape all along, and the
    `/Rotate` flag turned it back to portrait on screen.

    `page.rect` is the displayed rectangle - pymupdf applies `/Rotate`
    for us - so this compares what a reader draws, not what the file
    stores.
    """
    import pymupdf

    rows = "".join(f"<tr><td>Row {i}</td><td>{'wide ' * 12}</td></tr>" for i in range(6))
    html = (
        "<h1>Report</h1><p>Portrait text.</p>"
        '<div class="landscape-page"><table>'
        "<thead><tr><th>Name</th><th>Detail</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        "<p>More portrait text.</p>"
    )

    out = tmp_path / "rotated.pdf"
    build_pdf([Page(docs_rel_path="index.md", html=html, is_index=True)], str(out))
    with pymupdf.open(str(out)) as pdf:
        shapes = [
            "landscape" if page.rect.width > page.rect.height else "portrait"
            for page in pdf
        ]

    assert "landscape" in shapes, f"the table page should display landscape: {shapes}"
    # And only that page - the document either side of it is untouched.
    assert shapes[0] == "portrait" and shapes[-1] == "portrait"


@real_pandoc_and_weasyprint_required
def test_landscape_content_carries_on_across_pages(tmp_path: Path) -> None:
    """A `landscape-page` block is not limited to one page, and is not
    limited to tables.

    This is what a CSS `transform: rotate()` could not do, and the reason
    the block is diverted onto a landscape *page* instead: a rotated box
    clipped to a single page and pushed its own heading row off-page.
    Here a long table should simply paginate, repeating its header the
    way any table does, and a diagram should get a landscape page of its
    own - with the portrait document either side untouched.
    """
    import pymupdf as fitz

    rows = "".join(
        f"<tr><td>Row {i}</td><td>{'detail ' * 14}</td></tr>" for i in range(1, 90)
    )
    diagram = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='900' height='1400'>"
        "<rect width='900' height='1400' fill='%23cccccc'/></svg>"
    )
    html = (
        "<h1>Report</h1><p>Portrait before.</p>"
        '<div class="landscape-page"><table>'
        "<thead><tr><th>Name</th><th>Detail</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        "<p>Portrait between.</p>"
        f'<div class="landscape-page"><img src="data:image/svg+xml;utf8,{diagram}"'
        ' style="width:100%"></div>'
        "<p>Portrait after.</p>"
    )

    output_path = tmp_path / "wide.pdf"
    build_pdf([Page(docs_rel_path="index.md", html=html, is_index=True)], str(output_path))

    with fitz.open(str(output_path)) as pdf:
        shapes = [
            ("landscape" if page.rect.width > page.rect.height else "portrait")
            for page in pdf
        ]
        text = [page.get_text() for page in pdf]

    landscape = [i for i, shape in enumerate(shapes) if shape == "landscape"]
    # Pages the table's *body* reached, found from its rows rather than
    # from its header - using the header to find the pages and then
    # checking the header is on them would pass however few there were.
    table_pages = [i for i, page in enumerate(text) if "Row " in page]

    assert len(table_pages) >= 3, f"the table should span several pages: {shapes}"
    assert all(shapes[i] == "landscape" for i in table_pages), shapes
    # Consecutive - the table's pages are not interleaved with others.
    assert table_pages == list(range(table_pages[0], table_pages[-1] + 1))
    # The heading row repeats on *every* one of them: the likely case for
    # this class, and the thing a rotated box lost.
    missing = [i for i in table_pages if "Name" not in text[i]]
    assert not missing, f"heading row missing from pages {missing} of {table_pages}"
    # A diagram gets a landscape page of its own, and it is not the table's.
    assert set(landscape) - set(table_pages), f"the diagram got no landscape page: {shapes}"
    assert shapes[0] == "portrait" and shapes[-1] == "portrait"


def _png_data_uri(width: int, height: int) -> str:
    """A real raster image of a given size, as a data: URI.

    Raster rather than SVG: WeasyPrint draws a data-URI SVG as vectors,
    which `get_images()` does not report, so an SVG would measure
    nothing at all.
    """
    import base64

    import pymupdf as fitz

    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height))
    pix.set_rect(pix.irect, (60, 110, 200))
    return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()


def _drawn_width(pdf_path: str) -> float:
    """How wide the first image is actually drawn, in points."""
    import pymupdf as fitz

    with fitz.open(pdf_path) as pdf:
        for page in pdf:
            for xref in page.get_images(full=True):
                for rect in page.get_image_rects(xref[0]):
                    return rect.width
    raise AssertionError("no image found in the PDF")


@real_pandoc_and_weasyprint_required
def test_an_image_wider_than_the_text_column_is_held_to_the_page(
    tmp_path: Path,
) -> None:
    """A screenshot must not be drawn off the edge of the paper.

    The website gets this from its theme's own `img { max-width: 100% }`.
    The PDF stylesheet had no equivalent - the comment in
    prodockit.pdf.html that reasons about "a generic img { max-width:
    100% } rule elsewhere in the same stylesheet" was describing a rule
    that was not there. So a 1600px screenshot was drawn 1200pt wide on a
    595pt page, most of it past the trim edge
    (prodockit-extensions#480).

    Measured against the *text column*, not the paper: an image is held
    to the width of the content it sits in, which is what a reader means
    by "fits".
    """
    output_path = tmp_path / "wide-image.pdf"
    html = f'<h1>Report</h1><p>Before.</p><img src="{_png_data_uri(1600, 600)}"><p>After.</p>'
    build_pdf([Page(docs_rel_path="page.md", html=html, is_index=False)], str(output_path))

    import pymupdf as fitz

    with fitz.open(str(output_path)) as pdf:
        page_width = pdf[0].rect.width

    drawn = _drawn_width(str(output_path))
    # The A4 page is 595pt and the margins take 2cm a side, leaving about
    # 470pt of column. Asserting against the page is the weaker check and
    # the one that still catches running off the paper.
    assert drawn <= page_width, (
        f"image drawn {drawn:.0f}pt wide on a {page_width:.0f}pt page - off the paper"
    )
    assert drawn <= 480, f"image drawn {drawn:.0f}pt, wider than the ~470pt text column"


@real_pandoc_and_weasyprint_required
def test_a_percentage_width_scales_the_image(tmp_path: Path) -> None:
    """`{ width="50%" }` on an image is honoured in the PDF.

    HTML's `width` attribute is defined in pixels, and a percentage in it
    is a legacy browser behaviour rather than a specified one - so it is
    worth holding, since the same markdown works on the website and a
    silent difference between the two outputs is the failure this project
    keeps meeting (prodockit-extensions#480).

    Both spellings are checked together: the attribute the markdown
    produces, and the inline style it is equivalent to. They must agree,
    which a single-case test could not show.
    """
    src = _png_data_uri(1600, 600)
    widths = {}
    for label, tag in (
        ("attribute", f'<img src="{src}" width="50%" class="screenshot pdf-only">'),
        ("inline style", f'<img src="{src}" style="width:50%">'),
        ("no width", f'<img src="{src}">'),
    ):
        out = tmp_path / f"{label.replace(' ', '-')}.pdf"
        build_pdf(
            [Page(docs_rel_path="page.md", html=f"<h1>H</h1><p>x</p>{tag}<p>y</p>", is_index=False)],
            str(out),
        )
        widths[label] = _drawn_width(str(out))

    # Half the text column, not half the paper - and the two spellings
    # land in the same place.
    assert abs(widths["attribute"] - widths["inline style"]) < 2, widths
    assert 200 <= widths["attribute"] <= 260, widths
    # And it is a real reduction from the unconstrained image, so the
    # assertion cannot pass on an image that was never scaled at all.
    assert widths["attribute"] < widths["no width"] - 100, widths


@real_pandoc_and_weasyprint_required
def test_every_announced_stage_still_has_work_left_to_do(tmp_path: Path) -> None:
    """A stage must not be announced once the PDF is already written.

    The regression this guards is not a wrong count but a false one:
    #469 removed the landscape-page rotation and left its stage title
    behind, announced as the last statement before cleanup with nothing
    between. Every build reported "[4/4] Rotating landscape pages" and
    then rotated nothing, so a three-stage build called itself four
    (prodockit-extensions#482).

    Asserting the titles alone would not have caught it - the list was
    self-consistent, and the count matched the number announced. What
    separates a real stage from a leftover is whether anything happens
    afterwards, so that is what is measured: at the moment each stage is
    announced, the output file must not exist yet.
    """
    output_path = tmp_path / "staged.pdf"
    seen: list[tuple[str, bool]] = []

    def record(number: int, total: int, title: str) -> None:
        # Whether the finished PDF is already on disk when this stage
        # claims to be starting.
        seen.append((title, output_path.exists()))

    build_pdf(
        [Page(docs_rel_path="page.md", html="<h1>H</h1><p>Body.</p>", is_index=False)],
        str(output_path),
        on_stage=record,
    )

    assert seen, "the build announced no stages at all"
    finished = [title for title, done in seen if done]
    assert not finished, f"announced after the PDF was already written: {finished}"
    # And the announcements match what the build said it would do.
    from prodockit.pdf.build import _stage_titles

    assert [title for title, _ in seen] == _stage_titles(include_index=False)


@real_pandoc_and_weasyprint_required
def test_a_caption_does_not_narrow_the_figure_it_labels(tmp_path: Path) -> None:
    """Adding a caption must not shrink the picture.

    HTML's own default for <figure> is "margin: 1em 40px", which no
    website shows because every theme resets it. Nothing reset it here,
    so the same markdown filled the column on the site and came out 60pt
    narrower in the PDF - an image asking for width: 100% drawn at 410pt
    in a 470pt column, short of the margin on both sides while the
    paragraph above it ran the full width
    (prodockit-extensions#485).

    The comparison is the assertion: the two documents differ by a
    caption and nothing else, so any difference in width is the caption's
    doing. Asserting a figure's width on its own would have passed
    throughout, since 410pt looks perfectly reasonable until something
    beside it is 470.
    """
    src = _png_data_uri(1400, 900)
    widths = {}
    for label, frag in (
        ("captioned", f'<figure><p><img src="{src}" width="100%"></p>'
                      f"<figcaption><p>Figure 1. A diagram</p></figcaption></figure>"),
        ("uncaptioned", f'<p><img src="{src}" width="100%"></p>'),
    ):
        out = tmp_path / f"{label}.pdf"
        build_pdf(
            [Page(docs_rel_path="p.md", html=f"<h1>H</h1><p>text</p>{frag}<p>after</p>",
                  is_index=False)],
            str(out),
        )
        widths[label] = _drawn_width(str(out))

    assert abs(widths["captioned"] - widths["uncaptioned"]) < 2, (
        f"the caption cost the figure {widths['uncaptioned'] - widths['captioned']:.0f}pt "
        f"of width: {widths}"
    )
    # And it really is the full column, not two equally narrow figures -
    # which is what the comparison alone would allow.
    assert widths["captioned"] > 460, widths


@real_pandoc_and_weasyprint_required
def test_a_caption_does_not_narrow_the_table_it_labels(tmp_path: Path) -> None:
    """The same default margin reaches a captioned table.

    `figure.prodockit-table-caption` is a <figure>, so a table with a
    caption was inset by the same 60pt while a table without one was not
    (prodockit-extensions#485) - the same bug wearing different content,
    which is why it is checked separately rather than assumed to follow.
    """
    # Long enough that the table genuinely wants the whole column: with
    # short cells both versions fit comfortably and measure the same,
    # which is how the first draft of this test passed with the bug
    # still in place.
    rows = "".join(f"<tr><td>Row {i}</td><td>{'detail ' * 30}</td></tr>" for i in range(1, 4))
    table = (
        "<table><thead><tr><th>Name</th><th>Detail</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
    import pymupdf as fitz

    spans = {}
    for label, frag in (
        ("captioned",
         f'<figure class="prodockit-table-caption">{table}'
         "<figcaption><p>Table 1. Rows</p></figcaption></figure>"),
        ("uncaptioned", table),
    ):
        out = tmp_path / f"table-{label}.pdf"
        build_pdf(
            [Page(docs_rel_path="p.md", html=f"<h1>H</h1><p>text</p>{frag}", is_index=False)],
            str(out),
        )
        with fitz.open(str(out)) as pdf:
            # The row text, which spans the table's own width. Every page,
            # since a long table paginates.
            hits = [r for page in pdf for r in page.search_for("detail")]
            assert hits, f"no table rows found in the {label} PDF"
            spans[label] = max(r.x1 for r in hits) - min(r.x0 for r in hits)

    assert abs(spans["captioned"] - spans["uncaptioned"]) < 4, (
        f"the caption narrowed the table: {spans}"
    )
