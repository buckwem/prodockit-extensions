# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Generic Jinja macros/variables for a Zensical project's own `macros.py`
(via Zensical's `zensical.extensions.macros` plugin) - the pieces a
professional/academic report commonly wants that aren't specific to any one
project: a site-wide word count, the git-detected repository URL, chapter/
appendix numbering that continues across pages, and reference/acronym/
glossary list spacing that matches `zendoc.pdf`'s own PDF output.

Add it alongside your own project's `macros.py` (which keeps anything
genuinely project-specific - institution branding, a custom macro, and so
on) via `zensical.toml`:

```toml
[project.markdown_extensions.zensical.extensions.macros]
module_name = "macros"
modules = ["zendoc.zensical_macros"]
```

Zensical's macros plugin loads `module_name` and every entry in `modules`,
merging all of their `define_env()` contributions into the same Jinja
environment - so a project with no macros of its own can just use
`modules = ["zendoc.zensical_macros"]` alone, dropping `module_name`/
`macros.py` entirely.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any
from urllib.parse import urlparse, urlunparse

from zendoc.headings import prescan
from zendoc.settings import flatten_nav, reference_style_values
from zendoc.wordcount import compute_word_count

# Front matter flag excluding a page from the site-wide word count - see
# "Word count" in a project's own customisation docs. Shared with
# zendoc.pdf's own PDF-side word count, if a project computes one there too.
WORD_COUNT_EXCLUDED_FRONT_MATTER_KEY = "exclude_from_word_count"


def _front_matter_flag(path: str, key: str) -> bool:
    """True if the markdown file at `path` sets `key: true` in its YAML
    front matter."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    return bool(re.search(rf"^{re.escape(key)}:\s*true\s*$", parts[1], re.MULTILINE | re.IGNORECASE))


def _compute_site_word_count(config: dict[str, Any]) -> str:
    """Sums the prose word count across every nav page except the first
    (assumed to be the cover page) and any page flagged
    `exclude_from_word_count: true`. Returns a comma-formatted string (e.g.
    `"9,971"`) ready to drop straight into a page with `{{ word_count }}`."""
    docs_dir = config.get("docs_dir") or "docs"
    nav_pages = flatten_nav(config.get("nav") or [])
    counted_texts = []
    for i, nav_page in enumerate(nav_pages):
        if i == 0:
            continue
        full_path = os.path.join(docs_dir, nav_page["url"])
        if _front_matter_flag(full_path, WORD_COUNT_EXCLUDED_FRONT_MATTER_KEY):
            continue
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                counted_texts.append(f.read())
        except OSError:
            continue
    return f"{compute_word_count(counted_texts):,}"


def _get_repo_url() -> str:
    """Returns the fully-qualified https:// URL for the repo's origin
    remote (converting from `git@host:path.git` SSH syntax if necessary).
    Returns `""` if there's no git remote configured (e.g. the project
    hasn't been cloned/initialised yet).

    Deliberately computed from the local git remote rather than
    `project.repo_url` in `zensical.toml`: it's meant to reflect wherever
    *this* checkout actually points (e.g. a CI job's own token-embedded
    remote, stripped below), which in practice usually - but isn't
    guaranteed to - match the configured value."""
    try:
        remote_url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
    except Exception:
        return ""
    if not remote_url:
        return ""
    ssh_match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", remote_url)
    if ssh_match:
        host, path = ssh_match.group(1), ssh_match.group(2)
        return f"https://{host}/{path}"
    if remote_url.startswith(("http://", "https://")):
        remote_url = re.sub(r"\.git$", "", remote_url)
        parsed = urlparse(remote_url)
        if parsed.username or parsed.password:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc += f":{parsed.port}"
            parsed = parsed._replace(netloc=netloc)
            remote_url = urlunparse(parsed)
        return remote_url
    return remote_url


def define_env(env: Any) -> None:
    """Registers this module's variables/macros on `env` - see the module
    docstring for how to wire this into `zensical.toml`."""
    config = env.conf

    env.variables["word_count"] = _compute_site_word_count(config)
    env.variables["repo_url"] = _get_repo_url()
    env.variables["site_name"] = config.get("site_name") or ""

    @env.macro  # type: ignore[untyped-decorator]
    def heading_counter_reset(page: Any) -> str:
        """Continues chapter/section numbering (and the matching sidebar
        numbering) across pages, from this page's position in nav - see
        `zendoc.headings.prescan()`, the single source of truth for what
        number/letter a page actually gets, so this always matches what
        `\\ref{}` shows for a heading on this page. Usage: place
        `{{ heading_counter_reset(page) }}` near the top of each page;
        nothing else needs to change when pages are reordered or headings
        are added/removed.

        A page flagged `is_appendix: true` in its own front matter gets
        letter-based numbering instead - "Appendix A", "A.1", "A.1.1" -
        matching `zendoc.headings`' own `appendix_attr` default.
        """
        extra = config.get("extra") or {}
        if not bool(extra.get("heading_numbering", True)):
            return (
                "<style>\n"
                "  .md-typeset h1::before,\n"
                "  .md-typeset h2::before,\n"
                "  .md-typeset h3::before,\n"
                "  .md-nav--secondary > .md-nav__list > .md-nav__item > .md-nav__link .md-ellipsis::before,\n"
                "  .md-nav--secondary > .md-nav__list > .md-nav__item .md-nav__list > .md-nav__item > .md-nav__link .md-ellipsis::before {\n"
                '    content: "" !important;\n'
                "  }\n"
                '  .zendoc-figure-caption .caption-prefix::before { content: "Figure " !important; }\n'
                '  .zendoc-table-caption .caption-prefix::before { content: "Table " !important; }\n'
                "</style>"
            )
        page_path = getattr(page, "path", "")
        result = prescan()
        start_counts, appendix_letters = result if result is not None else ({}, {})
        letter = appendix_letters.get(page_path)
        if letter:
            return (
                "<style>\n"
                f'  .md-typeset h1::before {{ content: "Appendix {letter}. " !important; }}\n'
                f'  .md-typeset h2::before {{ content: "{letter}." counter(h2-count) " " !important; }}\n'
                f'  .md-typeset h3::before {{ content: "{letter}." counter(h2-count) "." counter(h3-count) " " !important; }}\n'
                f'  .md-nav--secondary > .md-nav__list > .md-nav__item > .md-nav__link .md-ellipsis::before {{ content: "{letter}." counter(toc2) " " !important; }}\n'
                f'  .md-nav--secondary > .md-nav__list > .md-nav__item .md-nav__list > .md-nav__item > .md-nav__link .md-ellipsis::before {{ content: "{letter}." counter(toc2) "." counter(toc3) " " !important; }}\n'
                f'  .zendoc-figure-caption .caption-prefix::before {{ content: "Figure {letter}." !important; }}\n'
                f'  .zendoc-table-caption .caption-prefix::before {{ content: "Table {letter}." !important; }}\n'
                "</style>"
            )
        n = start_counts.get(page_path, 0)
        return (
            "<style>\n"
            f'  .md-typeset {{ counter-reset: h1-count {n} !important; }}\n'
            f'  .md-nav--primary {{ counter-reset: toc1 {n + 1} !important; }}\n'
            "</style>"
        )

    @env.macro  # type: ignore[untyped-decorator]
    def reference_style() -> str:
        """Controls the layout of `.reference` paragraphs on a references
        page. The default look is the "european" style: single line
        spacing throughout, no indent, entries close together - spacing
        set by `project.extra.reference_spacing_european`. Set
        `project.extra.reference_style = "global"` in `zensical.toml` to
        switch to the common APA/MLA/Chicago style instead - single line
        spacing within each entry, but double spacing *between* entries
        (`reference_spacing_global`), with a hanging indent on wrapped
        lines (`reference_indent_global`). Usage: place
        `{{ reference_style() }}` once near the top of the references
        page."""
        extra = config.get("extra") or {}
        style, spacing_european, indent_global, spacing_global = reference_style_values(extra)
        if style != "global":
            return (
                "<style>\n"
                "  .md-typeset p.reference + p.reference {\n"
                f"    margin-top: {spacing_european} !important;\n"
                "  }\n"
                "</style>"
            )
        return (
            "<style>\n"
            "  .md-typeset p.reference {\n"
            f"    padding-left: {indent_global} !important;\n"
            f"    text-indent: -{indent_global} !important;\n"
            "  }\n"
            "  .md-typeset p.reference + p.reference {\n"
            f"    margin-top: {spacing_global} !important;\n"
            "  }\n"
            "</style>"
        )

    @env.macro  # type: ignore[untyped-decorator]
    def acronym_style() -> str:
        """Controls the layout of `.acronym` paragraphs on an acronyms page
        - same tight spacing as the references page's default "european"
        look, and the same `project.extra.reference_spacing_european`
        setting (see `reference_style()` above), since neither the acronym
        nor glossary list has a "global"-style alternative to switch to.
        Usage: place `{{ acronym_style() }}` once near the top of the
        acronyms page."""
        extra = config.get("extra") or {}
        _, spacing_european, _, _ = reference_style_values(extra)
        return (
            "<style>\n"
            "  .md-typeset p.acronym + p.acronym {\n"
            f"    margin-top: {spacing_european} !important;\n"
            "  }\n"
            "</style>"
        )

    @env.macro  # type: ignore[untyped-decorator]
    def glossary_style() -> str:
        """Controls the layout of `.glossary` paragraphs on a glossary page
        - see `acronym_style()` above, same reasoning. Usage: place
        `{{ glossary_style() }}` once near the top of the glossary page."""
        extra = config.get("extra") or {}
        _, spacing_european, _, _ = reference_style_values(extra)
        return (
            "<style>\n"
            "  .md-typeset p.glossary + p.glossary {\n"
            f"    margin-top: {spacing_european} !important;\n"
            "  }\n"
            "</style>"
        )
