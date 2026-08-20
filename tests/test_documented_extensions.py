# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Every registered extension is listed on the installation page.

The page that tells a reader how to enable an extension listed four of
them while nine were registered - `tables`, `tree`, `steps`,
`bibliography` and `index` had each been added with its own page and its
own entry point, and none of them reached the one page a new reader goes
to first. Nothing failed: the list was simply never revisited, and a
reader had no way to know it was short.

That is the shape of failure this project keeps meeting - output that is
wrong rather than absent - so it is asserted rather than remembered. The
entry points in `pyproject.toml` are the authority: an extension exists
because it is registered, and anything registered has to be findable.
"""

from __future__ import annotations

import importlib
import pathlib

from markdown.extensions import Extension

from prodockit.template_sync import read_config

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "installation.md"
DOCSTRING = ROOT / "src" / "prodockit" / "__init__.py"


def registered_extensions() -> list[str]:
    """Every name under the `markdown.extensions` entry point group."""
    config = read_config((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    group = config["project"]["entry-points"]["markdown.extensions"]
    return sorted(group)


def registered_extension_targets() -> dict[str, str]:
    """Every extension name and its importable ``module:class`` target."""
    config = read_config((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return dict(config["project"]["entry-points"]["markdown.extensions"])


def extension_from_target(target: str) -> Extension:
    """Construct an extension directly from its package entry-point target."""
    module_name, class_name = target.split(":", 1)
    extension_class = getattr(importlib.import_module(module_name), class_name)
    extension = extension_class()
    assert isinstance(extension, Extension)
    return extension


def test_every_registered_extension_is_on_the_installation_page() -> None:
    page = PAGE.read_text(encoding="utf-8")
    missing = [name for name in registered_extensions() if name not in page]

    assert not missing, (
        "These are registered as Python-Markdown extensions but do not appear on "
        f"{PAGE.relative_to(ROOT)}, so a reader enabling extensions never learns "
        f"they exist: {missing}"
    )


def test_every_registered_extension_has_a_page_to_link_to() -> None:
    """A name on the list is only useful if it goes somewhere."""
    pages = {p.stem for p in (ROOT / "docs" / "extensions").glob("*.md")}
    # `prodockit.index` documents itself under a longer name, because
    # "index.md" is a site's front page everywhere else.
    known = {"prodockit.index": "index-terms"}

    missing = [
        name
        for name in registered_extensions()
        if known.get(name, name.removeprefix("prodockit.")) not in pages
    ]

    assert not missing, f"registered with no page under docs/extensions/: {missing}"


def test_every_zensical_extension_setting_is_on_its_reference_page() -> None:
    """Keep author-facing TOML settings in step with extension source code."""
    known = {"prodockit.index": "index-terms"}
    missing: dict[str, list[str]] = {}

    for name, target in registered_extension_targets().items():
        page_name = known.get(name, name.removeprefix("prodockit."))
        page = ROOT / "docs" / "extensions" / f"{page_name}.md"
        text = page.read_text(encoding="utf-8")
        extension = extension_from_target(target)
        undocumented = [key for key in extension.getConfigs() if f"`{key}`" not in text]
        if undocumented:
            missing[name] = undocumented

    assert not missing, (
        "These Python-Markdown configuration keys can be set under their "
        "extension's zensical.toml table but are absent from its Authoring "
        f"Reference page: {missing}"
    )


def test_every_registered_extension_is_in_the_package_docstring() -> None:
    """`prodockit/__init__.py` is what `help(prodockit)` and PyPI show.

    It listed eight of the nine - `prodockit.tree` was missing - which is
    the same drift as the installation page, in the other place a reader
    looks.
    """
    text = DOCSTRING.read_text(encoding="utf-8")
    missing = [name for name in registered_extensions() if name not in text]

    assert not missing, f"registered but absent from the package docstring: {missing}"
