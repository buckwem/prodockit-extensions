# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""`prodockit.steps`, and the stylesheet that makes it a steps layout.

The CSS is tested here rather than left to review because both of its
traps fail silently and only in the PDF (prodockit-extensions#378).
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown
import pytest

REPO = Path(__file__).resolve().parents[1]
EXTRA_CSS = REPO / "docs" / "stylesheets" / "extra.css"
BOOTSTRAP_PAGE = REPO / "docs" / "devcons" / "bootstrap.md"

STEPS = """/// steps
{options}
//// step | First thing
Body text.

A second paragraph.
////

//// step | Second thing
More body.
////

///
"""


def render(options: str = "") -> str:
    text = STEPS.format(options=f"    {options}\n" if options else "")
    return markdown.markdown(text, extensions=["prodockit.steps", "pymdownx.superfences"])


def test_a_step_is_a_list_item_with_a_title_of_its_own() -> None:
    """The title is structure, not bold text - so it can be styled apart
    from other emphasis, collected, or given an id later."""
    html = render()

    assert '<ol class="prodockit-steps">' in html
    assert html.count("<li>") == 2
    assert html.count('<p class="prodockit-step-title">') == 2
    assert "First thing" in html and "Second thing" in html


def test_a_step_holds_paragraphs_rather_than_one_run_on_line() -> None:
    """Inline content ran a step's prose, its command and its explanation
    together, which reads worse than the plain list this replaces."""
    first = render().split("</li>")[0]

    assert first.count("<p>") == 2, first


def test_the_starting_number_is_written_in_both_spellings() -> None:
    """`start` is what a browser reads. WeasyPrint ignores it entirely and
    numbers from 1, so the PDF disagreed with the website while each
    looked right on its own. `counter-reset` is what WeasyPrint reads.

    Emitting both from one `start: 9` is the reason this is an extension
    rather than a documented HTML snippet.
    """
    html = render("start: 9")

    assert 'start="9"' in html
    assert "counter-reset: list-item 8" in html


def test_starting_at_one_says_neither() -> None:
    """The default needs no help, and an `<ol start="1">` is noise."""
    html = render("start: 1")

    assert "start=" not in html
    assert "counter-reset" not in html


def test_a_style_of_your_own_joins_the_counter_rather_than_replacing_it() -> None:
    """`attrs` may carry a `style`, and so does the starting number.

    Whichever were set last would otherwise win, and the one that
    silently lost would be the numbering - in the PDF only.
    """
    text = (
        "/// steps\n    start: 9\n    attrs: {style: 'font-size: 1.2em'}\n\n"
        "//// step | Only\nBody.\n////\n\n///\n"
    )
    html = markdown.markdown(text, extensions=["prodockit.steps"])

    assert "counter-reset: list-item 8" in html
    assert "font-size: 1.2em" in html


def test_a_step_can_hold_content_tabs() -> None:
    """One platform's instructions per tab, inside the step they belong to.

    Worth a test rather than an assumption: the step's body is parsed as
    blocks, and a tab set is a block construct nested inside another - a
    combination that could plausibly have been eaten by either.
    """
    text = (
        "/// steps\n\n//// step | Install Python\nPick your platform.\n\n"
        '=== "macOS"\n\n    ```bash\n    brew install python@3.14\n    ```\n\n'
        '=== "Windows"\n\n    ```powershell\n    winget install Python.Python.3.14\n    ```\n'
        "////\n\n///\n"
    )
    html = markdown.markdown(
        text, extensions=["prodockit.steps", "pymdownx.tabbed", "pymdownx.superfences"]
    )

    assert "tabbed-set" in html
    assert html.count("<label for=") == 2
    assert html.index("prodockit-step-title") < html.index("tabbed-set"), "inside the step"


def test_the_bootstrap_quick_start_uses_it() -> None:
    """The demonstration is a real page rather than a fixture: six steps
    with commands in them, which is what the layout is for."""
    page = BOOTSTRAP_PAGE.read_text(encoding="utf-8")
    quick = page[page.index("## Quick start") : page.index("## What it covers")]

    assert "/// steps" in quick
    assert quick.count("//// step | ") == 6, "six steps, as the workflow it mirrors"
    # Installing Python differs per platform, and the page already uses
    # tabs for exactly that above the quick start.
    assert '=== "macOS"' in quick and '=== "Windows"' in quick and '=== "Ubuntu"' in quick


# ---------------------------------------------------------------------------
# The stylesheet
# ---------------------------------------------------------------------------


def _steps_css() -> str:
    """This project's own stylesheet, not a copy of it.

    A copy would let the shipped CSS drift while the test kept passing,
    which is the failure this is here to prevent.
    """
    css = EXTRA_CSS.read_text(encoding="utf-8")
    start = css.index("/* prodockit.steps")
    return css[start:].replace(".md-typeset ", "")


def _centres(extra: str = "") -> list[tuple[float, float]]:
    """Where WeasyPrint actually put each number and each joining line."""
    weasyprint = pytest.importorskip("weasyprint")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    @page {{ size: A4; margin: 2cm; }} body {{ font-family: sans-serif; font-size: 11pt; }}
    {_steps_css()}
    ol.prodockit-steps {{ {extra} }}</style></head><body>
    <ol class="prodockit-steps"><li><p>One</p><p>More.</p></li><li><p>Two</p></li></ol>
    </body></html>"""
    page = weasyprint.HTML(string=html).render().pages[0]
    numbers: list[float] = []
    lines: list[float] = []
    def walk(box: object) -> None:
        tag = getattr(box, "element_tag", "")
        if type(box).__name__ == "AbsolutePlaceholder":
            centre = box.position_x + box.width / 2  # type: ignore[attr-defined]
            if tag == "li::before":
                numbers.append(centre)
            elif tag == "li::after":
                lines.append(centre)
        for child in getattr(box, "children", []):
            walk(child)
    walk(page._page_box)
    return list(zip(numbers, lines, strict=False))


@pytest.mark.parametrize(
    "change",
    [
        "",
        "--step-size: 3rem;",
        "--step-size: 1rem;",
        "--step-line: 6px;",
        "font-size: 1.6em;",
        "font-size: 0.7em;",
        # `em` is the one that used to fail: the number sets its own
        # font-size so the digits fit, so an `em` meant one thing in the
        # circle and another in the line - measured at -8.8pt adrift once
        # the text was scaled up.
        "--step-size: 1.65em;",
        "--step-size: 1.65em; font-size: 1.6em;",
    ],
)
def test_the_line_stays_centred_on_the_numbers(change: str) -> None:
    """Whatever is resized, the two are positioned from one measurement."""
    pairs = _centres(change)

    assert pairs, "nothing was laid out - the stylesheet did not apply"
    for number, line in pairs:
        assert abs(number - line) < 0.01, f"{change or 'as shipped'}: off by {number - line:+.2f}pt"


def test_the_last_step_has_no_trailing_line() -> None:
    """A line running past the final number points at nothing."""
    css = _steps_css()

    assert re.search(r"li:last-child::after\s*\{\s*content:\s*none", css), css[-400:]
