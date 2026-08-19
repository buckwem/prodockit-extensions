# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""`prodockit.template_sync`: bringing a project back into step with its
template without touching the work in it.

Every case here comes from a real assignment measured against the real
template (prodockit-template#188) - the paths, the rename and the single
edited file are what that comparison actually found, rather than shapes
invented to suit the code.
"""

from __future__ import annotations

import re

import pytest

from prodockit.template_sync import (
    MANIFEST_FILE,
    TEMPLATE_REMOTES,
    Baseline,
    TemplateSyncError,
    derive_baseline,
    load_manifest,
    resolve_template,
    unclassified,
)

MANIFEST = """
version = 1

[template]
owns = [".github/workflows/**", "docs/javascripts/**", "docs/stylesheets/**",
        "macros.py", "test/**"]

[project]
owns = ["docs/*.md", "docs/assets/**", "LICENSE.md", ".vscode/**"]
seed = ["LICENSE.md"]
ignore = [".vscode/"]

[shared]
files = ["zensical.toml", ".gitignore"]

[excluded]
paths = ["CHANGELOG.md", ".github/CODEOWNERS"]

[renames]
"docs/javascript" = "docs/javascripts"
"LICENSE" = "LICENSE.md"
"""


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


def test_every_group_is_read_back() -> None:
    manifest = load_manifest(MANIFEST)

    assert manifest.owner("macros.py") == "template"
    assert manifest.owner("docs/section1.md") == "project"
    assert manifest.owner("zensical.toml") == "shared"
    assert manifest.owner("CHANGELOG.md") == "excluded"


def test_a_directory_glob_covers_every_depth_below_it() -> None:
    """`docs/stylesheets/**` means the whole directory, however deep, and
    stops at its own name - a sibling that merely starts the same way is
    not inside it."""
    manifest = load_manifest(MANIFEST)

    assert manifest.owner("docs/stylesheets/extra.css") == "template"
    assert manifest.owner(".github/workflows/docs.yml") == "template"
    assert manifest.owner("test/fixtures/deep/nested/case.py") == "template"
    # Not below it, despite the shared prefix.
    assert manifest.owner("docs/stylesheets-old/extra.css") == "unclassified"


def test_a_file_no_rule_claims_is_an_error_not_a_default() -> None:
    """Both defaults are wrong: treating an unknown file as the
    template's overwrites somebody's work, and treating it as the
    project's silently stops delivering it."""
    manifest = load_manifest(MANIFEST)

    assert unclassified(manifest, ["macros.py", "docs/index.md"]) == []
    assert unclassified(manifest, ["tools/mermaid/package.json"]) == [
        "tools/mermaid/package.json"
    ]


def test_the_top_level_docs_glob_catches_the_report_itself() -> None:
    """`docs/**/*.md` alone does not match `docs/index.md`, and a
    manifest that misses it hands the report to the template - which is
    the one outcome this tool must never produce. Found by the coverage
    check while the manifest was being written, not by reading it.
    """
    manifest = load_manifest(MANIFEST)

    for page in ("docs/index.md", "docs/section4.md", "docs/originality.md"):
        assert manifest.owner(page) == "project", page


def test_a_seed_has_to_be_project_owned() -> None:
    """A seed is written once and then belongs to the project. One that
    is not project-owned would be updated by the rule it exists to be
    exempt from."""
    with pytest.raises(TemplateSyncError, match="seeded but not project-owned"):
        load_manifest(MANIFEST.replace('seed = ["LICENSE.md"]', 'seed = ["macros.py"]'))


def test_a_manifest_that_is_not_toml_says_so() -> None:
    with pytest.raises(TemplateSyncError, match=re.escape(f"{MANIFEST_FILE} is not valid TOML")):
        load_manifest("[template\nowns = ")


def test_a_list_of_the_wrong_shape_is_refused() -> None:
    with pytest.raises(TemplateSyncError, match=re.escape("template.owns must be a list of strings")):
        load_manifest('[template]\nowns = "everything"\n')


# ---------------------------------------------------------------------------
# Renames
# ---------------------------------------------------------------------------


def test_a_renamed_directory_maps_to_what_the_project_still_calls_it() -> None:
    """The real assignment predates `docs/javascript` -> `docs/javascripts`
    and still lists the old path in its own config. Comparing before
    renaming gives it a second copy instead of an update.
    """
    manifest = load_manifest(MANIFEST)

    assert manifest.rename("docs/javascripts/extra.js") == "docs/javascript/extra.js"
    assert manifest.rename("LICENSE.md") == "LICENSE"
    # Anything not renamed is left exactly as it is.
    assert manifest.rename("macros.py") == "macros.py"


def test_a_rename_does_not_match_a_merely_similar_prefix() -> None:
    """`docs/javascripts` must not rewrite `docs/javascripts-old/x.js`
    by prefix alone."""
    manifest = load_manifest(MANIFEST)

    assert manifest.rename("docs/javascriptsX/extra.js") == "docs/javascriptsX/extra.js"


# ---------------------------------------------------------------------------
# Which template a project tracks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("origin", "expected_host"),
    [
        ("git@gitlab.surrey.ac.uk:mb0105/cw-example-comm058-2026.git", "gitlab.surrey.ac.uk"),
        ("https://github.com/someone/report.git", "github.com"),
        ("git@gitlab.com:group/sub/report.git", "github.com"),
    ],
)
def test_the_template_follows_the_project_s_own_host(origin: str, expected_host: str) -> None:
    """A project on Surrey's GitLab tracks Surrey's mirror, because a
    student there may have no GitHub access at all. Everyone else tracks
    the canonical copy - so `gitlab.com` resolves to GitHub, which is
    the case a "same host" rule would get wrong.
    """
    assert expected_host in resolve_template(origin)


def test_a_project_with_no_remote_is_told_rather_than_guessed_at() -> None:
    """Defaulting to GitHub would silently hand a Surrey student the
    wrong template."""
    with pytest.raises(TemplateSyncError, match="no `origin` remote"):
        resolve_template(None)


def test_an_unknown_host_is_told_rather_than_guessed_at() -> None:
    with pytest.raises(TemplateSyncError, match=re.escape("no template is known for git.example.com")):
        resolve_template("git@git.example.com:someone/report.git")


def test_a_bare_override_means_that_host_s_usual_template() -> None:
    assert resolve_template(None, github="") == TEMPLATE_REMOTES["github.com"]
    assert resolve_template(None, surrey="") == TEMPLATE_REMOTES["gitlab.surrey.ac.uk"]


def test_an_override_with_a_slug_names_another_repository_on_that_host() -> None:
    assert (
        resolve_template(None, github="acme/report-template")
        == "git@github.com:acme/report-template.git"
    )
    # GitLab nests groups, and keeping only the first segment produced a
    # namespace that does not exist last time this was got wrong (#201).
    assert (
        resolve_template(None, surrey="cs-dept/year3/template")
        == "git@gitlab.surrey.ac.uk:cs-dept/year3/template.git"
    )


def test_an_override_beats_the_project_s_own_host() -> None:
    """A Surrey reader with GitHub access can take the canonical copy."""
    origin = "git@gitlab.surrey.ac.uk:mb0105/report.git"

    assert resolve_template(origin, github="") == TEMPLATE_REMOTES["github.com"]


def test_naming_two_templates_is_refused() -> None:
    with pytest.raises(TemplateSyncError, match="two different templates"):
        resolve_template(None, github="", surrey="")


def test_a_slug_without_a_group_is_refused() -> None:
    """`--github prodockit-template` has no owner, and guessing one
    would fetch somebody else's repository."""
    with pytest.raises(TemplateSyncError, match="takes group-or-name/repo"):
        resolve_template(None, github="prodockit-template")


# ---------------------------------------------------------------------------
# The baseline, and the edits it finds
# ---------------------------------------------------------------------------


def _fixture_history():
    """A template with three versions, and a project that took the
    second and then edited one file - the shape the real assignment
    turned out to have."""
    history = {
        "v3": {"macros.py": "c", "docs/stylesheets/extra.css": "z", ".vscode/x": "s3"},
        "v2": {"macros.py": "b", "docs/stylesheets/extra.css": "y", ".vscode/x": "s2"},
        "v1": {"macros.py": "a", "docs/stylesheets/extra.css": "x", ".vscode/x": "s1"},
    }
    project = {"macros.py": "b", "docs/stylesheets/extra.css": "y", ".vscode/x": "MINE"}
    return history, project


def test_the_baseline_is_the_version_the_files_agree_with() -> None:
    history, project = _fixture_history()

    result = derive_baseline(
        list(project), project.get, list(history), lambda v, p: history[v].get(p)
    )

    assert result.version == "v2"
    assert (result.matched, result.total) == (2, 3)


def test_the_same_scan_names_the_edited_files() -> None:
    """Being behind and having edited a file are indistinguishable until
    the baseline is known, so both answers come from one calculation."""
    history, project = _fixture_history()

    result = derive_baseline(
        list(project), project.get, list(history), lambda v, p: history[v].get(p)
    )

    assert result.edited == (".vscode/x",)


def test_a_project_that_matches_a_version_exactly_reports_no_edits() -> None:
    history, _ = _fixture_history()
    project = dict(history["v2"])

    result = derive_baseline(
        list(project), project.get, list(history), lambda v, p: history[v].get(p)
    )

    assert result.version == "v2"
    assert result.edited == ()
    assert result.matched == result.total


def test_a_file_the_project_does_not_have_is_not_counted_against_it() -> None:
    """A project generated before a file existed has not edited it - it
    has never seen it. Counting it as disagreement would drag the
    baseline backwards past the version it really matches."""
    history, project = _fixture_history()
    project.pop("docs/stylesheets/extra.css")

    result = derive_baseline(
        [*history["v2"]], project.get, list(history), lambda v, p: history[v].get(p)
    )

    assert result.total == 2
    assert result.version == "v2"


def test_a_project_with_nothing_to_compare_has_no_baseline() -> None:
    result = derive_baseline([], lambda p: None, ["v1"], lambda v, p: None)

    assert result == Baseline(version=None, matched=0, total=0)


def test_the_newest_of_two_equally_good_versions_wins() -> None:
    """Two versions can agree equally well without either being a
    complete match. The newest is the honest answer, and the scan is
    newest-first - so the comparison has to be strictly better to
    displace it.

    Deliberately not a fixture where the newest matches completely: the
    scan stops early on a complete match, so that case never exercises
    the tie-break at all. The first version of this test did exactly
    that and passed with the comparison inverted.
    """
    history = {
        "v3": {"a": "1", "b": "NEW"},
        "v2": {"a": "1", "b": "OLD"},
        "v1": {"a": "0", "b": "OLD"},
    }
    project = {"a": "1", "b": "MINE"}  # neither version matches fully

    result = derive_baseline(
        list(project), project.get, list(history), lambda v, p: history[v].get(p)
    )

    assert result.version == "v3"
    assert result.matched == 1
    assert result.edited == ("b",)


def test_ownership_is_decided_on_the_template_s_own_spelling() -> None:
    """A renamed path is for finding the project's copy, not for deciding
    who owns it.

    Classifying the renamed path asks whether `docs/javascript/extra.js`
    matches `docs/javascripts/**` - it does not, so a file the manifest
    plainly claims came back unclassified. Found by running the checker
    over the real template rather than over this fixture.
    """
    manifest = load_manifest(MANIFEST)

    assert manifest.owner("docs/javascripts/extra.js") == "template"
    assert unclassified(manifest, ["docs/javascripts/extra.js"]) == []
