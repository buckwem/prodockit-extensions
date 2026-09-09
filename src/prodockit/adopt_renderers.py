# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Align selected renderer scaffolds to the installed release, with backups."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from prodockit.init_tools import COMPONENT_FILES, TEMPLATE_DIR
from prodockit.shared_files import same_text_content

BACKUPS = ".prodockit-adopt-backups/renderers"
PACKAGES = {"mermaid": "@mermaid-js/mermaid-cli", "mathjax": "mathjax-full"}


def expected_version(component: str) -> str:
    lock = json.loads((TEMPLATE_DIR / component / "package-lock.json").read_text())
    return str(lock["packages"][f"node_modules/{PACKAGES[component]}"]["version"])


def installed_version(root: Path, component: str) -> str | None:
    path = root / "tools" / component / "node_modules" / PACKAGES[component] / "package.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["version"]
        return value if isinstance(value, str) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _safe(root: Path, path: Path) -> None:
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError(f"renderer path is a symbolic link: {current}")
        if current == current.parent:
            raise ValueError(f"renderer path is outside the project: {path}")
        current = current.parent


def changes(root: Path, component: str) -> dict[Path, bytes]:
    if component not in COMPONENT_FILES:
        raise ValueError(f"unknown renderer: {component}")
    result = {}
    for name in COMPONENT_FILES[component]:
        target = root / "tools" / component / name
        _safe(root, target)
        content = (TEMPLATE_DIR / component / name).read_bytes()
        if not target.exists() or not same_text_content(target.read_bytes(), content):
            result[target] = content
    return result


def align(root: Path, component: str, *, write: Callable[[Path, bytes], None]) -> list[Path]:
    planned = changes(root, component)
    # Preserve every old file before replacing any member of the manifest/lock pair.
    for path in planned:
        if path.exists():
            original = path.read_bytes()
            digest = hashlib.sha256(original).hexdigest()
            backup = root / BACKUPS / component / digest / path.name
            _safe(root, backup)
            if backup.exists():
                if backup.read_bytes() != original:
                    raise ValueError(f"renderer backup does not match its checksum: {backup}")
            else:
                write(backup, original)
    for path, content in planned.items():
        write(path, content)
    return list(planned)
