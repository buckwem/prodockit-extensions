# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Fetches a repo's latest published release tag, for a PDF cover page's
optional `{RELEASE}` marker (see `prodockit.pdf.config`'s own docs) - the
PDF-side equivalent of the version a website's own header repo widget
typically shows client-side, which Pandoc/WeasyPrint has no JS engine to
do the same way.

Deliberately its own module, not alongside `prodockit.zensical_macros`'
`_get_repo_url()`/word count helpers: those run on every website rebuild
(including every live-reload save during `zensical serve`), and adding a
network call there would slow all of them down for a value only the PDF
actually needs.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request


def get_latest_release_tag(repo_url: str) -> str:
    """Returns the latest published release's tag name (e.g. `"v0.0.11"`)
    for a GitHub or GitLab `repo_url`, or `""` on any failure - no
    `repo_url`, an unsupported host, no published release, network
    unavailable, rate-limited, and so on - so a missing release can never
    break a PDF build; most projects using `prodockit pdf` will never
    publish a release at all."""
    if not repo_url:
        return ""
    parsed = urllib.parse.urlparse(repo_url)
    host = (parsed.hostname or "").lower()
    owner_repo = parsed.path.strip("/")
    if not owner_repo:
        return ""
    try:
        if "github.com" in host:
            api_url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
        elif "gitlab" in host:
            project = urllib.parse.quote(owner_repo, safe="")
            api_url = f"https://{parsed.hostname}/api/v4/projects/{project}/releases/permalink/latest"
        else:
            return ""
        with urllib.request.urlopen(api_url, timeout=5) as resp:
            data = json.load(resp)
        return str(data.get("tag_name") or "")
    except Exception:
        return ""
