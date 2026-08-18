# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""`prodockit.bootstrap.fetch`, against a real server.

Both behaviours under test are protocol-level, so a mocked `urlopen`
would only assert that the mock was called - it could not catch urllib
quietly following a redirect, which is the failure that would matter
(prodockit-extensions#449).
"""

from __future__ import annotations

import http.server
import threading
from collections.abc import Iterator

import pytest

from prodockit.bootstrap.fetch import fetch


class _Handler(http.server.BaseHTTPRequestHandler):
    """Three answers, chosen by path."""

    # Named as http.server requires, not as this project would name it.
    def do_GET(self) -> None:
        if self.path == "/moved":
            # What a login-walled Pages site does: 302 to a consent page.
            self.send_response(302)
            self.send_header("Location", f"http://{self.headers['Host']}/ok")
            self.end_headers()
        elif self.path == "/ok":
            body = b'{"has_pages": true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args: object) -> None:
        """Quiet: the suite's output is not a web server's log."""


@pytest.fixture
def server() -> Iterator[str]:
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_redirect_is_reported_rather_than_followed(server: str) -> None:
    """The behaviour the site check is built on.

    A Surrey Pages URL answers 302 to GitLab's OAuth consent page, and
    that redirect *is* the evidence the site is published behind a login.
    Following it would return the consent page's own 200 and have the
    stage call a login-walled site publicly readable - a confident wrong
    answer in place of a correct one.
    """
    answer = fetch(f"{server}/moved")

    assert answer is not None
    assert answer.status == 302, "followed the redirect"


def test_an_ordinary_answer_carries_its_body(server: str) -> None:
    """The Pages check reads `has_pages` out of it."""
    answer = fetch(f"{server}/ok")

    assert answer is not None
    assert answer.status == 200
    assert '"has_pages": true' in answer.body


def test_a_refusal_is_an_answer(server: str) -> None:
    """404 means the host replied. It is not the same as being unable to
    ask, and the stages tell those two apart."""
    answer = fetch(f"{server}/nothing-here")

    assert answer is not None
    assert answer.status == 404


def test_being_unable_to_ask_is_not_a_status() -> None:
    """`None` is the third state, and the whole reason #374 exists: a
    probe that never ran was being read as a server saying no.

    Port 1 on localhost has nothing listening, so this is a refused
    connection rather than a slow one - no timeout to wait out.
    """
    assert fetch("http://127.0.0.1:1/", timeout=2.0) is None


def test_a_url_that_is_not_one_is_also_not_a_status() -> None:
    """Same rule, reached by a different route - a malformed URL must not
    raise out of a check that is only asking a question."""
    assert fetch("not-a-url", timeout=2.0) is None
