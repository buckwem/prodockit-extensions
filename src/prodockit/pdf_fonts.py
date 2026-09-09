# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Shared evidence for the actual PDF font-family matches, not filenames."""

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

PDF_FAMILIES = ("Inter", "JetBrains Mono")


@dataclass(frozen=True)
class FontEvidence:
    status: Literal["available", "missing", "unverified"]
    detail: str


def inspect_fonts(run: Callable[[list[str]], tuple[int, str]]) -> FontEvidence:
    """Ask fontconfig which family would actually be used by the renderer.

    Fontconfig inspects configured system and per-user font locations. No host
    filesystem paths or substitute filenames are treated as installation proof.
    """
    missing = []
    unknown = []
    for family in PDF_FAMILIES:
        try:
            code, output = run(["fc-match", "-f", "%{family}", family])
        except (OSError, subprocess.SubprocessError):
            unknown.append(family)
            continue
        if code or not output.strip():
            unknown.append(family)
            continue
        matches = {value.strip().casefold() for value in re.split(r"[,\n]", output)}
        if family.casefold() not in matches:
            missing.append(f"{family} (matched {output.strip()})")
    if missing:
        detail = "PDF fonts are missing: " + "; ".join(missing)
        if unknown:
            detail += "; could not verify " + ", ".join(unknown)
        return FontEvidence("missing", detail)
    if unknown:
        return FontEvidence(
            "unverified",
            "PDF fonts could not be verified: "
            + ", ".join(unknown)
            + ". The font inspection tool (fc-match, supplied by fontconfig) "
            "must be available. Repair the PDF runtime, then rerun this check.",
        )
    return FontEvidence("available", "Inter and JetBrains Mono font families verified")
