# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from prodockit.wordcount import compute_word_count, count_words


def test_count_words_counts_plain_prose() -> None:
    assert count_words("one two three") == 3


def test_count_words_strips_fenced_code_blocks_of_any_language() -> None:
    text = "before\n```mermaid\ngraph TD\nA --> B\n```\nafter"
    assert count_words(text) == 2


def test_count_words_strips_html_tags_and_comments() -> None:
    text = "<!-- a hidden comment --><p>real text</p>"
    assert count_words(text) == 2


def test_count_words_strips_markdown_image_and_keeps_link_text() -> None:
    text = "![alt text](image.png) see [the docs](https://example.com/) here"
    assert count_words(text) == 4


def test_compute_word_count_sums_across_texts() -> None:
    assert compute_word_count(["one two", "three four five"]) == 5


def test_compute_word_count_of_an_empty_list_is_zero() -> None:
    assert compute_word_count([]) == 0
