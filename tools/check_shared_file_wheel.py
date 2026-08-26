# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Confirm that a built wheel carries the canonical managed stylesheets."""

from __future__ import annotations

import argparse
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path

RESOURCES = {
    "prodockit/assets/pdk.css": Path("docs/stylesheets/pdk.css"),
    "prodockit/assets/pdk-pdf.css": Path("docs/stylesheets/pdk-pdf.css"),
}


def resolve_wheel(value: Path) -> Path:
    if value.is_file():
        return value
    wheels = sorted(value.glob("prodockit-*.whl")) if value.is_dir() else []
    if len(wheels) != 1:
        raise ValueError(f"expected one prodockit wheel in {value}; found {len(wheels)}")
    return wheels[0]


def check(wheel: Path, resources: Mapping[str, Path] | None = None) -> None:
    resources = RESOURCES if resources is None else resources
    with zipfile.ZipFile(wheel) as archive:
        for resource, canonical in resources.items():
            expected = canonical.read_bytes()
            try:
                packaged = archive.read(resource)
            except KeyError:
                raise ValueError(f"{wheel} does not contain {resource}") from None
            if packaged != expected:
                raise ValueError(f"{resource} does not match {canonical}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True, help="Wheel file or directory")
    args = parser.parse_args()
    try:
        wheel = resolve_wheel(args.wheel)
        check(wheel)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print("Every packaged managed stylesheet matches its canonical source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
