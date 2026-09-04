# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Run one hermetic bootstrap route from an installed candidate wheel.

The parent harness creates a fresh virtual environment and starts this file
with that environment's interpreter.  The repository operations below are
real Git operations against local bare repositories; only the boundaries that
cannot exist on a hosted runner (package managers, SSH account setup, an
editor and Pages) are simulated.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import click
from click.testing import CliRunner

import prodockit
import prodockit.bootstrap.stages as bootstrap_stages_module
import prodockit.cli as cli
import prodockit.sync_repo as sync_repo_module
from prodockit.bootstrap import (
    STAGES,
    BootstrapConfig,
    CheckResult,
    CommandResult,
    Stage,
    Status,
    SubprocessRunner,
    build_context,
    current_platform,
    load,
    resolve_host,
)
from prodockit.bootstrap.fetch import Fetched
from prodockit.template_sync import read_template_stamp

TEMPLATE_RELEASE = "v1.2.3"


class AcceptanceError(RuntimeError):
    """One route did not leave the repository in its promised state."""


_TRANSIENT_MERMAID_PROBE_MARKERS = (
    "timed out",
    "content snap gpu wrapper",
    "ensure slot is connected",
)


def transient_mermaid_probe_failure(
    command: Sequence[str], result: CommandResult
) -> bool:
    """Whether a real renderer probe is safe to repeat on the same fixture.

    Keep this deliberately narrow. In particular, a generic browser launch or
    Mermaid error can be a product regression and must fail on its first
    occurrence. The accepted signatures are hosted-runner timing and Ubuntu
    snap content-mount races observed in the release matrices.
    """

    rendered = " ".join(command).casefold()
    if "prodockit-mermaid-probe" not in rendered and "mmdc" not in rendered:
        return False
    detail = f"{result.stdout}\n{result.stderr}".casefold()
    return any(marker in detail for marker in _TRANSIENT_MERMAID_PROBE_MARKERS)


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if check and result.returncode:
        raise AcceptanceError(
            f"command failed ({' '.join(command)}):\n{result.stdout}\n{result.stderr}"
        )
    return result


def git(
    arguments: Sequence[str], *, cwd: Path, environment: dict[str, str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    return run(["git", *arguments], cwd=cwd, environment=environment, check=check)


def write_project(path: Path, *, marker: str, real_toolchains: bool = False) -> None:
    (path / "docs").mkdir(parents=True)
    (path / "docs" / "index.md").write_text(f"# {marker}\n", encoding="utf-8")
    (path / "README.md").write_text(f"# {marker}\n", encoding="utf-8")
    (path / "requirements.txt").write_text("\n", encoding="utf-8")
    (path / ".gitignore").write_text(
        ".venv/\nsite/\ntools/mermaid/node_modules/\ntools/mathjax/node_modules/\n",
        encoding="utf-8",
    )
    (path / "zensical.toml").write_text(
        f'''[project]
site_name = "{marker}"
site_url = "https://example.invalid/"
repo_url = "https://example.invalid/template"
repo_name = "template/project"
edit_uri = "edit/main/docs/"

[project.theme.icon]
repo = "fontawesome/brands/github"
''',
        encoding="utf-8",
    )
    if real_toolchains:
        # The fast harness simulates npm.  Native release acceptance crosses
        # that boundary, so its template and existing-project repositories
        # need the same tracked manifests that a real template supplies.
        source = Path(__file__).resolve().parent
        for tool, names in {
            "mermaid": ("package.json", "package-lock.json"),
            "mathjax": ("package.json", "package-lock.json", "tex2svg.js"),
        }.items():
            destination = path / "tools" / tool
            destination.mkdir(parents=True)
            for name in names:
                shutil.copy2(source / tool / name, destination / name)


def initialise_worktree(
    path: Path,
    *,
    marker: str,
    environment: dict[str, str],
    real_toolchains: bool = False,
) -> str:
    path.mkdir(parents=True)
    write_project(path, marker=marker, real_toolchains=real_toolchains)
    initialised = git(
        ["init", "-b", "main"], cwd=path, environment=environment, check=False
    )
    if initialised.returncode:
        # The real-upgrade route intentionally starts with Git 2.27; ``-b``
        # is the feature Bootstrap must upgrade Git to gain.  The local test
        # fixture therefore uses the older equivalent without concealing what
        # Bootstrap itself later executes.
        git(["init"], cwd=path, environment=environment)
        git(["checkout", "-b", "main"], cwd=path, environment=environment)
    git(["add", "-A"], cwd=path, environment=environment)
    git(["commit", "-m", marker], cwd=path, environment=environment)
    return git(["rev-parse", "HEAD"], cwd=path, environment=environment).stdout.strip()


def bare_clone(source: Path, destination: Path, *, environment: dict[str, str]) -> None:
    git(
        ["clone", "--bare", str(source), str(destination)],
        cwd=source.parent,
        environment=environment,
    )


def configure_rewrite(
    remote: str, local: Path, *, root: Path, environment: dict[str, str]
) -> None:
    git(
        ["config", "--global", "--add", f"url.{local.resolve().as_uri()}.insteadOf", remote],
        cwd=root,
        environment=environment,
    )


class HarnessRunner:
    """Run repository commands for real and simulate external machine edges."""

    def __init__(
        self,
        environment: dict[str, str],
        expected_remote: str,
        *,
        home: Path,
        old_software: bool = False,
        real_software: bool = False,
        remote_rewrites: dict[str, Path] | None = None,
    ) -> None:
        self.environment = environment
        self.expected_remote = expected_remote
        self.home = home
        self.old_software = old_software
        self.real_software = real_software
        self.remote_rewrites = remote_rewrites or {}
        self.system = SubprocessRunner()
        self.calls: list[list[str]] = []
        self.upgraded: set[str] = set()
        self.versions = {
            "vscode": "1.80.2" if old_software else bootstrap_stages_module.VSCODE_MIN_VERSION,
            "git": "2.27.1" if old_software else bootstrap_stages_module.GIT_MIN_VERSION,
            "pandoc": "2.19.2" if old_software else bootstrap_stages_module.PANDOC_VERSION,
            "pango": "1.42.4" if old_software else bootstrap_stages_module.PANGO_MIN_VERSION,
            "node": "18.20.0" if old_software else bootstrap_stages_module.NODE_MIN_VERSION,
            "npm": "6.14.18" if old_software else "10.9.2",
            "chromium": (
                "100.0.4896.60"
                if old_software
                else bootstrap_stages_module.CHROMIUM_MIN_VERSION
            ),
        }
        self.extensions = {
            name: ("0.1.0" if old_software else minimum)
            for name, minimum in bootstrap_stages_module.VSCODE_EXTENSION_MIN_VERSIONS.items()
        }
        self.chromium = True
        self.old_tool_bins = {
            name: Path(path)
            for name, path in json.loads(
                environment.get("PDKBOOT_ACCEPTANCE_OLD_TOOL_BINS", "{}")
            ).items()
        }

    def _reveal_installed_tools(self, *names: str) -> None:
        """Remove only upgraded portable fixtures from the controlled PATH."""
        hidden = {
            os.path.normcase(str(self.old_tool_bins[name]))
            for name in names
            if name in self.old_tool_bins
        }
        if not hidden:
            return
        parts = [
            part
            for part in self.environment.get("PATH", "").split(os.pathsep)
            if os.path.normcase(part) not in hidden
        ]
        value = os.pathsep.join(parts)
        self.environment["PATH"] = value
        os.environ["PATH"] = value

    def _record_real_machine_install(self, words: Sequence[str]) -> None:
        """Expose a new executable only after its real installer succeeds."""
        executable = Path(words[0]).name.lower()
        script = " ".join(words)
        upgraded: set[str] = set()
        if executable in {"winget", "winget.exe"} and "--id" in words:
            package = words[words.index("--id") + 1]
            selected = {
                "Microsoft.VisualStudioCode": "vscode",
                "Git.Git": "git",
                "JohnMacFarlane.Pandoc": "pandoc",
                "OpenJS.NodeJS.LTS": "node",
            }.get(package)
            if selected:
                upgraded.add(selected)
        elif executable == "sudo" and "apt" in words:
            if "/tmp/code.deb" in words:
                upgraded.add("vscode")
            if "git" in words:
                upgraded.add("git")
            if "/tmp/pandoc.deb" in words:
                upgraded.add("pandoc")
            if "nodejs" in words:
                upgraded.add("node")
        elif executable in {"brew", "bash"} and "brew" in script:
            if "visual-studio-code" in script:
                upgraded.add("vscode")
            for name in ("git", "pandoc", "node"):
                pattern = (
                    rf"(?:--formula\s+|\b(?:install|upgrade)\s+"
                    rf"(?:--force\s+)?){name}\b"
                )
                if re.search(pattern, script):
                    upgraded.add(name)
        self._reveal_installed_tools(*upgraded)

    def _run_real_machine_command(
        self,
        words: list[str],
        *,
        cwd: str | None,
        timeout: float | None,
        capture: bool,
    ) -> CommandResult:
        """Run a real command, retrying only known transient renderer probes."""

        result = self.system.run(words, cwd=cwd, timeout=timeout, capture=capture)
        for attempt, delay in enumerate((5, 15), start=1):
            if not transient_mermaid_probe_failure(words, result):
                break
            print(
                "Transient Mermaid browser probe failure "
                f"on attempt {attempt}/3; retrying in {delay}s.",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
            self.calls.append(list(words))
            result = self.system.run(words, cwd=cwd, timeout=timeout, capture=capture)
        if result.returncode == 0:
            self._record_real_machine_install(words)
        return result

    def _upgrade(self, *names: str) -> None:
        targets = {
            "vscode": bootstrap_stages_module.VSCODE_MIN_VERSION,
            "git": bootstrap_stages_module.GIT_MIN_VERSION,
            "pandoc": bootstrap_stages_module.PANDOC_VERSION,
            "pango": bootstrap_stages_module.PANGO_MIN_VERSION,
            "node": bootstrap_stages_module.NODE_MIN_VERSION,
            "npm": "10.9.2",
            "chromium": bootstrap_stages_module.CHROMIUM_MIN_VERSION,
        }
        for name in names:
            self.versions[name] = targets[name]
            self.upgraded.add(name)
        if "node" in names:
            self.versions["npm"] = "10.9.2"
            self.upgraded.add("npm")

    def _install_toolchain(self, prefix: Path) -> None:
        if prefix.name == "mermaid":
            binary = prefix / "node_modules" / ".bin"
            binary.mkdir(parents=True, exist_ok=True)
            (binary / ("mmdc.cmd" if os.name == "nt" else "mmdc")).write_text(
                "acceptance", encoding="utf-8"
            )
        if prefix.name == "mathjax":
            # ``SOURCE`` is rooted at the project (``tools/mathjax/...``),
            # while npm's ``--prefix`` names ``tools/mathjax`` itself.
            bundle = prefix.joinpath(
                "node_modules",
                "mathjax-full",
                "es5",
                bootstrap_stages_module.mathjax.BUNDLE,
            )
            bundle.parent.mkdir(parents=True, exist_ok=True)
            bundle.write_text("acceptance", encoding="utf-8")

    def run(
        self,
        command: Sequence[str],
        cwd: str | None = None,
        timeout: float | None = None,
        capture: bool = True,
    ) -> CommandResult:
        words = list(command)
        self.calls.append(words)
        executable = Path(words[0]).name.lower()
        working = Path(cwd) if cwd else Path.cwd()

        # Native release acceptance keeps the Git-host and repository edges
        # local, but deliberately crosses the machine boundary.  These are
        # actual programs and package managers on a disposable runner, not
        # the version-bearing test doubles used by ``--old-software``.
        real_machine_commands = {
            "bash",
            "brew",
            "code",
            "code.cmd",
            "curl",
            "dpkg",
            "dpkg-query",
            "fc-list",
            "node",
            "node.exe",
            "npm",
            "npm.cmd",
            "pandoc",
            "pandoc.exe",
            "pango-view",
            "pango-view.exe",
            "mmdc",
            "mmdc.cmd",
            "sudo",
            "winget",
            "winget.exe",
        }

        if self.old_software and executable in {"code", "code.cmd"}:
            if "--version" in words:
                return CommandResult(0, f"{self.versions['vscode']}\nacceptance\n")
            if "--list-extensions" in words:
                shown = [
                    f"{name}@{version}" if "--show-versions" in words else name
                    for name, version in self.extensions.items()
                ]
                return CommandResult(0, "\n".join(shown) + "\n")
            if "--install-extension" in words:
                name = words[words.index("--install-extension") + 1]
                minimum = bootstrap_stages_module.VSCODE_EXTENSION_MIN_VERSIONS[name]
                self.extensions[name] = minimum
                self.upgraded.add("vscode-extensions")
                return CommandResult(0, f"Updated {name}\n")

        if self.old_software and executable in {"pandoc", "pandoc.exe"}:
            return CommandResult(0, f"pandoc {self.versions['pandoc']}\n")
        if self.old_software and executable in {"pango-view", "pango-view.exe"}:
            return CommandResult(0, f"pango-view (pango) {self.versions['pango']}\n")
        if self.old_software and executable in {"node", "node.exe"}:
            return CommandResult(0, f"v{self.versions['node']}\n")
        if self.old_software and executable in {"mmdc", "mmdc.cmd"}:
            if "-o" in words:
                output = Path(words[words.index("-o") + 1])
                output.write_text("<svg></svg>\n", encoding="utf-8")
            return CommandResult(0, "11.12.0\n" if "--version" in words else "")
        if self.old_software and executable in {"npm", "npm.cmd"} and "--version" in words:
            return CommandResult(0, f"{self.versions['npm']}\n")
        if self.old_software and executable == "fc-list":
            return CommandResult(0, "Inter\nJetBrains Mono\n")
        if self.old_software and executable == "dpkg" and "--print-architecture" in words:
            architecture = (
                "arm64\n"
                if platform.machine().lower() in {"arm64", "aarch64"}
                else "amd64\n"
            )
            return CommandResult(0, architecture)
        if self.old_software and executable == "dpkg-query":
            return CommandResult(0, f"{self.versions['pango']}\n")

        if self.old_software and executable == "brew":
            if "visual-studio-code" in words:
                self._upgrade("vscode")
            if "git" in words:
                self._upgrade("git")
            selected = [name for name in ("pandoc", "pango") if name in words]
            if selected:
                self._upgrade(*selected)
            if "node" in words:
                self._upgrade("node")
            return CommandResult(0)

        if self.old_software and executable == "winget":
            package = words[words.index("--id") + 1] if "--id" in words else ""
            mapping = {
                "Microsoft.VisualStudioCode": ("vscode",),
                "Git.Git": ("git",),
                "JohnMacFarlane.Pandoc": ("pandoc",),
                "OpenJS.NodeJS.LTS": ("node",),
                "MSYS2.MSYS2": (),
            }
            if package in mapping:
                self._upgrade(*mapping[package])
                return CommandResult(0)

        if self.old_software and executable == "sudo":
            if "apt" in words:
                if "/tmp/code.deb" in words:
                    self._upgrade("vscode")
                if "git" in words:
                    self._upgrade("git")
                if "/tmp/pandoc.deb" in words:
                    self._upgrade("pandoc")
                if any(word.startswith("libpango") for word in words):
                    self._upgrade("pango")
                if "nodejs" in words:
                    self._upgrade("node")
                if "chromium-browser" in words:
                    self.chromium = True
                    self._upgrade("chromium")
                return CommandResult(0)
            if "debconf-set-selections" in words:
                return CommandResult(0)
            if "bash" in words and "/tmp/nodesource-setup.sh" in words:
                return CommandResult(0)
            if any(Path(word).name in {"npm", "npm.cmd"} for word in words):
                self._upgrade("npm")
                return CommandResult(0)

        if self.old_software and executable == "curl":
            return CommandResult(0)

        if self.old_software and executable in {"npm", "npm.cmd"} and "ci" in words:
            self._install_toolchain(Path(words[words.index("--prefix") + 1]))
            return CommandResult(0)

        if self.old_software and executable == "bash":
            script = " ".join(words)
            if "brew list" in script:
                if "visual-studio-code" in script:
                    self._upgrade("vscode")
                if re.search(
                    r"\b(?:brew (?:upgrade|install)(?: --force)?|--formula) git\b",
                    script,
                ):
                    self._upgrade("git")
                selected = [name for name in ("pandoc", "pango") if name in script]
                if selected:
                    self._upgrade(*selected)
                if re.search(
                    r"\b(?:brew (?:upgrade|install)(?: --force)?|--formula) node\b",
                    script,
                ):
                    self._upgrade("node")
                return CommandResult(0)
            if "chromium-browser" in script and "--version" in script:
                return CommandResult(0, f"Chromium {self.versions['chromium']}\n")
            if "npm ci" in script and "cd " in script:
                match = re.search(r"\bcd\s+([^;&]+?)\s+&&\s+npm ci", script)
                if match:
                    self._install_toolchain(Path(match.group(1).strip(" '\"")))
                return CommandResult(0)
            if "which chromium-browser" in script:
                return CommandResult(0, "/usr/bin/chromium-browser\n")
            return CommandResult(0)

        if executable in {"ssh", "ssh.exe"}:
            host = words[-1]
            if "github.com" in host:
                return CommandResult(
                    1,
                    stderr=(
                        "Hi acceptance-user! You've successfully authenticated, "
                        "but GitHub does not provide shell access."
                    ),
                )
            return CommandResult(0, "Welcome to GitLab, @mb0105!\n")

        if executable == "mv":
            shutil.move(words[1], words[2])
            return CommandResult(0)
        if executable in {"powershell", "powershell.exe"} and "Move-Item" in words[-1]:
            paths = re.findall(r"'(.*?)'", words[-1])
            if len(paths) != 2:
                return CommandResult(1, stderr="could not read Move-Item paths")
            shutil.move(paths[0].replace("''", "'"), paths[1].replace("''", "'"))
            return CommandResult(0)
        if self.real_software and executable in {"powershell", "powershell.exe", "pwsh"}:
            return self._run_real_machine_command(
                words, cwd=cwd, timeout=timeout, capture=capture
            )
        if self.old_software and executable in {"powershell", "powershell.exe"}:
            if "pacman -S" in words[-1]:
                self._upgrade("pango")
            if "npm.cmd ci" in words[-1] and "Set-Location -LiteralPath" in words[-1]:
                match = re.search(r"Set-Location -LiteralPath '((?:''|[^'])+)'", words[-1])
                if match:
                    self._install_toolchain(Path(match.group(1).replace("''", "'")))
            return CommandResult(0)

        if executable.startswith("zensical"):
            return CommandResult(0, "Build completed\n")

        if len(words) >= 4 and words[1:4] == ["-m", "prodockit", "sync-repo"]:
            before = Path.cwd()
            visibility = sync_repo_module.repository_is_public
            remote_url = sync_repo_module.get_remote_url
            try:
                os.chdir(working)
                vars(sync_repo_module)["repository_is_public"] = lambda _url: False
                # Git's ``insteadOf`` rewrite deliberately sends network
                # operations to the local bare repository.  It also makes
                # ``git remote get-url`` print that local file URL, whereas
                # sync-repo must see the realistic configured host URL.
                vars(sync_repo_module)["get_remote_url"] = (
                    lambda _remote="origin", *, cwd=None: self.expected_remote
                )
                checking = "--check" in words
                synced = sync_repo_module.sync_repo_metadata(check=checking)
            except Exception as error:  # pragma: no cover - diagnostic boundary
                return CommandResult(1, stderr=str(error))
            finally:
                vars(sync_repo_module)["repository_is_public"] = visibility
                vars(sync_repo_module)["get_remote_url"] = remote_url
                os.chdir(before)
            return CommandResult(
                1 if checking and synced.changed else 0,
                "\n".join(synced.changes),
            )

        if (
            len(words) == 6
            and words[1:4] == ["-m", "prodockit", "_record-template-release"]
            and words[4] == "--project-root"
        ):
            # This is an installed-wheel acceptance test, so exercise the
            # wheel's real hidden command. It is local and deterministic: it
            # reads the freshly cloned repository's tag and writes the
            # template stamp before Bootstrap archives that Git history.
            completed = run(
                words,
                cwd=working,
                environment=self.environment,
                check=False,
            )
            return CommandResult(
                completed.returncode,
                completed.stdout,
                completed.stderr,
            )

        if executable in {"git", "git.exe"} or executable.endswith("git.exe"):
            if self.old_software and words[1:] == ["--version"]:
                return CommandResult(0, f"git version {self.versions['git']}\n")
            if words[-3:] == ["remote", "get-url", "origin"]:
                completed = run(
                    ["git", *words[1:-3], "config", "--get", "remote.origin.url"],
                    cwd=working,
                    environment=self.environment,
                    check=False,
                )
                return CommandResult(
                    completed.returncode, completed.stdout, completed.stderr
                )
            clone_remote = (
                next(
                    (
                        word
                        for word in words[2:-1]
                        if word.startswith(("git@", "https://", "ssh://"))
                    ),
                    None,
                )
                if words[1:2] == ["clone"]
                else None
            )
            clone_destination = Path(words[-1]) if clone_remote else None
            words[0] = "git"
            # Keep every host boundary local even when Bootstrap has just
            # replaced Git itself.  Relying only on a global ``insteadOf``
            # setting made the rewrite disappear when a native upgrade
            # switched from the portable old Git to the package-manager Git.
            # Command-scoped configuration travels with the invocation and
            # cannot be lost during that transition.
            for remote, local in self.remote_rewrites.items():
                words[1:1] = [
                    "-c",
                    f"url.{local.resolve().as_uri()}.insteadOf={remote}",
                ]
            completed = run(words, cwd=working, environment=self.environment, check=False)
            if completed.returncode == 0 and clone_remote and clone_destination:
                run(
                    ["git", "remote", "set-url", "origin", clone_remote],
                    cwd=clone_destination,
                    environment=self.environment,
                )
            return CommandResult(completed.returncode, completed.stdout, completed.stderr)

        if self.real_software and executable in real_machine_commands:
            return self._run_real_machine_command(
                words, cwd=cwd, timeout=timeout, capture=capture
            )

        if (
            self.real_software
            and executable == Path(sys.executable).name.lower()
            and "-c" in words
        ):
            return self.system.run(words, cwd=cwd, timeout=timeout, capture=capture)

        if self.old_software and executable == Path(sys.executable).name.lower() and "-c" in words:
            script = words[words.index("-c") + 1]
            if "int.from_bytes" in script:
                machine = (
                    "0xaa64"
                    if platform.machine().lower() in {"arm64", "aarch64"}
                    else "0x8664"
                )
                return CommandResult(0, machine + "\n")
            return CommandResult(0)

        return CommandResult(127, stderr=f"unexpected acceptance command: {' '.join(words)}")


def _simulated_stage(stage: Stage) -> Stage:
    def satisfied(_context) -> CheckResult:  # type: ignore[no-untyped-def]
        return CheckResult(Status.OK, "provided by the acceptance runner")

    return Stage(stage.id, stage.summary, satisfied, stage.plan)


def acceptance_stages(
    *, old_software: bool = False, real_software: bool = False
) -> tuple[Stage, ...]:
    """Keep repository stages real and replace only external machine edges."""
    real = {
        "own-project",
        "pages",
        "clone-source",
        "clone",
        "fresh-history",
        "remote",
        "identity",
        "first-push",
        "site",
    }
    if old_software or real_software:
        real.update({"vscode", "git", "pandoc", "node", "extensions"})
    return tuple(stage if stage.id in real else _simulated_stage(stage) for stage in STAGES)


def supports_old_software_route(host: str, route: str) -> bool:
    """Whether a declared route is expected to exercise prerequisite upgrades."""
    return (host, route) in {
        ("surrey", "existing"),
        ("github", "new"),
    }


def machine_home(
    environment: dict[str, str], *, real_software: bool, platform_name: str
) -> Path:
    """Return the home directory where native applications are installed.

    Repository state remains below the acceptance scenario's isolated
    ``HOME``.  A real Windows software run must nevertheless inspect the
    runner's genuine per-user application directory: WinGet installs VS Code
    below ``USERPROFILE``, and hiding that directory turns an installed old
    version into a false "not installed" result.
    """
    if (
        real_software
        and platform_name == "windows"
        and (userprofile := environment.get("USERPROFILE"))
    ):
        return Path(userprofile)
    return Path(environment["HOME"])


def fetch(_url: str, timeout: float = 20.0) -> Fetched:
    del timeout
    if "api.github.com" in _url:
        return Fetched(200, '{"has_pages": true}')
    return Fetched(200, "published")


@contextmanager
def in_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def configure(
    *, root: Path, host_key: str, existing: bool, config_path: Path
) -> tuple[BootstrapConfig, str]:
    vars(cli)["connection_problem"] = lambda _value: None
    vars(cli)["_is_interactive"] = lambda: True
    vars(cli)["project_on_host"] = lambda _context: existing
    vars(cli)["own_project_exists"] = lambda _context: existing
    vars(cli)["own_project_has_content"] = lambda _context: existing
    if host_key == "surrey":
        answers = "1\nAcceptance Author\nmb0105\ny\ncommtest\n1\n2026\n"
    else:
        project = root / "report-acceptance"
        answers = (
            "2\nAcceptance Author\nauthor@example.com\nacceptance-user\n"
            f"acceptance-user\nreport-acceptance\n{project}\n"
        )
    result = CliRunner().invoke(
        cli.main,
        ["bootstrap", "--config", str(config_path), "--configure"],
        input=answers,
    )
    if result.exit_code:
        raise AcceptanceError(f"configure failed:\n{result.output}\n{result.exception}")
    return load(config_path), result.output


def invoke(
    arguments: list[str],
    *,
    config_path: Path,
    input_text: str = "",
    expected_exit_codes: frozenset[int] = frozenset({0}),
) -> str:
    result = CliRunner().invoke(
        cli.main,
        ["bootstrap", "--config", str(config_path), *arguments],
        input=input_text,
    )
    if result.exit_code not in expected_exit_codes:
        raise AcceptanceError(
            f"bootstrap {' '.join(arguments)} failed ({result.exit_code}):\n"
            f"{result.output}\n{result.exception}"
        )
    return result.output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--host", choices=("surrey", "github"), required=True)
    parser.add_argument("--route", choices=("new", "existing"), required=True)
    parser.add_argument("--old-software", action="store_true")
    parser.add_argument("--real-software", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if args.old_software and args.real_software:
        raise AcceptanceError("choose simulated or real old software, not both")
    if (args.old_software or args.real_software) and not supports_old_software_route(
        args.host, args.route
    ):
        raise AcceptanceError(
            "old-software acceptance is limited to Surrey's existing-repository "
            "route and GitHub's new-repository route"
        )

    started = time.perf_counter()
    root = args.root.resolve()
    # The native-upgrade parent creates ``root/home`` first so it can seed
    # real old editor extensions.  Reusing that deliberately prepared root
    # must not make the child acceptance route fail before Bootstrap starts.
    root.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    real_userprofile = environment.get("USERPROFILE")
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "HOME": str(root / "home"),
            "GIT_CONFIG_GLOBAL": str(root / "gitconfig"),
            "GIT_TERMINAL_PROMPT": "0",
            "PYTHONUTF8": "1",
        }
    )
    if args.real_software and current_platform() == "windows" and real_userprofile:
        environment["USERPROFILE"] = real_userprofile
    else:
        environment["USERPROFILE"] = str(root / "home")
    Path(environment["HOME"]).mkdir(exist_ok=True)
    if args.old_software and current_platform() == "windows":
        fonts = (
            Path(environment["HOME"])
            / "AppData"
            / "Local"
            / "Microsoft"
            / "Windows"
            / "Fonts"
        )
        fonts.mkdir(parents=True)
        for name in ("Inter-Regular.ttf", "JetBrainsMono-Regular.ttf"):
            (fonts / name).write_text("old acceptance font", encoding="utf-8")
    os.environ.update(environment)
    git(["config", "--global", "user.name", "Acceptance Author"], cwd=root, environment=environment)
    git(
        ["config", "--global", "user.email", "author@example.com"],
        cwd=root,
        environment=environment,
    )
    git(["config", "--global", "protocol.file.allow", "always"], cwd=root, environment=environment)

    existing = args.route == "existing"
    config_path = root / ".pdkboot.toml"
    with in_directory(root):
        config, configure_output = configure(
            root=root, host_key=args.host, existing=existing, config_path=config_path
        )
    host = resolve_host(config.host)
    if host is None:
        raise AcceptanceError(f"configure produced an unsupported host: {config.host}")
    project = Path(config.project_dir)
    expected_remote = host.remote_url(config.namespace, config.project_name)

    template_work = root / "template-work"
    template_bare = root / "template.git"
    initialise_worktree(
        template_work,
        marker="Template",
        environment=environment,
        real_toolchains=args.real_software,
    )
    git(["tag", TEMPLATE_RELEASE], cwd=template_work, environment=environment)
    bare_clone(template_work, template_bare, environment=environment)
    configure_rewrite(
        host.template_remote, template_bare, root=root, environment=environment
    )

    target_bare = root / "target.git"
    initial_head = ""
    if existing:
        target_work = root / "target-work"
        initialise_worktree(
            target_work,
            marker="Existing project",
            environment=environment,
            real_toolchains=args.real_software,
        )
        git(
            ["remote", "add", "origin", expected_remote],
            cwd=target_work,
            environment=environment,
        )
        visibility = sync_repo_module.repository_is_public
        remote_url = sync_repo_module.get_remote_url
        try:
            vars(sync_repo_module)["repository_is_public"] = lambda _url: False
            vars(sync_repo_module)["get_remote_url"] = (
                lambda _remote="origin", *, cwd=None: expected_remote
            )
            with in_directory(target_work):
                sync_repo_module.sync_repo_metadata()
        finally:
            vars(sync_repo_module)["repository_is_public"] = visibility
            vars(sync_repo_module)["get_remote_url"] = remote_url
        git(["add", "-A"], cwd=target_work, environment=environment)
        git(["commit", "--amend", "--no-edit"], cwd=target_work, environment=environment)
        initial_head = git(
            ["rev-parse", "HEAD"], cwd=target_work, environment=environment
        ).stdout.strip()
        bare_clone(target_work, target_bare, environment=environment)
    configure_rewrite(expected_remote, target_bare, root=root, environment=environment)

    harness = HarnessRunner(
        environment,
        expected_remote,
        home=machine_home(
            environment,
            real_software=args.real_software,
            platform_name=current_platform(),
        ),
        old_software=args.old_software,
        real_software=args.real_software,
        remote_rewrites={
            host.template_remote: template_bare,
            expected_remote: target_bare,
        },
    )
    vars(bootstrap_stages_module)["_check_ssh_authenticates"] = lambda _context: (
        CheckResult(Status.OK, "provided by the acceptance runner")
    )
    vars(cli)["STAGES"] = acceptance_stages(
        old_software=args.old_software,
        real_software=args.real_software,
    )
    vars(cli)["build_bootstrap_context"] = (
        lambda candidate, *, guided=False: build_context(
            candidate,
            runner=harness,
            platform=current_platform(),
            home=machine_home(
                environment,
                real_software=args.real_software,
                platform_name=current_platform(),
            ),
            exists=Path.exists,
            fetch=fetch,
            guided=guided,
        )
    )

    original_confirm = click.confirm
    original_prompt = click.prompt

    def confirm(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return True

    def prompt(text, *args, **kwargs):  # type: ignore[no-untyped-def]
        question = str(text)
        if "Have you created" in question:
            if not target_bare.exists():
                git(
                    ["init", "--bare", "--initial-branch=main", str(target_bare)],
                    cwd=root,
                    environment=environment,
                )
            return "yes"
        if "Has your first build published" in question:
            return "yes"
        return original_prompt(text, *args, **kwargs)

    click.confirm = confirm
    click.prompt = prompt
    try:
        with in_directory(root):
            # A dry run returns one while work remains, just as ``--check`` does.
            # Its output, rather than a zero exit status, is the contract here.
            dry_output = invoke(
                ["--dry-run"],
                config_path=config_path,
                expected_exit_codes=frozenset({0, 1}),
            )
            if project.exists():
                raise AcceptanceError("the dry run created the local project")
            apply_output = invoke(["--apply"], config_path=config_path)
            check_output = invoke(["--check"], config_path=config_path)
    finally:
        click.confirm = original_confirm
        click.prompt = original_prompt

    if "All 23 stages are set up" not in check_output:
        raise AcceptanceError(f"second check was not complete:\n{check_output}")
    if args.old_software:
        expected_upgrades = {
            "vscode",
            "git",
            "pandoc",
            "pango",
            "node",
            "npm",
            "vscode-extensions",
        }
        if current_platform() == "ubuntu":
            expected_upgrades.add("chromium")
        if harness.upgraded != expected_upgrades:
            raise AcceptanceError(
                "the old-software route did not accept every upgrade; "
                f"got {sorted(harness.upgraded)}, expected {sorted(expected_upgrades)}"
            )
        if apply_output.count("Action:   UPGRADE") < 5:
            raise AcceptanceError(
                "the old-software route did not present each software upgrade explicitly"
            )
    if args.real_software:
        expected = {
            "Visual Studio Code",
            "Git, installed and configured",
            "Pandoc, and the libraries WeasyPrint needs",
            "Node.js and the render toolchains",
            "VS Code extensions",
        }
        upgraded = {
            summary
            for summary in expected
            if f"{summary}\n  Action:   UPGRADE" in apply_output
        }
        if upgraded != expected:
            raise AcceptanceError(
                "the real back-level route did not present every upgrade; "
                f"got {sorted(upgraded)}, expected {sorted(expected)}\n{apply_output}"
            )
    if not project.is_dir() or not (project / ".git").is_dir():
        raise AcceptanceError("bootstrap did not create a complete local clone")
    if git(["status", "--porcelain"], cwd=project, environment=environment).stdout:
        raise AcceptanceError("bootstrap left uncommitted work")
    origin = git(
        ["config", "--get", "remote.origin.url"],
        cwd=project,
        environment=environment,
    ).stdout.strip()
    if origin != expected_remote:
        raise AcceptanceError(f"origin is {origin!r}, expected {expected_remote!r}")
    final_head = git(["rev-parse", "HEAD"], cwd=project, environment=environment).stdout.strip()
    remote_head = git(
        ["--git-dir", str(target_bare), "rev-parse", "HEAD"],
        cwd=root,
        environment=environment,
    ).stdout.strip()
    if final_head != remote_head:
        raise AcceptanceError("the local and remote HEADs differ")

    # A completed run must be genuinely resumable and idempotent.  Run the
    # public command again without supplying answers: any stage that still
    # needs confirmation will fail, and any unnoticed repository mutation is
    # caught by the HEAD and clean-tree checks below.
    with in_directory(root):
        invoke(["--apply"], config_path=config_path)
    rerun_head = git(
        ["rev-parse", "HEAD"], cwd=project, environment=environment
    ).stdout.strip()
    if rerun_head != final_head:
        raise AcceptanceError("a second apply changed the repository HEAD")
    if git(["status", "--porcelain"], cwd=project, environment=environment).stdout:
        raise AcceptanceError("a second apply left uncommitted work")

    backups = list(root.glob(f".{project.name}.git.pdk-template-backup*"))
    if existing:
        if final_head != initial_head:
            raise AcceptanceError("option 1 changed the existing repository HEAD")
        if backups:
            raise AcceptanceError("option 1 archived history that it should preserve")
        if "Option 1 selected automatically" not in (
            configure_output + dry_output + apply_output
        ):
            raise AcceptanceError("the existing route did not explain automatic option 1")
        if "Select 1, 2 or 3" in configure_output + apply_output:
            raise AcceptanceError("the existing route unexpectedly asked for a source choice")
    elif not backups:
        raise AcceptanceError("the new route did not preserve the template history backup")

    if not existing:
        stamp = read_template_stamp(project)
        if stamp is None or stamp.applied_release != TEMPLATE_RELEASE:
            raise AcceptanceError(
                "bootstrap did not preserve the successfully applied template release; "
                f"got {stamp!r}, expected {TEMPLATE_RELEASE!r}"
            )

    recovery = root / ".pdkboot.last-run.json"
    if not recovery.is_file():
        raise AcceptanceError("bootstrap did not write its recovery report")
    installed = Path(prodockit.__file__).resolve()
    if "site-packages" not in installed.as_posix():
        raise AcceptanceError(f"candidate was not imported from the installed wheel: {installed}")

    report = {
        "passed": True,
        "host": args.host,
        "route": args.route,
        "old_software": args.old_software,
        "real_software": args.real_software,
        "machine": platform.machine(),
        "platform": current_platform(),
        "python": platform.python_version(),
        "prodockit": getattr(prodockit, "__version__", "unknown"),
        "installed_from": str(installed),
        "remote": expected_remote,
        "head": final_head,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "commands": len(harness.calls),
        "dry_run_left_project_absent": True,
        "rerun_succeeded": True,
        "upgrades_accepted": sorted(harness.upgraded),
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except AcceptanceError as error:
        print(f"acceptance failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
