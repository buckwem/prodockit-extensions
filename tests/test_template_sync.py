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

import pathlib
import re
from collections.abc import Sequence

import pytest

from prodockit.template_sync import (
    FILE_ACTIONS,
    LOG_FILE,
    MANIFEST_FILE,
    TEMPLATE_REMOTES,
    Baseline,
    FileAction,
    TemplateSyncError,
    add_config_table,
    append_ignores,
    append_log,
    apply_config_changes,
    apply_dependency_updates,
    apply_file_actions,
    apply_seeds,
    baseline_report,
    blocking_changes,
    branch_name,
    cache_path_for,
    cache_root,
    classification_report,
    config_changes,
    default_branch,
    dependency_updates,
    derive_baseline,
    edited_managed_stylesheets,
    ensure_template,
    git_runner,
    ignore_the_log,
    latest_prodockit_version,
    leftovers,
    load_manifest,
    missing_ignores,
    missing_seeds,
    now,
    pending_writes,
    plan_template_files,
    prodockit_requirement,
    prodockit_upgrade_required,
    publish,
    publish_blockers,
    read_config,
    read_stamp,
    resolve_template,
    review_push_command,
    review_url,
    set_config_value,
    stage_changes,
    start_branch,
    submit_for_review,
    unclassified,
    update_report,
    write_stamp,
    written_report,
)

MANIFEST = """
version = 1

[template]
owns = [".github/workflows/**", "docs/javascripts/**",
        "docs/stylesheets/pdk.css", "docs/stylesheets/pdk-pdf.css",
        "macros.py", "test/**"]

[project]
owns = ["docs/*.md", "docs/assets/**", "docs/stylesheets/extra.css",
        "docs/stylesheets/print.css", "LICENSE.md", ".vscode/**"]
seed = ["LICENSE.md"]
ignore = [".vscode/"]

[shared]
files = ["zensical.toml", ".gitignore"]

[shared.zensical_toml]
take = ['project.markdown_extensions."prodockit.*"', "project.extra.pdf_*"]
never = ["project.extra.pdf_copyright"]

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


def test_template_prodockit_floor_is_read_from_requirements() -> None:
    requirement = prodockit_requirement(
        "# old example: prodockit>=0.40.0\nprodockit>=0.43.2  # current floor\n"
    )

    assert requirement is not None
    assert requirement.specifier == "prodockit>=0.43.2"
    assert requirement.version == "0.43.2"


def test_template_prodockit_floor_preserves_optional_extras() -> None:
    requirement = prodockit_requirement("prodockit[index,testing]>=0.43.2\n")

    assert requirement is not None
    assert requirement.specifier == "prodockit[index,testing]>=0.43.2"


def test_dependency_updates_align_every_project_declaration(tmp_path: pathlib.Path) -> None:
    template = tmp_path / "template"
    project = tmp_path / "project"
    for root in (template, project):
        (root / ".github" / "workflows").mkdir(parents=True)

    (template / "requirements.txt").write_text(
        "prodockit>=0.51.0\nzensical>=0.0.57\n", encoding="utf-8"
    )
    (template / ".github" / "workflows" / "docs.yml").write_text(
        "run: pip install prodockit==0.51.0 zensical==0.0.57\n", encoding="utf-8"
    )
    (project / "requirements.txt").write_text(
        "prodockit[index]>=0.39.0\nzensical>=0.0.53\n", encoding="utf-8"
    )
    (project / "testrequirements.txt").write_text(
        "prodockit[testing]>=0.39.0\n", encoding="utf-8"
    )
    (project / ".github" / "workflows" / "docs.yml").write_text(
        "run: pip install prodockit==0.39.0 zensical==0.0.53\n", encoding="utf-8"
    )

    updates = dependency_updates(template, project)

    assert [(item.package, item.version) for item in updates] == [
        ("prodockit", "0.51.0"),
        ("zensical", "0.0.57"),
    ]
    changed = apply_dependency_updates(project, updates)
    assert set(changed) == {
        "requirements.txt",
        "testrequirements.txt",
        ".github/workflows/docs.yml",
    }
    assert "prodockit[index]>=0.51.0" in (project / "requirements.txt").read_text()
    assert "prodockit[testing]>=0.51.0" in (project / "testrequirements.txt").read_text()
    workflow = (project / ".github" / "workflows" / "docs.yml").read_text()
    assert "prodockit==0.51.0" in workflow
    assert "zensical==0.0.57" in workflow


def test_dependency_updates_never_downgrade_a_project(tmp_path: pathlib.Path) -> None:
    template = tmp_path / "template"
    project = tmp_path / "project"
    template.mkdir()
    project.mkdir()
    (template / "requirements.txt").write_text("prodockit>=0.51.0\n", encoding="utf-8")
    (project / "requirements.txt").write_text("prodockit>=0.52.0\n", encoding="utf-8")

    assert dependency_updates(template, project) == []


def test_dependency_updates_take_highest_version_from_an_old_inconsistent_template(
    tmp_path: pathlib.Path,
) -> None:
    template = tmp_path / "template"
    project = tmp_path / "project"
    template.mkdir()
    project.mkdir()
    (template / "requirements.txt").write_text("prodockit>=0.51.0\n", encoding="utf-8")
    (template / "testrequirements.txt").write_text(
        "prodockit[testing]>=0.50.0\n", encoding="utf-8"
    )
    (project / "requirements.txt").write_text("prodockit>=0.49.0\n", encoding="utf-8")

    updates = dependency_updates(template, project)

    assert [(item.package, item.version) for item in updates] == [("prodockit", "0.51.0")]


@pytest.mark.parametrize(
    ("installed", "required", "upgrade"),
    [
        ("0.43.1", "0.43.2", True),
        ("0.43.2a1", "0.43.2", True),
        ("0.43.2", "0.43.2", False),
        ("0.44.0", "0.43.2", False),
        ("0.43.2+local.1", "0.43.2", False),
    ],
)
def test_prodockit_upgrade_warning_compares_release_versions(
    installed: str, required: str, upgrade: bool
) -> None:
    assert prodockit_upgrade_required(installed, required) is upgrade


def test_an_unfamiliar_local_version_never_blocks_template_sync() -> None:
    assert not prodockit_upgrade_required("working-tree", "0.43.2")


def test_latest_prodockit_release_is_read_from_pypi_metadata() -> None:
    assert (
        latest_prodockit_version(lambda _url: b'{"info": {"version": "0.43.3"}}')
        == "0.43.3"
    )


@pytest.mark.parametrize(
    "answer",
    [
        b"not json",
        b'{"info": {}}',
        b'{"info": {"version": "unexpected"}}',
    ],
)
def test_an_unusable_pypi_answer_does_not_block_template_sync(answer: bytes) -> None:
    assert latest_prodockit_version(lambda _url: answer) is None


def test_a_pypi_connection_failure_does_not_block_template_sync() -> None:
    def offline(_url: str) -> bytes:
        raise OSError("offline")

    assert latest_prodockit_version(offline) is None


def test_stylesheet_ownership_separates_managed_defaults_from_author_overrides() -> None:
    manifest = load_manifest(MANIFEST)

    assert manifest.owner("docs/stylesheets/pdk.css") == "template"
    assert manifest.owner("docs/stylesheets/pdk-pdf.css") == "template"
    assert manifest.owner("docs/stylesheets/extra.css") == "project"
    assert manifest.owner("docs/stylesheets/print.css") == "project"
    assert manifest.owner(".github/workflows/docs.yml") == "template"
    assert manifest.owner("test/fixtures/deep/nested/case.py") == "template"
    # No broad stylesheet glob should claim an unrelated file.
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


def test_an_origin_no_host_can_be_read_from_asks_for_a_flag() -> None:
    """A local-path remote asks for a flag rather than raising through.

    `parse_remote`'s `SyncRepoError` travelled all the way out as a
    traceback, which is what a student with an odd `origin` would see.
    """
    with pytest.raises(TemplateSyncError, match=re.escape("--surrey")):
        resolve_template("/Users/someone/GitLab/my-project")


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
        "v3": {"macros.py": "c", "docs/stylesheets/pdk.css": "z", ".vscode/x": "s3"},
        "v2": {"macros.py": "b", "docs/stylesheets/pdk.css": "y", ".vscode/x": "s2"},
        "v1": {"macros.py": "a", "docs/stylesheets/pdk.css": "x", ".vscode/x": "s1"},
    }
    project = {"macros.py": "b", "docs/stylesheets/pdk.css": "y", ".vscode/x": "MINE"}
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
    project.pop("docs/stylesheets/pdk.css")

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


# ---------------------------------------------------------------------------
# Reporting, and --verbose
# ---------------------------------------------------------------------------

FILES = [
    "macros.py",
    "docs/stylesheets/pdk.css",
    "docs/stylesheets/extra.css",
    "docs/index.md",
    "docs/section1.md",
    "zensical.toml",
    "CHANGELOG.md",
]


def test_the_summary_counts_every_file_exactly_once() -> None:
    """The point of the summary is that the numbers add up to the whole
    tree - a reader sees nothing was missed without reading every line."""
    lines = classification_report(load_manifest(MANIFEST), FILES)

    counts = [int(re.search(r": (\d+) \(", line).group(1)) for line in lines]
    assert counts == [2, 3, 1, 1]
    assert sum(counts) == len(FILES)


def test_the_summary_stays_a_summary() -> None:
    """Without `verbose` no filename appears - otherwise the count is
    decoration on a list somebody has to read anyway."""
    lines = classification_report(load_manifest(MANIFEST), FILES)

    assert not any(line.startswith("    ") for line in lines)


def test_verbose_lists_every_file_under_its_group() -> None:
    """The form worth having when the question is "why is *this* file
    being replaced", which a count cannot answer."""
    lines = classification_report(load_manifest(MANIFEST), FILES, verbose=True)

    listed = [line.strip() for line in lines if line.startswith("    ")]
    assert sorted(listed) == sorted(FILES), "every file should appear exactly once"
    # Under the right heading, in the order the report declares.
    text = "\n".join(lines)
    assert text.index("macros.py") < text.index("project")
    assert text.index("docs/index.md") > text.index("project")


def test_an_unclassified_file_is_reported_even_though_the_group_is_usually_absent() -> None:
    """A silent zero invites a shrug; a named file does not."""
    manifest = load_manifest(MANIFEST)

    quiet = classification_report(manifest, ["macros.py"])
    noisy = classification_report(manifest, ["macros.py", "tools/x.json"], verbose=True)

    assert not any("Missing a template rule" in line for line in quiet)
    assert any("Missing a template rule" in line for line in noisy)
    assert any("tools/x.json" in line for line in noisy)


def test_the_edited_files_are_always_listed() -> None:
    """They are the reason the tool will leave something alone, so a
    count of them is not actionable."""
    baseline = Baseline(version="v2", matched=1, total=2, edited=("macros.py",))

    lines = baseline_report(baseline)

    assert any("macros.py" in line for line in lines)
    assert any(line.startswith("Files changed in this project") for line in lines)


def test_verbose_adds_the_files_that_agreed() -> None:
    """How somebody checks the conclusion rather than taking it."""
    baseline = Baseline(
        version="v2", matched=1, total=2, edited=("macros.py",), agreeing=("test/a.py",)
    )

    quiet = baseline_report(baseline)
    noisy = baseline_report(baseline, verbose=True)

    assert not any("test/a.py" in line for line in quiet)
    assert any("test/a.py" in line for line in noisy)


def test_a_project_with_nothing_to_compare_says_so_rather_than_reporting_a_version() -> None:
    lines = baseline_report(Baseline(version=None, matched=0, total=0))

    assert lines == ["No template-managed files were found to compare."]


def test_each_group_says_what_will_happen_to_it() -> None:
    """A group's name is not its behaviour. `project` and `excluded` both
    mean untouched, for entirely different reasons, and a reader should
    not have to know the manifest to tell them apart."""
    lines = classification_report(load_manifest(MANIFEST), FILES)

    text = "\n".join(lines)
    assert "Template-managed files" in text and "unless you changed them" in text
    assert "Your project files" in text and "your writing - never changed" in text
    assert "Shared settings" in text and "keeping your choices" in text
    assert "Not copied into projects" in text and "not delivered" in text


def test_every_group_has_an_action_including_the_error_one() -> None:
    """A group added to the report without an action would render as a
    bare count, or raise - neither is discovered by reading."""
    from prodockit.template_sync import GROUP_ACTIONS, REPORT_ORDER

    assert set(REPORT_ORDER) == set(GROUP_ACTIONS)


def test_the_counts_survive_the_actions_being_added() -> None:
    """The count is still parseable, and still adds up to the tree."""
    lines = classification_report(load_manifest(MANIFEST), FILES)

    counts = [int(re.search(r": (\d+) \(", line).group(1)) for line in lines]
    assert sum(counts) == len(FILES)


# ---------------------------------------------------------------------------
# Stage 4: what blocks an update
# ---------------------------------------------------------------------------


def test_only_template_owned_changes_block_an_update() -> None:
    """A project being written always has a dirty tree - the report, its
    figures, its bibliography. Refusing on any of that refuses always,
    which is the same as not having the tool."""
    manifest = load_manifest(MANIFEST)
    dirty = ["docs/section1.md", "docs/assets/figure.png", "zensical.toml", "macros.py"]

    assert blocking_changes(manifest, dirty) == ["macros.py"]


def test_a_clean_enough_tree_blocks_nothing() -> None:
    manifest = load_manifest(MANIFEST)

    assert blocking_changes(manifest, ["docs/index.md", "docs/section4.md"]) == []


def test_blocking_is_what_makes_force_safe() -> None:
    """Anything an update can overwrite is committed, so `git checkout`
    gets it back. This is the check that guarantees it, so it is asserted
    directly rather than left as a comment: a template-owned file with
    uncommitted changes must always block."""
    manifest = load_manifest(MANIFEST)

    for path in ("macros.py", "docs/stylesheets/pdk.css", ".github/workflows/docs.yml"):
        assert blocking_changes(manifest, [path]) == [path], path


# ---------------------------------------------------------------------------
# Stage 6: what an update would do to each file
# ---------------------------------------------------------------------------


def _plan(project: dict[str, str], template: dict[str, str], edited=(), force=()):
    manifest = load_manifest(MANIFEST)
    baseline = Baseline(version="v1", matched=0, total=0, edited=tuple(edited))
    return {
        a.path: a.action
        for a in plan_template_files(
            manifest, list(template), project.get, template.get, baseline, force=force
        )
    }


def test_a_file_that_already_matches_is_left_alone() -> None:
    assert _plan({"macros.py": "a"}, {"macros.py": "a"}) == {"macros.py": "same"}


def test_a_file_the_project_lacks_is_added() -> None:
    """The template has gained it since this project was generated."""
    assert _plan({}, {"macros.py": "a"}) == {"macros.py": "add"}


def test_a_file_that_differs_and_was_not_edited_is_an_update() -> None:
    assert _plan({"macros.py": "old"}, {"macros.py": "new"}) == {"macros.py": "update"}


def test_a_file_the_project_edited_is_kept() -> None:
    """Theirs stands; the template's copy is written alongside as `.new`
    so the two can be compared without either being lost."""
    plan = _plan({"macros.py": "mine"}, {"macros.py": "new"}, edited=["macros.py"])

    assert plan == {"macros.py": "keep"}


def test_an_edited_file_can_be_overwritten_on_request() -> None:
    """`--force` names the file, so the instruction carries the knowledge
    that the file was edited."""
    plan = _plan(
        {"macros.py": "mine"}, {"macros.py": "new"}, edited=["macros.py"], force=["macros.py"]
    )

    assert plan == {"macros.py": "forced"}


def test_force_does_not_reach_a_file_it_was_not_given() -> None:
    """Forcing one file must not quietly force its neighbours."""
    plan = _plan(
        {"macros.py": "mine", "docs/stylesheets/pdk.css": "mine"},
        {"macros.py": "new", "docs/stylesheets/pdk.css": "new"},
        edited=["macros.py", "docs/stylesheets/pdk.css"],
        force=["macros.py"],
    )

    assert plan == {"macros.py": "forced", "docs/stylesheets/pdk.css": "keep"}


def test_edited_managed_stylesheets_are_named_separately() -> None:
    actions = [
        FileAction("docs/stylesheets/pdk.css", "docs/stylesheets/pdk.css", "keep", "edited"),
        FileAction(
            "docs/stylesheets/pdk-pdf.css",
            "docs/stylesheets/pdk-pdf.css",
            "forced",
            "edited",
        ),
        FileAction("macros.py", "macros.py", "keep", "edited"),
    ]

    assert edited_managed_stylesheets(actions) == [
        "docs/stylesheets/pdk-pdf.css",
        "docs/stylesheets/pdk.css",
    ]


def test_a_renamed_file_is_matched_against_what_the_project_calls_it() -> None:
    """The project predates `docs/javascript` -> `docs/javascripts`. Its
    copy is the same content under the older name, so this is `same` and
    not a file the template has gained."""
    manifest = load_manifest(MANIFEST)
    baseline = Baseline(version="v1", matched=1, total=1)

    actions = plan_template_files(
        manifest,
        ["docs/javascripts/extra.js"],
        {"docs/javascript/extra.js": "a"}.get,
        {"docs/javascripts/extra.js": "a"}.get,
        baseline,
    )

    assert [(a.action, a.project_path) for a in actions] == [
        ("same", "docs/javascript/extra.js")
    ]


def test_files_the_manifest_does_not_own_are_not_planned() -> None:
    """The report is the project's, and no stage reads it."""
    manifest = load_manifest(MANIFEST)
    baseline = Baseline(version="v1", matched=0, total=0)

    actions = plan_template_files(
        manifest, ["docs/index.md", "zensical.toml", "CHANGELOG.md"],
        lambda p: "x", lambda p: "y", baseline,
    )

    assert actions == []


# ---------------------------------------------------------------------------
# The update report
# ---------------------------------------------------------------------------


def test_the_update_report_never_lists_the_unchanged_files() -> None:
    """`same` is almost every file, and burying the five that matter
    under sixty that do not is how a report stops being read."""
    actions = [
        FileAction("macros.py", "macros.py", "same", "x"),
        FileAction("a.py", "a.py", "update", "y"),
    ]

    quiet = update_report(actions)
    noisy = update_report(actions, verbose=True)

    assert not any("up to date" in line for line in quiet)
    assert any("Already up to date: 1" in line for line in noisy)
    assert not any("macros.py" in line for line in noisy)
    assert not any("a.py" in line for line in quiet)
    assert any("a.py" in line for line in noisy)


def test_the_standard_report_lists_only_files_needing_an_author_s_decision() -> None:
    actions = [
        FileAction("new.py", "new.py", "add", FILE_ACTIONS["add"]),
        FileAction("routine.py", "routine.py", "update", FILE_ACTIONS["update"]),
        FileAction("mine.py", "mine.py", "keep", FILE_ACTIONS["keep"]),
        FileAction("replace.py", "replace.py", "forced", FILE_ACTIONS["forced"]),
    ]

    text = "\n".join(update_report(actions))

    assert "New template files to add: 1" in text
    assert "Template files to update: 1" in text
    assert "new.py" not in text and "routine.py" not in text
    assert "mine.py" in text and "replace.py" in text


def test_verbose_report_adds_routine_paths_and_plain_language_reasons() -> None:
    actions = [
        FileAction("new.py", "new.py", "add", FILE_ACTIONS["add"]),
        FileAction("routine.py", "routine.py", "update", FILE_ACTIONS["update"]),
        FileAction("mine.py", "mine.py", "keep", FILE_ACTIONS["keep"]),
    ]

    text = "\n".join(update_report(actions, verbose=True))

    assert "new.py" in text and "routine.py" in text and "mine.py" in text
    assert "new files supplied by the template" in text
    assert "template copies are saved as .new" in text


def test_the_verbose_update_report_says_why_for_each_group() -> None:
    actions = [FileAction("a.py", "a.py", "keep", FILE_ACTIONS["keep"])]

    text = "\n".join(update_report(actions, verbose=True))

    assert "versions stay" in text and ".new" in text


def test_a_renamed_file_shows_both_names() -> None:
    """Otherwise a reader cannot tell why the template's path is not the
    one being written."""
    actions = [FileAction("docs/javascripts/extra.js", "docs/javascript/extra.js", "update", "x")]

    quiet = "\n".join(update_report(actions))
    text = "\n".join(update_report(actions, verbose=True))

    assert "docs/javascript/extra.js" not in quiet
    assert "docs/javascript/extra.js" in text
    assert "<- docs/javascripts/extra.js" in text


# ---------------------------------------------------------------------------
# Stages 7 to 9: seeds, shared config, leftovers
# ---------------------------------------------------------------------------


def test_a_seed_is_written_only_when_it_is_missing() -> None:
    """Written once and then the project's. A project may rightly change
    its licence, and an update that restored the template's would be
    wrong rather than helpful."""
    manifest = load_manifest(MANIFEST)

    assert missing_seeds(manifest, lambda p: False) == ["LICENSE.md"]
    assert missing_seeds(manifest, lambda p: True) == []


def test_a_seed_is_looked_for_under_the_name_the_project_uses() -> None:
    """A project generated before `LICENSE` became `LICENSE.md` has the
    old name, and seeding it again would leave two licences."""
    manifest = load_manifest(MANIFEST)

    assert missing_seeds(manifest, lambda p: p == "LICENSE") == []


def test_the_template_s_own_config_keys_are_offered() -> None:
    template = {"project": {"markdown_extensions": {"prodockit.tree": {}}}}
    project: dict = {"project": {"markdown_extensions": {}}}

    added, updated = config_changes(load_manifest(MANIFEST), template, project)

    assert added == ['project.markdown_extensions."prodockit.tree"']
    assert updated == []


def test_a_changed_setting_is_an_update_not_an_addition() -> None:
    template = {"project": {"markdown_extensions": {"prodockit.tree": {"indent": 2}}}}
    project = {"project": {"markdown_extensions": {"prodockit.tree": {"indent": 4}}}}

    added, updated = config_changes(load_manifest(MANIFEST), template, project)

    assert (added, updated) == (
        [],
        ['project.markdown_extensions."prodockit.tree".indent'],
    )


def test_only_missing_settings_inside_the_template_boundary_are_added() -> None:
    """`site_name` is outside the manifest boundary, while a missing PDF
    parameter is introduced without changing an existing author value."""
    template = {"project": {"site_name": "Document Template", "extra": {"pdf_x": 1}}}
    project = {"project": {"site_name": "My Report", "extra": {}}}

    added, updated = config_changes(load_manifest(MANIFEST), template, project)

    assert added == ["project.extra.pdf_x"]
    assert updated == []


def test_an_extension_switched_off_is_not_switched_back_on() -> None:
    """Nothing is ever removed, and a key the project lacks is offered as
    an addition - but a reader who deleted it has made a choice, which is
    why this is reported rather than applied silently."""
    template: dict = {"project": {"markdown_extensions": {"prodockit.bibliography": {}}}}
    project: dict = {"project": {"markdown_extensions": {"prodockit.tree": {}}}}

    added, updated = config_changes(load_manifest(MANIFEST), template, project)

    assert added == ['project.markdown_extensions."prodockit.bibliography"']
    # The project's own extension is left entirely alone.
    assert not any("tree" in key for key in added + updated)


def test_a_dotted_extension_name_is_one_key_not_two() -> None:
    """`prodockit.tables` is a table *name* containing a dot. Split, it
    would match nothing and every extension setting would be missed."""
    template = {"project": {"markdown_extensions": {"prodockit.tables": {"x": 1}}}}

    added, _ = config_changes(load_manifest(MANIFEST), template, {})

    assert added == ['project.markdown_extensions."prodockit.tables".x']


def test_only_the_ignore_lines_the_project_lacks_are_offered() -> None:
    manifest = load_manifest(MANIFEST)

    # The log is always offered - see the LOG_FILE test below.
    assert missing_ignores(manifest, ["build/", "*.pyc"]) == [".vscode/", LOG_FILE]
    assert missing_ignores(manifest, ["build/", ".vscode/", LOG_FILE]) == []


def test_files_no_longer_delivered_are_reported_not_removed() -> None:
    """Removing files from somebody's repository because a manifest
    changed its mind is a different and more dangerous operation."""
    manifest = load_manifest(MANIFEST)

    assert leftovers(manifest, ["docs/index.md", "CHANGELOG.md", ".github/CODEOWNERS"]) == [
        ".github/CODEOWNERS",
        "CHANGELOG.md",
    ]


def test_existing_pdf_settings_are_preserved_even_when_the_manifest_claims_them() -> None:
    """The template's broad `take` pattern must not restore page defaults
    or put the template author's name on somebody else's report."""
    manifest = load_manifest(MANIFEST)
    template = {"project": {"extra": {"pdf_copyright": "Mark", "pdf_page_size": "A4"}}}
    project = {"project": {"extra": {"pdf_copyright": "123456", "pdf_page_size": "A5"}}}

    added, updated = config_changes(manifest, template, project)

    assert added == []
    assert updated == []


@pytest.mark.parametrize(
    "key",
    [
        "pdf_page_size",
        "pdf_margin_top",
        "pdf_margin_right",
        "pdf_margin_bottom",
        "pdf_margin_left",
        "pdf_margin_inner",
        "pdf_margin_outer",
        "pdf_double_sided",
        "pdf_header_footer_font_size",
        "pdf_header_footer_color",
        "pdf_header_footer_divider_color",
        "pdf_extra_css",
        "pdf_source_bundle_output",
        "pdf_future_page_setting",
    ],
)
def test_every_pdf_setting_is_preserved_when_it_differs(key: str) -> None:
    manifest = load_manifest(MANIFEST)
    template = {"project": {"extra": {key: "template default"}}}
    project = {"project": {"extra": {key: "author choice"}}}

    assert config_changes(manifest, template, project) == ([], [])


def test_a_new_pdf_setting_is_added_from_the_template() -> None:
    manifest = load_manifest(MANIFEST)
    template = {"project": {"extra": {"pdf_page_size": "A4"}}}

    assert config_changes(manifest, template, {}) == (["project.extra.pdf_page_size"], [])


# ---------------------------------------------------------------------------
# Applying: editing config without destroying it
# ---------------------------------------------------------------------------

CONFIG = '''# The project's own settings. Every line here was written on purpose.
[project]
site_name = "My Report"

# Margins are in the PDF's own units - see customisebuild.md for why
# these are not the browser defaults.
[project.extra]
pdf_page_size = "A4"
pdf_margin_top = "2cm"

[project.markdown_extensions."prodockit.tables"]
'''


def test_a_changed_value_leaves_every_other_line_byte_identical() -> None:
    """The reason this is surgical rather than a parse-and-dump: 367 of
    this file's 604 lines are comments explaining the settings, and
    re-emitting the document would discard all of them."""
    after = set_config_value(CONFIG, "project.extra.pdf_page_size", '"A5"')

    before_lines = CONFIG.splitlines()
    after_lines = after.splitlines()
    assert len(before_lines) == len(after_lines)
    changed = [i for i, (a, b) in enumerate(zip(before_lines, after_lines, strict=True)) if a != b]
    assert len(changed) == 1, "exactly one line should differ"
    assert after_lines[changed[0]] == 'pdf_page_size = "A5"'
    # And the comments survive, which is the whole point.
    assert "# Margins are in the PDF's own units" in after


def test_a_missing_key_is_inserted_into_its_own_table() -> None:
    after = set_config_value(CONFIG, "project.extra.pdf_double_sided", "true")

    assert "pdf_double_sided = true" in after
    # In [project.extra], not appended to the end of the document where
    # it would land in whatever table happens to be last.
    extra = after.split("[project.extra]")[1].split("[project.markdown")[0]
    assert "pdf_double_sided" in extra


def test_a_key_in_a_table_that_does_not_exist_is_refused() -> None:
    """Appending it to the end would put it in whatever table is last -
    a wrong answer that looks like a right one."""
    with pytest.raises(TemplateSyncError, match=re.escape("no [project.nope] table")):
        set_config_value(CONFIG, "project.nope.thing", "1")


def test_a_table_name_is_not_mistaken_for_a_key() -> None:
    with pytest.raises(TemplateSyncError, match="names a table, not a key"):
        set_config_value(CONFIG, 'project.markdown_extensions."prodockit.tree"', "")


def test_a_new_extension_table_is_added_once() -> None:
    once = add_config_table(CONFIG, 'project.markdown_extensions."prodockit.tree"')
    twice = add_config_table(once, 'project.markdown_extensions."prodockit.tree"')

    assert once.count('[project.markdown_extensions."prodockit.tree"]') == 1
    assert twice == once, "adding it again must change nothing"
    # Everything that was there before is still there, unchanged.
    assert once.startswith(CONFIG.rstrip("\n"))


def test_ignores_are_appended_and_never_reordered() -> None:
    """A .gitignore is read top to bottom by people as well as by git."""
    text = "build/\n*.pyc\n"

    after = append_ignores(text, [".vscode/", "*.pyc"])

    assert after == "build/\n*.pyc\n.vscode/\n"


def test_appending_nothing_changes_nothing() -> None:
    text = "build/\n"

    assert append_ignores(text, []) == text
    assert append_ignores(text, ["build/"]) == text


# ---------------------------------------------------------------------------
# Applying: writing the files
# ---------------------------------------------------------------------------


def _actions(*pairs: tuple[str, str]) -> list[FileAction]:
    return [FileAction(p, p, a, FILE_ACTIONS[a]) for p, a in pairs]


def test_an_unchanged_file_is_not_rewritten(tmp_path) -> None:
    """A tool that rewrites identical bytes makes every update look like
    a change to anyone reading `git status` afterwards."""
    (tmp_path / "macros.py").write_text("original")

    written = apply_file_actions(
        _actions(("macros.py", "same")), tmp_path, lambda p: b"from the template"
    )

    assert written == []
    assert (tmp_path / "macros.py").read_text() == "original"


def test_an_update_replaces_the_file(tmp_path) -> None:
    (tmp_path / "macros.py").write_text("old")

    apply_file_actions(_actions(("macros.py", "update")), tmp_path, lambda p: b"new")

    assert (tmp_path / "macros.py").read_bytes() == b"new"


def test_an_added_file_gets_its_directory_made(tmp_path) -> None:
    """The template can gain a whole directory, and a project that never
    had it has nowhere to put the file."""
    apply_file_actions(
        _actions(("tools/mermaid/package.json", "add")), tmp_path, lambda p: b"{}"
    )

    assert (tmp_path / "tools/mermaid/package.json").read_bytes() == b"{}"


def test_an_edited_file_is_left_alone_and_the_template_s_written_beside_it(tmp_path) -> None:
    """The whole reason an edited file is not simply skipped: both
    versions survive and can be compared."""
    (tmp_path / ".gitlab-ci.yml").write_text("mine")

    apply_file_actions(_actions((".gitlab-ci.yml", "keep")), tmp_path, lambda p: b"theirs")

    assert (tmp_path / ".gitlab-ci.yml").read_text() == "mine"
    assert (tmp_path / ".gitlab-ci.yml.new").read_bytes() == b"theirs"


def test_a_forced_file_is_overwritten_and_no_sidecar_is_left(tmp_path) -> None:
    """Forcing is the instruction to take the template's copy; leaving a
    `.new` beside it as well would be clutter nobody asked for."""
    (tmp_path / ".gitlab-ci.yml").write_text("mine")

    apply_file_actions(_actions((".gitlab-ci.yml", "forced")), tmp_path, lambda p: b"theirs")

    assert (tmp_path / ".gitlab-ci.yml").read_bytes() == b"theirs"
    assert not (tmp_path / ".gitlab-ci.yml.new").exists()


def test_nothing_outside_the_plan_is_touched(tmp_path) -> None:
    """The report is not in the plan, and must not be reachable from it."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "section1.md").write_text("my report")

    apply_file_actions(_actions(("macros.py", "update")), tmp_path, lambda p: b"x")

    assert (tmp_path / "docs" / "section1.md").read_text() == "my report"


def test_the_report_is_built_from_what_was_written(tmp_path) -> None:
    """Not from the plan: if the two ever disagree, this is where it
    shows."""
    written = apply_file_actions(
        _actions(("a.py", "update"), ("b.py", "same")), tmp_path, lambda p: b"x"
    )

    text = "\n".join(written_report(written, verbose=True))
    assert "a.py" in text
    assert "b.py" not in text, "a file that was not written must not be reported"

    quiet = "\n".join(written_report(written))
    assert "Template files to update: 1" in quiet
    assert "a.py" not in quiet


def test_a_project_already_in_step_says_so(tmp_path) -> None:
    assert written_report([]) == ["No template files needed changing."]


# ---------------------------------------------------------------------------
# Stage 7 applied: seeds
# ---------------------------------------------------------------------------


def test_a_missing_seed_is_written(tmp_path) -> None:
    written = apply_seeds(load_manifest(MANIFEST), tmp_path, lambda p: b"MIT ...")

    assert [w.path for w in written] == ["LICENSE.md"]
    assert (tmp_path / "LICENSE.md").read_bytes() == b"MIT ..."


def test_a_seed_already_there_is_never_touched(tmp_path) -> None:
    """However far it has diverged. A project may rightly change its
    licence, and restoring the template's would be wrong."""
    (tmp_path / "LICENSE.md").write_text("my own licence")

    written = apply_seeds(load_manifest(MANIFEST), tmp_path, lambda p: b"MIT ...")

    assert written == []
    assert (tmp_path / "LICENSE.md").read_text() == "my own licence"


def test_a_seed_is_not_written_twice_under_two_names(tmp_path) -> None:
    """A project generated before `LICENSE` became `LICENSE.md` has the
    old name, and seeding again would leave it with two licences."""
    (tmp_path / "LICENSE").write_text("the older name")

    assert apply_seeds(load_manifest(MANIFEST), tmp_path, lambda p: b"x") == []
    assert not (tmp_path / "LICENSE.md").exists()


# ---------------------------------------------------------------------------
# Stage 8 applied: the shared config
# ---------------------------------------------------------------------------


def test_a_new_extension_table_and_its_settings_are_written() -> None:
    """Tables first, then values: a key cannot be written into a table
    that is not there yet, and a project that never had the extension has
    neither."""
    template = {"project": {"markdown_extensions": {"prodockit.tree": {"indent": 2}}}}
    added = ['project.markdown_extensions."prodockit.tree".indent']

    after = apply_config_changes(CONFIG, template, added, [])

    assert '[project.markdown_extensions."prodockit.tree"]' in after
    assert "indent = 2" in after


def test_an_updated_value_replaces_only_itself() -> None:
    template = {"project": {"extra": {"pdf_page_size": "A5"}}}

    after = apply_config_changes(CONFIG, template, [], ["project.extra.pdf_page_size"])

    assert 'pdf_page_size = "A5"' in after
    assert 'pdf_margin_top = "2cm"' in after, "its neighbour is untouched"
    assert "# Margins are in the PDF's own units" in after, "and so are the comments"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "true"), (False, "false"), (3, "3"), ("A4", '"A4"'), (["a", "b"], '["a", "b"]')],
)
def test_values_are_written_as_toml_literals(value, expected) -> None:
    template = {"project": {"extra": {"pdf_thing": value}}}

    after = apply_config_changes(CONFIG, template, [], [])
    after = apply_config_changes(CONFIG, template, ["project.extra.pdf_thing"], [])

    assert f"pdf_thing = {expected}" in after


def test_a_value_shape_that_cannot_be_written_is_refused() -> None:
    """A wrongly quoted value produces a config that parses and means
    something different, which is worse than a refusal."""
    template = {"project": {"extra": {"pdf_thing": [1, 2, 3]}}}

    with pytest.raises(TemplateSyncError, match="copied by hand"):
        apply_config_changes(CONFIG, template, ["project.extra.pdf_thing"], [])


def test_a_quoted_string_survives_the_round_trip() -> None:
    """`pdf_copyright` holds HTML with quotes in it - which this must
    never take anyway, but the escaping has to be right for anything
    else that does."""
    template = {"project": {"extra": {"pdf_x": 'a "quoted" thing'}}}

    after = apply_config_changes(CONFIG, template, ["project.extra.pdf_x"], [])

    assert read_config(after)["project"]["extra"]["pdf_x"] == 'a "quoted" thing'


def test_an_extension_with_no_settings_still_gets_its_table() -> None:
    """`[project.markdown_extensions."prodockit.tree"]` with nothing
    under it is how most extensions are enabled - the table's presence is
    the setting. A project that never had it needs the header written,
    and there is no key to hang that off.
    """
    template: dict = {"project": {"markdown_extensions": {"prodockit.tree": {}}}}
    added, updated = config_changes(load_manifest(MANIFEST), template, {})
    assert added == ['project.markdown_extensions."prodockit.tree"'], added

    after = apply_config_changes(CONFIG, template, added, updated)

    assert '[project.markdown_extensions."prodockit.tree"]' in after
    assert "prodockit.tree" in read_config(after)["project"]["markdown_extensions"]


# ---------------------------------------------------------------------------
# Stage 10: the branch, the stamp, and staging
# ---------------------------------------------------------------------------


class FakeGit:
    """Records what would have been run, and answers as told.

    A fake rather than a real repository for the decisions - whether a
    branch is created or switched to is a choice this module makes, and
    it should be readable from the commands rather than inferred from
    the state afterwards.
    """

    def __init__(self, *, has_branch: bool = False, fails: bool = False) -> None:
        self.commands: list[list[str]] = []
        self.has_branch = has_branch
        self.fails = fails

    def __call__(self, command):  # type: ignore[no-untyped-def]
        self.commands.append(list(command))
        if command[1:3] == ["rev-parse", "--verify"]:
            return self.has_branch
        return not self.fails


def test_a_branch_is_named_after_the_template_version() -> None:
    assert branch_name("1.5.0") == "template-update-1.5.0"


def test_a_bare_sha_is_cut_to_something_typeable() -> None:
    """`git describe` on a template whose tags belong to something else
    produced `0.0.26-12-g2ae6640`, which names a branch nobody can read."""
    assert branch_name("6fbbbbeb87b8925623a7012e0f1e328bde71558c") == (
        "template-update-6fbbbbeb8"
    )


def test_a_version_that_names_nothing_is_refused() -> None:
    with pytest.raises(TemplateSyncError, match="no template version"):
        branch_name("   ")


def test_a_new_branch_is_created() -> None:
    git = FakeGit(has_branch=False)

    start_branch(git, "template-update-1.5.0")

    assert git.commands[-1] == ["git", "checkout", "-b", "template-update-1.5.0"]


def test_an_existing_branch_is_switched_to_not_replaced() -> None:
    """A second run against the same template version belongs on the same
    branch; deleting it would throw away whatever the first run left."""
    git = FakeGit(has_branch=True)

    start_branch(git, "template-update-1.5.0")

    assert git.commands[-1] == ["git", "checkout", "template-update-1.5.0"]
    assert not any("-b" in command for command in git.commands)


def test_the_stamp_records_the_version(tmp_path) -> None:
    write_stamp(tmp_path, "1.5.0")

    assert (tmp_path / ".prodockit-template").read_text() == "1.5.0\n"
    assert read_stamp(tmp_path) == "1.5.0"


def test_a_project_with_no_stamp_reads_as_none(tmp_path) -> None:
    """Which is what sends the next run to derive the baseline instead."""
    assert read_stamp(tmp_path) is None


def test_an_empty_stamp_is_not_mistaken_for_a_version(tmp_path) -> None:
    """A truncated write would otherwise be read as a version named ''
    and compared against every tag, matching nothing, silently."""
    (tmp_path / ".prodockit-template").write_text("\n")

    assert read_stamp(tmp_path) is None


def test_only_what_was_written_is_staged() -> None:
    git = FakeGit()

    stage_changes(git, ["macros.py", ".python-version"])

    assert git.commands[-1] == ["git", "add", "--", "macros.py", ".python-version"]


def test_staging_nothing_runs_no_command() -> None:
    """A run that changed nothing should leave no trace in the index."""
    git = FakeGit()

    assert stage_changes(git, []) is True
    assert git.commands == []


def test_the_commit_is_never_made() -> None:
    """The reader's history is theirs. A message written by a tool about
    somebody else's project is worth less than the time it saves."""
    git = FakeGit()

    start_branch(git, "template-update-1.5.0")
    stage_changes(git, ["macros.py"])

    assert not any("commit" in command for command in git.commands)


def test_a_gitlab_review_push_creates_a_merge_request() -> None:
    command, creates_request = review_push_command(
        "git@gitlab.surrey.ac.uk:assessment-test/report-test.git", "main"
    )

    assert creates_request is True
    assert command[-2:] == ["origin", "HEAD"]
    assert "--set-upstream" in command
    assert "--push-option=merge_request.create" in command
    assert "--push-option=merge_request.target=main" in command
    assert "--push-option=merge_request.remove_source_branch" in command


def test_a_github_review_push_publishes_the_branch_without_gitlab_options() -> None:
    command, creates_request = review_push_command(
        "git@github.com:someone/report.git", "main"
    )

    assert creates_request is False
    assert command == ["git", "push", "--set-upstream", "origin", "HEAD"]


def test_review_links_take_an_author_to_the_host_workflow() -> None:
    branch = "template-update-0.51.1"

    assert review_url(
        "git@gitlab.surrey.ac.uk:assessment-test/report-test.git", branch, "main"
    ) == (
        "https://gitlab.surrey.ac.uk/assessment-test/report-test/-/merge_requests"
    )
    assert review_url(
        "git@github.com:someone/report.git", branch, "main"
    ) == (
        "https://github.com/someone/report/compare/"
        "main...template-update-0.51.1?expand=1"
    )


def test_review_submission_prunes_commits_and_pushes_in_order() -> None:
    done: list[list[str]] = []

    def run(command: Sequence[str]) -> bool:
        done.append(list(command))
        return True

    created = submit_for_review(
        run,
        "git@gitlab.surrey.ac.uk:assessment-test/report-test.git",
        "main",
        "Sync with the template",
    )

    assert created is True
    assert [command[1] for command in done] == ["fetch", "commit", "push"]
    assert done[0] == ["git", "fetch", "--prune", "origin"]
    assert done[2][-2:] == ["origin", "HEAD"]


def test_a_failed_refresh_does_not_commit_or_push_a_review() -> None:
    done: list[list[str]] = []

    def run(command: Sequence[str]) -> bool:
        done.append(list(command))
        return "fetch" not in command

    with pytest.raises(TemplateSyncError, match="Nothing was committed or sent"):
        submit_for_review(
            run,
            "git@gitlab.surrey.ac.uk:assessment-test/report-test.git",
            "main",
            "Sync with the template",
        )

    assert [command[1] for command in done] == ["fetch"]


def test_the_real_runner_drives_a_real_repository(tmp_path) -> None:
    """The fake above says what this module *decides*; this says the
    decisions work against git itself.

    Worth having separately: a fake that answers however it is told
    cannot notice a command that git would reject, and every one of
    these is typed out by hand somewhere above.
    """
    import subprocess

    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "seed.txt").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=tmp_path, check=True)

    run = git_runner(tmp_path)
    name = branch_name("1.5.0")

    assert start_branch(run, name) is True
    on = subprocess.run(
        ["git", "branch", "--show-current"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert on == name

    # A second run finds the branch and switches rather than failing to
    # create it again - the case the fake can only assert about.
    assert start_branch(run, name) is True

    write_stamp(tmp_path, "1.5.0")
    (tmp_path / "macros.py").write_text("updated")
    assert stage_changes(run, [".prodockit-template", "macros.py"]) is True

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.split()
    assert sorted(staged) == [".prodockit-template", "macros.py"]

    # And nothing was committed: the reader's history is untouched.
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert log.count("\n") == 0, "only the fixture's own commit should exist"


def test_review_submission_recovers_a_deleted_remote_branch_without_git_commands(
    tmp_path,
) -> None:
    """Exercise the Git state that previously needed fetch/prune and -u by hand.

    The bare repository advertises push options so the same GitLab command is
    exercised without contacting GitLab or creating a real merge request.
    """
    import subprocess

    remote = tmp_path / "remote.git"
    project = tmp_path / "report"
    subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
    subprocess.run(
        ["git", "-C", str(remote), "config", "receive.advertisePushOptions", "true"],
        check=True,
    )
    subprocess.run(["git", "init", "-b", "main", "--quiet", str(project)], check=True)
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.com"),
        ("commit.gpgsign", "false"),
    ):
        subprocess.run(["git", "-C", str(project), "config", key, value], check=True)
    (project / "managed.txt").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "managed.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(project), "commit", "-qm", "initial"], check=True
    )
    subprocess.run(
        ["git", "-C", str(project), "remote", "add", "origin", str(remote)], check=True
    )
    subprocess.run(
        ["git", "-C", str(project), "push", "-qu", "origin", "main"], check=True
    )

    branch = "template-update-0.51.1"
    subprocess.run(
        ["git", "-C", str(project), "checkout", "-qb", branch], check=True
    )
    # Leave a stale origin/<branch> record behind, as GitLab does locally when
    # an earlier merge request deletes the host branch between fetches.
    subprocess.run(
        ["git", "-C", str(project), "push", "-qu", "origin", "HEAD"], check=True
    )
    subprocess.run(
        ["git", "-C", str(remote), "update-ref", "-d", f"refs/heads/{branch}"],
        check=True,
    )

    (project / "managed.txt").write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "managed.txt"], check=True)
    created = submit_for_review(
        git_runner(project),
        "git@gitlab.surrey.ac.uk:assessment-test/report-test.git",
        "main",
        "Sync with the template",
    )

    assert created is True
    upstream = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "--abbrev-ref", "@{upstream}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert upstream == f"origin/{branch}"
    remote_head = subprocess.run(
        ["git", "-C", str(remote), "rev-parse", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    local_head = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert remote_head == local_head


def test_the_runner_answers_false_rather_than_raising(tmp_path) -> None:
    """`start_branch` asks whether a branch exists by running a command
    that fails when it does not - so a non-zero exit has to be an answer,
    not an exception."""
    import subprocess

    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    run = git_runner(tmp_path)

    assert run(["git", "rev-parse", "--verify", "--quiet", "refs/heads/nope"]) is False


# ---------------------------------------------------------------------------
# The log
# ---------------------------------------------------------------------------


def test_a_run_is_appended_to_the_log_not_written_over(tmp_path: pathlib.Path) -> None:
    """The run worth diagnosing is usually not the last one."""
    append_log(tmp_path, ["first run"], now(), ["prodockit", "template-sync"])
    append_log(tmp_path, ["second run"], now(), ["prodockit", "template-sync", "--apply"])

    text = (tmp_path / LOG_FILE).read_text(encoding="utf-8")

    assert "first run" in text
    assert "second run" in text
    assert text.index("first run") < text.index("second run")


def test_the_log_records_when_a_run_started_and_when_it_finished(
    tmp_path: pathlib.Path,
) -> None:
    """Both ends, so a run that hung can be told from one that was slow."""
    started = now()
    append_log(tmp_path, ["  4 files"], started, ["prodockit", "template-sync"])

    lines = (tmp_path / LOG_FILE).read_text(encoding="utf-8").splitlines()

    assert lines[0].startswith(f"=== {started}  started")
    assert "  4 files" in lines
    last = [line for line in lines if line.strip()][-1]

    assert last.startswith("=== ")
    assert "finished" in last


def test_the_log_records_the_command_that_was_run(tmp_path: pathlib.Path) -> None:
    """Which flags were passed is the first thing anyone asks."""
    append_log(tmp_path, [], now(), ["prodockit", "template-sync", "--apply", "--force", "x"])

    assert "template-sync --apply --force x" in (tmp_path / LOG_FILE).read_text(encoding="utf-8")


def test_a_timestamp_keeps_its_utc_offset() -> None:
    """Local time reads naturally; the offset is what makes it comparable."""
    stamp = now()

    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$", stamp), stamp


def test_the_log_is_kept_out_of_git_whatever_the_manifest_says() -> None:
    """The log is the tool's own artefact, so the tool ignores it.

    Not left to the manifest: a project on an older template would
    otherwise commit a diagnostic file it never asked for.
    """
    manifest = load_manifest(MANIFEST)

    assert LOG_FILE in missing_ignores(manifest, [])
    assert LOG_FILE not in missing_ignores(manifest, [LOG_FILE])


def test_the_log_adds_its_own_ignore_line_once(tmp_path: pathlib.Path) -> None:
    """A dry run writes the log, so a dry run must also ignore it.

    The `.gitignore` stage only runs under `--apply`, which would leave
    the first (dry) run's log untracked and one `git add -A` away from
    being committed.
    """
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")

    assert ignore_the_log(tmp_path) is True
    assert ignore_the_log(tmp_path) is False

    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")

    assert text.count(LOG_FILE) == 1
    assert "build/" in text


def test_the_log_ignores_itself_where_there_is_no_gitignore_yet(
    tmp_path: pathlib.Path,
) -> None:
    """A project need not already have one for the log to be covered."""
    assert ignore_the_log(tmp_path) is True
    assert LOG_FILE in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_a_branch_holding_diverged_commits_is_refused_not_switched_to(
    tmp_path: pathlib.Path,
) -> None:
    """Only real divergence is refused: commits on the branch that the
    project does not have, and commits on the project the branch does
    not. Switching to it would run the sync against work that has parted
    company with where the reader is - and report success.
    """
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "--quiet")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "macros.py").write_text("first", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "first")

    name = branch_name("1.5.0")
    git("checkout", "--quiet", "-b", name)
    (tmp_path / "half-done.txt").write_text("an abandoned run", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "left on the branch")
    git("checkout", "--quiet", "-")

    (tmp_path / "chapter.md").write_text("my writing", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "my work")

    run = git_runner(tmp_path)
    with pytest.raises(TemplateSyncError, match=re.escape(name)) as caught:
        start_branch(run, name)

    assert "diverged" in str(caught.value)
    on = subprocess.run(
        ["git", "branch", "--show-current"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert on != name, "the refusal must leave the reader where they were"
    assert (tmp_path / "chapter.md").exists()


def test_a_branch_left_behind_by_an_earlier_run_is_moved_forward(
    tmp_path: pathlib.Path,
) -> None:
    """The ordinary case over a term, and one that used to block a run.

    A branch a previous run created and left with nothing in it, or one
    whose work has since been merged, holds nothing the project does not
    already have. Refusing it stopped students who had done nothing
    wrong, on every run, until they deleted a branch by hand.
    """
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "--quiet")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "macros.py").write_text("first", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "first")

    name = branch_name("1.5.0")
    git("branch", name)  # an earlier run's branch, with nothing on it

    (tmp_path / "chapter.md").write_text("my writing", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "my work")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()

    run = git_runner(tmp_path)

    assert start_branch(run, name) is True

    on = subprocess.run(
        ["git", "branch", "--show-current"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    tip = subprocess.run(
        ["git", "rev-parse", name], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()

    assert on == name
    assert tip == head, "the branch must be moved to the work, not the work to the branch"
    assert (tmp_path / "chapter.md").exists()


def test_a_branch_that_already_contains_your_work_is_continued_on(
    tmp_path: pathlib.Path,
) -> None:
    """The case the refusal above must not break: a second run against
    the same template version belongs on the branch the first one made.
    """
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "--quiet")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "macros.py").write_text("first", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "first")

    run = git_runner(tmp_path)
    name = branch_name("1.5.0")

    assert start_branch(run, name) is True
    git("checkout", "--quiet", "-")  # back to where the reader was
    assert start_branch(run, name) is True

    on = subprocess.run(
        ["git", "branch", "--show-current"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert on == name


# ---------------------------------------------------------------------------
# Running it repeatedly, over a term
# ---------------------------------------------------------------------------


def test_a_sidecar_that_is_already_there_is_not_written_again(
    tmp_path: pathlib.Path,
) -> None:
    """The second run against the same template version has nothing to do.

    A `keep` writes the template's copy to a `.new` sidecar. Run it again
    and that sidecar is already there with exactly those bytes - so the
    run must not count it as work, or every run for the rest of a term
    branches and announces a change that does not exist.
    """
    (tmp_path / "macros.py").write_text("mine", encoding="utf-8")
    (tmp_path / "macros.py.new").write_text("theirs", encoding="utf-8")
    plan = [FileAction("macros.py", "macros.py", "keep", "edited here")]

    assert pending_writes(plan, tmp_path, lambda _p: b"theirs") == []


def test_a_sidecar_whose_template_has_moved_on_is_written_again(
    tmp_path: pathlib.Path,
) -> None:
    """The case the skip above must not swallow."""
    (tmp_path / "macros.py").write_text("mine", encoding="utf-8")
    (tmp_path / "macros.py.new").write_text("theirs, last term", encoding="utf-8")
    plan = [FileAction("macros.py", "macros.py", "keep", "edited here")]

    assert pending_writes(plan, tmp_path, lambda _p: b"theirs, revised") == plan


def test_a_file_the_project_lacks_is_pending(tmp_path: pathlib.Path) -> None:
    plan = [FileAction(".python-version", ".python-version", "add", "absent here")]

    assert pending_writes(plan, tmp_path, lambda _p: b"3.13\n") == plan


def test_same_is_never_pending(tmp_path: pathlib.Path) -> None:
    """`same` is most of the tree, and reading every file to confirm it
    would be the slowest part of a run that has nothing to do."""
    plan = [FileAction("macros.py", "macros.py", "same", "matches")]

    def explode(_path: str) -> bytes:
        raise AssertionError("a `same` action must not be read at all")

    assert pending_writes(plan, tmp_path, explode) == []


# ---------------------------------------------------------------------------
# Fetching the template
# ---------------------------------------------------------------------------


class RecordingGit:
    """A git runner that records commands and answers as told.

    Every test below drives `ensure_template` through this rather than a
    real git, so nothing here can reach the network however the suite is
    run.
    """

    def __init__(self, **answers: bool) -> None:
        self.commands: list[list[str]] = []
        self.answers = answers

    def __call__(self, command: Sequence[str]) -> bool:
        self.commands.append(list(command))
        for verb, answer in self.answers.items():
            if verb in command:
                return answer
        return True


def test_the_cache_follows_each_platform_s_convention() -> None:
    """Asked about platforms this is not running on, so the answer does
    not depend on the machine the suite happens to be on."""
    mac = cache_root({"HOME": "/Users/someone"}, "darwin")
    windows = cache_root({"LOCALAPPDATA": r"C:\\Users\\someone\\AppData\\Local"}, "win32")
    linux = cache_root({"HOME": "/home/someone"}, "linux")
    xdg = cache_root({"HOME": "/home/someone", "XDG_CACHE_HOME": "/elsewhere"}, "linux")

    assert mac.parts[-3:] == ("Library", "Caches", "prodockit")
    assert windows.parts[-2:] == ("prodockit", "cache")
    assert linux.parts[-2:] == (".cache", "prodockit")
    assert xdg.parts[-2:] == ("elsewhere", "prodockit")


def test_the_cache_can_be_pointed_somewhere_else() -> None:
    """So a test, or a locked-down machine, need not write to $HOME."""
    root = cache_root({"HOME": "/home/someone", "PRODOCKIT_CACHE": "/tmp/somewhere"}, "linux")

    assert root.parts[-1:] == ("somewhere",)


def test_two_hosts_templates_do_not_share_a_cache_entry() -> None:
    """A project on Surrey's GitLab and one on GitHub track different
    templates that share a repository name. Caching both at the same path
    would hand a project the other one's files."""
    root = pathlib.Path("/cache")
    github = cache_path_for("git@github.com:buckwem/prodockit-template.git", root)
    surrey = cache_path_for("git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git", root)

    assert github != surrey
    assert "github.com" in github.parts
    assert "gitlab.surrey.ac.uk" in surrey.parts


def test_a_template_that_is_not_there_yet_is_cloned(tmp_path: pathlib.Path) -> None:
    run = RecordingGit()
    path = tmp_path / "templates" / "github.com" / "someone" / "report-template"

    assert ensure_template("git@github.com:someone/report-template.git", path, run) == "cloned"
    assert run.commands[-1][:2] == ["git", "clone"]
    assert path.parent.exists(), "the parent has to be made before git can clone into it"


def test_a_clone_that_fails_says_what_to_try(tmp_path: pathlib.Path) -> None:
    run = RecordingGit(clone=False)

    with pytest.raises(TemplateSyncError, match="--template-path"):
        ensure_template("git@github.com:someone/report-template.git", tmp_path / "t", run)


def test_a_cached_template_is_brought_up_to_date(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "cached"
    (path / ".git").mkdir(parents=True)
    run = RecordingGit()

    assert ensure_template("git@github.com:someone/report-template.git", path, run) == "updated"

    verbs = [c[3] for c in run.commands if len(c) > 3]

    assert "fetch" in verbs
    assert "reset" in verbs, "fetching alone leaves the working tree on the old version"
    assert not any(c[:2] == ["git", "clone"] for c in run.commands)


def test_a_host_that_cannot_be_reached_uses_what_is_cached(tmp_path: pathlib.Path) -> None:
    """Three answers, not two. A fetch that cannot reach the host is not
    the same as one that found nothing new, and it is not a failure - a
    student on a train should still see what their project would do.
    """
    path = tmp_path / "cached"
    (path / ".git").mkdir(parents=True)
    run = RecordingGit(fetch=False)

    assert ensure_template("git@github.com:someone/report-template.git", path, run) == "offline"
    assert not any("reset" in c for c in run.commands), (
        "a failed fetch must not be followed by a reset onto whatever FETCH_HEAD was"
    )


def test_a_cache_that_cannot_be_moved_forward_is_refused(tmp_path: pathlib.Path) -> None:
    """Rather than syncing against a half-updated checkout."""
    path = tmp_path / "cached"
    (path / ".git").mkdir(parents=True)
    run = RecordingGit(reset=False)

    with pytest.raises(TemplateSyncError, match="delete that directory"):
        ensure_template("git@github.com:someone/report-template.git", path, run)


# ---------------------------------------------------------------------------
# Finishing a sync: merge into the branch the host builds from, and push
# ---------------------------------------------------------------------------


def test_the_default_branch_comes_from_the_remote_first() -> None:
    """What the host builds from is what the host says, not what happens
    to be checked out - a pipeline guarded on `$CI_DEFAULT_BRANCH` follows
    the remote's idea of default."""
    answers = {("git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"): "refs/remotes/origin/trunk"}

    assert default_branch(lambda c: answers.get(tuple(c))) == "trunk"


def test_the_default_branch_falls_back_to_the_usual_names() -> None:
    def read(command: Sequence[str]) -> str | None:
        if "symbolic-ref" in command:
            return None
        return "ok" if "refs/heads/master" in command else None

    assert default_branch(read) == "master"


def test_no_default_branch_at_all_is_answered_with_none() -> None:
    """So the caller can say --push has nowhere to go, rather than
    guessing a branch and merging into it."""
    assert default_branch(lambda _c: None) is None


def test_uncommitted_writing_does_not_block_the_merge() -> None:
    """A project being written always has uncommitted work in it.

    An earlier version refused any modified file and so refused almost
    every real run - including its own staged changes, which are exactly
    what it was about to commit. Template-owned dirt is refused earlier,
    by `blocking_changes`; a half-written chapter is not a reason to stop.
    """
    def read(command: Sequence[str]) -> str | None:
        if "status" in command or "diff" in command:
            return " M docs/section2.md"
        if "rev-list" in command:
            return "0"
        return "ok"

    assert publish_blockers(read, "main") == []


def test_a_target_behind_its_remote_blocks_the_merge() -> None:
    """Or the push is rejected after the merge has already happened."""
    def read(command: Sequence[str]) -> str | None:
        if "status" in command:
            return ""
        if "rev-list" in command:
            return "3"
        return "ok"

    problems = publish_blockers(read, "main")

    assert any("behind origin/main" in p for p in problems)


def test_a_clean_repository_in_step_has_no_blockers() -> None:
    def read(command: Sequence[str]) -> str | None:
        if "status" in command:
            return ""
        if "rev-list" in command:
            return "0"
        return "ok"

    assert publish_blockers(read, "main") == []


def test_a_failed_merge_is_never_followed_by_a_push() -> None:
    """Or the host is handed whatever the working tree was left in."""
    done: list[list[str]] = []

    def run(command: Sequence[str]) -> bool:
        done.append(list(command))
        return "merge" not in command

    with pytest.raises(TemplateSyncError, match="resolve it by hand"):
        publish(run, "template-update-1", "main", "Sync")

    assert not any("push" in c for c in done)


def test_a_failed_push_says_the_merge_is_safe() -> None:
    """The work is committed and merged; only the host is behind."""
    def run(command: Sequence[str]) -> bool:
        return "push" not in command

    with pytest.raises(TemplateSyncError, match=re.escape("nothing is lost")):
        publish(run, "template-update-1", "main", "Sync")


def test_a_successful_publish_commits_merges_and_pushes_in_order() -> None:
    done: list[list[str]] = []

    def run(command: Sequence[str]) -> bool:
        done.append(list(command))
        return True

    assert publish(run, "template-update-1", "main", "Sync with the template") == "main"

    verbs = [c[1] for c in done]

    assert verbs == ["commit", "checkout", "merge", "push"]
    assert "--no-ff" in done[2], "the sync should be one thing to read, and to revert"


def test_the_remote_is_asked_before_the_local_cache() -> None:
    """`refs/remotes/origin/HEAD` is a cache written at clone time and it
    goes stale. On a test host it pointed at a `template-update-...`
    branch, which would have merged a branch into itself and pushed it.
    """
    def read(command: Sequence[str]) -> str | None:
        if "ls-remote" in command:
            return "ref: refs/heads/main\tHEAD\n0123456789abcdef\tHEAD"
        if "symbolic-ref" in command:
            return "refs/remotes/origin/template-update-6fbbbbeb8"
        return None

    assert default_branch(read) == "main"


def test_the_local_cache_is_used_when_the_remote_cannot_be_asked() -> None:
    """Offline, a stale answer beats no answer - the blockers below still
    refuse the case where it points somewhere absurd."""
    def read(command: Sequence[str]) -> str | None:
        if "ls-remote" in command:
            return None
        if "symbolic-ref" in command:
            return "refs/remotes/origin/trunk"
        return None

    assert default_branch(read) == "trunk"


def test_merging_a_branch_into_itself_is_refused() -> None:
    """Whatever produced that answer, it is never the right one."""
    problems = publish_blockers(lambda _c: "ok", "template-update-1", "template-update-1")

    assert any("into itself" in p for p in problems)
