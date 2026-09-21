# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = (ROOT / "docs/devcons/bootstrap.md").read_text(encoding="utf-8")
ADOPT_GUIDE = (ROOT / "docs/getting-started.md").read_text(encoding="utf-8")
MANUAL_GUIDE = (ROOT / "docs/manual-install.md").read_text(encoding="utf-8")


def test_template_site_installation_has_a_pdf_software_step() -> None:
    assert "### Stage 4 — Install for PDF" in GUIDE
    assert "### Stage 5 — Verifying the project" in GUIDE
    heading = "//// step | Install optional PDF software"
    assert heading in GUIDE
    assert GUIDE.index(heading) < GUIDE.index("//// step | Run project diagnostics")
    assert "Skip this step for a website-only project" in GUIDE


def test_template_site_pdf_install_builds_both_downloads() -> None:
    installation = GUIDE[
        GUIDE.index("### Stage 4 — Install for PDF") : GUIDE.index(
            "### Stage 5 — Verifying the project"
        )
    ]
    website = installation.index("zensical build --clean --strict")
    pdf = installation.index("\npdk pdf\n")
    source_bundle = installation.index("pdk source-bundle")

    assert website < pdf < source_bundle
    assert "Stop and correct any failure before continuing" in installation
    assert "consumes this\ncompleted Zensical build" in installation
    assert "Skip this\nstep for a website-only project" in installation


def test_template_site_verification_serves_and_checks_both_downloads() -> None:
    verification = GUIDE[GUIDE.index("### Stage 5 — Verifying the project") :]
    diagnostics = verification.index("//// step | Run project diagnostics")
    serve = verification.index("zensical serve")

    assert diagnostics < serve
    assert "Open the address printed by Zensical in a browser" in verification
    assert "both download buttons" in verification
    assert "rendered document PDF and source-bundle PDF" in verification
    assert "Press `Ctrl+C`" in verification


def test_template_site_pdf_step_covers_supported_host_prerequisites() -> None:
    for command in (
        "brew install pango node",
        "libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 nodejs",
        "winget install OpenJS.NodeJS.LTS",
        "node --version",
        "pdk pdf --prepare all",
    ):
        assert command in GUIDE


def test_template_site_pdf_step_distinguishes_forced_and_lazy_preparation() -> None:
    assert "force every optional component with `--prepare all`" in GUIDE
    assert "Ordinary `pdk pdf` is the simpler default" in GUIDE
    assert "prepares only components found" in GUIDE
    assert "no Node.js, npm,\nbrowser or MSYS2" in GUIDE


def test_installation_sections_four_five_and_six_show_exact_pdf_commands() -> None:
    for guide in (ADOPT_GUIDE, GUIDE, MANUAL_GUIDE):
        assert "brew install pango node" in guide
        assert "winget install OpenJS.NodeJS.LTS" in guide
        assert "libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 nodejs" in guide
        assert "node --version" in guide
