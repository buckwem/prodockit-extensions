# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Standalone command for the phased replacement of ``pdk boot``.

``prodockit bootstrap`` and ``pdk boot`` remain registered on the legacy
command group. This command has its own Click command object and activates
the phased behaviour profile only for the duration of its invocation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import click

from prodockit.cli import bootstrap as _legacy_command
from prodockit.cli import pdkboot_mode


def _run(**kwargs: Any) -> None:
    with pdkboot_mode():
        assert _legacy_command.callback is not None
        _legacy_command.callback(**kwargs)


main = click.Command(
    name="pdkboot",
    callback=_run,
    params=deepcopy(_legacy_command.params),
    help=_legacy_command.help,
    epilog=_legacy_command.epilog,
    context_settings=dict(_legacy_command.context_settings),
)
for parameter in main.params:
    if isinstance(parameter, click.Option) and parameter.name == "config_file":
        parameter.help = (
            ".pdkboot.toml is the default in the current directory. "
            "Pass another pdkboot config path explicitly."
        )

__all__ = ["main"]
