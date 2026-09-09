# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Template additions are reviewed once, not treated as executable defaults."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from prodockit import adopt
from prodockit import adopt_settings as settings
from prodockit.adopt import AdoptError, AdoptOptions, ensure_zensical_config, tomllib

TEMPLATE = """[project]
site_name = "Do not copy this branding"
extra_css = ["stylesheets/pdk.css", "stylesheets/template.css", "stylesheets/extra.css"]
[project.extra]
pdf_page_size = "A4"
future_setting = 42
pdf_copyright = "Do not copy this footer"
[project.markdown_extensions."prodockit.headings"]
numbering = "continuous"
"""


def project(root: Path) -> Path:
    path = root / "zensical.toml"
    path.write_text('[project]\nsite_name = "My document"\n')
    return path


def options(source=TEMPLATE):
    return AdoptOptions(template_snapshot=settings.Snapshot(source, "test:revision"))


def test_outcomes_and_inactive_unknowns(tmp_path):
    path = project(tmp_path)
    ensure_zensical_config(tmp_path, options())
    ledger = settings.load_ledger(tmp_path)
    assert ledger[("project", "site_name")] == "excluded"
    assert ledger[("project", "extra", "pdf_page_size")] == "added"
    assert ledger[("project", "extra", "future_setting")] == "commented"
    source = path.read_text()
    assert '"future_setting" = 42' in source
    assert "future_setting" not in tomllib.loads(source)["project"]["extra"]
    assert "Do not copy" not in source
    assert "template.css" not in source


def test_new_template_key_is_discovered_without_an_adopt_change(tmp_path):
    path = project(tmp_path)
    ensure_zensical_config(tmp_path, options())
    # An old key changing value is intentionally not reprocessed.
    source = TEMPLATE.replace("42", "99").replace(
        "future_setting = 99", 'future_setting = 99\nnew_option = "next"'
    )
    ensure_zensical_config(tmp_path, options(source))
    result = path.read_text()
    assert '# "future_setting" = 42' in result
    assert '# "future_setting" = 99' not in result
    assert '# "new_option" = "next"' in result
    assert len(settings.load_ledger(tmp_path)) == len(settings.settings(tomllib.loads(source)))


def test_repeated_runs_and_reset_do_not_duplicate_or_rewrite_config(tmp_path):
    path = project(tmp_path)
    ensure_zensical_config(tmp_path, options())
    original = path.read_bytes()
    stamp = path.stat().st_mtime_ns
    ledger_stamp = (tmp_path / settings.LEDGER).stat().st_mtime_ns
    ensure_zensical_config(tmp_path, options())
    assert (tmp_path / settings.LEDGER).stat().st_mtime_ns == ledger_stamp
    (tmp_path / settings.LEDGER).unlink()
    ensure_zensical_config(tmp_path, options())
    assert path.read_bytes() == original
    assert path.stat().st_mtime_ns == stamp


def test_existing_user_value_is_preserved_and_recorded(tmp_path):
    path = project(tmp_path)
    path.write_text(path.read_text() + "[project.extra]\nfuture_setting = 7 # mine\n")
    ensure_zensical_config(tmp_path, options())
    assert "future_setting = 7 # mine" in path.read_text()
    assert (
        settings.load_ledger(tmp_path)[("project", "extra", "future_setting")] == "already present"
    )


def test_preview_is_read_only(tmp_path):
    path = project(tmp_path)
    before = path.read_bytes()
    _, planned = adopt._planned_zensical_config(tmp_path, options())
    assert "future_setting" in planned
    assert path.read_bytes() == before
    assert not (tmp_path / settings.LEDGER).exists()


def test_invalid_ledger_blocks_before_config_write(tmp_path):
    path = project(tmp_path)
    before = path.read_bytes()
    (tmp_path / settings.LEDGER).write_text("schema = 999\n")
    with pytest.raises(AdoptError, match="delete it to reset"):
        ensure_zensical_config(tmp_path, options())
    assert path.read_bytes() == before


def test_ledger_write_failure_is_resumable(tmp_path, monkeypatch):
    path = project(tmp_path)
    write = adopt._atomic_write

    def fail_ledger(target, content):
        if target.name == settings.LEDGER:
            raise AdoptError("test ledger failure")
        write(target, content)

    monkeypatch.setattr(adopt, "_atomic_write", fail_ledger)
    with pytest.raises(AdoptError, match="test ledger failure"):
        ensure_zensical_config(tmp_path, options())
    before = path.read_bytes()
    assert not (tmp_path / settings.LEDGER).exists()
    monkeypatch.setattr(adopt, "_atomic_write", write)
    ensure_zensical_config(tmp_path, options())
    assert path.read_bytes() == before
    assert settings.load_ledger(tmp_path)


def test_ledger_does_not_skip_software_assessment(tmp_path, monkeypatch):
    project(tmp_path)
    ensure_zensical_config(tmp_path, options())
    calls = []

    def plan(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(
            blocked=False, needs_work=True, detail="software changed", commands=(), files=()
        )

    monkeypatch.setattr(adopt.supported_toolchain, "plan", plan)
    result = adopt.assess(tmp_path, options())
    assert calls
    assert next(step for step in result if step.id == "dependency").needs_work


def test_unknown_multiline_value_cannot_escape_comment(tmp_path):
    path = project(tmp_path)
    source = '[project]\n[project.extra]\nnew = """hello\n[bad]\nx=1\n"""\n'
    ensure_zensical_config(tmp_path, options(source))
    assert "bad" not in tomllib.loads(path.read_text())
    assert "new" not in tomllib.loads(path.read_text())["project"]["extra"]


def test_offline_cache_and_local_snapshot_do_not_access_network(tmp_path, monkeypatch):
    cache = tmp_path / "snapshot.json"
    monkeypatch.setattr(settings, "cache_path", lambda: cache)
    monkeypatch.setattr(settings, "_online_snapshot", lambda: pytest.fail("network called"))
    cached = settings.Snapshot(TEMPLATE, "github:test-revision")
    cache.write_bytes(settings.cache_content(cached))
    assert settings.load_snapshot(offline=True).source == TEMPLATE
    local = tmp_path / "template.toml"
    local.write_text(TEMPLATE)
    assert settings.load_snapshot(local=local).source == TEMPLATE


def test_bad_cache_rejected(tmp_path, monkeypatch):
    cache = tmp_path / "snapshot.json"
    monkeypatch.setattr(settings, "cache_path", lambda: cache)
    data = json.loads(settings.cache_content(settings.Snapshot(TEMPLATE, "github:test")))
    data["digest"] = "corrupt"
    cache.write_text(json.dumps(data))
    with pytest.raises(settings.SettingsError, match="No usable cache"):
        settings.load_snapshot(offline=True)


def test_download_retries_transient_failure_then_recovers(monkeypatch):
    calls, delays, notices = [], [], []

    def fetch(url):
        calls.append(url)
        if len(calls) < 3:
            raise settings.urllib.error.URLError("connection reset")
        return TEMPLATE

    monkeypatch.setattr(settings, "_fetch_once", fetch)
    monkeypatch.setattr(settings.time, "sleep", delays.append)
    assert settings._fetch("https://example.test/template", reporter=notices.append) == TEMPLATE
    assert delays == [2.0, 5.0]
    assert len(notices) == 2


@pytest.mark.parametrize("code,attempts", [(404, 1), (403, 1), (429, 3), (503, 3)])
def test_download_http_retry_is_bounded(monkeypatch, code, attempts):
    calls = []

    def fetch(url):
        calls.append(url)
        raise settings.urllib.error.HTTPError(url, code, "test", {}, None)

    monkeypatch.setattr(settings, "_fetch_once", fetch)
    monkeypatch.setattr(settings.time, "sleep", lambda delay: None)
    with pytest.raises(settings.urllib.error.HTTPError):
        settings._fetch("https://example.test/template")
    assert len(calls) == attempts


def test_invalid_download_is_not_retried(monkeypatch):
    def fetch(url):
        raise settings.SettingsError("template response exceeds the size limit")

    monkeypatch.setattr(settings, "_fetch_once", fetch)
    monkeypatch.setattr(settings.time, "sleep", lambda delay: pytest.fail("retried invalid data"))
    with pytest.raises(settings.SettingsError, match="size limit"):
        settings._fetch("https://example.test/template")


def test_online_source_uses_same_immutable_revision_and_compatible_pin(monkeypatch):
    from prodockit import __version__

    urls = []
    sha = "a" * 40

    def fetch(url):
        urls.append(url)
        if "api.github.com" in url:
            return json.dumps({"sha": sha})
        if url.endswith("requirements.txt"):
            return f"prodockit=={__version__}\n"
        return TEMPLATE

    monkeypatch.setattr(settings, "_fetch", fetch)
    assert settings._online_snapshot().source == TEMPLATE
    assert all(sha in url for url in urls[1:])
    monkeypatch.setattr(
        settings,
        "_fetch",
        lambda url: json.dumps({"sha": sha}) if "api.github.com" in url else "prodockit==999.0.0\n",
    )
    with pytest.raises(settings.SettingsError, match="requires newer or unspecified"):
        settings._online_snapshot()
