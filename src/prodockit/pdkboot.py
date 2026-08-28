# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Standalone command for the phased replacement of ``pdk boot``.

``prodockit bootstrap`` and ``pdk boot`` remain registered on the legacy
command group. This command has its own Click command object and activates
the phased behaviour profile only for the duration of its invocation.
"""

from __future__ import annotations

from copy import copy
from typing import Any

import click

from prodockit import __version__
from prodockit.cli import bootstrap as _legacy_command
from prodockit.cli import pdkboot_mode

_HELP = """Set up this machine and a project based on prodockit-template.

Checks all 23 stages, including the editor, Git and SSH, project checkout,
Python and Node environments, PDF tools and publishing. A stage whose goal is
already satisfied is rechecked and left alone.

With no operating-mode option this reports what it finds and changes nothing.
Use --dry-run to review exact work or --apply to perform it with confirmation,
progress and a resumable recovery report. It is specifically for projects based
on prodockit-template, not a general Zensical installer. This command uses
.pdkboot.toml and does not read or modify legacy bootstrap configuration.
"""


def _run(**kwargs: Any) -> None:
    with pdkboot_mode():
        assert _legacy_command.callback is not None
        _legacy_command.callback(**kwargs)


def _show_version(
    context: click.Context,
    _parameter: click.Parameter,
    value: bool,
) -> None:
    """Print the independently installable preview's package identity."""
    if value and not context.resilient_parsing:
        click.echo(f"pdkboot, version {__version__}")
        context.exit()


def _copy_parameter(parameter: click.Parameter) -> click.Parameter:
    """Copy a Click parameter without deep-copying Click's sentinels.

    Click parameter types and callbacks are deliberately shared.  Only the
    parameter object and its option-name lists need to be independent here,
    because pdkboot changes the copied ``--config`` help text below.  A deep
    copy fails on Python 3.10 when recent Click releases contain an enum whose
    value is an identity sentinel.
    """
    copied = copy(parameter)
    if isinstance(parameter, click.Option):
        copied.opts = list(parameter.opts)
        copied.secondary_opts = list(parameter.secondary_opts)
    return copied


main = click.Command(
    name="pdkboot",
    callback=_run,
    params=[
        click.Option(
            ["--version"],
            is_flag=True,
            is_eager=True,
            expose_value=False,
            callback=_show_version,
            help="Show the installed pdkboot package version and exit.",
        ),
        *(_copy_parameter(parameter) for parameter in _legacy_command.params),
    ],
    help=_HELP,
    epilog=_legacy_command.epilog,
    context_settings=dict(_legacy_command.context_settings),
)
for parameter in main.params:
    if isinstance(parameter, click.Option) and parameter.name == "config_file":
        parameter.help = (
            ".pdkboot.toml in the current or nearest parent directory is the default. "
            "Pass another pdkboot config path explicitly."
        )

__all__ = ["main"]
