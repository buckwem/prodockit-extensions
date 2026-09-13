# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Validate website maths and diagrams before a built-site PDF succeeds."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from prodockit.pdf.build import Page
from prodockit.pdf.site import BuiltSiteError, output_path
from prodockit.project_config import ProjectConfig
from prodockit.project_integrity import count_math_expressions, count_mermaid_fences
from prodockit.renderer_health import find_browser


class WebRenderError(BuiltSiteError):
    """A published page did not render its configured maths or diagrams."""


@dataclass(frozen=True)
class RenderTarget:
    source: str
    route: str
    maths: int
    mermaid: int


def _route(config: ProjectConfig, source: str) -> str:
    built = output_path(
        source,
        config.site_dir,
        directory_urls=bool(config.project.get("use_directory_urls", True)),
    ).relative_to(config.site_dir)
    if built.name == "index.html":
        parent = built.parent.as_posix()
        return "/" if parent == "." else f"/{parent}/"
    return f"/{built.as_posix()}"


def static_render_targets(config: ProjectConfig, pages: list[Page]) -> list[RenderTarget]:
    """Require active source notation to survive in the built article.

    Only pages included in this PDF are checked. HTML parsing ignores
    comments and escaped examples; quoted TeX inside ``<code>`` is not a
    rendered equation. Extra wrappers from macros are still checked in the
    browser, without treating them as a source-count mismatch.
    """
    targets: list[RenderTarget] = []
    for page in pages:
        source_file = config.docs_dir / page.docs_rel_path
        source = source_file.read_text(encoding="utf-8")
        expected_maths = count_math_expressions(source)
        expected_mermaid = count_mermaid_fences(source)
        article = BeautifulSoup(page.html, "html.parser")
        found_maths = len(article.select("div.arithmatex, span.arithmatex"))
        found_mermaid = len(article.select("pre.mermaid"))
        if found_maths < expected_maths:
            raise WebRenderError(
                f"{page.docs_rel_path}: {expected_maths} active maths expression(s) "
                f"in Markdown but only {found_maths} arithmatex element(s) in the "
                "built HTML; run `zensical build --clean --strict` and check this page"
            )
        if found_mermaid < expected_mermaid:
            raise WebRenderError(
                f"{page.docs_rel_path}: {expected_mermaid} active Mermaid fence(s) "
                f"in Markdown but only {found_mermaid} pre.mermaid element(s) in the "
                "built HTML; run `zensical build --clean --strict` and check this page"
            )
        if found_maths or found_mermaid:
            targets.append(
                RenderTarget(
                    page.docs_rel_path,
                    _route(config, page.docs_rel_path),
                    found_maths,
                    found_mermaid,
                )
            )
    return targets


def _puppeteer_module(root: Path) -> Path | None:
    for component, package in (
        ("mermaid", "puppeteer"),
        ("mathjax", "puppeteer-core"),
    ):
        candidate = root / "tools" / component / "node_modules" / package
        if candidate.is_dir():
            return candidate
    return None


def check_web_rendering(
    config: ProjectConfig,
    pages: list[Page],
    *,
    instant_navigation: bool = False,
) -> None:
    """Fail if the built site's active maths/diagrams do not appear in Chrome."""
    targets = static_render_targets(config, pages)
    if not targets:
        return
    node = shutil.which("node")
    module = _puppeteer_module(config.root)
    browser = find_browser()
    if not node or not module or not browser or not Path(browser).is_file():
        missing = []
        if not node:
            missing.append("Node.js")
        if not module:
            missing.append(
                "Puppeteer (run `npm ci --prefix tools/mermaid` or "
                "`npm ci --prefix tools/mathjax` after updating the tools)"
            )
        if not browser or not Path(browser).is_file():
            missing.append("Chrome/Chromium (or PUPPETEER_EXECUTABLE_PATH)")
        raise WebRenderError(
            "Cannot verify browser rendering for maths/diagrams: " + ", ".join(missing)
        )

    script = Path(__file__).with_name("web_render.cjs")
    diagnostics = Path(tempfile.mkdtemp(prefix="pdk-pdf-web-render-"))
    payload = {
        "siteDir": str(config.site_dir),
        "puppeteerModule": str(module),
        "browser": browser,
        "targets": [target.__dict__ for target in targets],
        "instantNavigation": instant_navigation,
        "startRoute": next(
            (
                _route(config, page.docs_rel_path)
                for page in pages
                if page.docs_rel_path != targets[0].source
            ),
            None,
        ),
        "diagnostics": str(diagnostics),
    }
    try:
        result = subprocess.run(
            [node, str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30 + 35 * len(targets) + (35 if instant_navigation else 0),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WebRenderError(
            f"Browser rendering check did not finish: {error}\n"
            f"Browser diagnostics: {diagnostics}"
        ) from error
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown browser failure"
        raise WebRenderError(
            f"Website maths/diagram rendering failed: {detail}\nBrowser diagnostics: {diagnostics}"
        )
    shutil.rmtree(diagnostics)
