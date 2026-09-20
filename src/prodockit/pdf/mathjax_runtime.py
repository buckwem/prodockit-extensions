# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Qualified project-local MathJax 4 runtime for PDF mathematics."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_download import download_release_asset
from prodockit.pdf.runtime_prepare import (
    RuntimeEnvironment,
    RuntimeProviderUnavailableError,
)
from prodockit.pdf.runtime_store import ArtifactDescriptor, RuntimeStoreError

MATHJAX_VERSION = "4.1.3"
MATHJAX_COMMIT = "0bfa580685ca72e4a3a37657ccd754a65c1a42c6"
MATHJAX_ARCHIVE_URL = (
    "https://codeload.github.com/mathjax/MathJax/zip/"
    f"{MATHJAX_COMMIT}"
)
MATHJAX_ARCHIVE_SHA256 = (
    "3ea993475f19e8a37d93422745bbf424fae3fa9fcec4e9bb4fdede9a7e173759"
)
MATHJAX_ARCHIVE_BYTES = 5_314_798
MATHJAX_DIRECTORY = Path(f"MathJax-{MATHJAX_COMMIT}")
MATHJAX_COMPONENT = MATHJAX_DIRECTORY / "tex-svg.js"
MATHJAX_LICENCE = MATHJAX_DIRECTORY / "LICENSE"
MATHJAX_ADAPTER = Path(__file__).with_name("tex2svg.cjs")
_PROBE_TIMEOUT = 60.0


def component_root(runtime: Path) -> Path:
    """Return the verified MathJax component directory in ``runtime``."""

    root = runtime / MATHJAX_DIRECTORY
    component = runtime / MATHJAX_COMPONENT
    licence = runtime / MATHJAX_LICENCE
    if (
        not root.is_dir()
        or root.is_symlink()
        or not component.is_file()
        or component.is_symlink()
        or not licence.is_file()
        or licence.is_symlink()
    ):
        raise RuntimeStoreError("prepared MathJax runtime is incomplete")
    return root


def adapter_path() -> Path:
    """Return the packaged promise-based MathJax 4 Node adapter."""

    if not MATHJAX_ADAPTER.is_file() or MATHJAX_ADAPTER.is_symlink():
        raise RuntimeStoreError("the packaged MathJax adapter is unavailable")
    return MATHJAX_ADAPTER


def probe_runtime(
    runtime: Path,
    *,
    runner: Any = subprocess.run,
    node: str | None = None,
) -> str:
    """Exercise inline and display TeX through the cached component."""

    executable = node or shutil.which("node")
    if not executable:
        raise RuntimeStoreError(
            "MathJax PDF rendering needs Node.js on PATH to run its transitional SVG "
            "adapter. pdk boot and pdk adopt do not install this optional host "
            "prerequisite. Install Node.js with `brew install node` on macOS, "
            "`winget install OpenJS.NodeJS.LTS` on Windows (then reopen the shell), "
            "or `sudo apt update && sudo apt install -y nodejs` on Ubuntu. Verify "
            "with `node --version`, then retry `pdk pdf --prepare mathjax` or "
            "`pdk pdf --prepare all`. If the PDF has no maths, do not force MathJax: "
            "use ordinary `pdk pdf` or prepare only Mermaid. No npm packages, "
            "node_modules, browser, or MSYS2 are required."
        )
    root = component_root(runtime)
    adapter = adapter_path()
    for mode, source in (
        ("inline", r"x^2 + \alpha"),
        ("display", r"\frac{1}{x^2-1}"),
    ):
        try:
            result = runner(
                [executable, str(adapter), str(root), mode],
                input=source,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_PROBE_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeStoreError(f"could not start prepared MathJax: {error}") from error
        if result.returncode or "<svg" not in result.stdout or "</svg>" not in result.stdout:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeStoreError(
                "prepared MathJax failed its TeX-to-SVG probe: "
                + (detail or f"exit status {result.returncode}")
            )
    return MATHJAX_VERSION


class MathJaxProvider:
    """Resolve and verify the official prebuilt MathJax 4 distribution."""

    def resolve(
        self, policy: ComponentPolicy, environment: RuntimeEnvironment
    ) -> ArtifactDescriptor:
        if policy.version not in {"latest", "supported", MATHJAX_VERSION}:
            raise RuntimeProviderUnavailableError(
                f"this release supports MathJax {MATHJAX_VERSION}; "
                f"pdk-pdf.toml requests {policy.version}"
            )
        return ArtifactDescriptor(
            component="mathjax",
            version=MATHJAX_VERSION,
            source_url=MATHJAX_ARCHIVE_URL,
            sha256=MATHJAX_ARCHIVE_SHA256,
            licence="Apache-2.0",
            provenance=(
                "official mathjax/MathJax 4.1.3 prebuilt distribution at commit "
                f"{MATHJAX_COMMIT}"
            ),
            platform=environment.system,
            architecture=environment.architecture,
            environment_identity=environment.identity,
            archive_format="zip",
            expected_paths=(
                MATHJAX_COMPONENT.as_posix(),
                MATHJAX_LICENCE.as_posix(),
                (MATHJAX_DIRECTORY / "adaptors/liteDOM.js").as_posix(),
                (MATHJAX_DIRECTORY / "sre/require.mjs").as_posix(),
            ),
        )

    def acquire(self, descriptor: ArtifactDescriptor, destination: Path) -> None:
        if (
            descriptor.source_url != MATHJAX_ARCHIVE_URL
            or descriptor.sha256 != MATHJAX_ARCHIVE_SHA256
        ):
            raise RuntimeStoreError("refusing an unreviewed MathJax artifact")
        download_release_asset(
            descriptor.source_url,
            destination,
            expected_bytes=MATHJAX_ARCHIVE_BYTES,
            label="MathJax",
        )

    def probe(self, descriptor: ArtifactDescriptor, runtime: Path) -> None:
        if descriptor.version != MATHJAX_VERSION:
            raise RuntimeStoreError("refusing to probe an unsupported MathJax runtime")
        probe_runtime(runtime)


__all__ = [
    "MATHJAX_ADAPTER",
    "MATHJAX_ARCHIVE_BYTES",
    "MATHJAX_ARCHIVE_SHA256",
    "MATHJAX_ARCHIVE_URL",
    "MATHJAX_COMMIT",
    "MATHJAX_COMPONENT",
    "MATHJAX_VERSION",
    "MathJaxProvider",
    "adapter_path",
    "component_root",
    "probe_runtime",
]
