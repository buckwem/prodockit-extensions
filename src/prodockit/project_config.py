# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Prodockit-owned reading of the project settings Prodockit consumes.

This is intentionally not a replacement for Zensical's configuration engine.
Zensical still builds the website. Prodockit's public PDF path, pre-scan and
testing features read the source configuration files directly so they do not
import ``zensical.config`` or depend on its normalized private data structures.
The old renderer remains separately available through the hidden legacy
command.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped, unused-ignore]

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by Python 3.10 CI
    import tomli as tomllib


class ProjectConfigError(ValueError):
    """A project configuration cannot be read without guessing."""


CONFIG_FILENAMES = (
    "zensical.toml",
    "zensical.yml",
    "zensical.yaml",
    "mkdocs.yml",
    "mkdocs.yaml",
)


@dataclass(frozen=True)
class NavPage:
    """One real Markdown page in depth-first navigation order."""

    title: str
    source_path: str
    is_index: bool


@dataclass(frozen=True)
class ProjectConfig:
    """The subset of project configuration consumed by Prodockit."""

    path: Path
    project: dict[str, Any]
    nav_pages: tuple[NavPage, ...]
    markdown_extensions: dict[str, dict[str, Any]]

    @property
    def root(self) -> Path:
        return self.path.parent

    @property
    def docs_dir(self) -> Path:
        return _project_path(self.root, self.project.get("docs_dir") or "docs")

    @property
    def site_dir(self) -> Path:
        return _project_path(self.root, self.project.get("site_dir") or "site")

    @property
    def site_name(self) -> str:
        return str(self.project.get("site_name") or "")

    @property
    def extra(self) -> dict[str, Any]:
        value = self.project.get("extra") or {}
        return dict(value) if isinstance(value, Mapping) else {}

    def as_resolved_mapping(self) -> dict[str, Any]:
        """Return the normalized compatibility shape Prodockit exposes.

        This is Prodockit's model, not a promise to reproduce every field in
        Zensical's private resolved configuration.
        """
        resolved = dict(self.project)
        resolved["docs_dir"] = str(self.docs_dir)
        resolved["site_dir"] = str(self.site_dir)
        resolved["nav"] = [
            {
                "title": page.title,
                "url": page.source_path,
                "is_index": page.is_index,
                "children": [],
            }
            for page in self.nav_pages
        ]
        resolved["mdx_configs"] = self.markdown_extensions
        return resolved


class _ConfigLoader(yaml.SafeLoader):  # type: ignore[misc, unused-ignore]
    """Read common MkDocs callable tags as names without importing them."""


def _python_name(_loader: _ConfigLoader, suffix: str, _node: yaml.Node) -> str:
    return suffix


def _python_object(loader: _ConfigLoader, suffix: str, node: yaml.Node) -> Any:
    value: Any
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node)
    else:  # pragma: no cover - PyYAML nodes are one of the three above
        value = None
    return {"callable": suffix, "arguments": value}


_ConfigLoader.add_multi_constructor("tag:yaml.org,2002:python/name:", _python_name)
_ConfigLoader.add_multi_constructor("tag:yaml.org,2002:python/object/apply:", _python_object)


def _project_path(root: Path, configured: object) -> Path:
    path = Path(str(configured))
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _markdown_extensions(value: object) -> dict[str, dict[str, Any]]:
    extensions: dict[str, dict[str, Any]] = {}
    if isinstance(value, Mapping):
        for name, options in value.items():
            extensions[str(name)] = dict(options) if isinstance(options, Mapping) else {}
        return extensions
    if value is None:
        return extensions
    if not isinstance(value, list):
        raise ProjectConfigError("markdown_extensions must be a mapping or list")
    for item in value:
        if isinstance(item, str):
            extensions[item] = {}
        elif isinstance(item, Mapping):
            for name, options in item.items():
                extensions[str(name)] = dict(options) if isinstance(options, Mapping) else {}
        else:
            raise ProjectConfigError(f"unsupported Markdown extension entry: {item!r}")
    return extensions


def _nav_pages(value: object) -> tuple[NavPage, ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list):
        raise ProjectConfigError("navigation must be a list")
    pages: list[NavPage] = []
    for item in value:
        if isinstance(item, str):
            pages.append(NavPage(Path(item).stem, item, Path(item).name == "index.md"))
            continue
        if not isinstance(item, Mapping):
            raise ProjectConfigError(f"unsupported navigation entry: {item!r}")
        if "url" in item:
            url = item.get("url")
            if url:
                source = str(url)
                pages.append(
                    NavPage(
                        str(item.get("title") or Path(source).stem),
                        source,
                        bool(item.get("is_index", Path(source).name == "index.md")),
                    )
                )
            children = item.get("children") or []
            pages.extend(_nav_pages(children))
            continue
        for title, destination in item.items():
            if isinstance(destination, str):
                pages.append(NavPage(str(title), destination, Path(destination).name == "index.md"))
            elif isinstance(destination, list):
                pages.extend(_nav_pages(destination))
            else:
                raise ProjectConfigError(
                    f"unsupported navigation destination for {title!r}: {destination!r}"
                )
    return tuple(pages)


def load_project_config(path: str | Path = "zensical.toml") -> ProjectConfig:
    """Read a Zensical TOML or MkDocs/Zensical YAML project file directly."""
    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise ProjectConfigError(f"project configuration not found: {config_path}")
    try:
        source = config_path.read_text(encoding="utf-8")
        if config_path.suffix.lower() == ".toml":
            raw = tomllib.loads(source)
            project_value = raw.get("project")
            if not isinstance(project_value, Mapping):
                raise ProjectConfigError(f"{config_path} has no [project] table")
            project = dict(project_value)
        else:
            loaded = yaml.load(source, Loader=_ConfigLoader)
            if not isinstance(loaded, Mapping):
                raise ProjectConfigError(f"{config_path} does not contain a configuration mapping")
            project = dict(loaded)
    except (OSError, tomllib.TOMLDecodeError, yaml.YAMLError) as error:
        raise ProjectConfigError(f"could not read {config_path}: {error}") from error

    return ProjectConfig(
        path=config_path,
        project=project,
        nav_pages=_nav_pages(project.get("nav")),
        markdown_extensions=_markdown_extensions(project.get("markdown_extensions")),
    )


def find_project_config(root: str | Path = ".") -> Path | None:
    """Return the first conventional project config below ``root``."""
    directory = Path(root).resolve()
    return next(
        (candidate for name in CONFIG_FILENAMES if (candidate := directory / name).is_file()),
        None,
    )
