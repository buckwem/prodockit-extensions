# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Test support for projects built with prodockit.

Two halves, usable independently:

- A **pytest plugin** (`prodockit.testing.plugin`, registered automatically
  via the `pytest11` entry point) providing `prodockit_*` fixtures for a
  project's own built output - the site directory and the PDF - resolved
  from its Zensical config rather than an assumed layout.
- **Checks** (`prodockit.testing.checks`) for the failure modes that are
  the same in every project, chiefly Mermaid diagrams and TeX maths
  reaching the PDF as raw source because their renderers weren't installed.

Install with ``pip install prodockit[testing]``. The fixtures test built
artifacts and never build anything, so run ``prodockit pdf`` and
``zensical build`` first.

Nothing here is imported by the rest of prodockit - a production install
that never runs pytest pays nothing for it.
"""

from prodockit.project_integrity import (
    assert_project_integrity,
    find_project_problems,
)
from prodockit.testing.checks import (
    assert_no_unrendered_mermaid,
    assert_no_unrendered_tex,
    contains_unrendered_mermaid,
    contains_unrendered_tex,
    find_unrendered_mermaid_pages,
    find_unrendered_tex_pages,
)

__all__ = [
    "assert_no_unrendered_mermaid",
    "assert_no_unrendered_tex",
    "assert_project_integrity",
    "contains_unrendered_mermaid",
    "contains_unrendered_tex",
    "find_project_problems",
    "find_unrendered_mermaid_pages",
    "find_unrendered_tex_pages",
]
