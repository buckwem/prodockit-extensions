# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""prodockit.index: mark a term inline for prodockit.pdf's own PDF-only
back-of-book index.

Confirmed directly, before settling on this syntax: plain ``attr_list``
can't wrap arbitrary inline text in a span at all on its own (`[Term]
{.index}` is left as literal text, unlike a block-level paragraph/heading,
which attr_list *does* support) - it only reaches inline content already
wrapped in something attr_list recognises (emphasis, a link, code), each
of which would force an unwanted visual side effect just to mark a term.
Raw inline HTML (`<span class="index">Term</span>`) works today with no
extension at all, but is exactly the "disrupts normal writing flow"
outcome the original issue wanted to avoid.

``\\index{Term}`` instead, matching this package's own established
convention for "mark something inline" (``\\ref{id}``, ``\\cite{id}``,
``\\gls{id}``) - unlike those, there's no separate "definition" step:
the term both displays inline exactly as written and is marked for
indexing in one go, and (unlike prodockit.refs/citations/glossary) needs
no shared registry or cross-page resolution at all - indexing happens
entirely inside prodockit.pdf, once every page is already concatenated
into a single document, so there's nothing here to coordinate across
pages in the first place.

**Hierarchical (sub-)entries**: ``\\index{Parent!Child!Grandchild}`` -
``!`` separates up to three levels, matching LaTeX ``makeidx``'s own
long-established ``\\index{primary!secondary!tertiary}`` convention. Only
the *last* segment displays inline (`Grandchild`, matching wherever the
term is actually mentioned in the prose) - the full path is carried on a
`data-index-term` attribute instead, for `prodockit.pdf.index` to build
the nested index from; a plain `\\index{Term}` (no `!`) has no such
attribute and behaves exactly as before.

**Code-styled terms**: ``\\index{`git commit`}`` (or, combined with
hierarchy, ``\\index{Git!`git commit`}``) - backticks around the *last*
segment mark it as a command/code term: it displays inline wrapped in a
real ``<code>`` element, and `prodockit.pdf.index` renders its own index
entry the same way (see `prodockit.pdf.css`'s existing document-wide
``code {}`` styling - no separate rule needed for the index to match).

This needs its own, separate `IndexCodeInlineProcessor` registered at a
*higher* priority than 'backtick' (190) - confirmed directly: at this
module's own low priority (`prodockit-index`, 42), Python-Markdown's
'backtick' pattern always gets first look at the *whole* text and stashes
any backtick pair it finds - including one sitting inside `\\index{...}` -
before a lower-priority pattern is ever tried, splitting `\\index{` and
`}` into separate fragments with the stashed code span in between, so a
single pattern at the usual priority could never see the whole construct.
Going higher than 'backtick' only for this specific, narrowly-shaped
pattern (requiring a backtick pair immediately before the closing `}`)
leaves the plain `\\index{Term}` pattern's own priority - and, confirmed
directly, its own "literal `` `\\index{Term}` `` stays untouched" example-
syntax escape hatch - completely unaffected: the code-styled pattern's
regex simply doesn't match plain text with no backticks, or a real code
span like `` `\\index{Term}` `` where the backticks sit *outside* the
whole call rather than immediately before its closing brace.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree

from markdown import Markdown, util
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor

#: The class prodockit.pdf.index's own mark_index_terms() looks for.
INDEX_TERM_CLASS = "index"

INDEX_RE = r"\\index\{([^}]+)\}"

#: See this module's own docstring for why this needs a separate pattern,
#: at a higher priority, rather than being folded into INDEX_RE above.
#: Group 1 is everything before the code segment (empty for a flat term,
#: or "Parent!"/"Parent!Child!" for a hierarchical one); group 2 is the
#: code segment's own inner text.
INDEX_CODE_RE = r"\\index\{([^}]*)`([^`}]+)`\}"


def _index_span(segments: list[str], *, code: bool) -> etree.Element:
    """Builds the `<span class="index">` element both InlineProcessors
    below emit - shared so the code-styled and plain paths stay in sync
    (`data-index-term`/`data-index-code` conventions, hierarchy handling).

    A code-styled term's own `<code>` text is wrapped in `util.AtomicString`
    (plus `util.code_escape`, HTML-escaping it) - the same two calls
    Python-Markdown's own `BacktickInlineProcessor` makes for a real code
    span. Confirmed directly this is needed: without it, a term like
    `git *rebase*` gets its own asterisks reprocessed into `<em>` by a
    later inline-pattern pass, same as this module's own plain (non-code)
    `\\index{Term}` display text already does deliberately - undesirable
    here, since a code/command term's own special characters should
    always stay literal, the same as inside any other code span.
    """
    el = etree.Element("span")
    el.set("class", INDEX_TERM_CLASS)
    if len(segments) > 1 or code:
        el.set("data-index-term", "!".join(segments))
    if code:
        el.set("data-index-code", "true")
        code_el = etree.SubElement(el, "code")
        code_el.text = util.AtomicString(util.code_escape(segments[-1]))
    else:
        el.text = segments[-1]
    return el


class IndexInlineProcessor(InlineProcessor):
    """Matches ``\\index{Term}`` and emits ``<span class="index">Term</span>``
    (or, for ``\\index{Parent!Child}``, ``<span class="index"
    data-index-term="Parent!Child">Child</span>`` - see this module's own
    docstring for the hierarchical syntax).

    Unlike `\\ref{id}`/`\\cite{id}`/`\\gls{id}` (each resolving a short id,
    not display text, via a later treeprocessor), the visible text isn't
    exempted from Python-Markdown's own subsequent inline-pattern passes -
    confirmed directly, `\\index{*emphasised*}` still renders as `<em>`
    inside the span, exactly as the same text would outside one. Harmless
    for indexing purposes either way: `prodockit.pdf.index`'s own
    `mark_index_terms()` reads the span's plain text via BeautifulSoup's
    `get_text()` (falling back to it whenever `data-index-term` isn't set),
    which already strips any nested tags regardless - only a flat term's
    *display* text can meaningfully carry nested markdown this way; a
    `data-index-term` path's own earlier segments are plain category
    labels, not reprocessed.

    Registered at a low inline-pattern priority so it runs after
    'backtick' (190) and 'escape' (180) - meaning inline code spans are
    already stashed out of reach by the time this pattern runs, so a
    literal `\\index{...}` shown as example syntax (e.g. in this
    project's own documentation) survives untouched.
    """

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        raw_path = m.group(1)
        segments = [segment.strip() for segment in raw_path.split("!")]
        if len(segments) > 1:
            el = _index_span(segments, code=False)
        else:
            # Preserved verbatim (not the stripped `segments[-1]`) - matches
            # this pattern's own long-standing behaviour for a flat term.
            el = etree.Element("span")
            el.set("class", INDEX_TERM_CLASS)
            el.text = raw_path
        return el, m.start(0), m.end(0)


class IndexCodeInlineProcessor(InlineProcessor):
    """Matches ``\\index{`Term`}``/``\\index{Parent!`Term`}`` - the code-
    styled variant. See this module's own docstring for the full syntax
    and why this needs a separate, higher-priority pattern."""

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element, int, int]:
        prefix, code_text = m.group(1), m.group(2)
        segments = [segment.strip() for segment in (prefix + code_text).split("!")]
        el = _index_span(segments, code=True)
        return el, m.start(0), m.end(0)


class IndexExtension(Extension):
    """Python-Markdown extension providing the ``\\index{Term}`` syntax -
    see this module's own docstring."""

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)
        md.inlinePatterns.register(
            IndexCodeInlineProcessor(INDEX_CODE_RE, md),
            "prodockit-index-code",
            195,
        )
        md.inlinePatterns.register(
            IndexInlineProcessor(INDEX_RE, md),
            "prodockit-index",
            42,
        )


def makeExtension(**kwargs: object) -> IndexExtension:
    return IndexExtension(**kwargs)
