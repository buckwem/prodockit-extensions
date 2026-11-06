"""Keep the RemoteLabs alias repair separate from environment verification."""

import os
import shutil
import subprocess
from pathlib import Path

import markdown
import pytest
from bs4 import BeautifulSoup
from jinja2 import Environment

INSTALLATION = Path(__file__).resolve().parents[1] / "docs/installation.md"


def test_alias_fix_is_only_in_step_five() -> None:
    source = INSTALLATION.read_text(encoding="utf-8")
    verify = source.split("//// step | Verify the active environment", 1)[1].split(
        "//// step | Fix the Python alias when needed", 1
    )[0]
    repair = source.split("//// step | Fix the Python alias when needed", 1)[1].split(
        "\n////", 1
    )[0]

    assert "unalias python" not in verify
    assert "python --version" in verify
    assert "command -v python" in verify
    assert "python3 -c 'import sys; print(sys.prefix)'" in verify
    assert "follow Step 5, then repeat this check" in verify
    assert "//// step | Fix the Python alias when needed **Optional**{: .bg-green}" in source
    assert "unalias python 2>/dev/null || true" in repair
    assert "Repeat Step 4 now" in repair
    assert "future interactive Bash logins" in repair


@pytest.mark.parametrize("is_surrey", [False, True])
def test_both_variants_render_distinct_check_and_repair_steps(is_surrey: bool) -> None:
    source = INSTALLATION.read_text(encoding="utf-8")
    section = source.split("//// step | Verify the active environment", 1)[1].split(
        "\n///\n\n## Understand the project structure", 1
    )[0]
    rendered = Environment(autoescape=False).from_string(
        "/// steps\n//// step | Verify the active environment" + section + "\n///"
    ).render(is_surrey=is_surrey)
    html = markdown.markdown(
        rendered,
        extensions=["attr_list", "prodockit.steps", "pymdownx.superfences", "pymdownx.tabbed"],
    )
    soup = BeautifulSoup(html, "html.parser")
    steps = soup.select("ol.prodockit-steps > li")

    assert len(steps) == 2
    assert [step.select_one(".prodockit-step-title").get_text(" ", strip=True) for step in steps] == [
        "Verify the active environment",
        "Fix the Python alias when needed Optional",
    ]
    assert "unalias python" not in steps[0].get_text(" ", strip=True)
    assert "unalias python 2>/dev/null || true" in steps[1].get_text(" ", strip=True)
    assert ("The Surrey tabs above use python3" in steps[1].get_text(" ", strip=True)) == is_surrey


@pytest.mark.skipif(shutil.which("bash") is None, reason="Bash is not installed")
def test_documented_bashrc_command_preserves_content_and_is_repeatable(
    tmp_path: Path,
) -> None:
    source = INSTALLATION.read_text(encoding="utf-8")
    command = source.split("//// step | Fix the Python alias when needed", 1)[1].split(
        "```bash\n", 2
    )[2].split("\n```", 1)[0]
    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("export KEEP=1", encoding="utf-8")

    for _ in range(2):
        subprocess.run(
            ["bash", "-c", command],
            env={**os.environ, "HOME": str(tmp_path)},
            check=True,
        )

    assert bashrc.read_text(encoding="utf-8") == (
        "export KEEP=1\nunalias python 2>/dev/null || true\n"
    )
