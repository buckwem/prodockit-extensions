# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Guards against a real bug found by checking the live site: this
project's own docs (docs/**/*.md) accidentally showing a prodockit
extension's own backslash-command syntax as literal example text using
inline backticks, when the syntax in question (a code-styled
`\\index{`Term`}`) isn't actually protected by inline backticks the way
a plain `\\index{Term}`/`\\ref{id}`/`\\cite{id}`/`\\gls{id}` is - see
prodockit.index's own module docstring, and tests/test_index.py's
`test_pymdownx_inlinehilite_also_fails_to_protect_inline_backticks`, for
the mechanism.

Renders every real doc page through the *actual* Zensical config this
project ships (the same `zensical.toml`, so the same `pymdownx.
inlinehilite` etc. that made the live bug happen) and fails if a raw
Python-Markdown internal stash placeholder leaks into any of them - the
exact, directly-observed symptom of this bug on the live site
(`klzzwxh:00NN` shown instead of the intended literal text). A future doc
edit that reintroduces this mistake (in this file or a new one) fails
here before it ever reaches the live site again.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# Collected at import time so a failure names the specific file in
# pytest's own test id, rather than one shared test looping silently
# past an early failure.
_DOC_FILES = sorted(DOCS_DIR.rglob("*.md"))


@pytest.mark.parametrize("doc_path", _DOC_FILES, ids=lambda p: str(p.relative_to(DOCS_DIR)))
def test_doc_page_has_no_stash_placeholder_leak(
    doc_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import zensical.config as zensical_config
    from zensical.markdown.render import render as zensical_render

    monkeypatch.chdir(REPO_ROOT)
    zensical_config.parse_config("zensical.toml")
    docs_rel_path = str(doc_path.relative_to(DOCS_DIR))
    raw = doc_path.read_text(encoding="utf-8")
    result = zensical_render(raw, docs_rel_path, docs_rel_path)
    html = result["content"]
    assert "klzzwxh" not in html
