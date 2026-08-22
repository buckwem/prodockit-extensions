# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Durable, isolated recovery state for the standalone ``pdkboot`` command."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA = 1


def pdkboot_report_path(config_path: Path) -> Path:
    """Put recovery state beside, but distinctly from, pdkboot's config."""
    return config_path.with_name(f"{config_path.stem}.last-run.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PdkbootRunJournal:
    """An atomically replaced account of the latest apply run.

    A damaged or half-written recovery file is worse than no recovery file,
    so every update is written, flushed and replaced as one filesystem
    operation. Journal failure never stops installation; ``error`` lets the
    command warn that this secondary safety net is unavailable.
    """

    def __init__(
        self,
        path: Path,
        *,
        version: str,
        config_path: Path,
        resume: Sequence[str],
        stages: Sequence[dict[str, Any]],
    ) -> None:
        self.path = path
        self.error: str | None = None
        started = _now()
        self.data: dict[str, Any] = {
            "schema": REPORT_SCHEMA,
            "pdkboot_version": version,
            "status": "running",
            "started_at": started,
            "updated_at": started,
            "config_file": str(config_path),
            "resume": list(resume),
            "current_stage": None,
            "failure": None,
            "stages": [dict(stage) for stage in stages],
        }
        self._write()

    def stage(
        self,
        stage_id: str,
        status: str,
        *,
        detail: str = "",
        action: str = "",
    ) -> None:
        """Record the latest known state of one stage and the active stage."""
        if self.error is not None:
            return
        for stage in self.data["stages"]:
            if stage["id"] == stage_id:
                stage["status"] = status
                stage["detail"] = detail
                if action:
                    stage["action"] = action
                break
        if status == "running":
            self.data["current_stage"] = stage_id
        elif (
            status in {"completed", "satisfied", "skipped"}
            and self.data["current_stage"] == stage_id
        ):
            self.data["current_stage"] = None
        self.data["updated_at"] = _now()
        self._write()

    def settle(self) -> str:
        """Finish normally, distinguishing a complete run from pending work."""
        pending = {"planned", "running", "skipped", "waiting", "unknown"}
        statuses = {stage["status"] for stage in self.data["stages"]}
        status = "incomplete" if statuses & pending else "completed"
        self.finish(status)
        return status

    def finish(
        self,
        status: str,
        *,
        failure: dict[str, Any] | None = None,
    ) -> None:
        """Close the run, retaining the failed/waiting stage when useful."""
        if self.error is not None:
            return
        self.data["status"] = status
        self.data["failure"] = failure
        if status == "completed":
            self.data["current_stage"] = None
        self.data["updated_at"] = _now()
        self._write()

    def _write(self) -> None:
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(self.data, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            self.error = f"could not update {self.path}: {error}"
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)


__all__ = ["PdkbootRunJournal", "pdkboot_report_path"]
