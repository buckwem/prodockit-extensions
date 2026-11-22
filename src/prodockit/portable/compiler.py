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
import xml.etree.ElementTree as ET
from collections.abc import Collection
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

import markdown
import yaml
from bs4 import BeautifulSoup
from markdown.extensions.attr_list import get_attrs_and_remainder

from prodockit.bibliography import _BibliographyCache
from prodockit.image_hotspots import _render as render_hotspots
from prodockit.portable import PortableError
from prodockit.portable.inputs import MaterializedInputs
from prodockit.portable.source_map import SourceText, apply_edits
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

_COMMAND = re.compile(
    r"\\(?P<name>autoref|ref|cite|gls)\{(?P<key>[^{}\s,]+)\}"
    r"|\\(?P<manual>citeref)\{(?P<keys>[^{}\n]+)\}"
    r"|\\(?P<bib>bibliography)(?!\w)(?:\{(?P<file>[^{}]*)\})?"
    r"(?:\{(?P<cited>true|false)\})?"
)
_UNSUPPORTED = re.compile(
    r"\\(?:pagebibliography|citeref|gls|cite|ref|autoref|bibliography)\b"
    r"|\{[{%]|--8<--|^\s*(?:!!!|\?\?\?|===|///)",
    re.MULTILINE,
)
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


@dataclass
class Edit:
    start: int
    end: int
    kind: str
    value: str
    key: str = ""
    cited: bool = False


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
    edits: list[Edit] = field(default_factory=list)
    headings: list[tuple[int, int, str]] = field(default_factory=list)
    targets: list[dict[str, Any]] = field(default_factory=list)
    definitions: list[Definition] = field(default_factory=list)


def _error(page: Page, offset: int, message: str) -> PortableError:
    line = page.text.count("\n", 0, offset) + 1
    return PortableError(f"{page.source}:{line}: {message}")


def _tokenizer() -> Any:
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
                "kind": match.group("name") or match.group("manual") or "bibliography",
                "key": match.group("key") or match.group("keys") or match.group("file") or "",
                "cited": match.group("cited") == "true",
                "in_link": state.linkLevel > 0,
            }
        state.pos = match.end()
        return True

    parser = MarkdownIt("commonmark")
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


def scan(source: str, text: str, *, extensions: Collection[str] = ()) -> Page:
    """Retain original spans, protecting code with the tokenizer's own rules."""
    original = SourceText.read(text)
    text = original.text
    lines = text.splitlines(keepends=True)
    body_start = 0
    meta: dict[str, Any] = {}
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() in {"---", "..."}), None)
        if end is None:
            raise PortableError(f"{source}: unclosed front matter")
        value = yaml.safe_load("".join(lines[1:end]))
        if value is not None and not isinstance(value, dict):
            raise PortableError(f"{source}: front matter must be a mapping")
        meta = value or {}
        body_start = sum(map(len, lines[: end + 1]))
    page = Page(source, text, meta, original)
    active_attributes = {
        name for name, extension in DEFINITION_EXTENSIONS.items() if extension in extensions
    }
    if meta.get("template") or meta.get("render_macros"):
        raise _error(page, 0, "generated page content is outside the portable prototype")
    body = text[body_start:]
    offsets = [body_start]
    for line in body.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    tokens = _tokenizer().parse(body)
    for index, token in enumerate(tokens):
        if token.map is None:
            continue
        start, end = (offsets[n] for n in token.map)
        if token.type == "fence" and token.info.strip() == "image-hotspots":
            if token.level != 0:
                raise _error(page, start, "nested hotspots are outside the portable prototype")
            page.edits.append(Edit(start, end, "hotspots", token.content))
        elif token.type == "html_block" and (
            _UNSUPPORTED.search(token.content)
            or active_attributes.intersection(_DEFINITION_ASSIGNMENT.findall(token.content))
        ):
            raise _error(page, start, "affected syntax in HTML is outside the portable prototype")
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
            top_level = token.level == 1 and tokens[index - 1].type == "paragraph_open"
            raw = text[start:end]
            if active_attributes and any(
                child.type == "text" and any(name in child.content for name in active_attributes)
                for child in children
            ):
                _definitions(page, start, raw, token.content, top_level, active_attributes)
            commands = [child.meta for child in children if child.type == "pdk_command"]
            if not commands:
                continue
            if not top_level:
                raise _error(
                    page, start, "affected syntax in nested content is outside the prototype"
                )
            at = raw.find(token.content)
            if at < 0 or raw.strip() != token.content:
                raise _error(page, start, "cannot map the affected content to an exact source span")
            for item in commands:
                if item["in_link"]:
                    raise _error(page, start, "references inside links are outside the prototype")
                a, b = start + at + item["start"], start + at + item["end"]
                if item["kind"] == "bibliography" and text[a:b] != token.content:
                    raise _error(page, a, "put the bibliography marker alone in its paragraph")
                page.edits.append(Edit(a, b, item["kind"], "", item["key"], item["cited"]))
    return page


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


def _heading_records(
    page: Page, headings: list[ET.Element], context: PageContext, registry: IdRegistry,
) -> None:
    collector = PageCollector(context, registry)
    for (start, end, line), heading in zip(page.headings, headings, strict=True):
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


def compile_pages(
    config: ProjectConfig,
    sources: dict[str, str],
    *,
    inputs: MaterializedInputs,
    pandoc: Path | None = None,
) -> tuple[dict[str, str], dict[str, Any], set[Path]]:
    """Compile the supported slice with explicit ownership and two passes."""
    if "prodockit.tables" in config.markdown_extensions:
        for source, text in sources.items():
            try:
                validate_table_attributes(
                    SourceText.read(text).text.split("\n"),
                    partial("{}:{}".format, source),
                )
            except TableError as error:
                raise PortableError(str(error)) from error
    extensions = config.markdown_extensions.keys()
    pages = {
        source: scan(source, text, extensions=extensions) for source, text in sources.items()
    }
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
    bib_used = any(e.kind in {"cite", "bibliography"} for p in pages.values() for e in p.edits)
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
                if edit.kind == "bibliography":
                    edit.key = dependency(edit.key) if edit.key else default_bib
                    if edit.key not in cache.all_bib_files:
                        cache.all_bib_files.append(edit.key)
                    cache.first_page_for_file.setdefault(edit.key, source)
                elif edit.kind == "cite":
                    cache.all_cited_keys.add(edit.key)

    outputs: dict[str, str] = {}
    details: dict[str, Any] = {}
    for source in order:
        page = pages[source]
        links: list[dict[str, str]] = []
        for edit in page.edits:
            if edit.kind in {"ref", "autoref"}:
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
            elif edit.kind == "cite":
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
        output, source_map = apply_edits(page.original, page.edits)
        outputs[source] = output
        details[source] = {
            "targets": page.targets, "links": links, "source_map": source_map,
            "numbering": {
                "start_count": contexts[source].start_count,
                "appendix_letter": contexts[source].appendix_letter,
            },
        }
    return outputs, details, dependencies
