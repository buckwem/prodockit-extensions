# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import yaml

from prodockit.adopt import LOCAL_IGNORE_PATTERNS, ensure_local_ignores
from prodockit.adopt_workflow import plan


def test_stock_workflow_repair_is_valid_and_idempotent(tmp_path):
    path = tmp_path / ".github/workflows/docs.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "jobs:\n  deploy:\n    steps:\n"
        "      - run: pip install zensical\n"
        "      - run: zensical build --clean\n"
    )
    _, content = plan(tmp_path)
    steps = yaml.safe_load(content)["jobs"]["deploy"]["steps"]
    assert steps[0]["run"] == "python -m pip install -r requirements.txt"
    assert "npm ci --prefix tools/mathjax" in steps[1]["run"]
    assert steps[2]["run"] == "zensical build --clean"
    path.write_text(content)
    assert plan(tmp_path) is None


def test_custom_workflow_untouched(tmp_path):
    path = tmp_path / ".github/workflows/docs.yml"
    path.parent.mkdir(parents=True)
    path.write_text("steps:\n  - run: pip install zensical custom-package\n")
    assert plan(tmp_path) is None


def test_ignores_preserve_authored_rules_and_are_idempotent(tmp_path):
    path = tmp_path / ".gitignore"
    path.write_text("# Custom rule\nprivate/\n")
    assert ensure_local_ignores(tmp_path) == [path]
    content = path.read_text()
    assert content.startswith("# Custom rule\nprivate/\n")
    assert all(line in content.splitlines() for line in LOCAL_IGNORE_PATTERNS)
    assert ensure_local_ignores(tmp_path) == []
