# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Collect semantics, then edit source spans; never render entire pages in Python.

The CommonMark tokenizer is a conservative boundary, not a claim of PyMdown
compatibility. Unsupported containers/generators are refused in this prototype.
Python-Markdown is used for isolated headings and definition attributes, with
explicit source identities. No Zensical context or extension discovery runs.
"""

from __future__ import annotations

import html
import re
import string
import xml.etree.ElementTree as ET
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import markdown
import yaml
from bs4 import BeautifulSoup
from markdown.extensions.attr_list import get_attrs_and_remainder

from prodockit._zensical_defaults import DOCUMENTED_MARKDOWN_DEFAULTS
from prodockit.bibliography import BibliographyResolverTreeprocessor, _BibliographyCache
from prodockit.image_hotspots import _render as render_hotspots
from prodockit.portable import PortableError, macros, snippets, step_blocks, tree_blocks
from prodockit.portable.captions import (
    CAPTION_EXTENSION,
    Caption,
    read_caption,
    register_caption_rule,
)
from prodockit.portable.containers import is_aligned_fence, register_container_rule
from prodockit.portable.inputs import MaterializedInputs
from prodockit.portable.literal_html import mask_literal_text
from prodockit.portable.source_map import SourceProjection, SourceText, apply_edits
from prodockit.project_config import ProjectConfig
from prodockit.semantics import (
    PageCollector,
    PageContext,
    PageOutline,
    continuous_numbering,
    resolve_reference,
)
from prodockit.tables import TableError, validate_table_attributes
from prodockit.util import CitationRegistry, GlossaryRegistry, IdRegistry, cross_page_href
from prodockit.zensical_macros import heading_counter_style

_COMMAND = re.compile(
    r"\\(?P<name>autoref|ref|cite|gls)\{(?P<key>[^{}\s,]+)\}"
    r"|\\(?P<manual>citeref)\{(?P<keys>[^{}\n]+)\}"
    r"|\\(?P<local>pagebibliography)(?!\w)(?:\{(?P<local_file>[^{}\n]*)\})?"
    r"(?:\{(?P<heading>[^{}\n]*)\})?"
    r"|\\(?P<bib>bibliography)(?!\w)(?:\{(?P<file>[^{}]*)\})?"
    r"(?:\{(?P<cited>true|false)\})?"
)
_AFFECTED_SYNTAX = (
    r"\\(?:pagebibliography|citeref|gls|cite|ref|autoref|bibliography)\b"
    r"|\{[{%]|--8<--"
)
_CONTAINER_MARKER = r"^\s*(?:!!!|\?\?\?|===|///)"
_UNSUPPORTED = re.compile(_AFFECTED_SYNTAX + "|" + _CONTAINER_MARKER, re.MULTILINE)
_EXPLICIT_AFFECTED = re.compile(_AFFECTED_SYNTAX)
_HTML_CONTAINER_MARKER = re.compile(_CONTAINER_MARKER, re.MULTILINE)
_LIST_MARKER = re.compile(r" *(?:[-+*]|[0-9]+\.)(?: {1,4}(?! )|(?=\n|$))")
_ATTRS = re.compile(r"\s+\{(?::\s*)?([^{}]*)\}\s*$")
DEFINITION_EXTENSIONS = {
    "data-term": "prodockit.glossary",
    "data-cite-text": "prodockit.citations",
}
_DEFINITION_NAMES = {"data-term": "glossary", "data-cite-text": "citation"}
_DEFINITION_ASSIGNMENT = re.compile(r"\b(data-term|data-cite-text)\s*=")
_DEFINITION_ATTRS = re.compile(
    r"""\{(?::\s*)?(?=[^\n]*\b(?:data-term|data-cite-text)\s*=)"""
    r"""((?:"[^"\n]*"|'[^'\n]*'|[^"'{}\n])*)\}"""
)
_ATTR_TOKEN = re.compile(r"""[^\s=]+="[^"]*"|[^\s=]+='[^']*'|[^\s]+""")
BIBLIOGRAPHY_MARKERS = {"bibliography", "pagebibliography"}


@dataclass
class Edit:
    start: int
    end: int
    kind: str
    value: str
    key: str = ""
    cited: bool = False
    heading: str = ""


@dataclass(frozen=True)
class Definition:
    start: int
    attribute: str
    key: str
    label: str


@dataclass
class Page:
    source: str
    text: str
    meta: dict[str, Any]
    original: SourceText
    projection: SourceProjection
    edits: list[Edit] = field(default_factory=list)
    headings: list[tuple[int, int, str]] = field(default_factory=list)
    targets: list[dict[str, Any]] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    caption_targets: list[dict[str, str]] = field(default_factory=list)
    definitions: list[Definition] = field(default_factory=list)
    snippets: dict[int, Path] = field(default_factory=dict)


def _source_line(page: Page, offset: int) -> int:
    return page.original.text.count("\n", 0, page.projection.source_offset(offset)) + 1


def _location(page: Page, offset: int) -> str:
    return f"{page.source}:{_source_line(page, offset)}"


def _error(page: Page, offset: int, message: str) -> PortableError:
    return PortableError(f"{_location(page, offset)}: {message}")


def _tokenizer(extensions: Collection[str]) -> Any:
    try:
        from markdown_it import MarkdownIt
    except ImportError as error:
        raise PortableError(
            "install the optional prototype with pip install 'prodockit[portable]'"
        ) from error

    def command(state: Any, silent: bool) -> bool:
        match = _COMMAND.match(state.src, state.pos)
        if match is None:
            unsupported = _UNSUPPORTED.match(state.src, state.pos)
            if unsupported is not None:
                if not silent:
                    token = state.push("pdk_unsupported", "", 0)
                    token.content = unsupported.group()
                state.pos = unsupported.end()
                return True
            return False
        if not silent:
            token = state.push("pdk_command", "", 0)
            token.meta = {
                "start": state.pos,
                "end": match.end(),
                "kind": match.group("name") or match.group("manual") or match.group("local")
                or "bibliography",
                "key": match.group("key") or match.group("keys") or match.group("file")
                or match.group("local_file") or "",
                "cited": match.group("cited") == "true",
                "heading": (match.group("heading") or "").strip(),
                "in_link": state.linkLevel > 0,
            }
        state.pos = match.end()
        return True

    parser = MarkdownIt("commonmark")
    register_caption_rule(parser)
    register_container_rule(parser, extensions)
    if tree_blocks.EXTENSION in extensions:
        tree_blocks.register_tree_rule(parser)
    if step_blocks.EXTENSION in extensions:
        step_blocks.register_step_rule(parser)
    parser.core.ruler.disable(["text_join"])
    parser.inline.ruler.before("escape", "pdk_command", command)
    return parser


def _definitions(
    page: Page,
    start: int,
    raw: str,
    content: str,
    top_level: bool,
    active_attributes: Collection[str],
) -> None:
    """Consume only a paragraph's standalone attribute list, keeping its other attributes."""
    matches = list(_DEFINITION_ATTRS.finditer(content))
    # A dedicated final attribute line owns the paragraph. Earlier inline
    # literals in its body may contain examples of the same attribute syntax.
    if matches and content[matches[-1].start() - 1:matches[-1].start()] == "\n":
        matches = matches[-1:]
    for match in matches:
        attrs, remainder = get_attrs_and_remainder(match[1].strip())
        labels = [(name, value) for name, value in attrs if name in active_attributes]
        if not labels:
            continue
        at = raw.find(content)
        begin = start + max(at, 0) + match.start()
        keys = [value for name, value in attrs if name == "id"]
        tokens = _ATTR_TOKEN.findall(match[1])
        others = [token for token in tokens if token.partition("=")[0] not in active_attributes]
        first = labels[0][0]
        kind = _DEFINITION_NAMES[first]
        if (
            not top_level or at < 0 or raw.strip() != content
            or content[match.start() - 1:match.start()] != "\n"
            or content[match.end():].strip()
            or remainder or len({name for name, _ in labels}) != len(labels)
            or len(tokens) != len(attrs) or len(tokens) - len(others) != len(labels)
            or len(keys) != 1 or not keys[0] or any(not value for _, value in labels)
        ):
            raise _error(
                page, begin,
                f"put each {kind} definition in a top-level paragraph with a separate "
                f"attribute line containing one ID and one {first} value",
            )
        # Qualify this attribute line with the same parser as the existing
        # adaptor. In particular, decode entities exactly as that parser does.
        rendered = markdown.markdown("Definition\n" + match[0], extensions=["attr_list"])
        paragraph = BeautifulSoup(rendered, "html.parser").p
        for attribute, _ in labels:
            label = paragraph.get(attribute) if paragraph is not None else None
            if paragraph is None or paragraph.get("id") != keys[0] or not isinstance(label, str):
                raise _error(
                    page, begin, f"{kind} definition attributes were not parsed as authored"
                )
            page.definitions.append(Definition(begin, attribute, keys[0], label))
        retained = "{: " + " ".join(others) + " }"
        page.edits.append(Edit(begin, begin + len(match[0]), f"{kind}-definition", retained))


def scan(
    source: str,
    text: str,
    *,
    extensions: Collection[str] = (),
    caption_options: dict[str, Any] | None = None,
    macro_context: macros.ConditionalContext | None = None,
) -> Page:
    """Retain original spans, protecting code with the tokenizer's own rules."""
    original = SourceText.read(text)
    text = original.text
    lines = text.splitlines(keepends=True)
    body_start = 0
    front_matter = ""
    meta: dict[str, Any] = {}
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() in {"---", "..."}), None)
        if end is None:
            raise PortableError(f"{source}: unclosed front matter")
        front_matter = "".join(lines[1:end])
        try:
            value = yaml.safe_load(front_matter)
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            line = mark.line + 2 if mark is not None else 2
            raise PortableError(f"{source}:{line}: invalid YAML front matter") from error
        if value is not None and not isinstance(value, dict):
            raise PortableError(f"{source}: front matter must be a mapping")
        meta = value or {}
        body_start = sum(map(len, lines[: end + 1]))
    def source_location(offset: int) -> str:
        return "{}:{}".format(source, text.count("\n", 0, body_start + offset) + 1)

    removed = (
        macros.conditional_removals(
            text[body_start:],
            macro_context or macros.ConditionalContext({}),
            front_matter,
            source_location,
        )
        if macros.EXTENSION in extensions else []
    )
    projection = SourceProjection.select(
        text, [(body_start + start, body_start + end) for start, end in removed]
    )
    text = projection.text
    page = Page(source, text, meta, original, projection)
    active_attributes = {
        name for name, extension in DEFINITION_EXTENSIONS.items() if extension in extensions
    }
    if meta.get("template") or meta.get("render_macros"):
        raise _error(page, 0, "generated page content is outside the portable prototype")
    body = text[body_start:]
    offsets = [body_start]
    for line in body.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    tokens = _tokenizer(extensions).parse(body)
    if step_blocks.EXTENSION in extensions:
        step_blocks.qualify_steps(tokens, lambda line: _location(page, offsets[line]))
    macro_calls = {
        body_start + offset: name
        for offset, name in macros.styling_calls(
            body, lambda offset: _location(page, body_start + offset)
        ).items()
    } if macros.EXTENSION in extensions else {}
    if macro_calls and meta.get("render_macros") is False:
        raise _error(page, min(macro_calls), "portable styling calls require macro rendering")
    if snippets.EXTENSION in extensions:
        header_lines = text.count("\n", 0, body_start)
        code_lines = {
            line + header_lines
            for token in tokens
            if token.type == "fence" and token.level == 0
            and token.info.strip() != "image-hotspots"
            and token.map is not None
            for line in range(token.map[0] + 1, token.map[1])
        }
        line_offset = 0
        for index, line in enumerate(text.splitlines(keepends=True)):
            if "8<-" in line:
                name = snippets.directive(
                    line.removesuffix("\n"), location=_location(page, line_offset),
                    in_code=index in code_lines,
                )
                if name is not None:
                    page.snippets[_source_line(page, line_offset)] = name
            line_offset += len(line)
    container_depth = 0
    list_items = []
    for index, token in enumerate(tokens):
        if token.type == "list_item_open":
            list_items.append(token)
        elif token.type == "list_item_close":
            list_items.pop()
        if token.type == "pdk_container_close":
            container_depth -= 1
            continue
        if token.map is None:
            continue
        start, end = (offsets[n] for n in token.map)
        if token.type == "pdk_container_open":
            container_depth += 1
            if token.meta["heading_title"]:
                raise _error(page, start, "headings in collapsible titles are unsupported")
        elif token.type == "pdk_tree":
            if not token.meta["closed"]:
                raise _error(page, start, "unclosed tree block")
            if token.meta.get("step_body_fence") == token.markup:
                raise _error(page, start, "a tree must use a different fence from its step")
            tree_blocks.check_options(token.meta["options"], _location(page, start))
            match = _EXPLICIT_AFFECTED.search(text, start, end)
            if match is not None:
                raise _error(page, match.start(), "affected syntax in tree content is unsupported")
        elif token.type == "pdk_caption":
            step_fence = token.meta.get("step_body_fence")
            if container_depth and step_fence is None and "admonition_indent" not in token.meta:
                raise _error(page, start, "numbered captions in native containers are unsupported")
            if step_fence == token.markup:
                raise _error(page, start, "a caption must use a different fence from its step")
            if caption_options is None:
                raise _error(page, start, "caption blocks require pymdownx.blocks.caption")
            block = text[start:end]
            interior = "\n".join(block.splitlines()[1:-1])
            if _UNSUPPORTED.search(interior) or re.search(r"(?m)^\s*#{1,6}\s", interior):
                raise _error(page, start, "affected syntax inside captions is unsupported")
            page.captions.append(
                read_caption(source, start, _source_line(page, start), block, caption_options)
            )
        elif token.type == "fence":
            if container_depth and re.search(r"(?:^|[.\s])image-hotspots\b", token.info):
                raise _error(page, start, "nested hotspots are outside the portable prototype")
            if token.info.strip() == "image-hotspots":
                if token.level != 0:
                    raise _error(page, start, "nested hotspots are outside the portable prototype")
                page.edits.append(Edit(start, end, "hotspots", token.content))
            elif container_depth and (
                "pymdownx.superfences" not in extensions
                or not is_aligned_fence(text[start:end], token.markup, token.info)
            ):
                raise _error(
                    page, start, "nested code requires an aligned, closed SuperFences block"
                )
        elif container_depth and token.type == "code_block" and (
            _UNSUPPORTED.search(token.content)
            or re.search(r"(?m)^\s*#", token.content)
            or active_attributes.intersection(_DEFINITION_ASSIGNMENT.findall(token.content))
        ):
            raise _error(page, start, "use a closed fence for affected syntax in nested code")
        elif token.type == "html_block":
            content = mask_literal_text(token.content)
            if (
                _EXPLICIT_AFFECTED.search(token.content)
                or _HTML_CONTAINER_MARKER.search(content)
                or active_attributes.intersection(_DEFINITION_ASSIGNMENT.findall(content))
                or (container_depth and re.search(
                    r"<h[1-6]\b|\bmarkdown[ \t]*=", content, re.IGNORECASE
                ))
            ):
                raise _error(
                    page, start, "affected syntax in HTML is outside the portable prototype"
                )
        elif token.type == "heading_open":
            if token.level != 0 or not token.markup.startswith("#"):
                raise _error(
                    page, start, "only top-level ATX headings are supported by the prototype"
                )
            following = tokens[index + 1]
            if any(child.type == "pdk_command" for child in following.children or []):
                raise _error(page, start, "references inside headings are outside the prototype")
            page.headings.append((start, end, text[start:end].rstrip("\n")))
        elif token.type == "inline":
            paragraph = tokens[index - 1].type == "paragraph_open"
            top_level = token.level == 1 and paragraph
            raw = text[start:end]
            if start in macro_calls:
                if not top_level or "\n" in raw.rstrip("\n"):
                    raise _error(page, start, "put portable styling calls in a top-level paragraph")
                if macro_calls.pop(start) in macros.HEADING_NAMES:
                    page.edits.append(Edit(start, end, "heading-counter-style", ""))
                continue
            children = token.children or []
            for child in children:
                if child.type == "pdk_unsupported":
                    raise _error(
                        page,
                        start,
                        "unsupported syntax or generated content in the portable prototype",
                    )
                if child.type in {"text", "html_inline"} and _UNSUPPORTED.search(child.content):
                    raise _error(
                        page,
                        start,
                        "unsupported syntax or generated content in the portable prototype",
                    )
                if child.type == "html_inline" and active_attributes.intersection(
                    _DEFINITION_ASSIGNMENT.findall(child.content)
                ):
                    raise _error(page, start, "definitions in HTML are unsupported")
            if active_attributes and any(
                child.type == "text" and any(name in child.content for name in active_attributes)
                for child in children
            ):
                _definitions(page, start, raw, token.content, top_level, active_attributes)
            commands = [child.meta for child in children if child.type == "pdk_command"]
            if not commands:
                continue
            list_item = (
                list_items[-1]
                if paragraph and list_items and token.level == list_items[-1].level + 2
                else None
            )
            nested_references = (
                paragraph
                and (
                    list_item is not None
                    or "step_body_fence" in token.meta
                    or "admonition_indent" in token.meta
                )
                and all(item["kind"] in {"ref", "autoref"} for item in commands)
            )
            if not top_level and not nested_references:
                raise _error(
                    page, start, "affected syntax in nested content is outside the prototype"
                )
            if list_item is not None:
                first_line = list_item.map[0]
                opening = text[offsets[first_line]:offsets[first_line + 1]]
                projected = _list_paragraph_source(raw, opening, first_line == token.map[0])
            else:
                projected = _paragraph_source(raw, token.meta.get("admonition_indent", 0))
            if projected is None:
                raise _error(page, start, "cannot map the list marker to an exact source span")
            at = projected.text.find(token.content)
            if at < 0 or projected.text.strip() != token.content:
                raise _error(page, start, "cannot map the affected content to an exact source span")
            for item in commands:
                if item["in_link"]:
                    raise _error(page, start, "references inside links are outside the prototype")
                a = start + projected.source_offset(at + item["start"])
                b = start + projected.source_offset(at + item["end"] - 1) + 1
                if item["kind"] in BIBLIOGRAPHY_MARKERS and text[a:b] != token.content:
                    raise _error(page, a, "put the bibliography marker alone in its paragraph")
                page.edits.append(
                    Edit(a, b, item["kind"], "", item["key"], item["cited"], item["heading"])
                )
    if macro_calls:
        raise _error(page, min(macro_calls), "put portable styling calls in a top-level paragraph")
    return page


def _paragraph_source(raw: str, indentation: int) -> SourceProjection:
    """Map a direct admonition paragraph through its authored indentation."""
    if not indentation:
        return SourceProjection.select(raw, [])
    prefix = " " * indentation
    removed: list[tuple[int, int]] = []
    offset = 0
    for line in raw.splitlines(keepends=True):
        if not line.startswith(prefix):
            # The caller's exact-content check rejects ambiguous indentation.
            return SourceProjection.select(raw, [])
        removed.append((offset, offset + indentation))
        offset += len(line)
    return SourceProjection.select(raw, removed)


def _list_paragraph_source(
    raw: str, opening: str, starts_item: bool
) -> SourceProjection | None:
    """Map a list paragraph after removing its marker and continuation indentation."""
    marker = _LIST_MARKER.match(opening)
    if marker is None:
        return None
    indentation = marker.end() + (1 if opening[marker.end():].startswith("\n") else 0)
    removed: list[tuple[int, int]] = []
    offset = 0
    for line in raw.splitlines(keepends=True):
        prefix = (
            marker.end()
            if starts_item and offset == 0
            else min(indentation, len(line) - len(line.lstrip(" ")))
        )
        if prefix:
            removed.append((offset, offset + prefix))
        offset += len(line)
    return SourceProjection.select(raw, removed)


def _parsed_headings(page: Page) -> list[ET.Element]:
    md = markdown.Markdown(extensions=["attr_list", "toc"], output_format="xhtml")
    # Parse only headings; unaffected page content still goes through Zensical.
    parsed = md.convert("\n\n".join(line for _, _, line in page.headings))
    root = ET.fromstring(f"<div>{parsed}</div>")
    headings = list(root)
    if len(headings) != len(page.headings) or any(
        not re.fullmatch("h[1-6]", h.tag) for h in headings
    ):
        raise PortableError(f"{page.source}: heading tokenizers disagree")
    return headings


def _render_page_bibliographies(
    page: Page, cache: _BibliographyCache, options: dict[str, Any], links: list[dict[str, str]]
) -> None:
    """Reuse citeproc's resolver with only bibliography tokens and an explicit page."""
    if not any(edit.kind in {"cite", "pagebibliography"} for edit in page.edits):
        return
    root = ET.Element("div")
    citations: list[tuple[Edit, ET.Element]] = []
    for edit in sorted(page.edits, key=lambda item: item.start):
        if edit.kind == "cite":
            node = ET.SubElement(root, "span", {"data-prodockit-bib-cite": edit.key})
            citations.append((edit, node))
        elif edit.kind == "pagebibliography":
            ET.SubElement(
                ET.SubElement(root, "p"),
                "span",
                {
                    "data-prodockit-bibliography-file": edit.key,
                    "data-prodockit-bibliography-scope": "page-cited",
                    "data-prodockit-bibliography-heading": edit.heading or "References",
                },
            )
    resolver = BibliographyResolverTreeprocessor(
        markdown.Markdown(),
        cache,
        page.source,
        str(options.get("unresolved", "?")),
        bool(options.get("page_backlinks", True)),
        bool(options.get("page_backlink_numbers", False)),
    )
    resolver.run(root)

    for edit, node in citations:
        edit.value = ET.tostring(node, encoding="unicode", method="html")
        anchor = node.find("a")
        if anchor is not None:
            href = anchor.attrib["href"]
            target = (
                page.source if href.startswith("#") else resolver._link_target_for_key(edit.key)
            )
            assert target is not None
            label = BeautifulSoup(edit.value, "html.parser").a
            assert label is not None
            links.append(
                {"page": target, "id": f"ref-{edit.key}", "text": label.get_text(" ", strip=True)}
            )

    for section in root.findall("section"):
        heading = section.find("h2")
        assert heading is not None and heading.text
        # A native Markdown heading participates in Zensical's ordinary ToC.
        # Encode punctuation so a custom plain-text title cannot become Markdown.
        title = "".join(
            f"&#{ord(char)};" if char in string.punctuation else char for char in heading.text
        )
        section.remove(heading)
        content = ET.tostring(section, encoding="unicode", method="html")
        end = len(page.text)
        block = f"\n\n## {title}\n\n{content}\n"
        page.edits.append(Edit(end, end, "pagebibliography-output", block))
        for backlink in section.iter("a"):
            if backlink.get("class") == "prodockit-bib-backlink":
                links.append(
                    {
                        "page": page.source,
                        "id": backlink.attrib["href"].removeprefix("#"),
                        "text": backlink.text or "",
                    }
                )


def _heading_records(
    page: Page, headings: list[ET.Element], context: PageContext, registry: IdRegistry,
) -> None:
    collector = PageCollector(context, registry)
    captions = iter(page.captions)
    caption = next(captions, None)

    def register(caption: Caption) -> None:
        collector.caption(caption.kind, caption.ident, "")
        label = collector.numbering.caption_label(caption.kind)
        page.edits.append(
            Edit(
                caption.options_start, caption.options_end, "caption-options",
                caption.numbered_options(label),
            )
        )
        page.caption_targets.append(
            {"id": caption.ident or "", "number": label, "kind": caption.kind}
        )

    for (start, end, line), heading in zip(page.headings, headings, strict=True):
        while caption is not None and caption.start < start:
            register(caption)
            caption = next(captions, None)
        ident = heading.get("id") or ""
        record = collector.heading(
            ident, int(heading.tag[1]), "".join(heading.itertext()),
            unnumbered="unnumbered" in (heading.get("class") or "").split(),
        )
        page.targets.append({"id": ident, "text": record.text, "number": record.number})
        # Preserve authored attributes, adding an explicit renderer-independent ID.
        line = re.sub(r"\s+#+\s*$", "", line)
        attrs = _ATTRS.search(line)
        if attrs is not None:
            if not re.search(r"(?:^|\s)(?:#\S+|id\s*=)", attrs.group(1)):
                line = line[: attrs.start()] + f" {{: {attrs.group(1)} #{ident} }}"
        else:
            line += f" {{: #{ident} }}"
        page.edits.append(Edit(start, end, "heading", line + "\n"))
    while caption is not None:
        register(caption)
        caption = next(captions, None)


def _validate_page_tables(page: Page) -> None:
    line_starts = [0, *(match.end() for match in re.finditer("\n", page.text))]
    try:
        validate_table_attributes(
            page.text.split("\n"), lambda line: _location(page, line_starts[line - 1])
        )
    except TableError as error:
        raise PortableError(str(error)) from error


def compile_pages(
    config: ProjectConfig,
    sources: dict[str, str],
    *,
    inputs: MaterializedInputs,
    pandoc: Path | None = None,
) -> tuple[dict[str, str], dict[str, Any], set[Path]]:
    """Compile the supported slice with explicit ownership and two passes."""
    extensions = (
        config.markdown_extensions if "markdown_extensions" in config.project
        else DOCUMENTED_MARKDOWN_DEFAULTS
    ).keys()
    caption_options = config.markdown_extensions.get(CAPTION_EXTENSION)
    macro_context = macros.ConditionalContext.from_config(
        config.project, config.markdown_extensions
    )
    pages = {
        source: scan(
            source, text, extensions=extensions, caption_options=caption_options,
            macro_context=macro_context,
        )
        for source, text in sources.items()
    }
    if "prodockit.tables" in extensions:
        for page in pages.values():
            _validate_page_tables(page)
    nav_order = list(dict.fromkeys(p.source_path for p in config.nav_pages))
    missing = set(nav_order) - pages.keys()
    if missing:
        raise PortableError(f"navigation pages are missing: {', '.join(sorted(missing))}")
    order = nav_order + sorted(pages.keys() - set(nav_order))
    registry = IdRegistry()
    glossary = GlossaryRegistry()
    citations = CitationRegistry()
    for source in order:
        for definition in pages[source].definitions:
            book = glossary if definition.attribute == "data-term" else citations
            if definition.key in book:
                kind = "glossary term" if definition.attribute == "data-term" else "citation key"
                raise _error(
                    pages[source], definition.start, f"duplicate {kind} {definition.key!r}"
                )
            book.register(source, definition.key, definition.label)
    heading_options = config.markdown_extensions.get("prodockit.headings", {})
    enabled = bool({"prodockit.headings", "prodockit.refs"} & config.markdown_extensions.keys())
    if not enabled and any(page.captions for page in pages.values()):
        raise PortableError(
            "portable caption numbering requires prodockit.headings or prodockit.refs"
        )
    continuous = heading_options.get("numbering") == "continuous"
    if continuous and not nav_order:
        raise PortableError("continuous numbering requires explicit navigation in the prototype")
    parsed = {source: _parsed_headings(pages[source]) for source in order} if enabled else {}
    starts: dict[str, int] = {}
    appendices: dict[str, str] = {}
    if continuous and enabled:
        outlines = [PageOutline(
            source,
            sum(
                1 for heading in parsed[source]
                if heading.tag == "h1" and "unnumbered" not in (heading.get("class") or "").split()
            ),
            bool(pages[source].meta.get(heading_options.get("appendix_attr", "is_appendix"))),
        ) for source in nav_order]
        if sum(page.is_appendix for page in outlines) > 26:
            raise PortableError("the prototype supports at most 26 appendices")
        starts, appendices = continuous_numbering(outlines)
    heading_style_enabled = bool((config.project.get("extra") or {}).get("heading_numbering", True))
    contexts = {
        source: PageContext(source, starts.get(source, 0), appendices.get(source))
        for source in order
    }
    for source in order:
        page = pages[source]
        if not enabled:
            continue
        _heading_records(page, parsed[source], contexts[source], registry)

    dependencies: set[Path] = set()

    def dependency(path: str) -> str:
        original = (config.root / path).resolve()
        dependencies.add(original)
        return str(inputs.dependency(original))

    bib_options = config.markdown_extensions.get("prodockit.bibliography", {})
    default_bib = str(bib_options.get("bib_file", "references.bib"))
    style = str(bib_options.get("csl_style", ""))
    bib_used = any(
        e.kind == "cite" or e.kind in BIBLIOGRAPHY_MARKERS
        for p in pages.values() for e in p.edits
    )
    if bib_used:
        default_bib = dependency(default_bib)
        style = dependency(style) if style else ""
    cache = _BibliographyCache(default_bib, style, pandoc=pandoc)
    if bib_used:
        if "prodockit.bibliography" not in config.markdown_extensions:
            raise PortableError("bibliography syntax requires prodockit.bibliography configuration")
        if pandoc is None:
            raise PortableError(
                "the bibliography prototype requires --pandoc PATH to an installed Pandoc"
            )
        for source in order:
            for edit in pages[source].edits:
                if edit.kind in BIBLIOGRAPHY_MARKERS:
                    file = edit.key.strip()
                    edit.key = dependency(file) if file else default_bib
                    if edit.key not in cache.all_bib_files:
                        cache.all_bib_files.append(edit.key)
                    if edit.kind == "bibliography":
                        cache.first_page_for_file.setdefault(edit.key, source)
                elif edit.kind == "cite":
                    cache.all_cited_keys.add(edit.key)

    local_bibliographies = any(
        edit.kind == "pagebibliography" for page in pages.values() for edit in page.edits
    )
    outputs: dict[str, str] = {}
    details: dict[str, Any] = {}
    for source in order:
        page = pages[source]
        links: list[dict[str, str]] = []
        if local_bibliographies:
            _render_page_bibliographies(page, cache, bib_options, links)
        for edit in page.edits:
            if edit.kind == "heading-counter-style":
                if heading_style_enabled and (
                    not continuous or heading_options.get("appendix_attr", "is_appendix")
                    != "is_appendix"
                ):
                    raise _error(
                        page, edit.start,
                        "portable heading-counter styling requires continuous numbering "
                        "and the default appendix flag",
                    )
                context = contexts[source]
                edit.value = heading_counter_style(
                    context.start_count, context.appendix_letter, enabled=heading_style_enabled
                ) + ("\n" if page.text[edit.start:edit.end].endswith("\n") else "")
            elif edit.kind in {"ref", "autoref"}:
                if "prodockit.refs" not in config.markdown_extensions:
                    raise _error(
                        page, edit.start, "reference syntax requires prodockit.refs configuration"
                    )
                reference = resolve_reference(contexts[source], registry, edit.key)
                if reference is None:
                    raise _error(page, edit.start, f"unresolved reference {edit.key!r}")
                href, label = reference.href, reference.text
                edit.value = (
                    f'<a class="prodockit-{edit.kind}" href="{html.escape(href, quote=True)}">'
                    f"{html.escape(label)}</a>"
                )
                links.append({"page": reference.target.source, "id": edit.key, "text": label})
            elif edit.kind == "gls":
                if "prodockit.glossary" not in extensions:
                    raise _error(page, edit.start, "glossary syntax requires prodockit.glossary")
                term_record = glossary.get(edit.key)
                if term_record is None:
                    raise _error(page, edit.start, f"unresolved glossary term {edit.key!r}")
                href = cross_page_href(term_record.source, source, edit.key)
                edit.value = (
                    f'<a class="prodockit-gls" href="{html.escape(href, quote=True)}">'
                    f"{html.escape(term_record.text)}</a>"
                )
                links.append(
                    {"page": term_record.source, "id": edit.key, "text": term_record.text.strip()}
                )
            elif edit.kind == "citeref":
                if "prodockit.citations" not in extensions:
                    raise _error(page, edit.start, "citation syntax requires prodockit.citations")
                keys = [key.strip() for key in edit.key.split(",") if key.strip()]
                if not keys:
                    raise _error(page, edit.start, "give the citation at least one key")
                anchors = []
                for key in keys:
                    record = citations.get(key)
                    if record is None:
                        raise _error(page, edit.start, f"unresolved citation key {key!r}")
                    href = html.escape(cross_page_href(record.source, source, key), quote=True)
                    anchors.append(
                        f'<a class="prodockit-cite-resolved" href="{href}">'
                        f"{html.escape(record.text)}</a>"
                    )
                    links.append({"page": record.source, "id": key, "text": record.text.strip()})
                edit.value = '<span class="prodockit-cite">[' + "; ".join(anchors) + "]</span>"
            elif edit.kind == "hotspots":
                fences = config.markdown_extensions.get("pymdownx.superfences", {}).get(
                    "custom_fences", []
                )
                if not any(
                    f.get("format") == "prodockit.image_hotspots.format_hotspots" for f in fences
                ):
                    raise _error(page, edit.start, "image-hotspots formatter must be configured")
                try:
                    edit.value = render_hotspots(edit.value, source, inputs.docs_dir) + "\n"
                except (ValueError, yaml.YAMLError) as error:
                    raise _error(page, edit.start, str(error)) from error
            elif edit.kind == "bibliography":
                edit.value = cache.bibliography_html(
                    edit.key, "site-cited" if edit.cited else "all"
                )
            elif edit.kind == "cite" and not local_bibliographies:
                formatted, resolved = cache.resolve_citation(edit.key)
                if not resolved:
                    raise _error(page, edit.start, f"unresolved citation {edit.key!r}")
                destinations = [
                    (file, target)
                    for file, target in cache.first_page_for_file.items()
                    if BeautifulSoup(cache.bibliography_html(file, "all"), "html.parser").find(
                        id=f"ref-{edit.key}"
                    )
                ]
                if not destinations:
                    raise _error(
                        page, edit.start, f"citation {edit.key!r} has no bibliography destination"
                    )
                target = destinations[0][1]
                href = cross_page_href(target, source, f"ref-{edit.key}")
                edit.value = (
                    f'<span class="prodockit-bib-cite"><a href="{html.escape(href, quote=True)}">'
                    f"{formatted}</a></span>"
                )
                links.append(
                    {
                        "page": target,
                        "id": f"ref-{edit.key}",
                        "text": BeautifulSoup(formatted, "html.parser").get_text(" ", strip=True),
                    }
                )
        output, source_map = apply_edits(page.original, page.edits, projection=page.projection)
        outputs[source] = output
        details[source] = {
            "targets": page.targets, "links": links, "source_map": source_map,
            "numbering": {
                "start_count": contexts[source].start_count,
                "appendix_letter": contexts[source].appendix_letter,
            },
        }
        if page.caption_targets:
            details[source]["captions"] = page.caption_targets
    return outputs, details, dependencies
