# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Review new template settings once, without treating them as executable policy."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import tomlkit
from packaging.version import Version

from prodockit import __version__
from prodockit.adopt_toml import inline
from prodockit.project_config import _markdown_extensions
from prodockit.renderer_resilience import RetryNotice, RetryReporter, run_with_retries

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

LEDGER = ".prodockit-adopt.toml"
MAX_BYTES = 2 * 1024 * 1024
MAX_RATE_LIMIT_WAIT = 10.0
OUTCOMES = {"added", "commented", "excluded", "already present"}
# Whole subtrees are excluded, not copied as commented branding examples.
EXCEPTIONS = (
    ("project", "site_name"),
    ("project", "site_description"),
    ("project", "site_author"),
    ("project", "site_url"),
    ("project", "site_dir"),
    ("project", "docs_dir"),
    ("project", "repo_url"),
    ("project", "repo_name"),
    ("project", "edit_uri"),
    ("project", "copyright"),
    ("project", "nav"),
    ("project", "theme"),
    ("project", "plugins"),
    ("project", "extra", "pdf_copyright"),
    ("project", "extra", "social"),
    ("project", "extra", "is_surrey"),
    ("project", "markdown_extensions", "pymdownx.emoji", "options", "custom_icons"),
)
EXCLUDED_ASSETS = {"stylesheets/template.css"}


class SettingsError(ValueError):
    """A snapshot or ledger cannot be used safely."""


@dataclass(frozen=True)
class Snapshot:
    source: str
    identity: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.source.encode("utf-8")).hexdigest()


def _parse(source: str) -> dict[str, Any]:
    try:
        parsed = tomllib.loads(source)
    except tomllib.TOMLDecodeError as error:
        raise SettingsError(f"invalid template TOML: {error}") from error
    if not isinstance(parsed.get("project"), dict):
        raise SettingsError("template configuration must contain [project]")
    return parsed


class _NoCredentialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        raise SettingsError(
            "authenticated template request redirected; refusing to forward credentials"
        )


def _fetch_once(url: str) -> str:
    headers = {"User-Agent": "prodockit-adopt"}
    parsed = urllib.parse.urlsplit(url)
    token = os.environ.get("GITHUB_TOKEN", "")
    authenticated = bool(token and parsed.scheme == "https" and parsed.netloc == "api.github.com")
    if authenticated:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    open_request = (
        urllib.request.build_opener(_NoCredentialRedirect()).open
        if authenticated
        else urllib.request.urlopen
    )
    with open_request(request, timeout=15) as response:
        data: bytes = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SettingsError("template response exceeds the size limit")
    return data.decode("utf-8")


def _github_rate_limit(error: urllib.error.HTTPError) -> tuple[float, str] | None:
    """Read bounded rate-limit evidence without exposing response bodies or tokens."""
    if urllib.parse.urlsplit(error.url).hostname != "api.github.com" or error.code not in {
        403,
        429,
    }:
        return None
    headers = {key.lower(): value for key, value in (error.headers or {}).items()}
    evidence = str(error.reason).lower()
    if error.code == 403 and not (
        headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers
    ):
        evidence += error.read(4096).decode("utf-8", errors="replace").lower()
        if "rate limit" not in evidence and "abuse detection" not in evidence:
            return None
    delays: list[float] = []
    now = time.time()

    def seconds(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite retry time")
        return number

    retry = headers.get("retry-after", "")
    if retry:
        try:
            delays.append(max(0.0, seconds(retry)))
        except ValueError:
            with suppress(ValueError, TypeError, OverflowError):
                delays.append(max(0.0, parsedate_to_datetime(retry).timestamp() - now))
    reset = headers.get("x-ratelimit-reset", "")
    if headers.get("x-ratelimit-remaining") == "0" and reset:
        with suppress(ValueError):
            delays.append(max(0.0, seconds(reset) - now))
    delay = max(delays) if delays else 60.0
    try:
        when = datetime.fromtimestamp(now + delay, timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):
        when = "the GitHub rate-limit reset time"
    return delay, (
        f"GitHub API rate limit reached (HTTP {error.code}). Wait until {when} before retrying, "
        "or supply GITHUB_TOKEN securely for authenticated API requests. "
        "A validated cache for this Prodockit version or --template-config can be used instead."
    )


def _fetch(url: str, *, reporter: RetryReporter | None = None) -> str:
    """Retry read-only requests, never malformed data or permanent HTTP failures."""

    minimum_wait = 0.0
    rate_limit_message = ""

    def attempt() -> str | OSError:
        nonlocal minimum_wait, rate_limit_message
        minimum_wait = 0.0
        rate_limit_message = ""
        try:
            return _fetch_once(url)
        except urllib.error.HTTPError as error:
            limited = _github_rate_limit(error)
            if limited is not None:
                minimum_wait, rate_limit_message = limited
                if minimum_wait > MAX_RATE_LIMIT_WAIT:
                    error.close()
                    raise SettingsError(rate_limit_message) from error
            elif error.code not in {408, 429, 500, 502, 503, 504}:
                raise
            error.close()
            return error
        except (OSError, urllib.error.URLError) as error:
            return error

    def detail(value: str | OSError) -> str:
        if isinstance(value, urllib.error.HTTPError):
            return f"service temporarily unavailable: HTTP {value.code}"
        return str(value)

    def report(notice: RetryNotice) -> None:
        if reporter is not None:
            reporter(replace(notice, delay=max(notice.delay, minimum_wait)))

    result = run_with_retries(
        "template settings download",
        attempt,
        succeeded=lambda value: isinstance(value, str),
        failure_detail=detail,
        reporter=report,
        sleeper=lambda delay: time.sleep(max(delay, minimum_wait)),
    )
    if isinstance(result.value, OSError):
        if rate_limit_message:
            raise SettingsError(rate_limit_message) from result.value
        raise result.value
    return result.value


def _online_snapshot(*, reporter: RetryReporter | None = None) -> Snapshot:
    def fetch(url: str) -> str:
        return _fetch(url, reporter=reporter) if reporter is not None else _fetch(url)

    metadata = json.loads(
        fetch("https://api.github.com/repos/buckwem/prodockit-template/commits/main")
    )
    if not isinstance(metadata, dict):
        raise SettingsError("GitHub returned invalid template metadata")
    revision = metadata.get("sha", "")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SettingsError("GitHub did not return a valid template revision")
    base = f"https://raw.githubusercontent.com/buckwem/prodockit-template/{revision}/"
    requirements = fetch(base + "requirements.txt")
    pins = re.findall(r"(?mi)^\s*prodockit\s*(?:==|>=)\s*([^\s;#]+)\s*(?:#.*)?$", requirements)
    if len(pins) != 1 or Version(pins[0]) > Version(__version__):
        raise SettingsError(
            f"current template requires newer or unspecified Prodockit (installed {__version__}); "
            "use a compatible cached snapshot or --template-config"
        )
    source = fetch(base + "zensical.toml")
    _parse(source)
    return Snapshot(source, f"github:prodockit-template@{revision}")


def cache_path() -> Path:
    from prodockit.template_sync import cache_root

    return cache_root() / "adopt-settings" / f"{__version__}.json"


def load_snapshot(
    *, offline: bool = False, local: Path | None = None, reporter: RetryReporter | None = None
) -> Snapshot:
    """Resolve once per command. A preview never writes the cache."""
    if local is not None:
        if local.stat().st_size > MAX_BYTES:
            raise SettingsError("local template configuration exceeds the size limit")
        source = local.read_text(encoding="utf-8")
        _parse(source)
        return Snapshot(source, f"local:{local.resolve()}")
    failure = "offline mode"
    if not offline:
        try:
            return (
                _online_snapshot(reporter=reporter) if reporter is not None else _online_snapshot()
            )
        except (OSError, ValueError, urllib.error.URLError) as error:
            failure = str(error)
    path = cache_path()
    try:
        if path.stat().st_size > MAX_BYTES * 4:
            raise SettingsError("cached template exceeds the size limit")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["version"] != __version__:
            raise SettingsError("cached snapshot belongs to another Prodockit version")
        if not isinstance(data["source"], str) or not isinstance(data["identity"], str):
            raise SettingsError("cached template has invalid fields")
        snapshot = Snapshot(data["source"], data["identity"])
        if snapshot.digest != data["digest"]:
            raise SettingsError("cached snapshot checksum mismatch")
        _parse(snapshot.source)
        return Snapshot(snapshot.source, f"cached ({failure}): {snapshot.identity}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SettingsError(
            f"cannot review template settings: {failure}. No usable cache at {path}. "
            "Retry online or provide --template-config PATH to a compatible zensical.toml."
        ) from error


def cache_content(snapshot: Snapshot) -> bytes:
    return json.dumps(
        {
            "version": __version__,
            "source": snapshot.source,
            "identity": snapshot.identity,
            "digest": snapshot.digest,
        },
        ensure_ascii=False,
    ).encode("utf-8")


def settings(parsed: Mapping[str, Any]) -> dict[tuple[str, ...], Any]:
    """Canonical key paths; extension names remain single path components."""
    result: dict[tuple[str, ...], Any] = {}

    def visit(value: Any, path: tuple[str, ...]) -> None:
        if len(path) == 1 and isinstance(value, Mapping) and not value:
            return
        if path == ("project", "markdown_extensions"):
            value = _markdown_extensions(value)
        if isinstance(value, Mapping) and value:
            for key, child in value.items():
                visit(child, (*path, str(key)))
        else:
            result[path] = value

    for key, value in parsed.items():
        visit(value, (str(key),))
    return result


def load_ledger(root: Path) -> dict[tuple[str, ...], str]:
    path = root / LEDGER
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != 1 or not isinstance(data.get("settings", []), list):
            raise ValueError("unsupported schema or settings list")
        entries: dict[tuple[str, ...], str] = {}
        for entry in data.get("settings", []):
            keys, outcome = entry["path"], entry["outcome"]
            if not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys):
                raise ValueError("setting paths must be nonempty lists of strings")
            if not isinstance(outcome, str) or outcome not in OUTCOMES or tuple(keys) in entries:
                raise ValueError("invalid outcome or duplicate setting")
            entries[tuple(keys)] = outcome
        return entries
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SettingsError(
            f"cannot read {path}: {error}; repair it or delete it to reset"
        ) from error


@dataclass(frozen=True)
class Review:
    source: str
    ledger: str
    count: int


def _value(value: Any) -> str:
    return inline(value).as_string()


def review(root: Path, source: str, snapshot: Snapshot, *, original: str) -> Review:
    """Classify only unseen keys after Adopt's known-setting handlers ran."""
    entries = load_ledger(root)
    current = settings(_parse(source))
    before = settings(_parse(original))
    additions: list[str] = []
    count = 0
    for path, value in settings(_parse(snapshot.source)).items():
        if path in entries:
            continue
        count += 1
        if any(path[: len(prefix)] == prefix for prefix in EXCEPTIONS):
            outcome = "excluded"
        elif path in current:
            outcome = "already present" if path in before else "added"
        else:
            if isinstance(value, list):
                value = [
                    item
                    for item in value
                    if not isinstance(item, str) or item.split("?", 1)[0] not in EXCLUDED_ASSETS
                ]
            marker = "# prodockit-adopt setting: " + json.dumps(list(path), ensure_ascii=False)
            if marker not in source:
                header = ".".join(json.dumps(key, ensure_ascii=False) for key in path[:-1])
                lines = [
                    marker,
                    "# New template setting: review before enabling; merge into the named table.",
                ]
                if value == {}:
                    lines.append("# [" + ".".join(json.dumps(k) for k in path) + "]")
                else:
                    lines.append(f"# In [{header}]:")
                    rendered = f"{json.dumps(path[-1])} = {_value(value)}"
                    lines.extend("# " + line for line in rendered.splitlines())
                additions.append("\n".join(lines))
            outcome = "commented"
        entries[path] = outcome
    if additions:
        document = tomlkit.parse(source)
        for addition in additions:
            document.add(tomlkit.nl())
            for line in addition.splitlines():
                document.add(tomlkit.comment(line.removeprefix("# ")))
        source = tomlkit.dumps(document)
    _parse(source)
    ledger = tomlkit.document()
    ledger.add(
        tomlkit.comment("Configuration review only. Delete this file to review settings again.")
    )
    ledger.add(tomlkit.comment("Software versions and runtime health are checked independently."))
    ledger["schema"] = 1
    ledger["template_source"] = snapshot.identity
    ledger["template_sha256"] = snapshot.digest
    records = tomlkit.aot()
    for path, outcome in sorted(entries.items()):
        record = tomlkit.table()
        record["path"] = list(path)
        record["outcome"] = outcome
        records.append(record)
    if entries:
        ledger["settings"] = records
    return Review(source, tomlkit.dumps(ledger), count)
