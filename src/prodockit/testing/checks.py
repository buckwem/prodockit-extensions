# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Checks on a *built* PDF that apply to any prodockit project.

These exist because `prodockit.pdf` degrades quietly by design. Mermaid
diagrams and TeX maths are pre-rendered to static images (WeasyPrint has no
JS engine), and when a renderer isn't found the content is left exactly as
it is rather than failing the build - the right default for a project using
neither feature, and a silent disaster for one that does. Three separate
projects published PDFs full of raw `flowchart LR ...` source and literal
LaTeX before anyone noticed.

`prodockit pdf` warns about that since 0.12.0, but a warning in build output
is easy to scroll past. These turn it into a test failure.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

# A rendered Mermaid diagram contributes vector drawings, not text, so a
# diagram-type keyword surviving as text means the fence was passed through
# as a literal code block.
#
# The keyword alone is not enough to conclude that. Line breaks in a PDF
# fall wherever the text happens to wrap, and several of these words are
# ordinary English - a user guide describing "a visual commit graph and
# richer history browsing" wrapped so that "graph" began a line, and a
# keyword-only check read it as an unrendered diagram. It passed locally and
# failed in CI, purely because different fonts there wrapped the line
# differently.
#
# So: a keyword *and* Mermaid's own link syntax shortly after it. An
# unrendered fence dumps the whole block, so the arrows are always present;
# wrapped prose has nothing resembling them.
MERMAID_KEYWORD_RE = re.compile(
    r"^\s*(graph|flowchart|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|erDiagram|"
    r"gantt|journey|pie|gitGraph|mindmap|timeline|quadrantChart|requirementDiagram)\b",
)
#: Flowchart/sequence arrows, plus entity-relationship cardinality pairs.
#: The ER form (`CUSTOMER ||--o{ ORDER : places`) has no arrowhead at all,
#: so an arrow-only pattern silently misses every unrendered ER diagram -
#: its left-hand cardinality token followed by the `--`/`..` connector is
#: what identifies it.
MERMAID_LINK_RE = re.compile(
    r"--+>|--+\||-\.->|==+>|->>|--\s*$|(?:\|\||\|o|\}o|\}\|)(?:--|\.\.)"
)

#: How far after a keyword line to look for that link syntax. A diagram's
#: first link is on the very next line in practice; the slack covers a
#: direction declaration or comment in between.
MERMAID_LOOKAHEAD_LINES = 6

#: Unlike Mermaid, unrendered maths has no ambiguous-word problem - these
#: sequences don't occur in prose. `\[`/`\]` are what pymdownx.arithmatex's
#: generic mode emits around display maths.
TEX_SOURCE_RE = re.compile(r"\\\[|\\\]|\\sum_|\\frac\{|\\infty|\\begin\{|\\alpha\b|\\beta\b")


def contains_unrendered_mermaid(text: str) -> bool:
    """True if `text` (one PDF page) looks like it contains a Mermaid block
    that was never rendered."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not MERMAID_KEYWORD_RE.match(line):
            continue
        window = lines[index : index + 1 + MERMAID_LOOKAHEAD_LINES]
        if any(MERMAID_LINK_RE.search(candidate) for candidate in window):
            return True
    return False


def contains_unrendered_tex(text: str) -> bool:
    """True if `text` (one PDF page) contains TeX that was never rendered."""
    return bool(TEX_SOURCE_RE.search(text))


def find_unrendered_mermaid_pages(page_texts: Iterable[str]) -> list[int]:
    """Zero-based indexes of pages containing unrendered Mermaid source."""
    return [i for i, text in enumerate(page_texts) if contains_unrendered_mermaid(text)]


def find_unrendered_tex_pages(page_texts: Iterable[str]) -> list[int]:
    """Zero-based indexes of pages containing unrendered TeX source."""
    return [i for i, text in enumerate(page_texts) if contains_unrendered_tex(text)]


def assert_no_unrendered_mermaid(page_texts: Sequence[str]) -> None:
    """Fails if any page carries raw Mermaid source."""
    pages = find_unrendered_mermaid_pages(page_texts)
    assert not pages, (
        f"Literal Mermaid source found on PDF page(s) {pages} (0-based) - the "
        "diagram reached the PDF as a code block instead of a rendered image. "
        "Run `prodockit init-tools` and install the tooling, or set "
        "`pdf_mmdc_bin` in your config."
    )


def assert_no_unrendered_tex(page_texts: Sequence[str]) -> None:
    """Fails if any page carries raw TeX source."""
    pages = find_unrendered_tex_pages(page_texts)
    assert not pages, (
        f"Literal TeX source found on PDF page(s) {pages} (0-based) - the "
        "formula reached the PDF unrendered. Run `prodockit init-tools` and "
        "install the tooling, or set `pdf_tex2svg_script` in your config."
    )
