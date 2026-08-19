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
    FILE_ACTIONS,
    MANIFEST_FILE,
    TEMPLATE_REMOTES,
    Baseline,
    FileAction,
    TemplateSyncError,
    add_config_table,
    append_ignores,
    apply_config_changes,
    apply_file_actions,
    apply_seeds,
    baseline_report,
    blocking_changes,
    classification_report,
    config_changes,
    derive_baseline,
    leftovers,
    load_manifest,
    missing_ignores,
    missing_seeds,
    plan_template_files,
    resolve_template,
    set_config_value,
    unclassified,
    update_report,
    written_report,
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


# ---------------------------------------------------------------------------
# Reporting, and --verbose
# ---------------------------------------------------------------------------

FILES = [
    "macros.py",
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

    counts = {line.split()[0]: int(line.split()[1]) for line in lines}
    assert counts == {"template": 2, "project": 2, "shared": 1, "excluded": 1}
    assert sum(counts.values()) == len(FILES)


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

    assert not any("unclassified" in line for line in quiet)
    assert any("unclassified" in line for line in noisy)
    assert any("tools/x.json" in line for line in noisy)


def test_the_edited_files_are_always_listed() -> None:
    """They are the reason the tool will leave something alone, so a
    count of them is not actionable."""
    baseline = Baseline(version="v2", matched=1, total=2, edited=("macros.py",))

    lines = baseline_report(baseline)

    assert any("macros.py" in line for line in lines)
    assert any(line.startswith("edited") for line in lines)


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

    assert lines == ["no template-owned files found - nothing to compare"]


def test_each_group_says_what_will_happen_to_it() -> None:
    """A group's name is not its behaviour. `project` and `excluded` both
    mean untouched, for entirely different reasons, and a reader should
    not have to know the manifest to tell them apart."""
    lines = classification_report(load_manifest(MANIFEST), FILES)

    text = "\n".join(lines)
    assert "template" in text and "replace where unedited" in text
    assert "project" in text and "never written" in text
    assert "shared" in text and "merge" in text
    assert "excluded" in text and "not delivered" in text


def test_every_group_has_an_action_including_the_error_one() -> None:
    """A group added to the report without an action would render as a
    bare count, or raise - neither is discovered by reading."""
    from prodockit.template_sync import GROUP_ACTIONS, REPORT_ORDER

    assert set(REPORT_ORDER) == set(GROUP_ACTIONS)


def test_the_counts_survive_the_actions_being_added() -> None:
    """The count is still parseable, and still adds up to the tree."""
    lines = classification_report(load_manifest(MANIFEST), FILES)

    counts = {line.split()[0]: int(line.split()[1]) for line in lines}
    assert sum(counts.values()) == len(FILES)


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

    for path in ("macros.py", "docs/stylesheets/extra.css", ".github/workflows/docs.yml"):
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
        {"macros.py": "mine", "docs/stylesheets/extra.css": "mine"},
        {"macros.py": "new", "docs/stylesheets/extra.css": "new"},
        edited=["macros.py", "docs/stylesheets/extra.css"],
        force=["macros.py"],
    )

    assert plan == {"macros.py": "forced", "docs/stylesheets/extra.css": "keep"}


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

    for verbose in (False, True):
        lines = update_report(actions, verbose=verbose)
        assert any("same" in line for line in lines), "still counted"
        assert not any("macros.py" in line for line in lines), verbose
        assert any("a.py" in line for line in lines)


def test_the_update_report_says_why_for_each_group() -> None:
    actions = [FileAction("a.py", "a.py", "keep", FILE_ACTIONS["keep"])]

    text = "\n".join(update_report(actions))

    assert "yours kept" in text and ".new" in text


def test_a_renamed_file_shows_both_names() -> None:
    """Otherwise a reader cannot tell why the template's path is not the
    one being written."""
    actions = [
        FileAction("docs/javascripts/extra.js", "docs/javascript/extra.js", "update", "x")
    ]

    text = "\n".join(update_report(actions))

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
    template = {"project": {"extra": {"pdf_double_sided": True}}}
    project = {"project": {"extra": {"pdf_double_sided": False}}}

    added, updated = config_changes(load_manifest(MANIFEST), template, project)

    assert (added, updated) == ([], ["project.extra.pdf_double_sided"])


def test_the_project_s_own_settings_are_never_touched() -> None:
    """`site_name` is the reader's, and nothing outside the patterns the
    manifest names may be offered at all."""
    template = {"project": {"site_name": "Document Template", "extra": {"pdf_x": 1}}}
    project = {"project": {"site_name": "My Report", "extra": {}}}

    added, updated = config_changes(load_manifest(MANIFEST), template, project)

    assert added == ["project.extra.pdf_x"]
    assert not any("site_name" in key for key in added + updated)


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

    assert missing_ignores(manifest, ["build/", "*.pyc"]) == [".vscode/"]
    assert missing_ignores(manifest, ["build/", ".vscode/"]) == []


def test_files_no_longer_delivered_are_reported_not_removed() -> None:
    """Removing files from somebody's repository because a manifest
    changed its mind is a different and more dangerous operation."""
    manifest = load_manifest(MANIFEST)

    assert leftovers(manifest, ["docs/index.md", "CHANGELOG.md", ".github/CODEOWNERS"]) == [
        ".github/CODEOWNERS",
        "CHANGELOG.md",
    ]


def test_a_key_that_holds_the_project_s_content_is_never_taken() -> None:
    """`project.extra.pdf_*` covers margins and page size - and also
    `pdf_copyright`, which on a real assignment reads `Author: 123456`
    against the template's own name. Overwriting that would put the
    template author's name on somebody else's report."""
    manifest = load_manifest(MANIFEST)
    template = {"project": {"extra": {"pdf_copyright": "Mark", "pdf_page_size": "A4"}}}
    project = {"project": {"extra": {"pdf_copyright": "123456", "pdf_page_size": "A5"}}}

    added, updated = config_changes(manifest, template, project)

    assert updated == ["project.extra.pdf_page_size"]
    assert not any("copyright" in key for key in added + updated)


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

    text = "\n".join(written_report(written))
    assert "a.py" in text
    assert "b.py" not in text, "a file that was not written must not be reported"


def test_a_project_already_in_step_says_so(tmp_path) -> None:
    assert written_report([]) == ["nothing to write - this project is already in step"]


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

    import tomllib

    assert tomllib.loads(after)["project"]["extra"]["pdf_x"] == 'a "quoted" thing'


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
    import tomllib

    assert "prodockit.tree" in tomllib.loads(after)["project"]["markdown_extensions"]
