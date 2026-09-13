# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from prodockit.pdf.build import Page
from prodockit.pdf.web_render import (
    RenderTarget,
    WebRenderError,
    check_web_rendering,
    static_render_targets,
)
from prodockit.project_config import load_project_config
from prodockit.renderer_health import find_browser


def _project(tmp_path: Path, source: str):
    (tmp_path / "zensical.toml").write_text('[project]\nsite_name = "Example"\n', encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text(source, encoding="utf-8")
    return load_project_config(tmp_path / "zensical.toml")


def test_real_maths_and_mermaid_map_to_built_markup(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        "<!-- $$hidden$$ -->\n`$$example$$`\n\n"
        "$$\nx^2\n$$\n\n"
        "<!--\n```mermaid\nA --- B\n```\n-->\n"
        "```mermaid\ngraph LR\n  A --> B\n```\n",
    )
    page = Page(
        "index.md",
        "<p><code>$$example$$</code></p>"
        '<div class="arithmatex">\\[x^2\\]</div>'
        '<pre class="mermaid"><code>graph LR</code></pre>',
    )

    assert static_render_targets(config, [page]) == [
        RenderTarget(source="index.md", route="/", maths=1, mermaid=1)
    ]


@pytest.mark.parametrize(
    ("source", "html", "missing"),
    [
        ("$$\nx^2\n$$\n", "<p>raw x^2</p>", "arithmatex"),
        ("$$x$$ and $$y$$", '<div class="arithmatex">\\[x\\]</div>', "arithmatex"),
        ("```mermaid\ngraph LR\n  A --> B\n```", "<pre>graph LR</pre>", "pre.mermaid"),
        (
            "```mermaid\ngraph LR\nA --> B\n```\n```mermaid\ngraph LR\nC --> D\n```",
            '<pre class="mermaid">graph LR</pre>',
            "pre.mermaid",
        ),
    ],
)
def test_missing_built_renderer_element_fails_before_pdf(
    tmp_path: Path, source: str, html: str, missing: str
) -> None:
    config = _project(tmp_path, source)
    with pytest.raises(WebRenderError, match=missing):
        static_render_targets(config, [Page("index.md", html)])


def test_comments_and_quoted_examples_do_not_require_rendering(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        "<!-- $$hidden$$ -->\n"
        "`$$literal$$`\n\n"
        "```text\n$$example$$\n```\n"
        "<!--\n```mermaid\nA --- B\n```\n-->\n",
    )
    page = Page(
        "index.md",
        '<!-- <div class="arithmatex">\\[hidden\\]</div> '
        '<pre class="mermaid">A --- B</pre> -->'
        "<p><code>$$literal$$</code></p>",
    )
    assert static_render_targets(config, [page]) == []
    check_web_rendering(config, [page])  # No browser prerequisite for examples only.


def test_front_matter_math_is_not_article_content(tmp_path: Path) -> None:
    config = _project(tmp_path, '---\ntitle: "$$metadata$$"\n---\n\n# Page\n')
    assert static_render_targets(config, [Page("index.md", "<h1>Page</h1>")]) == []


def test_nested_lists_tabs_and_grids_match_real_zensical_output(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "pdf_web_render_nested"
    shutil.copytree(fixture, tmp_path, dirs_exist_ok=True)
    result = subprocess.run(
        [sys.executable, "-m", "zensical", "build", "--clean", "--strict"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    article = BeautifulSoup(
        (tmp_path / "site" / "index.html").read_text(encoding="utf-8"), "html.parser"
    ).select_one("article.md-content__inner.md-typeset")
    assert article is not None
    assert len(article.select("ol .arithmatex")) == 1
    assert len(article.select(".task-list-item .arithmatex")) == 1
    assert len(article.select("dl .arithmatex")) == 1
    assert len(article.select(".grid .tabbed-set .arithmatex")) == 2
    assert static_render_targets(
        load_project_config(tmp_path / "zensical.toml"), [Page("index.md", str(article))]
    ) == [RenderTarget("index.md", "/", maths=9, mermaid=9)]


def test_active_maths_in_blockquote_is_not_suppressed(tmp_path: Path) -> None:
    config = _project(tmp_path, "> $$x^2$$\n")
    with pytest.raises(WebRenderError, match="arithmatex"):
        static_render_targets(config, [Page("index.md", "<blockquote>x^2</blockquote>")])


def test_active_mermaid_in_blockquote_is_not_suppressed(tmp_path: Path) -> None:
    config = _project(tmp_path, "> ```mermaid\n> graph LR\n>   A --> B\n> ```\n")
    with pytest.raises(WebRenderError, match=r"pre\.mermaid"):
        static_render_targets(config, [Page("index.md", "<blockquote>graph LR</blockquote>")])


def test_browser_prerequisite_is_an_explicit_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _project(tmp_path, "$$x^2$$")
    monkeypatch.setattr("prodockit.pdf.web_render.shutil.which", lambda _: None)
    with pytest.raises(WebRenderError, match=r"Node\.js"):
        check_web_rendering(config, [Page("index.md", '<div class="arithmatex">\\[x^2\\]</div>')])


def test_browser_failure_keeps_diagnostics_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _project(tmp_path, "$$x^2$$")
    module = tmp_path / "tools" / "mathjax" / "node_modules" / "puppeteer-core"
    module.mkdir(parents=True)
    browser = tmp_path / "chrome"
    browser.write_text("", encoding="utf-8")
    monkeypatch.setattr("prodockit.pdf.web_render.shutil.which", lambda _: "/usr/bin/node")
    monkeypatch.setattr("prodockit.pdf.web_render.find_browser", lambda: str(browser))
    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir()
    monkeypatch.setattr("prodockit.pdf.web_render.tempfile.mkdtemp", lambda **_: str(diagnostics))
    seen: dict = {}

    def failed_run(command, **kwargs):
        seen.update(json.loads(kwargs["input"]))
        return SimpleNamespace(returncode=1, stderr="no visible SVG", stdout="")

    monkeypatch.setattr("prodockit.pdf.web_render.subprocess.run", failed_run)
    with pytest.raises(WebRenderError, match="no visible SVG"):
        check_web_rendering(config, [Page("index.md", '<div class="arithmatex">\\[x^2\\]</div>')])
    assert seen["targets"][0]["maths"] == 1
    assert seen["targets"][0]["mermaid"] == 0
    assert Path(seen["diagnostics"]).is_dir()


@pytest.mark.parametrize(
    ("math_format", "missing"),
    [
        ("svg", None),
        ("chtml", None),
        ("katex", None),
        ("svg", "maths"),
        ("svg", "mermaid"),
    ],
)
def test_real_browser_checks_both_renderers_and_navigation(
    tmp_path: Path, math_format: str, missing: str | None
) -> None:
    node = shutil.which("node")
    browser = find_browser()
    module = Path(
        os.environ.get(
            "PDK_BROWSER_TEST_PUPPETEER",
            str(Path(__file__).parents[1] / "tools/mermaid/node_modules/puppeteer"),
        )
    )
    if not node or not browser or not module.is_dir():
        pytest.skip("Node, Chrome and the CI Puppeteer install are required")

    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        '<article class="md-content__inner md-typeset"><a href="/example/">Examples</a></article>',
        encoding="utf-8",
    )
    example = site / "example"
    example.mkdir()
    math_markup = {
        "svg": '<mjx-container><svg width="40" height="20"></svg></mjx-container>',
        "chtml": "<mjx-container><mjx-math>x²</mjx-math></mjx-container>",
        "katex": '<span class="katex"><span class="katex-html">x²</span></span>',
    }[math_format]
    math_script = (
        ""
        if missing == "maths"
        else (f"document.querySelector('.arithmatex').innerHTML = {json.dumps(math_markup)};")
    )
    mermaid_script = (
        ""
        if missing == "mermaid"
        else (
            "document.querySelector('.mermaid').innerHTML = "
            '\'<svg width="40" height="20"></svg>\';'
        )
    )
    (example / "index.html").write_text(
        '<article class="md-content__inner md-typeset">'
        '<div class="arithmatex">\\[x^2\\]</div>'
        '<pre class="mermaid">graph LR</pre></article>'
        f"<script>setTimeout(() => {{ {math_script} {mermaid_script} }}, 50)</script>",
        encoding="utf-8",
    )
    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir()
    payload = {
        "siteDir": str(site),
        "puppeteerModule": str(module),
        "browser": browser,
        "targets": [{"source": "example.md", "route": "/example/", "maths": 1, "mermaid": 1}],
        "instantNavigation": True,
        "startRoute": "/",
        "diagnostics": str(diagnostics),
        "timeoutMs": 1000,
    }
    result = subprocess.run(
        [node, str(Path(__file__).parents[1] / "src/prodockit/pdf/web_render.cjs")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    if missing is None:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert ("rendered equation" if missing == "maths" else "Mermaid") in result.stderr
        assert list(diagnostics.glob("*.html"))
        assert list(diagnostics.glob("*.png"))


@pytest.mark.parametrize("second_math_renders", [True, False])
def test_real_browser_visits_inactive_content_tabs(
    tmp_path: Path, second_math_renders: bool
) -> None:
    node = shutil.which("node")
    browser = find_browser()
    module = Path(
        os.environ.get(
            "PDK_BROWSER_TEST_PUPPETEER",
            str(Path(__file__).parents[1] / "tools/mermaid/node_modules/puppeteer"),
        )
    )
    if not node or not browser or not module.is_dir():
        pytest.skip("Node, Chrome and the CI Puppeteer install are required")

    site = tmp_path / "site"
    site.mkdir()
    blocks = (
        '<div class="tabbed-block"><div class="arithmatex">\\[x\\]</div>'
        '<pre class="mermaid">graph LR</pre></div>'
    ) * 2
    (site / "index.html").write_text(
        "<style>.tabbed-block{display:none}"
        "#t1:checked ~ .tabbed-content .tabbed-block:first-child{display:block}"
        "#t2:checked ~ .tabbed-content .tabbed-block:last-child{display:block}</style>"
        '<article class="md-content__inner md-typeset"><div class="tabbed-set">'
        '<input id="t1" name="tabs" type="radio" checked>'
        '<input id="t2" name="tabs" type="radio">'
        '<div class="tabbed-labels"><label for="t1">One</label>'
        '<label for="t2">Two</label></div>'
        f'<div class="tabbed-content">{blocks}</div></div></article>'
        "<script>setTimeout(() => {"
        'document.querySelectorAll(".mermaid").forEach(host => '
        'host.innerHTML = "<svg width=40 height=20></svg>");'
        'document.querySelectorAll(".arithmatex").forEach((host, index) => {'
        f"if (index === 0 || {str(second_math_renders).lower()}) "
        'host.innerHTML = "<mjx-container><svg width=40 height=20></svg></mjx-container>";'
        "});}, 50)</script>",
        encoding="utf-8",
    )
    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir()
    result = subprocess.run(
        [node, str(Path(__file__).parents[1] / "src/prodockit/pdf/web_render.cjs")],
        input=json.dumps(
            {
                "siteDir": str(site),
                "puppeteerModule": str(module),
                "browser": browser,
                "targets": [{"source": "index.md", "route": "/", "maths": 2, "mermaid": 2}],
                "instantNavigation": False,
                "diagnostics": str(diagnostics),
                "timeoutMs": 1000,
            }
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=25,
        check=False,
    )
    if second_math_renders:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert "index.md" in result.stderr
