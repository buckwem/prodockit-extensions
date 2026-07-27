# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Backwards-compatible home for the `prodockit` command-line entry point.

The CLI moved to `prodockit.cli` once it grew commands with nothing to do
with the PDF build (`prodockit sync-repo`), since a package-wide command
group living inside `prodockit.pdf` no longer described what it was. This
re-exports `main` so a `prodockit.pdf.cli:main` console script recorded in
an already-installed environment keeps working rather than breaking on
upgrade.
"""

from __future__ import annotations

from prodockit.cli import main as main

__all__ = ["main"]
