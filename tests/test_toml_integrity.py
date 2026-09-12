"""Malformed input must survive unchanged, with a recoverable location error."""

from pathlib import Path

import pytest

from prodockit import adopt, toolchain
from prodockit.toml_integrity import before_write, check, validate


@pytest.mark.parametrize(
    "name",
    [
        "zensical.toml",
        ".prodockit-components.toml",
        ".prodockit-toolchain.toml",
        ".prodockit-adopt.toml",
        "pyproject.toml",
    ],
)
def test_adopt_preflight_before_any_activity(tmp_path, monkeypatch, name):
    broken = tmp_path / name
    broken.write_text("[project]\nvalue = ]\n")
    monkeypatch.setattr(adopt, "_check_project_release", lambda root: None)
    with pytest.raises(adopt.AdoptError, match=r"line 2, column"):
        adopt.apply_step(tmp_path, adopt.AdoptOptions(), "core")
    assert broken.read_text() == "[project]\nvalue = ]\n"
    assert sorted(tmp_path.iterdir()) == [broken]


def test_manifest_can_resume_after_correction(tmp_path):
    path = tmp_path / ".prodockit-components.toml"
    path.write_text("schema = ]\n")
    completed = tmp_path / "completed.txt"
    completed.write_text("earlier work")
    with pytest.raises(adopt.AdoptError, match="rerun the same command"):
        adopt.write_manifest(tmp_path, adopt.AdoptOptions(mermaid=True))
    path.write_text("schema = 1\n")
    adopt.write_manifest(tmp_path, adopt.AdoptOptions(mermaid=True))
    assert adopt.load_manifest(tmp_path).mermaid
    check(path)
    original = path.read_bytes()
    adopt.write_manifest(tmp_path, adopt.AdoptOptions(mermaid=True))
    assert path.read_bytes() == original
    assert completed.read_text() == "earlier work"


def test_toolchain_preflight_precedes_install(tmp_path, monkeypatch):
    (tmp_path / ".prodockit-toolchain.toml").write_text("schema = ]")
    monkeypatch.setattr(toolchain, "plan", lambda *a, **k: pytest.fail("installer planning ran"))
    with pytest.raises(toolchain.ToolchainError, match="line 1"):
        toolchain.apply(tmp_path)


def test_existing_and_proposed_contents_checked(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text("value = 1\n")
    with pytest.raises(ValueError, match="line 1"):
        before_write(path, "value = ]")
    assert path.read_text() == "value = 1\n"
    path.write_text("value = ]")
    with pytest.raises(ValueError, match="line 1"):
        before_write(path, "value = 1\n")


def test_eof_location_and_private_contents():
    with pytest.raises(ValueError, match="line 2, column") as caught:
        validate('secret = """private\n', Path("settings.toml"))
    assert "private" not in str(caught.value)


def test_new_file_validated(tmp_path):
    path = tmp_path / "new.toml"
    before_write(path, "value = 1")
    with pytest.raises(ValueError):
        before_write(path, b"value = ]")
    assert not path.exists()


def test_atomic_writer_refuses_invalid_existing_file(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text("value = ]")
    with pytest.raises(adopt.AdoptError, match="line 1"):
        adopt._atomic_write(path, b"value = 1")
    assert path.read_text() == "value = ]"


def test_sync_repo_refuses_invalid_toml_before_update():
    from prodockit.sync_repo import SyncRepoError, update_config

    with pytest.raises(SyncRepoError, match="line 2"):
        update_config(
            "[project]\nvalue = ]",
            repo_url="https://github.com/example/site",
            namespace="example",
            repo_name="site",
            icon="github",
            edit_uri=None,
        )


def test_bootstrap_save_preserves_invalid_file(tmp_path):
    from prodockit.bootstrap.config import BootstrapConfig, BootstrapConfigError, save

    path = tmp_path / "bootstrap.toml"
    path.write_text("host = ]")
    with pytest.raises(BootstrapConfigError, match="line 1"):
        save(path, BootstrapConfig())
    assert path.read_text() == "host = ]"


def test_pins_refuses_invalid_file(tmp_path):
    from prodockit.pins import PinError, apply_version, discover

    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\ndependencies = ["zensical>=0.0.59"]\ninvalid = ]\n')
    state = discover(str(tmp_path))["zensical"]
    with pytest.raises(PinError, match="line 3"):
        apply_version(str(tmp_path), state, "0.0.60")
    assert "0.0.59" in path.read_text()
