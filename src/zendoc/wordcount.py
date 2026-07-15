# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""A rough prose word count for markdown source - the kind an assignment or
report with a submission word limit typically needs to show, on either the
website (see :mod:`zendoc.zensical_macros`) or the PDF (see
:mod:`zendoc.pdf`), and to enforce consistently between the two."""

from __future__ import annotations

import re


def count_words(text: str) -> int:
    """Rough prose word count for a single piece of markdown source text
    (or already-rendered HTML - the strips below handle either): strips
    fenced code blocks (any language, including e.g. a ```mermaid diagram's
    own source - never "content"), inline code, HTML comments/tags, and
    markdown link/image/emphasis syntax before splitting on whitespace.

    Not a precise count - close enough to show a submission's rough length
    against a word limit, not to enforce one exactly."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#*_~>|]", " ", text)
    return len(text.split())


def compute_word_count(texts: list[str]) -> int:
    """Sums :func:`count_words` across every text in `texts` - the caller
    decides which pages to include (e.g. excluding a cover page, or any
    page flagged `exclude_from_word_count: true` in its own front matter)."""
    return sum(count_words(text) for text in texts)
