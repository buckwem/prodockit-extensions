# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Qualified project-local Pandoc runtime for PDF and bibliography work."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_download import download_release_asset
from prodockit.pdf.runtime_prepare import (
    RuntimeEnvironment,
    RuntimeProviderUnavailableError,
)
from prodockit.pdf.runtime_store import ArtifactDescriptor, RuntimeStoreError

PANDOC_VERSION = "3.10.1"
_PROBE_TIMEOUT = 120.0


@dataclass(frozen=True)
class PandocAsset:
    filename: str
    sha256: str
    size: int
    archive_format: str
    executable: Path
    ignored_links: tuple[Path, ...] = ()

    @property
    def url(self) -> str:
        return f"https://github.com/jgm/pandoc/releases/download/{PANDOC_VERSION}/{self.filename}"


_ASSETS = {
    ("darwin", "arm64"): PandocAsset(
        "pandoc-3.10.1-arm64-macOS.zip",
        "8607160694a70ed9aa63776caa44acef3afb729c379c7c283724b7e27455bfda",
        41_741_911,
        "zip",
        Path("pandoc-3.10.1-arm64/bin/pandoc"),
        (
            Path("pandoc-3.10.1-arm64/bin/pandoc-lua"),
            Path("pandoc-3.10.1-arm64/bin/pandoc-server"),
        ),
    ),
    ("darwin", "x86_64"): PandocAsset(
        "pandoc-3.10.1-x86_64-macOS.zip",
        "76430dd0ce5305fc4b91d8c0d5c22a00c8d2197ad3cef3937f65048f087164f7",
        26_096_585,
        "zip",
        Path("pandoc-3.10.1-x86_64/bin/pandoc"),
        (
            Path("pandoc-3.10.1-x86_64/bin/pandoc-lua"),
            Path("pandoc-3.10.1-x86_64/bin/pandoc-server"),
        ),
    ),
    ("linux", "aarch64"): PandocAsset(
        "pandoc-3.10.1-linux-arm64.tar.gz",
        "cd3963da375793a4804c65ae538b4f7b9c23f87cac7f6c74a1cf5e2fff7e8d59",
        37_328_794,
        "tar",
        Path("pandoc-3.10.1/bin/pandoc"),
        (Path("pandoc-3.10.1/bin/pandoc-lua"), Path("pandoc-3.10.1/bin/pandoc-server")),
    ),
    ("linux", "arm64"): PandocAsset(
        "pandoc-3.10.1-linux-arm64.tar.gz",
        "cd3963da375793a4804c65ae538b4f7b9c23f87cac7f6c74a1cf5e2fff7e8d59",
        37_328_794,
        "tar",
        Path("pandoc-3.10.1/bin/pandoc"),
        (Path("pandoc-3.10.1/bin/pandoc-lua"), Path("pandoc-3.10.1/bin/pandoc-server")),
    ),
    ("linux", "amd64"): PandocAsset(
        "pandoc-3.10.1-linux-amd64.tar.gz",
        "72948bf5784f560d5ad1876709daca27e0667f262da727bb33f77b58e52df2f5",
        34_873_851,
        "tar",
        Path("pandoc-3.10.1/bin/pandoc"),
        (Path("pandoc-3.10.1/bin/pandoc-lua"), Path("pandoc-3.10.1/bin/pandoc-server")),
    ),
    ("linux", "x86_64"): PandocAsset(
        "pandoc-3.10.1-linux-amd64.tar.gz",
        "72948bf5784f560d5ad1876709daca27e0667f262da727bb33f77b58e52df2f5",
        34_873_851,
        "tar",
        Path("pandoc-3.10.1/bin/pandoc"),
        (Path("pandoc-3.10.1/bin/pandoc-lua"), Path("pandoc-3.10.1/bin/pandoc-server")),
    ),
    ("windows", "amd64"): PandocAsset(
        "pandoc-3.10.1-windows-x86_64.zip",
        "4725a1883e2171c2e181e6fd45003acb59ca4e9cbe031fdd3b79ef0d697d36aa",
        41_675_076,
        "zip",
        Path("pandoc-3.10.1/pandoc.exe"),
    ),
    ("windows", "x86_64"): PandocAsset(
        "pandoc-3.10.1-windows-x86_64.zip",
        "4725a1883e2171c2e181e6fd45003acb59ca4e9cbe031fdd3b79ef0d697d36aa",
        41_675_076,
        "zip",
        Path("pandoc-3.10.1/pandoc.exe"),
    ),
}


def _asset_for(environment: RuntimeEnvironment) -> PandocAsset:
    try:
        return _ASSETS[(environment.system, environment.architecture)]
    except KeyError as error:
        raise RuntimeProviderUnavailableError(
            "the project-local Pandoc runtime has no qualified artifact for "
            f"{environment.system} {environment.architecture}"
        ) from error


def executable_in_runtime(
    runtime: Path,
    environment: RuntimeEnvironment,
) -> Path:
    executable = runtime / _asset_for(environment).executable
    if not executable.is_file() or executable.is_symlink():
        raise RuntimeStoreError(
            "prepared Pandoc runtime is missing "
            f"{_asset_for(environment).executable.as_posix()}"
        )
    return executable


def probe_runtime(
    runtime: Path,
    environment: RuntimeEnvironment,
    *,
    runner: Any = subprocess.run,
) -> str:
    """Verify the absolute CLI and its built-in citeproc implementation."""

    executable = executable_in_runtime(runtime, environment)
    try:
        version = runner(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeStoreError(f"could not start prepared Pandoc: {error}") from error
    output = "\n".join(part.strip() for part in (version.stdout, version.stderr) if part.strip())
    if version.returncode or f"pandoc {PANDOC_VERSION}" not in output.lower():
        raise RuntimeStoreError(
            "prepared Pandoc returned an unexpected version result: "
            + (output or f"exit status {version.returncode}")
        )

    with tempfile.TemporaryDirectory(prefix="prodockit-pandoc-probe-") as temporary:
        bibliography = Path(temporary) / "probe.bib"
        bibliography.write_text(
            "@book{probe, title={Runtime Probe}, author={Example, Ada}, year={2026}}\n",
            encoding="utf-8",
        )
        try:
            citeproc = runner(
                [
                    str(executable),
                    "-f",
                    "markdown",
                    "-t",
                    "html",
                    "--citeproc",
                    f"--bibliography={bibliography}",
                ],
                input="[@probe]",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_PROBE_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeStoreError(f"prepared Pandoc citeproc failed: {error}") from error
    if citeproc.returncode or "Runtime Probe" not in citeproc.stdout:
        detail = "\n".join(
            part.strip() for part in (citeproc.stdout, citeproc.stderr) if part.strip()
        )
        raise RuntimeStoreError(
            "prepared Pandoc citeproc failed: "
            + (detail or f"exit status {citeproc.returncode}")
        )
    return PANDOC_VERSION


class PandocProvider:
    """Resolve and verify official Pandoc archives on supported hosts."""

    def resolve(
        self, policy: ComponentPolicy, environment: RuntimeEnvironment
    ) -> ArtifactDescriptor:
        if policy.version not in {"supported", PANDOC_VERSION}:
            raise RuntimeProviderUnavailableError(
                f"this release supports Pandoc {PANDOC_VERSION}; "
                f"pdk-pdf.toml requests {policy.version}"
            )
        asset = _asset_for(environment)
        return ArtifactDescriptor(
            component="pandoc",
            version=PANDOC_VERSION,
            source_url=asset.url,
            sha256=asset.sha256,
            licence="GPL-2.0-or-later",
            provenance="official jgm/pandoc 3.10.1 release archive",
            platform=environment.system,
            architecture=environment.architecture,
            environment_identity=environment.identity,
            archive_format=asset.archive_format,
            expected_paths=(asset.executable.as_posix(),),
            ignored_link_paths=tuple(path.as_posix() for path in asset.ignored_links),
        )

    def acquire(self, descriptor: ArtifactDescriptor, destination: Path) -> None:
        asset = next((item for item in _ASSETS.values() if item.url == descriptor.source_url), None)
        if asset is None or descriptor.sha256 != asset.sha256:
            raise RuntimeStoreError("refusing an unreviewed Pandoc artifact")
        download_release_asset(
            asset.url,
            destination,
            expected_bytes=asset.size,
            label="Pandoc",
        )

    def probe(self, descriptor: ArtifactDescriptor, runtime: Path) -> None:
        if descriptor.version != PANDOC_VERSION:
            raise RuntimeStoreError("refusing to probe an unsupported Pandoc runtime")
        environment = RuntimeEnvironment(*descriptor.environment_identity.split(":"))
        probe_runtime(runtime, environment)


__all__ = [
    "PANDOC_VERSION",
    "PandocAsset",
    "PandocProvider",
    "executable_in_runtime",
    "probe_runtime",
]
