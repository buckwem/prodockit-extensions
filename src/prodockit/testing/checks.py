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
# Keywords split by how much they prove on their own.
#
# `graph`/`flowchart` always carry a direction token in Mermaid
# (`graph LR`, `flowchart TD`), and that pairing does not occur in prose -
# so matching it makes the keyword line self-evidently a diagram. Bare
# "graph traversal is covered below" no longer matches at all, which is the
# false positive that started all of this.
#
# The rest of this group are names no sentence begins with by accident.
MERMAID_STRONG_KEYWORD_RE = re.compile(
    r"^\s*(?:(?:graph|flowchart)\s+(?:LR|RL|TB|BT|TD)\b"
    r"|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|erDiagram"
    r"|gitGraph|mindmap|quadrantChart|requirementDiagram)",
)

# These are ordinary English words that also happen to be diagram types, and
# Mermaid gives them no distinguishing token to key on. They are accepted
# only on the strongest evidence (see WEAK_LINK_RE below).
MERMAID_WEAK_KEYWORD_RE = re.compile(r"^\s*(?:gantt|journey|pie|timeline)\b")
#: Syntax that only a Mermaid diagram's own source contains. Three families,
#: because no single one survives every document:
#:
#: - Flowchart and sequence arrows (`-->`, `-->|`, `->>`, `==>`, `-.->`).
#: - Entity-relationship cardinality pairs. The ER form
#:   (`CUSTOMER ||--o{ ORDER : places`) has no arrowhead at all, so an
#:   arrow-only pattern silently misses every unrendered ER diagram.
#: - Node definitions (`id[Label]`, `id{Label}`). These matter because a
#:   PDF set in a font with programming ligatures - JetBrains Mono, a common
#:   choice for code blocks - renders `-->` as a single ligature glyph, and
#:   it extracts back out as `//>` rather than the characters written. The
#:   arrows are then invisible to any pattern looking for them, while the
#:   brackets, which are in no ligature set, survive intact. Found in
#:   prodockit-template, whose own PDF uses that font.
#:
#: Any one of the three is enough after a *strong* keyword.
MERMAID_LINK_RE = re.compile(
    r"--+>|--+\||-\.->|==+>|->>|--\s*$"
    r"|(?:\|\||\|o|\}o|\}\|)(?:--|\.\.)"
    r"|\w+\[[^\]\n]+\]|\w+\{[^}\n]+\}"
)

#: What a *weak* keyword needs: arrows or ER pairs only, never the node
#: brackets. `data[1]`, `items[0]` and `format{spec}` are all ordinary
#: technical prose, and a line beginning "pie charts are supported" or
#: "timeline of the project" followed by any of them would otherwise read as
#: an unrendered diagram.
MERMAID_WEAK_LINK_RE = re.compile(
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
    that was never rendered.

    Needs a diagram-type keyword *and* corroborating syntax shortly after
    it, with how much corroboration depending on how much the keyword
    proved on its own - see the two keyword patterns above.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        strong = MERMAID_STRONG_KEYWORD_RE.match(line)
        weak = MERMAID_WEAK_KEYWORD_RE.match(line) if not strong else None
        if not strong and not weak:
            continue
        pattern = MERMAID_LINK_RE if strong else MERMAID_WEAK_LINK_RE
        window = lines[index : index + 1 + MERMAID_LOOKAHEAD_LINES]
        if any(pattern.search(candidate) for candidate in window):
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
