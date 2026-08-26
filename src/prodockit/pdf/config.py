# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Drives a full PDF build entirely from `zensical.toml`, for a project
that doesn't want to write any Python at all - see `prodockit.pdf.cli` for the
command-line tool built on top of this.

`build_pdf_from_built_site()` powers the public command: it reads the project
settings, invokes Zensical's documented build command, then assembles the PDF
from the completed site. `build_pdf_from_zensical_config()` retains the old
Zensical Python rendering path for the hidden legacy command. Both call
`prodockit.pdf.build.build_pdf()` with icon, Mermaid and MathJax detection
wired up.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
from pathlib import Path

from prodockit._zensical import _installed_zensical_version
from prodockit.pdf.build import Page, StageReporter, build_pdf
from prodockit.pdf.icons import (
    build_icon_registry,
    build_site_icon_registry,
    discover_icon_dirs,
    discover_legacy_icon_dirs,
)
from prodockit.pdf.mermaid import render_mermaid_diagram
from prodockit.pdf.release import get_latest_release_tag
from prodockit.pdf.site import build_site, page_html, page_metadata
from prodockit.pdf.source_bundle import build_source_bundle, discover_markdown_and_config_files
from prodockit.project_config import load_project_config
from prodockit.settings import flatten_nav, heading_numbering_enabled, reference_style_values
from prodockit.zensical_macros import (
    _compute_site_word_count,
    _get_release,
    _get_repo_url,
)

# Front matter flag marking a page for letter-based numbering ("A", "A.1",
# ...) - same default name as prodockit.headings' own `appendix_attr` option,
# so a project already using continuous numbering doesn't need a second,
# differently-named flag for the PDF.
APPENDIX_FRONT_MATTER_KEY = "is_appendix"

# Front matter key overriding a page's own running header text - see
# `fix_up_page_html()`'s own docstring in prodockit.pdf.html.
RECTO_TITLE_FRONT_MATTER_KEY = "recto_title"

# Front matter flag excluding one navigation page from a complete PDF while
# leaving it in the website. An explicit ``false`` is required; omission keeps
# every existing project unchanged. A ``-m`` single-page build deliberately
# ignores this flag because the author has requested that page directly.
PDF_INCLUDE_FRONT_MATTER_KEY = "pdf_include"


def _inline_css_urls(css_text: str, css_dir: str) -> str:
    """Rewrites every relative `url(...)` reference in `css_text` (e.g. a
    `background-image` or a `.md-logo img { content: url(...) }` swap) into
    a base64 `data:` URI resolved against `css_dir`, leaving anything
    already a `data:`/`http(s):`/fragment (`#...`) URL, or a path that
    doesn't resolve to a real file, untouched.

    `build_pdf()`'s compiled CSS lives in its own temporary work directory,
    not `css_dir` - a relative reference in a project's own `extra_css`
    that resolves fine on the live website (relative to that stylesheet's
    own path) would otherwise point nowhere once compiled there, silently
    breaking e.g. a light/dark logo swap or a header background image."""

    def url_replacer(match: re.Match[str]) -> str:
        quote, ref = match.group(1), match.group(2)
        if ref.startswith(("data:", "http://", "https://", "#")):
            return match.group(0)
        asset_path = os.path.abspath(os.path.join(css_dir, ref))
        if not os.path.isfile(asset_path):
            return match.group(0)
        ext = os.path.splitext(asset_path)[1].lower().strip(".")
        mime_type = {"svg": "image/svg+xml", "jpg": "image/jpeg"}.get(ext, f"image/{ext}")
        with open(asset_path, "rb") as f:
            b64_payload = base64.b64encode(f.read()).decode("utf-8")
        return f"url({quote}data:{mime_type};base64,{b64_payload}{quote})"

    return re.sub(r'url\((["\']?)([^)"\']+)\1\)', url_replacer, css_text)


def _css_escape_content_string(text: str) -> str:
    """Collapses `text` to a single line and escapes it for safe use inside
    a CSS `content: "..."` string - `build_css()`'s own docs note `site_name`
    "should already be CSS-content-string-safe" before being passed in,
    since it substitutes it directly into such a string with no escaping of
    its own.

    Only `site_name` needs this now - `copyright_text` is a real HTML
    fragment rendered as a real DOM element instead (see `build_pdf()`'s and
    `prodockit.pdf.css`'s own docs), not escaped into a CSS `content`
    string, so a real link inside it survives. `project.site_name` is
    typically a short, single-line, plain-text value, but passed through
    unescaped, a raw newline or `"` would still break the generated CSS rule
    outright, silently dropping the whole running header entry with no
    error."""
    clean_text = text.strip().replace("\n", " ").replace("\r", " ")
    sanitized_text = clean_text.replace("&copy;", "©").replace("&#169;", "©")
    escaped_text = "".join(
        f"\\{ord(char):04X} " if ord(char) > 127 else char for char in sanitized_text
    )
    return escaped_text.replace('"', '\\"')


# Windows cannot start the extensionless `mmdc` that `npm` writes into
# `node_modules/.bin`: that one is a POSIX shell script, and the runnable
# shims sit beside it as `mmdc.cmd` and `mmdc.ps1`. The bare name is the
# spelling every platform's documentation uses, and `os.path.exists`
# confirms it happily - so it resolves, then fails at the point of use with
# `[WinError 193] %1 is not a valid Win32 application`, which surfaces as a
# per-diagram render warning rather than anything naming the real cause.
#
# A fixed suffix list rather than `PATHEXT`: this is about what
# `CreateProcess` can start, which does not vary per machine, and a user who
# has added `.PS1` to their own `PATHEXT` would otherwise steer us onto a
# shim that is not directly executable either.
_WINDOWS = os.name == "nt"
_EXECUTABLE_SUFFIXES = (".cmd", ".exe", ".bat", ".com")


def _runnable_spellings(path: str) -> list[str]:
    """Returns the ways `path` might name something this platform can
    actually execute, most preferred first. Everywhere but Windows, and for
    a path that already carries a suffix, that is just `path` itself."""
    if not _WINDOWS or os.path.splitext(path)[1]:
        return [path]
    return [path + suffix for suffix in _EXECUTABLE_SUFFIXES] + [path]


def _find_mmdc_bin(configured: str | None) -> str | None:
    """Resolves a usable `mmdc` (mermaid-cli) binary path: an explicit
    `configured` path if given and it exists, else whatever `mmdc` is found
    on `PATH`, else a couple of common local-install locations, else None
    (Mermaid diagrams are then left unrendered rather than failing the
    whole build).

    A relative `configured` path resolves against the current working
    directory, not wherever the `zensical.toml` it came from lives - fine
    for the common case of running `prodockit pdf` from the project root
    (the same directory both `configured` and `config_path` are typically
    relative to), but a `-f`/`--config-file` pointing at a project in a
    different directory needs an absolute `pdf_mmdc_bin` instead.

    On Windows every location is tried with an executable suffix first, so
    a `configured` or default path naming the bare `mmdc` still resolves to
    the runnable `mmdc.cmd` beside it - see `_runnable_spellings`.
    """
    if configured:
        for candidate in _runnable_spellings(configured):
            if os.path.exists(candidate):
                return candidate
    found = shutil.which("mmdc")
    if found:
        return found
    for base in (
        os.path.join("tools", "mermaid", "node_modules", ".bin", "mmdc"),
        os.path.join("node_modules", ".bin", "mmdc"),
    ):
        for candidate in _runnable_spellings(base):
            if os.path.exists(candidate):
                return os.path.abspath(candidate)
    return None


def _find_tex2svg_script(configured: str | None) -> str | None:
    """Resolves a usable `tex2svg`-style Node script path for TeX math
    pre-rendering: an explicit `configured` path if given and it exists,
    else a common local-install location, else None (math formulas are
    then left as literal, unrendered text rather than failing the whole
    build). Same CWD-relative caveat for a relative `configured` path as
    `_find_mmdc_bin` above."""
    if configured and os.path.exists(configured):
        return os.path.abspath(configured)
    candidate = os.path.join("tools", "mathjax", "tex2svg.js")
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    return None


def _warn_if_release_sources_disagree(api_release_tag: str) -> str | None:
    """Warns when the PDF's `{RELEASE}` marker and the website's
    `{{ release }}` will show different things, and returns the message.

    They are resolved from deliberately different sources.
    `{{ release }}` is `git describe --tags` on the local checkout, chosen so
    the website's hot rebuild path - every save under `zensical serve` -
    never makes a network call. `{RELEASE}` queries the host's releases API,
    chosen for a cover page that isn't part of a macro-rendered site at all.
    Both are right for their context, so neither is changed here.

    What was missing is that a disagreement was invisible. A reader
    comparing the published site with its downloadable PDF could see two
    different release numbers, with nothing in either build having failed.
    See prodockit-extensions#125 for the cases: a tag with no published
    release, a published release in a checkout with no tags (a shallow
    clone), and the window during a release when the version-bump commit is
    pushed before its tag.
    """
    local_tag = _get_release()
    if local_tag == api_release_tag:
        return None
    if local_tag and api_release_tag:
        message = (
            f"⚠️  Release mismatch: this PDF will show {api_release_tag!r} (from "
            f"the host's releases API) while the website's `{{{{ release }}}}` "
            f"shows {local_tag!r} (from `git describe --tags`)."
        )
    elif local_tag:
        message = (
            f"⚠️  Release mismatch: the website's `{{{{ release }}}}` shows "
            f"{local_tag!r}, but no published release was found via the host's "
            "API, so this PDF's `{RELEASE}` line will be dropped entirely."
        )
    else:
        message = (
            f"⚠️  Release mismatch: this PDF will show {api_release_tag!r} (from "
            "the host's releases API) while the website's `{{ release }}` will "
            "be empty - `git describe --tags` found no tag, which usually means "
            "a shallow clone."
        )
    print(message)
    return message


def build_pdf_from_zensical_config(
    config_path: str = "zensical.toml",
    *,
    markdown_file: str | None = None,
    on_stage: StageReporter | None = None,
) -> str:
    """Build through the legacy Zensical Python rendering path.

    This remains available through the hidden ``prodockit pdf-legacy``
    command as a rollback path.
    """
    return _build_pdf_from_config(
        config_path,
        markdown_file=markdown_file,
        on_stage=on_stage,
        built_site=False,
    )


def build_pdf_from_built_site(
    config_path: str = "zensical.toml",
    *,
    markdown_file: str | None = None,
    on_stage: StageReporter | None = None,
) -> str:
    """Build from the output of Zensical's documented build command.

    This is the implementation behind the public ``prodockit pdf`` command.
    It remains separate from :func:`build_pdf_from_zensical_config` so the
    legacy renderer can stay available as an undocumented rollback command.
    """
    return _build_pdf_from_config(
        config_path,
        markdown_file=markdown_file,
        on_stage=on_stage,
        built_site=True,
    )


def _build_pdf_from_config(
    config_path: str = "zensical.toml",
    *,
    markdown_file: str | None = None,
    on_stage: StageReporter | None = None,
    built_site: bool,
) -> str:
    """Builds a PDF entirely from `config_path` (a Zensical config file)
    and returns the path it was written to.

    If `markdown_file` is given (a path relative to `project.docs_dir`),
    the PDF is built from just that one file instead of `project.nav` -
    everything else (fonts, page size, margins, `heading_numbering`, and so
    on) still comes from `config_path` exactly as it would for a full
    nav-driven build. `pdf_output` still overrides the output path if set;
    otherwise it defaults to `markdown_file`'s own name (with a `.pdf`
    extension) inside `docs_dir`, rather than `site_documentation.pdf`.

    Reads (all optional except `nav` when `markdown_file` isn't given, with
    defaults matching a typical Zensical project):

    - `project.nav` - which pages to include, in order (ignored if
      `markdown_file` is given).
    - `project.docs_dir` (default `"docs"`).
    - `project.site_name`, `project.copyright`, `project.repo_url`.
    - `project.theme.font.text`/`.code` - main/monospace font.
    - `project.theme.icon.admonition` - per-admonition-type icon shortcodes,
      if you've customised them (used to give admonitions an icon in the
      PDF the same way your website already shows one).
    - Under `project.extra`: `pdf_output` (default
      `"<docs_dir>/site_documentation.pdf"`), `pdf_copyright` (overrides
      `project.copyright` for the PDF's own running footer only - the live
      website's copyright text, which always reads `project.copyright`
      directly, is untouched either way; unset by default, so every
      existing project's PDF and website keep showing the exact same text
      they always have. Both accept a real HTML fragment, same as
      Zensical's own website-side `copyright` setting already does - a real
      `<a href="...">` link renders as a real, clickable link in the PDF
      too, not flattened to plain text; use a real `<br>` for a forced line
      break. The one thing a PDF-only value makes possible that the shared
      one can't: a second line crediting the PDF pipeline specifically,
      without also adding that same markup to the website's copyright
      text), `pdf_page_size`,
      `pdf_margin_{top,right,bottom,left}`, `pdf_double_sided` (default
      `false`) and its own `pdf_margin_{inner,outer}` (replace
      `pdf_margin_{left,right}` when set - see `build_pdf()`'s own
      `double_sided` docs), `pdf_header_footer_{font_size,color,divider_color}`,
      `heading_numbering` (default `true`), `reference_style` (`"european"`
      - the default - or `"global"`), `reference_spacing_european`,
      `reference_indent_global`, `reference_spacing_global`,
      `pdf_mmdc_bin` and `pdf_tex2svg_script` (both auto-detected if unset -
      see `_find_mmdc_bin`/`_find_tex2svg_script` - Mermaid diagrams/math
      formulas are simply left unrendered if neither is found, rather than
      failing the build), `pdf_math_dir`, `pdf_include_table_of_contents`
      (default `true`), `pdf_table_of_contents_title`, `pdf_extra_css` (a
      list of `docs_dir`-relative stylesheet paths, same
      shape as `project.extra_css` below, but meant *only* for the PDF -
      e.g. a rule that would look wrong on the live website, or one
      overriding something `project.extra_css` itself sets - concatenated
      after it, so it wins the cascade).

      Bundling this project's own Markdown source into a separate PDF is
      `prodockit source-bundle`, a different command - see
      `build_source_bundle_from_zensical_config()` below
      (prodockit-extensions#212). It reads `pdf_source_bundle_output` and
      `pdf_page_size` under `project.extra`, not this function.
    - Under `project.markdown_extensions."prodockit.index"`: `include`
      (default `false`) generates a back-of-book index from every
      `\\index{Term}` marker, and `title` (default `"Index"`) sets that
      page's heading. See `build_pdf()`'s own `include_index` documentation
      for why this needs a real two-pass build, and `prodockit.pdf.index`
      for the module behind it.
    - `project.extra_css` - your site's own stylesheet(s) (the same setting
      Zensical itself reads to style the live website), passed through as
      `build_pdf()`'s own `extra_css` - so a project-specific `@media print`
      rule (e.g. hiding a website-only "Download PDF" link/button) applies
      in the PDF too, since WeasyPrint always renders in print mode. Any
      relative `url(...)` reference in it (e.g. a light/dark logo swap or
      a header background image) is resolved and base64-embedded before
      being passed through, since the compiled CSS `build_pdf()` writes
      lives in its own temporary directory, not wherever your stylesheet
      does.

    A page's own front matter `pdf_include: false` keeps it on the website but
    omits it from a complete, navigation-driven PDF. An explicit single-page
    build with `-m` still includes the requested page. A page's own front
    matter `is_appendix: true` flag gives it letter-
    based numbering, matching `prodockit.headings`' own `appendix_attr`
    default. A page's own front matter `recto_title: "Short Title"`
    overrides that page's running header text - see `fix_up_page_html()`'s
    own docstring in `prodockit.pdf.html`.

    **Cover page markers**: for a full, nav-driven build (never a
    `markdown_file`-scoped one) whose first page is `nav`'s own index
    page, any of these literal strings in that page's markdown are
    substituted with a real value once its HTML exists - no configuration
    needed beyond writing the marker itself:

    - `{WORDCOUNT}` - the site-wide word count (see
      `prodockit.zensical_macros._compute_site_word_count()` - the exact
      same value a `{{ word_count }}` website macro would show), so a
      submission's PDF cover page and its live website page never
      disagree.
    - `{REPOURL}` - the git-detected repo URL (see
      `prodockit.zensical_macros._get_repo_url()`).
    - `{RELEASE}` - the latest published GitHub/GitLab release tag (see
      `prodockit.pdf.release.get_latest_release_tag()`) - the whole line
      containing this marker is dropped instead if there isn't one (most
      projects never publish a release at all).
    - `{{ site_name }}` - this function never evaluates Jinja, so the
      exact same literal text a website macro variable uses substitutes
      directly here too.
    """
    project_config = None
    zensical_render = None
    rendered_site_icons: dict[str, str] = {}
    if built_site:
        project_config = load_project_config(config_path)
        project_theme = project_config.project.get("theme") or {}
        project_icon_config = (
            project_theme.get("icon") or {} if isinstance(project_theme, dict) else {}
        )
        project_admonition_icons = (
            project_icon_config.get("admonition") or {}
            if isinstance(project_icon_config, dict)
            else {}
        )
        rendered_site_icons = build_site(project_config, project_admonition_icons)
        config = project_config.as_resolved_mapping()
        # Preserve the command's user-facing relative output paths and build
        # arguments. The extractor itself uses ProjectConfig's resolved paths,
        # so it does not depend on the caller's CWD.
        config["docs_dir"] = project_config.project.get("docs_dir") or "docs"
        config["site_dir"] = project_config.project.get("site_dir") or "site"
    else:
        # Deliberately retained only for the hidden legacy command. These are
        # the undocumented APIs issue #561 is intended to remove eventually.
        import zensical.config as zensical_config
        from zensical.markdown.render import render as _zensical_render

        config = zensical_config.parse_config(config_path)
        zensical_render = _zensical_render
    extra = config.get("extra") or {}
    theme = config.get("theme") or {}
    font = theme.get("font") or {}
    admonition_icon_config = (theme.get("icon") or {}).get("admonition") or {}

    docs_dir = config.get("docs_dir") or "docs"
    source_docs_dir = str(project_config.docs_dir) if project_config is not None else str(docs_dir)
    if markdown_file:
        nav_pages = [{"url": markdown_file}]
    else:
        nav_pages = flatten_nav(config.get("nav") or [])
        if not nav_pages:
            raise ValueError(f"No pages found in {config_path}'s nav - nothing to build")

    icon_dirs = (
        discover_icon_dirs(source_docs_dir)
        if project_config is not None
        else discover_legacy_icon_dirs(str(docs_dir))
    )
    icon_registry = build_icon_registry(icon_dirs)
    if project_config is not None:
        # The public path recovers bundled theme icons from the completed
        # site rather than the installed Zensical package layout. The CSS is
        # a fallback for defaults; the temporary Markdown probe is
        # authoritative for explicitly configured icon shortcodes.
        built_icons = build_site_icon_registry(project_config.site_dir, admonition_icon_config)
        built_icons.update(rendered_site_icons)
        built_icons.update(icon_registry)
        icon_registry = built_icons

    extra_css = ""
    # project.extra_css - shared website/PDF stylesheets - first, then
    # extra.pdf_extra_css - stylesheets meant only for the PDF. build_pdf()
    # places its generated renderer foundation before this complete string,
    # so pdk.css -> extra.css -> pdk-pdf.css -> print.css is a real cascade
    # in which the author-owned files can override equal-specificity defaults.
    for css_rel_path in (config.get("extra_css") or []) + list(extra.get("pdf_extra_css") or []):
        full_css_path = os.path.join(source_docs_dir, css_rel_path)
        with open(full_css_path, encoding="utf-8") as f:
            extra_css += _inline_css_urls(f.read(), os.path.dirname(full_css_path)) + "\n"

    mmdc_bin = _find_mmdc_bin(extra.get("pdf_mmdc_bin"))
    mermaid_state = {"count": 0}
    render_mermaid = None
    if mmdc_bin:
        mermaid_dir = os.path.join(source_docs_dir, ".prodockit-pdf-mermaid")

        def render_mermaid(source: str) -> str | None:
            mermaid_state["count"] += 1
            return render_mermaid_diagram(source, mmdc_bin, mermaid_dir, mermaid_state["count"])

    tex2svg_script = _find_tex2svg_script(extra.get("pdf_tex2svg_script"))
    math_dir = extra.get("pdf_math_dir")
    if math_dir:
        # build_lua_filter()'s math_dir "must already exist or be creatable
        # by the caller" - only relevant here for an explicitly configured
        # directory; the default (build_pdf()'s own work_dir) already
        # exists by the time the Lua filter needs it.
        os.makedirs(math_dir, exist_ok=True)

    page_objects: list[Page] = []
    for nav_page in nav_pages:
        docs_rel_path = nav_page["url"]
        full_path = os.path.join(source_docs_dir, docs_rel_path)
        source_meta = page_metadata(Path(full_path))
        if not markdown_file and source_meta.get(PDF_INCLUDE_FRONT_MATTER_KEY, True) is False:
            continue
        if project_config is not None:
            html = page_html(project_config, docs_rel_path)
            meta = source_meta
        else:
            assert zensical_render is not None
            with open(full_path, encoding="utf-8") as f:
                raw_content = f.read()
            result = zensical_render(raw_content, docs_rel_path, docs_rel_path)
            try:
                html = result["content"]
                meta = result["meta"]
            except (KeyError, TypeError) as error:
                installed = _installed_zensical_version()
                raise RuntimeError(
                    f"prodockit expected Zensical's render() result to carry {error}, "
                    f"rendering {docs_rel_path!r}. Zensical {installed} appears to have "
                    "changed the result shape. prodockit cannot build the PDF without it."
                ) from error
        page_objects.append(
            Page(
                docs_rel_path=docs_rel_path,
                html=html,
                # Zensical marks every directory's `index.md` as an index
                # page for website routing. Only the first navigation page
                # can be this compiled document's cover; treating a nested
                # `about/index.md` as another cover strips its chapter number
                # and bookmark from the PDF.
                is_index=not page_objects and bool(nav_page.get("is_index")),
                is_appendix=bool(meta.get(APPENDIX_FRONT_MATTER_KEY, False)),
                recto_title=meta.get(RECTO_TITLE_FRONT_MATTER_KEY) or None,
            )
        )

    # Cover-page markers (see this function's own docs below) - a
    # nav-driven build's own cover page (its first page, if flagged
    # is_index) can use {WORDCOUNT}/{REPOURL}/{RELEASE}/{{ site_name }}
    # literally in its markdown, substituted here once the page's real
    # HTML exists. Skipped for a single markdown_file build - there's no
    # "cover page" to speak of, just whichever one page was requested.
    if not markdown_file and page_objects and page_objects[0].is_index and len(page_objects) > 1:
        cover = page_objects[0]
        cover_html = cover.html
        if "{WORDCOUNT}" in cover_html:
            cover_html = cover_html.replace("{WORDCOUNT}", _compute_site_word_count(config))
        if "{REPOURL}" in cover_html or "{RELEASE}" in cover_html:
            # Computed from the local git remote (like the website's own
            # {{ repo_url }} - see _get_repo_url()), not this function's
            # own repo_url (config.get("repo_url"), passed to build_pdf()
            # below): in practice they usually match, but they're not the
            # same mechanism.
            git_repo_url = _get_repo_url()
        if "{REPOURL}" in cover_html:
            cover_html = cover_html.replace("{REPOURL}", git_repo_url)
        if "{RELEASE}" in cover_html:
            # Unlike {WORDCOUNT}/{REPOURL}, which are always locally
            # computable, most projects will never have a published
            # release - an empty result drops the whole line rather than
            # leaving a bare "Release: " label behind.
            release_tag = get_latest_release_tag(git_repo_url)
            _warn_if_release_sources_disagree(release_tag)
            if release_tag:
                cover_html = cover_html.replace("{RELEASE}", release_tag)
            else:
                cover_html = re.sub(r"^.*\{RELEASE\}.*\n?", "", cover_html, flags=re.MULTILINE)
        if "{{ site_name }}" in cover_html:
            # prodockit.pdf never evaluates Jinja, so the exact same
            # literal "{{ site_name }}" text used for the website's macro
            # variable can just be substituted directly here too - one
            # line of markdown works for both outputs, no separate marker.
            cover_html = cover_html.replace("{{ site_name }}", config.get("site_name") or "")
        cover.html = cover_html

    if extra.get("pdf_output"):
        output_path = str(extra["pdf_output"])
    elif markdown_file:
        stem = os.path.splitext(os.path.basename(markdown_file))[0]
        output_path = os.path.join(docs_dir, f"{stem}.pdf")
    else:
        output_path = os.path.join(docs_dir, "site_documentation.pdf")
    (
        reference_style,
        reference_spacing_european,
        reference_indent_global,
        reference_spacing_global,
    ) = reference_style_values(extra)

    index_config = (config.get("mdx_configs") or {}).get("prodockit.index") or {}

    build_pdf(
        page_objects,
        output_path,
        docs_dir=docs_dir,
        extra_css=extra_css,
        repo_url=config.get("repo_url") or "",
        admonition_icon_config=admonition_icon_config,
        icon_registry=icon_registry,
        render_mermaid=render_mermaid,
        # Zensical supplies these documented Material-theme defaults in its
        # resolved configuration even when a source config has no ``font``
        # table.  The direct reader deliberately does not call that private
        # resolver, so carry the same public defaults here.  Prodockit-based
        # projects still use Inter/JetBrains Mono because their configs name
        # those fonts explicitly.
        main_font=font.get("text") or "Roboto",
        mono_font=font.get("code") or "Roboto Mono",
        copyright_text=(extra.get("pdf_copyright") or config.get("copyright") or "").strip(),
        site_name=_css_escape_content_string(config.get("site_name") or ""),
        page_size=extra.get("pdf_page_size") or "A4",
        margin_top=extra.get("pdf_margin_top") or "2cm",
        margin_right=extra.get("pdf_margin_right") or "2cm",
        # 2.5cm, not 2cm like the others: the running footer lives in this
        # margin and a two-line one came within 6.1mm of the paper edge -
        # see prodockit.pdf.css's own margin_bottom.
        margin_bottom=extra.get("pdf_margin_bottom") or "2.5cm",
        margin_left=extra.get("pdf_margin_left") or "2cm",
        double_sided=bool(extra.get("pdf_double_sided", False)),
        margin_inner=extra.get("pdf_margin_inner") or "2cm",
        margin_outer=extra.get("pdf_margin_outer") or "2cm",
        header_footer_font_size=extra.get("pdf_header_footer_font_size") or "10pt",
        header_footer_color=extra.get("pdf_header_footer_color") or "#555555",
        header_footer_divider_color=extra.get("pdf_header_footer_divider_color") or "#e2e8f0",
        reference_style_global=reference_style == "global",
        reference_spacing_european=reference_spacing_european,
        reference_indent_global=reference_indent_global,
        reference_spacing_global=reference_spacing_global,
        heading_numbering_enabled=heading_numbering_enabled(extra),
        mathjax_available=tex2svg_script is not None,
        math_dir=math_dir,
        tex2svg_script=tex2svg_script or "",
        include_table_of_contents=bool(extra.get("pdf_include_table_of_contents", True)),
        table_of_contents_title=extra.get("pdf_table_of_contents_title") or "Table of Contents",
        include_index=bool(index_config.get("include", False)),
        index_title=index_config.get("title") or "Index",
        on_stage=on_stage,
    )

    return output_path


def build_source_bundle_from_zensical_config(config_path: str = "zensical.toml") -> str:
    """Builds this project's source bundle - its Markdown content and its
    own Zensical config, one file per page - entirely from `config_path`,
    and returns the path it was written to.

    A separate command from `prodockit pdf` (prodockit-extensions#212):
    the two PDFs serve different purposes (a rendered document vs. a
    record of what was written) and previously could not be built
    independently of one another - a project that wanted only the
    document paid for the source bundle's own `git ls-files` and
    WeasyPrint pass regardless, and a project that wanted only an updated
    source bundle paid for the far more expensive Pandoc/WeasyPrint
    document pipeline (Mermaid/TeX pre-rendering included) to get it.

    Reads, all optional except `site_name` for a report with no running
    header:

    - `project.docs_dir` (default `"docs"`).
    - `project.site_name` - the running header's report name.
    - Under `project.extra`: `pdf_source_bundle_output` (default
      `"<docs_dir>/source_bundle.pdf"` - inside `docs_dir`, unlike the
      pre-#212 default of the project's top-level directory, so Zensical
      serves it without a separate copy step) and `pdf_page_size`
      (default `"A4", shared with `build_pdf_from_zensical_config()`'s
      own setting of the same name - one physical page size for both
      PDFs a project publishes).

    Which files are included is decided by
    `discover_markdown_and_config_files()` - root `README.md`, every `.md`
    file below `docs_dir`, and this project's own Zensical config. Paths are
    `root`-relative to `config_path`'s own directory, matching how
    `git ls-files` reports them regardless of where the command was run.

    Raises `SourceBundleError` if the underlying `git`/`weasyprint`
    invocation fails.
    """
    project_config = load_project_config(config_path)
    config = project_config.project
    extra = project_config.extra
    docs_dir = str(config.get("docs_dir") or "docs")
    root = str(project_config.root)

    if extra.get("pdf_source_bundle_output"):
        output_path = str(extra["pdf_source_bundle_output"])
    else:
        output_path = os.path.join(docs_dir, "source_bundle.pdf")

    build_source_bundle(
        output_path,
        root=root,
        report_name=config.get("site_name") or "",
        page_size=extra.get("pdf_page_size") or "A4",
        files=discover_markdown_and_config_files(
            root,
            docs_dir=docs_dir,
            config_file=config_path,
        ),
    )
    return output_path
