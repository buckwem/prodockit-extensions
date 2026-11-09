# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import subprocess
import sys

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from prodockit.image_hotspots import _render

_BLOCK = """image: ../assets/test.png
alt: Test map
hotspots:
  - {label: 'First & second', href: '#first', rect: [20, 10, 40, 30]}
  - {label: 'Other page', href: '../other.md#section', rect: [100, 50, 20, 10]}
  - {label: 'External', href: 'https://example.com/', rect: [190, 90, 10, 10]}
"""


@pytest.fixture
def project(tmp_path):
    (tmp_path / "zensical.toml").write_text(
        """[project]
site_name = "Hotspot test"
site_url = "https://example.com/subpath/"
[project.markdown_extensions.pymdownx.superfences]
custom_fences = [
    {name = "image-hotspots", class = "image-hotspots", format = "prodockit.image_hotspots.format_hotspots"},
]
[project.markdown_extensions.zensical.extensions.glightbox]
""",
        encoding="utf-8",
    )
    (tmp_path / "docs/assets").mkdir(parents=True)
    (tmp_path / "docs/guide").mkdir()
    Image.new("RGB", (200, 100)).save(tmp_path / "docs/assets/test.png")
    return tmp_path


def test_zensical_resolves_image_and_links(project):
    (project / "docs/guide/demo.md").write_text(
        f"# Demo\n\n```image-hotspots\n{_BLOCK}```\n\n## First\n", encoding="utf-8"
    )
    (project / "docs/other.md").write_text("# Other\n\n## Section\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "zensical",
            "build",
            "-f",
            str(project / "zensical.toml"),
            "--clean",
            "--strict",
        ],
        cwd=project.parent,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    soup = BeautifulSoup(
        (project / "site/guide/demo/index.html").read_text(encoding="utf-8"), "html.parser"
    )
    figure = soup.select_one("figure.pdk-hotspots")
    assert figure is not None
    image = figure.select_one(".pdk-hotspots-image > img")
    assert image is not None
    assert image["src"] == "../../assets/test.png"
    assert image["alt"] == "Test map"
    regions = figure.select(".pdk-hotspots-region")
    assert [link["href"] for link in regions] == [
        "#first",
        "../../other/#section",
        "https://example.com/",
    ]
    assert [link["aria-label"] for link in regions] == ["First & second", "Other page", "External"]
    assert figure.select("a") == regions
    assert regions[0]["style"] == (
        "left:10.0000000000%;top:10.0000000000%;width:20.0000000000%;height:30.0000000000%"
    )
    assert "web-only" not in regions[0]["class"]


@pytest.mark.parametrize(
    "rect",
    ["[0, 0, 0, 1]", "[-1, 0, 1, 1]", "[199, 0, 2, 1]", "[0, .nan, 1, 1]", "[0, 0, true, 1]"],
)
def test_rejects_invalid_rectangles(project, rect):
    with pytest.raises(ValueError, match="hotspot 1: rect"):
        _render(_BLOCK.replace("[20, 10, 40, 30]", rect), "guide/demo.md", project / "docs")


@pytest.mark.parametrize(
    "href", ["javascript:alert(1)", "data:text/html,hi", "//example.com", r"\evil"]
)
def test_rejects_unsafe_destinations(project, href):
    with pytest.raises(ValueError, match="hotspot 1: href"):
        _render(_BLOCK.replace("#first", href), "guide/demo.md", project / "docs")


def test_rejects_images_outside_docs(project):
    Image.new("RGB", (200, 100)).save(project / "private.png")
    with pytest.raises(ValueError, match="inside the documentation directory"):
        _render(
            _BLOCK.replace("../assets/test.png", "../../private.png"),
            "guide/demo.md",
            project / "docs",
        )
