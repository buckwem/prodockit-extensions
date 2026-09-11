# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Repair verified stock workflows; propose changes separately for custom CI."""

from hashlib import sha256
from pathlib import Path

# Verified against zensical/zensical at be163399a59743ec76bc29d4b0c2d70fcd8d41d5:
# python/zensical/bootstrap/.github/workflows/docs.yml
# Unknown variants are custom, rather than guessed from one matching command.
STOCK_GITHUB = """name: Documentation
on:
  push:
    branches:
      - master
      - main
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/configure-pages@v6
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v6
        with:
          python-version: 3.x
      - run: pip install zensical
      - run: zensical build --clean
      - uses: actions/upload-pages-artifact@v5
        with:
          path: site
      - uses: actions/deploy-pages@v5
        id: deployment
"""

MATHJAX = """      - name: Restore optional MathJax website files
        run: |
          if [ -f tools/mathjax/package.json ]; then
            npm ci --prefix tools/mathjax
            pdk init-mathjax
          fi
"""

PROPOSAL_NOTICE = (
    "# Proposed Prodockit build instructions — review and merge manually.\n"
    "# This root-level file is not activated by Adopt.\n"
    "# Preserve your existing triggers, permissions, secrets and deployment settings.\n"
)


def _requirements(root: Path) -> str:
    for name in ("requirements.txt", "requirements/docs.txt", "docs/requirements.txt"):
        if (root / name).is_file():
            return name
    return "requirements.txt"


def github_content(root: Path) -> str:
    return STOCK_GITHUB.replace(
        "      - run: pip install zensical\n",
        f"      - run: python -m pip install -r {_requirements(root)}\n" + MATHJAX,
    )


def gitlab_content(root: Path) -> str:
    return (
        PROPOSAL_NOTICE
        + f"""# Merge the relevant commands into your existing Pages job.
# This hidden example job does not run by itself, even if included.
# It builds the website only; PDF generation needs additional tooling.
.prodockit-pages-example:
  image: python:3.14
  before_script:
    - python -m pip install -r {_requirements(root)}
    - |
      if [ -f tools/mathjax/package.json ]; then
        apt-get update
        apt-get install -y nodejs npm
        npm ci --prefix tools/mathjax
        pdk init-mathjax
      fi
  script:
    - zensical build --clean --strict
# Keep your existing Pages publish directory and deployment configuration.
# Adjust the build output directory to match that configuration.
"""
    )


def plans(root: Path) -> list[tuple[Path, str]]:
    changes = []
    github = root / ".github/workflows/docs.yml"
    if github.is_file():
        original_hash = sha256(github.read_bytes()).hexdigest()
        updated = github_content(root)
        if original_hash == sha256(STOCK_GITHUB.encode("utf-8")).hexdigest():
            changes.append((github, updated))
        elif original_hash != sha256(updated.encode("utf-8")).hexdigest():
            proposal = root / "pdk.yml"
            if not proposal.exists():
                changes.append((proposal, PROPOSAL_NOTICE + updated))
    gitlab = root / ".gitlab-ci.yml"
    if gitlab.is_file():
        # No verified stock GitLab baseline is bundled: unknown files are custom.
        # Never infer "unmodified" from a matching job or install command.
        proposal = root / ".gitlab-pdk.yml"
        if not proposal.exists():
            changes.append((proposal, gitlab_content(root)))
    return changes


def plan(root: Path) -> tuple[Path, str] | None:
    """Compatibility accessor for callers asking whether any work is pending."""
    pending = plans(root)
    return pending[0] if pending else None
