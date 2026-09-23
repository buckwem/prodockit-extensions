# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from prodockit.pdf.build import Page, build_pdf
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
    source = f'<pre><code data-prodockit-highlight="{encoded}">[project]\nrelease</code></pre>'
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


@pytest.mark.skipif(
    shutil.which("pandoc") is None or shutil.which("node") is None,
    reason="Pandoc and Node.js are required",
)
def test_real_pandoc_renders_generic_display_maths(tmp_path) -> None:
    adapter = tmp_path / "tex2svg.cjs"
    adapter.write_text(
        "process.stdin.resume(); process.stdin.on('end', () => "
        'process.stdout.write(\'<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 10 10"><text>equation</text></svg>\'));',
        encoding="utf-8",
    )
    lua_filter = tmp_path / "filter.lua"
    lua_filter.write_text(
        build_lua_filter(False, True, str(tmp_path), str(adapter)),
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["pandoc", "-f", "html", "-t", "html", f"--lua-filter={lua_filter}"],
        input='<div class="arithmatex">\\[x^2\\]</div>',
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )

    assert 'class="pdf-math-display"' in completed.stdout
    assert "equation" in (tmp_path / "formula_1.svg").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_mathjax_adapter_emits_xml_safe_svg(tmp_path) -> None:
    runtime = tmp_path / "MathJax"
    runtime.mkdir()
    (runtime / "tex-svg.js").write_text(
        "MathJax.startup.promise = Promise.resolve();\n"
        "MathJax.startup.adaptor = {outerHTML: () => "
        '\'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">\' + '
        '\'<path data-semantic-speech="<mark name=&quot;1&quot;/>" d="M0 0L10 10"/>\' + '
        "'</svg>'};\n"
        "MathJax.tex2svgPromise = async () => ({});\n"
        "MathJax.done = () => {};\n",
        encoding="utf-8",
    )
    adapter = Path(__file__).parents[1] / "src/prodockit/pdf/tex2svg.cjs"
    completed = subprocess.run(
        ["node", str(adapter), str(runtime), "display"],
        input="x^2",
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )

    svg = ET.fromstring(completed.stdout)
    assert svg.find("{http://www.w3.org/2000/svg}path").attrib["data-semantic-speech"] == (
        '<mark name="1"/>'
    )


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc is required")
def test_failed_math_render_is_not_silent(tmp_path) -> None:
    adapter = tmp_path / "broken.cjs"
    adapter.write_text("process.stderr.write('broken adapter'); process.exit(2);", encoding="utf-8")
    lua_filter = tmp_path / "filter.lua"
    lua_filter.write_text(
        build_lua_filter(False, True, str(tmp_path), str(adapter)), encoding="utf-8"
    )
    completed = subprocess.run(
        ["pandoc", "-f", "html", "-t", "html", f"--lua-filter={lua_filter}"],
        input='<div class="arithmatex">\\[x^2\\]</div>',
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode != 0
    assert "MathJax display rendering failed" in completed.stderr


@pytest.mark.skipif(
    shutil.which("pandoc") is None or shutil.which("node") is None,
    reason="Pandoc and Node.js are required",
)
def test_real_mathjax_renders_template_display_equation(tmp_path) -> None:
    runtime = os.environ.get("PDK_TEST_MATHJAX_RUNTIME")
    if not runtime:
        pytest.skip("Set PDK_TEST_MATHJAX_RUNTIME to a prepared MathJax runtime")
    adapter = Path(__file__).parents[1] / "src/prodockit/pdf/tex2svg.cjs"
    lua_filter = tmp_path / "filter.lua"
    lua_filter.write_text(
        build_lua_filter(False, True, str(tmp_path), str(adapter), runtime),
        encoding="utf-8",
    )

    source = (
        '<div class="arithmatex">\\[\n'
        r"\cos x=\sum_{k=0}^{\infty}\frac{(-1)^k}{(2k)!}x^{2k}"
        "\n\\]</div>"
    )
    completed = subprocess.run(
        ["pandoc", "-f", "html", "-t", "html", f"--lua-filter={lua_filter}"],
        input=source,
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )

    assert 'class="pdf-math-display"' in completed.stdout
    ET.fromstring((tmp_path / "formula_1.svg").read_text(encoding="utf-8"))


@pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("pandoc", "node", "weasyprint")),
    reason="Pandoc, Node.js and WeasyPrint are required",
)
def test_pdf_build_renders_template_display_equation(tmp_path) -> None:
    """The SVG must be visible in the PDF, not just generated on disk."""
    pymupdf = pytest.importorskip("pymupdf")
    runtime = os.environ.get("PDK_TEST_MATHJAX_RUNTIME")
    if not runtime:
        fake_runtime = tmp_path / "MathJax"
        fake_runtime.mkdir()
        (fake_runtime / "tex-svg.js").write_text(
            "MathJax.startup.promise = Promise.resolve();\n"
            "MathJax.startup.adaptor = {outerHTML: () => "
            '\'<svg xmlns="http://www.w3.org/2000/svg" '
            'width="120" height="30" viewBox="0 0 120 30">\' + '
            '\'<path data-semantic-speech="<mark name=&quot;1&quot;/>" '
            'd="M0 0L120 30" stroke="black"/>\' + \'</svg>\'};\n'
            "MathJax.tex2svgPromise = async () => ({});\n"
            "MathJax.done = () => {};\n",
            encoding="utf-8",
        )
        runtime = str(fake_runtime)
    adapter = Path(__file__).parents[1] / "src/prodockit/pdf/tex2svg.cjs"
    source = (
        '<h1>Examples</h1><h2>Maths</h2><div class="arithmatex">\\[\n'
        r"\cos x=\sum_{k=0}^{\infty}\frac{(-1)^k}{(2k)!}x^{2k}"
        "\n\\]</div><p>Below the equation.</p>"
    )
    output = tmp_path / "out.pdf"
    build_pdf(
        [Page(docs_rel_path="examples.md", html=source)],
        str(output),
        mathjax_available=True,
        tex2svg_script=str(adapter),
        mathjax_runtime=runtime,
        work_dir=str(tmp_path / "work"),
        keep_work_dir=True,
        include_table_of_contents=False,
        weasyprint_executable=shutil.which("weasyprint") or "weasyprint",
    )
    assert output.is_file()
    svg_files = list((tmp_path / "work").glob("formula_*.svg"))
    assert len(svg_files) == 1
    ET.fromstring(svg_files[0].read_text(encoding="utf-8"))
    with pymupdf.open(output) as pdf:
        page = pdf[0]
        words = page.get_text("words")
        heading_bottom = max(word[3] for word in words if word[4] == "Maths")
        paragraph_top = min(word[1] for word in words if word[4] == "Below")
        assert any(
            heading_bottom < drawing["rect"].y0 < paragraph_top for drawing in page.get_drawings()
        ), "display equation is absent from the rendered PDF"
