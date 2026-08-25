# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from prodockit import pins
from prodockit.cli import main
from prodockit.pins import (
    PackageState,
    PinError,
    PinSite,
    apply_version,
    discover,
    version_key,
)


def _project(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_version_key_orders_numerically_not_lexically() -> None:
    """0.0.9 sorts below 0.0.52 - a plain string compare puts it above,
    which would report an up-to-date project as behind (and vice versa)."""
    assert version_key("0.0.9") < version_key("0.0.52")
    assert version_key("69.0") < version_key("70.0")
    assert version_key("1.2.10") > version_key("1.2.9")


def test_version_key_sorts_a_prerelease_below_its_release() -> None:
    assert version_key("1.0.0rc1") < version_key("1.0.0")


def test_discover_finds_every_declaration_across_both_ci_layouts(tmp_path: Path) -> None:
    """The same version is declared in several files at once - that is the
    whole problem this solves - and GitHub and GitLab keep their jobs in
    different places."""
    _project(
        tmp_path,
        {
            "pyproject.toml": 'dependencies = [\n  "zensical>=0.0.52",\n]\n',
            ".github/workflows/docs.yml": '    - run: pip install "zensical==0.0.52" "weasyprint==69.0"\n',
            ".gitlab-ci.yml": "  script:\n    - pip install zensical==0.0.52\n",
            "requirements.txt": "weasyprint==69.0\n",
        },
    )

    states = discover(str(tmp_path))

    assert [s.path for s in states["zensical"].sites] == [
        "pyproject.toml",
        ".gitlab-ci.yml",
        os.path.join(".github", "workflows", "docs.yml"),
    ]
    assert {s.path for s in states["weasyprint"].sites} == {
        "requirements.txt",
        os.path.join(".github", "workflows", "docs.yml"),
    }


def test_discover_includes_compact_testrequirements_filename(tmp_path: Path) -> None:
    """The template uses testrequirements.txt rather than a hyphenated
    requirements-test.txt. It is still a top-level requirements file and
    must move with every other declaration (#565)."""
    _project(
        tmp_path,
        {
            "requirements.txt": "prodockit[index]>=0.45.0\n",
            "testrequirements.txt": "prodockit[testing]>=0.45.0\n",
        },
    )

    state = discover(str(tmp_path))["prodockit"]

    assert [site.path for site in state.sites] == ["requirements.txt", "testrequirements.txt"]
    apply_version(str(tmp_path), state, "0.46.0")
    assert (tmp_path / "testrequirements.txt").read_text(encoding="utf-8") == (
        "prodockit[testing]>=0.46.0\n"
    )


def test_check_offline_detects_testrequirements_drift(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {
            "requirements.txt": "prodockit>=0.45.0\n",
            "testrequirements.txt": "prodockit[testing]>=0.15.2\n",
        },
    )

    result = CliRunner().invoke(
        main, ["pins", "--root", str(tmp_path), "--check", "--offline"]
    )

    assert result.exit_code == 1
    assert "testrequirements.txt:1" in result.output
    assert "declared inconsistently" in result.output
    assert "Every managed package is current and consistent" not in result.output


def test_discover_records_the_operator_as_written(tmp_path: Path) -> None:
    """A floor and an exact pin are both correct in their own place - the
    library floor must not be flattened into a pin on rewrite."""
    _project(
        tmp_path,
        {
            "pyproject.toml": '  "zensical>=0.0.52",\n',
            ".gitlab-ci.yml": "    - pip install zensical==0.0.52\n",
        },
    )

    ops = {s.path: s.op for s in discover(str(tmp_path))["zensical"].sites}

    assert ops == {"pyproject.toml": ">=", ".gitlab-ci.yml": "=="}


def test_discover_ignores_a_package_whose_name_merely_contains_a_managed_one(
    tmp_path: Path,
) -> None:
    _project(tmp_path, {"requirements.txt": "my-zensical-fork==1.0\nzensical-extras==2.0\n"})

    assert discover(str(tmp_path))["zensical"].sites == []


def test_discover_finds_the_transitive_markdown_renderers(tmp_path: Path) -> None:
    """`markdown` and `pymdown-extensions` are managed by default even
    though nothing installs them directly - they arrive under Zensical,
    which declares only floors for them, so pinning Zensical alone leaves
    the library that renders every page free to move
    (prodockit-extensions#178).

    `pymdown-extensions` is the first managed name containing a hyphen,
    which is not incidental: the matcher's own lookbehind excludes a
    preceding `-` so that `my-zensical-fork` is not mistaken for
    `zensical`, and a hyphen *inside* a name has to keep working anyway.
    """
    _project(
        tmp_path,
        {
            ".github/workflows/docs.yml": (
                '    - run: pip install "zensical==0.0.53" "Markdown==3.10.3" '
                '"pymdown-extensions==11.0.1"\n'
            ),
        },
    )

    states = discover(str(tmp_path))

    assert [s.version for s in states["markdown"].sites] == ["3.10.3"]
    assert [s.version for s in states["pymdown-extensions"].sites] == ["11.0.1"]


def test_discover_does_not_mistake_pymdown_extensions_for_markdown(tmp_path: Path) -> None:
    """Both are managed, and one line can declare either. A `markdown`
    match must not be found inside `pymdown-extensions`, which would report
    a phantom site and rewrite the wrong package's version."""
    _project(tmp_path, {"requirements.txt": "pymdown-extensions==11.0.1\n"})

    states = discover(str(tmp_path))

    assert states["markdown"].sites == []
    assert [s.version for s in states["pymdown-extensions"].sites] == ["11.0.1"]


def test_discover_ignores_a_specifier_written_in_a_comment(tmp_path: Path) -> None:
    """A comment explaining a pin is prose, not a declaration.

    The matching is textual, so `zensical>=0.0.52` reads the same whether
    it is a dependency or a sentence about one. Counting the sentence gave
    a phantom declaration site, a false "declared inconsistently" from
    `--check`, and - worst - `--set` rewriting the prose into a statement
    that was no longer true (prodockit-extensions#184).

    Found while documenting why a transitive package was pinned, where
    naming the floors it inherits was the natural thing to write.
    """
    _project(
        tmp_path,
        {
            ".github/workflows/docs.yml": (
                "      # zensical declares only a floor, zensical>=0.0.52, so pinning\n"
                "      # it here is what actually fixes the version:\n"
                '      - run: pip install "zensical==0.0.53"\n'
            ),
        },
    )

    sites = discover(str(tmp_path))["zensical"].sites

    assert [s.version for s in sites] == ["0.0.53"], (
        "only the install line is a declaration; the two comment lines are prose"
    )


def test_discover_still_finds_a_declaration_with_a_trailing_comment(tmp_path: Path) -> None:
    """The counterpart, and what stops the fix being "ignore any line with
    a #". Only the part *after* the marker is prose; a comment explaining a
    pin must not hide the pin it explains."""
    _project(
        tmp_path,
        {
            "requirements.txt": "zensical==0.0.53  # bumped deliberately, see docs.yml\n",
        },
    )

    sites = discover(str(tmp_path))["zensical"].sites

    assert [(s.line, s.version) for s in sites] == [(1, "0.0.53")]


def test_discover_does_not_treat_a_hash_inside_quotes_as_a_comment(tmp_path: Path) -> None:
    """Stopping at the first `#` regardless of quoting would silently skip
    the rest of the line - the same quiet wrongness in a different place."""
    _project(
        tmp_path,
        {
            "requirements.txt": "# see https://example.com/deps#pinning\nzensical==0.0.53\n",
            ".gitlab-ci.yml": '  image: "python:3.13"  # not zensical==9.9.9\n',
        },
    )

    sites = discover(str(tmp_path))["zensical"].sites

    assert [s.version for s in sites] == ["0.0.53"], (
        "the URL fragment is inside a comment line and the 9.9.9 is inside one too"
    )


def test_apply_version_leaves_a_trailing_comment_on_the_same_line_alone(tmp_path: Path) -> None:
    """`subn` rewrites every occurrence it is given. Handed the whole line,
    a declaration whose own trailing comment quotes the same specifier
    would have both rewritten, leaving prose asserting a version that is no
    longer there."""
    _project(
        tmp_path,
        {"requirements.txt": "zensical==0.0.52  # matches the zensical==0.0.52 pin in docs.yml\n"},
    )
    state = discover(str(tmp_path))["zensical"]

    apply_version(str(tmp_path), state, "0.0.53")
    text = (tmp_path / "requirements.txt").read_text(encoding="utf-8")

    assert text.startswith("zensical==0.0.53"), "the declaration should move"
    assert "# matches the zensical==0.0.52 pin in docs.yml" in text, (
        "the comment is prose about another file and must not be rewritten"
    )


def test_discover_skips_build_output_and_virtualenvs(tmp_path: Path) -> None:
    """A copy of a workflow inside site/ or .venv/ is a build artifact, not
    a declaration anyone edits."""
    _project(
        tmp_path,
        {
            ".github/workflows/docs.yml": '- run: pip install "zensical==0.0.52"\n',
            ".gitlab/ci/build.yml": "    - pip install zensical==0.0.52\n",
        },
    )
    stale = tmp_path / ".github" / "workflows" / "node_modules"
    stale.mkdir(parents=True)
    (stale / "copy.yml").write_text('pip install "zensical==9.9.9"\n', encoding="utf-8")

    versions = {s.version for s in discover(str(tmp_path))["zensical"].sites}

    assert versions == {"0.0.52"}


def test_discover_reports_a_package_that_is_not_declared_at_all(tmp_path: Path) -> None:
    """A project that has not pinned WeasyPrint yet should still see it
    listed, rather than silently omitted from the report."""
    _project(tmp_path, {"pyproject.toml": '  "zensical>=0.0.52",\n'})

    states = discover(str(tmp_path))

    assert states["weasyprint"].sites == []
    assert states["weasyprint"].current is None


def test_current_is_the_highest_when_files_disagree(tmp_path: Path) -> None:
    """Files disagreeing is itself the bug being surfaced; treat the
    highest as current so the fix moves everything forward."""
    _project(
        tmp_path,
        {
            "pyproject.toml": '  "zensical>=0.0.9",\n',
            ".gitlab-ci.yml": "    - pip install zensical==0.0.52\n",
        },
    )

    state = discover(str(tmp_path))["zensical"]

    assert state.is_consistent is False
    assert state.current == "0.0.52"


def test_apply_version_rewrites_every_site_and_keeps_each_operator(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {
            "pyproject.toml": 'dependencies = [\n  "zensical>=0.0.52",\n]\n',
            ".github/workflows/docs.yml": '    - run: pip install "zensical==0.0.52"\n',
            ".gitlab-ci.yml": "    - pip install zensical == 0.0.52\n",
        },
    )
    state = discover(str(tmp_path))["zensical"]

    changed = apply_version(str(tmp_path), state, "0.0.53")

    assert len(changed) == 3
    assert '"zensical>=0.0.53"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '"zensical==0.0.53"' in (tmp_path / ".github" / "workflows" / "docs.yml").read_text(
        encoding="utf-8"
    )
    # Whitespace around the operator as written is tolerated.
    assert "zensical==0.0.53" in (tmp_path / ".gitlab-ci.yml").read_text(encoding="utf-8")


def test_apply_version_leaves_other_mentions_of_the_package_alone(tmp_path: Path) -> None:
    """A changelog line or a prose mention of the same version must not be
    rewritten - only the lines discovery identified as declarations."""
    workflow = (
        "# zensical 0.0.52 redrew an icon; see the changelog\n"
        '    - run: pip install "zensical==0.0.52"\n'
    )
    _project(tmp_path, {".github/workflows/docs.yml": workflow})
    state = discover(str(tmp_path))["zensical"]

    apply_version(str(tmp_path), state, "0.0.53")
    text = (tmp_path / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")

    assert "# zensical 0.0.52 redrew an icon" in text
    assert '"zensical==0.0.53"' in text


def test_apply_version_skips_sites_already_at_the_target(tmp_path: Path) -> None:
    _project(tmp_path, {"requirements.txt": "zensical==0.0.53\n"})
    state = discover(str(tmp_path))["zensical"]

    assert apply_version(str(tmp_path), state, "0.0.53") == []


def test_apply_version_refuses_to_guess_when_the_file_moved_under_it(tmp_path: Path) -> None:
    """Rewriting by line number is only safe while the file is unchanged.
    Fail loudly rather than corrupt an unrelated line."""
    _project(tmp_path, {"requirements.txt": "zensical==0.0.52\n"})
    state = discover(str(tmp_path))["zensical"]
    (tmp_path / "requirements.txt").write_text("something-else==1.0\n", encoding="utf-8")

    with pytest.raises(PinError, match="no longer contains"):
        apply_version(str(tmp_path), state, "0.0.53")


def test_is_behind_compares_numerically() -> None:
    state = PackageState(
        package="zensical",
        sites=[PinSite("pyproject.toml", 1, "zensical", ">=", "0.0.9")],
        latest="0.0.52",
    )

    assert state.is_behind is True


def test_is_behind_is_false_when_no_latest_is_known() -> None:
    """An unreachable PyPI must not read as "up to date" *or* as drift."""
    state = PackageState(
        package="zensical",
        sites=[PinSite("pyproject.toml", 1, "zensical", ">=", "0.0.52")],
        latest=None,
        latest_error="could not reach PyPI",
    )

    assert state.is_behind is False


def test_discover_finds_github_runner_labels(tmp_path: Path) -> None:
    """`runs-on: ubuntu-24.04` is a build input like any other - it carries
    pandoc, the fonts a PDF embeds and the Chrome that rasterises diagrams -
    but it is not a pip specifier: no operator, and the version is joined by
    a hyphen."""
    _project(
        tmp_path,
        {
            ".github/workflows/ci.yml": "jobs:\n  test:\n    runs-on: ubuntu-24.04\n",
            ".github/workflows/docs.yml": '    runs-on: "ubuntu-24.04"\n',
        },
    )

    state = discover(str(tmp_path), ["ubuntu"])["ubuntu"]

    assert [s.version for s in state.sites] == ["24.04", "24.04"]
    assert {s.kind for s in state.sites} == {"runner"}
    assert state.sites[0].spec == "ubuntu-24.04"


def test_discover_finds_pandoc_version_ci_variables(tmp_path: Path) -> None:
    """`PANDOC_VERSION: "3.10.1"` in a GitHub Actions `env:` block or a
    GitLab `variables:` block - the shape is identical in both, so one
    pattern covers it without caring which host a file belongs to
    (prodockit-extensions#209)."""
    _project(
        tmp_path,
        {
            ".github/workflows/docs.yml": 'env:\n  PANDOC_VERSION: "3.10.1"\n',
            ".gitlab-ci.yml": "variables:\n  PANDOC_VERSION: \"3.10.1\"\n",
        },
    )

    state = discover(str(tmp_path), ["pandoc"])["pandoc"]

    assert [s.version for s in state.sites] == ["3.10.1", "3.10.1"]
    assert {s.kind for s in state.sites} == {"env"}
    # The closing quote is deliberately not part of spec/op - see
    # _ENV_RE_TEMPLATE - so it is absent here too, not a typo.
    assert state.sites[0].spec == 'PANDOC_VERSION: "3.10.1'


def test_pandoc_version_is_matched_without_quotes_too(tmp_path: Path) -> None:
    """YAML does not require quoting a value like `3.10.1` - it is not a
    valid number, so it is already a string either way."""
    _project(tmp_path, {".github/workflows/ci.yml": "env:\n  PANDOC_VERSION: 3.10.1\n"})

    sites = discover(str(tmp_path), ["pandoc"])["pandoc"].sites

    assert len(sites) == 1
    assert sites[0].version == "3.10.1"
    assert sites[0].kind == "env"


def test_discover_finds_container_image_tags(tmp_path: Path) -> None:
    """GitLab CI pins its job image the same way most projects pin any
    container - `image: python:3.13`."""
    _project(
        tmp_path,
        {
            ".gitlab-ci.yml": "drift:\n  image: python:3.13\n",
            ".gitlab/ci/build.yml": "  image: docker.io/library/python:3.12\n",
        },
    )

    state = discover(str(tmp_path), ["python"])["python"]

    assert {s.version for s in state.sites} == {"3.13", "3.12"}
    assert {s.kind for s in state.sites} == {"image"}


def test_python_version_file_and_container_are_one_managed_pin(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {
            ".python-version": "3.14\n",
            ".gitlab-ci.yml": "build:\n  image: python:3.13\n",
        },
    )

    state = discover(str(tmp_path), ["python"])["python"]

    assert [(site.path, site.kind, site.version) for site in state.sites] == [
        (".python-version", "version-file", "3.14"),
        (".gitlab-ci.yml", "image", "3.13"),
    ]
    assert state.is_consistent is False
    assert state.on_pypi is False


def test_apply_python_version_rewrites_file_and_container_together(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {
            ".python-version": "3.13\n",
            ".gitlab-ci.yml": "build:\n  image: python:3.13\n",
        },
    )
    state = discover(str(tmp_path), ["python"])["python"]

    apply_version(str(tmp_path), state, "3.14")

    assert (tmp_path / ".python-version").read_text(encoding="utf-8") == "3.14\n"
    assert "image: python:3.14" in (tmp_path / ".gitlab-ci.yml").read_text(
        encoding="utf-8"
    )


def test_runner_and_image_states_are_not_looked_up_on_pypi(tmp_path: Path) -> None:
    """Asking PyPI for "ubuntu" would either miss or, worse, find an
    unrelated package of that name and report a nonsense upgrade."""
    from prodockit.pins import resolve_latest

    _project(tmp_path, {".github/workflows/ci.yml": "    runs-on: ubuntu-24.04\n"})
    states = discover(str(tmp_path), ["ubuntu"])

    resolve_latest(states)  # would hit the network for a pip package

    assert states["ubuntu"].on_pypi is False
    assert states["ubuntu"].latest is None
    assert "not a PyPI package" in (states["ubuntu"].latest_error or "")
    assert states["ubuntu"].is_behind is False


def test_apply_version_rewrites_pandoc_version_keeping_the_quote_style(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {
            ".github/workflows/docs.yml": 'env:\n  PANDOC_VERSION: "3.10.1"\n',
            ".gitlab-ci.yml": "variables:\n  PANDOC_VERSION: '3.10.1'\n",
        },
    )
    pandoc = discover(str(tmp_path), ["pandoc"])["pandoc"]

    apply_version(str(tmp_path), pandoc, "3.11.0")

    gh = (tmp_path / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")
    gl = (tmp_path / ".gitlab-ci.yml").read_text(encoding="utf-8")
    assert 'PANDOC_VERSION: "3.11.0"' in gh
    assert "PANDOC_VERSION: '3.11.0'" in gl, "the single-quote style must survive, unlike the version inside it"


def test_apply_version_preserves_the_upper_case_variable_name(tmp_path: Path) -> None:
    """`site.package` is always lower-cased, for lookup against the
    packages a caller asked to manage - using it to rewrite the file would
    turn `PANDOC_VERSION` into `pandoc_VERSION`, and the workflow step that
    reads `${{ env.PANDOC_VERSION }}` would stop finding it. The file has
    to end up with the name exactly as it was declared, not as prodockit's
    internal lookup key happens to be spelled."""
    _project(tmp_path, {".github/workflows/ci.yml": 'env:\n  PANDOC_VERSION: "3.10.1"\n'})
    pandoc = discover(str(tmp_path), ["pandoc"])["pandoc"]

    apply_version(str(tmp_path), pandoc, "3.11.0")

    text = (tmp_path / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "PANDOC_VERSION" in text, "the declared name must not be lower-cased on rewrite"
    assert "pandoc_VERSION" not in text
    assert 'PANDOC_VERSION: "3.11.0"' in text


def test_apply_version_rewrites_a_runner_label_keeping_its_separator(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {
            ".github/workflows/ci.yml": "jobs:\n  test:\n    runs-on: ubuntu-24.04\n",
            ".gitlab-ci.yml": "  image: python:3.13\n",
        },
    )
    ubuntu = discover(str(tmp_path), ["ubuntu"])["ubuntu"]
    python = discover(str(tmp_path), ["python"])["python"]

    apply_version(str(tmp_path), ubuntu, "26.04")
    apply_version(str(tmp_path), python, "3.14")

    assert "runs-on: ubuntu-26.04" in (tmp_path / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "image: python:3.14" in (tmp_path / ".gitlab-ci.yml").read_text(encoding="utf-8")


def test_a_runner_label_is_not_mistaken_for_a_pip_specifier(tmp_path: Path) -> None:
    """The pip pattern requires a real operator, so a hyphenated label must
    not match it - otherwise the same line would be recorded twice and
    rewritten twice."""
    _project(tmp_path, {".github/workflows/ci.yml": "    runs-on: ubuntu-24.04\n"})

    sites = discover(str(tmp_path), ["ubuntu"])["ubuntu"].sites

    assert len(sites) == 1
    assert sites[0].kind == "runner"


def test_discover_finds_a_requirement_with_extras(tmp_path: Path) -> None:
    """`package[extra]==version` is an ordinary shape, not an edge case -
    prodockit[index], uvicorn[standard], celery[redis]. The bracket sits
    between the name and the operator, which the first implementation could
    not see at all: it reported "not declared anywhere", which reads as
    nothing to do rather than could not parse."""
    _project(tmp_path, {"requirements.txt": "prodockit[index]>=0.17.2\n"})

    sites = discover(str(tmp_path), ["prodockit"])["prodockit"].sites

    assert len(sites) == 1
    assert sites[0].extras == "[index]"
    assert sites[0].version == "0.17.2"
    assert sites[0].spec == "prodockit[index]>=0.17.2"


def test_apply_version_keeps_extras_on_rewrite(tmp_path: Path) -> None:
    """Dropping the extras would silently stop installing an optional
    dependency - for prodockit[index] the back-of-book index simply stops
    being generated, with no error anywhere."""
    _project(tmp_path, {"requirements.txt": "prodockit[index]>=0.17.2\n"})
    state = discover(str(tmp_path), ["prodockit"])["prodockit"]

    apply_version(str(tmp_path), state, "0.17.4")

    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "prodockit[index]>=0.17.4\n"
    )


def test_multiple_extras_round_trip(tmp_path: Path) -> None:
    _project(tmp_path, {"requirements.txt": "prodockit[index,testing]==0.17.2\n"})
    state = discover(str(tmp_path), ["prodockit"])["prodockit"]

    assert state.sites[0].extras == "[index,testing]"
    apply_version(str(tmp_path), state, "0.17.4")

    assert "prodockit[index,testing]==0.17.4" in (tmp_path / "requirements.txt").read_text(
        encoding="utf-8"
    )


def test_a_plain_requirement_gains_no_bracket(tmp_path: Path) -> None:
    """The extras group is optional; a bare specifier must round-trip
    unchanged rather than acquiring an empty `[]`."""
    _project(tmp_path, {"requirements.txt": "prodockit==0.17.2\n"})
    state = discover(str(tmp_path), ["prodockit"])["prodockit"]

    assert state.sites[0].extras == ""
    apply_version(str(tmp_path), state, "0.17.4")

    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == "prodockit==0.17.4\n"


def test_extras_and_plain_declarations_of_one_package_are_both_found(tmp_path: Path) -> None:
    """The real shape this has to handle: a consuming project declaring the
    extras form in requirements.txt and a plain pin on a CI install line."""
    _project(
        tmp_path,
        {
            "requirements.txt": "prodockit[index]>=0.17.2\n",
            ".github/workflows/docs.yml": '    - run: pip install "prodockit==0.17.2"\n',
        },
    )

    state = discover(str(tmp_path), ["prodockit"])["prodockit"]
    apply_version(str(tmp_path), state, "0.17.4")

    assert "prodockit[index]>=0.17.4" in (tmp_path / "requirements.txt").read_text(encoding="utf-8")
    assert '"prodockit==0.17.4"' in (tmp_path / ".github" / "workflows" / "docs.yml").read_text(
        encoding="utf-8"
    )


def test_runner_labels_still_carry_no_extras(tmp_path: Path) -> None:
    """The runner/image patterns gained an empty extras group so the shared
    construction can read it unconditionally - it must stay empty."""
    _project(tmp_path, {".github/workflows/ci.yml": "    runs-on: ubuntu-24.04\n"})

    site = discover(str(tmp_path), ["ubuntu"])["ubuntu"].sites[0]

    assert site.extras == ""
    assert site.spec == "ubuntu-24.04"


def _both_packages(root: Path) -> None:
    """The ordinary shape: one package declared in package metadata, another
    pinned for the build, both in the default managed set."""
    _project(
        root,
        {
            "pyproject.toml": 'dependencies = [\n  "zensical>=0.0.52",\n]\n',
            "requirements.txt": "weasyprint==69.0\n",
        },
    )


def test_set_progress_line_shows_the_real_variable_name_not_the_lower_cased_key(
    tmp_path: Path,
) -> None:
    """Caught by running --set against real files rather than only unit
    testing apply_version(): the file itself was rewritten correctly, but
    this progress line was built separately and used `site.package`
    (lower-cased, for lookup) instead of `name_as_written` - so a run
    reported rewriting `PANDOC_VERSION` to `pandoc_VERSION`, a change that
    never actually happened."""
    _project(tmp_path, {".github/workflows/ci.yml": 'env:\n  PANDOC_VERSION: "3.10.1"\n'})

    result = CliRunner().invoke(
        main,
        ["pins", "--root", str(tmp_path), "--offline", "--set", "pandoc=3.11.0"],
        input="",
    )

    assert result.exit_code == 0, result.output
    assert "pandoc_VERSION" not in result.output
    assert 'PANDOC_VERSION: "3.10.1 -> PANDOC_VERSION: "3.11.0' in result.output


def test_set_updates_the_named_package_without_prompting_for_the_others(tmp_path: Path) -> None:
    """`--set` is for unattended use - a drift job, a release script - so
    naming one package must not leave the command waiting on stdin for the
    rest of the managed set. With no stdin to answer it, the prompt aborted
    the whole run and wrote nothing at all, including the package it had
    been told explicitly to set."""
    _both_packages(tmp_path)

    result = CliRunner().invoke(
        main,
        ["pins", "--root", str(tmp_path), "--offline", "--set", "zensical=0.0.53"],
        input="",
    )

    assert result.exit_code == 0, result.output
    assert '"zensical>=0.0.53"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    # Not named, so left exactly as it was rather than prompted for.
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == "weasyprint==69.0\n"


def test_set_reports_the_packages_it_left_untouched(tmp_path: Path) -> None:
    """Silently ignoring the rest of the managed set would read as "nothing
    to do there" - say which packages were skipped and why."""
    _both_packages(tmp_path)

    result = CliRunner().invoke(
        main,
        ["pins", "--root", str(tmp_path), "--offline", "--set", "zensical=0.0.53"],
        input="",
    )

    assert "Left untouched (no version given): weasyprint" in result.output


def test_no_input_alone_writes_nothing_and_still_reports(tmp_path: Path) -> None:
    """`--no-input` without a version to apply is a report, not a failure."""
    _both_packages(tmp_path)

    result = CliRunner().invoke(
        main, ["pins", "--root", str(tmp_path), "--offline", "--no-input"], input=""
    )

    assert result.exit_code == 0, result.output
    assert '"zensical>=0.0.52"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == "weasyprint==69.0\n"


def test_an_interrupted_prompt_keeps_the_answers_already_given(tmp_path: Path) -> None:
    """Answering one prompt and then breaking out must not discard that
    answer. Writing nothing while reporting an abort is the failure that
    hides work the user explicitly asked for."""
    _both_packages(tmp_path)

    result = CliRunner().invoke(
        main,
        ["pins", "--root", str(tmp_path), "--offline"],
        input="0.0.53\n",  # answers zensical, then stdin ends at weasyprint
    )

    assert '"zensical>=0.0.53"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == "weasyprint==69.0\n"
    # The run *was* cut short, so it should not report success.
    assert result.exit_code != 0


def test_set_still_rejects_a_package_that_is_not_managed(tmp_path: Path) -> None:
    _both_packages(tmp_path)

    # Not "pandoc" - it joined the default managed set once it could be
    # matched as a `PANDOC_VERSION` CI variable (prodockit-extensions#209),
    # which would make this test pass for the wrong reason.
    result = CliRunner().invoke(
        main,
        ["pins", "--root", str(tmp_path), "--offline", "--set", "not-a-real-package=3.1"],
        input="",
    )

    assert result.exit_code == 1
    assert "not being managed" in result.output


def test_prodockit_is_watched_like_every_other_build_input() -> None:
    """prodockit-template#173.

    Its absence from the managed set had exactly the consequence the set
    exists to prevent: the template pinned `prodockit==0.35.0` and
    drifted two releases behind with nothing noticing, because the one
    command that looks at pins was not looking at this one. Moving it
    needed `-p prodockit` typed by hand, which is the step nobody
    remembers.

    On the merits too: prodockit renders the PDF and generates the
    back-of-book index, so its version changes published output as
    directly as Zensical's does.
    """
    assert "prodockit" in pins.DEFAULT_PACKAGES


def test_python_build_version_is_watched_by_default() -> None:
    assert "python" in pins.DEFAULT_PACKAGES


def test_python_is_never_looked_up_as_an_unrelated_pypi_package(tmp_path: Path) -> None:
    state = discover(str(tmp_path), ["python"])["python"]

    assert state.sites == []
    assert state.on_pypi is False


def test_this_projects_own_metadata_is_not_a_pin(tmp_path: Path) -> None:
    """The risk of adding prodockit to the default set.

    In prodockit's *own* repository the name appears in `pyproject.toml`
    as the project's identity, not as a dependency. Matching `name =
    "prodockit"` or the adjacent `version = "0.36.2"` would have
    `prodockit pins` offer to rewrite the release number of the package
    being built.

    The specifier pattern requires an operator after the name, so
    neither is a declaration - asserted here because nothing else would
    catch it until a release was quietly renumbered.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "prodockit"\nversion = "0.36.2"\n'
        'dependencies = ["zensical>=0.0.55"]\n',
        encoding="utf-8",
    )

    found = pins.discover(str(tmp_path))

    assert found["prodockit"].sites == [], found["prodockit"].sites
    assert [s.version for s in found["zensical"].sites] == ["0.0.55"]


def test_an_extra_survives_being_repinned(tmp_path: Path) -> None:
    """`prodockit[index]` is how the User Guide declares it, and the
    extra is what pulls in pymupdf for the back-of-book index. Dropping
    it on rewrite would stop the index being generated, with no error
    anywhere - so this matters more now that prodockit is repinned
    automatically rather than by hand.
    """
    (tmp_path / "requirements.txt").write_text(
        "prodockit[index]==0.21.0\n", encoding="utf-8"
    )

    result = CliRunner().invoke(
        main,
        ["pins", "--root", str(tmp_path), "--offline", "--set", "prodockit=0.36.2"],
        input="",
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "prodockit[index]==0.36.2\n"
    )
