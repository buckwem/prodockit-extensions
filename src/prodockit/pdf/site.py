# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Read document content from Zensical's documented build output.

Zensical remains responsible for Markdown rendering.  Prodockit invokes its
public CLI, then extracts the already-rendered article from each generated
HTML page.  No Zensical Python package internals are imported here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml  # type: ignore[import-untyped, unused-ignore]
from bs4 import BeautifulSoup

from prodockit.project_config import ProjectConfig


class BuiltSiteError(RuntimeError):
    """A documented Zensical build or its output cannot be consumed."""


_ICON_PROBE_SOURCE = ".prodockit-pdf-icon-probe.md"
_ICON_PROBE_HEADING_PREFIX = "prodockit-icon-"


def _zensical_cli() -> str:
    """Return the Zensical CLI from Prodockit's active Python environment."""
    scripts = Path(sys.executable).parent
    names = ("zensical.exe", "zensical") if sys.platform == "win32" else ("zensical",)
    for name in names:
        candidate = scripts / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which("zensical") or "zensical"


def _icon_key(shortcode: str) -> str:
    """Return the registry spelling used for a Zensical icon shortcode."""
    return shortcode.strip().strip(":/").lower().replace("/", "-")


def _icon_probe_source(admonition_icons: dict[str, Any]) -> str:
    """Build a temporary Markdown page that asks Zensical to render icons."""
    sections = ["# Prodockit PDF icon probe", ""]
    for adm_type, shortcode in admonition_icons.items():
        if not isinstance(shortcode, str) or not shortcode.strip():
            continue
        sections.extend(
            [
                f"## {_ICON_PROBE_HEADING_PREFIX}{str(adm_type).lower()}",
                "",
                f":{_icon_key(shortcode)}:",
                "",
            ]
        )
    return "\n".join(sections)


def _read_icon_probe(path: Path, admonition_icons: dict[str, Any]) -> dict[str, str]:
    """Extract the SVGs Zensical rendered on the temporary probe page."""
    if not path.is_file():
        raise BuiltSiteError(f"zensical build did not create the icon probe page: {path}")
    html = path.read_text(encoding="utf-8")
    registry: dict[str, str] = {}
    missing: list[str] = []
    for adm_type, shortcode in admonition_icons.items():
        if not isinstance(shortcode, str) or not shortcode.strip():
            continue
        heading_id = re.escape(f"{_ICON_PROBE_HEADING_PREFIX}{str(adm_type).lower()}")
        section = re.search(
            rf'<h2\b[^>]*\bid=["\']{heading_id}["\'][^>]*>.*?'
            r"(?P<svg><svg\b.*?</svg>)",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if section is None:
            missing.append(str(shortcode))
            continue
        # Keep the generated SVG verbatim. Parsing it through an HTML parser
        # lowercases case-sensitive SVG attributes such as ``viewBox``;
        # Pandoc then rejects the otherwise valid image.
        registry[_icon_key(shortcode)] = section.group("svg")
    if missing:
        raise BuiltSiteError(
            "zensical built the icon probe but did not render the configured "
            f"icon shortcode(s): {', '.join(missing)}"
        )
    return registry


def build_site(
    config: ProjectConfig,
    admonition_icons: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Run Zensical's public clean build and return its configured icon SVGs.

    The temporary probe is ordinary Markdown containing the configured icon
    shortcodes.  Zensical therefore remains responsible for resolving theme
    icons; Prodockit neither imports its icon loader nor reads its private
    package directories.
    """
    configured_icons = admonition_icons or {}
    probe_source = config.docs_dir / _ICON_PROBE_SOURCE
    directory_urls = bool(config.project.get("use_directory_urls", True))
    probe_output = output_path(_ICON_PROBE_SOURCE, config.site_dir, directory_urls=directory_urls)
    if configured_icons and probe_source.exists():
        raise BuiltSiteError(
            f"temporary PDF icon probe would overwrite an existing file: {probe_source}"
        )
    if configured_icons:
        probe_source.write_text(_icon_probe_source(configured_icons), encoding="utf-8")
    try:
        try:
            result = subprocess.run(
                [_zensical_cli(), "build", "--clean", "--config-file", str(config.path)],
                cwd=config.root,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            raise BuiltSiteError(f"could not run zensical build: {error}") from error
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else ""
            raise BuiltSiteError(f"zensical build exited with status {result.returncode}{suffix}")
        return _read_icon_probe(probe_output, configured_icons) if configured_icons else {}
    finally:
        if configured_icons:
            probe_source.unlink(missing_ok=True)
            if directory_urls:
                shutil.rmtree(probe_output.parent, ignore_errors=True)
            else:
                probe_output.unlink(missing_ok=True)


def output_path(source_path: str, site_dir: Path, *, directory_urls: bool = True) -> Path:
    """Map one nav Markdown path to its documented generated HTML path."""
    source = PurePosixPath(source_path)
    if source.suffix.lower() != ".md":
        raise BuiltSiteError(f"navigation target is not a Markdown page: {source_path}")
    if source.name.lower() == "index.md":
        relative = source.with_suffix(".html")
    elif directory_urls:
        relative = source.with_suffix("") / "index.html"
    else:
        relative = source.with_suffix(".html")
    return site_dir.joinpath(*relative.parts)


def page_html(
    config: ProjectConfig,
    source_path: str,
    *,
    directory_urls: bool | None = None,
) -> str:
    """Extract only the rendered document article for ``source_path``."""
    if directory_urls is None:
        directory_urls = bool(config.project.get("use_directory_urls", True))
    path = output_path(source_path, config.site_dir, directory_urls=directory_urls)
    if not path.is_file():
        raise BuiltSiteError(f"zensical build did not create the expected page: {path}")
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    article = soup.select_one("article.md-content__inner.md-typeset")
    if article is None:
        raise BuiltSiteError(
            f"could not find the document article in {path}; the generated HTML layout changed"
        )
    for website_only in article.select(":scope > a, :scope > footer, nav.md-tags, .md-feedback"):
        website_only.decompose()
    # ``str(Comment(...))`` returns only the comment body, without ``<!--``
    # and ``-->``. Joining the children therefore turns source comments into
    # visible PDF prose. Encoding the article's inner HTML preserves node
    # types while still excluding the outer website-only article wrapper.
    return article.decode_contents().strip()


def page_metadata(source_file: Path) -> dict[str, Any]:
    """Read a page's YAML front matter without invoking Zensical."""
    text = source_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        raise BuiltSiteError(f"unterminated YAML front matter in {source_file}") from None
    try:
        value = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as error:
        raise BuiltSiteError(f"invalid YAML front matter in {source_file}: {error}") from error
    if not isinstance(value, dict):
        raise BuiltSiteError(f"YAML front matter in {source_file} must be a mapping")
    return value
