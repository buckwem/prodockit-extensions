# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Bounded source compilation, public CLI integration and reversible switching."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup
from click.testing import CliRunner
from PIL import Image

from prodockit.cli import main
from prodockit.portable import PortableError
from prodockit.portable.compiler import scan
from prodockit.portable.project import build, prepare, validate


@pytest.fixture
def portable_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = Path(__file__).resolve().parents[1] / "src"
    monkeypatch.setenv("PYTHONPATH", str(source))
    config = tmp_path / "zensical.toml"
    config.write_text(
        """[project]
site_name = "Portable prototype"
site_url = "https://example.test/manual/"
nav = [{Home = "index.md"}, {Guide = "guide/install.md"}, {References = "references.md"}]
[project.theme]
font = false
[project.markdown_extensions.attr_list]
[project.markdown_extensions.toc]
permalink = true
[project.markdown_extensions.tables]
[project.markdown_extensions."prodockit.headings"]
numbering = "continuous"
[project.markdown_extensions."prodockit.refs"]
[project.markdown_extensions.pymdownx.superfences]
custom_fences = [
  {name = "image-hotspots", class = "image-hotspots", format = "prodockit.image_hotspots.format_hotspots"},
  {name = "mermaid", class = "mermaid"},
]
""",
        encoding="utf-8",
    )
    (tmp_path / "docs/guide").mkdir(parents=True)
    (tmp_path / "docs/assets").mkdir()
    (tmp_path / "docs/index.md").write_text(
        r"""# Home {: #home .unnumbered }

See \ref{installation} and \autoref{installation}.

Literal `\ref{not-a-target}` and escaped \\ref{not-a-target}.

```markdown
\ref{also-not-a-target}
```

| Name | Value |
| --- | --- |
| Example | Unchanged table |
""",
        encoding="utf-8",
    )
    (tmp_path / "docs/guide/install.md").write_text(
        r"""# Setup

## Installation

Same page: \ref{installation}. Back: \ref{home}.

```image-hotspots
image: ../assets/map.png
alt: Example map
hotspots:
  - {label: Installation, href: '#installation', rect: [0, 0, 100, 50]}
  - {label: Home, href: '../index.md#home', rect: [100, 50, 100, 50]}
```
""",
        encoding="utf-8",
    )
    (tmp_path / "docs/references.md").write_text(
        "# References {: .unnumbered }\n", encoding="utf-8"
    )
    Image.new("RGB", (200, 100)).save(tmp_path / "docs/assets/map.png")
    return config


def _article(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def test_preparation_is_selective_and_deterministic(portable_project: Path) -> None:
    root = portable_project.parent
    original = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    first = prepare(str(portable_project))
    second = prepare(str(portable_project))
    assert first.config != second.config  # Independent, concurrent-safe generations.
    for name in ("index.md", "guide/install.md", "references.md"):
        one = (first.config.parent / "docs" / name).read_text()
        assert one == (second.config.parent / "docs" / name).read_text()
    source = (first.config.parent / "docs/index.md").read_text()
    assert (
        '<a class="prodockit-ref" href="guide/install.md#installation">1.1 Installation</a>'
        in source
    )
    assert "Literal `\\ref{not-a-target}`" in source
    assert r"escaped \\ref{not-a-target}" in source
    assert "| Example | Unchanged table |" in source
    generated = first.config.read_text()
    assert "prodockit.refs" not in generated
    assert "format_hotspots" not in generated
    assert "mermaid" in generated
    assert "tables" in generated
    for path, contents in original.items():
        assert Path(path).read_bytes() == contents
    assert not (root / "site").exists()


def test_build_without_private_context_and_switch_back(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = portable_project.parent
    runner = CliRunner()
    result = runner.invoke(main, ["build", "-f", str(portable_project), "--clean", "--strict"])
    assert result.exit_code == 0, result.output
    original = _article(root / "site/index.html").select_one("a.prodockit-ref")
    assert original is not None
    # A separate Python startup hook makes private Prodockit context use fatal
    # in the child CLI as well as in preparation. Zensical may use its own API.
    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text("""import prodockit._zensical_page_context as context
def forbidden(*args, **kwargs):
    raise AssertionError("private page context was called")
context._rendering_context = forbidden
""")
    monkeypatch.setenv("PYTHONPATH", str(guard) + os.pathsep + os.environ["PYTHONPATH"])
    import prodockit._zensical_page_context as context

    with monkeypatch.context() as isolated:
        isolated.setattr(
            context, "_rendering_context", lambda *_: pytest.fail("private page context was called")
        )
        prepared = build(str(portable_project))
    portable = _article(prepared.site / "index.html")
    ref = portable.select_one("a.prodockit-ref")
    assert ref is not None
    assert (ref["href"], ref.get_text()) == (original["href"], original.get_text())
    assert portable.select_one("table") is not None
    assert (
        _article(prepared.site / "guide/install/index.html").select_one("figure.pdk-hotspots")
        is not None
    )
    assert json.loads((prepared.site / ".pdk-build.json").read_text())["mode"] == "portable"
    # Switching back never consumes the prepared tree, even if it is damaged.
    (prepared.config.parent / "docs/index.md").write_text("BROKEN PREPARED SOURCE")
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src"))
    result = runner.invoke(main, ["build", "-f", str(portable_project), "--clean", "--strict"])
    assert result.exit_code == 0, result.output
    assert (
        _article(root / "site/index.html").select_one("a.prodockit-ref").get_text()
        == "1.1 Installation"
    )


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="requires real Pandoc citeproc")
def test_bibliography_uses_citeproc_before_zensical_indexes(portable_project: Path) -> None:
    root = portable_project.parent
    with portable_project.open("a") as config:
        config.write(
            '\n[project.markdown_extensions."prodockit.bibliography"]\nbib_file = "references.bib"\n'
        )
    (root / "references.bib").write_text(
        "@book{example, title={A distinctive research title}, author={Doe, Jane}, year={2025}}\n"
    )
    with (root / "docs/index.md").open("a") as page:
        page.write("\nA citation: \\cite{example}.\n")
    with (root / "docs/references.md").open("a") as page:
        page.write("\n## Reference list\n\n\\bibliography\n")
    prepared = build(str(portable_project), pandoc=Path(shutil.which("pandoc")))
    soup = _article(prepared.site / "references/index.html")
    assert soup.find(id="ref-example") is not None
    assert soup.select_one('nav a[href="#reference-list"]') is not None
    link = _article(prepared.site / "index.html").select_one(".prodockit-bib-cite a")
    assert link["href"] == "references/#ref-example"
    assert (
        "a distinctive research title"
        in (prepared.config.parent / "docs/references.md").read_text().lower()
    )


def test_default_wrapper_selects_nonstandard_configuration(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = portable_project.parent
    config = portable_project.rename(root / "custom.toml")
    source = root / "docs/index.md"
    source.write_text(source.read_text().replace("#home .unnumbered", "#home"))
    # An inherited override must not defeat the explicit per-invocation choice.
    monkeypatch.setenv("PRODOCKIT_CONFIG_FILE", str(root / "missing.toml"))
    result = CliRunner().invoke(main, ["build", "-f", str(config), "--strict"])
    assert result.exit_code == 0, result.output
    assert (
        _article(root / "site/index.html").select_one("a.prodockit-ref").get_text()
        == "2.1 Installation"
    )
    assert os.environ["PRODOCKIT_CONFIG_FILE"] == str(root / "missing.toml")


@pytest.mark.parametrize("prefix", [["--portable"], ["-p"]])
def test_cli_aliases_and_opt_in(portable_project: Path, prefix: list[str]) -> None:
    result = CliRunner().invoke(main, [*prefix, "prepare", "-f", str(portable_project)])
    assert result.exit_code == 0, result.output
    assert "Prepared configuration:" in result.output
    assert CliRunner().invoke(main, ["prepare", "-f", str(portable_project)]).exit_code == 2
    assert CliRunner().invoke(main, [*prefix, "pdf"]).exit_code == 2


@pytest.mark.parametrize(
    "text",
    [
        "- A nested \\ref{target}.\n",
        "# Title\n\n{{ generated_heading() }}\n",
        '# Title\n\n--8<-- "snippet.md"\n',
        "# Title\n\n\\pagebibliography\n",
        "# Title\n\n\\citeref{key}\n",
        "Setext\n======\n",
        "# Title\n\n!!! note\n    \\ref{target}\n",
    ],
)
def test_refuses_unproved_constructs(text: str) -> None:
    with pytest.raises(PortableError):
        scan("guide/page.md", text)


def test_stale_inputs_and_missing_output_are_detected(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    (prepared.site / "guide/install/index.html").unlink()
    with pytest.raises(PortableError, match="build is incomplete"):
        validate(prepared)
    source = portable_project.parent / "docs/index.md"
    source.write_text(source.read_text() + "\nNew content\n")
    with pytest.raises(PortableError, match="stale"):
        validate(prepared)


def test_unresolved_target_does_not_replace_existing_output(portable_project: Path) -> None:
    good = build(str(portable_project))
    previous = (good.site / "index.html").read_bytes()
    source = portable_project.parent / "docs/index.md"
    source.write_text(source.read_text().replace("ref{installation}", "ref{missing}"))
    with pytest.raises(PortableError, match=r"index\.md:3: unresolved reference"):
        build(str(portable_project))
    assert (good.site / "index.html").read_bytes() == previous


def test_generated_input_tampering_is_detected(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    (prepared.config.parent / "docs/index.md").write_text("changed")
    with pytest.raises(PortableError, match="prepared input changed"):
        validate(prepared)


def test_wrong_reference_label_is_rejected(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    page = prepared.site / "index.html"
    page.write_text(page.read_text().replace(">1.1 Installation</a>", ">??</a>"))
    with pytest.raises(PortableError, match="label changed"):
        validate(prepared)


def test_image_dependency_invalidates_output(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    Image.new("RGB", (400, 200)).save(portable_project.parent / "docs/assets/map.png")
    with pytest.raises(PortableError, match="stale"):
        validate(prepared)


def test_heading_rendering_drift_is_rejected(portable_project: Path) -> None:
    prepared = build(str(portable_project))
    page = prepared.site / "guide/install/index.html"
    page.write_text(
        page.read_text().replace('id="installation">Installation', 'id="installation">Changed')
    )
    with pytest.raises(PortableError, match="differs from its collected text"):
        validate(prepared)


@pytest.mark.parametrize("replacement_fails", [False, True])
def test_preview_handles_edits_during_startup_and_failed_replacement(
    portable_project: Path, monkeypatch: pytest.MonkeyPatch, replacement_fails: bool
) -> None:
    from prodockit.portable import project

    starts = []
    processes = []
    reports = []
    source = portable_project.parent / "docs/guide/install.md"

    def start(prepared, address):
        starts.append(prepared)
        if len(starts) == 1:
            # The first validated generation is already built at this point.
            source.write_text(source.read_text().replace(
                "## Installation", "## During startup {: #installation }"
            ))
        elif len(starts) == 2 and replacement_fails:
            raise PortableError("replacement preview could not start")
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        processes.append(process)
        return process

    def report(message):
        reports.append(message)
        if "updated" in message or "Keeping" in message:
            raise KeyboardInterrupt

    polls = 0

    def tick(_):
        nonlocal polls
        polls += 1
        if polls > 2:
            pytest.fail("the edit during startup was missed")

    monkeypatch.setattr(project, "_start", start)
    monkeypatch.setattr(project.time, "sleep", tick)
    with pytest.raises(KeyboardInterrupt):
        project.serve(str(portable_project), report=report)
    assert len(starts) == (3 if replacement_fails else 2)
    assert "During startup" in (starts[1].site / "guide/install/index.html").read_text()
    if replacement_fails:
        assert starts[-1] == starts[0]
        assert "replacement preview could not start" in reports[-1]
    for process in processes:
        process.terminate.assert_called_once()
    assert not (portable_project.parent / ".pdk/portable/lock").exists()


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX SIGINT acceptance; Windows lifecycle needs separate qualification",
)
def test_live_preview_rebuild_recovery_and_switching(portable_project: Path) -> None:
    root = portable_project.parent
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    address = f"127.0.0.1:{port}"

    def fetch() -> str:
        try:
            with urllib.request.urlopen(f"http://{address}/", timeout=0.5) as response:
                soup = BeautifulSoup(response.read(), "html.parser")
            link = soup.select_one("a.prodockit-ref")
            return link.get_text() if link is not None else ""
        except (OSError, urllib.error.URLError):
            return ""

    def await_value(expected: str, process: subprocess.Popen, log: Path) -> None:
        until = time.monotonic() + 25
        while time.monotonic() < until:
            assert process.poll() is None, log.read_text()
            if fetch() == expected:
                return
            time.sleep(0.1)
        pytest.fail(f"preview did not reach {expected!r}: {log.read_text()}")

    source = root / "docs/guide/install.md"
    log = root / "preview.log"
    with log.open("w") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "prodockit",
                "-p",
                "serve",
                "-f",
                str(portable_project),
                "-a",
                address,
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            await_value("1.1 Installation", process, log)
            source.write_text(
                source.read_text().replace(
                    "## Installation", "## Updated installation {: #installation }"
                )
            )
            await_value("1.1 Updated installation", process, log)
            home = root / "docs/index.md"
            original = home.read_text()
            home.write_text(original.replace("ref{installation}", "ref{missing}"))
            until = time.monotonic() + 10
            while (
                time.monotonic() < until and "Keeping the previous preview" not in log.read_text()
            ):
                time.sleep(0.1)
            assert "Keeping the previous preview" in log.read_text()
            assert fetch() == "1.1 Updated installation"
            home.write_text(original)
            source.write_text(
                source.read_text().replace("Updated installation", "Final installation")
            )
            await_value("1.1 Final installation", process, log)
        finally:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
        assert process.returncode == 0, log.read_text()
    assert not (root / ".pdk/portable/lock").exists()
    # The same original project can immediately be served through the other path.
    with log.open("w") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "prodockit",
                "serve",
                "-f",
                str(portable_project),
                "-a",
                address,
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            await_value("1.1 Final installation", process, log)
        finally:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
        assert process.returncode == 0, log.read_text()
