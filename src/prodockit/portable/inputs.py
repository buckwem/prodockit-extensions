# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Captured bytes and their isolated paths for portable preparation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from prodockit.portable import PortableError
from prodockit.project_config import ProjectConfig


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class MaterializedInputs:
    docs_dir: Path
    paths: Mapping[Path, Path]

    def dependency(self, original: Path) -> Path:
        try:
            return self.paths[original.resolve()]
        except KeyError as error:
            raise PortableError(f"dependency was not captured: {original}") from error


@dataclass(frozen=True)
class InputSnapshot:
    config: ProjectConfig
    files: Mapping[Path, bytes]

    @property
    def hashes(self) -> dict[str, str]:
        return {str(path): digest(data) for path, data in sorted(self.files.items())}

    @property
    def documents(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.config.docs_dir).as_posix(): data
            for path, data in sorted(self.files.items())
            if path.is_relative_to(self.config.docs_dir)
        }

    @property
    def sources(self) -> dict[str, str]:
        return {
            name: data.decode("utf-8")
            for name, data in self.documents.items()
            if Path(name).suffix.lower() == ".md"
        }

    def materialize(self, root: Path) -> MaterializedInputs:
        """Write the captured bytes, never reopening author-owned inputs."""
        paths: dict[Path, Path] = {}
        for index, (original, data) in enumerate(sorted(self.files.items())):
            if original == self.config.path:
                relative = Path(".inputs/config.toml")
            elif original.is_relative_to(self.config.docs_dir):
                relative = Path(".inputs/docs") / original.relative_to(self.config.docs_dir)
            else:
                relative = Path(".inputs/dependencies") / str(index) / original.name
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            paths[original] = target
        # Empty documentation directories still have a well-defined capture.
        docs = root / ".inputs/docs"
        docs.mkdir(parents=True, exist_ok=True)
        return MaterializedInputs(docs, paths)
