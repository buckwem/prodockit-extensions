# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Tests for `prodockit.testing.checks` - detecting Mermaid diagrams and TeX
maths that reached a PDF as raw source."""

from __future__ import annotations

import pytest

from prodockit.testing.checks import (
    assert_no_unrendered_mermaid,
    assert_no_unrendered_tex,
    contains_unrendered_mermaid,
    contains_unrendered_tex,
    find_unrendered_mermaid_pages,
    find_unrendered_tex_pages,
)

# Extracted verbatim from a PDF built without mermaid-cli installed.
UNRENDERED_MERMAID = (
    "they're a paid, approved service for hosting confidential company data.\n"
    "graph LR\n"
    "  A[Start] --> B{Error?};\n"
    "  B -->|Yes| C[Hmm...];\n"
    "  C --> D[Debug];\n"
)

# The false positive that broke a real CI run: ordinary prose that wrapped so
# a diagram keyword began a line. Green locally, red in CI, because the fonts
# there wrapped the sentence differently.
WRAPPED_PROSE = (
    "annotations - showing who last changed each line, and when -\n"
    "directly above your text, along with a visual commit\n"
    "graph and richer history browsing. It's especially useful once\n"
    "you're using the branches and issues workflow.\n"
)

UNRENDERED_TEX = (
    "details, go to the math documentation.\n"
    "\\[ \\cos x=\\sum_{k=0}^{\\infty}\\frac{(-1)^k}{(2k)!}x^{2k} \\]\n"
)


def test_detects_a_genuinely_unrendered_mermaid_block() -> None:
    assert contains_unrendered_mermaid(UNRENDERED_MERMAID)


@pytest.mark.parametrize(
    "source",
    [
        "sequenceDiagram\n    Alice->>John: Hello John\n",
        "stateDiagram-v2\n    [*] --> Still\n",
        "flowchart TD\n    A-->B\n",
        "erDiagram\n    CUSTOMER ||--o{ ORDER : places\n",
    ],
)
def test_detects_other_diagram_types(source: str) -> None:
    assert contains_unrendered_mermaid(source)


def test_does_not_flag_prose_that_wraps_onto_a_diagram_keyword() -> None:
    """Regression test for a real CI failure. A keyword-only check reads
    'a visual commit / graph and richer history browsing' as a diagram."""
    assert not contains_unrendered_mermaid(WRAPPED_PROSE)


@pytest.mark.parametrize(
    "prose",
    [
        "We considered Mermaid diagrams and flowcharts, but used neither.\n",
        "The pie chart below shows the split.\n",
        "A timeline of the project follows.\n",
        "This journey begins with installation.\n",
    ],
)
def test_does_not_flag_ordinary_english_starting_a_line(prose: str) -> None:
    """`pie`, `timeline`, `journey`, `graph` are all real Mermaid diagram
    types and all ordinary words - the link-syntax requirement is what keeps
    them apart."""
    assert not contains_unrendered_mermaid(prose)


def test_detects_unrendered_tex() -> None:
    assert contains_unrendered_tex(UNRENDERED_TEX)


def test_does_not_flag_prose_mentioning_maths() -> None:
    assert not contains_unrendered_tex(
        "Zensical supports mathematical notation using MathJax. Write inline "
        "maths with the dollar syntax.\n"
    )


def test_finds_the_offending_page_numbers() -> None:
    pages = ["clean", UNRENDERED_MERMAID, "clean", UNRENDERED_MERMAID]
    assert find_unrendered_mermaid_pages(pages) == [1, 3]
    assert find_unrendered_tex_pages(["clean", UNRENDERED_TEX]) == [1]


def test_assertions_pass_on_clean_output() -> None:
    clean = ["a page", "another page", WRAPPED_PROSE]
    assert_no_unrendered_mermaid(clean)
    assert_no_unrendered_tex(clean)


def test_assertions_fail_with_the_page_number_and_the_fix() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_no_unrendered_mermaid(["clean", UNRENDERED_MERMAID])
    message = str(excinfo.value)
    assert "[1]" in message
    assert "prodockit init-tools" in message, "the failure should name the fix"

    with pytest.raises(AssertionError, match="prodockit init-tools"):
        assert_no_unrendered_tex([UNRENDERED_TEX])
