# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Provider boundary for explicit project-local PDF runtime preparation.

G1 intentionally ships no network providers.  Component gates add approved
providers only after their artifacts, licences, platform coverage and probes
have passed their own evidence work.  Local fixtures exercise this complete
orchestration path in the meantime.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol

from prodockit.pdf.runtime_config import (
    COMPONENTS,
    ComponentPolicy,
    PdfRuntimeConfig,
    load_pdf_runtime_config,
)
from prodockit.pdf.runtime_store import ArtifactDescriptor, PreparationResult, RuntimeStore


class RuntimeProviderUnavailableError(RuntimeError):
    """An explicitly requested component has no qualified provider yet."""


@dataclass(frozen=True)
class RuntimeEnvironment:
    """Stable compatibility identity passed to every artifact provider."""

    system: str
    architecture: str
    python_implementation: str
    python_version: str

    @property
    def identity(self) -> str:
        return ":".join(
            (
                self.system,
                self.architecture,
                self.python_implementation,
                self.python_version,
            )
        )


class RuntimeProvider(Protocol):
    """Resolve, acquire and smoke-test one approved component artifact."""

    def resolve(
        self, policy: ComponentPolicy, environment: RuntimeEnvironment
    ) -> ArtifactDescriptor: ...

    def acquire(self, descriptor: ArtifactDescriptor, destination: Path) -> None: ...

    def probe(self, descriptor: ArtifactDescriptor, runtime: Path) -> None: ...


def current_runtime_environment() -> RuntimeEnvironment:
    system = platform.system().lower() or sys.platform.lower()
    architecture = platform.machine().lower() or "unknown"
    return RuntimeEnvironment(
        system=system,
        architecture=architecture,
        python_implementation=platform.python_implementation().lower(),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
    )


def default_runtime_providers(
    environment: RuntimeEnvironment,
) -> Mapping[str, RuntimeProvider]:
    """Return only providers qualified for this release and host family."""

    if environment.system != "windows":
        return {}
    from prodockit.pdf.weasyprint_runtime import WindowsWeasyPrintProvider

    return {"weasyprint": WindowsWeasyPrintProvider()}


def normalise_requested_components(requested: Sequence[str]) -> tuple[str, ...]:
    """Expand ``all`` and remove duplicates while retaining canonical order."""

    lowered = tuple(component.lower() for component in requested)
    unknown = sorted(set(lowered) - {*COMPONENTS, "all"})
    if unknown:
        raise RuntimeProviderUnavailableError(
            "unknown PDF runtime component(s): " + ", ".join(unknown)
        )
    selected = set(COMPONENTS if "all" in lowered else lowered)
    return tuple(component for component in COMPONENTS if component in selected)


def prepare_runtime_components(
    config_file: str | Path,
    requested: Sequence[str],
    *,
    providers: Mapping[str, RuntimeProvider] | None = None,
    environment: RuntimeEnvironment | None = None,
) -> tuple[PreparationResult, ...]:
    """Prepare requested components and exit without building a site or PDF."""

    selected = normalise_requested_components(requested)
    if not selected:
        return ()
    config: PdfRuntimeConfig = load_pdf_runtime_config(config_file)
    runtime_environment = environment or current_runtime_environment()
    available = (
        default_runtime_providers(runtime_environment)
        if providers is None
        else providers
    )
    missing = [component for component in selected if component not in available]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeProviderUnavailableError(
            f"{joined} preparation is not available in this release; "
            "the existing PDF runtime remains unchanged"
        )
    store = RuntimeStore(config.project_root)
    results: list[PreparationResult] = []
    for component in selected:
        provider = available.get(component)
        if provider is None:  # pragma: no cover - guarded by the preflight above
            raise AssertionError("provider preflight disagrees with provider lookup")
        descriptor = provider.resolve(config.policy_for(component), runtime_environment)
        if descriptor.component != component:
            raise RuntimeProviderUnavailableError(
                f"the {component} provider resolved an artifact for {descriptor.component}"
            )
        if descriptor.environment_identity != runtime_environment.identity:
            raise RuntimeProviderUnavailableError(
                f"the {component} provider returned incompatible environment identity "
                f"{descriptor.environment_identity!r}"
            )
        results.append(
            store.prepare(
                descriptor,
                acquire=partial(provider.acquire, descriptor),
                probe=partial(provider.probe, descriptor),
            )
        )
    return tuple(results)


def prepare_windows_weasyprint_runtime(
    config_file: str | Path,
    *,
    providers: Mapping[str, RuntimeProvider] | None = None,
    environment: RuntimeEnvironment | None = None,
) -> PreparationResult | None:
    """Prepare Windows x64 WeasyPrint; other platforms keep their system CLI."""

    runtime_environment = environment or current_runtime_environment()
    if runtime_environment.system != "windows":
        return None
    prepared = prepare_runtime_components(
        config_file,
        ("weasyprint",),
        providers=providers,
        environment=runtime_environment,
    )
    return prepared[0]


__all__ = [
    "RuntimeEnvironment",
    "RuntimeProvider",
    "RuntimeProviderUnavailableError",
    "current_runtime_environment",
    "default_runtime_providers",
    "normalise_requested_components",
    "prepare_runtime_components",
    "prepare_windows_weasyprint_runtime",
]
