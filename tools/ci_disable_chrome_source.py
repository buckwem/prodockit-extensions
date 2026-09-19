"""Disable only unused Chrome APT entries on disposable GitHub runners."""

import re
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
    for path in root.glob("*.sources"):
        original = path.read_text()
        blocks = re.split(r"(\n\s*\n)", original)
        for index in range(0, len(blocks), 2):
            block = blocks[index]
            uri = re.search(r"^URIs:[^\n]*(?:\n[ \t]+[^\n]+)*", block, re.MULTILINE)
            if not uri:
                continue
            urls = uri.group().split(":", 1)[1].split()
            retained = [url for url in urls if "dl.google.com/linux/chrome" not in url]
            if retained == urls:
                continue
            if retained:
                block = block[: uri.start()] + "URIs: " + " ".join(retained) + block[uri.end() :]
            elif re.search(r"^Enabled:", block, re.MULTILINE):
                block = re.sub(r"^Enabled:.*$", "Enabled: no", block, flags=re.MULTILINE)
            else:
                block = "Enabled: no\n" + block
            blocks[index] = block
        updated = "".join(blocks)
        if updated != original:
            path.write_text(updated)


if __name__ == "__main__":
    disable(Path("/etc/apt/sources.list.d"))
