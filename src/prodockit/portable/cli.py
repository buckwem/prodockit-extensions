# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Lazy CLI dispatch: the default path remains the ordinary Zensical CLI."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from prodockit.portable import PortableError
from prodockit.project_config import load_project_config

F = TypeVar("F", bound=Callable[..., Any])


def register_commands(group: click.Group) -> None:
    def config_option(function: F) -> F:
        return click.option(
            "--config-file",
            "-f",
            default="zensical.toml",
            type=click.Path(exists=True, dir_okay=False),
        )(function)

    def pandoc_option(function: F) -> F:
        return click.option(
            "--pandoc",
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            help="Explicit Pandoc for portable bibliography preparation.",
        )(function)

    def portable(ctx: click.Context) -> bool:
        return bool(ctx.find_root().obj.get("portable"))

    def require_portable(ctx: click.Context) -> None:
        if not portable(ctx):
            raise click.UsageError("use pdk --portable (or pdk -p) for this experimental command")

    @group.command("prepare")
    @config_option
    @pandoc_option
    @click.pass_context
    def prepare(ctx: click.Context, config_file: str, pandoc: Path | None) -> None:
        """Prepare an isolated source generation without building it."""
        require_portable(ctx)
        from prodockit.portable.project import prepare as prepare_project

        try:
            result = prepare_project(config_file, pandoc=pandoc)
        except click.exceptions.Exit:
            raise
        except (ValueError, OSError, RuntimeError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Prepared configuration: {result.config}")
        click.echo(f"Manifest: {result.manifest}")

    @group.command("build")
    @config_option
    @pandoc_option
    @click.option("--clean", "-c", is_flag=True)
    @click.option("--strict", "-s", is_flag=True)
    @click.pass_context
    def build(
        ctx: click.Context, config_file: str, pandoc: Path | None, clean: bool, strict: bool
    ) -> None:
        """Build normally, or prepare and validate with --portable/-p."""
        from prodockit.portable.project import _environment, command
        from prodockit.portable.project import build as build_project

        try:
            if portable(ctx):
                result = build_project(config_file, pandoc=pandoc, clean=clean)
                click.echo(f"Portable site: {result.site}")
                click.echo(f"Manifest: {result.manifest}")
            else:
                if pandoc is not None:
                    raise PortableError("--pandoc applies only to --portable preparation")
                config = load_project_config(config_file)
                options = (["--clean"] if clean else []) + (["--strict"] if strict else [])
                ctx.exit(
                    subprocess.run(
                        command(config.path, "build", *options), cwd=config.root,
                        env=_environment(config.path), check=False,
                    ).returncode
                )
        except click.exceptions.Exit:
            raise
        except (ValueError, OSError, RuntimeError) as error:
            raise click.ClickException(str(error)) from error

    @group.command("serve")
    @config_option
    @pandoc_option
    @click.option("--dev-addr", "-a", default="127.0.0.1:8000")
    @click.pass_context
    def serve(ctx: click.Context, config_file: str, pandoc: Path | None, dev_addr: str) -> None:
        """Preview normally, or supervise prepared generations with --portable."""
        from prodockit.portable.project import _environment, _stop, command
        from prodockit.portable.project import serve as serve_project

        try:
            if portable(ctx):
                serve_project(config_file, pandoc=pandoc, address=dev_addr, report=click.echo)
            else:
                if pandoc is not None:
                    raise PortableError("--pandoc applies only to --portable preparation")
                config = load_project_config(config_file)
                process = subprocess.Popen(
                    command(config.path, "serve", "--dev-addr", dev_addr), cwd=config.root,
                    env=_environment(config.path),
                )
                try:
                    ctx.exit(process.wait())
                finally:
                    _stop(process)
        except KeyboardInterrupt:
            pass
        except click.exceptions.Exit:
            raise
        except (ValueError, OSError, RuntimeError) as error:
            raise click.ClickException(str(error)) from error

    @group.command("validate")
    @click.option(
        "--manifest", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path)
    )
    @click.pass_context
    def validate(ctx: click.Context, manifest: Path) -> None:
        """Validate an explicitly selected portable generation and its inputs."""
        require_portable(ctx)
        from prodockit.portable.project import Prepared
        from prodockit.portable.project import validate as validate_project

        root = manifest.resolve().parent
        try:
            validate_project(Prepared(root / "zensical.toml", manifest.resolve(), root / "site"))
        except (ValueError, OSError, RuntimeError) as error:
            raise click.ClickException(str(error)) from error
        click.echo("Portable output and original inputs validated.")
