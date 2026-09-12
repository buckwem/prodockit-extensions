"""YAML preflight and safe recovery apply to configuration and CI files."""

from pathlib import Path

import pytest

from prodockit import adopt
from prodockit.config_integrity import before_write, validate


@pytest.mark.parametrize(
    "name",
    ["mkdocs.yml", "zensical.yaml", ".gitlab-ci.yml", ".github/workflows/docs.yml", "pdk.yml"],
)
def test_invalid_yaml_blocks_activity_before_changes(tmp_path, monkeypatch, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("site_name: Example\nbroken: [\n")
    monkeypatch.setattr(adopt, "_check_project_release", lambda root: pytest.fail("too late"))
    with pytest.raises(adopt.AdoptError, match=r"line 3, column 1: invalid YAML"):
        adopt.apply_step(tmp_path, adopt.AdoptOptions(), "core")
    assert path.read_text() == "site_name: Example\nbroken: [\n"
    assert not (tmp_path / "docs").exists()


def test_yaml_writer_resumes_after_fix(tmp_path):
    path = tmp_path / "mkdocs.yml"
    path.write_text("site_name: [")
    proposed = b"site_name: Example\n"
    with pytest.raises(adopt.AdoptError, match="rerun the same command"):
        adopt._atomic_write(path, proposed)
    assert path.read_text() == "site_name: ["
    path.write_text("site_name: Previous\n")
    adopt._atomic_write(path, proposed)
    adopt._atomic_write(path, proposed)
    assert path.read_bytes() == proposed


def test_proposed_yaml_checked(tmp_path):
    path = tmp_path / "docs.yml"
    path.write_text("name: Documentation\n")
    with pytest.raises(ValueError, match="invalid YAML"):
        before_write(path, "name: [")
    assert path.read_text() == "name: Documentation\n"


@pytest.mark.parametrize(
    "source",
    [
        "job:\n  script: !reference [.common, script]\n",
        "markdown_extensions:\n  - pymdownx.superfences:\n      format: !!python/name:example.format\n",
        "on: [push]\njobs:\n  build:\n    if: ${{ github.ref == 'refs/heads/main' }}\n",
        "defaults: &defaults {name: test}\njob: {<<: *defaults}\n",
    ],
)
def test_valid_tags_and_ci_syntax_are_not_executed(source):
    validate(source, Path("config.yml"))


def test_non_yaml_files_are_not_parsed(tmp_path):
    before_write(tmp_path / "extra.js", "not: [ YAML")


def test_private_values_not_in_error():
    with pytest.raises(ValueError) as caught:
        validate("token: private-secret\ninvalid: [", Path("config.yml"))
    assert "private-secret" not in str(caught.value)
