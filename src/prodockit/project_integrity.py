# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Source-project integrity checks shared by the CLI and pytest support."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from prodockit.project_config import ProjectConfig, load_project_config


@dataclass(frozen=True)
class ProjectProblem:
    """One source input or integration that will otherwise fail silently."""

    path: str
    message: str


_INLINE_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(\s*(?:<(?P<angle>[^>]+)>|(?P<plain>[^\s)]+))"
)
_REFERENCE_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\[([^\]]*)\]")
_REFERENCE_DEFINITION_RE = re.compile(
    r"^\s*\[([^\]]+)\]:\s*(?:<([^>]+)>|([^\s]+))", re.MULTILINE
)
_INLINE_CODE_RE = re.compile(r"(`+)(.*?)\1")
_ARITHMATEX_RE = re.compile(
    r"(?:"
    r"(?<!\\)\$\$(?:\\.|[^\\])+?\$\$"
    r"|(?<!\\)\$(?!\s)(?:\\.|[^\\$\x02\x03])+?(?<!\s)\$"
    r"|(?<!\\)\\\((?:\\[^)]|[^\\\x02\x03])+?\\\)"
    r"|(?<!\\)\\\[(?:\\[^]]|[^\\])+?\\\]"
    r"|\\begin\{(?P<env>[a-z]+\*?)\}(?:\\.|[^\\])+?\\end\{(?P=env)\}"
    r")",
    re.DOTALL | re.IGNORECASE,
)

_SYNTAX_REQUIREMENTS = (
    (re.compile(r"\\(?:ref|autoref)\{"), "prodockit.refs", "reference"),
    (re.compile(r"\\citeref\{"), "prodockit.citations", "citation reference"),
    (re.compile(r"\\gls\{"), "prodockit.glossary", "glossary reference"),
    (
        re.compile(r"\\(?:cite\{|bibliography(?:\{|\s*$))", re.MULTILINE),
        "prodockit.bibliography",
        "bibliography",
    ),
    (re.compile(r"\\index\{"), "prodockit.index", "index term"),
    (re.compile(r"^\s*///+\s+steps(?:\s|$)", re.MULTILINE), "prodockit.steps", "steps block"),
    (re.compile(r"^\s*///+\s+tree(?:\s|$)", re.MULTILINE), "prodockit.tree", "tree block"),
)


class _ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        values = dict(attrs)
        if values.get("src"):
            self.sources.append(str(values["src"]))


def _without_fenced_code(source: str) -> str:
    """Blank fenced code, preserving line numbers and ordinary directives."""
    lines: list[str] = []
    fence_char = ""
    fence_length = 0
    for line in source.splitlines(keepends=True):
        marker = re.match(r"^\s*([`~]{3,})", line)
        if fence_char:
            lines.append("\n" if line.endswith("\n") else "")
            if marker and marker.group(1)[0] == fence_char and len(marker.group(1)) >= fence_length:
                fence_char = ""
                fence_length = 0
            continue
        if marker:
            fence_char = marker.group(1)[0]
            fence_length = len(marker.group(1))
            lines.append("\n" if line.endswith("\n") else "")
            continue
        lines.append(line)
    return "".join(lines)


def _scannable_markdown(source: str) -> str:
    return _INLINE_CODE_RE.sub("", _without_fenced_code(source))


def _uses_mermaid(source: str) -> bool:
    """Return whether a real Markdown fence selects the Mermaid renderer."""
    fence_char = ""
    fence_length = 0
    for line in source.splitlines():
        marker = re.match(r"^\s*([`~]{3,})(.*)$", line)
        if fence_char:
            if (
                marker
                and marker.group(1)[0] == fence_char
                and len(marker.group(1)) >= fence_length
                and not marker.group(2).strip()
            ):
                fence_char = ""
                fence_length = 0
            continue
        if not marker:
            continue
        fence_char = marker.group(1)[0]
        fence_length = len(marker.group(1))
        info = marker.group(2).strip()
        if re.match(r"^mermaid(?:\s|$)", info, flags=re.IGNORECASE):
            return True
    return False


def _uses_maths(source: str) -> bool:
    """Return whether prose contains notation handled by Arithmatex."""
    return bool(_ARITHMATEX_RE.search(_scannable_markdown(source)))


def _is_remote(value: str) -> bool:
    stripped = value.strip()
    if stripped.startswith("//"):
        return True
    scheme = urlsplit(stripped).scheme.lower()
    return bool(scheme and scheme not in {"file"})


def _local_target(
    config: ProjectConfig, value: str, *, markdown: Path | None = None
) -> Path | None:
    value = value.strip().strip("<>")
    if not value or value.startswith("#") or _is_remote(value):
        return None
    path_text = unquote(urlsplit(value).path)
    if not path_text:
        return None
    if path_text.startswith("/"):
        return config.docs_dir / path_text.lstrip("/")
    base = markdown.parent if markdown is not None else config.docs_dir
    return base / path_text


def _display(config: ProjectConfig, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(config.root))
    except ValueError:
        return str(path)


def _configured_local_files(config: ProjectConfig) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for key in ("extra_css", "extra_javascript"):
        values = config.project.get(key) or []
        if isinstance(values, str):
            values = [values]
        if isinstance(values, list):
            found.extend((f"project.{key}", value) for value in values if isinstance(value, str))
    values = config.extra.get("pdf_extra_css") or []
    if isinstance(values, str):
        values = [values]
    if isinstance(values, list):
        found.extend(
            ("project.extra.pdf_extra_css", value)
            for value in values
            if isinstance(value, str)
        )
    return found


def _markdown_image_sources(source: str) -> list[str]:
    clean = _scannable_markdown(source)
    references = {
        match.group(1).strip().casefold(): (match.group(2) or match.group(3))
        for match in _REFERENCE_DEFINITION_RE.finditer(clean)
    }
    found = [
        match.group("angle") or match.group("plain")
        for match in _INLINE_IMAGE_RE.finditer(clean)
    ]
    for match in _REFERENCE_IMAGE_RE.finditer(clean):
        key = (match.group(2).strip() or match.group(1).strip()).casefold()
        if key and key in references:
            found.append(references[key])
    parser = _ImageParser()
    parser.feed(clean)
    found.extend(parser.sources)
    return found


def _tool_path(root: Path, configured: object, defaults: tuple[str, ...]) -> Path | None:
    if configured:
        candidate = Path(str(configured))
        candidate = candidate if candidate.is_absolute() else root / candidate
        return candidate if candidate.is_file() else None
    for default in defaults:
        candidate = root / default
        for spelling in (candidate, Path(f"{candidate}.cmd"), Path(f"{candidate}.exe")):
            if spelling.is_file():
                return spelling
    return None


def _mermaid_configured(config: ProjectConfig) -> bool:
    options = config.markdown_extensions.get("pymdownx.superfences", {})
    fences = options.get("custom_fences") or []
    return isinstance(fences, list) and any(
        isinstance(fence, dict) and fence.get("name") == "mermaid" for fence in fences
    )


def _renderer_requirements_from_sources(
    config: ProjectConfig, sources: list[str]
) -> tuple[bool, bool]:
    """Return which optional PDF renderers the project's content needs."""
    mermaid = _mermaid_configured(config) and any(_uses_mermaid(source) for source in sources)
    maths = "pymdownx.arithmatex" in config.markdown_extensions and any(
        _uses_maths(source) for source in sources
    )
    return mermaid, maths


def renderer_requirements(config: ProjectConfig) -> tuple[bool, bool]:
    """Return Mermaid/MathJax requirements without treating defaults as use."""
    sources: list[str] = []
    if config.docs_dir.is_dir():
        for markdown in sorted(config.docs_dir.rglob("*.md")):
            try:
                sources.append(markdown.read_text(encoding="utf-8"))
            except OSError:
                continue
    return _renderer_requirements_from_sources(config, sources)


def inspect_project(config: ProjectConfig) -> tuple[ProjectProblem, ...]:
    """Return missing inputs and integrations for a configured project."""
    problems: list[ProjectProblem] = []

    for setting, value in _configured_local_files(config):
        target = _local_target(config, value)
        if target is not None and not target.is_file():
            problems.append(
                ProjectProblem(
                    setting,
                    f"local file does not exist: {_display(config, target)}",
                )
            )

    for page in config.nav_pages:
        target = _local_target(config, page.source_path)
        if target is not None and not target.is_file():
            problems.append(
                ProjectProblem(
                    "project.nav",
                    f"page does not exist: {_display(config, target)}",
                )
            )

    markdown_files = sorted(config.docs_dir.rglob("*.md")) if config.docs_dir.is_dir() else []
    markdown_sources: list[str] = []
    enabled = set(config.markdown_extensions)
    for markdown in markdown_files:
        try:
            source = markdown.read_text(encoding="utf-8")
        except OSError as error:
            problems.append(
                ProjectProblem(_display(config, markdown), f"cannot read page: {error}")
            )
            continue
        markdown_sources.append(source)
        for image in _markdown_image_sources(source):
            target = _local_target(config, image, markdown=markdown)
            if target is not None and not target.is_file():
                problems.append(
                    ProjectProblem(
                        _display(config, markdown),
                        f"image does not exist: {image}",
                    )
                )
        clean = _scannable_markdown(source)
        for pattern, extension, syntax in _SYNTAX_REQUIREMENTS:
            if extension not in enabled and pattern.search(clean):
                problems.append(
                    ProjectProblem(
                        _display(config, markdown),
                        f"uses {syntax} syntax but {extension} is not enabled",
                    )
                )

    bibliography = config.markdown_extensions.get("prodockit.bibliography", {})
    if bibliography.get("csl_style"):
        style = Path(str(bibliography["csl_style"]))
        style = style if style.is_absolute() else config.root / style
        if not style.is_file():
            problems.append(
                ProjectProblem(
                    'project.markdown_extensions."prodockit.bibliography".csl_style',
                    f"file does not exist: {_display(config, style)}",
                )
            )

    mermaid_required, maths_required = _renderer_requirements_from_sources(
        config, markdown_sources
    )
    if mermaid_required:
        configured = config.extra.get("pdf_mmdc_bin")
        found = _tool_path(
            config.root,
            configured,
            ("tools/mermaid/node_modules/.bin/mmdc", "node_modules/.bin/mmdc"),
        )
        if found is None and not (configured is None and shutil.which("mmdc")):
            problems.append(
                ProjectProblem(
                    "project.extra.pdf_mmdc_bin",
                    "Mermaid diagrams are used but the mmdc renderer is not installed",
                )
            )

    if maths_required:
        configured = config.extra.get("pdf_tex2svg_script")
        if _tool_path(config.root, configured, ("tools/mathjax/tex2svg.js",)) is None:
            problems.append(
                ProjectProblem(
                    "project.extra.pdf_tex2svg_script",
                    "maths is used but its MathJax tex2svg renderer is not installed",
                )
            )

    return tuple(sorted(set(problems), key=lambda problem: (problem.path, problem.message)))


def find_project_problems(config_file: str | Path = "zensical.toml") -> tuple[ProjectProblem, ...]:
    """Convenience entry point used by project tests."""
    return inspect_project(load_project_config(config_file))


def assert_project_integrity(config_file: str | Path = "zensical.toml") -> None:
    """Fail one project test with all missing inputs and integrations."""
    problems = find_project_problems(config_file)
    if problems:
        details = "\n".join(f"- {problem.path}: {problem.message}" for problem in problems)
        raise AssertionError(f"Prodockit project integrity problems:\n{details}")
