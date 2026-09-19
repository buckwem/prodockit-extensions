# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from prodockit.pdf import font_runtime as runtime
from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_prepare import RuntimeEnvironment, RuntimeProviderUnavailableError


def test_provider_records_both_reviewed_upstream_archives() -> None:
    environment = RuntimeEnvironment("windows", "amd64", "cpython", "3.14")

    descriptor = runtime.FontProvider().resolve(ComponentPolicy("supported"), environment)

    assert descriptor.version == "4.1+2.304"
    assert descriptor.sha256 == runtime.FONT_BUNDLE_SHA256
    assert "rsms/inter" in descriptor.source_url
    assert "JetBrains/JetBrainsMono" in descriptor.source_url
    assert descriptor.licence == "OFL-1.1"
    assert len(descriptor.expected_paths) == 10


def test_provider_rejects_an_unqualified_bundle_version() -> None:
    environment = RuntimeEnvironment("linux", "x86_64", "cpython", "3.14")

    with pytest.raises(RuntimeProviderUnavailableError, match="supports font bundle"):
        runtime.FontProvider().resolve(ComponentPolicy("4.0"), environment)


def _font_archive(path: Path, source: runtime.FontSource, marker: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for member, _target in source.members:
            archive.writestr(member, marker if member.endswith(".ttf") else b"OFL")


def test_bundle_is_deterministic_and_css_uses_absolute_file_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inter = runtime.FontSource(
        "Inter fixture",
        "https://github.com/example/inter.zip",
        "",
        0,
        (("Inter.ttf", "fonts/Inter-Regular.ttf"), ("OFL.txt", "licences/Inter-OFL.txt")),
    )
    mono = runtime.FontSource(
        "Mono fixture",
        "https://github.com/example/mono.zip",
        "",
        0,
        (
            ("Regular.ttf", "fonts/JetBrainsMono-Regular.ttf"),
            ("OFL.txt", "licences/JetBrainsMono-OFL.txt"),
        ),
    )
    first = tmp_path / "inter.zip"
    second = tmp_path / "mono.zip"
    _font_archive(first, inter, b"\x00\x01\x00\x00inter")
    _font_archive(second, mono, b"\x00\x01\x00\x00mono")
    inter = runtime.FontSource(**{**inter.__dict__, "sha256": hashlib.sha256(first.read_bytes()).hexdigest()})
    mono = runtime.FontSource(**{**mono.__dict__, "sha256": hashlib.sha256(second.read_bytes()).hexdigest()})
    monkeypatch.setattr(runtime, "_SOURCES", (inter, mono))

    one = tmp_path / "one.zip"
    two = tmp_path / "two.zip"
    runtime.assemble_font_bundle((first, second), one)
    runtime.assemble_font_bundle((first, second), two)

    assert one.read_bytes() == two.read_bytes()


def test_font_face_css_binds_all_styles_to_project_files(tmp_path: Path) -> None:
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    for name in (
        "Inter-Regular.ttf",
        "Inter-Italic.ttf",
        "Inter-Bold.ttf",
        "Inter-BoldItalic.ttf",
        "JetBrainsMono-Regular.ttf",
        "JetBrainsMono-Italic.ttf",
        "JetBrainsMono-Bold.ttf",
        "JetBrainsMono-BoldItalic.ttf",
    ):
        (fonts / name).write_bytes(b"\x00\x01\x00\x00fixture")

    css = runtime.font_face_css(tmp_path)

    assert css.count("@font-face") == 8
    assert 'font-family: "Inter"' in css
    assert 'font-family: "JetBrains Mono"' in css
    assert "font-weight: 700" in css
    assert fonts.resolve().as_uri() in css

