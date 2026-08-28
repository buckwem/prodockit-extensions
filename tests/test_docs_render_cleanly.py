# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Guards against a real bug found by checking the live site: this
project's own docs (docs/**/*.md) accidentally showing a prodockit
extension's own backslash-command syntax as literal example text using
inline backticks, when the syntax in question (a code-styled
`\\index{`Term`}`) isn't actually protected by inline backticks the way
a plain `\\index{Term}`/`\\ref{id}`/`\\citeref{id}`/`\\gls{id}` is - see
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

import re
import subprocess
from pathlib import Path

import pytest

from prodockit.pdf.site import page_html
from prodockit.project_config import ProjectConfig, load_project_config

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# Collected at import time so a failure names the specific file in
# pytest's own test id, rather than one shared test looping silently
# past an early failure.
_DOC_FILES = sorted(DOCS_DIR.rglob("*.md"))

_INTENTIONAL_JINJA_BY_PAGE = {
    "index.md": {
        "{% if release %}",
        '<p class="cover-hero-release">Release: {{ release }}</p>',
        "{% endif %}",
    },
    "prodockit-template.md": {
        "{% if is_surrey %}",
        "{% else %}",
        "{% endif %}",
    },
}


@pytest.fixture(scope="module")
def built_project() -> ProjectConfig:
    """Build once through Zensical's documented CLI for all page checks."""
    project = load_project_config(REPO_ROOT / "zensical.toml")
    subprocess.run(
        ["zensical", "build", "--clean", "--strict", "--config-file", str(project.path)],
        cwd=project.root,
        check=True,
    )
    return project


@pytest.mark.parametrize("doc_path", _DOC_FILES, ids=lambda p: str(p.relative_to(DOCS_DIR)))
def test_doc_page_has_no_stash_placeholder_leak(
    doc_path: Path, built_project: ProjectConfig
) -> None:
    docs_rel_path = str(doc_path.relative_to(DOCS_DIR))
    html = page_html(built_project, docs_rel_path)
    assert "klzzwxh" not in html
    assert "<p>{{ heading_counter_reset(page) }}</p>" not in html


@pytest.mark.parametrize("doc_path", _DOC_FILES, ids=lambda p: str(p.relative_to(DOCS_DIR)))
def test_doc_page_has_no_unintended_jinja_delimiter(doc_path: Path) -> None:
    docs_rel_path = str(doc_path.relative_to(DOCS_DIR))
    text = doc_path.read_text(encoding="utf-8")
    text = re.sub(r"{% raw %}.*?{% endraw %}", "", text, flags=re.DOTALL)
    text = text.replace("{{ heading_counter_reset(page) }}", "")
    for expression in _INTENTIONAL_JINJA_BY_PAGE.get(docs_rel_path, set()):
        text = text.replace(expression, "")

    assert "{{" not in text
    assert "{%" not in text
    assert "{#" not in text
