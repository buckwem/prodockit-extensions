# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Bounded source compilation, public CLI integration and reversible switching."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup
from click.testing import CliRunner
from PIL import Image

from prodockit.cli import main
from prodockit.portable import PortableError
from prodockit.portable.compiler import scan
from prodockit.portable.manifest import read_manifest, write_manifest
from prodockit.portable.project import build, prepare, validate


@pytest.fixture
def portable_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = Path(__file__).resolve().parents[1] / "src"
    monkeypatch.setenv("PYTHONPATH", str(source))
    config = tmp_path / "zensical.toml"
    config.write_text(
        """[project]
site_name = "Portable prototype"
site_url = "https://example.test/manual/"
nav = [{Home = "index.md"}, {Guide = "guide/install.md"}, {References = "references.md"}]
[project.theme]
font = false
[project.markdown_extensions.attr_list]
[project.markdown_extensions.toc]
permalink = true
[project.markdown_extensions.tables]
[project.markdown_extensions."prodockit.headings"]
numbering = "continuous"
[project.markdown_extensions."prodockit.refs"]
[project.markdown_extensions.pymdownx.superfences]
custom_fences = [
  {name = "image-hotspots", class = "image-hotspots", format = "prodockit.image_hotspots.format_hotspots"},
  {name = "mermaid", class = "mermaid"},
]
""",
        encoding="utf-8",
    )
    (tmp_path / "docs/guide").mkdir(parents=True)
    (tmp_path / "docs/assets").mkdir()
    (tmp_path / "docs/index.md").write_text(
        r"""# Home {: #home .unnumbered }

See \ref{installation} and \autoref{installation}.

Literal `\ref{not-a-target}` and escaped \\ref{not-a-target}.

```markdown
\ref{also-not-a-target}
```

| Name | Value |
| --- | --- |
| Example | Unchanged table |
""",
        encoding="utf-8",
    )
    (tmp_path / "docs/guide/install.md").write_text(
        r"""# Setup

## Installation

Same page: \ref{installation}. Back: \ref{home}.

```image-hotspots
image: ../assets/map.png
alt: Example map
hotspots:
  - {label: Installation, href: '#installation', rect: [0, 0, 100, 50]}
  - {label: Home, href: '../index.md#home', rect: [100, 50, 100, 50]}
```
""",
        encoding="utf-8",
    )
    (tmp_path / "docs/references.md").write_text(
        "# References {: .unnumbered }\n", encoding="utf-8"
    )
    Image.new("RGB", (200, 100)).save(tmp_path / "docs/assets/map.png")
    return config


def _article(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


@pytest.mark.parametrize("directory_urls", [True, False])
def test_glossary_links_match_in_both_build_modes(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch, directory_urls: bool
) -> None:
    config = portable_project.read_text().replace(
        "[project]", f"[project]\nuse_directory_urls = {str(directory_urls).lower()}"
    )
    portable_project.write_text(config + '\n[project.markdown_extensions."prodockit.glossary"]\n')
    root = portable_project.parent
    guide = root / "docs/guide/install.md"
    refs = root / "docs/references.md"
    guide.write_text(
        guide.read_text() + '\nUse \\gls{data} and \\gls{local}. Literal `\\gls{literal}`.\n'
        '\n**Local term** with example `{: #fake data-term="Literal" }`.\n'
        '{: #local .glossary data-term="Local term" }\n',
        encoding="utf-8",
    )
    refs.write_text(
        refs.read_text()
        + '\n**Data**.\n{: #data .glossary data-term="R&amp;D café" title="See this" }\n',
        encoding="utf-8",
    )
    originals = {path: path.read_bytes() for path in (guide, refs, portable_project)}

    def rendered(site: Path) -> tuple[list[tuple[str, str]], str]:
        guide_html = "guide/install/index.html" if directory_urls else "guide/install.html"
        refs_html = "references/index.html" if directory_urls else "references.html"
        page = _article(site / guide_html)
        assert any(code.get_text() == r"\gls{literal}" for code in page.select("code"))
        target = _article(site / refs_html).select_one("p#data.glossary")
        assert target is not None and target["title"] == "See this"
        assert not target.has_attr("data-term")
        return [(a["href"], a.get_text()) for a in page.select("a.prodockit-gls")], str(target)

    cmd = ["build", "-f", str(portable_project), "--strict", "--clean"]
    normal = CliRunner().invoke(main, cmd)
    assert normal.exit_code == 0, normal.output
    expected = rendered(root / "site")
    forward = "../../references/" if directory_urls else "../references.html"
    assert expected[0] == [(forward + "#data", "R&D café"), ("#local", "Local term")]
    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import prodockit.glossary\n"
        "def forbidden(*args, **kwargs):\n"
        "    raise AssertionError('legacy glossary adapter was called')\n"
        "prodockit.glossary.GlossaryExtension.extendMarkdown = forbidden\n",
        encoding="utf-8",
    )
    with monkeypatch.context() as isolated:
        isolated.setenv("PYTHONPATH", str(guard) + os.pathsep + os.environ["PYTHONPATH"])
        prepared = build(str(portable_project))
    assert rendered(prepared.site) == expected
    result = CliRunner().invoke(main, cmd)
    assert result.exit_code == 0, result.output
    assert rendered(root / "site") == expected
    assert all(path.read_bytes() == data for path, data in originals.items())


@pytest.mark.parametrize(
    ("authored", "message"),
    [
        ("\\gls{absent}", "unresolved glossary term 'absent'"),
        ('- **Nested**\n  {: #nested data-term="Nested" }', "top-level paragraph"),
        ('# Heading {: #heading data-term="Heading" }', "top-level paragraph"),
        ('Text\n{: #term data-term="A *term*" }', "attributes were not parsed as authored"),
        ('First\n{: #term data-term="One" }\n\nSecond\n{: #term data-term="Two" }',
         "duplicate glossary term 'term'"),
    ],
)
def test_portable_glossary_refuses_invalid_or_unqualified_input(
    portable_project: Path, authored: str, message: str
) -> None:
    with portable_project.open("a", encoding="utf-8") as config:
        config.write('\n[project.markdown_extensions."prodockit.glossary"]\n')
    page = portable_project.parent / "docs/references.md"
    page.write_text(authored + "\n", encoding="utf-8")
    with pytest.raises(PortableError, match=r"references\.md:\d+: .*" + message):
        prepare(str(portable_project))


@pytest.mark.parametrize("directory_urls", [True, False])
def test_manual_citation_groups_match_in_both_build_modes(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch, directory_urls: bool
) -> None:
    config = portable_project.read_text().replace(
        "[project]", f"[project]\nuse_directory_urls = {str(directory_urls).lower()}"
    )
    portable_project.write_text(
        config + '\n[project.markdown_extensions."prodockit.citations"]\n'
        '\n[project.markdown_extensions."prodockit.glossary"]\n'
    )
    root = portable_project.parent
    guide = root / "docs/guide/install.md"
    refs = root / "docs/references.md"
    guide.write_text(
        guide.read_text() + '\nSee \\citeref{study, local, study} and \\gls{study}. '
        'Literal `\\citeref{literal}`.\n'
        '\n**Local work**.\n{: #local .reference data-cite-text="Local, 2025" }\n',
        encoding="utf-8",
    )
    refs.write_text(
        refs.read_text()
        + '\n**Study**.\n{: #study .reference data-cite-text="R&amp;D, 2026" data-term="Study" }\n',
        encoding="utf-8",
    )
    paths = [guide, refs, portable_project]
    originals = [path.read_bytes() for path in paths]

    def rendered(site: Path) -> tuple[str, list[tuple[str, str]], str]:
        guide_html = "guide/install/index.html" if directory_urls else "guide/install.html"
        refs_html = "references/index.html" if directory_urls else "references.html"
        page = _article(site / guide_html)
        assert any(code.get_text() == r"\citeref{literal}" for code in page.select("code"))
        target = _article(site / refs_html).select_one("p#study.reference")
        assert target is not None and not target.has_attr("data-cite-text")
        assert not target.has_attr("data-term")
        group = page.select_one("span.prodockit-cite")
        assert group is not None
        items = [(anchor["href"], anchor.get_text()) for anchor in group.select("a")]
        term = page.select_one("a.prodockit-gls")
        assert term is not None and term.get_text() == "Study"
        return group.get_text(), items, term["href"]

    runner = CliRunner()
    cmd = ["build", "-f", str(portable_project), "--strict", "--clean"]
    normal = runner.invoke(main, cmd)
    assert normal.exit_code == 0, normal.output
    expected = rendered(root / "site")
    forward = "../../references/#study" if directory_urls else "../references.html#study"
    assert expected == (
        "[R&D, 2026; Local, 2025; R&D, 2026]",
        [(forward, "R&D, 2026"), ("#local", "Local, 2025"), (forward, "R&D, 2026")],
        forward,
    )

    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import prodockit.citations\n"
        "def forbidden(*args, **kwargs):\n"
        "    raise AssertionError('legacy citation adaptor was called')\n"
        "prodockit.citations.CitationsExtension.extendMarkdown = forbidden\n",
        encoding="utf-8",
    )
    with monkeypatch.context() as isolated:
        isolated.setenv("PYTHONPATH", str(guard) + os.pathsep + os.environ["PYTHONPATH"])
        prepared = build(str(portable_project))
    assert rendered(prepared.site) == expected
    normal = runner.invoke(main, cmd)
    assert normal.exit_code == 0, normal.output
    assert rendered(root / "site") == expected
    assert [path.read_bytes() for path in paths] == originals


@pytest.mark.parametrize(
    ("authored", "message"),
    [
        ("\\citeref{missing}", "unresolved citation key 'missing'"),
        ("\\citeref{ , }", "give the citation at least one key"),
        ('- **Nested**\n  {: #nested data-cite-text="Nested" }', "top-level paragraph"),
        (
            'First\n{: #one data-cite-text="One" }\n\nSecond\n{: #one data-cite-text="Two" }',
            "duplicate citation key 'one'",
        ),
    ],
)
def test_portable_manual_citations_report_authored_location(
    portable_project: Path, authored: str, message: str
) -> None:
    with portable_project.open("a", encoding="utf-8") as config:
        config.write('\n[project.markdown_extensions."prodockit.citations"]\n')
    page = portable_project.parent / "docs/references.md"
    page.write_text(authored + "\n", encoding="utf-8")
    with pytest.raises(PortableError, match=r"references\.md:\d+: .*" + message):
        prepare(str(portable_project))


@pytest.mark.parametrize(("directory_urls", "appendix"), [(True, False), (False, True)])
def test_portable_caption_parity(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch, directory_urls: bool, appendix: bool
) -> None:
    root = portable_project.parent
    config = portable_project.read_text().replace(
        "[project]", f"[project]\nuse_directory_urls = {str(directory_urls).lower()}"
    )
    portable_project.write_text(
        config + '''
[project.markdown_extensions."pymdownx.blocks.caption"]
types = [
  { name = "figure-caption", prefix = "{}.", classes = "prodockit-figure-caption" },
  { name = "table-caption", prefix = "{}.", classes = "prodockit-table-caption" },
]
''',
        encoding="utf-8",
    )
    home = root / "docs/index.md"
    home.write_text(
        '# Home {: #home }\n\nSee \\ref{fig-list-one}, \\autoref{fig-list-two} and \\ref{tab-results}.\n',
        encoding="utf-8",
    )
    source = root / "docs/guide/install.md"
    body = """# Setup

![First](../assets/map.png)
/// figure-caption
Unlabelled figure
///

1. Inspect the first figure.

    ![First](../assets/map.png){ width="65%" }
    /// figure-caption | #fig-list-one
    First nested figure
    ///

2. Inspect the second figure.

    ![Second](../assets/map.png)
    /// figure-caption
        attrs: {id: fig-list-two}

    Second nested figure
    ///

| Name | Value |
| --- | --- |
| Result | 12 |
/// table-caption | <
    attrs: {id: tab-results}

Results table
///

```markdown
/// figure-caption | #literal
This is a code example.
///
```
"""
    front = "---\nis_appendix: true\n---\n\n" if appendix else ""
    source.write_text(front + body, encoding="utf-8")
    originals = {path: path.read_bytes() for path in (portable_project, home, source)}
    runner = CliRunner()
    ordinary = ["build", "-f", str(portable_project), "--clean", "--strict"]
    result = runner.invoke(main, ordinary)
    assert result.exit_code == 0, result.output

    def links(site: Path) -> list[tuple[str, str]]:
        return [
            (link["href"], link.get_text())
            for link in _article(site / "index.html").select(".prodockit-ref, .prodockit-autoref")
        ]

    chapter = "A" if appendix else "2"
    base = "guide/install/" if directory_urls else "guide/install.html"
    expected = [
        (base + "#fig-list-one", f"Figure {chapter}.2"),
        (base + "#fig-list-two", f"Figure {chapter}.3"),
        (base + "#tab-results", f"Table {chapter}.1"),
    ]
    assert links(root / "site") == expected
    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import prodockit._zensical_page_context as context\n"
        "import prodockit.headings\n"
        "def forbidden(*args, **kwargs):\n"
        "    raise AssertionError('legacy page context or heading processor was called')\n"
        "context._rendering_context = forbidden\n"
        "prodockit.headings.HeadingsTreeprocessor.run = forbidden\n",
        encoding="utf-8",
    )
    with monkeypatch.context() as isolated:
        isolated.setenv("PYTHONPATH", str(guard) + os.pathsep + os.environ["PYTHONPATH"])
        prepared = build(str(portable_project))
    assert links(prepared.site) == expected
    guide_file = "guide/install/index.html" if directory_urls else "guide/install.html"
    soup = _article(prepared.site / guide_file)
    figures = soup.select("figure.prodockit-figure-caption")
    assert len(figures) == 3
    assert [fig["id"] for fig in soup.select("ol li figure")] == ["fig-list-one", "fig-list-two"]
    assert "width: 65%;" in figures[1]["style"]
    old = _article(root / "site" / guide_file)
    assert figures[1]["style"] == old.select_one("#fig-list-one")["style"]
    assert soup.select_one("#tab-results").find(recursive=False).name == "figcaption"
    assert [p.get_text() for p in soup.select(".pdk-prepared-caption-prefix")] == [
        f"Figure {chapter}.1.", f"Figure {chapter}.2.", f"Figure {chapter}.3.", f"Table {chapter}.1."
    ]
    assert soup.select_one("#literal") is None
    built = prepared.site / guide_file
    prefix = soup.select_one(".pdk-prepared-caption-prefix")
    assert prefix is not None
    prefix.string = "Figure 99.99."
    built.write_text(str(soup), encoding="utf-8")
    with pytest.raises(PortableError, match="prepared caption anchor or number changed"):
        validate(prepared)
    assert all(path.read_bytes() == data for path, data in originals.items())
    result = runner.invoke(main, ordinary)
    assert result.exit_code == 0, result.output
    assert links(root / "site") == expected


def test_caption_scanner_keeps_literal_code_and_rejects_manual_numbers() -> None:
    fixture = """    /// figure-caption | #literal
    An indented code example.
    ///

![Example](example.png)
/// figure-caption | 4 #manual
Manual number
///
"""
    page = scan("guide.md", fixture.rsplit("\n\n", 1)[0], caption_options={})
    assert not page.captions
    with pytest.raises(PortableError, match=r"guide\.md:6: custom caption numbering"):
        scan("guide.md", fixture, caption_options={})


def _enable_prodockit_tables(config: Path) -> None:
    with config.open("a", encoding="utf-8") as handle:
        handle.write('\n[project.markdown_extensions."prodockit.tables"]\n')


def test_table_layout_matches_without_private_page_context(portable_project: Path) -> None:
    root = portable_project.parent
    _enable_prodockit_tables(portable_project)
    source = root / "docs/index.md"
    source.write_text(
        source.read_text().replace(
            "| Name | Value |", '| Name {: width="30%" } | Value |'
        )
        + '\n```markdown\n| Example{: width="30%" } | Taken literally |\n```\n',
        encoding="utf-8",
    )
    original = {path: path.read_bytes() for path in (portable_project, source)}
    runner = CliRunner()
    ordinary = ["build", "-f", str(portable_project), "--clean", "--strict"]
    result = runner.invoke(main, ordinary)
    assert result.exit_code == 0, result.output
    expected = _article(root / "site/index.html").select_one("table")
    assert expected is not None and expected.select_one("colgroup col") is not None

    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import prodockit.tables\n"
        "def forbidden(*args, **kwargs):\n"
        "    raise AssertionError('legacy table source diagnostics were called')\n"
        "prodockit.tables.page_source = forbidden\n"
        "prodockit.tables.MalformedTableAttributePreprocessor.run = forbidden\n",
        encoding="utf-8",
    )
    with pytest.MonkeyPatch.context() as isolated:
        isolated.setenv("PYTHONPATH", str(guard) + os.pathsep + os.environ["PYTHONPATH"])
        prepared = build(str(portable_project))
    assert _article(prepared.site / "index.html").select_one("table") == expected
    result = runner.invoke(main, ordinary)
    assert result.exit_code == 0, result.output
    assert _article(root / "site/index.html").select_one("table") == expected
    assert all(path.read_bytes() == data for path, data in original.items())


def test_table_preparation_reports_authored_path_and_line(portable_project: Path) -> None:
    _enable_prodockit_tables(portable_project)
    root = portable_project.parent
    source = root / "docs/guide/install.md"
    source.write_bytes(
        b'---\r\ntitle: Guide\r\n---\r\n\r\n# Setup\r\n\r\n'
        b'| Name{: width="30%" } | Description |\r\n| --- | --- |\r\n'
    )
    with pytest.raises(PortableError, match=r"guide/install\.md:7: missing space"):
        prepare(str(portable_project))
    assert not list((root / ".pdk/portable/generations").iterdir())


def test_preparation_is_selective_and_deterministic(portable_project: Path) -> None:
    root = portable_project.parent
    original = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    first = prepare(str(portable_project))
    second = prepare(str(portable_project))
    assert first.config != second.config  # Independent, concurrent-safe generations.
    one_manifest, two_manifest = read_manifest(first.manifest), read_manifest(second.manifest)
    assert one_manifest.pop("generation") != two_manifest.pop("generation")
    assert one_manifest == two_manifest
    assert len(one_manifest["content_id"]) == 64
    for name in ("index.md", "guide/install.md", "references.md"):
        one = (first.config.parent / "docs" / name).read_text()
        assert one == (second.config.parent / "docs" / name).read_text()
    source = (first.config.parent / "docs/index.md").read_text()
    assert (
        '<a class="prodockit-ref" href="guide/install.md#installation">1.1 Installation</a>'
        in source
    )
    assert "Literal `\\ref{not-a-target}`" in source
    assert r"escaped \\ref{not-a-target}" in source
    assert "| Example | Unchanged table |" in source
    generated = first.config.read_text()
    assert "prodockit.refs" not in generated
    assert "format_hotspots" not in generated
    assert "mermaid" in generated
    assert "tables" in generated
    for path, contents in original.items():
        assert Path(path).read_bytes() == contents
    assert not (root / "site").exists()


@pytest.mark.parametrize("restore", [False, True])
def test_preparation_uses_captured_hotspot_bytes_during_edits(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch, restore: bool,
) -> None:
    from prodockit.portable import project

    previous = prepare(str(portable_project))
    previous_bytes = previous.manifest.read_bytes()
    generations = set(previous.config.parent.parent.iterdir())
    image = portable_project.parent / "docs/assets/map.png"
    original = image.read_bytes()
    compile_pages = project.compile_pages

    def compile_while_edited(*args, **kwargs):
        Image.new("RGB", (400, 200)).save(image)
        result = compile_pages(*args, **kwargs)
        assert 'width="200"' in result[0]["guide/install.md"]
        if restore:
            image.write_bytes(original)
        return result

    monkeypatch.setattr(project, "compile_pages", compile_while_edited)
    if restore:
        prepared = prepare(str(portable_project))
        assert read_manifest(prepared.manifest)["content_id"] == read_manifest(
            previous.manifest
        )["content_id"]
    else:
        with pytest.raises(PortableError, match="changed during preparation"):
            prepare(str(portable_project))
        assert set(previous.config.parent.parent.iterdir()) == generations
    assert previous.manifest.read_bytes() == previous_bytes
    assert not (portable_project.parent / ".pdk/portable/lock").exists()


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="requires real Pandoc citeproc")
def test_bibliography_compiles_captured_external_dependency(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prodockit.portable import project

    root = portable_project.parent
    bib = root / "references.bib"
    original = b"@book{example, title={Captured title}, author={Doe, Jane}, year={2025}}\n"
    bib.write_bytes(original)
    with portable_project.open("a") as config:
        config.write('\n[project.markdown_extensions."prodockit.bibliography"]\n')
    with (root / "docs/references.md").open("a") as page:
        page.write("\n\\bibliography\n")
    compile_pages = project.compile_pages

    def compile_while_edited(*args, **kwargs):
        bib.write_bytes(original.replace(b"Captured title", b"Live changed title"))
        try:
            return compile_pages(*args, **kwargs)
        finally:
            bib.write_bytes(original)

    monkeypatch.setattr(project, "compile_pages", compile_while_edited)
    prepared = prepare(str(portable_project), pandoc=Path(shutil.which("pandoc")))
    manifest = read_manifest(prepared.manifest)
    captured = manifest["captured_inputs"][str(bib)]
    assert captured.startswith(".inputs/dependencies/")
    assert (prepared.config.parent / captured).read_bytes() == original
    rendered = (prepared.config.parent / "docs/references.md").read_text().lower()
    assert "captured title" in rendered and "live changed title" not in rendered
    assert not list((prepared.config.parent / "docs").rglob("*.bib"))


def test_captured_configuration_drives_preparation(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prodockit.portable import project

    home = portable_project.parent / "docs/index.md"
    home.write_text(home.read_text().replace("#home .unnumbered", "#home"))
    load = project.load_project_config

    def edit_after_initial_load(path):
        previous = load(path)
        portable_project.write_text(portable_project.read_text().replace(
            'numbering = "continuous"', 'numbering = "per-document"'
        ))
        return previous

    monkeypatch.setattr(project, "load_project_config", edit_after_initial_load)
    prepared = prepare(str(portable_project))
    assert read_manifest(prepared.manifest)["input_hashes"]
    assert (prepared.config.parent / ".inputs/config.toml").read_bytes() == portable_project.read_bytes()
    # Continuous numbering in the stale initial load would make this chapter 2.
    assert "1.1 Installation" in (prepared.config.parent / "docs/index.md").read_text()


@pytest.mark.parametrize("change", ["add", "remove", "capture", "config"])
def test_prepared_inventory_is_checked_before_zensical(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    from prodockit.portable import project

    prepared = prepare(str(portable_project))
    root = prepared.config.parent
    if change == "add":
        (root / "docs/extra.txt").write_text("untracked input")
    elif change == "remove":
        (root / "docs/assets/map.png").unlink()
    elif change == "capture":
        (root / ".inputs/docs/index.md").write_text("changed capture")
    else:
        prepared.config.write_text("changed config")
    monkeypatch.setattr(project.subprocess, "run", lambda *_a, **_k: pytest.fail("CLI was run"))
    with pytest.raises(PortableError, match="prepared input changed"):
        project._build(prepared)


@pytest.mark.parametrize("change", ["fingerprint", "generation", "schema", "paths", "pages", "map", "runtime"])
def test_invalid_manifest_is_rejected(portable_project: Path, change: str) -> None:
    from prodockit.portable.project import _validate_prepared

    prepared = prepare(str(portable_project))
    manifest = read_manifest(prepared.manifest)
    if change == "fingerprint":
        manifest["directory_urls"] = False
    elif change == "generation":
        manifest["generation"] = "another-generation"
    elif change == "schema":
        manifest["schema"] = 1
    elif change == "paths":
        manifest["captured_inputs"][str(portable_project)] = "../zensical.toml"
    elif change == "pages":
        manifest["pages"]["index.md"]["links"] = [None]
    elif change == "map":
        manifest["pages"]["index.md"]["source_map"].pop()
    else:
        manifest["toolchain"]["pandoc"] = ["invalid"]
    if change == "fingerprint":
        prepared.manifest.write_text(json.dumps(manifest))
    else:
        write_manifest(prepared.manifest, manifest)
    with pytest.raises(PortableError):
        _validate_prepared(prepared)


def test_changed_toolchain_is_rejected(portable_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from prodockit.portable import manifest
    from prodockit.portable.project import _validate_prepared

    prepared = prepare(str(portable_project))
    monkeypatch.setattr(manifest, "version", lambda _: "a different version")
    with pytest.raises(PortableError, match="toolchain changed"):
        _validate_prepared(prepared)


def test_separate_public_build_and_manifest_validation(portable_project: Path) -> None:
    from prodockit.portable.project import command

    prepared = prepare(str(portable_project))
    subprocess.run(
        command(prepared.config, "build", "--clean", "--strict"),
        cwd=prepared.config.parent, check=True,
    )
    result = CliRunner().invoke(main, ["-p", "validate", "--manifest", str(prepared.manifest)])
    assert result.exit_code == 0, result.output
    assert not (prepared.site / ".inputs").exists()
    assert not (prepared.site / ".pdk-build.json").exists()  # Separate public CLI has no receipt.


def test_site_receipt_must_match_generation(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    receipt = prepared.site / ".pdk-build.json"
    contents = json.loads(receipt.read_text())
    assert contents["content_id"] == read_manifest(prepared.manifest)["content_id"]
    contents["content_id"] = "another-preparation"
    receipt.write_text(json.dumps(contents))
    with pytest.raises(PortableError, match="receipt does not match"):
        validate(prepared)


@pytest.mark.parametrize("change", ["missing-receipt", "wrong-project", "stale", "site-files"])
def test_portable_pdf_rejects_unverified_site(
    portable_project: Path, change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prodockit.portable import project

    built = build(str(portable_project))
    args = ["-p", "pdf", "--manifest", str(built.manifest)]
    if change == "missing-receipt":
        (built.site / ".pdk-build.json").unlink()
        message = "requires a completed pdk -p build"
    elif change == "wrong-project":
        other = portable_project.with_name("other.toml")
        other.write_bytes(portable_project.read_bytes())
        args += ["-f", str(other)]
        message = "different original configuration"
    elif change == "stale":
        (portable_project.parent / "docs/references.md").write_text("# Changed\n")
        message = "portable output is stale"
    else:
        (built.site / "assets/map.png").write_bytes(b"unexpected bytes")
        message = "site files changed after build"
    monkeypatch.setattr(
        project, "render_portable_pdf", lambda *a, **k: pytest.fail("unverified site reached PDF")
    )
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 1 and message in result.output, result.output
    assert not (built.manifest.parent / "pdf").exists()


def test_portable_pdf_preserves_published_pdf_if_sources_change(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prodockit.pdf import config

    built = build(str(portable_project))
    root = built.manifest.parent
    previous = root / "pdf" / "site_documentation.pdf"
    previous.parent.mkdir()
    previous.write_bytes(b"previous PDF")

    def render(_config, *, output_directory, **_kwargs):
        output = output_directory / previous.name
        output.write_bytes(b"replacement PDF")
        (portable_project.parent / "docs/references.md").write_text("# Changed\n")
        return str(output)

    monkeypatch.setattr(config, "build_pdf_from_built_site", render)
    result = CliRunner().invoke(main, ["-p", "pdf", "--manifest", str(built.manifest)])
    assert result.exit_code == 1 and "portable output is stale" in result.output, result.output
    assert previous.read_bytes() == b"previous PDF"
    assert not list(root.glob(".pdf-*"))


def test_ordinary_pdf_refuses_a_portable_site(portable_project: Path) -> None:
    from prodockit.pdf.site import BuiltSiteError, validate_built_site
    from prodockit.project_config import load_project_config

    built = build(str(portable_project))
    with pytest.raises(BuiltSiteError, match="portable site selected"):
        validate_built_site(load_project_config(built.config), ["index.md"])


@pytest.mark.skipif(
    not shutil.which("pandoc") or not shutil.which("weasyprint"),
    reason="requires real Pandoc and WeasyPrint",
)
def test_portable_pdf_uses_selected_site_and_matches_ordinary_pdf(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prodockit.pdf import config

    pymupdf = pytest.importorskip("pymupdf")
    root = portable_project.parent
    with (root / "docs/guide/install.md").open("a", encoding="utf-8") as guide:
        guide.write("\n[Project website](https://example.com/project)\n")
    monkeypatch.setattr(
        config, "_prepare_pdf_build_runtime", lambda *_a, **_k: (shutil.which("pandoc"), "")
    )
    runner = CliRunner()
    standard = runner.invoke(main, ["build", "--strict", "-f", str(portable_project)])
    assert standard.exit_code == 0, standard.output
    baseline = runner.invoke(main, ["pdf", "-f", str(portable_project)])
    assert baseline.exit_code == 0, baseline.output
    ordinary_pdf = root / "docs/site_documentation.pdf"
    expected = ordinary_pdf.read_bytes()
    portable = build(str(portable_project))
    # Never fall back to the ordinary HTML or overwrite its PDF.
    site = root / "site"
    (site / "index.html").write_text("ordinary site sentinel", encoding="utf-8")
    config_bytes = portable_project.read_bytes()
    result = runner.invoke(main, ["-p", "pdf", "--manifest", str(portable.manifest)])
    assert result.exit_code == 0, result.output
    rendered = portable.manifest.parent / "pdf/site_documentation.pdf"
    with (
        pymupdf.open(stream=expected, filetype="pdf") as a,
        pymupdf.open(rendered) as b,
    ):
        assert a.get_toc() == b.get_toc()
        assert [page.get_text() for page in a] == [page.get_text() for page in b]
        assert [page.rect for page in a] == [page.rect for page in b]
        assert any("1.1 Installation" in page.get_text() for page in b)
        assert any(
            link.get("uri") == "https://example.com/project"
            for page in b
            for link in page.get_links()
        )
    assert ordinary_pdf.read_bytes() == expected
    assert (site / "index.html").read_text() == "ordinary site sentinel"
    assert (portable.site / rendered.name).read_bytes() == expected
    assert portable_project.read_bytes() == config_bytes
    validate(portable, require_receipt=True)

    single = runner.invoke(
        main, ["--portable", "pdf", "--manifest", str(portable.manifest), "-m", "guide/install.md"]
    )
    assert single.exit_code == 0, single.output
    with pymupdf.open(portable.manifest.parent / "pdf/install.pdf") as document:
        text = "".join(page.get_text() for page in document)
        assert "Same page:" in text and "Unchanged table" not in text


def test_build_without_private_context_and_switch_back(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = portable_project.parent
    runner = CliRunner()
    result = runner.invoke(main, ["build", "-f", str(portable_project), "--clean", "--strict"])
    assert result.exit_code == 0, result.output
    original = _article(root / "site/index.html").select_one("a.prodockit-ref")
    assert original is not None
    # A separate Python startup hook makes private Prodockit context use fatal
    # in the child CLI as well as in preparation. Zensical may use its own API.
    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text("""import prodockit._zensical_page_context as context
def forbidden(*args, **kwargs):
    raise AssertionError("private page context was called")
context._rendering_context = forbidden
from prodockit.headings import HeadingsTreeprocessor
HeadingsTreeprocessor.run = forbidden
""")
    monkeypatch.setenv("PYTHONPATH", str(guard) + os.pathsep + os.environ["PYTHONPATH"])
    import prodockit._zensical_page_context as context

    with monkeypatch.context() as isolated:
        isolated.setattr(
            context, "_rendering_context", lambda *_: pytest.fail("private page context was called")
        )
        from prodockit.headings import HeadingsTreeprocessor

        isolated.setattr(
            HeadingsTreeprocessor, "run", lambda *_: pytest.fail("legacy heading adapter was called")
        )
        prepared = build(str(portable_project))
    portable = _article(prepared.site / "index.html")
    ref = portable.select_one("a.prodockit-ref")
    assert ref is not None
    assert (ref["href"], ref.get_text()) == (original["href"], original.get_text())
    assert portable.select_one("table") is not None
    assert (
        _article(prepared.site / "guide/install/index.html").select_one("figure.pdk-hotspots")
        is not None
    )
    assert json.loads((prepared.site / ".pdk-build.json").read_text())["mode"] == "portable"
    # Switching back never consumes the prepared tree, even if it is damaged.
    (prepared.config.parent / "docs/index.md").write_text("BROKEN PREPARED SOURCE")
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src"))
    result = runner.invoke(main, ["build", "-f", str(portable_project), "--clean", "--strict"])
    assert result.exit_code == 0, result.output
    assert (
        _article(root / "site/index.html").select_one("a.prodockit-ref").get_text()
        == "1.1 Installation"
    )


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="requires real Pandoc citeproc")
def test_bibliography_uses_citeproc_before_zensical_indexes(portable_project: Path) -> None:
    root = portable_project.parent
    with portable_project.open("a") as config:
        config.write(
            '\n[project.markdown_extensions."prodockit.bibliography"]\nbib_file = "references.bib"\n'
        )
    (root / "references.bib").write_text(
        "@book{example, title={A distinctive research title}, author={Doe, Jane}, year={2025}}\n"
    )
    with (root / "docs/index.md").open("a") as page:
        page.write("\nA citation: \\cite{example}.\n")
    with (root / "docs/references.md").open("a") as page:
        page.write("\n## Reference list\n\n\\bibliography\n")
    prepared = build(str(portable_project), pandoc=Path(shutil.which("pandoc")))
    soup = _article(prepared.site / "references/index.html")
    assert soup.find(id="ref-example") is not None
    assert soup.select_one('nav a[href="#reference-list"]') is not None
    link = _article(prepared.site / "index.html").select_one(".prodockit-bib-cite a")
    assert link["href"] == "references/#ref-example"
    assert (
        "a distinctive research title"
        in (prepared.config.parent / "docs/references.md").read_text().lower()
    )


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="requires real Pandoc citeproc")
@pytest.mark.parametrize(("backlinks", "numbered"), [(True, False), (True, True), (False, False)])
def test_page_bibliographies_match_legacy_in_real_builds(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch, backlinks: bool, numbered: bool
) -> None:
    pandoc = shutil.which("pandoc")
    assert pandoc
    root = portable_project.parent
    with portable_project.open("a", encoding="utf-8") as config:
        config.write(
            '\n[project.markdown_extensions.footnotes]\n'
            '[project.markdown_extensions."prodockit.bibliography"]\n'
            f'page_backlinks = {str(backlinks).lower()}\n'
            f'page_backlink_numbers = {str(numbered).lower()}\n'
        )
    (root / "references.bib").write_text(
        "@book{global, title={Global source}, author={Doe, Jane}, year={2025}}\n",
        encoding="utf-8",
    )
    alternate = root / "background.bib"
    alternate.write_text(
        "@book{local, title={Local source}, author={Roe, John}, year={2024}}\n"
        "@book{unused, title={Unused source}, author={Doe, Jane}, year={2023}}\n",
        encoding="utf-8",
    )
    guide = root / "docs/guide/install.md"
    guide.write_text(
        guide.read_text()
        + "\n\\pagebibliography{background.bib}{Sources & further reading}\n"
        "\nSee \\cite{local}, \\cite{global} and \\cite{local} again. Unknown \\cite{missing}.\n"
        "\n\\pagebibliography{ background.bib }{Duplicate title}\n"
        "\nLast authored paragraph.[^end]\n\n[^end]: A footnote.\n",
        encoding="utf-8",
    )
    index = root / "docs/index.md"
    index.write_text(
        index.read_text() + "\nSee \\cite{global}.\n\n\\pagebibliography{background.bib}\n",
        encoding="utf-8",
    )
    references = root / "docs/references.md"
    references.write_text(
        references.read_text() + "\nA citation to a local-only entry \\cite{local}.\n"
        "\n\\bibliography\n",
        encoding="utf-8",
    )
    originals = {path: path.read_bytes() for path in (guide, index, references, alternate)}

    guard = root / "runtime"
    guard.mkdir()
    startup = guard / "sitecustomize.py"
    startup.write_text(
        "from pathlib import Path\n"
        "import prodockit.bibliography as bibliography\n"
        f"bibliography._project_pandoc_executable = lambda: Path({pandoc!r})\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(guard) + os.pathsep + os.environ["PYTHONPATH"])
    result = CliRunner().invoke(
        main, ["build", "-f", str(portable_project), "--strict", "--clean"]
    )
    assert result.exit_code == 0, result.output

    def rendered(site: Path):
        soup = _article(site / "guide/install/index.html")
        title = soup.select_one("h2#sources-further-reading")
        assert title is not None and title.get_text(strip=True).startswith(
            "Sources & further reading"
        )
        assert soup.select_one('nav a[href="#sources-further-reading"]') is not None
        assert len(soup.select(".prodockit-page-bibliography")) == 1
        assert len(soup.select("#ref-local")) == 1 and soup.select_one("#ref-unused") is None
        assert soup.select_one("#ref-global") is None
        assert soup.select_one(".prodockit-bib-cite-unresolved").get_text() == "?"
        article = soup.select_one("article.md-content__inner")
        assert article.get_text().index("Last authored paragraph") < article.get_text().index(
            "Sources & further reading"
        ) < article.get_text().index("A footnote.")
        other_page = _article(site / "index.html")
        assert other_page.select_one(".prodockit-page-bibliography") is None
        assert other_page.select_one('.prodockit-bib-cite a')["href"] == "references/#ref-global"
        global_page = _article(site / "references/index.html")
        unlinked = global_page.select_one(".prodockit-bib-cite")
        assert unlinked is not None and "Roe 2024" in unlinked.get_text()
        assert unlinked.a is None
        assert global_page.select_one("#ref-local") is None
        citations = [
            (anchor.parent.get("id"), anchor["href"], anchor.get_text())
            for anchor in soup.select(".prodockit-bib-cite a")
        ]
        returns = [
            (anchor["href"], anchor.get_text(), anchor["aria-label"])
            for anchor in soup.select("#ref-local a.prodockit-bib-backlink")
        ]
        return citations, returns

    expected = rendered(root / "site")
    assert [href for _, href, _ in expected[0]] == [
        "#ref-local", "../../references/#ref-global", "#ref-local"
    ]
    assert len(expected[1]) == (2 if backlinks else 0)
    if backlinks:
        assert [href for href, _, _ in expected[1]] == [
            "#" + expected[0][0][0], "#" + expected[0][2][0]
        ]
        assert [label for _, label, _ in expected[1]] == (["↩1", "↩2"] if numbered else ["↩", "↩"])
    else:
        assert all(occurrence is None for occurrence, _, _ in expected[0])
    with startup.open("a", encoding="utf-8") as guard_file:
        guard_file.write(
            "def forbidden(*args, **kwargs):\n"
            "    raise AssertionError('legacy bibliography adaptor was called')\n"
            "bibliography.BibliographyExtension.extendMarkdown = forbidden\n"
        )
    prepared = build(str(portable_project), pandoc=Path(pandoc))
    assert rendered(prepared.site) == expected
    assert all(path.read_bytes() == data for path, data in originals.items())
    manifest = read_manifest(prepared.manifest)
    assert str(alternate) in manifest["captured_inputs"]
    if backlinks:
        built = prepared.site / "guide/install/index.html"
        rendered_html = _article(built)
        arrow = rendered_html.select_one("a.prodockit-bib-backlink")
        assert arrow is not None
        arrow.decompose()
        built.write_text(str(rendered_html), encoding="utf-8")
        with pytest.raises(PortableError, match=r"expected reference to guide/install.md#cite-"):
            validate(prepared)


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="requires real Pandoc citeproc")
def test_page_bibliography_uses_default_file_and_heading(portable_project: Path) -> None:
    with portable_project.open("a", encoding="utf-8") as config:
        config.write('\n[project.markdown_extensions."prodockit.bibliography"]\n')
    root = portable_project.parent
    (root / "references.bib").write_text(
        "@book{example, title={Default source}, author={Doe, Jane}, year={2025}}\n",
        encoding="utf-8",
    )
    source = root / "docs/index.md"
    source.write_text(source.read_text() + "\n\\pagebibliography\n\nSee \\cite{example}.\n")
    pandoc = shutil.which("pandoc")
    assert pandoc
    prepared = build(str(portable_project), pandoc=Path(pandoc))
    soup = _article(prepared.site / "index.html")
    assert soup.select_one("h2#references") is not None
    assert soup.select_one(".prodockit-page-bibliography #ref-example") is not None
    link = soup.select_one(".prodockit-bib-cite a")
    assert link is not None and link["href"] == "#ref-example"
    # With an overlapping global list on the same page, the local citation
    # would otherwise link to whichever entry Zensical happens to emit first.
    with source.open("a", encoding="utf-8") as page:
        page.write("\n\\bibliography\n")
    with pytest.raises(PortableError, match=r"index\.md: duplicate bibliography entry anchor"):
        build(str(portable_project), pandoc=Path(pandoc))


def test_default_wrapper_selects_nonstandard_configuration(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = portable_project.parent
    config = portable_project.rename(root / "custom.toml")
    source = root / "docs/index.md"
    source.write_text(source.read_text().replace("#home .unnumbered", "#home"))
    # An inherited override must not defeat the explicit per-invocation choice.
    monkeypatch.setenv("PRODOCKIT_CONFIG_FILE", str(root / "missing.toml"))
    result = CliRunner().invoke(main, ["build", "-f", str(config), "--strict"])
    assert result.exit_code == 0, result.output
    assert (
        _article(root / "site/index.html").select_one("a.prodockit-ref").get_text()
        == "2.1 Installation"
    )
    assert os.environ["PRODOCKIT_CONFIG_FILE"] == str(root / "missing.toml")


@pytest.mark.parametrize("numbering", ["continuous", "per-document"])
@pytest.mark.parametrize("directory_urls", [True, False])
def test_shared_semantics_match_across_build_modes(
    portable_project: Path, numbering: str, directory_urls: bool,
) -> None:
    root = portable_project.parent
    config = portable_project.read_text().replace(
        'site_name = "Portable prototype"',
        f'site_name = "Portable prototype"\nuse_directory_urls = {str(directory_urls).lower()}',
    ).replace('numbering = "continuous"', f'numbering = "{numbering}"\nappendix_attr = "annex"')
    portable_project.write_text(config)
    (root / "docs/index.md").write_text(r"""# Cover {: #cover .unnumbered }

# First {: #first }

Forward: \ref{second}, \autoref{detail}, \ref{cafe-tea}, \ref{overview_1}, \ref{note}.

Appendix: \ref{terms}. Back to cover: \ref{cover}.
""")
    (root / "docs/guide/install.md").write_text("""# Second {: #second }

### Detail

## Café & *tea*

## Overview

## Overview

## Note {: .unnumbered }
""")
    (root / "docs/references.md").write_text("""---
annex: true
---
# Appendix

## Terms
""")
    # A page outside navigation keeps per-document numbering even when its
    # front matter carries the appendix flag, matching the legacy approach.
    (root / "docs/loose.md").write_text("""---
annex: true
---
# Loose

Self: \\ref{loose}.
""")
    originals = {
        path: path.read_bytes()
        for path in [portable_project, *(root / "docs").rglob("*")]
        if path.is_file()
    }

    def references(site: Path) -> dict[str, list[tuple[str, str]]]:
        result = {}
        for page in site.rglob("*.html"):
            result[page.relative_to(site).as_posix()] = [
                (link.get_text(), str(link["href"]))
                for link in _article(page).select("a.prodockit-ref, a.prodockit-autoref")
            ]
        return result

    runner = CliRunner()
    normal = runner.invoke(main, ["build", "-f", str(portable_project), "--clean", "--strict"])
    assert normal.exit_code == 0, normal.output
    before = references(root / "site")
    chapter = "2" if numbering == "continuous" else "1"
    appendix = "A" if numbering == "continuous" else "1"
    assert [text for text, href in before["index.html"]] == [
        f"{chapter} Second", f"{chapter}.1.1 Detail", f"{chapter}.2 Café & tea",
        f"{chapter}.4 Overview", "Note", f"{appendix}.1 Terms", "Cover",
    ]
    prepared = build(str(portable_project))
    assert references(prepared.site) == before
    assert references(root / "site") == before
    manifest = json.loads(prepared.manifest.read_text())
    assert manifest["pages"]["loose.md"]["numbering"] == {
        "start_count": 0, "appendix_letter": None,
    }
    normal = runner.invoke(main, ["build", "-f", str(portable_project), "--clean", "--strict"])
    assert normal.exit_code == 0, normal.output
    assert references(root / "site") == before
    assert all(path.read_bytes() == contents for path, contents in originals.items())


@pytest.mark.parametrize("prefix", [["--portable"], ["-p"]])
def test_cli_aliases_and_opt_in(portable_project: Path, prefix: list[str]) -> None:
    result = CliRunner().invoke(main, [*prefix, "prepare", "-f", str(portable_project)])
    assert result.exit_code == 0, result.output
    assert "Prepared configuration:" in result.output
    assert CliRunner().invoke(main, ["prepare", "-f", str(portable_project)]).exit_code == 2
    assert CliRunner().invoke(main, [*prefix, "pdf"]).exit_code == 2


@pytest.mark.parametrize(
    "text",
    [
        "- A nested \\ref{target}.\n",
        "# Title\n\n{{ generated_heading() }}\n",
        '# Title\n\n--8<-- "snippet.md"\n',
        "# Title\n\n- Nested \\pagebibliography\n",
        "# Title\n\n- Nested \\citeref{key}\n",
        "Setext\n======\n",
        "# Title\n\n!!! note\n    \\ref{target}\n",
    ],
)
def test_refuses_unproved_constructs(text: str) -> None:
    with pytest.raises(PortableError):
        scan("guide/page.md", text)




_CONTAINER_EXTENSIONS = {
    "admonition", "pymdownx.details", "pymdownx.tabbed",
    "pymdownx.superfences", "prodockit.glossary", "prodockit.citations",
}


def test_native_containers_render_the_same_in_both_modes(portable_project: Path) -> None:
    root = portable_project.parent
    with portable_project.open("a", encoding="utf-8") as file:
        file.write(
            '\n[project.markdown_extensions.admonition]\n'
            '[project.markdown_extensions.pymdownx.details]\n'
            '[project.markdown_extensions.pymdownx.tabbed]\nalternate_style = true\n'
        )
    source = root / "docs/guide/install.md"
    containers = r"""
!!! warning "Native warning"

    Ordinary **formatted content** and a [link](../index.md#home).

    ???+ tip "Read more"

        A nested paragraph.

=== "macOS"

    !!! note "Literal examples"

        ```markdown
        ## Literal heading
        \ref{literal-reference}
        ```

=== "Ubuntu"

    Prose with an inline `\ref{literal-reference}` example.

## After containers

See \ref{installation}.
"""
    with source.open("a", encoding="utf-8") as page:
        page.write(containers)
    originals = {path: path.read_bytes() for path in (portable_project, source)}
    runner = CliRunner()
    args = ["build", "--strict", "--clean", "-f", str(portable_project)]
    normal = runner.invoke(main, args)
    assert normal.exit_code == 0, normal.output
    prepared = build(str(portable_project))
    generated = (prepared.config.parent / "docs/guide/install.md").read_text(encoding="utf-8")
    native = containers.split("\n## After containers", maxsplit=1)[0]
    assert native in generated
    expected = _article(root / "site/guide/install/index.html")
    rendered = _article(prepared.site / "guide/install/index.html")
    for selector in ("article > .admonition", "article > .tabbed-set"):
        ordinary_container = expected.select_one(selector)
        portable_container = rendered.select_one(selector)
        assert ordinary_container is not None and portable_container == ordinary_container
    assert rendered.select_one("details[open] summary").get_text(strip=True) == "Read more"
    assert "\\ref{literal-reference}" in rendered.select_one(".tabbed-set pre").get_text()
    assert [heading["id"] for heading in rendered.select("article h2")] == [
        "installation", "after-containers",
    ]
    validate(prepared, require_receipt=True)
    assert all(path.read_bytes() == data for path, data in originals.items())
    switched = runner.invoke(main, args)
    assert switched.exit_code == 0, switched.output
    assert _article(root / "site/guide/install/index.html").select_one("article") == (
        expected.select_one("article")
    )


@pytest.mark.parametrize(
    ("body", "line", "message"),
    [
        ("!!! note\n\n    See \\ref{topic}.", 5, "nested content"),
        ('!!! note "See \\ref{topic}"\n\n    Text.', 3, "nested content"),
        ('=== "Tab"\n\n    !!! note\n\n        \\pagebibliography', 7, "nested content"),
        ('???+ note "Summary"\n\n    ## New heading', 5, "top-level ATX"),
        ('??? note "# Summary"\n\n    Text.', 3, "headings in collapsible titles"),
        ('=== "Tab"\n\n    Entry\n    {: #term data-term="Term" }', 5,
         "top-level paragraph"),
        ('=== "Tab"\n\n    Entry\n    {: #ref data-cite-text="Author" }', 5,
         "top-level paragraph"),
        ('!!! note\n\n    ```image-hotspots\n    image: map.svg\n    ```', 5, "nested hotspots"),
        ('!!! note\n\n    ```markdown\n    \\ref{topic}', 5, "aligned, closed SuperFences"),
        ('!!! note\n\n    ```markdown\n    \\ref{topic}\n     ```', 5,
         "aligned, closed SuperFences"),
        ('!!! note\n\n        \\ref{topic}', 5, "use a closed fence"),
        ('!!! note\n\n    ![Map](map.svg)\n    /// figure-caption\n    Map\n    ///', 6,
         "numbered captions in native containers"),
        ('!!! note\n\n    <div markdown="1">\n    ## Generated heading\n    </div>', 5,
         "affected syntax in HTML"),
    ],
)
def test_native_containers_report_affected_syntax(body: str, line: int, message: str) -> None:
    with pytest.raises(PortableError, match=rf"index\.md:{line}: .*{message}"):
        scan("index.md", f"# Home\n\n{body}\n", extensions=_CONTAINER_EXTENSIONS)



def _configure_portable_macros(config: Path) -> Path:
    with config.open("a", encoding="utf-8") as file:
        file.write(
            '\n[project.markdown_extensions."zensical.extensions.macros"]\n'
            'module_name = "local_macros"\non_error_fail = true\n'
        )
    module = config.parent / "local_macros.py"
    module.write_text(
        '"""Load the standard Prodockit macros."""\n'
        'from prodockit.zensical_macros import define_env as define_env\n',
        encoding="utf-8",
    )
    return module


@pytest.mark.parametrize(
    ("appendix", "enabled", "css"),
    [(False, True, "counter-reset: h1-count 1"),
     (True, True, 'content: "Appendix A. "'),
     (False, False, 'content: "" !important')],
)
def test_portable_heading_counter_and_native_styling_match(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch, appendix: bool, enabled: bool, css: str
) -> None:
    root = portable_project.parent
    module = _configure_portable_macros(portable_project)
    with portable_project.open("a", encoding="utf-8") as file:
        file.write(f'\n[project.extra]\nheading_numbering = {str(enabled).lower()}\n')
    home = root / "docs/index.md"
    home.write_text(
        home.read_text(encoding="utf-8").replace("# Home {: #home .unnumbered }", "# Home {: #home }"),
        encoding="utf-8",
    )
    source = root / "docs/guide/install.md"
    source.write_text(
        ("---\nis_appendix: true\n---\n\n" if appendix else "")
        + "{{ heading_counter_reset(page) }}\n\n"
        + "{{ pdk_reference_style() }}\n\n"
        + "`{% raw %}{{ pdk_heading_counter_reset(page) }}{% endraw %}`\n\n"
        + source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    originals = {path: path.read_bytes() for path in (home, source, module, portable_project)}
    runner = CliRunner()
    args = ["build", "--clean", "--strict", "-f", str(portable_project)]
    ordinary = runner.invoke(main, args)
    assert ordinary.exit_code == 0, ordinary.output
    path = "guide/install/index.html"
    baseline = _article(root / "site" / path)
    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        """import prodockit.zensical_macros as macros

def forbidden(*args, **kwargs):
    raise AssertionError("legacy macro pre-scan was called")

macros.prescan = forbidden
""",
        encoding="utf-8",
    )
    with monkeypatch.context() as isolated:
        isolated.setenv("PYTHONPATH", str(guard) + os.pathsep + os.environ["PYTHONPATH"])
        prepared = build(str(portable_project))
    portable = _article(prepared.site / path)
    normal_styles = [node.get_text() for node in baseline.select("article > style")]
    assert any(css in style for style in normal_styles)
    assert any("p.reference + p.reference" in style for style in normal_styles)
    assert [node.get_text() for node in portable.select("article > style")] == normal_styles
    assert portable.find("code", string="{{ pdk_heading_counter_reset(page) }}") is not None
    generated = (prepared.config.parent / "docs/guide/install.md").read_text(encoding="utf-8")
    assert "{{ pdk_reference_style() }}" in generated
    assert "{{ heading_counter_reset(page) }}" not in generated
    assert read_manifest(prepared.manifest)["generated_hashes"]["macros.py"]
    assert all(path.read_bytes() == data for path, data in originals.items())
    validate(prepared, require_receipt=True)
    switched = runner.invoke(main, args)
    assert switched.exit_code == 0, switched.output
    assert [node.get_text() for node in _article(root / "site" / path).select("article > style")] == (
        normal_styles
    )
    (prepared.config.parent / "macros.py").write_text("changed", encoding="utf-8")
    with pytest.raises(PortableError, match="prepared input changed"):
        validate(prepared)


@pytest.mark.parametrize("template", [
    "{{ make_heading() }}", "{% if is_surrey %}\n# Heading\n{% endif %}",
    "```jinja\n{{ pdk_heading_counter_reset(page) }}\n```",
    "Inline {{ pdk_heading_counter_reset(page) }}",
    "{{ pdk_heading_counter_reset(page) }}\nSame paragraph",
])
def test_portable_refuses_unqualified_macro_rendering(portable_project: Path, template: str) -> None:
    _configure_portable_macros(portable_project)
    page = portable_project.parent / "docs/index.md"
    page.write_text(f"# Home\n\n{template}\n", encoding="utf-8")
    with pytest.raises(PortableError, match=r"index\.md:[34]: (unsupported template|put portable)"):
        prepare(str(portable_project))


def test_portable_refuses_project_macro_initialisation(portable_project: Path) -> None:
    module = _configure_portable_macros(portable_project)
    with module.open("a", encoding="utf-8") as file:
        file.write("\nprint('custom startup')\n")
    with pytest.raises(PortableError, match="plain define_env re-export"):
        prepare(str(portable_project))


@pytest.mark.parametrize("theme_path", ["theme-overrides", "docs/theme-overrides"])
def test_custom_theme_build_parity_and_freshness(portable_project: Path, theme_path: str) -> None:
    from prodockit.project_config import load_project_config

    root = portable_project.parent
    config = portable_project.read_text(encoding="utf-8").replace(
        "[project.theme]", f'[project.theme]\ncustom_dir = "{theme_path}"'
    )
    portable_project.write_text(config, encoding="utf-8")
    overrides = root / theme_path
    (overrides / "partials").mkdir(parents=True)
    (overrides / "main.html").write_text(
        '{% extends "base.html" %}\n'
        '{% block extrahead %}{{ super() }}\n'
        '{% include "partials/portable-marker.html" %}\n'
        '{% endblock %}',
        encoding="utf-8",
    )
    marker = '<meta name="portable-theme" content="original">'
    partial = overrides / "partials/portable-marker.html"
    partial.write_text(marker, encoding="utf-8")

    runner = CliRunner()
    ordinary = runner.invoke(main, ["build", "--strict", "-f", str(portable_project)])
    assert ordinary.exit_code == 0, ordinary.output
    prepared = build(str(portable_project))
    generation = prepared.config.parent
    prepared_data = load_project_config(prepared.config).project
    captured = generation / prepared_data["theme"]["custom_dir"]
    assert captured.is_relative_to(generation / ".inputs")
    assert marker in (root / "site/index.html").read_text(encoding="utf-8")
    assert marker in (prepared.site / "index.html").read_text(encoding="utf-8")
    assert read_manifest(prepared.manifest)["captured_inputs"][str(partial)] == (
        captured.relative_to(generation) / "partials/portable-marker.html"
    ).as_posix()
    validate(prepared, require_receipt=True)
    assert portable_project.read_text(encoding="utf-8") == config
    assert partial.read_text(encoding="utf-8") == marker

    partial.write_text(marker.replace("original", "revised"), encoding="utf-8")
    with pytest.raises(PortableError, match="stale"):
        validate(prepared)
    updated = build(str(portable_project))
    assert 'content="revised"' in (updated.site / "index.html").read_text(encoding="utf-8")
    assert marker in (prepared.site / "index.html").read_text(encoding="utf-8")
    (captured / "partials/portable-marker.html").write_text("tampered", encoding="utf-8")
    with pytest.raises(PortableError, match="prepared input changed"):
        validate(prepared, fresh=False)


def test_custom_theme_rejects_symlinked_template(portable_project: Path) -> None:
    root = portable_project.parent
    source = portable_project.read_text(encoding="utf-8").replace(
        "[project.theme]", '[project.theme]\ncustom_dir = "overrides"'
    )
    portable_project.write_text(source, encoding="utf-8")
    theme = root / "overrides"
    theme.mkdir()
    try:
        (theme / "main.html").symlink_to(root / "docs/index.md")
    except OSError as error:
        pytest.skip(f"cannot create a symlink: {error}")
    with pytest.raises(PortableError, match="symlinked source"):
        prepare(str(portable_project))



@pytest.mark.parametrize("name", ["legal/LICENCE.txt", "docs/assets/example.txt"])
def test_native_fenced_snippet_parity(portable_project: Path, name: str) -> None:
    root = portable_project.parent
    with portable_project.open("a", encoding="utf-8") as config:
        config.write('\n[project.markdown_extensions.pymdownx.snippets]\n')
    source = root / "docs/index.md"
    with source.open("a", encoding="utf-8") as page:
        page.write(f'\n```text\n--8<-- "{name}"\n```\n')
    included = root / name
    included.parent.mkdir(parents=True, exist_ok=True)
    included.write_text("Licence example\n# Still code\n\\ref{also-code}\n", encoding="utf-8")

    runner = CliRunner()
    ordinary = runner.invoke(main, ["build", "--strict", "-f", str(portable_project)])
    assert ordinary.exit_code == 0, ordinary.output
    prepared = build(str(portable_project))
    assert str(included) in read_manifest(prepared.manifest)["input_hashes"]
    assert f'--8<-- "{name}"' in (prepared.config.parent / "docs/index.md").read_text(
        encoding="utf-8"
    )
    standard_blocks = _article(root / "site/index.html").select("pre")
    prepared_blocks = _article(prepared.site / "index.html").select("pre")
    assert [block.get_text() for block in standard_blocks] == [
        block.get_text() for block in prepared_blocks
    ]
    assert any("# Still code" in block.get_text() for block in prepared_blocks)
    validate(prepared, require_receipt=True)
    included.write_text("Updated licence\n", encoding="utf-8")
    with pytest.raises(PortableError, match="stale"):
        validate(prepared)
    updated = build(str(portable_project))
    assert "Updated licence" in (updated.site / "index.html").read_text(encoding="utf-8")
    assert "Licence example" in (prepared.site / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("directive", "body", "message"),
    [
        ('--8<-- "example.txt"', "Text", "whole-file includes in fences"),
        ('```text\n--8<-- "example.txt"\n```', "```\n# Heading",
         "introduce a fence or an include"),
        ('```text\n--8<-- "example.txt:1"\n```', "Text", "project-relative file path"),
        ('```text\n--8<-- "../example.txt"\n```', "Text", "project-relative file path"),
    ],
)
def test_portable_snippets_reject_unproved_expansion(
    portable_project: Path, directive: str, body: str, message: str,
) -> None:
    with portable_project.open("a", encoding="utf-8") as config:
        config.write('\n[project.markdown_extensions.pymdownx.snippets]\n')
    root = portable_project.parent
    (root / "docs/index.md").write_text(f"# Home\n\n{directive}\n", encoding="utf-8")
    (root / "example.txt").write_text(body, encoding="utf-8")
    with pytest.raises(PortableError, match=rf"index\.md:[34]: .*{message}"):
        prepare(str(portable_project))



def test_stale_inputs_and_missing_output_are_detected(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    (prepared.site / "guide/install/index.html").unlink()
    with pytest.raises(PortableError, match="build is incomplete"):
        validate(prepared)
    source = portable_project.parent / "docs/index.md"
    source.write_text(source.read_text() + "\nNew content\n")
    with pytest.raises(PortableError, match="stale"):
        validate(prepared)


def test_unresolved_target_does_not_replace_existing_output(portable_project: Path) -> None:
    good = build(str(portable_project))
    previous = (good.site / "index.html").read_bytes()
    source = portable_project.parent / "docs/index.md"
    source.write_text(source.read_text().replace("ref{installation}", "ref{missing}"))
    with pytest.raises(PortableError, match=r"index\.md:3: unresolved reference"):
        build(str(portable_project))
    assert (good.site / "index.html").read_bytes() == previous


def test_generated_input_tampering_is_detected(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    (prepared.config.parent / "docs/index.md").write_text("changed")
    with pytest.raises(PortableError, match="prepared input changed"):
        validate(prepared)


def test_wrong_reference_label_is_rejected(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    page = prepared.site / "index.html"
    page.write_text(page.read_text().replace(">1.1 Installation</a>", ">??</a>"))
    with pytest.raises(PortableError, match="label changed"):
        validate(prepared)


def test_image_dependency_invalidates_output(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    Image.new("RGB", (400, 200)).save(portable_project.parent / "docs/assets/map.png")
    with pytest.raises(PortableError, match="stale"):
        validate(prepared)


def test_heading_rendering_drift_is_rejected(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    page = prepared.site / "guide/install/index.html"
    page.write_text(
        page.read_text().replace('id="installation">Installation', 'id="installation">Changed')
    )
    with pytest.raises(PortableError, match="differs from its collected text"):
        validate(prepared)


@pytest.mark.parametrize("startup_error", [None, PortableError, OSError])
def test_preview_handles_edits_during_startup_and_failed_replacement(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch, startup_error: type[Exception] | None
) -> None:
    from prodockit.portable import project

    starts = []
    contents = []
    processes = []
    reports = []
    source = portable_project.parent / "docs/guide/install.md"

    def start(prepared, address):
        starts.append(prepared)
        contents.append((prepared.site / "guide/install/index.html").read_text())
        if len(starts) == 1:
            # The first validated generation is already built at this point.
            source.write_text(source.read_text().replace(
                "## Installation", "## During startup {: #installation }"
            ))
        elif len(starts) == 2 and startup_error is not None:
            raise startup_error("replacement preview could not start")
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        processes.append(process)
        return process

    def report(message):
        reports.append(message)
        if "updated" in message:
            raise KeyboardInterrupt

    polls = 0
    clock = 0.0

    def tick(_):
        nonlocal polls, clock
        polls += 1
        clock += 5 if polls == 3 else 0.5
        if polls == 3:
            assert len(starts) == 3  # Retried only after allowing the old preview to run.
        if polls > 3:
            pytest.fail("the preview did not retry the unchanged source snapshot")

    monkeypatch.setattr(project, "_start", start)
    monkeypatch.setattr(project.time, "sleep", tick)
    monkeypatch.setattr(project.time, "monotonic", lambda: clock)
    with pytest.raises(KeyboardInterrupt):
        project.serve(str(portable_project), report=report)
    assert len(starts) == (4 if startup_error is not None else 2)
    assert "During startup" in contents[-1]
    if startup_error is not None:
        assert starts[2] == starts[0]
        assert not starts[1].config.parent.exists()
        assert sum("replacement preview could not start" in report for report in reports) == 1
    for process in processes:
        process.terminate.assert_called_once()
    assert not (portable_project.parent / ".pdk/portable/lock").exists()


def test_failed_build_discards_only_its_candidate(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prodockit.portable import project

    previous = build(str(portable_project))
    old_site = (previous.site / "index.html").read_bytes()
    candidates = []

    def fail(prepared, **_options):
        candidates.append(prepared)
        prepared.site.mkdir()
        (prepared.site / "index.html").write_text("incomplete", encoding="utf-8")
        raise PortableError("validation failed")

    monkeypatch.setattr(project, "_build", fail)
    with pytest.raises(PortableError, match="validation failed"):
        build(str(portable_project))
    assert len(candidates) == 1 and not candidates[0].config.parent.exists()
    assert (previous.site / "index.html").read_bytes() == old_site


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="requires real Pandoc citeproc")
def test_preview_rebuilds_when_only_the_bibliography_changes(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prodockit.portable import project

    root = portable_project.parent
    with portable_project.open("a", encoding="utf-8") as config:
        config.write('\n[project.markdown_extensions."prodockit.bibliography"]\n')
    source = root / "docs/index.md"
    with source.open("a", encoding="utf-8") as page:
        page.write("\nSee \\cite{guide}.\n\n\\pagebibliography\n")
    original = source.read_bytes()
    bibliography = root / "references.bib"
    before = "@book{guide, title={Guide}, author={Doe, Jane}, year={2025}}\n"
    bibliography.write_text(before, encoding="utf-8")
    labels = []

    def start(prepared, _address):
        soup = _article(prepared.site / "index.html")
        labels.append(soup.select_one(".prodockit-bib-cite").get_text())
        if len(labels) == 1:
            bibliography.write_text(before.replace("2025", "2026"), encoding="utf-8")
        child = Mock(spec=subprocess.Popen)
        child.poll.return_value = None
        return child

    def report(message):
        if "updated" in message:
            raise KeyboardInterrupt

    polls = 0

    def tick(_):
        nonlocal polls
        polls += 1
        if polls > 3:
            pytest.fail("editing the bibliography did not trigger a preview rebuild")

    monkeypatch.setattr(project, "_start", start)
    monkeypatch.setattr(project.time, "sleep", tick)
    pandoc = shutil.which("pandoc")
    assert pandoc
    with pytest.raises(KeyboardInterrupt):
        project.serve(str(portable_project), pandoc=Path(pandoc), report=report)
    assert labels == ["(Doe 2025)", "(Doe 2026)"]
    assert source.read_bytes() == original


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX SIGINT acceptance; Windows lifecycle needs separate qualification",
)
def test_live_preview_rebuild_recovery_and_switching(portable_project: Path) -> None:
    root = portable_project.parent
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    address = f"127.0.0.1:{port}"

    def fetch() -> str:
        try:
            with urllib.request.urlopen(f"http://{address}/", timeout=0.5) as response:
                soup = BeautifulSoup(response.read(), "html.parser")
            link = soup.select_one("a.prodockit-ref")
            return link.get_text() if link is not None else ""
        except (OSError, urllib.error.URLError):
            return ""

    def await_value(expected: str, process: subprocess.Popen, log: Path) -> None:
        until = time.monotonic() + 25
        while time.monotonic() < until:
            assert process.poll() is None, log.read_text()
            if fetch() == expected:
                return
            time.sleep(0.1)
        pytest.fail(f"preview did not reach {expected!r}: {log.read_text()}")

    def await_error(message: str, process: subprocess.Popen) -> None:
        until = time.monotonic() + 15
        while time.monotonic() < until:
            assert process.poll() is None, log.read_text()
            if message in log.read_text():
                return
            time.sleep(0.1)
        pytest.fail(f"preview did not report {message!r}: {log.read_text()}")

    def status(path: str) -> int:
        try:
            with urllib.request.urlopen(f"http://{address}/{path}", timeout=2) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    source = root / "docs/guide/install.md"
    log = root / "preview.log"
    with log.open("w") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "prodockit",
                "-p",
                "serve",
                "-f",
                str(portable_project),
                "-a",
                address,
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            await_value("1.1 Installation", process, log)
            source.write_text(
                source.read_text().replace(
                    "## Installation", "## Updated installation {: #installation }"
                )
            )
            await_value("1.1 Updated installation", process, log)
            edited = source.read_text()
            source.write_text("---\ntitle: [\n---\n\n" + edited)
            await_error("invalid YAML front matter", process)
            assert fetch() == "1.1 Updated installation"
            source.write_text(edited)
            home = root / "docs/index.md"
            original = home.read_text()
            home.write_text(original.replace("ref{installation}", "ref{missing}"))
            await_error("unresolved reference 'missing'", process)
            assert fetch() == "1.1 Updated installation"
            home.write_text(original)
            source.write_text(
                source.read_text().replace("Updated installation", "Final installation")
            )
            await_value("1.1 Final installation", process, log)

            renamed = source.rename(source.with_name("renamed.md"))
            await_error("navigation pages are missing: guide/install.md", process)
            assert status("guide/install/") == 200
            config = portable_project.read_text()
            portable_project.write_text(config.replace("guide/install.md", "guide/renamed.md"))
            renamed.write_text(renamed.read_text().replace("Final installation", "Renamed guide"))
            await_value("1.1 Renamed guide", process, log)
            assert status("guide/renamed/") == 200
            assert status("guide/install/") == 404

            renamed.unlink()
            await_error("navigation pages are missing: guide/renamed.md", process)
            assert status("guide/renamed/") == 200
            portable_project.write_text(config.replace('{Guide = "guide/install.md"}, ', ""))
            home.write_text(original.replace("{installation}", "{home}"))
            await_value("Home", process, log)
            assert status("guide/renamed/") == 404
        finally:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
        assert process.returncode == 0, log.read_text()
    assert not (root / ".pdk/portable/lock").exists()
    # The same original project can immediately be served through the other path.
    with log.open("w") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "prodockit",
                "serve",
                "-f",
                str(portable_project),
                "-a",
                address,
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            await_value("Home", process, log)
        finally:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
        assert process.returncode == 0, log.read_text()
