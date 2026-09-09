"""Disable only unused Chrome APT entries on disposable GitHub runners."""

from pathlib import Path


def disable(root: Path) -> None:
    for path in root.glob("*.list"):
        original = path.read_text()
        lines = original.splitlines(keepends=True)
        updated = "".join(
            "# Disabled for CI: " + line
            if line.lstrip().startswith(("deb ", "deb-src "))
            and "dl.google.com/linux/chrome" in line
            else line
            for line in lines
        )
        if updated != original:
            path.write_text(updated)


if __name__ == "__main__":
    disable(Path("/etc/apt/sources.list.d"))
