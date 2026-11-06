# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Exercise real pipe decoding without requiring Pandoc or WeasyPrint."""

import subprocess
import sys
from pathlib import Path

import pytest

from prodockit.pdf.build import Page, PdfBuildError, build_pdf
from prodockit.pdf.source_bundle import SourceBundleError, build_source_bundle


@pytest.mark.parametrize("builder", ["document", "source-bundle"])
@pytest.mark.parametrize("returncode", [0, 43])
@pytest.mark.parametrize("message", [b"renderer detail \x85 end", "renderer detail café end".encode()])
def test_pdf_subprocess_diagnostics_do_not_mask_renderer_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    builder: str, returncode: int, message: bytes,
) -> None:
    # Run Python instead of a native renderer, but retain the production
    # capture/decoding options. No shell scripts: this also runs on Windows,
    # where subprocess drains text pipes in background reader threads.
    real_run = subprocess.run
    captured = []
    output = tmp_path / "report.pdf"
    script = (
        "import pathlib, sys; "
        "message = bytes.fromhex(sys.argv[1]); "
        "sys.stdout.buffer.write(message); "
        "sys.stderr.buffer.write(message); "
        "pathlib.Path(sys.argv[2]).write_bytes(b'%PDF-1.4 stub'); "
        "sys.exit(int(sys.argv[3]))"
    )

    def renderer_run(command, **kwargs):
        assert command[0] == "test-renderer"
        result = real_run(
            [sys.executable, "-c", script, message.hex(), str(output), str(returncode)],
            **kwargs,
        )
        captured.append(result)
        return result

    monkeypatch.setattr(subprocess, "run", renderer_run)

    def build():
        if builder == "document":
            return build_pdf(
                [Page(docs_rel_path="index.md", html="<h1>Report</h1>", is_index=True)],
                str(output), pandoc_executable="test-renderer",
            )
        (tmp_path / "index.md").write_text("# Report\n", encoding="utf-8")
        return build_source_bundle(
            str(output), root=str(tmp_path), files=["index.md"],
            weasyprint_executable="test-renderer",
        )

    expected = message.decode("utf-8", errors="replace")
    if returncode:
        error_type = PdfBuildError if builder == "document" else SourceBundleError
        # The stub even leaves an output file on failure: its existence must
        # never override the renderer's failure status.
        with pytest.raises(error_type) as error:
            build()
        assert error.value.returncode == returncode
        assert error.value.stderr == expected
        assert "status 43" in str(error.value)
    else:
        build()
    assert output.read_bytes().startswith(b"%PDF")
    assert len(captured) == 1
    assert captured[0].returncode == returncode
    assert captured[0].stdout == expected
    assert captured[0].stderr == expected
    printed = capsys.readouterr()
    assert "renderer detail" not in printed.out + printed.err
