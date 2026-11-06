# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Small, deterministic macro module used only by the rendering catalogue."""

from prodockit.zensical_macros import define_env as define_prodockit_env


def define_env(env) -> None:  # type: ignore[no-untyped-def]
    """Expose one stable value whose rendered result can be asserted."""
    define_prodockit_env(env)
    env.variables["catalogue_phase"] = "Phase 4 macro output"
