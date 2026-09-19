# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from prodockit.project_config import load_project_config
from prodockit.project_integrity import (
    assert_project_integrity,
    inspect_project,
    renderer_requirements,
)


def _project(tmp_path: Path, body: str, pages: dict[str, str] | None = None) -> Path:
    config = tmp_path / "zensical.toml"
    config.write_text('[project]\nsite_name = "Example"\n' + body, encoding="utf-8")
    for name, content in (pages or {}).items():
        path = tmp_path / "docs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return config


def _messages(config: Path) -> list[str]:
    return [
        f"{problem.path}: {problem.message}"
        for problem in inspect_project(load_project_config(config))
    ]


def test_missing_local_css_and_javascript_are_reported_but_urls_are_allowed(
    tmp_path: Path,
) -> None:
    config = _project(
        tmp_path,
        'extra_css = ["styles/site.css", "https://cdn.example/site.css"]\n'
        'extra_javascript = ["scripts/site.js", "//cdn.example/site.js"]\n',
    )

    messages = _messages(config)

    assert any("styles/site.css" in message for message in messages)
    assert any("scripts/site.js" in message for message in messages)
    assert not any("cdn.example" in message for message in messages)


def test_pdf_only_stylesheet_is_checked(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        '[project.extra]\npdf_extra_css = ["styles/print.css"]\n',
    )

    assert any("styles/print.css" in message for message in _messages(config))


def test_local_stylesheets_and_javascript_must_be_configured(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        'extra_css = ["stylesheets/configured.css"]\n'
        'extra_javascript = ["javascripts/configured.js"]\n'
        "[project.extra]\n"
        'pdf_extra_css = ["stylesheets/print.css"]\n',
    )
    assets = {
        "stylesheets/configured.css": "",
        "stylesheets/print.css": "",
        "stylesheets/missing-from-config.css": "",
        "javascripts/configured.js": "",
        "javascripts/missing-from-config.js": "",
    }
    for name, content in assets.items():
        path = tmp_path / "docs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    messages = _messages(config)

    assert any(
        "docs/stylesheets/missing-from-config.css" in message
        and "project.extra_css or pdk-pdf.toml [document].extra_css" in message
        for message in messages
    )
    assert any(
        "docs/javascripts/missing-from-config.js" in message
        and "project.extra_javascript" in message
        for message in messages
    )
    assert not any("configured.css" in message for message in messages)
    assert not any("configured.js" in message for message in messages)
    assert not any("print.css" in message for message in messages)


def test_nested_javascript_and_cache_key_references_are_matched(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        'extra_javascript = ["javascripts/vendor/tool.js?v=2"]\n',
    )
    script = tmp_path / "docs/javascripts/vendor/tool.js"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")

    assert _messages(config) == []


def test_every_nav_page_must_exist(tmp_path: Path) -> None:
    config = _project(tmp_path, 'nav = [{"Missing" = "missing.md"}]\n')

    assert _messages(config) == ["project.nav: page does not exist: docs/missing.md"]


def test_invalid_utf8_markdown_is_reported_as_a_project_problem(tmp_path: Path) -> None:
    config = _project(tmp_path, "")
    invalid = tmp_path / "docs" / "invalid-utf8.md"
    invalid.parent.mkdir()
    invalid.write_bytes(b"\x89PNG\r\n\x1a\n")

    expected_path = str(Path("docs") / "invalid-utf8.md")
    assert _messages(config) == [
        f"{expected_path}:1:1: invalid UTF-8 byte sequence"
    ]
    assert renderer_requirements(load_project_config(config)) == (False, False)


def test_nav_urls_and_page_fragments_do_not_create_false_missing_pages(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        'nav = [{"Home" = "index.md#start"}, {"External" = "https://example.test"}]\n',
        {"index.md": "# Start"},
    )

    assert _messages(config) == []


def test_local_markdown_images_exist_after_query_and_theme_fragment_are_removed(
    tmp_path: Path,
) -> None:
    config = _project(
        tmp_path,
        "",
        {
            "index.md": (
                "![Inline](assets/exists.png#only-light)\n"
                "![Reference][figure]\n"
                "![Shortcut][]\n"
                "[figure]: assets/missing.png?raw=1\n"
                "[shortcut]: assets/exists.png#only-dark\n"
                '<img src="/assets/also-missing.svg#only-dark">\n'
                "![Remote](https://example.test/remote.png)\n"
                "```md\n![Example only](assets/example.png)\n```\n"
            ),
            "assets/exists.png": "not a real png, but an existing input",
        },
    )

    messages = _messages(config)

    assert any("assets/missing.png?raw=1" in message for message in messages)
    assert any("/assets/also-missing.svg#only-dark" in message for message in messages)
    assert not any("exists.png" in message for message in messages)
    assert not any("remote.png" in message for message in messages)
    assert not any("example.png" in message for message in messages)


def test_local_markdown_image_paths_may_contain_balanced_parentheses(
    tmp_path: Path,
) -> None:
    config = _project(
        tmp_path,
        "",
        {
            "index.md": "![Parenthesised](assets/foo(bar).svg)\n",
            "assets/foo(bar).svg": "<svg></svg>\n",
        },
    )

    assert _messages(config) == []


def test_missing_parenthesised_image_reports_the_complete_destination(
    tmp_path: Path,
) -> None:
    config = _project(
        tmp_path,
        "",
        {"index.md": "![Parenthesised](assets/foo(bar).svg)\n"},
    )

    assert _messages(config) == [
        "docs/index.md: image does not exist: assets/foo(bar).svg"
    ]


def test_csl_style_must_exist(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        '[project.markdown_extensions."prodockit.bibliography"]\ncsl_style = "styles/house.csl"\n',
    )

    assert any("styles/house.csl" in message for message in _messages(config))


def test_bibliography_file_must_exist(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        '[project.markdown_extensions."prodockit.bibliography"]\nbib_file = "references.bib"\n',
    )

    assert _messages(config) == [
        'project.markdown_extensions."prodockit.bibliography".bib_file: '
        "file does not exist: references.bib"
    ]

    (tmp_path / "references.bib").write_text("", encoding="utf-8")
    assert _messages(config) == []


@pytest.mark.parametrize(
    ("source", "extension"),
    [
        ("See \\ref{figure-one}.", "prodockit.refs"),
        ("See \\citeref{source-one}.", "prodockit.citations"),
        ("Use \\gls{api}.", "prodockit.glossary"),
        ("Use \\cite{book}.", "prodockit.bibliography"),
        ("Mark \\index{Term}.", "prodockit.index"),
        ("/// steps\n", "prodockit.steps"),
        ("/// tree\n", "prodockit.tree"),
    ],
)
def test_prodockit_syntax_requires_its_extension(
    tmp_path: Path, source: str, extension: str
) -> None:
    config = _project(tmp_path, "", {"index.md": source})

    assert any(extension in message for message in _messages(config))


def test_example_syntax_in_code_does_not_require_an_extension(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        "",
        {"index.md": "Use `\\ref{id}` or:\n```md\n/// steps\n\\index{Term}\n```\n"},
    )

    assert _messages(config) == []


@pytest.mark.parametrize(
    "source",
    [
        "# Page\n\n    Example reference: \\ref{target}.\n",
        "# Page\n\n\tExample reference: \\ref{target}.\n",
        "# Page\n\n>     Example reference: \\ref{target}.\n",
        "# Page\n\n- Item\n\n        Example reference: \\ref{target}.\n",
    ],
)
def test_example_syntax_in_indented_code_does_not_require_an_extension(
    tmp_path: Path, source: str
) -> None:
    config = _project(tmp_path, "", {"index.md": source})

    assert _messages(config) == []


def test_active_syntax_in_an_indented_list_paragraph_still_requires_extension(
    tmp_path: Path,
) -> None:
    config = _project(
        tmp_path,
        "",
        {"index.md": "# Page\n\n- Item\n\n    Active reference: \\ref{target}.\n"},
    )

    assert any("prodockit.refs" in message for message in _messages(config))


@pytest.mark.parametrize(
    "syntax",
    [
        r"\ref{target}",
        r"\autoref{target}",
        r"\citeref{source}",
        r"\gls{api}",
        r"\cite{book}",
        r"\index{Term}",
        "/// steps\n",
        "/// tree\n",
    ],
)
@pytest.mark.parametrize("multiline", [False, True])
def test_commented_syntax_is_not_active(tmp_path: Path, syntax: str, multiline: bool) -> None:
    gap = "\n" if multiline else " "
    config = _project(tmp_path, "", {"index.md": f"# Page\n<!--{gap}{syntax}{gap}-->\n"})
    assert _messages(config) == []


def test_active_syntax_after_a_comment_still_requires_extension(tmp_path: Path) -> None:
    config = _project(tmp_path, "", {"index.md": "<!-- \\gls{hidden} -->\nSee \\ref{visible}."})
    messages = _messages(config)
    assert any("prodockit.refs" in message for message in messages)
    assert not any("prodockit.glossary" in message for message in messages)


def test_project_integrity_leaves_mermaid_cache_preparation_to_pdf(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        "[project.markdown_extensions.pymdownx.superfences]\n"
        'custom_fences = [{name = "mermaid"}]\n',
        {
            "index.md": (
                "# No diagrams\n\n````markdown\n```mermaid\ngraph LR\n  A --> B\n```\n````\n"
            )
        },
    )

    (tmp_path / "docs" / "index.md").write_text(
        "# Diagram\n\n```mermaid\ngraph LR\n  A --> B\n```\n", encoding="utf-8"
    )
    assert not any("renderer.mermaid" in message for message in _messages(config))


@pytest.mark.parametrize(
    "example",
    [
        "<!--\n```mermaid\ngraph LR\n  A --- B\n```\n-->",
        "````markdown\n```mermaid\ngraph LR\n  A --> B\n```\n````",
        "` ```mermaid ` is an example, not a diagram.",
    ],
)
def test_quoted_or_commented_mermaid_fence_does_not_require_a_renderer(
    tmp_path: Path, monkeypatch, example: str
) -> None:
    monkeypatch.setenv("PATH", "")
    config = _project(
        tmp_path,
        "[project.markdown_extensions.pymdownx.superfences]\n"
        'custom_fences = [{name = "mermaid"}]\n',
        {"index.md": f"# Examples\n\n{example}\n"},
    )

    assert not any("Python renderer is unavailable" in message for message in _messages(config))


def test_real_mermaid_fence_is_not_a_static_integrity_problem(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        "[project.markdown_extensions.pymdownx.superfences]\n"
        'custom_fences = [{name = "mermaid"}]\n',
        {
            "index.md": (
                "<!-- ```mermaid is an example -->\n"
                "The literal opening marker `<!--` is also an example.\n\n"
                "```mermaid\ngraph LR\n  A --> B\n```\n"
            )
        },
    )

    assert not any("renderer.mermaid" in message for message in _messages(config))


def test_standard_mathjax_cache_is_not_a_static_integrity_problem(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        "[project.markdown_extensions.pymdownx.arithmatex]\n",
        {"index.md": "The price is $5 and the example is `\\(x\\)`.\n"},
    )

    (tmp_path / "docs" / "index.md").write_text("The area is $a^2$.\n", encoding="utf-8")
    assert not any("tex2svg renderer" in message for message in _messages(config))


@pytest.mark.parametrize(
    "example",
    [
        "<!-- $$x^2$$ -->",
        "<!--\n$$\nx^2\n$$\n-->",
        "`$$x^2$$`",
        "`` Example: `$$x^2$$` ``",
        "```markdown\n$$\nx^2\n$$\n```",
        "~~~text\n$$x^2$$\n~~~",
        "    Example: $$x^2$$",
        "\tExample: $$x^2$$",
        r"\$\$x^2\$\$",
    ],
)
def test_quoted_or_commented_display_maths_does_not_require_a_renderer(
    tmp_path: Path, example: str
) -> None:
    config = _project(
        tmp_path,
        "[project.markdown_extensions.pymdownx.arithmatex]\n",
        {"index.md": f"# Examples\n\n{example}\n"},
    )

    assert not any("tex2svg renderer" in message for message in _messages(config))


def test_real_display_maths_uses_the_lazy_standard_renderer(
    tmp_path: Path,
) -> None:
    config = _project(
        tmp_path,
        "[project.markdown_extensions.pymdownx.arithmatex]\n",
        {"index.md": "<!-- $$hidden$$ -->\n`$$example$$`\n\n$$\nx^2\n$$\n"},
    )

    assert not any("tex2svg renderer" in message for message in _messages(config))


def test_mathjax_renderer_must_run_not_merely_exist(tmp_path: Path, monkeypatch) -> None:
    config = _project(
        tmp_path,
        '[project.extra]\npdf_tex2svg_script = "tools/mathjax/tex2svg.js"\n'
        "[project.markdown_extensions.pymdownx.arithmatex]\n",
        {"index.md": "The area is $a^2$.\n"},
    )
    script = tmp_path / "tools" / "mathjax" / "tex2svg.js"
    script.parent.mkdir(parents=True)
    script.write_text("renderer", encoding="utf-8")
    monkeypatch.setattr("prodockit.project_integrity.shutil.which", lambda _name: "node")
    monkeypatch.setattr(
        "prodockit.project_integrity.probe_mathjax",
        lambda node, path: SimpleNamespace(path=path, ok=False, error="Cannot find module"),
    )

    assert any("cannot run: Cannot find module" in message for message in _messages(config))


def test_complete_project_passes_and_testing_assertion_is_reusable(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        'nav = [{"Home" = "index.md"}]\n'
        'extra_css = ["styles/site.css"]\n'
        '[project.markdown_extensions."prodockit.refs"]\n',
        {
            "index.md": "![Diagram](assets/diagram.png#only-light) See \\ref{diagram}.",
            "assets/diagram.png": "placeholder",
            "styles/site.css": "body {}",
        },
    )

    assert_project_integrity(config)


def test_testing_assertion_lists_all_problems(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        'nav = [{"Missing" = "missing.md"}]\nextra_css = ["missing.css"]\n',
    )

    with pytest.raises(AssertionError, match="project integrity problems") as caught:
        assert_project_integrity(config)

    assert "missing.md" in str(caught.value)
    assert "missing.css" in str(caught.value)
