# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Opt-in, deliberately bounded source-preparation prototype (issue #1072)."""


class PortableError(ValueError):
    """The prototype cannot prepare this project without changing its meaning."""
