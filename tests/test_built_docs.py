# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Checks this project's own built site and PDF, using the pytest plugin
this project ships.

Everything else under `tests/` exercises the library against synthetic
documents in `tmp_path`. Nothing looked at what `prodockit pdf` actually
produced from `docs/` - which is how the Mermaid diagram in
`extensions/bibliography.md` reached every published PDF as raw
`flowchart LR ...` source until 0.12.0, on the very page documenting how
Mermaid fences are pre-rendered. The build warning added then makes that
visible; these make it fail.

Marked `built` because they need `prodockit pdf` and `zensical build` to
have run. The ordinary unit run deselects them (see pyproject.toml's
`addopts`); `docs.yml` runs them after building. Deselecting rather than
skipping is deliberate - a skip in an unbuilt checkout looks like a pass.

This is also the only place prodockit's own pytest plugin is used against a
real project rather than a synthetic one, so it doubles as a check that the
plugin resolves a real config correctly.
"""

from __future__ import annotations

import pytest

from prodockit.testing import assert_no_unrendered_mermaid, assert_no_unrendered_tex

pytestmark = pytest.mark.built

#: Mermaid's default node fill (#ECECFF). Every node shape in a rendered
#: diagram is painted with it, and nothing else in these docs uses it, so it
#: distinguishes a real diagram from ordinary page furniture - unlike
#: `page.get_drawings()` being non-empty, which is true of every page.
MERMAID_NODE_FILL = (0.925, 0.925, 1.0)
FILL_TOLERANCE = 0.02


def _mermaid_node_shapes(page):
    shapes = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if fill and all(
            abs(channel - expected) <= FILL_TOLERANCE
            for channel, expected in zip(fill, MERMAID_NODE_FILL, strict=False)
        ):
            shapes.append(drawing)
    return shapes


def test_the_pdf_built_and_has_pages(prodockit_pdf):
    assert prodockit_pdf.page_count > 5


def test_no_page_contains_unrendered_mermaid_source(prodockit_pdf_page_texts):
    """The regression that shipped for real: `extensions/bibliography.md`'s
    architecture diagram reaching the PDF as its own source text."""
    assert_no_unrendered_mermaid(prodockit_pdf_page_texts)


def test_no_page_contains_unrendered_tex_source(prodockit_pdf_page_texts):
    assert_no_unrendered_tex(prodockit_pdf_page_texts)


def test_the_architecture_diagram_actually_rendered(prodockit_pdf):
    """The counterpart to the check above, which would still pass if the
    diagram vanished from the PDF entirely rather than reaching it as text.

    Asserts on Mermaid's own node fill rather than the presence of any
    vector content: every page has drawings (headers, rules), so a
    non-empty `get_drawings()` proves nothing.
    """
    total = sum(len(_mermaid_node_shapes(page)) for page in prodockit_pdf)
    assert total > 0, (
        "No shape in the PDF is filled with Mermaid's node colour - the "
        "diagram in extensions/bibliography.md did not render"
    )


def test_the_site_built(prodockit_site_dir, prodockit_site_html_files):
    assert (prodockit_site_dir / "index.html").is_file()
    assert len(prodockit_site_html_files) > 5


def test_every_nav_page_reached_the_site(prodockit_nav_pages, prodockit_site_dir):
    """A nav entry that silently failed to build would otherwise only show up
    as a 404 on the published site."""
    missing = []
    for page in prodockit_nav_pages:
        stem = page.removesuffix(".md")
        candidates = [
            prodockit_site_dir / f"{stem}.html",
            prodockit_site_dir / stem / "index.html",
        ]
        if stem == "index":
            candidates.append(prodockit_site_dir / "index.html")
        if not any(candidate.is_file() for candidate in candidates):
            missing.append(page)
    assert not missing, f"Nav pages missing from the built site: {missing}"
