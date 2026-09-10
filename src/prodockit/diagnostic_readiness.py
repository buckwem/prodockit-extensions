# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Read-only author-facing publishing and generated-file checks."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from prodockit.project_config import ProjectConfig

if TYPE_CHECKING:
    from prodockit.diagnostics import DiagnosticResult


def checks(config: ProjectConfig) -> list[DiagnosticResult]:
    from prodockit.adopt_identity import missing_fields
    from prodockit.diagnostics import DiagnosticResult
    from prodockit.sync_repo import SyncRepoError, parse_remote

    root = config.root
    project = config.project
    section = "Publishing preparation (not required for local builds)"
    details = []
    if "repo_name" in missing_fields(project):
        details.append("The repository display name (repo_name) has not been set.")
    if config.site_name.strip().casefold() in {
        "",
        "documentation",
        "my docs",
        "my site",
        "your site",
        "your site name",
    }:
        details.append("The site title is still a starter value.")
    address = str(project.get("site_url") or "")
    parsed = urlparse(address)
    if not address or parsed.hostname in {
        "example.com",
        "www.example.com",
        "example.org",
        "www.example.org",
    }:
        details.append("The website address (site_url) is missing or still an example.")
    elif parsed.scheme not in {"https", "http"} or not parsed.hostname:
        details.append("The website address must be a full http:// or https:// address.")

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )

    repository = bool(shutil.which("git") and git("rev-parse", "--show-toplevel").returncode == 0)
    remote = git("remote", "get-url", "origin") if repository else None
    if remote is not None and remote.returncode == 0:
        try:
            host, namespace, name = parse_remote(remote.stdout.strip())
            expected = f"https://{host}/{namespace}/{name}"
            if str(project.get("repo_url") or "").rstrip("/") != expected:
                details.append("Repository link (repo_url) is missing or differs from origin.")
            correction = (
                "Run `pdk adopt --apply` to complete missing details. If the origin remote "
                "has changed, run `pdk sync-repo --create-readme` to align existing links."
            )
        except (ValueError, SyncRepoError):
            details.append("The origin remote could not be interpreted as a hosted repository.")
            correction = (
                "Review the origin remote in Stage 6, then run `pdk sync-repo`; "
                "no remote is changed by diagnostics."
            )
    else:
        details.append(
            "No origin remote is configured; repository links cannot yet be set automatically."
        )
        correction = (
            "Continue local testing. Run `pdk adopt --apply` for the optional site and "
            "repository questions, or defer repository setup until Stage 6."
        )
    results = [
        DiagnosticResult(
            "publishing.details",
            section,
            "warn" if details else "pass",
            "Publishing details need attention; local testing can continue"
            if details
            else "Site and repository details are configured",
            (
                *details,
                correction,
                "A configured URL does not prove that the website is published.",
            ),
        )
    ]

    if repository:
        candidates = [
            ".venv/pyvenv.cfg",
            "__pycache__/probe.pyc",
            "tools/mermaid/node_modules/probe",
            "tools/mathjax/node_modules/probe",
        ]
        for path in (config.site_dir, config.docs_dir / ".prodockit-pdf-mermaid"):
            if path.is_relative_to(root):
                candidates.append(path.relative_to(root).as_posix() + "/probe")
        for key, default in (
            ("pdf_output", "docs/site_documentation.pdf"),
            ("pdf_source_bundle_output", "docs/source_bundle.pdf"),
        ):
            path = Path(str(config.extra.get(key) or default))
            if not path.is_absolute() and ".." not in path.parts:
                candidates.append(path.as_posix())
        ignore_results = {
            path: git("check-ignore", "--no-index", "-q", "--", path).returncode
            for path in candidates
        }
        unignored = [path for path, code in ignore_results.items() if code == 1]
        tracked = git(
            "ls-files",
            "--",
            ".venv",
            "tools/mermaid/node_modules",
            "tools/mathjax/node_modules",
            *[p.removesuffix("/probe") for p in candidates[4:]],
        )
        problems = []
        if any(code not in {0, 1} for code in ignore_results.values()):
            problems.append("Git could not inspect ignore rules; check repository access.")
        if unignored:
            problems.append("Ignore rules are missing for: " + ", ".join(unignored))
            problems.append(
                "Run `pdk adopt --apply` to add baseline ignore rules. "
                "Custom output paths need matching project ignore rules."
            )
        if tracked.stdout.strip():
            problems.append(
                "Generated/local files are already tracked by Git: "
                + ", ".join(tracked.stdout.splitlines()[:10])
            )
            problems.append(
                "Review and untrack those files while retaining local copies; "
                "adding ignore rules alone does not untrack them. Diagnostics never removes files."
            )
        if tracked.returncode:
            problems.append(
                "Git could not verify tracked generated files; "
                "inspect repository access before continuing."
            )
        results.append(
            DiagnosticResult(
                "repository.generated-files",
                "Repository and template maintenance",
                "warn" if problems else "pass",
                "Generated-file protection needs attention"
                if problems
                else "Checked local environments and generated outputs are protected from Git",
                tuple(problems),
            )
        )

    workflow_dir = root / ".github/workflows"
    workflows = [
        *sorted(workflow_dir.glob("*.yml")),
        *sorted(workflow_dir.glob("*.yaml")),
        root / ".gitlab-ci.yml",
    ]
    present = [path for path in workflows if path.is_file()]
    if present:
        problems = []
        for path in present:
            source = "\n".join(
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")
            )
            if (
                re.search(r"pip(?:3)? install zensical(?:\s|$)", source)
                and "requirements.txt" not in source
                and "prodockit" not in source.lower()
            ):
                problems.append(
                    f"{path.relative_to(root)} installs only Zensical, not Prodockit. "
                    "Run `pdk adopt --apply` to review the stock workflow repair."
                )
            for requirement in re.findall(r"(?:^|\s)-r\s+([\w./-]+)", source):
                if not (root / requirement).is_file():
                    problems.append(
                        f"{path.relative_to(root)} refers to missing {requirement}; "
                        "restore the dependency file or review the workflow in Build and publish."
                    )
        results.append(
            DiagnosticResult(
                "publishing.workflow",
                section,
                "warn" if problems else "pass",
                "Publishing workflow needs attention"
                if problems
                else "Basic local publishing workflow checks passed",
                (
                    *problems,
                    "This is not a full CI validation. Check the hosting provider's pipeline "
                    "and Pages settings in Stage 6; remote publication has not been verified.",
                ),
            )
        )
    return results
