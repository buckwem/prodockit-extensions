# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""macOS WeasyPrint setup is visible wherever readers run PDF-backed checks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPLE_SILICON_EXPORT = "export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib"
PORTABLE_EXPORT = 'export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib'
SYMPTOM = "cannot load library 'libgobject-2.0-0'"


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_development_setup_precedes_pytest_with_the_macos_library_path() -> None:
    guide = _text("docs/devcons/development.md")

    assert PORTABLE_EXPORT in guide
    assert SYMPTOM in guide
    assert guide.index(PORTABLE_EXPORT) < guide.index("pytest")


def test_release_gates_are_self_contained_on_macos() -> None:
    guide = _text("docs/devcons/releasing.md")

    assert APPLE_SILICON_EXPORT in guide
    assert SYMPTOM in guide
    assert "described in\n[Contributing]" not in guide


def test_public_pdf_requirements_explain_the_macos_loader_failure() -> None:
    guide = _text("docs/pdf.md")

    assert APPLE_SILICON_EXPORT in guide
    assert SYMPTOM in guide
    assert "brew install pango" in guide
