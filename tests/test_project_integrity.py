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


def test_every_nav_page_must_exist(tmp_path: Path) -> None:
    config = _project(tmp_path, 'nav = [{"Missing" = "missing.md"}]\n')

    assert _messages(config) == ["project.nav: page does not exist: docs/missing.md"]


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


def test_csl_style_must_exist(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        '[project.markdown_extensions."prodockit.bibliography"]\n'
        'csl_style = "styles/house.csl"\n',
    )

    assert any("styles/house.csl" in message for message in _messages(config))


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


def test_configured_mermaid_is_optional_until_a_diagram_uses_it(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("PATH", "")
    config = _project(
        tmp_path,
        "[project.markdown_extensions.pymdownx.superfences]\n"
        'custom_fences = [{name = "mermaid"}]\n',
        {
            "index.md": (
                "# No diagrams\n\n"
                "````markdown\n"
                "```mermaid\n"
                "graph LR\n  A --> B\n"
                "```\n"
                "````\n"
            )
        },
    )

    assert not any("mmdc renderer" in message for message in _messages(config))

    (tmp_path / "docs" / "index.md").write_text(
        "# Diagram\n\n```mermaid\ngraph LR\n  A --> B\n```\n", encoding="utf-8"
    )
    assert any("mmdc renderer" in message for message in _messages(config))


def test_mermaid_renderer_must_run_not_merely_exist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "")
    config = _project(
        tmp_path,
        '[project.extra]\npdf_mmdc_bin = "tools/mermaid/mmdc"\n'
        "[project.markdown_extensions.pymdownx.superfences]\n"
        'custom_fences = [{name = "mermaid"}]\n',
        {"index.md": "```mermaid\ngraph LR\n  A --> B\n```\n"},
    )
    binary = tmp_path / "tools" / "mermaid" / "mmdc"
    binary.parent.mkdir(parents=True)
    binary.write_text("incomplete", encoding="utf-8")
    monkeypatch.setattr(
        "prodockit.project_integrity.probe_mermaid",
        lambda path: SimpleNamespace(path=path, ok=False, error="ERR_MODULE_NOT_FOUND"),
    )

    assert any("cannot run: ERR_MODULE_NOT_FOUND" in message for message in _messages(config))


def test_configured_maths_is_optional_until_notation_uses_it(tmp_path: Path) -> None:
    config = _project(
        tmp_path,
        "[project.markdown_extensions.pymdownx.arithmatex]\n",
        {"index.md": "The price is $5 and the example is `\\(x\\)`.\n"},
    )

    assert not any("tex2svg renderer" in message for message in _messages(config))

    (tmp_path / "docs" / "index.md").write_text("The area is $a^2$.\n", encoding="utf-8")
    assert any("tex2svg renderer" in message for message in _messages(config))


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
