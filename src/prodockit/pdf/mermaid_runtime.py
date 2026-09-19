# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Reviewed project-local Python runtime for Mermaid PDF rendering.

The base Prodockit wheel deliberately does not import these packages.  This
provider downloads four exact PyPI wheels, verifies each one, and combines
their installed files into one deterministic archive for RuntimeStore.  Only
the short-lived Mermaid worker adds that archive's ``site-packages`` directory
to ``sys.path``.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_download import download_release_asset
from prodockit.pdf.runtime_prepare import RuntimeEnvironment, RuntimeProviderUnavailableError
from prodockit.pdf.runtime_store import ArtifactDescriptor, RuntimeStoreError, sha256_file

MERMAID_RUNTIME_VERSION = "0.9.5"
SITE_PACKAGES = Path("site-packages")
_PROBE_TIMEOUT = 60.0
_FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class _Wheel:
    filename: str
    url: str
    sha256: str
    size: int


_MERMAIDX = _Wheel(
    "mermaidx-0.9.5-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/7a/62/39480a6aa506aa756021802eedde019f70aa3a15525f377708f705aa5fc8/mermaidx-0.9.5-py3-none-any.whl",
    "46dfbdc7c101bd5395f05bca2f0917c467b9c5d5c3cbec1fbe238c546b673039",
    1_776_497,
)
_TERMAID = _Wheel(
    "termaid-0.9.0-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/42/7b/ecd6564a681a84cd9000f028752c1b9226c15df2d992af2af19ab3439dee/termaid-0.9.0-py3-none-any.whl",
    "793287486983d1be8cc6bb826340206af0a07676b8c25c0683ef3afe9870ac9d",
    166_741,
)

_PLATFORM_WHEELS: dict[str, tuple[_Wheel, _Wheel]] = {
    "darwin-arm64": (
        _Wheel(
            "quickjs_ng-0.16.2.1-cp310-abi3-macosx_11_0_arm64.whl",
            "https://files.pythonhosted.org/packages/de/e1/e91954cfb83e8a0b4a064a50df4395394722cbfc090f6e98a126a3b029c5/quickjs_ng-0.16.2.1-cp310-abi3-macosx_11_0_arm64.whl",
            "5edf6aeb394d270ca7193279251a8b3e7e68577aed9f2ede7406a676056d6ffc",
            531_728,
        ),
        _Wheel(
            "resvg_py-0.5.0-cp310-abi3-macosx_11_0_arm64.whl",
            "https://files.pythonhosted.org/packages/74/bf/4083b177388125e5ce2ab9fa4cd9efd881fa133dd97e5b2d4ca68e543256/resvg_py-0.5.0-cp310-abi3-macosx_11_0_arm64.whl",
            "7b43f942157f5d16126e108dab8ab37e4bc2b198099e5f6274b753a3b1ac7b6e",
            1_216_814,
        ),
    ),
    "linux-aarch64": (
        _Wheel(
            "quickjs_ng-0.16.2.1-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl",
            "https://files.pythonhosted.org/packages/21/16/ed077e854cf64fc8eb76a81a9107765e65b042b31984f333ffec2bd8e1e0/quickjs_ng-0.16.2.1-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl",
            "7446efb6134226d4d10236363c0b308a877613214ff2d798e4e270a8f22e579d",
            2_459_036,
        ),
        _Wheel(
            "resvg_py-0.5.0-cp310-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
            "https://files.pythonhosted.org/packages/52/92/1dfd0d7b5f8dbb16f9c889bba0d7477ab514d1f2a81a5f904662215103bc/resvg_py-0.5.0-cp310-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
            "1e66216f78c84a27d34ce75f4535d8e26565771be4f1848ddc71e8a7ce78973a",
            1_414_542,
        ),
    ),
    "linux-x86_64": (
        _Wheel(
            "quickjs_ng-0.16.2.1-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
            "https://files.pythonhosted.org/packages/65/52/c124d48efaf9d1f5b706c2d8366d6fb010873d8f447295f1c604825e5393/quickjs_ng-0.16.2.1-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
            "780bc24ba5f26b9dc6f9c737de9db8f9787c6a0ab72f91e0f778623fefce2d4d",
            2_537_370,
        ),
        _Wheel(
            "resvg_py-0.5.0-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
            "https://files.pythonhosted.org/packages/9e/08/217f2289ceb16a4eafd9c9c6f69aa3221ef047a6abe4ff1ce5c8d6be87d8/resvg_py-0.5.0-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
            "84f2378ecc7a8e38b03429efaefc816daec1b1970114909a6f973393b297c91b",
            1_405_807,
        ),
    ),
    "windows-x86_64": (
        _Wheel(
            "quickjs_ng-0.16.2.1-cp310-abi3-win_amd64.whl",
            "https://files.pythonhosted.org/packages/57/f7/1b02fd4e531f31cdbe5fb2418b0b25587d3b721137fa9c7e457a003fd2d8/quickjs_ng-0.16.2.1-cp310-abi3-win_amd64.whl",
            "7dd5f9fd78917c4c444c52eb2029f51610487bc219f5ca1b2766bcbd98b8afc3",
            521_986,
        ),
        _Wheel(
            "resvg_py-0.5.0-cp310-abi3-win_amd64.whl",
            "https://files.pythonhosted.org/packages/fe/53/aa8f92ce6eb2f97095d8b6359a1613c5a5ee0aa9b1a33434df9294362979/resvg_py-0.5.0-cp310-abi3-win_amd64.whl",
            "1f6b8956c4143dbfe107bcd35799d0dfd778a40a8cd537893c0bf489898a6c3c",
            1_242_277,
        ),
    ),
}

# SHA-256 of the deterministic composite made by _build_runtime_archive.
_RUNTIME_SHA256 = {
    "darwin-arm64": "dd2a6e52c5de848b3273ff2b45b8aee90d39ac373dcba57d2dcefe7245edd89b",
    "linux-aarch64": "ea1c530fe692940b27d50f4367deb3d9c41b3bf363557fc4c538fda1b5556972",
    "linux-x86_64": "d88898ea1c904519f6556119e8e7a7df732c5a469fb1c70ecf65323f64f367a6",
    "windows-x86_64": "178bc56445a38cccdaf64787662408a28826a654d9dbbef940c0188910ac9063",
}


def _platform_key(environment: RuntimeEnvironment) -> str:
    system = environment.system.lower()
    architecture = environment.architecture.lower()
    architecture = {"amd64": "x86_64", "arm64": "arm64" if system == "darwin" else "aarch64"}.get(
        architecture, architecture
    )
    return f"{system}-{architecture}"


def _wheels_for(key: str) -> tuple[_Wheel, ...]:
    try:
        native = _PLATFORM_WHEELS[key]
    except KeyError as error:
        supported = ", ".join(sorted(_PLATFORM_WHEELS))
        raise RuntimeProviderUnavailableError(
            f"Mermaid PDF rendering is unavailable for {key}; supported hosts: {supported}"
        ) from error
    return (_MERMAIDX, _TERMAID, *native)


def _safe_wheel_member(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\0" in name:
        raise RuntimeStoreError(f"unsafe Mermaid wheel path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        raise RuntimeStoreError(f"unsafe Mermaid wheel path: {name!r}")
    if path.suffix == ".pth":
        raise RuntimeStoreError(f"refusing executable Python path hook in Mermaid wheel: {name}")
    return path


def _build_runtime_archive(wheels: tuple[Path, ...], destination: Path) -> None:
    """Merge exact wheel payloads into a reproducible, inert ZIP archive."""

    members: dict[str, tuple[str, bytes, int]] = {}
    for wheel in wheels:
        try:
            with zipfile.ZipFile(wheel) as bundle:
                for info in bundle.infolist():
                    if info.is_dir():
                        continue
                    path = _safe_wheel_member(info.filename)
                    mode = info.external_attr >> 16
                    kind = stat.S_IFMT(mode)
                    if stat.S_ISLNK(mode) or (kind and kind != stat.S_IFREG):
                        raise RuntimeStoreError(
                            f"refusing special file in Mermaid wheel: {info.filename}"
                        )
                    target = (SITE_PACKAGES / path).as_posix()
                    folded = target.casefold()
                    if folded in members:
                        raise RuntimeStoreError(f"duplicate Mermaid runtime path: {target}")
                    members[folded] = (target, bundle.read(info), mode & 0o111)
        except (OSError, zipfile.BadZipFile) as error:
            raise RuntimeStoreError(
                f"cannot inspect reviewed Mermaid wheel {wheel.name}: {error}"
            ) from error

    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_STORED) as output:
        for folded in sorted(members):
            target, data, executable = members[folded]
            info = zipfile.ZipInfo(target, _FIXED_ZIP_TIME)
            info.create_system = 3
            info.external_attr = ((0o100644 | executable) << 16)
            output.writestr(info, data)


def runtime_site_packages(runtime: Path) -> Path:
    path = runtime / SITE_PACKAGES
    expected = (
        path / "mermaidx" / "assets" / "mermaid.js",
        path / "quickjs" / "__init__.py",
        path / "termaid" / "__init__.py",
        path / "resvg_py" / "__init__.py",
    )
    if path.is_symlink() or not path.is_dir() or any(
        item.is_symlink() or not item.is_file() for item in expected
    ):
        raise RuntimeStoreError("prepared Mermaid runtime is incomplete")
    return path


def probe_runtime(runtime: Path, *, runner: Any = subprocess.run) -> None:
    site_packages = runtime_site_packages(runtime)
    code = (
        "from prodockit.pdf._standalone_quickjs import StandaloneQuickJSMermaidEngine;"
        "e=StandaloneQuickJSMermaidEngine();e.start();"
        "s=e.render_svg('graph LR; A[Start] --> B[Done]', "
        "config={'htmlLabels':False,'flowchart':{'htmlLabels':False}});e.close();"
        "assert s.startswith('<svg') and 'Start' in s and 'Done' in s"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(site_packages)
    try:
        result = runner(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeStoreError(f"could not start prepared Mermaid runtime: {error}") from error
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeStoreError(
            "prepared Mermaid runtime failed its SVG probe: "
            + (detail or f"exit status {result.returncode}")
        )


class MermaidProvider:
    """Resolve and acquire the exact reviewed Python Mermaid runtime."""

    def resolve(
        self, policy: ComponentPolicy, environment: RuntimeEnvironment
    ) -> ArtifactDescriptor:
        if policy.version not in {"latest", "supported", MERMAID_RUNTIME_VERSION}:
            raise RuntimeProviderUnavailableError(
                f"this release supports Mermaid runtime {MERMAID_RUNTIME_VERSION}; "
                f"pdk-pdf.toml requests {policy.version}"
            )
        key = _platform_key(environment)
        wheels = _wheels_for(key)
        return ArtifactDescriptor(
            component="mermaid",
            version=MERMAID_RUNTIME_VERSION,
            source_url=_MERMAIDX.url,
            sha256=_RUNTIME_SHA256[key],
            licence="MIT and bundled dependency licences",
            provenance="deterministic composite of reviewed PyPI wheels: "
            + ", ".join(wheel.filename for wheel in wheels),
            platform=environment.system,
            architecture=environment.architecture,
            environment_identity=environment.identity,
            archive_format="zip",
            expected_paths=(
                "site-packages/mermaidx/assets/mermaid.js",
                "site-packages/quickjs/__init__.py",
                "site-packages/termaid/__init__.py",
                "site-packages/resvg_py/__init__.py",
                "site-packages/mermaidx-0.9.5.dist-info/licenses/LICENSE.txt",
            ),
        )

    def acquire(self, descriptor: ArtifactDescriptor, destination: Path) -> None:
        key = _platform_key(
            RuntimeEnvironment(
                descriptor.platform,
                descriptor.architecture,
                "cpython",
                "runtime",
            )
        )
        wheels = _wheels_for(key)
        if (
            descriptor.component != "mermaid"
            or descriptor.version != MERMAID_RUNTIME_VERSION
            or descriptor.source_url != _MERMAIDX.url
            or descriptor.sha256 != _RUNTIME_SHA256[key]
        ):
            raise RuntimeStoreError("refusing an unreviewed Mermaid runtime")
        with tempfile.TemporaryDirectory(
            prefix="mermaid-wheels-", dir=destination.parent
        ) as temporary:
            root = Path(temporary)
            paths: list[Path] = []
            for wheel in wheels:
                path = root / wheel.filename
                download_release_asset(
                    wheel.url,
                    path,
                    expected_bytes=wheel.size,
                    label=wheel.filename,
                )
                if sha256_file(path) != wheel.sha256:
                    raise RuntimeStoreError(f"reviewed wheel digest changed: {wheel.filename}")
                paths.append(path)
            _build_runtime_archive(tuple(paths), destination)

    def probe(self, descriptor: ArtifactDescriptor, runtime: Path) -> None:
        if descriptor.version != MERMAID_RUNTIME_VERSION:
            raise RuntimeStoreError("refusing to probe an unsupported Mermaid runtime")
        probe_runtime(runtime)


__all__ = [
    "MERMAID_RUNTIME_VERSION",
    "MermaidProvider",
    "probe_runtime",
    "runtime_site_packages",
]
