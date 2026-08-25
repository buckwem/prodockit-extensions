# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Admonition icons for the PDF.

Zensical's own admonition HTML has no icon markup at all - the website
draws it via a CSS trick (a mask-image/background referencing a theme
asset) that doesn't exist in a standalone PDF (confirmed directly: a built
admonition's title paragraph is just its plain text, nothing else). This
module resolves an admonition type (note, warning, tip, ...) to its
accent-coloured icon SVG markup instead, so a caller (see
:mod:`prodockit.pdf.html`) can insert it explicitly.
"""

from __future__ import annotations

import glob
import os
import re
import site
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

# Mirrors the border-left-color a compiled PDF stylesheet typically sets per
# admonition type (see prodockit.pdf.css), so the icon matches the coloured bar
# rather than rendering in its raw (black) fill.
ADMONITION_ACCENT_COLORS: dict[str, str] = {
    "note": "#448aff",
    "abstract": "#00b0ff",
    "info": "#00b8d4",
    "tip": "#00bfa5",
    "success": "#00c853",
    "question": "#64dd17",
    "warning": "#ff9100",
    "failure": "#ff5252",
    "danger": "#ff1744",
    "bug": "#ec407a",
    "example": "#651fff",
    "quote": "#9e9e9e",
}


def discover_icon_dirs(docs_dir: str = "docs") -> list[str]:
    """Discover project-owned ``.icons`` directories.

    Zensical's installed package layout is deliberately not searched.  Theme
    icons are recovered from the documented built website instead; only a
    project's explicit overrides need filesystem discovery here.
    """
    dirs = [
        os.path.abspath(os.path.join(os.getcwd(), "overrides", ".icons")),
        os.path.abspath(os.path.join(os.getcwd(), ".icons")),
        os.path.abspath(os.path.join(os.getcwd(), docs_dir, ".icons")),
    ]

    valid_dirs = []
    for d in dirs:
        abs_d = os.path.abspath(d)
        if os.path.isdir(abs_d) and abs_d not in valid_dirs:
            valid_dirs.append(abs_d)
    return valid_dirs


def discover_legacy_icon_dirs(docs_dir: str = "docs") -> list[str]:
    """Reproduce the legacy PDF path's installed-package discovery.

    This deliberately remains separate from :func:`discover_icon_dirs`: the
    public built-site renderer must not depend on Zensical's package layout,
    while the hidden legacy command retains its old lookup behaviour.
    """
    dirs = discover_icon_dirs(docs_dir)
    site_paths: list[str] = []
    if hasattr(site, "getsitepackages"):
        site_paths.extend(site.getsitepackages())
    if hasattr(site, "getusersitepackages"):
        site_paths.append(site.getusersitepackages())

    candidates: list[str] = []
    for site_path in site_paths:
        for package in ("material", "mkdocs_material", "zensical"):
            candidates.append(os.path.join(site_path, package, "templates", ".icons"))
            candidates.append(os.path.join(site_path, package, ".icons"))

    for local_dir in (".venv", "venv", "env"):
        base_venv = os.path.join(os.getcwd(), local_dir)
        if not os.path.isdir(base_venv):
            continue
        for package in ("material", "mkdocs_material", "zensical"):
            for site_packages in ("lib/python*/site-packages", "Lib/site-packages"):
                parts = (base_venv, *site_packages.split("/"), package)
                candidates.extend(glob.glob(os.path.join(*parts, "templates", ".icons")))
                candidates.extend(glob.glob(os.path.join(*parts, ".icons")))

    for candidate in candidates:
        absolute = os.path.abspath(candidate)
        if os.path.isdir(absolute) and absolute not in dirs:
            dirs.append(absolute)
    return dirs


_ADMONITION_ICON_VARIABLE = re.compile(
    r"--md-admonition-icon--(?P<type>[\w-]+)\s*:\s*url\(\s*"
    r"(?P<quote>['\"])data:image/svg\+xml(?:;charset=[^,]+)?,"
    r"(?P<payload>.*?)(?P=quote)\s*\)",
    re.IGNORECASE | re.DOTALL,
)

_UNQUOTED_ADMONITION_ICON_VARIABLE = re.compile(
    r"--md-admonition-icon--(?P<type>[\w-]+)\s*:\s*url\(\s*"
    r"data:image/svg\+xml(?:;charset=[^,]+)?,(?P<payload>.*?)\s*\)",
    re.IGNORECASE | re.DOTALL,
)


def build_site_icon_registry(
    site_dir: str | Path,
    admonition_icon_config: dict[str, Any] | None,
) -> dict[str, str]:
    """Recover configured admonition SVGs from a completed site build.

    Zensical compiles each configured admonition icon into a CSS custom
    property containing an SVG data URI.  Reading that public build output
    avoids importing Zensical or relying on its private package directories.
    Stylesheets are processed in page order, so a later project stylesheet
    overrides the theme exactly as it does in the website.
    """
    if not admonition_icon_config:
        return {}
    root = Path(site_dir).resolve()
    index = root / "index.html"
    css_paths: list[Path] = []
    if index.is_file():
        soup = BeautifulSoup(index.read_text(encoding="utf-8"), "html.parser")
        for link in soup.select('link[rel~="stylesheet"][href]'):
            href = str(link.get("href", ""))
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            local_path = unquote(parsed.path).lstrip("/")
            candidate = (
                (root / local_path).resolve()
                if parsed.path.startswith("/")
                else (index.parent / local_path).resolve()
            )
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if candidate.is_file():
                css_paths.append(candidate)
    else:
        css_paths = sorted(root.rglob("*.css"))

    by_type: dict[str, str] = {}
    for css_path in css_paths:
        css = css_path.read_text(encoding="utf-8")
        matches = list(_ADMONITION_ICON_VARIABLE.finditer(css))
        matches.extend(_UNQUOTED_ADMONITION_ICON_VARIABLE.finditer(css))
        for match in sorted(matches, key=lambda item: item.start()):
            svg = unquote(match.group("payload")).strip()
            if svg.startswith("<svg") and "</svg>" in svg:
                by_type[match.group("type").lower()] = svg[: svg.index("</svg>") + 6]

    registry: dict[str, str] = {}
    for adm_type, shortcode in admonition_icon_config.items():
        configured_svg = by_type.get(str(adm_type).lower())
        if configured_svg and isinstance(shortcode, str):
            key = shortcode.strip("/").lower().replace("/", "-")
            registry[key] = configured_svg
    return registry


def build_icon_registry(icon_dirs: list[str]) -> dict[str, str]:
    """Indexes every ``.svg`` under each of icon_dirs (see
    :func:`discover_icon_dirs`), keyed by every plausible shortcode form a
    caller might look it up by (hyphenated, underscored, "set-name" short
    form, FontAwesome's own "fa-style-name" form, and the bare file name) -
    so a lookup doesn't need to know exactly which convention produced the
    shortcode it's resolving.

    Earlier entries in icon_dirs win on key collision (each key is only
    ever set once, via the ``if key not in registry`` pattern below for
    the derived short forms - the primary hyphen_slug form is always
    (re)written, so a *later* dir's exact same icon simply overwrites the
    earlier one for that one key. Pass icon_dirs pre-ordered by priority
    if this matters for a given lookup.
    """
    registry: dict[str, str] = {}
    for base_dir in icon_dirs:
        if not os.path.isdir(base_dir):
            continue
        for root, _, files in os.walk(base_dir):
            for file in files:
                if not file.lower().endswith(".svg"):
                    continue
                full_path = os.path.abspath(os.path.join(root, file)).replace("\\", "/")
                rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/").lower()

                slug = os.path.splitext(rel_path)[0]
                hyphen_slug = slug.replace("/", "-")

                registry[hyphen_slug] = full_path
                registry[hyphen_slug.replace("_", "-")] = full_path
                registry[hyphen_slug.replace("-", "_")] = full_path

                parts = slug.split("/")
                if len(parts) > 1:
                    short_key = f"{parts[0]}-{parts[-1]}"
                    if short_key not in registry:
                        registry[short_key] = full_path

                    if parts[0] == "fontawesome" and len(parts) > 2:
                        fa_key = f"fa-{parts[1]}-{parts[-1]}"
                        registry[fa_key] = full_path

                flat_key = parts[-1]
                if flat_key not in registry:
                    registry[flat_key] = full_path
    return registry


def admonition_icon_svg(
    adm_type: str,
    admonition_icon_config: dict[str, Any] | None,
    icon_registry: dict[str, str],
) -> str | None:
    """Resolves an admonition type (note, warning, tip, ...) to its
    accent-coloured icon SVG markup, using the icon shortcode configured
    for it in `admonition_icon_config` (Zensical's own
    ``project.theme.icon.admonition`` table, e.g.
    ``{"note": "fontawesome/solid/note-sticky", ...}`` - see
    https://zensical.org/docs/authoring/admonitions/#supported-types).

    Returns None if nothing is configured for `adm_type`, or the icon file
    can't be found in `icon_registry` (see :func:`build_icon_registry`).
    """
    shortcode = admonition_icon_config.get(adm_type) if admonition_icon_config else None
    if not shortcode:
        return None
    key = shortcode.strip("/").lower().replace("/", "-")
    icon_source = icon_registry.get(key)
    if not icon_source:
        return None
    if icon_source.lstrip().startswith("<svg"):
        svg_data = icon_source
    else:
        try:
            with open(icon_source, encoding="utf-8") as f:
                svg_data = f.read()
        except OSError:
            return None
    accent_color = ADMONITION_ACCENT_COLORS.get(adm_type)
    if accent_color:
        # "currentColor" resolves against the CSS `color` property, not
        # `fill` - setting fill="..." on the <svg> root has no effect on a
        # descendant path's fill="currentColor", so replace it directly.
        svg_data = re.sub(r"currentColor", accent_color, svg_data, flags=re.IGNORECASE)
    return svg_data
