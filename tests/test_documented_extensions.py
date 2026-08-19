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

import pathlib

from prodockit.template_sync import read_config

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "installation.md"


def registered_extensions() -> list[str]:
    """Every name under the `markdown.extensions` entry point group."""
    config = read_config((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    group = config["project"]["entry-points"]["markdown.extensions"]
    return sorted(group)


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
