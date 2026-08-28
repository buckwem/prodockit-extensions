# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Reads a handful of `project.extra.*` zensical.toml settings that both the
website (see :mod:`prodockit.zensical_macros`) and the PDF (see
:mod:`prodockit.pdf.config`) need to agree on - factored out here so both sides
share one fallback default per setting, rather than each hand-maintaining
its own copy that only stays in sync by coincidence (or a test)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtraSetting:
    """One Prodockit-owned ``project.extra`` setting.

    Runtime readers and configuration diagnostics both use this registry, so
    adding or renaming a setting cannot leave a separate validator list stale.
    ``None`` means the final value depends on other project context or is
    auto-detected.
    """

    key: str
    default: object
    group: str


EXTRA_SETTINGS = (
    ExtraSetting("heading_numbering", True, "Shared rendering"),
    ExtraSetting("reference_style", "european", "Shared rendering"),
    ExtraSetting("reference_spacing_european", "-0.8em", "Shared rendering"),
    ExtraSetting("reference_indent_global", "1.27cm", "Shared rendering"),
    ExtraSetting("reference_spacing_global", "2em", "Shared rendering"),
    ExtraSetting("pdf_output", None, "PDF"),
    ExtraSetting("pdf_copyright", None, "PDF"),
    ExtraSetting("pdf_page_size", "A4", "PDF"),
    ExtraSetting("pdf_margin_top", "2cm", "PDF"),
    ExtraSetting("pdf_margin_right", "2cm", "PDF"),
    ExtraSetting("pdf_margin_bottom", "2.5cm", "PDF"),
    ExtraSetting("pdf_margin_left", "2cm", "PDF"),
    ExtraSetting("pdf_double_sided", False, "PDF"),
    ExtraSetting("pdf_margin_inner", "2cm", "PDF"),
    ExtraSetting("pdf_margin_outer", "2cm", "PDF"),
    ExtraSetting("pdf_header_footer_font_size", "10pt", "PDF"),
    ExtraSetting("pdf_header_footer_color", "#555555", "PDF"),
    ExtraSetting("pdf_header_footer_divider_color", "#e2e8f0", "PDF"),
    ExtraSetting("pdf_include_table_of_contents", True, "PDF"),
    ExtraSetting("pdf_table_of_contents_title", "Table of Contents", "PDF"),
    ExtraSetting("pdf_mmdc_bin", None, "PDF"),
    ExtraSetting("pdf_tex2svg_script", None, "PDF"),
    ExtraSetting("pdf_math_dir", None, "PDF"),
    ExtraSetting("pdf_extra_css", (), "PDF"),
    ExtraSetting("pdf_source_bundle_output", None, "PDF"),
)

EXTRA_SETTING_BY_KEY = {setting.key: setting for setting in EXTRA_SETTINGS}


def extra_default(key: str) -> Any:
    """Return the one declared default for a Prodockit-owned extra setting."""
    return EXTRA_SETTING_BY_KEY[key].default


def flatten_nav(nav_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten Prodockit's normalized nav model into page order.

    Each item carries ``url``/``is_index``/``children``. A group heading
    contributes no entry of its own, only its descendants. The model is
    produced by :mod:`prodockit.project_config`, not a Zensical Python API.
    """
    pages = []
    for item in nav_items:
        if item.get("url"):
            pages.append(item)
        children = item.get("children") or []
        if children:
            pages.extend(flatten_nav(children))
    return pages


def heading_numbering_enabled(extra: dict[str, Any] | None) -> bool:
    """Whether `project.extra.heading_numbering` (default `True`) enables
    chapter/appendix numbering on headings and captions, on both the
    website and the PDF."""
    return bool((extra or {}).get("heading_numbering", extra_default("heading_numbering")))


def reference_style_values(extra: dict[str, Any] | None) -> tuple[str, str, str, str]:
    """Reads `project.extra.reference_style` plus the three spacing/indent
    values behind it, returning `(style, spacing_european, indent_global,
    spacing_global)`:

    - `style`: `"global"` only when `project.extra.reference_style` is
      explicitly set to that value, else `"european"` (the default) - so a
      typo falls back to the current/default look rather than silently
      doing nothing.
    - `spacing_european`: `project.extra.reference_spacing_european`
      (default `"-0.8em"`) - the `european` style's margin-top between
      consecutive `.reference` entries; also used, unconditionally, for
      `.acronym`/`.glossary` entry spacing, since neither has a `global`-
      style alternative to switch to.
    - `indent_global`: `project.extra.reference_indent_global` (default
      `"1.27cm"`) - the `global` style's hanging indent on wrapped lines.
    - `spacing_global`: `project.extra.reference_spacing_global` (default
      `"2em"`) - the `global` style's margin-top between entries.
    """
    extra = extra or {}
    style = str(extra.get("reference_style", extra_default("reference_style"))).strip().lower()
    style = "global" if style == "global" else "european"
    spacing_european = str(
        extra.get("reference_spacing_european", extra_default("reference_spacing_european"))
    )
    indent_global = str(
        extra.get("reference_indent_global", extra_default("reference_indent_global"))
    )
    spacing_global = str(
        extra.get("reference_spacing_global", extra_default("reference_spacing_global"))
    )
    return style, spacing_european, indent_global, spacing_global
