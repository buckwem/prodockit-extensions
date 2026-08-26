# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""A page-level macro exception must fail the documented Zensical CLI build."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_on_error_fail_stops_a_real_zensical_build(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text(
        "# Broken macro\n\n{{ missing_macro() }}\n",
        encoding="utf-8",
    )
    (tmp_path / "zensical.toml").write_text(
        """[project]
site_name = "Broken macro fixture"
docs_dir = "docs"
site_dir = "site"
nav = [{ "Home" = "index.md" }]

[project.markdown_extensions.zensical.extensions.macros]
module_name = ""
on_error_fail = true
""",
        encoding="utf-8",
    )

    executable = Path(sys.executable).with_name(
        "zensical.exe" if os.name == "nt" else "zensical"
    )
    completed = subprocess.run(
        [str(executable), "build", "--config-file", "zensical.toml"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode != 0, output
    assert "missing_macro" in output
