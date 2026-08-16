# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""``prodockit.steps`` - numbered steps a reader works through in order.

A procedure is not a list of facts. Each step is a thing to stop and do,
and the layout should say so: a number to find your place by, room to put
a command and its explanation, and a line joining one step to the next.

Written on pymdownx's Blocks API - the machinery Material's own
admonitions and tabs use - so it reads as Markdown rather than as
embedded HTML::

    /// steps
        start: 9

    //// step | Load the key into the agent
    ```bash
    ssh-add --apple-use-keychain ~/.ssh/id_ed25519_gitlab
    ```
    ////

    //// step | Upload the public key
    Paste it into your host's SSH keys page.
    ////

    ///

``start`` is the one option, and it exists because a long procedure is
often split across sections: the second half continues at 9 rather than
beginning again at 1. ``attrs`` works as it does on every other block -
the Blocks API reserves it - so a style or an id can be put on the list
without this extension knowing anything about either.

**The starting number is written twice in the HTML, deliberately.** An
``<ol start="9">`` is what a browser reads; WeasyPrint ignores it
entirely and numbers from 1, so the PDF disagreed with the website while
both looked right on their own. ``counter-reset: list-item 8`` is what
WeasyPrint reads. Emitting both from one ``start: 9`` is the whole reason
this is an extension rather than a documented HTML snippet: an author who
maintains the pair by hand will one day change one of them, and the
failure is silent and PDF-only.

The stylesheet is the project's own - the same arrangement
``prodockit.tables`` has - and `docs/devcons/steps.md` carries a copy to
start from, including the two traps that make it worth copying rather
than writing from scratch.
"""

from __future__ import annotations

import xml.etree.ElementTree as etree
from typing import Any, ClassVar

from pymdownx.blocks import BlocksExtension
from pymdownx.blocks.block import Block, type_number

#: The list, and the title inside each item. Named rather than styled
#: here: prodockit ships the structure, a project ships the look.
STEPS_CLASS = "prodockit-steps"
STEP_TITLE_CLASS = "prodockit-step-title"


class StepsBlock(Block):  # type: ignore[misc]
    """``/// steps`` - the list the steps live in."""

    NAME = "steps"
    ARGUMENT = None
    OPTIONS: ClassVar[dict[str, list[Any]]] = {"start": [1, type_number]}

    def on_create(self, parent: etree.Element) -> etree.Element:
        ordered = etree.SubElement(parent, "ol")
        ordered.set("class", STEPS_CLASS)
        return ordered

    def on_end(self, block: etree.Element) -> None:
        """Both spellings of the starting number, set after `attrs`.

        After, because `attrs` may carry a `style` of its own and this
        has to join it rather than replace it - a reader who writes
        `attrs: {style: 'font-size: 1.2em'}` alongside `start: 9` should
        get both, not whichever the code happened to set last.
        """
        start = int(self.options["start"])
        if start == 1:
            return
        block.set("start", str(start))
        counter = f"counter-reset: list-item {start - 1}"
        existing = block.get("style", "").strip()
        block.set("style", f"{counter}; {existing}" if existing else counter)


class StepBlock(Block):  # type: ignore[misc]
    """``//// step | Title`` - one step, with everything it needs."""

    NAME = "step"
    ARGUMENT = None  # optional: a step without a title is still a step
    OPTIONS: ClassVar[dict[str, list[Any]]] = {}

    def on_create(self, parent: etree.Element) -> etree.Element:
        return etree.SubElement(parent, "li")

    def on_add(self, block: etree.Element) -> etree.Element:
        return block

    def on_markdown(self) -> str:
        """Block, so a step's body becomes paragraphs.

        Inline content runs a step's prose, its command and its
        explanation together into one line, which reads worse than the
        plain numbered list this replaces.
        """
        return "block"

    def on_end(self, block: etree.Element) -> None:
        """The title, put in front of whatever the body turned into.

        A `<p>` of its own rather than bold text, so it can be styled
        apart from other emphasis, collected, or given an id later.
        """
        if not self.argument:
            return
        title = etree.Element("p")
        title.set("class", STEP_TITLE_CLASS)
        title.text = self.argument
        block.insert(0, title)


class StepsExtension(BlocksExtension):  # type: ignore[misc]
    """Registers both blocks; neither is useful without the other."""

    def extendMarkdownBlocks(self, md: object, block_mgr: object) -> None:
        block_mgr.register(StepsBlock, self.getConfigs())  # type: ignore[attr-defined]
        block_mgr.register(StepBlock, self.getConfigs())  # type: ignore[attr-defined]


def makeExtension(**kwargs: object) -> StepsExtension:
    return StepsExtension(**kwargs)
