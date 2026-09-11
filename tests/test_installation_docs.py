# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""The requirements documentation against what the project actually declares.

The requirements table is read by people setting a machine up and edited
by nobody, which is the shape of documentation that goes quietly wrong.
It had `Markdown (>= 3.4)` long after the real floor moved to 3.10.3,
and omitted `pymdown-extensions` entirely - a dependency whose class
shapes `prodockit.pdf` matches on (prodockit-extensions#372).

Neither would break a build. Both would send a reader to install the
wrong thing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALLATION = REPO / "docs" / "installation.md"
REQUIREMENTS = REPO / "docs" / "requirements-dependencies.md"
PYPROJECT = REPO / "pyproject.toml"
ADOPTION = REPO / "docs" / "adopt.md"
BOOTSTRAP_GUIDE = REPO / "docs" / "devcons" / "bootstrap.md"
FIRST_SITE = REPO / "docs" / "getting-started.md"
PUBLISHING = REPO / "docs" / "publishing.md"
MANUAL_INSTALL = REPO / "docs" / "manual-install.md"
POWERSHELL_POLICY = "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned"


def test_adoption_routes_refresh_environment_between_apply_and_build():
    for page in (FIRST_SITE, ADOPTION):
        text = page.read_text(encoding="utf-8")
        refresh = text.index("//// step | Refresh the project environment")
        assert text.index("adopt --apply") < refresh
        section = text[refresh:].split("\n////\n", 1)[0]
        assert "source .venv/bin/activate" in section
        assert r".\.venv\Scripts\Activate.ps1" in section
        assert "Windows Terminal" in section
        assert "macOS" in section
        assert "Linux (Ubuntu)" in section
        assert "zensical build" in text[refresh:]


if sys.version_info >= (3, 11):  # pragma: no cover - version-gated import
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def _declared() -> dict[str, str]:
    """Every runtime dependency and its floor, from `pyproject.toml`."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    wanted = list(project["dependencies"])
    # The index extra is documented in the same table, marked as optional.
    wanted += project.get("optional-dependencies", {}).get("index", [])

    floors: dict[str, str] = {}
    for spec in wanted:
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*>=\s*([0-9][\w.]*)", spec)
        if match:
            floors[match.group(1).lower()] = match.group(2)
    return floors


def test_every_declared_dependency_is_documented() -> None:
    """A dependency absent from the table is one a reader never installs
    deliberately - it arrives silently with `pip`, and its version is
    then nobody's decision."""
    page = REQUIREMENTS.read_text(encoding="utf-8").lower()

    missing = [name for name in _declared() if name not in page]

    assert not missing, f"not mentioned in requirements-dependencies.md: {missing}"


def test_the_documented_floors_match_the_declared_ones() -> None:
    """The failure this exists for: the page said `Markdown (>= 3.4)`
    while `pyproject.toml` said 3.10.3.

    Read as "the page names this floor somewhere for this package"
    rather than by parsing the table's shape, so the table can be
    rewritten freely - it is the *number* that must not drift.
    """
    page = REQUIREMENTS.read_text(encoding="utf-8").lower()
    wrong = []
    for name, floor in _declared().items():
        # The line that mentions the package must carry its floor.
        lines = [line for line in page.splitlines() if name in line]
        if not any(floor in line for line in lines):
            wrong.append(f"{name}: pyproject says >= {floor}, page does not")

    assert not wrong, "\n".join(wrong)


def test_pandoc_and_weasyprint_are_not_filed_as_the_same_kind_of_thing() -> None:
    """One is a `pip install` away and the other is not.

    Both used to be labelled "(external binary)". A reader who treats
    them alike goes looking for a pandoc package that does not exist, or
    misses a weasyprint one that does.
    """
    page = REQUIREMENTS.read_text(encoding="utf-8")

    assert "A Python package, but not a dependency of prodockit" in page
    assert "Genuinely not a Python package" in page


def test_the_versions_bootstrap_enforces_are_the_ones_documented() -> None:
    """`prodockit bootstrap` refuses a pandoc below `PANDOC_MIN_MAJOR`
    and installs `PANDOC_VERSION`; it wants Node `NODE_MAJOR`. A reader
    following this page should end up with a machine bootstrap agrees
    with, rather than one it then argues about.
    """
    from prodockit.bootstrap.stages import NODE_MAJOR, PANDOC_MIN_MAJOR, PANDOC_VERSION

    page = REQUIREMENTS.read_text(encoding="utf-8")

    assert f">= {PANDOC_MIN_MAJOR}" in page, "the pandoc floor is not stated"
    assert PANDOC_VERSION in page, "the pinned pandoc release is not stated"
    assert f"Node >= {NODE_MAJOR}" in page, "the Node major version is not stated"


def test_every_documented_powershell_activation_sets_the_execution_policy() -> None:
    """Keep every copyable PowerShell activation sequence usable on clean Windows."""
    paths = [REPO / "CONTRIBUTING.md", *(REPO / "docs").rglob("*.md")]
    paths.append(REPO / "tests" / "adopt_install" / "README.md")
    checked = 0

    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            # Audit executable lines, not inline-code definition-list terms.
            if line.strip() != r".\.venv\Scripts\Activate.ps1":
                continue
            checked += 1
            assert index and lines[index - 1].strip() == POWERSHELL_POLICY, (
                f"{path.relative_to(REPO)}:{index + 1} activates PowerShell without first "
                "setting the CurrentUser execution policy"
            )

    assert checked > 1, "the documentation activation audit did not find every usage"


def test_installation_preparation_is_shared_by_later_routes() -> None:
    preparation_page = INSTALLATION.read_text(encoding="utf-8")
    preparation = preparation_page[
        preparation_page.index("## Prepare Python and its environment") :
    ]

    for command in (
        "brew --version",
        "brew install python@3.14",
        '"$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv',
        "py -3.14 --version",
        "py -3.14 -m venv .venv",
        "sudo apt install python3.14 python3.14-venv python3-pip",
        "python3.14 -m venv .venv",
        "python --version",
    ):
        assert command in preparation

    assert "[:simple-homebrew: Install Homebrew](https://brew.sh/)" in preparation
    assert ".homebrew-button" in preparation
    assert "close Terminal completely and reopen" in preparation
    assert "current terminal will not know about the new `brew` command" in preparation

    assert preparation.count("//// step | ") == 4
    assert preparation.count('=== ":material-apple: macOS"') == 5
    assert preparation.count('=== ":fontawesome-brands-windows: Windows"') == 5
    assert preparation.count('=== ":material-linux: Linux (Ubuntu)"') == 5

    for route in (ADOPTION, BOOTSTRAP_GUIDE, FIRST_SITE):
        page = route.read_text(encoding="utf-8")
        assert "installation.md#installation-preparation" in page
        assert "Open section 3.1 to prepare your environment" in page
        assert '.md-button--primary target="_blank" rel="noopener"' in page

    assert "the directory that holds all your repositories" in preparation
    assert "| Route |" not in preparation
    assert "Create a repositories directory if this is your first one" in preparation
    assert "mkdir -p ~/repos" in preparation
    assert "Set-Location ~\\repos" in preparation
    assert "++tab++" in preparation

    assert "Restart Windows after installation" not in preparation_page
    assert "RESTART YOUR TERMINAL — WINDOWS SETTINGS HAVE CHANGED" not in preparation_page
    assert "## Install Prodockit from PyPI" not in preparation_page
    assert "## Enabling an extension" not in preparation_page

    publishing = PUBLISHING.read_text(encoding="utf-8")
    assert "## Configure Prodockit features" in publishing
    assert "## Choose your features" in publishing
    assert "### Authoring extensions" in publishing
    assert "### What is *not* an extension" in publishing


def test_docs_enable_zensicals_standard_pymdown_extensions() -> None:
    config = tomllib.loads((REPO / "zensical.toml").read_text(encoding="utf-8"))
    pymdownx = config["project"]["markdown_extensions"]["pymdownx"]
    expected = {
        "arithmatex",
        "betterem",
        "caret",
        "details",
        "emoji",
        "highlight",
        "inlinehilite",
        "keys",
        "magiclink",
        "mark",
        "smartsymbols",
        "snippets",
        "superfences",
        "tabbed",
        "tasklist",
        "tilde",
    }

    assert expected <= pymdownx.keys()
    assert pymdownx["highlight"]["line_spans"] == "__span"
    assert pymdownx["highlight"]["pygments_lang_class"] is True
    assert pymdownx["tabbed"]["combine_header_slug"] is True
    assert pymdownx["tasklist"]["custom_checkbox"] is True


def test_reader_facing_homebrew_install_routes_link_to_the_official_installer() -> None:
    button = "[:simple-homebrew: Install Homebrew](https://brew.sh/)"

    routes = (
        INSTALLATION,
        REPO / "docs" / "extensions" / "bibliography.md",
        REPO / "docs" / "pdf.md",
    )
    for path in routes:
        page = path.read_text(encoding="utf-8")
        assert button in page, f"{path.relative_to(REPO)} lacks the Homebrew installer action"


def test_adoption_continues_after_shared_preparation() -> None:
    page = ADOPTION.read_text(encoding="utf-8")

    assert "pip3 install --upgrade prodockit" in page
    assert page.count("pip install --upgrade prodockit") == 2

    assert "MkDocs" not in page

    review_start = page.index("### Stage 1 — Review the existing project")
    review_end = page.index("### Stage 2 — Preview and apply")
    review = page[review_start:review_end]
    assert review.count("//// step | ") == 4
    assert "Ask for an assessment" not in review
    apply_step = page.split("//// step | Apply the reviewed stages", 1)[1].split("////", 1)[0]
    assert "command-output-anatomy.svg" in apply_step
    assert "//// step | Prepare Python and the setup environment" in review
    assert "//// step | Enter the project and prepare its environment" in review
    assert "//// step | Choose optional renderers" in review
    assert 'python3.14" -m venv --clear .venv' in review
    assert "py -3.14 -m venv --clear .venv" in review
    assert "python3.14 -m venv --clear .venv" in review

    assert "### Stage 3 — Build and review" in page

    resume = page[
        page.index("//// step | Resume an interrupted installation") : page.index(
            "//// step | Work from prepared caches when offline"
        )
    ]
    assert "Skip this step when Apply completed successfully" in resume
    assert '=== ":material-apple: macOS"' in resume
    assert '=== ":fontawesome-brands-windows: Windows"' in resume
    assert '=== ":material-linux: Linux (Ubuntu)"' in resume
    assert "python --version\nprodockit adopt --apply" in resume


def test_first_site_proves_zensical_before_adopting_prodockit() -> None:
    page = FIRST_SITE.read_text(encoding="utf-8")

    assert "installation.md#installation-preparation" in page
    assert "Unlike the template-site route" in page
    assert page.count("//// step | ") == 27
    stages = re.split(r"(?m)^### Stage \d+[ab]? —", page)[1:]
    assert stages[0].count("//// step | ") == 0
    assert stages[1].count("//// step | ") == 3
    assert stages[2].count("//// step | ") == 4
    assert stages[3].count("//// step | ") == 3
    assert "//// step | Enter the project root directory" in stages[3]
    assert "//// step | Create a virtual environment **Optional**" in stages[3]
    assert "//// step | Activate the virtual environment" in stages[3]
    assert "//// step | Install Prodockit" in stages[4]
    existing_site = stages[3]
    assert "cd ~/repos/prodockit-project" in existing_site
    assert "If `cd` fails, stop" in existing_site
    assert existing_site.count("    deactivate\n    cd ~/repos/prodockit-project\n") == 3
    assert "another name" in existing_site
    assert page.count("/// tree") == 0
    assert page.count("/// steps") == 8
    assert stages[5].count("//// step | ") == 2
    assert page.index("### Stage 7a — Publish the website **Clean**") < page.index(
        "### Stage 7b — Review the project changes **Update**"
    )

    preparation = INSTALLATION.read_text(encoding="utf-8")
    structure = preparation[
        preparation.index("## Understand the project structure") : preparation.index(
            "## Continue with an installation route"
        )
    ]
    assert structure.count("/// tree") == 3
    routes = preparation[preparation.index("## Continue with an installation route") :]
    assert "grid cards installation-route-grid" in routes
    assert routes.count(".md-button--primary .installation-route-button") == 4
    assert "### A clean Zensical site" in structure
    assert "### The site after adding Prodockit" in structure
    assert "### A site created from prodockit-template" in structure
    for stylesheet in (
        "pdk.css",
        "template.css",
        "extra.css",
        "pdk-pdf.css",
        "print.css",
    ):
        assert stylesheet in structure
    assert structure.count("USER-MANAGED") == 6
    assert "`pdk.css` first and `extra.css` last" in structure
    assert "`pdk-pdf.css` followed by `print.css`" in structure
    assert structure.count("pdk.js - managed Prodockit website behaviour") == 2
    assert structure.count("mathjax.js - generated Prodockit") == 2
    assert structure.count("tex-svg-full.js - vendor MathJax browser bundle") == 2
    assert structure.count("extra.js - USER-MANAGED website behaviour") == 2
    assert structure.count("LICENSE - vendor licence supplied with MathJax") == 2
    assert page.count("installation.md#installation-project-structure") == 2
    for phase in (
        "### Stage 1 — Prepare the setup environment",
        "### Stage 2 — Prepare the project environment",
        "### Stage 3a — Install and prove Zensical",
        "### Stage 3b — Return to Zensical environment",
        "### Stage 4 — Add and configure Prodockit",
        "### Stage 5 — Verify the adopted website",
        "### Stage 6 — Add downloadable outputs",
    ):
        assert phase in page

    prepare_python = page.index("### Stage 1 — Prepare the setup environment")
    prepare_directory = page.index("//// step | Prepare the empty project directory")
    install_zensical = page.index("//// step | Install Zensical")
    create_zensical = page.index("//// step | Create the Zensical site")
    build_zensical = page.index("//// step | Build the plain Zensical site")
    serve_zensical = page.index("//// step | Preview the plain Zensical site")
    install_prodockit = page.index("//// step | Install Prodockit")
    choose_renderers = page.index("//// step | Choose optional renderers")
    adopt = page.index("//// step | Adopt the Zensical site")
    diagnose = page.index("//// step | Diagnose the adopted site")
    add_content = page.index("//// step | Add and verify Prodockit content")
    build_adopted = page.index("//// step | Build and preview the adopted website")
    pdf = page.index("//// step | Generate the rendered PDF")
    source = page.index("//// step | Generate the source bundle")
    downloads = page.index("//// step | Add both downloads to the site")
    assert (
        prepare_python
        < prepare_directory
        < install_zensical
        < create_zensical
        < build_zensical
        < serve_zensical
        < install_prodockit
        < choose_renderers
        < adopt
        < diagnose
        < add_content
        < build_adopted
        < pdf
        < source
        < downloads
    )

    before_prodockit = page[:install_prodockit]
    assert "zensical build --clean --strict" in before_prodockit
    assert before_prodockit.index("zensical build --clean --strict") < before_prodockit.index(
        "zensical serve"
    )
    assert "pip install --upgrade prodockit" not in before_prodockit
    renderer_choice = page[choose_renderers:adopt]
    assert "pdk adopt --configure" in renderer_choice
    assert "Adopt will check Node.js and npm" in renderer_choice
    assert "need to install them manually first" in renderer_choice
    assert "pdk adopt --dry-run\n```" in page[adopt:]
    assert "```bash\npdk adopt --apply\n```" in page[adopt:]
    assert "pdk diag" in page[diagnose:add_content]
    assert "pdk pdf" in page[pdf:source]
    assert "pdk source-bundle" in page[source:downloads]
    handoff = page[prepare_directory:install_zensical]
    assert handoff.count("    cd ~/repos\n") == 3
    assert "mkdir prodockit-project" in handoff
    assert "cd prodockit-project" in handoff
    assert "Set-Location" not in handoff
    assert 'python3.14" -m venv .venv' in handoff
    assert "py -3.14 -m venv .venv" in handoff
    assert "python3.14 -m venv .venv" in handoff
    assert "python -c 'import sys; print(sys.prefix)'" in handoff
    assert 'python -c "import sys; print(sys.prefix)"' in handoff
    assert "~/repos/.venv" in handoff


def test_prodockit_is_not_presented_as_supporting_mkdocs() -> None:
    """MkDocs may only be named for compatibility or configuration filenames."""
    paths = [
        REPO / "README.md",
        *(REPO / "docs").rglob("*.md"),
        *(REPO / "src" / "prodockit").rglob("*.py"),
    ]
    unsupported_phrases = (
        "zensical or mkdocs",
        "mkdocs document",
        "mkdocs project",
    )
    violations: list[str] = []

    for path in paths:
        contents = path.read_text(encoding="utf-8").lower()
        for phrase in unsupported_phrases:
            if phrase in contents:
                violations.append(f"{path.relative_to(REPO)}: {phrase}")

    assert not violations, "MkDocs is not a supported Prodockit generator:\n" + "\n".join(
        violations
    )


def test_bootstrap_continues_after_shared_preparation() -> None:
    page = BOOTSTRAP_GUIDE.read_text(encoding="utf-8")

    assert ".prodockit-components.toml" in page
    assert "/// tree" not in page
    assert "records Mermaid and maths as the project's selected components" in page
    assert "later `pdk adopt` can therefore repair" in page

    installation = page[
        page.index("## Install with bootstrap") : page.index("## Understand the completed project")
    ]
    assert "installation.md#installation-preparation" in installation
    assert installation.count("//// step | ") == 14
    assert "### Stage 1 — Prepare the setup environment" in installation
    assert "### Stage 2 — Assess and preview" in installation
    assert "### Stage 3 — Apply and confirm" in installation
    assert "### Stage 4 — Enter and verify the project" in installation
    assert "//// step | Prepare Python and the setup environment" in installation
    assert "//// step | Restart the terminal on Windows if instructed" in installation
    assert "//// step | Install Prodockit into the active environment" in installation
    install_step = installation[
        installation.index(
            "//// step | Install Prodockit into the active environment"
        ) : installation.index("//// step | Confirm the Prodockit version")
    ]
    assert '=== ":material-apple: macOS"' in install_step
    assert '=== ":fontawesome-brands-windows: Windows"' in install_step
    assert '=== ":material-linux: Linux (Ubuntu)"' in install_step
    assert "pip3 install --upgrade pip\n    pip3 install --upgrade prodockit" in install_step
    assert install_step.count("pip install --upgrade pip\n    pip install --upgrade prodockit") == 2
    manual_start = installation.index("//// step | Complete the browser actions")
    manual_end = installation.index("//// step | Confirm every Bootstrap activity")
    manual = installation[manual_start:manual_end]
    assert '!!! warning "Complete the manual step before confirming"' in manual
    assert "Type `yes` only after checking that the action succeeded" in " ".join(manual.split())
    assert "Do not run the complete `pdk diag` here" in installation
    verification = installation[installation.index("### Stage 4 — Enter and verify") :]
    assert "Changing directory" in verification
    assert verification.count("pdk diag") == 2
    assert verification.count("pdk template-sync") == 1
    assert verification.count('python -c "import sys; print(sys.prefix)"') == 1
    assert "//// step | Enter and activate the project" in verification
    assert "Fully close Windows Terminal or VS Code" in verification
    assert "new and pre-existing" in verification
    assert "The `Project` line must name the clone" in verification
    assert "python3.14 -m venv" not in installation
    assert "py -3.14 -m venv" not in installation

    for legacy_tab in ('=== "macOS"', '=== "Windows"', '=== "Ubuntu"'):
        assert legacy_tab not in page


def test_install_routes_explain_ownership_and_maintenance() -> None:
    routes = {
        FIRST_SITE: "installation.md#installation-adopted-structure",
        ADOPTION: "installation.md#installation-adopted-structure",
        BOOTSTRAP_GUIDE: "fig-template-file-ownership",
        MANUAL_INSTALL: "installation.md#installation-project-structure",
    }

    for path, ownership_reference in routes.items():
        page = path.read_text(encoding="utf-8")
        completed = page[
            page.index("## Understand the completed project") : page.index("## Where to go next")
        ]
        assert "### Know what becomes yours" in completed
        assert "### Keep the project current" in completed
        assert ownership_reference in completed

    first_site = FIRST_SITE.read_text(encoding="utf-8")
    assert "Adoption does not create or remove a template relationship" in first_site

    adoption = ADOPTION.read_text(encoding="utf-8")
    assert "neither creates nor removes a template relationship" in adoption

    for page in (first_site, adoption):
        maintenance = page[
            page.index("### Keep the project current") : page.index("## Where to go next")
        ]
        assert maintenance.index("upgrade\n   Prodockit") < maintenance.index("pdk adopt --dry-run")
        assert maintenance.index("pdk adopt --dry-run") < maintenance.index("pdk diag")
        assert "pdk adopt --apply" in maintenance
        assert "Continue only when the required checks pass" in maintenance

    bootstrap = BOOTSTRAP_GUIDE.read_text(encoding="utf-8")
    maintenance = bootstrap[
        bootstrap.index("### Keep the project current") : bootstrap.index("## Where to go next")
    ]
    assert maintenance.index("pdk template-sync") < maintenance.index("pdk adopt --dry-run")
    assert maintenance.index("pdk adopt --dry-run") < maintenance.index("pdk diag")
    assert "pdk adopt --apply" in maintenance
    assert "Continue only when the required checks pass" in maintenance

    manual = MANUAL_INSTALL.read_text(encoding="utf-8")
    assert "Path 1" in manual and "Path 2" in manual
    assert "preview `pdk template-sync`" in manual
