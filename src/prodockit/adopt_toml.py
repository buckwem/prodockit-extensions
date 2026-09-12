# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Comment-preserving Adopt configuration editing through TOML Kit."""

import sys
from collections.abc import Mapping, MutableMapping
from typing import TYPE_CHECKING, Any, cast

import tomlkit
from tomlkit.items import Item

if TYPE_CHECKING:
    from prodockit.adopt import AdoptOptions

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def inline(value: Any) -> Item:
    if isinstance(value, Mapping):
        result = tomlkit.inline_table()
        for key, child in value.items():
            result[str(key)] = inline(child)
        return result
    if isinstance(value, (list, tuple)):
        array = tomlkit.array()
        for child in value:
            array.append(inline(child))
        return array
    return cast(Item, tomlkit.item(value))


def update(source: str, options: "AdoptOptions") -> str:
    from prodockit._zensical_defaults import DOCUMENTED_MARKDOWN_DEFAULTS
    from prodockit.adopt import (
        TREE_ICON_EXTENSION,
        TREE_ICON_SETTINGS,
        AdoptError,
        _asset_reference,
        _extra_defaults_missing,
        _missing_caption_types,
        _missing_core_extensions,
    )

    tomllib.loads(source)
    document = tomlkit.parse(source)
    project: Any = document["project"]
    if "markdown_extensions" not in project:
        project["markdown_extensions"] = tomlkit.table()
        for name, settings in DOCUMENTED_MARKDOWN_DEFAULTS.items():
            table = tomlkit.table()
            for key, value in settings.items():
                table[key] = inline(value)
            project["markdown_extensions"][name] = table
    extensions = project["markdown_extensions"]

    def extension(name: str) -> Any:
        if isinstance(extensions, list):
            for index, entry in enumerate(extensions):
                if isinstance(entry, str) and entry == name:
                    extensions[index] = inline({name: {}})
                    return extensions[index][name]
                if isinstance(entry, Mapping) and name in entry:
                    return entry[name]
            extensions.append(inline({name: {}}))
            return extensions[-1][name]
        if not isinstance(extensions, MutableMapping):
            raise AdoptError("markdown_extensions must be a table or list")
        if name in extensions:
            return extensions[name]
        nested = extensions
        for part in name.split("."):
            if not isinstance(nested, Mapping) or part not in nested:
                break
            nested = nested[part]
        else:
            return nested
        extensions[name] = tomlkit.table()
        return extensions[name]

    parsed = tomllib.loads(tomlkit.dumps(document))
    for name in _missing_core_extensions(parsed):
        extension(name)
    icons = extension(TREE_ICON_EXTENSION)
    for key, value in TREE_ICON_SETTINGS.items():
        if key not in icons:
            icons[key] = value
    captions = _missing_caption_types(parsed)
    if captions:
        caption = extension("pymdownx.blocks.caption")
        if "types" not in caption:
            caption["types"] = tomlkit.array()
        for value in captions:
            caption["types"].append(inline(value))
    if "extra" not in project:
        project["extra"] = tomlkit.table()
    extra = project["extra"]
    if not isinstance(extra, MutableMapping):
        raise AdoptError("project.extra must be a table")
    for key, value in _extra_defaults_missing(parsed).items():
        extra[key] = value

    def asset(table: Any, key: str, expected: str, *, first: bool = False) -> None:
        if key not in table:
            table[key] = tomlkit.array().multiline(True)
        values = table[key]
        if not isinstance(values, list):
            raise AdoptError(f"{key} must be an array")
        if any(_asset_reference(item) == expected for item in values):
            return
        if first:
            values.insert(0, expected)
        else:
            values.append(expected)

    asset(project, "extra_css", "stylesheets/pdk.css", first=True)
    asset(project, "extra_css", "stylesheets/extra.css")
    asset(extra, "pdf_extra_css", "stylesheets/pdk-pdf.css", first=True)
    asset(extra, "pdf_extra_css", "stylesheets/print.css")
    if options.mermaid:
        fences = extension("pymdownx.superfences")
        if "custom_fences" not in fences:
            fences["custom_fences"] = tomlkit.array()
        if not any(
            isinstance(item, Mapping) and item.get("name") == "mermaid"
            for item in fences["custom_fences"]
        ):
            fences["custom_fences"].append(
                inline(
                    {
                        "name": "mermaid",
                        "class": "mermaid",
                        "format": "pymdownx.superfences.fence_code_format",
                    }
                )
            )
    if options.maths:
        extension("pymdownx.arithmatex")["generic"] = True
        asset(project, "extra_javascript", "javascripts/vendor/mathjax/tex-svg-full.js", first=True)
        asset(project, "extra_javascript", "javascripts/mathjax.js", first=True)
    asset(project, "extra_javascript", "javascripts/pdk.js", first=True)
    asset(project, "extra_javascript", "javascripts/extra.js")
    output = tomlkit.dumps(document)
    tomllib.loads(output)
    return output
