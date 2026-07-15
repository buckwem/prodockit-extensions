# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Reads a handful of `project.extra.*` zensical.toml settings that both the
website (see :mod:`zendoc.zensical_macros`) and the PDF (see
:mod:`zendoc.pdf.config`) need to agree on - factored out here so both sides
share one fallback default per setting, rather than each hand-maintaining
its own copy that only stays in sync by coincidence (or a test)."""

from __future__ import annotations

from typing import Any


def flatten_nav(nav_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flattens Zensical's own resolved nav tree (each item already
    carrying `url`/`is_index`/`children`, as returned by
    `zensical.config.parse_config()` or available as `env.conf["nav"]`
    inside a Zensical macros-plugin `define_env()`) into an ordered,
    depth-first list of real pages only - a nav group heading (`url` is
    `None`, only `children`) contributes no entry of its own, just its
    descendants. Shared by :mod:`zendoc.pdf.config` and
    :mod:`zendoc.zensical_macros`, which both need the same page list."""
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
    return bool((extra or {}).get("heading_numbering", True))


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
    style = str(extra.get("reference_style", "european")).strip().lower()
    style = "global" if style == "global" else "european"
    spacing_european = str(extra.get("reference_spacing_european", "-0.8em"))
    indent_global = str(extra.get("reference_indent_global", "1.27cm"))
    spacing_global = str(extra.get("reference_spacing_global", "2em"))
    return style, spacing_european, indent_global, spacing_global
