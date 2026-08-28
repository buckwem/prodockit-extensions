# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Create the private configuration used only for prodockit.org.

The committed Zensical configuration remains reusable and analytics-free.
The deployment workflow supplies the canonical site's Google Analytics
measurement ID through a repository secret and writes the resulting temporary
configuration outside version control.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

MEASUREMENT_ID = re.compile(r"G-[A-Z0-9]+")
ANALYTICS_CONFIG = '''

# Added by tools/canonical_site_config.py for the canonical deployment only.
[project.extra.analytics]
provider = "google"
property = {measurement_id}

[project.extra.consent]
title = "Cookie consent"
description = """
  We use optional analytics cookies to understand which documentation is
  useful and improve prodockit. Google Analytics remains disabled unless you
  choose to accept it.
"""
actions = ["accept", "reject", "manage"]

[project.extra.consent.cookies]
analytics.name = "Google Analytics"
analytics.checked = false
'''


def create_canonical_config(source: Path, destination: Path, measurement_id: str) -> None:
    """Write an analytics-enabled copy of *source* to *destination*."""

    if not MEASUREMENT_ID.fullmatch(measurement_id):
        raise ValueError(
            "GOOGLE_ANALYTICS_ID must be a GA4 measurement ID such as G-ABC123"
        )

    source_text = source.read_text(encoding="utf-8")
    source_config = tomllib.loads(source_text)
    source_extra = source_config.get("project", {}).get("extra", {})
    if "analytics" in source_extra or "consent" in source_extra:
        raise ValueError(
            f"{source} already contains analytics or consent configuration; "
            "keep the committed configuration reusable and analytics-free"
        )

    generated = source_text.rstrip() + "\n" + ANALYTICS_CONFIG.format(
        measurement_id=repr(measurement_id)
    )
    parsed = tomllib.loads(generated)
    extra = parsed["project"]["extra"]
    if extra["analytics"]["property"] != measurement_id:
        raise ValueError("the generated analytics configuration did not validate")
    if extra["consent"]["cookies"]["analytics"]["checked"] is not False:
        raise ValueError("analytics consent must be disabled by default")

    destination.write_text(generated, encoding="utf-8")


def main(arguments: list[str] | None = None) -> int:
    """Command-line entry point used by the documentation workflow."""

    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) != 3:
        print(
            "usage: canonical_site_config.py SOURCE DESTINATION GOOGLE_ANALYTICS_ID",
            file=sys.stderr,
        )
        return 2

    source, destination, measurement_id = arguments
    try:
        create_canonical_config(Path(source), Path(destination), measurement_id)
    except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
