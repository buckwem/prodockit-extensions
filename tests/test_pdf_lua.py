# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from zendoc.pdf.lua import build_lua_filter


def test_heading_numbering_flag_is_substituted_as_a_lua_boolean() -> None:
    enabled = build_lua_filter(True, False, "/tmp/math", "/tmp/tex2svg.js")
    disabled = build_lua_filter(False, False, "/tmp/math", "/tmp/tex2svg.js")
    assert "local heading_numbering_enabled = true" in enabled
    assert "local heading_numbering_enabled = false" in disabled


def test_mathjax_availability_flag_is_substituted_as_a_lua_boolean() -> None:
    available = build_lua_filter(True, True, "/tmp/math", "/tmp/tex2svg.js")
    unavailable = build_lua_filter(True, False, "/tmp/math", "/tmp/tex2svg.js")
    assert "local mathjax_available = true" in available
    assert "local mathjax_available = false" in unavailable


def test_math_dir_and_tex2svg_script_paths_are_embedded_literally() -> None:
    lua = build_lua_filter(True, True, "/some/math/dir", "/some/tex2svg.js")
    assert 'local math_dir = "/some/math/dir"' in lua
    assert 'local tex2svg_script = "/some/tex2svg.js"' in lua


def test_every_expected_lua_filter_function_is_present() -> None:
    lua = build_lua_filter(True, True, "/tmp/math", "/tmp/tex2svg.js")
    for fn in ("function Div(", "function Span(", "function Figure(", "function Header(", "function Math(", "function Pandoc("):
        assert fn in lua


def test_header_handler_prefixes_appendix_letters_not_numbers() -> None:
    lua = build_lua_filter(True, False, "/tmp/math", "/tmp/tex2svg.js")
    assert "block.classes:includes('appendix')" in lua
    assert "'Appendix ' .. to_letter(appendix_index)" in lua
