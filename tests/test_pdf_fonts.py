# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

import subprocess
from types import SimpleNamespace

import pytest

from prodockit.bootstrap.model import MACOS, UBUNTU, WINDOWS, CommandResult, Status
from prodockit.bootstrap.stages import _check_pandoc, _pdf_font_evidence
from prodockit.pdf_fonts import inspect_fonts


@pytest.mark.parametrize("platform", [WINDOWS, UBUNTU, MACOS])
@pytest.mark.parametrize("location", ["system", "user"])
def test_fontconfig_verifies_registered_fonts_without_directory_guesses(
    tmp_path, platform, location
):
    # No guessed per-user font directory exists. The renderer's own resolver
    # reports the registered fonts, whether installed system-wide or per-user.
    calls = []

    def run(command):
        calls.append(command)
        return CommandResult(0, command[-1])

    context = SimpleNamespace(platform=platform, home=tmp_path, runner=SimpleNamespace(run=run))
    assert _pdf_font_evidence(context).status == "available"
    assert len(calls) == 2


@pytest.mark.parametrize("fallback", ["DejaVu Sans", "Inter Display", "JetBrains Mono NL"])
def test_substitute_family_is_not_accepted(fallback):
    evidence = inspect_fonts(lambda command: (0, fallback))
    assert evidence.status == "missing"
    assert "matched" in evidence.detail


@pytest.mark.parametrize("response", [(127, ""), (1, ""), (0, "")])
def test_missing_or_broken_inspection_is_unknown(response):
    evidence = inspect_fonts(lambda command: response)
    assert evidence.status == "unverified"
    assert "fontconfig" in evidence.detail


def test_timeout_is_unknown():
    def run(command):
        raise subprocess.TimeoutExpired(command, 15)

    assert inspect_fonts(run).status == "unverified"


def test_missing_font_and_unknown_font_are_both_reported():
    evidence = inspect_fonts(
        lambda command: (0, "DejaVu Sans") if command[-1] == "Inter" else (127, "")
    )
    assert evidence.status == "missing"
    assert "could not verify JetBrains Mono" in evidence.detail


def test_bootstrap_unknown_is_warning_not_verified_pass(tmp_path):
    from prodockit.bootstrap.config import BootstrapConfig
    from prodockit.bootstrap.model import GITHUB_COM, Context

    def run(command, **kwargs):
        if "pandoc" in command[0]:
            return CommandResult(0, "pandoc 3.10.1")
        if "pango" in command[0]:
            return CommandResult(0, "pango-view (pango) 1.56.3")
        return CommandResult(127)

    context = Context(BootstrapConfig(), GITHUB_COM, UBUNTU, SimpleNamespace(run=run), tmp_path)
    result = _check_pandoc(context)
    assert result.status is Status.WARNING
    assert "could not be verified" in result.detail
    assert not result.needs_work
