# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""This project's own Zensical macros - just re-exports
prodockit.zensical_macros.define_env(), since this site has no
institution branding or other project-specific macro of its own to add.

Called directly here rather than via zensical.toml's documented
`modules = [...]` extension option: that option makes Zensical also watch
the module's file for auto-reload, and if the module lives outside the
project directory (true for any pip-installed package, e.g. in CI where
dependencies install outside the checkout) that watch triggers an upstream
panic in `zensical build`'s file watcher (zensical/zensical#823) - the same
workaround prodockit-template/prodockit-userguide's own macros.py use.
Calling it as a plain import instead gives identical behaviour without
that second watch registration."""

from prodockit.zensical_macros import define_env as define_env
