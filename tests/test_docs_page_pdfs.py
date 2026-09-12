# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from prodockit.template_sync import read_config
from tools.docs_page_pdfs import ROOT, check_partial, page_url, partial, publish, targets, verify


def fixture_site(root: Path) -> None:
    (root / ".github").mkdir()
    (root / ".github/docs-single-page-pdfs.toml").write_text(
        '[build]\npages = ["pdf.md", "commands/pdf.md", "about/index.md"]\n'
        '[covered]\n"choosing-installation.md" = "pdf.md"\n', encoding="utf-8"
    )
    (root / "overrides/partials").mkdir(parents=True)
    (root / "overrides/partials/page-pdf.html").write_text(partial(root), encoding="utf-8")
    for source, target in targets(root).items():
        output = root / "docs" / f"{Path(source).stem}.pdf"
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(b"%PDF-" + source.encode())
        publish(source, root)
        html = root / "site" / page_url(source) / "index.html"
        html.parent.mkdir(parents=True, exist_ok=True)
        depth = len(Path(page_url(source)).parts)
        html.write_text(
            f'<a title="Download this page as PDF" href="{"../" * depth}{target}">PDF</a>',
            encoding="utf-8",
        )


def test_committed_partial_matches_matrix():
    check_partial(ROOT)
    rendered = partial(ROOT)
    assert 'page.url == "commands/pdf/"' not in rendered
    assert 'page.url == "commands/update-dates/"' not in rendered
    assert 'page.url == "choosing-installation/"' not in rendered
    assert 'page.url == "about/"' in rendered


def test_documentation_config_matches_publishing_layout():
    project = read_config((ROOT / "zensical.toml").read_text())["project"]
    assert project.get("docs_dir", "docs") == "docs"
    assert project.get("site_dir", "site") == "site"
    assert project.get("use_directory_urls", True) is True
    assert not project.get("extra", {}).get("pdf_output"), "matrix snapshots use default CLI outputs"


def test_distinct_source_pdfs_survive_flat_output_collisions(tmp_path):
    fixture_site(tmp_path)
    verify(tmp_path)
    for directory in ("docs", "site"):
        assert (tmp_path / directory / "page-pdfs/pdf.pdf").read_bytes() == b"%PDF-pdf.md"
        assert (tmp_path / directory / "page-pdfs/commands/pdf.pdf").read_bytes() == b"%PDF-commands/pdf.md"


@pytest.mark.parametrize("fault", ["missing", "wrong", "duplicate", "external", "not-pdf"])
def test_verifier_rejects_bad_artifacts_and_actions(tmp_path, fault):
    fixture_site(tmp_path)
    html = tmp_path / "site/commands/pdf/index.html"
    if fault == "missing":
        (tmp_path / "site/page-pdfs/commands/pdf.pdf").unlink()
    elif fault == "not-pdf":
        (tmp_path / "site/page-pdfs/commands/pdf.pdf").write_text("error")
    else:
        text = html.read_text()
        if fault == "wrong":
            text = text.replace("page-pdfs/commands/pdf.pdf", "page-pdfs/pdf.pdf")
        elif fault == "external":
            text = text.replace("../../", "https://example.com/")
        else:
            text += text
        html.write_text(text)
    with pytest.raises(ValueError):
        verify(tmp_path)


def test_verifier_rejects_action_on_covered_page(tmp_path):
    fixture_site(tmp_path)
    (tmp_path / "site/choosing-installation.html").write_text(
        '<a title="Download this page as PDF" href="page-pdfs/pdf.pdf">PDF</a>'
    )
    with pytest.raises(ValueError, match="Unexpected PDF action"):
        verify(tmp_path)


def test_verifier_requires_each_built_page_and_its_action(tmp_path):
    fixture_site(tmp_path)
    html = tmp_path / "site/pdf/index.html"
    html.write_text("no action")
    with pytest.raises(ValueError, match="Incorrect PDF action"):
        verify(tmp_path)
    html.unlink()
    with pytest.raises(ValueError, match="Missing PDF pages"):
        verify(tmp_path)


def test_workflow_copies_each_successful_build_and_checks_final_site():
    workflow = (ROOT / ".github/workflows/docs.yml").read_text()
    build = workflow.index('subprocess.run(["prodockit", "pdf", "-m", path], check=True)')
    assert build < workflow.index("publish(path)", build)
    assert workflow.index("Build the canonical prodockit.org website") < workflow.index(
        "python tools/docs_page_pdfs.py verify"
    ) < workflow.index("actions/upload-pages-artifact")
