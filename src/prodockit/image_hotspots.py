# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Render an image-hotspots SuperFences block as an image and ordinary links."""

from __future__ import annotations

import math
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

import yaml
from markdown import Markdown
from PIL import Image
from pymdownx.superfences import SuperFencesException

from prodockit._zensical import page_source
from prodockit._zensical_page_context import ZensicalPageContextAPIError, current_docs_dir


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _url(value: object, field: str) -> str:
    url = _text(value, field)
    if re.search(r"[\\\x00-\x20\x7f]", url):
        raise ValueError(f"{field} contains whitespace, a backslash or a control character")
    parts = urlsplit(url)
    if (parts.scheme and (parts.scheme not in {"http", "https"} or not parts.hostname)) or (
        not parts.scheme and (url.startswith("/") or parts.netloc)
    ):
        raise ValueError(f"{field} must be a relative URL, fragment or HTTP(S) URL")
    return url


def _dimensions(image: str, source: str, docs: Path) -> tuple[int, int]:
    parts = urlsplit(image)
    if not parts.path or parts.scheme or parts.query or parts.fragment:
        raise ValueError("image must be a page-relative path to a local raster image")
    page = Path(source)
    if not page.is_absolute():
        page = docs / page
    path = (page.parent / unquote(parts.path)).resolve()
    if not path.is_relative_to(docs):
        raise ValueError("image must be inside the documentation directory")
    try:
        with Image.open(path) as raster:
            return raster.size
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError(f"cannot read dimensions of raster image {image!r}: {error}") from error


def _position(rect: object, width: int, height: int) -> str:
    if (
        not isinstance(rect, list)
        or len(rect) != 4
        or any(type(value) not in (int, float) for value in rect)
    ):
        raise ValueError("rect must contain four numbers [left, top, width, height]")
    left, top, span_x, span_y = rect
    if not (
        0 <= left < width
        and 0 <= top < height
        and 0 < span_x <= width - left
        and 0 < span_y <= height - top
        and all(math.isfinite(value) for value in rect)
    ):
        raise ValueError("rect must have positive dimensions and fit inside the source image")
    return (
        f"left:{left / width:.10%};top:{top / height:.10%};"
        f"width:{span_x / width:.10%};height:{span_y / height:.10%}"
    )


def _render(src: str, source: str, docs: Path) -> str:
    data = yaml.safe_load(src)
    if not isinstance(data, dict):
        raise ValueError("expected a mapping with image, alt and hotspots")
    image = _url(data.get("image"), "image")
    alt = _text(data.get("alt"), "alt")
    hotspots = data.get("hotspots")
    if not isinstance(hotspots, list) or not hotspots:
        raise ValueError("hotspots must be a non-empty list")
    width, height = _dimensions(image, source, docs)

    figure = ET.Element("figure", {"class": "pdk-hotspots"})
    canvas = ET.SubElement(figure, "div", {"class": "pdk-hotspots-image"})
    ET.SubElement(
        canvas,
        "img",
        {
            "src": image,
            "alt": alt,
            "class": "off-glb",
            "width": str(width),
            "height": str(height),
        },
    )
    link_group = ET.SubElement(figure, "div", {"class": "pdk-hotspots-links"})
    links = ET.SubElement(link_group, "ul")
    for index, entry in enumerate(hotspots, start=1):
        try:
            if not isinstance(entry, dict):
                raise ValueError("expected a mapping with label, href and rect")
            label = _text(entry.get("label"), "label")
            href = _url(entry.get("href"), "href")
            style = _position(entry.get("rect"), width, height)
        except ValueError as error:
            raise ValueError(f"hotspot {index}: {error}") from error
        ET.SubElement(
            canvas,
            "a",
            {
                "href": href,
                "aria-label": label,
                "style": style,
                "class": "pdk-hotspots-region web-only",
            },
        )
        ET.SubElement(ET.SubElement(links, "li"), "a", {"href": href}).text = label
    return ET.tostring(figure, encoding="unicode", method="html")


def format_hotspots(
    src: str,
    language: str,
    class_name: str,
    options: dict[str, object],
    md: Markdown,
    **kwargs: object,
) -> str:
    """SuperFences formatter configured under pymdownx.superfences."""
    source = page_source(md)
    try:
        if source is None:
            raise ValueError("a Zensical page context is required to resolve the source image")
        return _render(src, source, current_docs_dir(md))
    except (ValueError, yaml.YAMLError, ZensicalPageContextAPIError) as error:
        # SuperFences otherwise swallows formatter errors and renders a code block.
        raise SuperFencesException(f"{source or '<markdown>'}: image-hotspots: {error}") from error
