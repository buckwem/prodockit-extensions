# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import io
import json
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

import prodockit.pdf.runtime_store as runtime_store_module
from prodockit.pdf.runtime_store import (
    ArtifactDescriptor,
    RuntimePreparationError,
    RuntimeStore,
    RuntimeStoreError,
)


def _zip(path: Path, content: bytes = b"runtime") -> str:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("bin/tool", content)
        archive.writestr("LICENSE", b"test licence")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _descriptor(digest: str, *, version: str = "1.0.0") -> ArtifactDescriptor:
    return ArtifactDescriptor(
        component="weasyprint",
        version=version,
        source_url=f"https://example.invalid/runtime-{version}.zip",
        sha256=digest,
        licence="BSD-3-Clause",
        provenance="test fixture",
        platform="windows",
        architecture="x86_64",
        environment_identity="windows-x86_64:test",
        archive_format="zip",
        expected_paths=("bin/tool", "LICENSE"),
    )


def _copy_from(source: Path, calls: list[Path]):
    def acquire(destination: Path) -> None:
        calls.append(destination)
        destination.write_bytes(source.read_bytes())

    return acquire


def test_prepare_activates_metadata_then_warm_reuse_does_no_acquisition(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))
    calls: list[Path] = []
    probes: list[Path] = []
    store = RuntimeStore(tmp_path / "project")

    cold = store.prepare(
        descriptor,
        acquire=_copy_from(archive, calls),
        probe=lambda root: probes.append(root),
    )
    warm = store.prepare(
        descriptor,
        acquire=lambda _path: pytest.fail("a healthy cache must not contact its provider"),
        probe=lambda _root: pytest.fail("a healthy cache must not repeat its smoke test"),
    )

    assert cold.cached is False
    assert warm.cached is True
    assert warm.path == cold.path
    assert (warm.path / "bin/tool").read_bytes() == b"runtime"
    assert len(calls) == len(probes) == 1
    current = json.loads((store.root / "current.json").read_text(encoding="utf-8"))
    marker = json.loads((warm.path / ".prodockit-runtime.json").read_text(encoding="utf-8"))
    assert current["weasyprint"]["source_url"] == descriptor.source_url
    assert current["weasyprint"]["environment_identity"] == descriptor.environment_identity
    assert marker["sha256"] == descriptor.sha256
    assert marker["licence"] == "BSD-3-Clause"
    assert warm.path.relative_to(store.root).parts == ("r", descriptor.cache_key)
    assert store.active("weasyprint") == warm
    assert store.active_for(descriptor) == warm
    incompatible = ArtifactDescriptor(
        **{**descriptor.__dict__, "environment_identity": "windows-x86_64:other"}
    )
    assert store.active_for(incompatible) is None


def test_corrupt_active_runtime_is_rebuilt_from_the_validated_download(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))
    calls: list[Path] = []
    store = RuntimeStore(tmp_path / "project")
    first = store.prepare(descriptor, acquire=_copy_from(archive, calls), probe=lambda _root: None)
    (first.path / "bin/tool").write_bytes(b"corrupt")

    repaired = store.prepare(
        descriptor,
        acquire=lambda _path: pytest.fail("the verified download is already cached"),
        probe=lambda _root: None,
    )

    assert repaired.cached is False
    assert (repaired.path / "bin/tool").read_bytes() == b"runtime"
    assert len(calls) == 1


def test_executable_bit_tampering_invalidates_the_active_runtime(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))
    store = RuntimeStore(tmp_path / "project")
    active = store.prepare(
        descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
    )
    tool = active.path / "bin/tool"
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)

    assert store.active("weasyprint") is None


def test_failed_update_preserves_and_reports_last_known_good(tmp_path: Path) -> None:
    first_archive = tmp_path / "first.zip"
    first = _descriptor(_zip(first_archive, b"first"), version="1.0.0")
    store = RuntimeStore(tmp_path / "project")
    active = store.prepare(
        first, acquire=_copy_from(first_archive, []), probe=lambda _root: None
    )
    second_archive = tmp_path / "second.zip"
    second = _descriptor(_zip(second_archive, b"second"), version="2.0.0")

    with pytest.raises(RuntimePreparationError, match="last-known-good") as caught:
        store.prepare(
            second,
            acquire=_copy_from(second_archive, []),
            probe=lambda _root: (_ for _ in ()).throw(RuntimeStoreError("probe failed")),
        )

    assert caught.value.fallback == active.path
    retained = store.active("weasyprint")
    assert retained is not None
    assert retained.path == active.path
    assert retained.version == active.version
    assert (active.path / "bin/tool").read_bytes() == b"first"


def test_repairing_current_does_not_replace_the_previous_known_good(tmp_path: Path) -> None:
    first_archive = tmp_path / "first.zip"
    first = _descriptor(_zip(first_archive, b"first"), version="1.0.0")
    second_archive = tmp_path / "second.zip"
    second = _descriptor(_zip(second_archive, b"second"), version="2.0.0")
    store = RuntimeStore(tmp_path / "project")
    first_result = store.prepare(
        first, acquire=_copy_from(first_archive, []), probe=lambda _root: None
    )
    second_result = store.prepare(
        second, acquire=_copy_from(second_archive, []), probe=lambda _root: None
    )
    (second_result.path / "bin/tool").write_bytes(b"corrupt")

    repaired = store.prepare(
        second,
        acquire=lambda _path: pytest.fail("the download should remain cached"),
        probe=lambda _root: None,
    )

    previous = json.loads((store.root / "previous.json").read_text(encoding="utf-8"))
    assert repaired.path == second_result.path
    assert previous["weasyprint"]["path"] == first_result.path.relative_to(store.root).as_posix()


def test_arbitrary_provider_failure_is_wrapped_and_retains_fallback(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))
    store = RuntimeStore(tmp_path / "project")
    active = store.prepare(
        descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
    )
    update = ArtifactDescriptor(
        **{
            **descriptor.__dict__,
            "version": "2.0.0",
            "sha256": hashlib.sha256(b"new artifact").hexdigest(),
        }
    )

    with pytest.raises(RuntimePreparationError, match="provider failed") as caught:
        store.prepare(
            update,
            acquire=lambda _path: (_ for _ in ()).throw(ValueError("provider failed")),
            probe=lambda _root: None,
        )

    assert caught.value.fallback == active.path


def test_wrong_download_digest_never_becomes_active(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor("0" * 64)
    _zip(archive)
    store = RuntimeStore(tmp_path / "project")

    with pytest.raises(RuntimePreparationError, match="SHA-256 mismatch"):
        store.prepare(
            descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
        )

    assert store.active("weasyprint") is None
    assert not (store.root / "current.json").exists()


@pytest.mark.parametrize(
    "name",
    ["../escape", "..\\escape", "/absolute", "C:/escape", "CON/file", "name./file"],
)
def test_zip_archive_rejects_unsafe_paths(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("bin/tool", b"runtime")
        bundle.writestr("LICENSE", b"licence")
        bundle.writestr(name, b"escape")
    descriptor = _descriptor(hashlib.sha256(archive.read_bytes()).hexdigest())

    with pytest.raises(RuntimePreparationError, match="unsafe archive path"):
        RuntimeStore(tmp_path / "project").prepare(
            descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
        )

    assert not (tmp_path / "escape").exists()


def test_archive_rejects_unicode_normalisation_collisions(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("bin/tool", b"runtime")
        bundle.writestr("LICENSE", b"licence")
        bundle.writestr("caf\N{LATIN SMALL LETTER E WITH ACUTE}.txt", b"first")
        bundle.writestr("cafe\N{COMBINING ACUTE ACCENT}.txt", b"second")
    descriptor = _descriptor(hashlib.sha256(archive.read_bytes()).hexdigest())

    with pytest.raises(RuntimePreparationError, match="duplicate archive path"):
        RuntimeStore(tmp_path / "project").prepare(
            descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
        )


def test_zip_archive_rejects_symbolic_links(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("bin/tool", b"runtime")
        bundle.writestr("LICENSE", b"licence")
        link = zipfile.ZipInfo("link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(link, "bin/tool")
    descriptor = _descriptor(hashlib.sha256(archive.read_bytes()).hexdigest())

    with pytest.raises(RuntimePreparationError, match="symbolic link"):
        RuntimeStore(tmp_path / "project").prepare(
            descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
        )


def test_zip_archive_rejects_special_entries(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("bin/tool", b"runtime")
        bundle.writestr("LICENSE", b"licence")
        device = zipfile.ZipInfo("device")
        device.external_attr = (stat.S_IFCHR | 0o600) << 16
        bundle.writestr(device, b"")
    descriptor = _descriptor(hashlib.sha256(archive.read_bytes()).hexdigest())

    with pytest.raises(RuntimePreparationError, match="special entry"):
        RuntimeStore(tmp_path / "project").prepare(
            descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
        )


def test_provider_cannot_supply_a_symbolic_link_as_the_download(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))

    def acquire(destination: Path) -> None:
        destination.symlink_to(archive)

    with pytest.raises(RuntimePreparationError, match="did not create"):
        RuntimeStore(tmp_path / "project").prepare(
            descriptor, acquire=acquire, probe=lambda _root: None
        )


def test_provider_cannot_exceed_the_common_archive_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))
    monkeypatch.setattr(runtime_store_module, "MAX_ARCHIVE_BYTES", 4)

    with pytest.raises(RuntimePreparationError, match="limit is 4"):
        RuntimeStore(tmp_path / "project").prepare(
            descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
        )


def test_tar_archive_uses_the_same_validation_and_activation_path(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name, content in (("bin/tool", b"runtime"), ("LICENSE", b"licence")):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mode = 0o755 if name == "bin/tool" else 0o644
            bundle.addfile(member, io.BytesIO(content))
    base = _descriptor(hashlib.sha256(archive.read_bytes()).hexdigest())
    descriptor = ArtifactDescriptor(**{**base.__dict__, "archive_format": "tar"})

    result = RuntimeStore(tmp_path / "project").prepare(
        descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
    )

    assert (result.path / "bin/tool").read_bytes() == b"runtime"


def test_component_lock_has_a_bounded_wait(tmp_path: Path) -> None:
    first = RuntimeStore(tmp_path / "project")
    second = RuntimeStore(tmp_path / "project", lock_timeout=0.01)

    with first.component_lock("mermaid"), pytest.raises(
        RuntimeStoreError, match="timed out"
    ), second.component_lock("mathjax"):
        pytest.fail("the shared metadata lock must serialize different components")


def test_stale_partial_state_for_the_component_is_cleaned_under_its_lock(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))
    store = RuntimeStore(tmp_path / "project")
    store.prepare(descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None)
    stale_file = store.root / "staging/download-weasyprint-stale.partial"
    stale_directory = store.root / "staging/runtime-weasyprint-stale"
    stale_file.write_bytes(b"partial")
    stale_directory.mkdir()

    store.prepare(
        descriptor,
        acquire=lambda _path: pytest.fail("the active runtime is healthy"),
        probe=lambda _root: pytest.fail("the active runtime is healthy"),
    )

    assert not stale_file.exists()
    assert not stale_directory.exists()


def test_new_runtime_paths_are_compact_for_windows_dll_loading(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))
    project = tmp_path / ("project-" + "x" * 80)
    store = RuntimeStore(project)
    staged: list[Path] = []

    active = store.prepare(
        descriptor,
        acquire=_copy_from(archive, []),
        probe=lambda root: staged.append(root),
    )

    assert len(staged[0].relative_to(store.root).as_posix()) <= 40
    assert len(active.path.relative_to(store.root).as_posix()) <= 40


def test_store_refuses_a_symlinked_project_cache_boundary(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / ".prodockit").symlink_to(outside, target_is_directory=True)
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))

    with pytest.raises(RuntimeStoreError, match="symbolic link"):
        RuntimeStore(project).prepare(
            descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None
        )

    assert list(outside.iterdir()) == []


def test_reading_absent_active_state_is_non_mutating(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    store = RuntimeStore(project)

    assert store.active("mermaid") is None
    assert not store.root.exists()


def test_projects_do_not_share_runtime_state(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    descriptor = _descriptor(_zip(archive))
    first = RuntimeStore(tmp_path / "one")
    second = RuntimeStore(tmp_path / "two")
    first.prepare(descriptor, acquire=_copy_from(archive, []), probe=lambda _root: None)

    assert first.active("weasyprint") is not None
    assert second.active("weasyprint") is None
    assert first.root != second.root


@pytest.mark.parametrize(
    "change",
    [
        {"component": "browser"},
        {"version": "supported"},
        {"version": "CON"},
        {"sha256": "ABC"},
        {"archive_format": "7z"},
        {"expected_paths": ("../escape",)},
    ],
)
def test_descriptor_validation_fails_before_creating_the_store(
    tmp_path: Path, change: dict[str, object]
) -> None:
    base = _descriptor("0" * 64)
    descriptor = ArtifactDescriptor(**{**base.__dict__, **change})
    store = RuntimeStore(tmp_path / "project")

    with pytest.raises(RuntimeStoreError):
        store.prepare(descriptor, acquire=lambda _path: None, probe=lambda _root: None)

    assert not store.root.exists()
