# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""`prodockit.tree`, and the stylesheet that draws its rails.

The CSS is measured rather than reviewed for the same reason
`prodockit.steps`'s is: a connector that drifts is invisible at one size
and obvious at another, and the PDF is where it shows up last
(prodockit-extensions#379).
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown
import pytest

from prodockit.tree import TreeError

REPO = Path(__file__).resolve().parents[1]
EXTRA_CSS = REPO / "docs" / "stylesheets" / "extra.css"

LISTING = """/// tree
{options}
docs/ - the documentation source tree
  index.md - the cover page
  stylesheets/ - CSS for both outputs
    extra.css - website customisations
zensical.toml - project configuration
///
"""


def render(listing: str = "", options: str = "") -> str:
    text = listing or LISTING.format(options=f"    {options}\n" if options else "")
    return markdown.markdown(text, extensions=["prodockit.tree"])


def test_indentation_becomes_structure() -> None:
    """The whole point: the shape is read from the listing rather than
    typed as nested bullets."""
    html = render()

    assert '<div class="prodockit-tree">' in html
    # docs/ contains two entries, one of which contains one.
    assert html.count("<ul>") == 3
    assert html.count("<li") == 5


def test_a_trailing_slash_is_the_only_marker_of_a_directory() -> None:
    """Nothing is typed twice. An entry is a directory because its name
    says so, so the icon and the emphasis cannot disagree with it."""
    html = render()

    assert '<li class="tree-directory">' in html
    assert '<li class="tree-file">' in html
    # The slash is the marker, not part of the name - a listing reads
    # `docs`, with the icon saying what it is.
    assert '<span class="tree-name">docs</span>' in html
    assert "docs/</span>" not in html


def test_a_description_is_an_element_rather_than_trailing_text() -> None:
    """So a stylesheet can align it, dim it, or drop it from one output
    without touching the names."""
    html = render()

    assert '<span class="tree-note">the cover page</span>' in html


def test_a_hyphenated_filename_is_not_split() -> None:
    """`harvard-cite-them-right.csl` is a real file in these projects.
    Requiring spaces around the separator is what keeps it whole - a bare
    hyphen would take the name apart."""
    html = render(
        "/// tree\nharvard-cite-them-right.csl - fetched per build\n///\n"
    )

    assert ">harvard-cite-them-right.csl</span>" in html
    assert '<span class="tree-note">fetched per build</span>' in html


def test_an_entry_needs_no_description() -> None:
    html = render("/// tree\nREADME.md\ndocs/\n  index.md\n///\n")

    assert "tree-note" not in html
    assert html.count("<li") == 3


def test_the_indent_width_can_be_stated() -> None:
    """Four spaces is common enough to be worth allowing rather than
    silently mis-reading as two levels."""
    html = render(
        "/// tree\n    indent: 4\n\ndocs/\n    index.md\n///\n"
    )

    assert html.count("<ul>") == 2, html


@pytest.mark.parametrize(
    ("listing", "because"),
    [
        ("/// tree\ndocs/\n   index.md\n///\n", "indent of 3 is not a multiple"),
        ("/// tree\ndocs/\n    index.md\n///\n", "indented 2 levels at once"),
    ],
)
def test_a_listing_that_cannot_be_read_is_refused(listing: str, because: str) -> None:
    """Refused rather than guessed at.

    A listing is read for its shape, so attaching an entry to the wrong
    parent produces a diagram that is wrong and looks right - which is
    read as fact.
    """
    with pytest.raises(TreeError, match=re.escape(because)):
        render(listing)


def test_a_listing_starting_indented_is_refused() -> None:
    """Exercised directly, because the block cannot deliver it.

    pymdownx's Blocks API strips the body's common indentation before
    this sees it, so a uniformly indented listing arrives at depth 0 -
    which is the right behaviour, and leaves this guard covering
    `_build`'s own invariant rather than anything an author can type.
    """
    import xml.etree.ElementTree as etree

    from prodockit.tree import _build

    with pytest.raises(TreeError, match="first entry is indented"):
        _build(etree.Element("div"), "  index.md\n", 2)


# ---------------------------------------------------------------------------
# The stylesheet
# ---------------------------------------------------------------------------


def _tree_css() -> str:
    """This project's own stylesheet, not a copy of it."""
    css = EXTRA_CSS.read_text(encoding="utf-8")
    return css[css.index("/* prodockit.tree") :].replace(".md-typeset ", "")


def _rails(extra: str = "") -> list[tuple[float, float, float]]:
    """Where WeasyPrint puts each rail and stub: (rail x, stub x, stub y)."""
    weasyprint = pytest.importorskip("weasyprint")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    @page {{ size: A4; margin: 2cm; }} body {{ font-size: 11pt; }}
    {_tree_css()}
    .prodockit-tree {{ {extra} }}</style></head><body>
    {render()}</body></html>"""
    page = weasyprint.HTML(string=html).render().pages[0]

    rails: list[tuple[float, float, float]] = []
    pending: dict[str, object] = {}

    def walk(box: object) -> None:
        tag = getattr(box, "element_tag", "")
        if type(box).__name__ == "AbsolutePlaceholder":
            if tag == "li::before":
                pending["rail"] = box.position_x  # type: ignore[attr-defined]
            elif tag == "li::after" and "rail" in pending:
                rails.append(
                    (
                        float(pending.pop("rail")),  # type: ignore[arg-type]
                        box.position_x,  # type: ignore[attr-defined]
                        box.position_y,  # type: ignore[attr-defined]
                    )
                )
        for child in getattr(box, "children", []):
            walk(child)

    walk(page._page_box)
    return rails


def test_every_stub_starts_on_its_own_rail() -> None:
    """The two are positioned from one measurement, so they cannot drift
    apart - the failure `prodockit.steps` had to be measured into
    submission."""
    rails = _rails()

    assert rails, "nothing was laid out - the stylesheet did not apply"
    for rail_x, stub_x, _ in rails:
        assert abs(rail_x - stub_x) < 0.01, f"stub starts {stub_x - rail_x:+.2f}pt off"


@pytest.mark.parametrize("change", ["", "--tree-indent: 3rem;", "--tree-stub: 2rem;"])
def test_the_rails_hold_when_the_indentation_changes(change: str) -> None:
    """Whatever is resized, one measurement drives both."""
    rails = _rails(change)

    assert rails, change
    for rail_x, stub_x, _ in rails:
        assert abs(rail_x - stub_x) < 0.01, f"{change or 'as shipped'}: {stub_x - rail_x:+.2f}pt"


def test_the_last_entry_has_no_rail_running_past_it() -> None:
    """A rail below the last entry points at nothing."""
    css = _tree_css()

    assert re.search(r"li:last-child::before\s*\{[^}]*bottom:\s*auto", css), css[-500:]


def test_the_icon_comes_from_the_projects_own_set() -> None:
    """prodockit-extensions#379.

    The extension emits a shortcode rather than SVG, so the icons are
    whatever the project already uses - Material's here, or a custom set
    under a configured `custom_icons` directory. Emitting SVG directly
    would hard-code one project's icons into every document.
    """
    from zensical.extensions.emoji import to_svg, twemoji

    html = markdown.markdown(
        "/// tree\ndocs/\n  index.md\n///\n",
        extensions=["prodockit.tree", "pymdownx.emoji"],
        extension_configs={
            "pymdownx.emoji": {"emoji_index": twemoji, "emoji_generator": to_svg}
        },
    )

    assert html.count("<svg") == 2, "one icon per entry"
    assert ":material-" not in html, "the shortcode should have been rendered"


def test_the_icons_can_be_replaced() -> None:
    """A project with its own set names them rather than restyling."""
    html = render(
        "/// tree\n    directory_icon: ':octicons-file-directory-16:'\n"
        "    file_icon: ':octicons-file-16:'\n\ndocs/\n  index.md\n///\n"
    )

    assert ":octicons-file-directory-16:" in html
    assert ":material-folder:" not in html
