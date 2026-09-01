# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The maintenance guide covers the repository's real operating workflow."""

from __future__ import annotations

import re
from pathlib import Path

from prodockit.template_sync import read_config

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "zensical.toml"
TABLE_DELIMITER = re.compile(
    r"^\|?\s*:?-{1,}:?\s*(?:\|\s*:?-{1,}:?\s*)+\|?$"
)


def _nav_group(title: str) -> list[dict[str, str]]:
    config = read_config(CONFIG.read_text(encoding="utf-8"))
    nav = config["project"]["nav"]
    return next(item[title] for item in nav if title in item)


def test_getting_started_holds_installation_routes() -> None:
    getting_started = _nav_group("Getting started")
    publishing = _nav_group("Publish a document")
    maintenance = _nav_group("Maintain prodockit")

    assert {"3. Add prodockit to an existing document": "adopt.md"} in getting_started
    assert {"4. Set up a template project": "devcons/bootstrap.md"} in getting_started
    assert {"5. Start with prodockit-template": "prodockit-template.md"} in getting_started
    assert {
        "23. Staying in step with the template": "devcons/template-sync.md"
    } in publishing
    assert maintenance == [
        {"26. Maintenance overview": "project-maintenance.md"},
        {"27. Repository metadata": "devcons/repo-metadata.md"},
        {"28. Version pinning and drift": "devcons/pinning-drift.md"},
        {"29. Build and release": "devcons/releasing.md"},
    ]


def test_release_guide_covers_every_github_actions_workflow() -> None:
    guide = (ROOT / "docs" / "devcons" / "releasing.md").read_text(encoding="utf-8")
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

    missing = [workflow.name for workflow in workflows if workflow.name not in guide]
    assert not missing, f"GitHub Actions workflows absent from the release guide: {missing}"


def test_release_diagram_distinguishes_entry_points_from_steps() -> None:
    guide = (ROOT / "docs" / "devcons" / "releasing.md").read_text(encoding="utf-8")
    source = (
        ROOT / "tools" / "documentation-diagrams" / "29.1-release-workflow.drawio"
    ).read_text(encoding="utf-8")

    assert "29.1-release-workflow.png" in guide
    assert "Release branch" in source
    assert "SCHEDULED TRIGGER" in source
    assert "Every Monday" in source
    assert "fillColor=#19c866" in source


def test_documentation_builds_the_website_before_the_pdf() -> None:
    """The PDF consumes a completed Zensical build; examples must preserve that."""

    documentation_paths = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    for path in documentation_paths:
        contents = path.read_text(encoding="utf-8")
        assert not re.search(
            r"prodockit pdf\s*\n\s*zensical build",
            contents,
        ), path

    source = (
        ROOT / "tools" / "documentation-diagrams" / "24.1-publication-pipeline.drawio"
    ).read_text(encoding="utf-8")
    assert source.index('value="Build website"') < source.index('value="Build PDF"')


def test_adoption_diagram_stays_independent_of_the_site_generator() -> None:
    source = (
        ROOT / "tools" / "documentation-diagrams" / "3.1-adoption-workflow.drawio"
    ).read_text(encoding="utf-8")

    assert "Existing documentation&lt;br&gt;project" in source


def test_adoption_guide_is_for_zensical_projects() -> None:
    guide = (ROOT / "docs" / "adopt.md").read_text(encoding="utf-8")

    assert "mkdocs" not in guide.lower()
    assert "zensical build --clean --strict" in guide
    assert "zensical build -f zensical.yml --clean --strict" in guide
    assert "zensical build -f zensical.yaml --clean --strict" in guide


def test_documentation_flow_diagrams_have_editable_drawio_sources() -> None:
    diagram_dir = ROOT / "tools" / "documentation-diagrams"

    for image in (ROOT / "docs" / "assets" / "diagrams").glob("*.png"):
        if image.name in {
            "1.1-prodockit-output-relationship.png",
            "19.1-website-and-pdf-example.png",
        }:
            continue
        source = diagram_dir / f"{image.stem}.drawio"
        contents = source.read_text(encoding="utf-8")
        assert "<mxGraphModel" in contents, source
        assert 'vertex="1"' in contents, source
        assert 'edge="1"' in contents, source


def test_documentation_flow_diagrams_are_committed_raster_images() -> None:
    """Architecture diagrams stay identical in the website and PDF."""

    expected = {
        "docs/adopt.md": ("3.1-adoption-workflow.png",),
        "docs/authoring.md": ("7.1-authoring-feature-map.png",),
        "docs/stylesheets.md": (
            "21.1-website-stylesheet-cascade.png",
            "21.2-pdf-stylesheet-cascade.png",
        ),
        "docs/update-dates.md": ("18.1-page-update-dates.png",),
        "docs/prodockit-template.md": ("5.1-template-file-ownership.png",),
        "docs/devcons/continuous-integration.md": ("24.1-publication-pipeline.png",),
        "docs/devcons/extension-internals.md": (
            "32.1-extension-integration-flow.png",
            "32.2-cross-reference-resolution.png",
            "32.3-bibliography-pipeline.png",
        ),
        "docs/devcons/pdf-internals.md": ("33.1-pdf-pipeline.png",),
        "docs/devcons/pinning-drift.md": ("28.1-version-pinning-drift.png",),
        "docs/devcons/releasing.md": (
            "29.1-release-workflow.png",
            "29.2-downstream-release-cascade.png",
        ),
        "docs/devcons/template-sync.md": ("23.1-template-sync-decision.png",),
        "docs/devcons/testing.md": ("25.1-output-testing-layers.png",),
        "docs/introduction.md": ("1.1-prodockit-output-relationship.png",),
        "docs/pdf.md": ("19.1-website-and-pdf-example.png",),
    }
    png_signature = b"\x89PNG\r\n\x1a\n"

    for guide_path in (ROOT / "docs").rglob("*.md"):
        source_lines = guide_path.read_text(encoding="utf-8").splitlines()
        assert "```mermaid" not in (line.strip() for line in source_lines), guide_path

    for relative_path, image_names in expected.items():
        guide = (ROOT / relative_path).read_text(encoding="utf-8")
        for image_name in image_names:
            assert image_name in guide, f"{relative_path} does not use {image_name}"
            semantic_name = image_name.split("-", 1)[1]
            caption_id = f"attrs: {{id: fig-{Path(semantic_name).stem}}}"
            assert caption_id in guide, (
                f"{relative_path} does not caption {image_name} with {caption_id}"
            )
            image = ROOT / "docs" / "assets" / "diagrams" / image_name
            assert image.read_bytes().startswith(png_signature), image

    expected_images = {
        image_name for image_names in expected.values() for image_name in image_names
    }
    committed_images = {
        image.name for image in (ROOT / "docs" / "assets" / "diagrams").glob("*.png")
    }
    assert committed_images == expected_images


def test_every_documentation_table_has_a_numbered_caption_above_it() -> None:
    """Keep tables identifiable in prose and consistent in website/PDF output."""

    missing: list[str] = []
    table_count = 0

    for guide_path in sorted((ROOT / "docs").rglob("*.md")):
        lines = guide_path.read_text(encoding="utf-8").splitlines()
        in_fence = False
        line_number = 0

        while line_number < len(lines):
            stripped = lines[line_number].lstrip()
            if stripped.startswith(("```", "~~~")):
                in_fence = not in_fence

            is_table = (
                not in_fence
                and stripped.startswith("|")
                and line_number + 1 < len(lines)
                and TABLE_DELIMITER.match(lines[line_number + 1].strip()) is not None
            )
            if not is_table:
                line_number += 1
                continue

            table_count += 1
            table_line = line_number + 1
            line_number += 2
            while (
                line_number < len(lines)
                and lines[line_number].lstrip().startswith("|")
            ):
                line_number += 1
            while line_number < len(lines) and not lines[line_number].strip():
                line_number += 1

            caption = lines[line_number:] if line_number < len(lines) else []
            has_leading_caption = bool(
                caption and caption[0].lstrip() == "/// table-caption | <"
            )
            has_static_id = any(
                "attrs: {id: tab-" in line for line in caption[:4]
            )
            if not (has_leading_caption and has_static_id):
                relative = guide_path.relative_to(ROOT)
                missing.append(f"{relative}:{table_line}")

    assert table_count, "documentation table audit did not find any tables"
    assert not missing, "tables without leading numbered captions: " + ", ".join(missing)


def test_tables_and_figures_are_introduced_before_they_appear() -> None:
    """Introduce every numbered table and figure in the preceding narrative."""

    missing: list[str] = []

    for guide_path in sorted((ROOT / "docs").rglob("*.md")):
        lines = guide_path.read_text(encoding="utf-8").splitlines()
        in_fence = False

        for line_number, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            is_table = (
                stripped.startswith("|")
                and line_number + 1 < len(lines)
                and TABLE_DELIMITER.match(lines[line_number + 1].strip()) is not None
            )
            is_figure = ".documentation-diagram" in line
            if not (is_table or is_figure):
                continue

            previous = line_number - 1
            while previous >= 0 and not lines[previous].strip():
                previous -= 1
            if previous < 0 or lines[previous].lstrip().startswith("#"):
                relative = guide_path.relative_to(ROOT)
                missing.append(f"{relative}:{line_number + 1}")

            introduction = "\n".join(lines[max(0, line_number - 12) : line_number])

            if is_table:
                following = line_number + 2
                while (
                    following < len(lines)
                    and lines[following].lstrip().startswith("|")
                ):
                    following += 1
                caption = "\n".join(lines[following : following + 6])
                match = re.search(r"attrs: \{id: (tab-[^}]+)", caption)
                if match is None or f"\\ref{{{match.group(1)}}}" not in introduction:
                    relative = guide_path.relative_to(ROOT)
                    missing.append(f"{relative}:{line_number + 1} (no table reference)")

            if is_figure:
                caption = "\n".join(lines[line_number + 1 : line_number + 7])
                match = re.search(r"attrs: \{id: (fig-[^}]+)", caption)
                if match is None or f"\\ref{{{match.group(1)}}}" not in introduction:
                    relative = guide_path.relative_to(ROOT)
                    missing.append(f"{relative}:{line_number + 1} (no figure reference)")

    assert not missing, "tables or figures without preceding narrative: " + ", ".join(
        missing
    )


def test_parent_sections_introduce_their_subsections() -> None:
    """A parent heading should orient the reader before the first child heading."""

    missing: list[str] = []

    for guide_path in sorted((ROOT / "docs").rglob("*.md")):
        lines = guide_path.read_text(encoding="utf-8").splitlines()
        in_fence = False

        for line_number, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence or not line.startswith("#"):
                continue

            level = len(line) - len(line.lstrip("#"))
            following = line_number + 1
            while following < len(lines) and not lines[following].strip():
                following += 1
            if following >= len(lines) or not lines[following].startswith("#"):
                continue
            next_level = len(lines[following]) - len(lines[following].lstrip("#"))
            if next_level > level:
                relative = guide_path.relative_to(ROOT)
                missing.append(f"{relative}:{line_number + 1}")

    assert not missing, "parent sections without introductory narrative: " + ", ".join(
        missing
    )


def test_sections_introduce_structured_content() -> None:
    """Explain a procedure, command, list, or example before presenting it."""

    structural_starts = (
        "```",
        "~~~",
        "|",
        "- ",
        "* ",
        "!!!",
        "???",
        "///",
        '=== "',
        "<",
    )
    missing: list[str] = []

    for guide_path in sorted((ROOT / "docs").rglob("*.md")):
        # A changelog is intentionally a sequence of release headings and bullets.
        if guide_path.name == "changelog.md":
            continue

        lines = guide_path.read_text(encoding="utf-8").splitlines()
        in_fence = False

        for line_number, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence or not line.startswith("#"):
                continue

            following = line_number + 1
            while following < len(lines) and not lines[following].strip():
                following += 1
            if following >= len(lines):
                continue

            first_content = lines[following].lstrip()
            is_numbered_list = re.match(r"\d+\.\s", first_content) is not None
            if first_content.startswith(structural_starts) or is_numbered_list:
                relative = guide_path.relative_to(ROOT)
                missing.append(f"{relative}:{line_number + 1}")

    assert not missing, "sections without introductory narrative: " + ", ".join(
        missing
    )


def test_visual_introductions_do_not_use_placeholder_prose() -> None:
    """A numbered reference must tell the reader what the object contributes."""

    documentation = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "docs").rglob("*.md"))
    )
    assert "The relevant details are summarised in" not in documentation


def test_reference_tables_reserve_space_for_identifier_columns() -> None:
    """Do not let a wide prose column collapse short labels or identifiers."""

    documentation = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "docs").rglob("*.md"))
    )
    identifier_headers = (
        "Variable",
        "Macro",
        "Setting",
        "File",
        "Workflow",
        "Extension",
        "Command",
        "Requirement",
        "Surface",
        "Option",
        "Fixture",
        "Function",
        "API",
        "Module",
        "Alternative",
        "Symptom",
        "Path",
        "Marker",
    )

    missing_width = [
        header
        for header in identifier_headers
        if re.search(rf"^\| {re.escape(header)} \|", documentation, re.MULTILINE)
    ]
    assert not missing_width, (
        "reference-table identifier columns without an explicit width: "
        + ", ".join(missing_width)
    )


def test_pdf_platform_tabs_use_the_standard_labels_and_icons() -> None:
    guide = (ROOT / "docs" / "pdf.md").read_text(encoding="utf-8")

    for label in (
        '=== ":material-apple: macOS"',
        '=== ":fontawesome-brands-windows: Windows"',
        '=== ":material-linux: Linux (Ubuntu)"',
    ):
        assert guide.count(label) == 2


def test_release_guide_covers_the_version_sources_and_release_gates() -> None:
    guide = (ROOT / "docs" / "devcons" / "releasing.md").read_text(encoding="utf-8")
    required = (
        "pyproject.toml",
        "src/prodockit/__init__.py",
        "docs/about/changelog.md",
        "prodockit pins --check --offline",
        "pytest",
        "ruff check .",
        "mypy src",
        "zensical build --clean --strict",
        'python -m pip install "twine==7.0.0"',
        "python -m twine check --strict dist/*.whl dist/*.tar.gz",
        "GitHub release",
        "PyPI",
        "Trusted Publishing",
    )

    missing = [item for item in required if item not in guide]
    assert not missing, f"release steps or gates absent from the guide: {missing}"


def test_package_artifacts_are_strictly_checked_before_they_can_be_published() -> None:
    publish = (ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    install = 'pip install build "twine==7.0.0"'
    build = "python -m build"
    check = "python -m twine check --strict dist/*.whl dist/*.tar.gz"
    upload = "uses: actions/upload-artifact@v4"

    for workflow in (publish, ci):
        assert install in workflow
        assert build in workflow
        assert check in workflow
        assert workflow.index(install) < workflow.index(build) < workflow.index(check)

    assert publish.index(check) < publish.index(upload)
    assert "needs: build" in publish


def test_command_map_lists_every_public_command() -> None:
    guide = (ROOT / "docs" / "command-line.md").read_text(encoding="utf-8")
    commands = (
        "bootstrap",
        "config",
        "diag",
        "init-mathjax",
        "init-tools",
        "pdf",
        "pins",
        "shared-files",
        "source-bundle",
        "sync-repo",
        "template-sync",
    )

    missing = [command for command in commands if f"`prodockit {command}" not in guide]
    assert not missing, f"public CLI commands absent from the command map: {missing}"


def test_template_sync_guide_covers_package_only_updates() -> None:
    guide = (ROOT / "docs" / "devcons" / "template-sync.md").read_text(encoding="utf-8")

    assert "version of prodockit installed" in guide
    assert "python -m pip install" in guide
    assert "When only prodockit needs upgrading" in guide
    assert "Pages" in guide and "documentation" in guide
    assert "manual rebuild is still necessary" in guide


def test_template_sync_links_managed_stylesheet_warnings_to_the_style_guide() -> None:
    guide = (ROOT / "docs" / "devcons" / "template-sync.md").read_text(encoding="utf-8")

    assert "Warning - managed stylesheet changes found" in guide
    assert "[Stylesheets](../stylesheets.md)" in guide


def test_contributor_guide_records_the_managed_stylesheet_release_contract() -> None:
    guide = (ROOT / "docs" / "devcons" / "extension-internals.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "[Stylesheets](../stylesheets.md)",
        "force-include",
        "src/prodockit/shared_files.py",
        "prodockit-template",
        "prodockit-userguide",
        "prodockit pins --check",
    ):
        assert phrase in guide

    code_map = (ROOT / "docs" / "devcons" / "development.md").read_text(encoding="utf-8")
    for phrase in (
        "stylesheet-delivery-code-map",
        "docs/stylesheets/pdk.css",
        "docs/stylesheets/pdk-pdf.css",
        "src/prodockit/shared_files.py",
        "src/prodockit/template_sync.py",
        "src/prodockit/pdf/config.py",
        "tests/test_shared_file_wheel.py",
    ):
        assert phrase in code_map
