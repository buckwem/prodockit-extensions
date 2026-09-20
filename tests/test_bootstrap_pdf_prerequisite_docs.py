# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = (ROOT / "docs/devcons/bootstrap.md").read_text(encoding="utf-8")


def test_template_site_installation_has_a_pdf_software_step() -> None:
    heading = "//// step | Install optional PDF software"
    assert heading in GUIDE
    assert GUIDE.index(heading) < GUIDE.index("//// step | Run project diagnostics")
    assert "Skip this step for a website-only project" in GUIDE


def test_template_site_pdf_step_covers_supported_host_prerequisites() -> None:
    for command in (
        "brew install pango",
        "libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0",
        "brew install node",
        "winget install OpenJS.NodeJS.LTS",
        "sudo apt install -y nodejs",
        "node --version",
        "pdk pdf --prepare all",
    ):
        assert command in GUIDE


def test_template_site_pdf_step_distinguishes_forced_and_lazy_preparation() -> None:
    assert "force every optional component with `--prepare all`" in GUIDE
    assert "Ordinary `pdk pdf` is the simpler default" in GUIDE
    assert "prepares only components found" in GUIDE
    assert "no Node.js, npm,\nbrowser or MSYS2" in GUIDE
