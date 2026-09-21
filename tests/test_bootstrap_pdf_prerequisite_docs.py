# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = (ROOT / "docs/devcons/bootstrap.md").read_text(encoding="utf-8")
ADOPT_GUIDE = (ROOT / "docs/getting-started.md").read_text(encoding="utf-8")
MANUAL_GUIDE = (ROOT / "docs/manual-install.md").read_text(encoding="utf-8")


def test_template_site_installation_has_an_optional_pdf_software_stage() -> None:
    assert "### Stage 4 — Enter the project" in GUIDE
    assert "### Stage 5 — Install PDF support (optional)" in GUIDE
    assert "### Stage 6 — Build the PDF downloads (optional)" in GUIDE
    assert "### Stage 7 — Verify the project" in GUIDE
    heading = "//// step | Install optional PDF software"
    assert heading in GUIDE
    assert GUIDE.index(heading) < GUIDE.index("//// step | Run project diagnostics")
    assert "Complete Stages 5 and 6 only when you need to generate PDFs locally" in GUIDE
    assert "Skip both\nfor website-only work and on Windows ARM64" in GUIDE
    assert "use the GitLab build for both PDF\ndownloads" in GUIDE
    assert '!!! important "Install Pandoc through Prodockit"' in GUIDE
    assert "pdk pdf --prepare pandoc" in GUIDE
    assert "Do not install Pandoc with Homebrew, Winget or apt" in GUIDE
    assert "do not rely on a\n    system `pandoc` command from `PATH`" in GUIDE


def test_template_site_pdf_install_builds_both_downloads() -> None:
    installation = GUIDE[
        GUIDE.index("### Stage 6 — Build the PDF downloads (optional)") : GUIDE.index(
            "### Stage 7 — Verify the project"
        )
    ]
    website = installation.index("zensical build --clean --strict")
    pdf = installation.index("\npdk pdf\n")
    source_bundle = installation.index("pdk source-bundle")

    assert source_bundle < website < pdf
    assert "//// step | Build the source bundle" in installation
    assert "//// step | Build the website for PDF rendering" in installation
    assert "//// step | Build the rendered document PDF" in installation
    assert "Stop and correct any failure before continuing" in installation
    assert "consumes this\ncompleted Zensical build" in installation
    assert "Skip it for website-only work and on Windows ARM64" in installation
    assert "GitLab\nbuild generates both downloads" in installation


def test_template_site_verification_serves_and_checks_both_downloads() -> None:
    verification = GUIDE[GUIDE.index("### Stage 7 — Verify the project") :]
    diagnostics = verification.index("//// step | Run project diagnostics")
    serve = verification.index("zensical serve")

    assert diagnostics < serve
    assert "Open the address printed by Zensical in a browser" in verification
    assert "both download buttons" in verification
    assert "rendered document PDF and source-bundle PDF" in verification
    assert "On Windows ARM64" in verification
    assert "check both PDFs from the successful GitLab build" in verification
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


def test_adopt_has_distinct_optional_pdf_install_and_prepare_steps() -> None:
    stage = "### Stage 6 — Add downloadable outputs **Optional**"
    host = "//// step | Install PDF host software"
    prepare = "//// step | Prepare PDF components"

    assert stage in ADOPT_GUIDE
    assert "The whole stage is optional" in ADOPT_GUIDE
    assert host in ADOPT_GUIDE
    assert prepare in ADOPT_GUIDE
    assert f"{host} **Optional**" not in ADOPT_GUIDE
    assert f"{prepare} **Optional**" not in ADOPT_GUIDE
    assert ADOPT_GUIDE.index(stage) < ADOPT_GUIDE.index(host) < ADOPT_GUIDE.index(prepare)
    section = ADOPT_GUIDE[
        ADOPT_GUIDE.index(stage) : ADOPT_GUIDE.index("### Stage 7a")
    ]
    assert "Skip it\nfor website-only work and on Windows ARM64" in section
    assert "pdk pdf --prepare all" in section
    assert "If you prefer lazy preparation" in section
    assert "`pdk pdf` prepares only the components used" in section
    assert "No npm packages, browser or MSYS2 installation is required" in section


def test_installation_sections_four_five_and_six_show_exact_pdf_commands() -> None:
    for guide in (ADOPT_GUIDE, GUIDE, MANUAL_GUIDE):
        assert "brew install pango node" in guide
        assert "winget install OpenJS.NodeJS.LTS" in guide
        assert "libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 nodejs" in guide
        assert "node --version" in guide
