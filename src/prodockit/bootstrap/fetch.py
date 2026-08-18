# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Asking a URL what it says, without launching another program.

Two stages ask a host a question and read the answer: whether the
documentation site is serving, and whether Pages is switched on. Both
used to shell out to `curl`, and that cost three separate fixes:

- #374, curl absent because it arrives four stages later, and
  ``curl: not found`` read as though the server had answered
- #443, ``-o /dev/null`` on a platform with no such device, so the probe
  failed on every Windows machine
- and a misdiagnosis of this module's own making, where a `curl` typed at
  a PowerShell prompt resolved to `Invoke-WebRequest` and looked like an
  absent program

Each was fixed as a property of curl. The common cause is making an HTTP
request by starting a process at all, when Python is already here
(prodockit-extensions#449).

Two behaviours have to survive the move, and both are load-bearing:

**Redirects are not followed.** A `302` is how a login-walled site is
recognised as published - a Surrey Pages URL answers `302` to GitLab's
own OAuth consent page. An opener that followed it would report the
consent page's `200` and call a site publicly readable when it is not.

**"Could not establish" stays distinguishable from "not there".** A
refused connection, a DNS failure or a timeout returns `None`, which is
not a status and must never be read as one.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

#: How long to wait, in seconds. The same 20 the curl calls used.
DEFAULT_TIMEOUT = 20.0


@dataclass(frozen=True)
class Fetched:
    """What a URL answered."""

    status: int
    body: str = ""


class _KeepRedirects(urllib.request.HTTPRedirectHandler):
    """Reports a redirect rather than chasing it.

    Returning `None` from `redirect_request` tells urllib not to follow,
    and it raises `HTTPError` carrying the 3xx instead - which is exactly
    the answer wanted here.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def fetch(url: str, timeout: float = DEFAULT_TIMEOUT) -> Fetched | None:
    """What `url` says to an anonymous caller, or `None` if it could not be asked.

    `None` means the question was never put - not that the answer was no.
    """
    opener = urllib.request.build_opener(_KeepRedirects)
    try:
        with opener.open(url, timeout=timeout) as answer:
            return Fetched(answer.status, _text(answer.read()))
    except urllib.error.HTTPError as refused:
        # Not a failure to ask: the host answered, with 3xx/4xx/5xx.
        return Fetched(refused.code, _text(refused.read()))
    except (urllib.error.URLError, OSError, ValueError):
        # No route, no name, no listener, or a URL that is not one.
        return None


def _text(raw: bytes) -> str:
    """The body as text, never raising on what a host chose to send."""
    return raw.decode("utf-8", errors="replace")
