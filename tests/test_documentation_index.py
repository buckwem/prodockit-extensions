# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Primary documentation topics remain discoverable in the PDF index."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_topic_owner_pages_define_their_principal_index_entries() -> None:
    expected = {
        "docs/introduction.md": (r"\index{Zensical}",),
        "docs/getting-started.md": (r"\index{virtual environment}", r"\index{`zensical serve`}"),
        "docs/authoring.md": (r"\index{Markdown}", r"\index{PyMdown Blocks}"),
        "docs/publishing.md": (r"\index{publishing workflow}", r"\index{continuous integration}"),
        "docs/prodockit-template.md": (r"\index{`prodockit-template`}", r"\index{`is_surrey`}"),
        "docs/command-line.md": (r"\index{command-line interface}",),
        "docs/update-dates.md": (r"\index{page update dates}",),
        "docs/stylesheets.md": (r"\index{stylesheets!stylesheet ownership}",),
        "docs/pdf.md": (
            r"\index{commands!`prodockit pdf`}",
            r"\index{commands!`prodockit init-tools`}",
            r"\index{commands!`prodockit source-bundle`}",
        ),
        "docs/project-maintenance.md": (r"\index{maintenance cycle}",),
        "docs/devcons/devcons.md": (r"\index{contributor internals}",),
        "docs/devcons/development.md": (r"\index{development environment}", r"\index{source code map}"),
        "docs/devcons/bootstrap-internals.md": (r"\index{bootstrap design}",),
        "docs/devcons/pdf-internals.md": (r"\index{PDF pipeline}",),
        "docs/devcons/zensical-coupling.md": (r"\index{Zensical coupling}",),
        "docs/devcons/limitations.md": (
            r"\index{limitations!extensions}",
            r"\index{limitations!PDF generation}",
            r"\index{limitations!website macros}",
        ),
        "docs/devcons/template-sync.md": (r"\index{commands!`prodockit template-sync`}",),
        "docs/devcons/bootstrap.md": (r"\index{commands!`prodockit bootstrap`}",),
        "docs/devcons/repo-metadata.md": (r"\index{commands!`prodockit sync-repo`}",),
        "docs/devcons/continuous-integration.md": (
            r"\index{continuous integration}",
            r"\index{GitHub Actions}",
            r"\index{GitLab CI}",
        ),
        "docs/devcons/pinning-drift.md": (
            r"\index{commands!`prodockit pins`}",
            r"\index{dependency drift}",
        ),
        "docs/devcons/releasing.md": (r"\index{release process}", r"\index{PyPI!Trusted Publishing}"),
        "docs/about/support.md": (r"\index{compatibility}", r"\index{platform testing}"),
        "docs/about/index.md": (r"\index{prodockit}",),
        "docs/about/limitations.md": (r"\index{limitations}",),
        "docs/extensions/steps.md": (r"\index{`prodockit.steps`}", r"\index{prodockit.steps!`start`}"),
        "docs/extensions/tree.md": (r"\index{`prodockit.tree`}", r"\index{prodockit.tree!`indent`}"),
        "docs/extensions/tables.md": (r"\index{prodockit.tables!`width`}", r"\index{prodockit.tables!`rotate`}"),
    }

    for relative_path, markers in expected.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in text]
        assert not missing, f"{relative_path} is missing index entries: {missing}"


def test_index_reference_results_do_not_pollute_the_real_index() -> None:
    text = (ROOT / "docs/extensions/index-terms.md").read_text(encoding="utf-8")
    results = re.findall(
        r'^=== "Result"\n\n(?P<body>(?:(?:    .*|)\n)*)',
        text,
        re.MULTILINE,
    )

    assert results
    assert all(r"\index{" not in result for result in results)
