import runpy
from pathlib import Path

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
