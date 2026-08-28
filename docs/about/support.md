---
icon: lucide/badge-check
---

{{ heading_counter_reset(page) }}

# Support and compatibility

This page is for anyone deciding whether prodockit fits a project or checking
whether their platform and tool versions are covered. It describes the public
support and \index{compatibility} boundary; implementation-specific constraints remain in
[Contributor internals](../devcons/devcons.md).

## Maturity and stability

prodockit is currently classified as **Alpha** and uses pre-1.0 versions. Its
document features and publishing tools are functional and tested, but there is
not yet a formal, versioned public API stability contract. A pre-1.0 upgrade
can therefore include a breaking change when the change is needed to make the
public configuration consistent. Such changes are identified in the
[release notes](changelog.md).

The future stability contract is tracked in
[issue #7](https://github.com/buckwem/prodockit-extensions/issues/7).

## Required versions

Installing prodockit installs these Python dependencies automatically:

The current test matrix covers Python 3.10, 3.11, 3.12, 3.13, and Python 3.14. The
documentation build currently pins Zensical 0.0.57 and pymdown-extensions
11.0.2 so changes to either renderer arrive as reviewed version changes rather
than silently altering published output.

\ref{tab-about-support-required-versions} gives the supported dependency ranges and explains why each boundary matters.

| Requirement {: width="30%" } | Supported or tested range | Why it matters |
|---|---|---|
| Python | 3.10–3.14 tested | The package requires Python 3.10 or later |
| Zensical | 0.0.57 or later | Site configuration, rendering, navigation, macros, and icons |
| Python-Markdown | 3.10.3 or later | The extension engine used by every authoring feature |
| pymdown-extensions | 11.0.2 or later | PyMdown Blocks is the direct foundation for `prodockit.steps` and `prodockit.tree`; the PDF pipeline also preserves PyMdown output |
/// table-caption | <
    attrs: {id: tab-about-support-required-versions}

Required versions
///

The dependency boundaries in \ref{tab-about-support-required-versions} are
tested rather than inferred. PyMdown Blocks is particularly important when
evaluating the authoring model.
The numbered-steps and directory-tree extensions are specialised Blocks API
implementations, so their slash fences, nesting rules, and option layout follow
[PyMdown's block syntax](https://facelessuser.github.io/pymdown-extensions/extensions/blocks/).
They are not separate parsers that only resemble it.

Pandoc, WeasyPrint, Node tools, fonts, and other optional publishing
requirements depend on the output being built. See
[Installation](../installation.md#installation-external) for that complete
tool-by-tool boundary.

## Platforms and test depth

The \index{platform testing} described here covers Linux, macOS, and Windows.
Bootstrap has now completed
manual end-to-end testing on Ubuntu Linux, Windows, and macOS against both the
University of Surrey's GitLab (`gitlab.surrey.ac.uk`) and GitHub.com.

Two complete document workflows were exercised:

1. **Start a new document:** prepare the machine with bootstrap, create a new
   document repository on the selected host, and reach a working local build.
2. **Adopt an existing document:** take an existing online repository, install
   it locally on the prepared machine, and reach a working local build.

This is practical integration testing across the three operating systems, two
hosts, and both common starting points. It verifies that the stages work
together in real environments, beyond unit tests or inspection of generated
commands. It is not an automated cross-platform full-suite regression matrix,
however:

\ref{tab-about-support-platforms-and-test-depth} distinguishes routine platform coverage from the deeper tests run for platform-specific installers.

| Platform | Regression test coverage | Manual bootstrap coverage |
|---|---|---|
| Ubuntu Linux | Full test suite on every push and pull request using `ubuntu-24.04`; installed-wheel adoption on x64 and ARM64 | Both repository workflows on Surrey GitLab and GitHub.com |
| macOS | The full test suite is also run locally; installed-wheel adoption runs on hosted ARM64 | Both repository workflows on Surrey GitLab and GitHub.com |
| Windows | Installed-wheel adoption on Windows 2025 x64 and Windows 11 ARM64; no hosted full-suite job | Both repository workflows on Surrey GitLab and GitHub.com |
/// table-caption | <
    attrs: {id: tab-about-support-platforms-and-test-depth}

Platforms and test depth
///

\ref{tab-about-support-platforms-and-test-depth} distinguishes automated
regression coverage from manual bootstrap exercises. The installed-wheel
adoption jobs build the candidate package afresh and test
TOML and YAML projects with the core, Mermaid-only, maths-only and combined
component choices. They also check that a second apply changes no files. This
narrow cross-platform matrix complements rather than replaces the full Python
test suite.

The manual matrix gives confidence in installation and first-use integration,
but it is a point-in-time result. The locally run macOS suite adds full
regression coverage on that platform, although it is not enforced by a hosted
pull-request gate. Windows can still regress outside the adoption workflow
because it does not yet run the full suite for every change.

Windows requires native libraries for PDF generation that `pip` cannot
install. It also uses different default text encodings. The known setup steps
are documented under [PDF requirements](../pdf.md#pdf-requirements), and
`prodockit bootstrap` checks the corresponding tools. Report a Windows-only
failure rather than assuming it is local configuration; it may expose a real
coverage gap.

Bootstrap also recognises GitLab.com, but the completed manual platform matrix
described above covers Surrey GitLab and GitHub.com. See
[Set up a machine](../devcons/bootstrap.md#bootstrap-hosts) for the host
boundary.

## Supported surfaces

\ref{tab-about-support-supported-surfaces} defines which interfaces carry a
compatibility promise and which remain internal.

| Surface {: width="38%" } | Current support |
|---|---|
| Markdown extensions | All nine registered extensions are documented and tested |
| PyMdown Blocks integration | `prodockit.steps` and `prodockit.tree` directly use the Blocks API |
| Zensical website macros | Implemented and tested; tied to some pre-1.0 Zensical internals |
| PDF and source bundles | Implemented and tested with Pandoc and WeasyPrint; external renderer versions can affect layout |
| GitHub and GitLab publishing | Maintained through the annotated workflows in prodockit-template |
| Repository and template commands | Implemented and tested; commands that write files provide a report or dry-run path first |
/// table-caption | <
    attrs: {id: tab-about-support-supported-surfaces}

Supported surfaces
///

For observable constraints such as live-reload staleness, unsupported citation
forms, and differences between browser and PDF rendering, see
[Known limitations](limitations.md). If the behaviour is
not listed there, search or open a
[GitHub issue](https://github.com/buckwem/prodockit-extensions/issues).

## Upgrade safely

Read the [release notes](changelog.md) before changing a pinned version. Build
the site with `zensical build --clean --strict`, build the PDF if the project
publishes one, and run its built-output checks before merging. Template-based
projects should also review changes reported by
[template-sync](../devcons/template-sync.md).
