# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Original locations remain useful through selective edits and newline conversion."""

from __future__ import annotations

import pytest

from prodockit.portable import PortableError
from prodockit.portable.compiler import Edit
from prodockit.portable.source_map import (
    SourceText,
    apply_edits,
    original_location,
    validate_source_map,
)


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_complete_map_preserves_unicode_positions_and_copied_text(newline: str) -> None:
    original = f"Café 🌻 {newline}before TOKEN after NEXT.{newline}tail{newline}"
    source = SourceText.read(original)
    token, second = source.text.index("TOKEN"), source.text.index("NEXT")
    generated, mapping = apply_edits(source, [
        Edit(token, token + 5, "reference", "<a>expanded\nreference</a>"),
        Edit(second, second + 4, "reference", "<a>next</a>"),
    ])
    assert generated == "Café 🌻 \nbefore <a>expanded\nreference</a> after <a>next</a>.\ntail\n"
    assert [span["kind"] for span in mapping] == ["copy", "reference", "copy", "reference", "copy"]
    assert mapping[1]["source_start"] == {"offset": original.index("TOKEN"), "line": 2, "column": 8}
    assert mapping[-1]["source_end"]["offset"] == len(original)
    assert mapping[-1]["generated_end"]["offset"] == len(generated)
    assert original_location(mapping, 3, 1) == (2, 8)  # Expanded reference.
    assert original_location(mapping, 3, 16) == (2, 15)  # Copied word 'after'.
    assert original_location(mapping, 4, 3) == (3, 3)  # Unchanged trailing text.
    assert original_location(mapping, 5, 1) == (4, 1)  # End-of-file.
    validate_source_map(original, generated, mapping)


def test_no_edits_still_has_complete_map() -> None:
    generated, mapping = apply_edits(SourceText.read("ordinary\r\nMarkdown"), [])
    assert generated == "ordinary\nMarkdown"
    assert len(mapping) == 1 and mapping[0]["kind"] == "copy"
    assert original_location(mapping, 2, 4) == (2, 4)
    validate_source_map("ordinary\r\nMarkdown", generated, mapping)
    assert apply_edits(SourceText.read(""), []) == ("", [])
    assert original_location([], 1, 1) == (1, 1)


def test_source_map_rejects_wrong_copy_and_missing_coverage() -> None:
    generated, mapping = apply_edits(SourceText.read("original\n"), [])
    with pytest.raises(PortableError, match="copied text"):
        validate_source_map("original\n", "modified\n", mapping)
    with pytest.raises(PortableError, match="complete document"):
        validate_source_map("original\n", generated, [])
    with pytest.raises(PortableError, match="outside"):
        original_location(mapping, 3)
