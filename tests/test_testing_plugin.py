# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for the `prodockit.testing` pytest plugin.

Run through `pytester`, which executes real, isolated pytest sessions
against synthetic projects - the plugin's whole job is fixture resolution
and config reading inside a pytest run, so calling the functions directly
would test almost none of it.
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]

CONFIG = """\
[project]
site_name = "Example"
docs_dir = "docs"
site_dir = "public"
nav = [
  {"Home" = "index.md"},
]

[project.markdown_extensions."prodockit.index"]
include = true
title = "Subject index"
"""


def _make_project(pytester: pytest.Pytester, *, config: str = CONFIG) -> None:
    pytester.makefile(".toml", zensical=config)
    pytester.mkdir("docs")
    site = pytester.mkdir("public")
    (site / "index.html").write_text("<html><body><h1>Hi</h1></body></html>", encoding="utf-8")


def _write_pdf(pytester: pytest.Pytester, path: str, *, text: str = "Hello") -> None:
    """A real, openable one-page PDF - the fixture opens it with pymupdf, so
    a stub file of bytes wouldn't exercise anything."""
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    target = pytester.path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target))
    doc.close()


def test_paths_come_from_the_config_not_an_assumed_layout(pytester: pytest.Pytester) -> None:
    """site_dir defaults to `site` but is commonly `public`; docs_dir and
    the PDF name are configurable too."""
    _make_project(pytester)
    _write_pdf(pytester, "docs/site_documentation.pdf")
    pytester.makepyfile(
        """
        def test_paths(prodockit_paths):
            assert prodockit_paths.site_dir.name == "public"
            assert prodockit_paths.docs_dir.name == "docs"
            assert prodockit_paths.pdf.name == "site_documentation.pdf"
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_site_dir_falls_back_to_zensical_default(pytester: pytest.Pytester) -> None:
    _make_project(pytester, config=CONFIG.replace('site_dir = "public"\n', ""))
    pytester.makepyfile(
        """
        def test_default(prodockit_paths):
            assert prodockit_paths.site_dir.name == "site"
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_resolved_config_and_nav_use_prodockits_normalized_model(
    pytester: pytest.Pytester,
) -> None:
    _make_project(pytester)
    pytester.makepyfile(
        """
        def test_config(prodockit_resolved_config, prodockit_nav_pages):
            assert prodockit_nav_pages == ["index.md"]
            assert prodockit_resolved_config["nav"][0]["is_index"] is True
            assert prodockit_resolved_config["mdx_configs"]["prodockit.index"] == {
                "include": True,
                "title": "Subject index",
            }
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_pdf_output_setting_is_honoured(pytester: pytest.Pytester) -> None:
    config = CONFIG + '\n[project.extra]\npdf_output = "dist/report.pdf"\n'
    _make_project(pytester, config=config)
    _write_pdf(pytester, "dist/report.pdf")
    pytester.makepyfile(
        """
        def test_output(prodockit_paths, prodockit_pdf):
            assert prodockit_paths.pdf.name == "report.pdf"
            assert prodockit_pdf.page_count == 1
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_pdf_path_can_be_overridden_by_ini_option(pytester: pytest.Pytester) -> None:
    _make_project(pytester)
    _write_pdf(pytester, "somewhere/else.pdf")
    pytester.makeini("[pytest]\nprodockit_pdf = somewhere/else.pdf\n")
    pytester.makepyfile(
        """
        def test_override(prodockit_paths):
            assert prodockit_paths.pdf.name == "else.pdf"
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_pdf_fixture_opens_the_real_document(pytester: pytest.Pytester) -> None:
    _make_project(pytester)
    _write_pdf(pytester, "docs/site_documentation.pdf", text="Findable text")
    pytester.makepyfile(
        """
        def test_text(prodockit_pdf_page_texts):
            assert len(prodockit_pdf_page_texts) == 1
            assert "Findable text" in prodockit_pdf_page_texts[0]
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_missing_pdf_fails_with_a_message_naming_the_build_step(
    pytester: pytest.Pytester,
) -> None:
    """The most common way to run these tests wrong is forgetting to build
    first, so the failure has to say so rather than raising a bare OSError."""
    _make_project(pytester)
    pytester.makepyfile(
        """
        def test_needs_pdf(prodockit_pdf):
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*prodockit pdf*"])


def test_missing_config_fails_with_a_message_naming_the_ini_option(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        """
        def test_needs_config(prodockit_paths):
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*prodockit_config_file*"])


def test_site_fixtures_read_the_built_site(pytester: pytest.Pytester) -> None:
    _make_project(pytester)
    (pytester.path / "public" / "page.html").write_text("<html></html>", encoding="utf-8")
    pytester.makepyfile(
        """
        def test_site(prodockit_site_dir, prodockit_site_html_files, prodockit_soup_for):
            assert prodockit_site_dir.name == "public"
            assert len(prodockit_site_html_files) == 2
            soup = prodockit_soup_for(prodockit_site_dir / "index.html")
            assert soup.find("h1").get_text() == "Hi"
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_missing_site_fails_with_a_message_naming_the_build_step(
    pytester: pytest.Pytester,
) -> None:
    _make_project(pytester)
    (pytester.path / "public" / "index.html").unlink()
    pytester.makepyfile(
        """
        def test_needs_site(prodockit_site_dir):
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*zensical build*"])


def test_plugin_is_harmless_in_a_project_that_is_not_a_prodockit_site(
    pytester: pytest.Pytester,
) -> None:
    """The plugin loads into every pytest run in an environment where
    prodockit is installed. A project with no zensical.toml, that never
    touches these fixtures, must be completely unaffected."""
    pytester.makepyfile(
        """
        def test_unrelated():
            assert 1 + 1 == 2
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)
    assert result.ret == 0
    # The plugin appears in pytest's own header line, which is expected and
    # harmless. What matters is that none of its machinery ran: no attempt to
    # find a config, and no warning or error attributable to it.
    output = result.stdout.str()
    assert "zensical.toml" not in output
    assert "prodockit_config_file" not in output


def test_checks_are_usable_against_the_pdf_fixtures(pytester: pytest.Pytester) -> None:
    """The two halves working together, which is the intended usage."""
    _make_project(pytester)
    _write_pdf(pytester, "docs/site_documentation.pdf", text="ordinary prose")
    pytester.makepyfile(
        """
        from prodockit.testing import assert_no_unrendered_mermaid, assert_no_unrendered_tex

        def test_nothing_unrendered(prodockit_pdf_page_texts):
            assert_no_unrendered_mermaid(prodockit_pdf_page_texts)
            assert_no_unrendered_tex(prodockit_pdf_page_texts)
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_checks_fail_against_a_pdf_with_raw_diagram_source(
    pytester: pytest.Pytester,
) -> None:
    """The failure this whole module exists to catch, end to end through a
    real PDF rather than a string literal."""
    _make_project(pytester)
    _write_pdf(pytester, "docs/site_documentation.pdf", text="graph LR\n  A --> B;")
    pytester.makepyfile(
        """
        from prodockit.testing import assert_no_unrendered_mermaid

        def test_should_fail(prodockit_pdf_page_texts):
            assert_no_unrendered_mermaid(prodockit_pdf_page_texts)
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Literal Mermaid source*"])
