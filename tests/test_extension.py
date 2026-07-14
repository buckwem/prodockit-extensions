# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import markdown

from zendoc import ZendocExtension, __version__


def test_version_is_set() -> None:
    assert __version__


def test_extension_registers_via_class() -> None:
    md = markdown.Markdown(extensions=[ZendocExtension()])
    assert md.convert("hello") == "<p>hello</p>"


def test_extension_registers_via_entry_point_name() -> None:
    md = markdown.Markdown(extensions=["zendoc"])
    assert md.convert("hello") == "<p>hello</p>"
