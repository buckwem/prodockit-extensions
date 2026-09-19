# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Pinned project-local Inter and JetBrains Mono files for PDF rendering."""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_download import download_release_asset
from prodockit.pdf.runtime_prepare import RuntimeEnvironment, RuntimeProviderUnavailableError
from prodockit.pdf.runtime_store import (
    ArtifactDescriptor,
    RuntimeStoreError,
    sha256_file,
)

FONT_BUNDLE_VERSION = "4.1+2.304"
FONT_BUNDLE_SHA256 = "103fb116f21c8ada4893eb08a9ceedc6872507f48e59142d6adc7cb65b11953f"


@dataclass(frozen=True)
class FontSource:
    label: str
    url: str
    sha256: str
    size: int
    members: tuple[tuple[str, str], ...]


_INTER = FontSource(
    "Inter 4.1",
    "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip",
    "9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e",
    33_707_794,
    (
        ("extras/ttf/Inter-Regular.ttf", "fonts/Inter-Regular.ttf"),
        ("extras/ttf/Inter-Italic.ttf", "fonts/Inter-Italic.ttf"),
        ("extras/ttf/Inter-Bold.ttf", "fonts/Inter-Bold.ttf"),
        ("extras/ttf/Inter-BoldItalic.ttf", "fonts/Inter-BoldItalic.ttf"),
        ("LICENSE.txt", "licences/Inter-OFL.txt"),
    ),
)
_JETBRAINS_MONO = FontSource(
    "JetBrains Mono 2.304",
    "https://github.com/JetBrains/JetBrainsMono/releases/download/"
    "v2.304/JetBrainsMono-2.304.zip",
    "6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf",
    5_622_857,
    (
        ("fonts/ttf/JetBrainsMono-Regular.ttf", "fonts/JetBrainsMono-Regular.ttf"),
        ("fonts/ttf/JetBrainsMono-Italic.ttf", "fonts/JetBrainsMono-Italic.ttf"),
        ("fonts/ttf/JetBrainsMono-Bold.ttf", "fonts/JetBrainsMono-Bold.ttf"),
        ("fonts/ttf/JetBrainsMono-BoldItalic.ttf", "fonts/JetBrainsMono-BoldItalic.ttf"),
        ("OFL.txt", "licences/JetBrainsMono-OFL.txt"),
    ),
)
_SOURCES = (_INTER, _JETBRAINS_MONO)
_EXPECTED_PATHS = tuple(target for source in _SOURCES for _member, target in source.members)


def _reviewed_member(archive: zipfile.ZipFile, name: str, *, label: str) -> bytes:
    try:
        member = archive.getinfo(name)
    except KeyError as error:
        raise RuntimeStoreError(f"official {label} archive is missing {name}") from error
    if member.is_dir() or member.file_size > 16 * 1024 * 1024:
        raise RuntimeStoreError(f"official {label} archive has an invalid {name} entry")
    return archive.read(member)


def assemble_font_bundle(source_archives: tuple[Path, Path], destination: Path) -> None:
    """Create a stable uncompressed bundle containing only reviewed font files."""

    payloads: list[tuple[str, bytes]] = []
    for source, archive_path in zip(_SOURCES, source_archives, strict=True):
        if sha256_file(archive_path) != source.sha256:
            raise RuntimeStoreError(f"official {source.label} artifact failed SHA-256 validation")
        with zipfile.ZipFile(archive_path) as archive:
            for member, target in source.members:
                payloads.append((target, _reviewed_member(archive, member, label=source.label)))
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_STORED) as bundle:
        for target, payload in payloads:
            info = zipfile.ZipInfo(target, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, payload)


def _font_path(runtime: Path, name: str) -> Path:
    path = runtime / "fonts" / name
    if not path.is_file() or path.is_symlink():
        raise RuntimeStoreError(f"prepared font runtime is missing fonts/{name}")
    return path


def font_face_css(runtime: Path) -> str:
    """Return explicit local file rules so host font installation is irrelevant."""

    faces = (
        ("Inter", "Inter-Regular.ttf", "normal", "400"),
        ("Inter", "Inter-Italic.ttf", "italic", "400"),
        ("Inter", "Inter-Bold.ttf", "normal", "700"),
        ("Inter", "Inter-BoldItalic.ttf", "italic", "700"),
        ("JetBrains Mono", "JetBrainsMono-Regular.ttf", "normal", "400"),
        ("JetBrains Mono", "JetBrainsMono-Italic.ttf", "italic", "400"),
        ("JetBrains Mono", "JetBrainsMono-Bold.ttf", "normal", "700"),
        ("JetBrains Mono", "JetBrainsMono-BoldItalic.ttf", "italic", "700"),
    )
    rules = []
    for family, name, style, weight in faces:
        uri = _font_path(runtime, name).resolve().as_uri()
        rules.append(
            "@font-face {\n"
            f'    font-family: "{family}";\n'
            f'    src: url("{uri}") format("truetype");\n'
            f"    font-style: {style};\n"
            f"    font-weight: {weight};\n"
            "}"
        )
    return "\n\n".join(rules)


def probe_runtime(runtime: Path) -> str:
    for relative in _EXPECTED_PATHS:
        path = runtime / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeStoreError(f"prepared font runtime is missing {relative}")
        if relative.endswith(".ttf") and path.read_bytes()[:4] not in {
            b"\x00\x01\x00\x00",
            b"OTTO",
        }:
            raise RuntimeStoreError(f"prepared font runtime contains an invalid {relative}")
    css = font_face_css(runtime)
    if "Inter-Regular.ttf" not in css or "JetBrainsMono-Regular.ttf" not in css:
        raise RuntimeStoreError("prepared font runtime did not produce complete font CSS")
    return FONT_BUNDLE_VERSION


class FontProvider:
    """Acquire a deterministic bundle from two official OFL release archives."""

    def resolve(
        self, policy: ComponentPolicy, environment: RuntimeEnvironment
    ) -> ArtifactDescriptor:
        if policy.version not in {"supported", FONT_BUNDLE_VERSION}:
            raise RuntimeProviderUnavailableError(
                f"this release supports font bundle {FONT_BUNDLE_VERSION}; "
                f"pdk-pdf.toml requests {policy.version}"
            )
        return ArtifactDescriptor(
            component="fonts",
            version=FONT_BUNDLE_VERSION,
            source_url=" + ".join(source.url for source in _SOURCES),
            sha256=FONT_BUNDLE_SHA256,
            licence="OFL-1.1",
            provenance="official Inter 4.1 and JetBrains Mono 2.304 release archives",
            platform=environment.system,
            architecture=environment.architecture,
            environment_identity=environment.identity,
            archive_format="zip",
            expected_paths=_EXPECTED_PATHS,
        )

    def acquire(self, descriptor: ArtifactDescriptor, destination: Path) -> None:
        if descriptor.sha256 != FONT_BUNDLE_SHA256:
            raise RuntimeStoreError("refusing an unreviewed font bundle")
        with tempfile.TemporaryDirectory(prefix="prodockit-fonts-") as temporary:
            directory = Path(temporary)
            archives: list[Path] = []
            for index, source in enumerate(_SOURCES):
                archive = directory / f"{index}.zip"
                download_release_asset(
                    source.url,
                    archive,
                    expected_bytes=source.size,
                    label=source.label,
                )
                if sha256_file(archive) != source.sha256:
                    raise RuntimeStoreError(
                        f"official {source.label} artifact failed SHA-256 validation"
                    )
                archives.append(archive)
            assemble_font_bundle((archives[0], archives[1]), destination)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != FONT_BUNDLE_SHA256:
            destination.unlink(missing_ok=True)
            raise RuntimeStoreError("assembled font bundle did not match its reviewed digest")

    def probe(self, descriptor: ArtifactDescriptor, runtime: Path) -> None:
        if descriptor.version != FONT_BUNDLE_VERSION:
            raise RuntimeStoreError("refusing to probe an unsupported font runtime")
        probe_runtime(runtime)


__all__ = [
    "FONT_BUNDLE_SHA256",
    "FONT_BUNDLE_VERSION",
    "FontProvider",
    "assemble_font_bundle",
    "font_face_css",
    "probe_runtime",
]
