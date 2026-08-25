# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Confirm that a built wheel carries the canonical shared stylesheet."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

RESOURCE = "prodockit/assets/extra.css"


def resolve_wheel(value: Path) -> Path:
    if value.is_file():
        return value
    wheels = sorted(value.glob("prodockit-*.whl")) if value.is_dir() else []
    if len(wheels) != 1:
        raise ValueError(f"expected one prodockit wheel in {value}; found {len(wheels)}")
    return wheels[0]


def check(wheel: Path, canonical: Path) -> None:
    expected = canonical.read_bytes()
    with zipfile.ZipFile(wheel) as archive:
        try:
            packaged = archive.read(RESOURCE)
        except KeyError:
            raise ValueError(f"{wheel} does not contain {RESOURCE}") from None
    if packaged != expected:
        raise ValueError(f"{RESOURCE} does not match {canonical}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True, help="Wheel file or directory")
    parser.add_argument(
        "--canonical",
        type=Path,
        default=Path("docs/stylesheets/extra.css"),
        help="Canonical source stylesheet",
    )
    args = parser.parse_args()
    try:
        wheel = resolve_wheel(args.wheel)
        check(wheel, args.canonical)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"{RESOURCE} matches {args.canonical}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
