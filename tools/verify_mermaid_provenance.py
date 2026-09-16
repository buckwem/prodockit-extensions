#!/usr/bin/env python3
# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Verify the official npm artifact recorded for standalone Mermaid."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prodockit.pdf._mermaid_provenance import (
    MermaidProvenanceError,
    load_mermaid_provenance,
    verify_mermaid_npm_tarball,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a pinned mermaid npm tarball and its runtime asset."
    )
    parser.add_argument("tarball", type=Path, help="Path to mermaid-11.16.0.tgz")
    args = parser.parse_args()
    try:
        verify_mermaid_npm_tarball(args.tarball)
    except MermaidProvenanceError as exc:
        parser.error(str(exc))
    provenance = load_mermaid_provenance()
    print(
        f"verified {provenance.npm_name}@{provenance.npm_version}: "
        f"{provenance.asset_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
