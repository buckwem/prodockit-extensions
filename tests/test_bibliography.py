# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import shutil
from pathlib import Path

import markdown
import pytest

import prodockit.bibliography as prodockit_bibliography
from prodockit.bibliography import BibliographyError, BibliographyExtension
from prodockit.citations import CitationsExtension

pandoc_required = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="prodockit.bibliography's citation/bibliography formatting is delegated "
    "entirely to `pandoc --citeproc` - these tests need a real pandoc install.",
)

BIB_FIXTURE = """
@book{chacon2014,
  author = {Chacon, Scott and Straub, Ben},
  title = {Pro Git},
  year = {2014},
  publisher = {Apress}
}

@book{skou2023,
  author = {Skoulikari, Angela},
  title = {Learning Git},
  year = {2023},
  publisher = {O'Reilly Media}
}
"""


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets a fresh module-level cache, so tests can't leak
    resolved citations/bibliography HTML into one another via the real
    process-lifetime singleton (in production, deliberately shared for the
    whole build's lifetime)."""
    monkeypatch.setattr(prodockit_bibliography, "_ZENSICAL_SHARED_CACHES", {})


@pytest.fixture()
def bib_file(tmp_path: Path) -> str:
    path = tmp_path / "refs.bib"
    path.write_text(BIB_FIXTURE, encoding="utf-8")
    return str(path)


def _convert(text: str, bib_file: str, **kwargs: object) -> str:
    ext = BibliographyExtension(bib_file=bib_file, source="doc.md", **kwargs)
    return markdown.markdown(text, extensions=[ext])


def test_multi_key_citation_is_not_matched(bib_file: str) -> None:
    """\\citebib{id1,id2} isn't supported (see module docstring) - falls
    through as literal text rather than being silently mishandled."""
    html = _convert("See \\citebib{chacon2014,skou2023}.", bib_file)
    assert "\\citebib{chacon2014,skou2023}" in html


def test_the_old_bare_cite_syntax_no_longer_resolves(bib_file: str) -> None:
    """Regression test: prodockit.bibliography used to also respond to
    plain \\cite{id} (the same syntax prodockit.citations uses), which
    made the two extensions conflict if both were enabled in the same
    build. Renamed to \\citebib{id} specifically so they no longer
    collide - a bare \\cite{id} now falls through as literal text here,
    same as any other unrecognised syntax."""
    html = _convert("See \\cite{chacon2014}.", bib_file)
    assert "\\cite{chacon2014}" in html
    assert "prodockit-bib-cite" not in html


@pandoc_required
def test_citations_and_bibliography_can_be_enabled_together(bib_file: str) -> None:
    """The whole point of \\citebib{id} being distinct from
    prodockit.citations' own \\cite{id}: both extensions can now be
    enabled in the same build without one hijacking the other's syntax -
    e.g. a project citing some sources via a hand-written data-cite-text
    paragraph and others via a shared .bib file, or (as here) a docs site
    demonstrating both features side by side."""
    md = markdown.Markdown(
        extensions=[
            "attr_list",
            CitationsExtension(),
            BibliographyExtension(bib_file=bib_file, source="doc.md"),
        ]
    )
    html = md.convert(
        'Skoulikari, A. (2023) *Learning Git*.\n'
        '{: #hand2023 .reference data-cite-text="Skoulikari, 2023" }\n\n'
        "See \\cite{hand2023} and \\citebib{chacon2014}.\n"
    )
    assert '<a class="prodockit-cite-resolved" href="#hand2023">Skoulikari, 2023</a>' in html
    assert 'class="prodockit-bib-cite"' in html
    assert "Chacon" in html


def test_run_pandoc_citeproc_includes_csl_only_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class _Result:
        returncode = 0
        stdout = "<p>ok</p>"
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> _Result:
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(prodockit_bibliography.shutil, "which", lambda _: "/usr/bin/pandoc")
    monkeypatch.setattr(prodockit_bibliography.subprocess, "run", fake_run)

    prodockit_bibliography._run_pandoc_citeproc("body", bib_files=["x.bib"], csl_style="apa.csl")
    assert "--csl=apa.csl" in captured["cmd"]
    assert "--bibliography=x.bib" in captured["cmd"]

    prodockit_bibliography._run_pandoc_citeproc("body", bib_files=["x.bib"], csl_style="")
    assert not any(c.startswith("--csl=") for c in captured["cmd"])


def test_run_pandoc_citeproc_merges_multiple_bibliography_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A citation may need to resolve against more than one distinct
    .bib file (see prodockit-extensions#89's per-marker file overrides) -
    Pandoc merges repeated --bibliography= flags natively."""
    captured: dict[str, object] = {}

    class _Result:
        returncode = 0
        stdout = "<p>ok</p>"
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> _Result:
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(prodockit_bibliography.shutil, "which", lambda _: "/usr/bin/pandoc")
    monkeypatch.setattr(prodockit_bibliography.subprocess, "run", fake_run)

    prodockit_bibliography._run_pandoc_citeproc(
        "body", bib_files=["a.bib", "b.bib"], csl_style=""
    )
    assert "--bibliography=a.bib" in captured["cmd"]
    assert "--bibliography=b.bib" in captured["cmd"]


def test_missing_pandoc_raises_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prodockit_bibliography.shutil, "which", lambda _: None)
    with pytest.raises(BibliographyError, match="pandoc not found"):
        prodockit_bibliography._run_pandoc_citeproc("body", bib_files=["x.bib"], csl_style="")


def test_pandoc_failure_raises_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(prodockit_bibliography.shutil, "which", lambda _: "/usr/bin/pandoc")
    monkeypatch.setattr(prodockit_bibliography.subprocess, "run", lambda *a, **k: _Result())
    with pytest.raises(BibliographyError, match="boom"):
        prodockit_bibliography._run_pandoc_citeproc("body", bib_files=["x.bib"], csl_style="")


@pandoc_required
def test_resolves_a_known_citation(bib_file: str) -> None:
    html = _convert("See \\citebib{chacon2014}.", bib_file)
    assert 'class="prodockit-bib-cite"' in html
    assert "Chacon" in html
    assert "2014" in html


@pandoc_required
def test_unknown_citation_renders_the_unresolved_marker(bib_file: str) -> None:
    html = _convert("See \\citebib{doesnotexist}.", bib_file)
    assert '<span class="prodockit-bib-cite prodockit-bib-cite-unresolved">?</span>' in html


@pandoc_required
def test_custom_unresolved_marker(bib_file: str) -> None:
    html = _convert("See \\citebib{doesnotexist}.", bib_file, unresolved="[MISSING]")
    assert ">[MISSING]</span>" in html


@pandoc_required
def test_same_page_citation_links_to_a_bare_fragment(bib_file: str) -> None:
    html = _convert("See \\citebib{chacon2014}.\n\n\\bibliography\n", bib_file)
    assert 'href="#ref-chacon2014"' in html


@pandoc_required
def test_unresolved_citation_has_no_link(bib_file: str) -> None:
    html = _convert("See \\citebib{doesnotexist}.\n\n\\bibliography\n", bib_file)
    assert "href" not in html.split("</span>")[0].split("<span")[-1]


@pandoc_required
def test_bibliography_marker_generates_the_full_list(bib_file: str) -> None:
    html = _convert("\\bibliography\n", bib_file)
    assert 'id="ref-chacon2014"' in html
    assert 'id="ref-skou2023"' in html


@pandoc_required
def test_bibliography_entries_get_the_reference_class(bib_file: str) -> None:
    html = _convert("\\bibliography\n", bib_file)
    assert 'class="csl-entry reference"' in html


@pandoc_required
def test_bibliography_marker_replaces_its_whole_paragraph(bib_file: str) -> None:
    """Splicing the generated <div>-based bibliography list directly
    inside the marker's own <p> would be invalid HTML - the whole <p>
    should be gone, replaced by the <div id="refs"> block directly."""
    html = _convert("\\bibliography\n", bib_file)
    assert "<p>" not in html


@pandoc_required
def test_bibliography_marker_file_argument_overrides_the_default(
    tmp_path: Path, bib_file: str
) -> None:
    """prodockit-extensions#89: \\bibliography{file.bib} draws from a
    specific file instead of the extension's configured default - e.g. a
    broader background-reading list kept separate from the main
    references.bib used for in-text \\citebib{} citations."""
    background = tmp_path / "background.bib"
    background.write_text(
        "@book{knuth1997,\n"
        "  author = {Knuth, Donald},\n"
        "  title = {The Art of Computer Programming},\n"
        "  year = {1997},\n"
        "  publisher = {Addison-Wesley}\n"
        "}\n",
        encoding="utf-8",
    )
    html = _convert(f"\\bibliography{{{background}}}\n", bib_file)
    assert "Knuth" in html
    assert "Chacon" not in html and "Skoulikari" not in html


@pandoc_required
def test_bibliography_marker_cited_only_includes_only_cited_entries(bib_file: str) -> None:
    """\\bibliography{file}{true} (prodockit-extensions#89) restricts the
    generated list to entries actually \\citebib{}-cited somewhere in the
    build - chacon2014 is cited here, skou2023 isn't, so only chacon2014
    should appear."""
    html = _convert(
        f"See \\citebib{{chacon2014}}.\n\n\\bibliography{{{bib_file}}}{{true}}\n", bib_file
    )
    assert "Chacon" in html
    assert "Skoulikari" not in html


@pandoc_required
def test_bibliography_marker_empty_file_argument_falls_back_to_default(bib_file: str) -> None:
    """\\bibliography{}{true} - an empty first argument still means "use
    the configured default bib_file", only toggling cited_only."""
    html = _convert("See \\citebib{chacon2014}.\n\n\\bibliography{}{true}\n", bib_file)
    assert "Chacon" in html
    assert "Skoulikari" not in html


@pandoc_required
def test_two_markers_one_cited_only_one_full_same_file(bib_file: str) -> None:
    """The exact scenario issue #89 asks for: a strict References section
    (cited_only=true) and a broader Bibliography section (cited_only=false,
    i.e. every entry) generated from the same .bib file in one build."""
    html = _convert(
        f"See \\citebib{{chacon2014}}.\n\n"
        f"## References\n\n\\bibliography{{{bib_file}}}{{true}}\n\n"
        f"## Bibliography\n\n\\bibliography{{{bib_file}}}{{false}}\n",
        bib_file,
    )
    references_html, bibliography_html = html.split("Bibliography</h2>", 1)
    assert "Chacon" in references_html
    assert "Skoulikari" not in references_html
    assert "Chacon" in bibliography_html
    assert "Skoulikari" in bibliography_html
    assert 'id="refs"' in html


@pandoc_required
def test_no_bibliography_marker_means_citations_are_unlinked(bib_file: str) -> None:
    """No \\bibliography anywhere means there's nowhere to link a resolved
    citation to - it should still resolve/format correctly, just without
    an <a href>."""
    html = _convert("See \\citebib{chacon2014}.", bib_file)
    assert "Chacon" in html
    assert "<a href" not in html
