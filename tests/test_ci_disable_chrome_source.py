import runpy
from pathlib import Path

import pytest

disable = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "tools" / "ci_disable_chrome_source.py")
)["disable"]


def test_disables_only_chrome_and_is_idempotent(tmp_path):
    source = tmp_path / "sources.list"
    ubuntu = "deb https://archive.ubuntu.com/ubuntu noble main\n"
    chrome = "deb [arch=amd64] https://dl.google.com/linux/chrome-stable/deb/ stable main\n"
    source.write_text(ubuntu + chrome + "# existing comment\n")
    disable(tmp_path)
    expected = ubuntu + "# Disabled for CI: " + chrome + "# existing comment\n"
    assert source.read_text() == expected
    disable(tmp_path)
    assert source.read_text() == expected


@pytest.mark.parametrize("enabled", ["", "Enabled: yes\n", "Enabled: no\n"])
def test_deb822_chrome_disabled_without_touching_other_stanzas(tmp_path, enabled):
    source = tmp_path / "vendor.sources"
    ubuntu = "Types: deb\nURIs: https://archive.ubuntu.com/ubuntu\nSuites: noble\n"
    chrome = (
        enabled
        + "Types: deb\nURIs: https://dl.google.com/linux/chrome-stable/deb/\nSuites: stable\n"
    )
    source.write_text(ubuntu + "\n" + chrome)
    disable(tmp_path)
    expected = source.read_text()
    assert expected.startswith(ubuntu + "\n")
    assert "Enabled: yes" not in expected
    assert expected.count("Enabled: no") == 1
    disable(tmp_path)
    assert source.read_text() == expected


def test_deb822_mixed_uris_preserves_other_repository(tmp_path):
    source = tmp_path / "mixed.sources"
    source.write_text(
        "Types: deb\nURIs: https://dl.google.com/linux/chrome-stable/deb/\n https://example.org/deb\nSuites: stable\n"
    )
    disable(tmp_path)
    assert "URIs: https://example.org/deb" in source.read_text()
    assert "Enabled: no" not in source.read_text()
    expected = source.read_text()
    disable(tmp_path)
    assert source.read_text() == expected
