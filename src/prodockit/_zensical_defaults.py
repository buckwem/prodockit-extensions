# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Prodockit-owned representation of Zensical's documented Markdown defaults.

Adoption must materialise these defaults before adding an explicit extension
configuration, because an explicit table replaces Zensical's implicit set.
Importing ``zensical.config.DEFAULT_MARKDOWN_EXTENSIONS`` tied that file edit
to an undocumented Python constant.  This serializable copy follows the
public list at https://zensical.org/docs/setup/extensions/about/ and is
covered by adoption build acceptance tests.
"""

from __future__ import annotations

from typing import Any

DOCUMENTED_MARKDOWN_DEFAULTS: dict[str, dict[str, Any]] = {
    "abbr": {},
    "admonition": {},
    "attr_list": {},
    "def_list": {},
    "footnotes": {},
    "md_in_html": {},
    "toc": {"permalink": True},
    "pymdownx.arithmatex": {"generic": True},
    "pymdownx.betterem": {},
    "pymdownx.caret": {},
    "pymdownx.details": {},
    "pymdownx.emoji": {
        "emoji_generator": "zensical.extensions.emoji.to_svg",
        "emoji_index": "zensical.extensions.emoji.twemoji",
    },
    "pymdownx.highlight": {
        "anchor_linenums": True,
        "line_spans": "__span",
        "pygments_lang_class": True,
    },
    "pymdownx.inlinehilite": {},
    "pymdownx.keys": {},
    "pymdownx.magiclink": {},
    "pymdownx.mark": {},
    "pymdownx.smartsymbols": {},
    "pymdownx.superfences": {
        "custom_fences": [{"name": "mermaid", "class": "mermaid"}],
    },
    "pymdownx.tabbed": {"alternate_style": True, "combine_header_slug": True},
    "pymdownx.tasklist": {"custom_checkbox": True},
    "pymdownx.tilde": {},
}
