# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from prodockit.pdf.runtime_config import ComponentPolicy
from prodockit.pdf.runtime_prepare import (
    RuntimeEnvironment,
    RuntimeProviderUnavailableError,
    normalise_requested_components,
    prepare_runtime_components,
)
from prodockit.pdf.runtime_store import ArtifactDescriptor


class FixtureProvider:
    def __init__(self, archive: Path, environment: RuntimeEnvironment) -> None:
        self.archive = archive
        self.environment = environment
        self.resolved: list[ComponentPolicy] = []
        self.acquisitions = 0
        self.probes = 0

    def resolve(
        self, policy: ComponentPolicy, environment: RuntimeEnvironment
    ) -> ArtifactDescriptor:
        assert environment == self.environment
        self.resolved.append(policy)
        return ArtifactDescriptor(
            component="mermaid",
            version="11.12.2",
            source_url="https://example.invalid/mermaid.zip",
            sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            licence="MIT",
            provenance="local G1 fixture",
            platform=environment.system,
            architecture=environment.architecture,
            environment_identity=environment.identity,
            archive_format="zip",
            expected_paths=("renderer.py", "LICENSE"),
        )

    def acquire(self, descriptor: ArtifactDescriptor, destination: Path) -> None:
        assert descriptor.component == "mermaid"
        self.acquisitions += 1
        destination.write_bytes(self.archive.read_bytes())

    def probe(self, descriptor: ArtifactDescriptor, runtime: Path) -> None:
        assert descriptor.component == "mermaid"
        assert (runtime / "renderer.py").read_text(encoding="utf-8") == "# fixture\n"
        self.probes += 1


def _fixture(tmp_path: Path) -> tuple[Path, RuntimeEnvironment, FixtureProvider]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "zensical.toml").write_text("[project]\n", encoding="utf-8")
    (project / "pdk-pdf.toml").write_text(
        "schema_version = 1\n[mermaid]\nversion = 'supported'\n",
        encoding="utf-8",
    )
    archive = tmp_path / "mermaid.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("renderer.py", "# fixture\n")
        bundle.writestr("LICENSE", "MIT\n")
    environment = RuntimeEnvironment("test", "x86_64", "cpython", "3.14")
    return project, environment, FixtureProvider(archive, environment)


def test_fixture_provider_exercises_cold_and_warm_preparation(tmp_path: Path) -> None:
    project, environment, provider = _fixture(tmp_path)

    cold = prepare_runtime_components(
        project / "zensical.toml",
        ["mermaid"],
        providers={"mermaid": provider},
        environment=environment,
    )
    warm = prepare_runtime_components(
        project / "zensical.toml",
        ["mermaid"],
        providers={"mermaid": provider},
        environment=environment,
    )

    assert cold[0].cached is False
    assert warm[0].cached is True
    assert provider.resolved == [ComponentPolicy("supported"), ComponentPolicy("supported")]
    assert provider.acquisitions == provider.probes == 1


def test_missing_provider_fails_before_creating_runtime_state(tmp_path: Path) -> None:
    project, environment, _provider = _fixture(tmp_path)

    with pytest.raises(RuntimeProviderUnavailableError, match="not available in this release"):
        prepare_runtime_components(
            project / "zensical.toml", ["mermaid"], environment=environment
        )

    assert not (project / ".prodockit").exists()


def test_all_preflights_every_provider_before_preparing_any_component(tmp_path: Path) -> None:
    project, environment, provider = _fixture(tmp_path)

    with pytest.raises(RuntimeProviderUnavailableError, match="mathjax, weasyprint"):
        prepare_runtime_components(
            project / "zensical.toml",
            ["all"],
            providers={"mermaid": provider},
            environment=environment,
        )

    assert provider.resolved == []
    assert not (project / ".prodockit").exists()


def test_all_expands_in_canonical_order_and_duplicates_are_removed() -> None:
    assert normalise_requested_components(["MERMAID", "mermaid"]) == ("mermaid",)
    assert normalise_requested_components(["all", "mathjax"]) == (
        "mathjax",
        "mermaid",
        "weasyprint",
        "pandoc",
        "fonts",
    )


def test_provider_cannot_cross_component_or_environment_boundaries(tmp_path: Path) -> None:
    project, environment, provider = _fixture(tmp_path)
    original = provider.resolve

    def wrong_component(policy: ComponentPolicy, current: RuntimeEnvironment):
        descriptor = original(policy, current)
        return ArtifactDescriptor(**{**descriptor.__dict__, "component": "mathjax"})

    provider.resolve = wrong_component  # type: ignore[method-assign]
    with pytest.raises(RuntimeProviderUnavailableError, match="artifact for mathjax"):
        prepare_runtime_components(
            project / "zensical.toml",
            ["mermaid"],
            providers={"mermaid": provider},
            environment=environment,
        )


def test_unknown_request_is_rejected() -> None:
    with pytest.raises(RuntimeProviderUnavailableError, match="unknown PDF runtime"):
        normalise_requested_components(["browser"])
