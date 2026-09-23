# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Source checks for Jinja controls inside Markdown pipe tables."""

from __future__ import annotations

import markdown
import pytest
from jinja2 import Environment

from prodockit.table_jinja import untrimmed_table_controls


@pytest.mark.parametrize("variable", ["is_surrey", "show_extra"])
def test_untrimmed_nested_branches_are_reported(variable: str) -> None:
    source = (
        "| Name | Value |\n| --- | --- |\n| First | One |\n"
        f"{{% if {variable} %}}\n| Second | Two |\n"
        "{% if nested %}\n| Third | Three |\n{% endif %}\n"
        "{% elif other %}\n| Fourth | Four |\n"
        "{% else %}\n| Fifth | Five |\n{% endif %}\n"
        "| Last | Six |\n"
    )
    assert untrimmed_table_controls(source) == (4, 6, 8, 9, 11, 13)
    assert untrimmed_table_controls(source.replace("%}", "-%}")) == ()


@pytest.mark.parametrize("value", [False, True])
def test_trimmed_control_preserves_rendered_table(value: bool) -> None:
    source = (
        "| Name | Value |\n| --- | --- |\n| First | One |\n"
        "{% if is_surrey -%}\n| Second | Two |\n{% endif -%}\n"
        "| Last | Three |\n"
    )
    rendered = Environment().from_string(source).render(is_surrey=value)
    html = markdown.markdown(rendered, extensions=["tables"])
    assert html.count("<table>") == 1
    assert html.count("<tr>") == (4 if value else 3)
    assert "| Last |" not in html


@pytest.mark.parametrize("value", [False, True])
def test_untrimmed_control_can_break_rendered_table(value: bool) -> None:
    source = (
        "| Name | Value |\n| --- | --- |\n| First | One |\n"
        "{% if is_surrey %}\n| Second | Two |\n{% endif %}\n"
        "| Last | Three |\n"
    )
    rendered = Environment().from_string(source).render(is_surrey=value)
    html = markdown.markdown(rendered, extensions=["tables"])
    assert "| Last |" in html
    assert untrimmed_table_controls(source) == (4, 6)


def test_examples_and_non_table_conditionals_are_ignored() -> None:
    source = (
        "```markdown\n| A | B |\n|---|---|\n{% if x %}\n| 1 | 2 |\n```\n"
        "~~~\n| A | B |\n|---|---|\n{% endif %}\n| 1 | 2 |\n~~~\n"
        "    | A | B |\n    |---|---|\n    {% if x %}\n"
        "> | A | B |\n> |---|---|\n> {% if x %}\n"
        "<!--\n| A | B |\n|---|---|\n{% if x %}\n| 1 | 2 |\n-->\n"
        "{% raw %}\n| A | B |\n|---|---|\n{% if x %}\n| 1 | 2 |\n{% endraw %}\n"
        "Here is prose | with pipes | but not a table.\n{% if x %}\n"
        "/// tab | Example\n{% if x %}\n///\n"
        "{% if x %}\nA section, not a table.\n{% endif %}\n"
        "| `A | B` | C |\n|---|---|\n| x | y |\n"
    )
    assert untrimmed_table_controls(source) == ()


def test_html_comment_does_not_hide_following_table() -> None:
    source = (
        "<!-- explanation\n    with indented text\n-->\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n{% if x %}\n| 3 | 4 |\n"
    )
    assert untrimmed_table_controls(source) == (7,)


def test_leading_trim_alone_is_not_enough() -> None:
    source = "| A | B |\n|---|---|\n| 1 | 2 |\n{%- if x %}\n| 3 | 4 |\n"
    assert untrimmed_table_controls(source) == (4,)


def test_untrimmed_endif_before_caption_is_reported() -> None:
    source = (
        "| A | B |\n|---|---|\n| 1 | 2 |\n"
        "{% if x -%}\n| 3 | 4 |\n{% endif %}\n"
        "/// table-caption\nExample\n///\n"
    )
    assert untrimmed_table_controls(source) == (6,)


def test_single_column_pipe_table_is_checked() -> None:
    source = "| A |\n|---|\n| 1 |\n{% if x %}\n| 2 |\n"
    assert untrimmed_table_controls(source) == (4,)
