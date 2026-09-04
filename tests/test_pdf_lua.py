# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import shutil
import subprocess

import pytest

from prodockit.pdf.lua import build_lua_filter


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


def test_math_dir_and_tex2svg_script_paths_with_a_quote_are_escaped() -> None:
    """Regression test: math_dir/tex2svg_script used to be interpolated
    into the Lua string literal with no escaping at all - a path
    containing a literal `"` produced syntactically broken Lua, only
    discoverable at real `pandoc` runtime."""
    lua = build_lua_filter(True, True, '/some/weird"dir', '/some/tex2svg"script.js')
    assert 'local math_dir = "/some/weird\\"dir"' in lua
    assert 'local tex2svg_script = "/some/tex2svg\\"script.js"' in lua


def test_math_dir_and_tex2svg_script_paths_with_a_backslash_are_escaped() -> None:
    """Same as the quote-escaping regression above, for an unescaped
    backslash (e.g. a Windows-style path passed through as-is)."""
    lua = build_lua_filter(True, True, "C:\\math", "C:\\tex2svg.js")
    assert 'local math_dir = "C:\\\\math"' in lua
    assert 'local tex2svg_script = "C:\\\\tex2svg.js"' in lua


def test_every_expected_lua_filter_function_is_present() -> None:
    lua = build_lua_filter(True, True, "/tmp/math", "/tmp/tex2svg.js")
    for fn in (
        "function CodeBlock(",
        "function Div(",
        "function Span(",
        "function Figure(",
        "function Header(",
        "function Math(",
        "function Pandoc(",
    ):
        assert fn in lua


def test_header_handler_prefixes_appendix_letters_not_numbers() -> None:
    lua = build_lua_filter(True, False, "/tmp/math", "/tmp/tex2svg.js")
    assert "block.classes:includes('appendix')" in lua
    assert "'Appendix ' .. to_letter(appendix_index)" in lua


def test_code_block_handler_restores_carried_highlight_markup() -> None:
    lua = build_lua_filter(True, False, "/tmp/math", "/tmp/tex2svg.js")

    assert "local function decode_hex(value)" in lua
    assert "el.attributes['prodockit-highlight']" in lua
    assert "pandoc.RawBlock('html'" in lua
    assert 'class="highlight prodockit-highlight"' in lua


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc is not installed")
def test_real_pandoc_restores_highlight_markup(tmp_path) -> None:
    markup = '<span class="k">[project]</span>\n<span class="n">release</span>'
    encoded = markup.encode("utf-8").hex()
    source = (
        f'<pre><code data-prodockit-highlight="{encoded}">'
        '[project]\nrelease</code></pre>'
    )
    lua_filter = tmp_path / "filter.lua"
    lua_filter.write_text(
        build_lua_filter(False, False, str(tmp_path), str(tmp_path / "tex2svg.js")),
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["pandoc", "-f", "html", "-t", "html", f"--lua-filter={lua_filter}"],
        input=source,
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )

    assert '<div class="highlight prodockit-highlight"><pre><code>' in completed.stdout
    assert markup in completed.stdout
    assert "prodockit-highlight=" not in completed.stdout
