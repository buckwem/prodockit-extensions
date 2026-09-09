# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Narrow repair of Zensical's stock GitHub workflow, not custom pipelines."""

import re
from pathlib import Path


def plan(root: Path) -> tuple[Path, str] | None:
    path = root / ".github" / "workflows" / "docs.yml"
    if not path.is_file():
        return None
    original = path.read_text(encoding="utf-8")
    # Only the exact stock single-package installation is ours to migrate.
    # Never replace a user's multi-command or custom dependency installation.
    pattern = r"(?m)^([ \t]*)- run: (?:python -m )?pip install zensical[ \t]*$"
    match = re.search(pattern, original)
    if not match:
        return None
    indent = match.group(1)
    replacement = indent + "- run: python -m pip install -r requirements.txt"
    replacement += (
        "\n" + indent + "- name: Restore optional MathJax website files"
        "\n" + indent + "  run: |"
        "\n" + indent + "    if [ -f tools/mathjax/package.json ]; then"
        "\n" + indent + "      npm ci --prefix tools/mathjax"
        "\n" + indent + "      pdk init-mathjax"
        "\n" + indent + "    fi"
    )
    updated = original[: match.start()] + replacement + original[match.end() :]
    return path, updated
