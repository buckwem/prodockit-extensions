# Release Notes

## Unreleased

- A new `unbookmarked` heading class removes a heading from the PDF's
  bookmark outline - the navigation pane a PDF reader shows down the side -
  separately from `unlisted`, which only keeps it off the generated Table
  of Contents *page*
  ([#173](https://github.com/buckwem/prodockit-extensions/issues/173)).

    The two are built by different tools. Pandoc's own
    `pandoc.structure.table_of_contents()` builds the contents page and
    honours `unlisted`; WeasyPrint builds the outline separately, straight
    from its own UA stylesheet, and nothing about `unlisted` (or any other
    class prodockit stamps on a heading) ever reached it - `prodockit.pdf.css`
    set no `bookmark-level` rule at all. An `unlisted` `h1` therefore still
    became a top-level outline node, and because outline nesting follows
    heading level, every later, lower-level heading nested underneath it
    instead of under its real chapter. Silent either way: the build
    succeeds and exits zero.

    `unlisted` itself is unchanged, and keeps meaning exactly what Pandoc
    means by it. `unbookmarked` is new and additive - `prodockit.pdf.css`
    now gives `h1.unbookmarked`-`h6.unbookmarked` `bookmark-level: none`,
    and nothing prodockit generates itself carries the class, so no
    existing PDF's outline moves. The back-of-book index's own A/B/C
    letter headings, the Table of Contents title, and every cover-page
    heading all carry `unnumbered unlisted` and deliberately stay off
    `unbookmarked`, since a reader still needs them in the outline to
    navigate - keying the new rule off `unlisted` itself, instead of adding
    a separate class, would have removed all three.

    Documented alongside `unnumbered` in
    [prodockit.headings](../extensions/headings.md#unlisted-and-unbookmarked-headings-pdf-only)
    and [PDF generation](../pdf.md#table-of-contents-and-bookmark-outline),
    where the two-tables-of-contents split is now explained as its own
    surface for the first time. This project's own
    `docs/extensions/refs.md` (whose illustrative headings needed exactly
    this, previously worked around with a project-local
    `.example-heading { bookmark-level: none; }` in
    `docs/stylesheets/extra.css`) now uses `unbookmarked` directly instead.

- The docs build now pins `Markdown` and `pymdown-extensions`, and
  `prodockit pins` manages them
  ([#178](https://github.com/buckwem/prodockit-extensions/issues/178)).

    Pinning a dependency exactly does nothing for the packages underneath
    it. `zensical` was pinned; it declares only floors for the two
    libraries that actually turn every page's Markdown into HTML, so every
    build rendered with whatever those resolved to that morning. A release
    of either could have changed the HTML on every page, and the site would
    have published it, green, with nothing committed.

    That matters more here than in most projects that render Markdown:
    `prodockit.pdf.css` and `prodockit.pdf.lua` both match on the specific
    class shapes pymdownx emits, so the renderer is an input to the PDF's
    own correctness, not only to the website's appearance.

    `prodockit pins` covers both by default now, so `--check` and the
    weekly drift job watch them alongside `zensical` and `weasyprint`. The
    drift job installs and reports them on both sides of its comparison -
    without that, a pymdownx release would have appeared in *both* builds
    and diffed to nothing.

    `Markdown`'s floor in `pyproject.toml` moves from 3.4 to 3.10.3 to
    match the pinned version, the same convention `zensical` already
    follows. Older releases are not known to break; the floor records what
    this is built and tested against.

- `prodockit pins --set PACKAGE=VERSION` no longer prompts for the packages
  it was not given, and no longer throws away the one it was.

    `--set` says "here is the version, do not ask" - the help text has
    always said it implies `--no-input` - but it only pre-answered the
    package named. Any other package in the managed set still prompted, so
    `pins --set zensical=0.0.53` in a release script or a drift job stopped
    at `weasyprint: version to set [69.0]:` and, with no stdin to answer
    it, aborted. Nothing was written *including the zensical sites it had
    been told explicitly to set* - the sharper half of the bug, because the
    run reported an abort rather than a partial write, and the workaround
    (`--package zensical --set zensical=0.0.53`) reads as though the two
    options mean different things.

    `--set` and `--latest` now suppress prompting outright. A package with
    no version given is reported under "Left untouched (no version given)"
    and its files are not opened. `--no-input`, which the help text named
    but the command never accepted, is now a real flag for the same
    behaviour with nothing set.

    An interrupted *interactive* run now keeps what it was already told:
    answers given before the interrupt are applied, the rest is left alone,
    and it still exits non-zero and says so. Writing nothing was the wrong
    reading of a cancelled prompt - the answers above it were not
    cancelled.

- Zensical pinned to **0.0.53** (from 0.0.52), after a byte-for-byte
  comparison of the site and PDF built under both.

    The PDF is **byte-identical** - same 994,803 bytes, same SHA-256, 151
    pages, 268 outline entries. The site changes 22 HTML files, each by
    exactly three lines: the `generator` meta tag and two asset-bundle
    hashes. No rendered page content changes.

    The bundles themselves grew 146 bytes (CSS) and 121 (JS). The whole CSS
    delta is `.md-search__button` - offsets and `text-align` moved out of
    the base rule into `[dir=ltr]`/`[dir=rtl]` variants, which is the
    release's right-to-left search fix. Every class prodockit couples to is
    unchanged (`md-typeset` 778 occurrences either side, `md-nav` 237,
    `md-content` 60; glightbox and mermaid hooks identical). Unlike 0.0.52,
    this release redraws no icon: icons are inlined as SVG into the HTML,
    and the HTML is identical apart from those three lines.

    Two builds of 0.0.52 were compared first, to establish that a
    difference means something: they were identical down to the PDF's raw
    SHA-256, so the build is fully deterministic and nothing above is
    build noise.

    The release notes list a `pymdownx` bump to 11.0, but that is a
    **floor raise only** - 0.0.52 declares `pymdown-extensions>=10.21.3`
    and 0.0.53 declares `>=11.0`, and both already resolve to 11.0.1. It
    was therefore not a variable in this comparison. See
    [#178](https://github.com/buckwem/prodockit-extensions/issues/178):
    the library that actually renders Markdown is not pinned at all.

    Every undocumented Zensical API on the
    [Zensical coupling](../devcons/zensical-coupling.md) page was
    re-checked against 0.0.53 and still resolves; `__all__` is still
    exactly `build`/`serve`/`version`. The page's "last verified against"
    now reads 0.0.53.

- The "this document contains TeX maths" warning no longer fires on a page
  that merely *documents* maths handling
  ([#176](https://github.com/buckwem/prodockit-extensions/issues/176)).

    A page quoting `<div class="arithmatex">` in a code span reaches the
    rendered HTML as `<code>&lt;div class="arithmatex"&gt;</code>` -
    Python-Markdown escapes the angle brackets and leaves the attribute
    text alone. The detector matched the bare `class="..."`, so prose about
    maths counted as maths, and `prodockit pdf` warned that formulas would
    ship as raw LaTeX in a document with no formulas in it. This project's
    own `devcons/limitations.md` did exactly that on every build.

    It now anchors on a real `<div`/`<span` opening tag, the way the
    Mermaid detector always has - which is why Mermaid never had the
    problem. A false alarm matters more here than most: the warning exists
    to make a *silent* degradation visible, and one that cries wolf teaches
    the reader to ignore the only signal there is.

- The MathJax toolchain `prodockit pdf` uses to pre-render TeX maths is now
  committed and installed in CI, alongside the Mermaid one
  ([#175](https://github.com/buckwem/prodockit-extensions/pull/175)).

    `tools/mathjax/` gains `package.json`, `package-lock.json` and
    `tex2svg.js` exactly as `prodockit init-tools` scaffolds them, with
    `npm ci --prefix tools/mathjax` added to `docs.yml` and `drift.yml`,
    both of which installed Mermaid only. Both sibling repos already
    tracked all three files; this brings extensions in line.

    **This fixed no live defect.** These docs contain no maths, so nothing
    was being published as raw LaTeX. The warning that prompted the work
    was the false positive fixed above. What it buys is that the first page
    to add a formula renders it, rather than shipping the source the way
    the Mermaid diagram in `extensions/bibliography.md` once did.

    The lockfile is committed deliberately, matching `tools/mermaid` -
    without it CI resolves whatever MathJax is newest rather than the
    version the output was checked against, which is the drift
    `prodockit pins` exists to catch.

    Worth knowing when relying on this: as merged, nothing here is guarded
    by a test that can fail. `test_no_page_contains_unrendered_tex_source`
    passes with the toolchain removed again, because with no maths in these
    docs it can only confirm that nothing unrendered reaches the PDF, not
    that the renderer is present. Closing that needs
    `pymdownx.arithmatex` enabled on this project's own docs, so the
    toolchain is exercised by the build that ships it.

- Documentation restructured: the six build-and-operate pages are now
  grouped under a **Dev Considerations** section, and `Refs` is renamed
  **Cross-References**
  ([#170](https://github.com/buckwem/prodockit-extensions/issues/170)).

    The nav had grown to thirteen top-level entries, enough that the theme
    cut the tabs off. Nine now, with `docs/devcons/` holding continuous
    integration, repository metadata, version pinning and drift, testing
    your built site, Zensical coupling, and limitations and workarounds
    behind a short introduction.

    `Managing the build` was one 747-line page carrying three unrelated
    subjects; it is split at its own level-2 boundaries into
    `continuous-integration.md`, `repo-metadata.md` and `pinning-drift.md`,
    each promoted one heading level so it reads as a page rather than a
    fragment. **Every existing heading anchor is unchanged**, so the only
    part of a link that moved is the file it points at.

    Page URLs *have* moved - `/continuous-integration/`, `/testing/`,
    `/limitations/` and `/zensical-coupling/` are now under `/devcons/`.
    Every link inside the docs and the README was updated with them; any
    external bookmark to an old URL will 404.

## 0.18.1 (2026-08-04)

- New [Zensical coupling](../devcons/zensical-coupling.md) page, listing every
  Zensical API prodockit depends on that Zensical neither documents nor
  treats as public
  ([#166](https://github.com/buckwem/prodockit-extensions/issues/166)).

    Zensical exports exactly three names - `build`, `serve`, `version` -
    and prodockit uses none of them. Everything else it reaches for is a
    module-level import from inside the package, so any of it can be
    renamed in a *patch* release without that counting as a breaking change
    upstream. Nothing in these docs said which, so the coupling was
    invisible until a release broke it.

    The page records each API with its call site and why it is needed, the
    undocumented *data shapes* prodockit reads (the resolved nav tree's
    `url`/`is_index`/`children`, `env.conf`, the packaged icon directory
    layout), and - deliberately - a list of the Zensical features that
    *are* documented, so it doubles as a triage aid when something breaks.

    It also sets out what a Zensical upgrade actually needs: not a green
    test run, but a build of both site and PDF with the **output compared**,
    since 0.0.52 silently redrew an icon with no source change. Recorded as
    last verified against 0.0.52.

- prodockit now says so when an undocumented Zensical API it depends on
  moves, instead of failing in a way that points at its own internals
  ([#167](https://github.com/buckwem/prodockit-extensions/issues/167)).

    `prodockit._zensical`'s two Zensical lookups guarded the *import* and
    nothing after it, so they handled exactly one failure mode - "Zensical
    isn't installed". A renamed `ContextPreprocessor.from_markdown`, a
    changed signature, or a `Page.path` renamed to something else all
    import perfectly and then raise `AttributeError`/`TypeError` from deep
    inside a `zensical build`, with nothing connecting it to the version
    bump that caused it. None of these APIs is public - `zensical` exports
    only `build`/`serve`/`version` - so a rename can arrive in a patch
    release.

    The guards now cover the attribute access and the call as well, and
    emit a warning naming the API, the installed Zensical version, and what
    actually degrades. Deliberately *not* a bare `except Exception: return
    None`: `page_source()` returning None silently makes every page share
    one default source, each render wiping the previous page's registry
    entries, so cross-page references, citations and glossary terms resolve
    to `??` on a site that still builds and exits zero. That is
    [#54](https://github.com/buckwem/prodockit-extensions/issues/54) again,
    in a form no test would catch.

    A plain `ImportError` stays silent - not running under Zensical is a
    legitimate state for any other Python-Markdown consumer - and each API
    is reported once per process rather than once per page, since
    `page_source()` runs on every render.

## 0.18.0 (2026-08-02)

- A reference to a page's *title* heading now resolves in the PDF
  ([#163](https://github.com/buckwem/prodockit-extensions/issues/163)).
  Each page's own anchor was written onto its first heading, **replacing**
  whatever id that heading already had - so `\ref{chapter-two}` pointed at
  an anchor that no longer existed. The reference still rendered its text,
  so nothing looked wrong; the link was simply dead, and `\autoref` printed
  "on page" with nothing after it.

    Sections *within* a page were unaffected, which is why it went
    unnoticed - the broken case is the most natural reference to write.

    The page anchor is now carried by an empty span inside that heading, so
    both exist: the page's own anchor for a cross-page link with no
    fragment, and the heading's for a reference to the heading itself.
    Inside rather than before, because a numbered `h1` breaks to a new page
    and an anchor placed before one would sit at the foot of the previous
    page, reporting a page number one too low.

- Cross-references say what they point at. `\ref{id}` renders the target's
  **number and name** - "1.1 Configuration" - because a bare "see 1.1"
  tells a reader nothing about what they are being sent to, and having to
  look it up in the contents defeats the point of the cross-reference
  ([#151](https://github.com/buckwem/prodockit-extensions/issues/151)).

    An appendix needs nothing special: its letter is already the first
    segment of its number, so a reference to an appendix section renders
    "A.1 Terms".

    An `unnumbered` heading - a cover page, appendix front matter - has no
    number but does have a name, so it resolves to just the name. Only a
    genuinely unknown id is unresolved.

- New `\autoref{id}`, for references that still work on paper. It renders
  the same text as `\ref{id}` and additionally carries the target's
  **page number** in the PDF: *"Configuration is covered in 1.1
  Configuration on page 12."*

    The suffix comes from prodockit.pdf's own stylesheet, so it appears
    only there - a page number on a scrolling website would be meaningless
    - and needs no configuration. Which to use is a per-reference
    decision: `\autoref{id}` where a printed reader needs to turn to
    something, `\ref{id}` where "on page N" would just be noise.

    Implemented with CSS `target-counter()`, which resolves the target's
    page at layout time and so needs no second pass - unlike the
    back-of-book index, which has to deduplicate a term repeated on one
    page and therefore cannot use it.

- The generated index now appears in the Table of Contents
  ([#141](https://github.com/buckwem/prodockit-extensions/issues/141)). Its
  heading carried Pandoc's `unlisted` class, which is exactly what
  `pandoc.structure.table_of_contents()` honours - so an index a reader
  goes looking for was the one section the contents never mentioned.

    It stays `unnumbered`, so it takes no chapter number and appears at the
    end alongside the last chapter. Two things deliberately keep
    `unlisted`: the Table of Contents heading itself, since a contents
    listing itself is noise, and the index's own A/B/C letter headings,
    which would otherwise fill the contents with single letters.

- The default bottom margin is now `2.5cm` rather than `2cm`, so a
  multi-line running footer is not cropped when printed
  ([#139](https://github.com/buckwem/prodockit-extensions/issues/139)).

    The footer is top-aligned in the bottom margin and grows *downward* as
    it gains lines, so whatever the margin does not use is the space left
    before the paper edge. This project's own footer is two lines - a
    copyright line and a "Made with" credit - and measured on a real render
    it ended **6.1mm** from the edge. Consumer and office printers commonly
    cannot print within 5-6.4mm, so the second line was at real risk of
    being cropped: the PDF was correct and the paper was not.

    2.5cm leaves about 11.1mm. The other three margins are unchanged, so
    pages are 5mm shorter and a long document gains a few pages - this
    project's own went from 134 to 139. Set `pdf_margin_bottom` to `"2cm"`
    to restore the previous layout, and set it higher for a footer of three
    or more lines.

    Raising the margin rather than moving the footer within it: both footer
    boxes are top-aligned with matching `margin-top`/`padding-top` so their
    border-tops form one continuous rule across the page. Bottom-aligning
    them to guarantee clearance instead would let a two-line box and the
    one-line page number sit at different heights and break that rule.

## 0.17.5 (2026-08-02)

- `prodockit --version` prints the installed version
  ([#149](https://github.com/buckwem/prodockit-extensions/issues/149)).
  There was no way to tell which version a checkout or CI job was actually
  running short of `pip show prodockit`.

    Prints the bare number, matching `zensical --version` rather than
    click's own default of `prodockit, version X.Y.Z` - the two are
    normally installed and reported together, and a matching format means
    neither needs parsing to compare them.

- `prodockit pins` now sees a requirement with extras
  ([#156](https://github.com/buckwem/prodockit-extensions/issues/156)).
  `package[extra]==version` is an ordinary shape - `prodockit[index]`,
  `uvicorn[standard]`, `celery[redis]` - and the bracket sits between the
  name and the operator, exactly where the matcher expected one to
  follow the other. Such a declaration was invisible.

    The failure mode was the bad one: `pins` reported "not declared
    anywhere", which reads as *nothing to do* rather than *could not parse
    this*. A project could pin something, run `pins --check` in CI, and get
    a pass while the declaration drifted untouched.

    Extras are recorded per site and written back on rewrite, the same way
    each site's operator already is, so `prodockit[index]>=0.17.2` becomes
    `prodockit[index]==0.17.4` rather than `prodockit==0.17.4`. Dropping
    them would silently stop installing an optional dependency - for
    `prodockit[index]` that means the back-of-book index quietly stops
    being generated.

## 0.17.4 (2026-08-02)

Documentation only - no library, CLI or CI behaviour changes.

- The three pages covering how a prodockit build is run and kept stable -
  repository metadata, continuous integration, and version pinning and
  drift - are now one page, **Managing the build**. They were written
  separately and read as three answers to the same question; a reader
  setting up a pipeline needed all three and had no reason to expect the
  third. Each is now a section, introduced by a short chapter overview
  naming all three, and continuous integration keeps its own H2 rather
  than being the page's implicit subject.

    Existing links still resolve: `version-pinning.md` and
    `repository-metadata.md` are gone, and every reference to them - in
    the README, in these release notes - now points at the corresponding
    anchor on the merged page.

- The GitHub Actions example in that page now shows the `verify` job from
  0.17.2, so the recipe a reader copies includes the delivery check rather
  than the version that predates it.

- The 0.17.1 entry below now carries the CI costs that were actually
  measured, rather than describing them as "paid once per interpreter".
  Installing WeasyPrint took the 3.13 job from 59 seconds to about 14
  minutes - a 13-minute install, compiling from source, against roughly 20
  seconds on 3.10-3.12 - and enabling the pip cache brought that install
  back to 15 seconds and the job to under two minutes. Those are the
  figures that tell a reader whether the cache is worth enabling in their
  own matrix.

## 0.17.3 (2026-08-02)

- Docs deploys no longer run from a release event, which never worked and
  failed silently. A release event runs against `refs/tags/<tag>`, so the
  Pages deployment it created carried a tag ref - and with Pages
  configured `source: {branch: main}`, that deployment was accepted,
  reported `success`, and was then never served. The site simply carried
  on returning the previous build.

    Every release from 0.17.0 to 0.17.2 did this, each needing a manual
    `gh workflow run docs.yml --ref main` afterwards. The evidence is
    unambiguous: across nine Pages deployments, every one from `main` went
    live and every one from a tag ref did not
    ([#147](https://github.com/buckwem/prodockit-extensions/issues/147)).

    It was not a race between the push-triggered and release-triggered
    runs, which is what it looked like for a long time. The concurrency
    group serialised them correctly - on 0.17.2 the release run started
    only after the push run had finished, deployed later, and still lost.

    `docs.yml` now triggers on `push` and `workflow_dispatch` only. A new
    `release-redeploy.yml` handles the post-release rebuild by
    re-triggering `docs.yml` against `main`, so the deployment carries a
    branch ref - automating exactly what the manual fix did each time. The
    `tag: prodockit-v*` entry in the github-pages environment's deployment
    branch policies is now redundant.

    [Continuous integration](../devcons/continuous-integration.md#ci-release-numbering)
    documents the trap, since the obvious fix is the broken one.

## 0.17.2 (2026-07-30)

- README, the package description and the module docstring now cover
  `prodockit pins` alongside the other commands, so a reader arriving from
  PyPI sees it exists.

- New `prodockit pins` command: shows every place a build-input version is
  declared across a project, and moves them all together. Pinning a build
  means writing the same version in several files at once - a floor in
  `pyproject.toml`, an exact pin in each CI job that builds the docs,
  another in whatever job checks for drift - and nothing enforces that
  they agree. When they disagree the failure is quiet: CI builds with one
  version while the declared floor says another.

    Run it with no options for a prompt per package - press ++enter++ to
    take the newest release on PyPI, or type a version. Each site keeps
    **its own operator**, so a library floor stays a floor and a build pin
    stays exact; one answer updates every file correctly.

    Three shapes of declaration are recognised, because a build input is
    not always a pip package: a pip specifier (`zensical==0.0.52`), a
    GitHub runner label (`runs-on: ubuntu-24.04`) and a container image tag
    (`image: python:3.13`). The last two carry `pandoc`, the fonts a PDF
    embeds and the Chrome that rasterises diagrams - none of which pip can
    reach - so they belong in the same inventory. Neither has a package
    index to ask, so the suggested default is simply what is already set.

    `--check` reports and exits non-zero if anything is behind PyPI *or*
    if the files disagree with each other, for a scheduled job.
    `--set PACKAGE=VERSION`, `--latest` and `--offline` cover the
    non-interactive cases.

    Scans both CI layouts - `.github/workflows/` and
    `.gitlab-ci.yml`/`.gitlab/` - plus `pyproject.toml`, `setup.cfg` and
    root `requirements`/`constraints` files, so the same command works
    whichever host a project uses. Build output and virtualenvs are
    skipped, so a stale copy of a workflow inside `site/` or `.venv/` is
    not mistaken for a declaration.

- `weasyprint` is now pinned in the docs build and the test job, alongside
  `zensical`. It decides pagination, so a release that lays out one
  paragraph differently shifts every page number after it - and those page
  numbers are content, resolved into the back-of-book index and the table
  of contents. That is a silently wrong document rather than a failed
  build. Pinned in `ci.yml` too, because the real-render tests assert on
  where things physically land, which makes the layout engine an input to
  those assertions rather than an implementation detail.

- New `drift.yml`, so pinning does not mean going quietly stale. Weekly it
  builds the docs twice in one job - once with the pinned versions, once
  with the newest - diffs the results byte for byte, runs the
  built-output checks against the newer build, and opens an issue saying
  what an upgrade would change. Both builds share a job, so pandoc,
  Chrome, fonts and the runner image are identical between them and any
  difference is attributable to the upgraded packages alone. It reports
  rather than fails, and keeps one open issue updated in place: a
  scheduled job that goes red every week trains everyone to ignore it.

- CI runners are pinned to `ubuntu-24.04` rather than `ubuntu-latest`.
  The image is the build input pip cannot reach: `pandoc` comes from it
  (and distribution packages lag upstream far enough that some markdown
  edge cases parse differently), as do the fonts the PDF embeds and the
  Chrome that rasterises Mermaid diagrams. On `ubuntu-latest` all three
  move the day GitHub migrates the label, with nothing committed - the
  same silent change the package pins exist to prevent, one layer down.

    `ubuntu-latest` already *is* 24.04, so nothing changes today; it takes
    effect at the migration, which is exactly when a documentation build
    wants to be told rather than surprised. Pinned images are retired
    about a year after the following LTS and the job then fails outright
    rather than drifting - the better failure, and at a time of your
    choosing.

- New [Version pinning and drift](../devcons/pinning-drift.md#pinning-version-pinning-and-drift) page documenting
  the whole arrangement - where a version gets declared and why the forms
  differ, `prodockit pins`, and a drift job for **both** GitHub Actions
  and GitLab CI, the latter using pipeline schedules and the GitLab issues
  API.

- `zensical` now declares a floor (`>=0.0.52`) rather than being left
  entirely open. It records the version prodockit is developed and built
  against - not a minimum below which anything breaks, since 0.0.50 and
  0.0.51 both work. Zensical is pre-1.0 and prodockit reaches well past
  its public surface (the config loader, the per-page render context
  `prodockit.headings` detects, the icon set `prodockit.pdf.icons`
  resolves against), so which version produced a given build is worth
  recording. A floor rather than an exact pin because prodockit is a
  library: `==` would propagate to every consumer and conflict with any
  project needing a different Zensical.

    What prompted this is worth keeping visible. Rebuilding against 0.0.52
    and diffing the output byte for byte against 0.0.51: the PDF is
    identical, and every page of the website differs - Font Awesome moved
    7.2.0 to 7.3.1 and redrew the GitHub brand icon used in the header's
    repository link and the social footer. One visible change out of the
    nine icons the site uses, arriving with nothing committed. The rest is
    the generator version string, content-hashed asset filenames, and
    minified bundle churn.

    A floor does not prevent that recurring: dependency resolution still
    takes whatever is newest, so the next Zensical release can change the
    published site the same way. Reproducible builds need a constraint on
    the *build* side - in `docs.yml` - rather than in library metadata.

## 0.17.1 (2026-07-29)

- This project's own PDF now has the back-of-book index its own docs
  describe. `zensical.toml` never set `extra.pdf_include_index`, which
  defaults to off, so the live `\index{}` markers in
  `docs/extensions/index-terms.md`'s `=== "Result"` tabs produced nothing:
  the page documenting the feature sat in a PDF that didn't have it.

    Turning the setting on alone would only have indexed those five demo
    markers, so the docs are now marked properly throughout: every module
    at its own page's opening sentence, every option/setting/fixture in
    the reference table that defines it, and the concepts and external
    tools where each is introduced. Options are nested under what they
    belong to, so the `source`/`registry`/`unresolved` that five different
    extensions each define group per module instead of collapsing into one
    misleading entry. That gives a real two-page index of about 95
    entries, covering every marker shape the extension supports.

    Costs one extra `pandoc`+WeasyPrint pass on that one build. The
    twelve single-page `prodockit pdf -m` builds in `docs.yml` pay
    nothing: `build_pdf()` skips the second pass entirely for a document
    with no markers, and none of those pages has any. Mermaid and TeX
    pre-rendering both happen before either pass, so neither is repeated.
    Measured locally at roughly 8s → 12s for a 119-page document, against
    a docs workflow dominated by apt, Chrome and npm setup.

- The 0.17.0 fix above now has a permanent CI guard. Its regression test
  needs a real `pandoc`+WeasyPrint install, so it is deselected in the
  `test` job, which installs neither - the shipped fix was effectively
  unguarded. `tests/test_built_docs.py` gains three `built`-marked checks,
  which run in `docs.yml` after a real build: that no marker reached the
  PDF's text layer, that the index was generated with every marked term in
  it, and that each entry cites a page the term is actually on.

    The text-layer check matches only a marker followed by a real digit,
    rather than the blunter substring the synthetic test can afford. These
    release notes legitimately print `⟦prodockit-index-N⟧` (with a literal
    "N") in the 0.17.0 entry below, and name the
    `h2.prodockit-index-letter` CSS class in an earlier one - both are
    prose about the feature, and both belong in the text layer.

- A long index term no longer overflows its own column. An index entry is
  often a single unbroken token with nowhere to wrap - a dotted module
  path, a long option name, a function signature - and
  `div.prodockit-index-entry` set no `overflow-wrap`, so such a term ran
  straight over the column rule into the next column's entries, and off
  the page edge entirely from the right-hand column. Found while indexing
  this project's own docs. `overflow-wrap: break-word` (not `break-all`,
  so ordinary multi-word terms still break at their spaces first) fixes
  it. Covered by a real-render test that measures where the glyphs
  actually land, since it renders as perfectly ordinary text either way
  and only its position gives it away.

- The generated index's pages are now headed "Index" (or whatever
  `pdf_index_title` says) rather than by the last chapter of the
  document. The index's own `h1` is `unnumbered` - correct, since it must
  not take a section number or a Table of Contents entry - but
  `unnumbered` is also what excludes a heading from feeding the running
  header's `chapter-title` string. That exclusion suits the Table of
  Contents, which sits at the front where `chapter-title` is still empty,
  and fails for the index, which is always the very last thing in the
  document: whatever chapter came last simply stayed in the header. This
  project's own PDF was headed "18. License" across its entire index. The
  heading now carries a `prodockit-index-title` class with a `string-set`
  rule of its own; nothing else about it changes.

- CI now installs WeasyPrint for the `test` job, so the nine real-render
  tests that assert on where things actually land in a finished PDF -
  which page a heading starts on, what the running header says, whether a
  long index term stayed inside its column - finally run. They are gated
  on a real `pandoc`+`weasyprint` install and `ci.yml` had only `pandoc`,
  so they skipped silently on every run; `docs.yml` does install
  WeasyPrint, but runs only `-m built` against `tests/test_built_docs.py`,
  so it never reached them either. The behaviour they exist to pin was
  going unchecked everywhere, including both fixes above.

    The tests themselves add about 20 seconds per matrix entry.
    Installing WeasyPrint costs more, and unevenly: it pulls in packages
    with no wheel published for every interpreter the matrix covers. On
    3.10-3.12 the install step took roughly 20 seconds; on 3.13 it spent
    **13 minutes** compiling them from source, taking that job from 59
    seconds to about 14 minutes.

    `actions/setup-python`'s own pip cache is now enabled, which holds
    pip's *built* wheels as well as its downloads. That brought the same
    3.13 install back to **15 seconds** and the job to under two minutes.

## 0.17.0 (2026-07-28)

- Back-of-book index markers no longer leave anything in the PDF's text
  layer ([#133](https://github.com/buckwem/prodockit-extensions/issues/133)).
  Every `\index{Term}` used to deposit a `⟦prodockit-index-N⟧` token
  next to the word it marked - 67 of them in this project's own User
  Guide. They were invisible on the page, but real text in the file, so
  they surfaced in copy and paste, in the reader's own search, in text
  extraction, and, worst, in screen readers, read out mid-sentence.

    The markers had to stay findable, which is why they were text: the
    second pass locates each one to learn its page number, and a
    `font-size: 0` span is dropped from the text layer entirely, leaving
    nothing to find. Shrinking further was never an option.

    Each occurrence is now marked with an *empty* span carrying only an
    `id`, and its page is read back from the PDF's own named destinations
    - WeasyPrint emits one per element `id`, whether or not anything
    links to it. Nothing is encoded as text, so nothing can leak. An
    empty span also occupies no width, which removes the previous
    design's awkward question of whether stripping 67 tiny spans between
    passes might reflow the very pages whose numbers they had just
    recorded.

    Needs no configuration change, and no new dependency: `pymupdf` was
    already required for `pdf_include_index`, and the API used has been
    available since well below the existing floor.

## 0.16.0 (2026-07-28)

- The website's `{{ release }}` and the PDF's `{RELEASE}` come from
  deliberately different sources - `git describe --tags` on the local
  checkout, and the host's releases API - and could disagree with nothing
  saying so
  ([#125](https://github.com/buckwem/prodockit-extensions/issues/125)). A
  reader comparing a published site with its downloadable PDF could see two
  different release numbers, and neither build had failed.

    Neither source changes: each is right for its own context. `{{ release }}`
    is re-evaluated on every website rebuild, including every save under
    `zensical serve`, so it must not make a network call; `{RELEASE}` serves
    a cover page that isn't part of a macro-rendered site at all. What was
    missing is that the disagreement was invisible.

    `prodockit pdf` now warns when the two will show different things,
    naming both values and where each came from. The macros pass warns
    separately when `{{ release }}` came back empty *because* the checkout
    is a shallow clone, which fetches no tags even from a repository that
    has them - the failure behind #122, silent because an empty value just
    renders as a missing line. The warning names `fetch-depth: 0` and
    `GIT_DEPTH`, and fires once per process rather than once per rebuild.

    A project with no tags at all stays silent: that is a normal state, and
    warning about it would only train people to ignore the message. See
    [Limitations and workarounds](../devcons/limitations.md#limitations-pdf-generation).

## 0.15.2 (2026-07-28)

- `prodockit.testing`'s Mermaid check now detects a diagram whose arrows
  were swallowed by font ligatures. A PDF set in a font with programming
  ligatures - JetBrains Mono, a common choice for code blocks - renders
  `-->` as a single glyph that extracts back out as `//>`, leaving every
  arrow-based pattern blind to an unrendered diagram. Node-definition
  brackets (`id[Label]`) survive extraction, so they now count as evidence
  too. Found in `prodockit-template`, whose own PDF uses that font.

    Accepting bracket syntax needed the keywords tightened first, or it
    would have fired on ordinary prose. `graph`/`flowchart` now require
    their direction token (`graph LR`), which no sentence produces by
    accident, and the four diagram types that are also plain English words
    - `gantt`, `journey`, `pie`, `timeline` - accept only arrow or
    entity-relationship evidence, never brackets. Without that, a line
    beginning "timeline of the project" followed by `data[1]` read as an
    unrendered diagram.

## 0.15.1 (2026-07-27)

- Documentation only. New
  [Continuous integration](../devcons/continuous-integration.md) page: complete,
  working GitHub Actions and GitLab CI recipes for building a prodockit
  site, and the reasoning behind each part
  ([#124](https://github.com/buckwem/prodockit-extensions/issues/124)).

    This knowledge previously existed only as comments scattered across
    three projects' workflow files, which is why the same mistakes kept
    recurring. The page is organised around the failure modes that are
    *silent* - fonts not installed (WeasyPrint substitutes one and the PDF
    just looks wrong), a shallow clone fetching no tags (the release line
    vanishes), the renamed Puppeteer variable, and a release deploying
    before its own tag exists.

## 0.15.0 (2026-07-27)

- New `prodockit.testing` package - `pip install prodockit[testing]`. A
  pytest plugin giving a project `prodockit_*` fixtures for its own built
  site and PDF, resolved from its Zensical config rather than an assumed
  layout, plus checks for the failure modes every prodockit project shares.
  See [Testing your built site](../devcons/testing.md).

    Chiefly `assert_no_unrendered_mermaid()` and
    `assert_no_unrendered_tex()`, which turn the 0.12.0 build warning into
    a test failure - three projects published PDFs full of raw
    `flowchart LR ...` source and literal LaTeX before anyone noticed
    ([#124](https://github.com/buckwem/prodockit-extensions/issues/124)).

    The Mermaid check requires a diagram-type keyword *and* Mermaid's own
    link syntax nearby. Several diagram types (`graph`, `pie`, `journey`,
    `timeline`) are ordinary English words, and PDF line breaks fall
    wherever text wraps, so a keyword-only check read "a visual commit
    graph and richer history browsing" as an unrendered diagram - passing
    locally and failing in CI only because different fonts wrapped that
    sentence differently.

    The plugin registers through pytest's entry point, so it loads into
    every test run in an environment where prodockit is installed. It
    imports nothing heavy at module scope, prefixes every fixture, and
    fails individual fixtures rather than collection, so an unrelated
    project is unaffected.

## 0.14.0 (2026-07-27)

- New `prodockit init-tools` command: scaffolds the Node tooling
  `prodockit pdf` needs to render Mermaid diagrams and TeX maths, then
  prints the `npm` commands, `.gitignore` lines and CI environment
  variables to finish the job. See
  [Mermaid diagrams and TeX maths](../pdf.md#mermaid-diagrams-and-tex-maths).

    `prodockit.pdf` has always looked for `tools/mermaid/node_modules/.bin/mmdc`
    and `tools/mathjax/tex2svg.js` while shipping neither, leaving every
    project to hand-write the same two manifests and the same `tex2svg.js`
    ([#124](https://github.com/buckwem/prodockit-extensions/issues/124)).
    All three projects using it got that wrong independently: one had no
    `tools/` directory at all and published PDFs full of raw
    `flowchart LR ...` source, two set the pre-rename
    `PUPPETEER_SKIP_CHROMIUM_DOWNLOAD` that puppeteer 25.x ignores, and one
    committed two config files nothing reads. The canonical copies now live
    in the library, pinned in one place.

    Existing files are never overwritten without `--force`, since a project
    will have run `npm ci` against its own committed lockfile.

- The missing-renderer warning added in 0.12.0 now points at
  `prodockit init-tools` rather than `npm ci --prefix tools/mermaid`, which
  could not work in the case that actually happened - no `tools/`
  directory to install into.

## 0.13.0 (2026-07-27)

- Documented the Python version requirement. `requires-python = ">=3.10"`
  has always been enforced by `pip`, and CI has always tested 3.10-3.13,
  but nothing said so anywhere a reader would look: the PyPI classifiers
  listed only `Programming Language :: Python :: 3`, and neither the
  README nor the installation page mentioned a version at all. Per-version
  classifiers added, and [Installation](../installation.md) now opens with
  the requirement plus a full table of what `pip` does and doesn't install
  - including `pandoc`/`weasyprint`, and the Node tooling needed only for
  Mermaid diagrams and TeX maths in the PDF.

- New `prodockit sync-repo` command, and the `prodockit.sync_repo` module
  behind it: keeps `repo_url`, `repo_name`, `[project.theme.icon] repo`,
  `edit_uri` and your README's badge row matching the git remote a
  checkout actually uses, so forking or mirroring a project between
  GitHub, GitLab and Bitbucket doesn't leave stale links, the wrong brand
  icon, or badges pointing at somebody else's repository. `--check` writes
  nothing and exits non-zero on drift, for CI. See
  [Repository metadata](../devcons/repo-metadata.md#sync-repo-repository-metadata).

    This was previously a `sync_repo_icon.py` script copied byte-for-byte
    between two consuming projects
    ([#124](https://github.com/buckwem/prodockit-extensions/issues/124)).
    Two things changed in promoting it: the default branch is now detected
    from the remote rather than hardcoded to `main`, and `repo_name` keeps
    whichever shape (`owner/repo` or bare `repo`) your config already uses,
    since Zensical prints it verbatim in the site header and the script's
    fixed choice would have restyled the header of any project using the
    other one.

- The command-line entry point moved from `prodockit.pdf.cli` to
  `prodockit.cli`, now that it has commands unrelated to the PDF build.
  `prodockit.pdf.cli` re-exports `main`, so an entry point recorded in an
  already-installed environment keeps working.

## 0.12.0 (2026-07-27)

- `prodockit pdf` now warns when a document contains Mermaid diagrams or
  TeX maths but the renderer needed to turn them into static images
  wasn't found. Both have always been optional, and both deliberately
  leave the content untouched rather than failing the build - the right
  default for a project using neither, but silent for one that *is*
  using them. That silence let raw `flowchart LR ...` source and literal
  LaTeX reach the published PDFs of three separate projects, including
  this one's own. The build still succeeds; the degradation is simply
  announced, and the warning names the fix rather than just the symptom.
- Fixed this project's own docs: the architecture diagram in
  `extensions/bibliography.md` had never rendered in any published PDF,
  for exactly the reason above. `tools/mermaid` and the CI steps to
  install it are now in place - so the page describing how Mermaid
  fences are pre-rendered finally demonstrates it.

## 0.11.1 (2026-07-27)

No code changes - fixes a regression in 0.11.0's own release:

- The "Release: `<tag>`" cover-page line added in 0.11.0 never actually
  appeared on the deployed site or PDF - `actions/checkout`'s default
  shallow clone (`fetch-depth: 1`) fetches no tags at all, so
  `prodockit.zensical_macros`' `{{ release }}` (`git describe --tags
  --abbrev=0`) always returned `""` in CI, even though it worked
  correctly in any full local checkout. Fixed by adding `fetch-depth: 0`
  to this project's own `docs.yml`/`ci.yml` checkout steps. Confirmed
  directly against the redeployed live site.
- Fixed [#120](https://github.com/buckwem/prodockit-extensions/issues/120):
  `.cover-hero-subtitle`/`.cover-hero-release` (this project's own
  `docs/stylesheets/extra.css`) both rendered in black rather than the
  intended grey in the PDF - `color: var(--md-default-fg-color--light)`
  is undefined in `prodockit.pdf`'s own generated CSS, and an unresolved
  `var()` with no fallback falls back to the *inherited* value instead
  of erroring.
- Fixed [#121](https://github.com/buckwem/prodockit-extensions/issues/121):
  rather than just special-casing the PDF, added a `var()` fallback
  pointing at this project's own explicit `--prodockit-fg-color-light`
  custom property - the live website still gets the real, theme-adaptive
  Zensical variable whenever it's actually defined, but a future
  Zensical rename/removal of that variable can no longer silently break
  this project's own PDF-visible text again.

## 0.11.0 (2026-07-27)

New `{{ release }}` variable in `prodockit.zensical_macros`: the latest
git tag reachable from `HEAD` (e.g. `"1.2.0"`, `""` if the checkout has no
tags at all), matching `word_count`/`repo_url`'s existing pattern.
Promotes a one-off custom macro `prodockit-userguide` already had in its
own project-local `macros.py` into the shared library, so every project
gets it for free instead of hand-rolling the same
`git describe --tags --abbrev=0` shell-out. Resolves identically for the
website and for `prodockit pdf`, since both render through the same
macro environment - unlike `prodockit.pdf`'s own `{RELEASE}` cover-page
marker, which queries the host's GitHub/GitLab API instead, for a
project whose cover page isn't part of a live, macro-rendered site at
all.

This project's own docs site now shows "Release: `<tag>`" on its cover
page, using the `.cover-hero-release` CSS class that was already defined
but never actually used - enabling the macros plugin here for the first
time in the process. Also fixed a real bug found while wiring this up:
`.cover-hero-release` rendered in a bold weight in the PDF
(`Inter-Ultra-Bold` instead of `Inter`, confirmed via the PDF's own
extracted font info) - it was missing the `font-weight: 400` its sibling
`.cover-hero-subtitle` already has, for the same Pandoc-pipeline reason.

Fixes [#116](https://github.com/buckwem/prodockit-extensions/issues/116).
See [#120](https://github.com/buckwem/prodockit-extensions/issues/120)
for a related, separate rendering issue found along the way (both
`.cover-hero-subtitle` and `.cover-hero-release` render in black rather
than the intended light gray in the PDF - not fixed here).

## 0.10.9 (2026-07-26)

Docs only, no code changes:

- New [Limitations and workarounds](../devcons/limitations.md) page, consolidating
  every confirmed limitation across prodockit's three surfaces (the
  Python-Markdown extensions, `prodockit.pdf`, and
  `prodockit.zensical_macros`) and its workaround in one place, including
  cross-page resolution going stale under `zensical serve`'s live reload
  ([#99](https://github.com/buckwem/prodockit-extensions/issues/99)) -
  previously scattered across `pdf.md`'s own "Limitations and
  workarounds" section, which is now a short pointer here instead.
- `bibliography.md`'s "What this project's own template and user guide
  currently do" section no longer says neither downstream project has
  adopted `prodockit.bibliography` -
  [prodockit-template](https://github.com/buckwem/prodockit-template) has
  since migrated, and is now a real worked example of
  [Multiple sections](../extensions/bibliography.md#bibliography-multiple-sections):
  a cited-only `references.md` and a separate, everything-included
  `bibliography.md` from a distinct further-reading `.bib` file.
- Added GitHub issue templates (bug report, feature request), matching
  [prodockit-template](https://github.com/buckwem/prodockit-template)'s
  own.

## 0.10.8 (2026-07-26)

**Breaking:** the two citation extensions swap syntaxes.
`prodockit.bibliography` now uses `\cite{id}` - the natural spelling for
the workflow most projects reach for first - and `prodockit.citations`
moves to `\citeref{id}`.

**If you use `prodockit.citations`, replace every `\cite{id}` in your
content with `\citeref{id}`.** A `\cite{id}` left behind will no longer
resolve: with `prodockit.citations` alone it falls through as literal
text, and in a build that also enables `prodockit.bibliography` it will be
read as a `.bib` key instead.

The two extensions still own distinct syntaxes, so either can be enabled
alongside the other without hijacking it - only which name belongs to
which has changed. Each is now pinned by a test asserting it leaves the
other's syntax alone; neither had one before, so nothing would have caught
the two silently overlapping.

Multi-key citations remain a `prodockit.citations` feature
(`\citeref{id1,id2}`); `prodockit.bibliography` matches single keys only,
for the reasons its own documentation gives.

Part of [#111](https://github.com/buckwem/prodockit-extensions/issues/111);
the matching updates to `prodockit-template` and `prodockit-userguide`
follow separately.

## 0.10.7 (2026-07-25)

Two numbering fixes, both cases of the same shape: a raw-text pre-scan and
a parsed-document count applying different rules to the same content.

**Website and PDF disagreeing on appendix letters.** Appendix lettering was
computed twice. The website gave a letter to any page whose front matter
set `is_appendix`, unconditionally; the PDF's Lua filter counted appendix
h1s instead. An appendix page contributing no numbered h1 - none at all, or
one marked `unnumbered`, which the filter skips - gave Lua nothing to
count, so every later appendix came out a letter early. Reproduced against
`prodockit-template`: the same Bibliography page rendered as "Appendix E"
on the website but "Appendix D" in the PDF.

`prodockit.pdf.build` now assigns every appendix page's letter once, by
position in the page list, and stamps it on that page's heading for
`Header()` to read rather than counting for itself. A page with no numbered
h1 still consumes its letter, so the two stay in step.

**Setext headings invisible to the nav pre-scan.** `_count_top_level_headings()`
matched ATX headings only, so a title underlined with `=` was never
counted - though Zensical's renderer and Pandoc both produce a real h1
either way, and both number it. Later pages' start counts came out short,
which broke numbering twice over: the website contradicted itself, giving
the next page the chapter number a setext heading had already taken, and it
fell one behind the PDF. Each rule of the setext syntax was checked against
the real renderer rather than assumed - a single `=` is enough, a `-`
underline is an h2, a two-line paragraph followed by `=====` is no heading
at all, and `attr_list` puts `{: .unnumbered }` on the text line.

**Stale cross-page references under `zensical serve`.** `preseed()` is
deliberately first-wins so a duplicate id resolves to the first page in nav
order. Under `zensical build` that is all it has to do; under
`zensical serve` the process outlives the files, and first-wins silently
discarded fresh data - an edited definition kept its original text, and a
deleted one stayed resolvable, until the dev server restarted.
`preseed_attr_from_nav()` now rebuilds the provisional set from scratch on
each scan, and `prodockit.headings` keys its cached scan on every nav
page's mtime and size as well as the numbering settings, so an edit to a
page a given render doesn't touch still invalidates it.

Note this fixes the pre-scan, not Zensical's incremental rebuild: verified
against a live `zensical serve`, editing page A does not cause page B to
re-render, so B's output still only catches up when B itself is
re-rendered. What is guaranteed now is that a page being re-rendered
resolves against current disk state rather than a snapshot from server
startup.

Fixes [#104](https://github.com/buckwem/prodockit-extensions/issues/104),
[#106](https://github.com/buckwem/prodockit-extensions/issues/106) and
[#99](https://github.com/buckwem/prodockit-extensions/issues/99).

## 0.10.6 (2026-07-25)

Fixed footnote text in the PDF rendering in a column roughly two thirds
of the page's content width, wrapping a footnote onto five short lines
whose first held just two words.

This had been documented in `prodockit.pdf.css`'s own `.pdf-footnote`
rule as an unfixable WeasyPrint `float: footnote` limitation being
tracked upstream. That was a misdiagnosis. The real cause is Pandoc's
HTML writer hard-wrapping its output at ~72 columns, inserting newlines
*inside* the `<span class="pdf-footnote">` carrying a footnote's text.
Those newlines are insignificant whitespace in HTML, but WeasyPrint's
`float: footnote` width computation treats them as hard break
opportunities when sizing the footnote area, so the rendered text
collapses toward the longest *source* line rather than the page's
content width.

Confirmed by holding the HTML and CSS constant and varying only the
Pandoc step: the same document rendered 304.1pt wide through Pandoc but
462.9pt straight through WeasyPrint. `prodockit.pdf.build` now passes
`--wrap=none`, giving 474.2pt of a ~482pt content width. WeasyPrint 69.0
is already the latest release, so waiting upstream had no path forward.

This does not stop footnotes wrapping in the PDF - `--wrap=none` governs
only newlines in the generated HTML source, never the engine's own line
breaking. A long footnote still occupies as many lines as it needs, each
now using the full measure: a seven-sentence footnote renders on six
full-width lines rather than ten narrow ones.

The misleading `KNOWN LIMITATION` comment in `prodockit.pdf.css` has been
replaced with the real cause so it isn't re-derived, and two regression
tests added - one asserting the flag at the command level (so it can't be
dropped where Pandoc isn't installed), one measuring real rendered text
width via a genuine Pandoc/WeasyPrint build, since the CSS is identical
either way and only a real render can tell the two apart.

Fixes [#101](https://github.com/buckwem/prodockit-extensions/issues/101),
reported downstream as
[prodockit-template#95](https://github.com/buckwem/prodockit-template/issues/95).

## 0.10.5 (2026-07-25)

Fixed a real bug found by reproducing it directly: a cross-page
`\ref{id}` under `zensical build` depended on whether the page defining
`id` happened to be rendered before the page referencing it, in the same
Python process - `zensical build` renders pages neither in nav order nor
necessarily all in one process, so this was pure luck. Reproduced
locally on a 3-page site: the previous release left 1-5 references as
`??` per build, varying from one otherwise-identical build to the next
(only 2 of 12 clean builds fully resolved).

`prodockit.headings` now pre-scans every nav page's headings (ids,
levels, section numbers) into the shared registry before any page is
converted - the same idea `prodockit.citations`/`prodockit.glossary`
already use for their own cross-page definitions - so resolution no
longer depends on build order. A page actually rendered in this process
still supersedes its own pre-scanned entries with the real ones. 20
consecutive clean builds now produce byte-identical, fully-resolved
output; `prodockit-template`'s entire built site is byte-identical
before and after this change.

Also fixed a second bug found while testing the above: extension order
isn't guaranteed, so `prodockit.refs` can construct its own default
`HeadingsExtension` and trigger the pre-scan with per-document numbering
before a project's configured `numbering = "continuous"` instance runs
- silently showing a cross-page reference's number one step behind
(`1.1` instead of `2.1`) roughly 1 build in 12. The pre-scan now reruns
if a differently-configured instance appears.

Fixes [#54](https://github.com/buckwem/prodockit-extensions/issues/54).
See [#99](https://github.com/buckwem/prodockit-extensions/issues/99) for
a related, separate limitation found along the way (this pre-scan can go
stale under `zensical serve`'s live-reload - not fixed here).

## 0.10.4 (2026-07-25)

- Added `CONTRIBUTING.md` and a `.github/pull_request_template.md`,
  adapted from [prodockit-template](https://github.com/buckwem/prodockit-template)'s
  own - library-specific setup (`pip install -e ".[dev]"`,
  `pytest`/`ruff`/`mypy`, the real-`pandoc` requirement for
  `prodockit.bibliography`'s own tests) rather than the template's
  assignment-writing framing. Linked from README.md's Development
  section.
- Docs: added an admonition to `headings.md` documenting a real gap this
  project's own docs hit directly while enabling every prodockit
  extension on its own site (#87) - Zensical's automatic cross-page id
  sharing only warns (rather than raising) on a heading name shared
  across pages, and build order isn't guaranteed stable, so the "keeping
  the first" winner can change between builds. Documents the fix - an
  explicit, page-prefixed id via `attr_list` - pointing to this
  project's own docs as a worked example.

No code changes.

## 0.10.3 (2026-07-25)

Docs: several extension pages mixed "why it was built this way" design
rationale into their opening paragraph, ahead of the practical "what it
does"/"how to use it" content most readers want first - moved that
reasoning further down each page instead:

- `bibliography.md`: trimmed the intro to the core value proposition,
  moved the Pandoc-delegation rationale and architecture diagram out of
  Requirements (now just what to install) into a new "How it works"
  section after Reference, and folded the "can be enabled alongside
  prodockit.citations" note into Comparing the two approaches.
- `citations.md`/`glossary.md`: moved the "why bundled into one
  extension, unlike headings/refs" rationale from the intro into their
  own Syntax section.
- `tables.md`: moved the "auto-enables Python-Markdown's own tables
  extension" implementation note from the intro into Syntax.
- `index-terms.md`: moved the "why a Markdown extension, not attr_list"
  rationale from the intro to the end of CSS hooks, wrapped in its own
  admonition naming the subject explicitly.

`headings.md`/`refs.md` were already lean and needed no changes. No
syntax, behaviour, or code changes.

## 0.10.2 (2026-07-25)

Docs: `extensions/index-terms.md` described the live website's search as
generic "browser/Ctrl-F search" - updated to point at
[Zensical's own built-in site search](https://zensical.org/docs/setup/search/)
instead, a more accurate and discoverable description of how a reader
actually finds a term on the live website. No code changes.

## 0.10.1 (2026-07-24)

Docs: `prodockit.index`'s marking syntax and `prodockit.pdf`'s back-of-book
index *generation* were split across two pages (`extensions/index-terms.md`
and `pdf.md` respectively), even though the marker is useless without
turning `pdf_include_index` on and vice versa - `prodockit.bibliography`'s
own docs already combine marking and generation into one page. Moved the
generation content into `extensions/index-terms.md` as a new "Generating
the index" section, merged the per-feature rendered-output examples into
their existing marking sections instead of duplicating them, and renamed
the page from "Index terms" to "Index (pdf-only)" now that it covers the
whole feature. `pdf.md` keeps only a short pointer, matching how
`prodockit.bibliography` is treated there. No code changes.

## 0.10.0 (2026-07-24)

`prodockit.bibliography`'s `\bibliography` marker now takes two optional,
positional parameters - `\bibliography{<file>}{<true|false>}` - so a
project can generate both a strict **References** section (only sources
actually `\citebib{}`-cited in the text) and a broader **Bibliography**
section (every entry, including background reading that's never
individually cited) in one build, from the same or different `.bib`
files:

```md
<!-- references.md -->
\bibliography{}{true}
```

```md
<!-- bibliography.md -->
\bibliography{background.bib}
```

Bare `\bibliography` is completely unchanged - fully backward compatible,
no breaking change. A `\citebib{id}` citation now cross-links to
whichever marker's page actually defines that entry (via a new,
lightweight `.bib` entry-key discovery helper, not a CSL reimplementation)
rather than assuming a single global bibliography page - the common
single-file case is unaffected. See
[Multiple sections: References and Bibliography](../extensions/bibliography.md#bibliography-multiple-sections)
for the full syntax and worked examples.

Fixes [#89](https://github.com/buckwem/prodockit-extensions/issues/89).

## 0.9.0 (2026-07-24)

**Breaking:** `copyright`/`pdf_copyright` are now a real HTML fragment,
rendered as a real DOM element in the PDF's running footer via CSS Paged
Media's `position: running()`/`content: element()`, instead of being
escaped into a CSS `content: "..."` string. This is what makes a real
`<a href="...">` link inside either value survive as a real, clickable
link in the PDF - on every page, not just wherever the source element
itself sits - matching how Zensical's own website-side `copyright`
setting already works. Use a real `<br>` for a forced line break; the
`\A ` CSS-escape trick added in 0.8.0 only ever worked for a plain
string, not real markup, and no longer applies - update any existing
`pdf_copyright` using it to a real `<br>` instead.

`prodockit.pdf.css.build_css()` no longer takes a `copyright_text`
parameter (`site_name` is unaffected, still a plain CSS content string)
- no formal, versioned public API surface yet for `prodockit.pdf` (see
prodockit-extension#7), so this is an acceptable break at this stage.

This project's own cover page (`docs/index.md`'s hero subtitle) no
longer hyperlinks the word "Zensical" - it stays as plain text, matching
this project's own PDF footer now crediting Zensical/prodockit with
real links instead of the cover page doing it via a website-only,
PDF-invisible link.

## 0.8.1 (2026-07-24)

Docs: this project's own docs site and PDF were missing the "Made with
Zensical and prodockit" credit line that `overrides/partials/
copyright.html`/`pdf_copyright` (new in 0.8.0) already give a downstream
project - added both here too, via a new `overrides/partials/
copyright.html` for the website and `extra.pdf_copyright` in
`zensical.toml` for the PDF, so this site credits itself the same way a
project built with it does. No library code changed.

## 0.8.0 (2026-07-24)

New `pdf_copyright` setting: `project.copyright` (a plain, native Zensical
setting) already feeds the footer of both the website and the PDF by
default - `pdf_copyright` is an opt-in override for the PDF's footer only,
for a project that wants its PDF footer to say something different from
its website's (e.g. adding a "Made with Zensical and prodockit" credit
line only to the downloadable PDF, not the live site). Write a forced
line break in either setting with a literal `\A ` inside a TOML *literal*
string (`'''...'''`) - see [Copyright text](../pdf.md#copyright-text) for
the full mechanism and why a literal string is required.

Also fixed a real, previously-undocumented rendering gap found while
building this: a `\A ` forced line break inside a `content` string only
actually renders as a line break under `white-space: pre-line` - under
WeasyPrint's default `white-space: normal` it silently collapsed to a
plain space instead. Both the single-sided and double-sided verso
copyright footer boxes now set `white-space: pre-line` so the forced
break always works as expected.

## 0.7.1 (2026-07-24)

This project's own documentation site now enables every prodockit
extension (`prodockit.headings`, `prodockit.refs`, `prodockit.citations`,
`prodockit.glossary`, `prodockit.bibliography`, in addition to the
`prodockit.tables`/`prodockit.index` already enabled) via `zensical.toml`,
dogfooding the full set rather than just the two used to build this
site previously.

Doing so surfaced a real bug: Zensical does not render pages in a stable
order between builds, so a heading name shared across two or more pages
(e.g. "Quick start", "Syntax", "Options") non-deterministically resolves
its id collision differently from one `zensical build` to the next -
confirmed by running repeated clean builds and observing the reported
"keeping the first" winner change between runs. Fixed by giving every
colliding heading across the docs an explicit, unique, page-prefixed id
via `attr_list` (e.g. `## Quick start {: #refs-quick-start }`), rather
than relying on build order at all. No library code changed - this is a
docs-content-only fix, and not something a project sharing a heading
name across its own pages will normally have to think about, since a
one-off name collision is far less likely there than in this project's
consciously-parallel per-extension documentation structure.

## 0.7.0 (2026-07-24)

**Breaking:** `prodockit.bibliography` now uses its own `\citebib{id}`
syntax instead of `\cite{id}`. Previously it registered the same
`\cite{id}` pattern `prodockit.citations` uses, at the same inline-pattern
priority - enabling both extensions together left it undefined which one
actually resolved a given `\cite{...}` occurrence. Renaming
`prodockit.bibliography`'s own syntax removes the conflict entirely: both
extensions can now be enabled in the same build with no interference,
each citing its own sources by its own marker. A project still using
`prodockit.bibliography` on its own needs to update every `\cite{id}` in
its source to `\citebib{id}` - the old syntax no longer resolves.

## 0.6.8 (2026-07-21)

`build_pdf_from_zensical_config()` (what `prodockit pdf` runs) now supports
cover page markers, so a project no longer needs its own custom Python
just to fill in a cover page's word count/repo URL/release tag - found via
`prodockit-template`, whose `build_pdf.py` had grown to nearly nothing
except this one piece:

- `{WORDCOUNT}` - the site-wide word count (the same value a
  `{{ word_count }}` website macro shows).
- `{REPOURL}` - the git-detected repo URL.
- `{RELEASE}` - the latest published GitHub/GitLab release tag - the
  whole line is dropped instead if there isn't one.
- `{{ site_name }}` - substituted literally, since `prodockit pdf` never
  evaluates Jinja.

All four are opt-in by literally writing the marker in your `nav`'s index
page - no new `zensical.toml` setting needed. See
[Cover page markers](../pdf.md#cover-page-markers).

Also new: `pdf_extra_css`, a stylesheet meant *only* for the PDF (e.g. a
rule that would look wrong on the live website), concatenated after
`extra_css` - the same `["stylesheets/print.css"]` role a project's own
custom PDF-build script might have hardcoded outside `zensical.toml`
entirely before, now expressible as ordinary configuration.

Also fixed two real bugs found while building this:

- `extra_css`'s (and now `pdf_extra_css`'s) own relative `url(...)`
  references (e.g. a light/dark logo swap or a header background image)
  were passed through unresolved, pointing nowhere once compiled into the
  PDF's own temporary work directory - now resolved and base64-embedded,
  matching how a local `<img>` reference already was.
- `copyright`/`site_name` were passed straight into `build_pdf()`'s
  generated CSS `content: "..."` string with no escaping at all -
  `project.copyright` is commonly a triple-quoted TOML string spanning
  multiple lines, and a raw embedded newline (or a literal `"`) silently
  broke the whole generated rule, dropping the running header/footer
  entirely with no error. Both are now collapsed to one line and escaped
  before being passed through.

## 0.6.7 (2026-07-21)

Fixed `prodockit.pdf.html.fix_up_page_html()` permanently embedding
*both* halves of a `#only-light`/`#only-dark` (or GitHub's
`#gh-light-mode-only`/`#gh-dark-mode-only`) image pair in a PDF, stacked
one after the other, instead of just one - found via `prodockit-template`'s
own cover page hero graphic showing twice. A PDF has no light/dark toggle
to make that convention meaningful, but `to_base64_data_uri()` already
strips anything from `#` onward before resolving the file (to find the
right one), so the resulting `data:` URI has no trace of the fragment
left for any stylesheet to hide either half by. The `#only-dark`/
`#gh-dark-mode-only` half is now dropped entirely rather than embedded.

## 0.6.6 (2026-07-21)

- Docs: the cover page hero graphic (`docs/assets/cover-hero-*.svg`) used
  a different colour palette in light mode (blue) than in dark mode
  (green) - recoloured the light variant to match dark exactly, so the
  hero reads the same regardless of theme. The "Download PDF" button
  also picked up this same green, rather than the theme's default
  primary colour.
- `prodockit.pdf.css`'s back-of-book index letter-group headings
  (`h2.prodockit-index-letter` - the "A", "B", "C" separators) were
  hardcoded to the hero graphic's *old* light-theme blue - updated to
  match the now-green hero, which a PDF always shows regardless of a
  project's own website light/dark toggle.
- No functional (Python package behaviour) changes beyond the index
  letter colour.

## 0.6.5 (2026-07-21)

Extends the 0.6.4 always-excluded-directory mechanism in
`prodockit.pdf.source_bundle` to two more classes of vendored, never
student-written content:

- Any directory literally named `styles` - a Vale `StylesPath`
  (conventionally named this way) holds downloaded rule packs (e.g. the
  Microsoft, proselint, and Readability style guides), typically tracked
  for offline/CI builds rather than gitignored.
- Common dependency lockfiles by exact file name - `package-lock.json`,
  `npm-shrinkwrap.json`, `yarn.lock`, `pnpm-lock.yaml`, `Pipfile.lock`,
  `poetry.lock`, `Cargo.lock` - machine-generated by a package manager,
  never hand-written, and often thousands of lines each.

Neither is project-configurable, matching 0.6.4's `.icons` exclusion: a
project can't reach for the same knob to narrow what a bundle archives.

Also fixes `source_bundle.pdf`'s running header naming the wrong file: a
file's own last page could show the *next* file's name instead of its
own, because the invisible marker that sets the header text had no page
break of its own - only the following content did - so it rendered on
the tail end of the previous file's last page. The break now moves onto
the marker itself, so the string-set and the page it applies to always
agree.

## 0.6.4 (2026-07-21)

`prodockit.pdf.source_bundle` now always excludes any directory literally
named `.icons` (e.g. a `custom_icons` directory, per `pymdownx.emoji`'s
own convention) from `source_bundle.pdf`, regardless of `.gitignore` -
found via `prodockit-template`, whose own vendored icon packs
(`overrides/.icons/bootstrap`, `overrides/.icons/gitlab` - together
~2,500 unused SVGs) turned a source bundle meant to hold a student's own
report content into a 3,000-page dump of unreferenced vendor assets.
`.gitignore` alone can't fix this, since these directories are typically
*tracked* (needed for the site/PDF to build at all) - deliberately not a
project-configurable setting, so a project can't reach for the same knob
to exclude something that should actually be archived.

## 0.6.3 (2026-07-20)

Bug fixes found by an in-depth test-coverage review of the extensions and
PDF pipeline test suites - each paired with a new regression test.

- Fixed `prodockit pdf`'s CLI command showing a raw, unhandled traceback
  instead of a clean `Error: ...` message when `pdf_source_bundle` was
  enabled and the underlying `git`/`weasyprint` invocation failed -
  `SourceBundleError` wasn't in the CLI's caught exception tuple.
- Fixed `prodockit.headings` numbering a skipped heading level (e.g. h1
  followed directly by h3, or a document starting below h1) with a
  literal "0" segment (e.g. "1.0.1") - a shallower level with no heading
  of its own yet is now treated as an implicit first one instead.
- Fixed `prodockit.pdf.mermaid` letting an uncaught `OSError`/
  `PermissionError` (e.g. a non-executable `mmdc` binary) escape instead
  of failing just that one diagram gracefully.
- Fixed `prodockit.pdf.source_bundle` crashing the whole bundle build on
  a file that's valid UTF-8 in the first 8 KiB sniffed to decide "is
  this text?" but not further in - now skipped like any other binary
  file instead.
- Fixed `prodockit.pdf`'s generated Lua filter producing broken syntax
  if a configured math/tex2svg path contained a quote or backslash -
  both are now escaped.
- Fixed `prodockit.pdf.build_pdf()` having no timeout on the underlying
  `pandoc`/WeasyPrint invocation, so a hang (e.g. a pathological CSS
  layout) could block the whole build indefinitely - added a
  `pandoc_timeout` parameter (default 30 minutes).
- Fixed a back-of-book index term nested more than three levels deep
  rendering with no extra indent at all, since the generated CSS only
  defines an indent step up to level 3 - now clamped to the deepest
  available indent instead.
- Substantially expanded test coverage across the extensions and PDF
  pipeline test suites (shared registries, cross-page linking, malformed
  input, table/index edge cases, icon/rotation/CSS edge cases) - no
  other functional changes.

## 0.6.2 (2026-07-20)

- Docs: fixed a real bug found by checking the live site after 0.6.1 -
  four spots in `docs/extensions/index-terms.md`/`docs/pdf.md` (plus two
  more in this same changelog) tried to show the code-styled `\index{}`
  syntax as literal example text using *inline* backticks around a
  hierarchical, code-styled path. Confirmed directly this doesn't work
  the way it does for the plain syntax - the code-styled pattern has to
  run before Python-Markdown's own backtick handling (see 0.6.0's own
  entry below), so inline backticks don't protect it, and the live site
  was rendering a raw internal Python-Markdown placeholder string instead
  of the intended literal text. Moved each one to a fenced code block
  (already documented as the safe way to show this syntax) or reworded to
  avoid the literal example entirely.
- No functional changes.

## 0.6.1 (2026-07-20)

- Docs: `prodockit.index` (new in 0.6.0) was missing from `README.md` -
  and so from PyPI's own project page - entirely: added it to the
  "Status" line and the extensions table, and mentioned
  `pdf_include_index` alongside `prodockit.pdf`'s other PDF-only
  features. Also added it to `pyproject.toml`'s own `description` (PyPI's
  summary line) and `src/prodockit/__init__.py`'s module docstring, both
  of which had the same gap.
- No functional changes.

## 0.6.0 (2026-07-20)

- New `prodockit.index` extension: mark a term inline with `\index{Term}`
  for a traditional, PDF-only back-of-book index (browser/Ctrl-F search
  covers this on the live website, so there's no equivalent there) - the
  term displays inline exactly as written and is marked for indexing in
  one go, no separate "definition" step. Needed its own extension rather
  than the usual `attr_list` marker convention every other prodockit
  extension uses - confirmed directly plain `attr_list` can't wrap
  arbitrary inline text in a span on its own.
    - **Sub-entries**: `\index{Parent!Child!Grandchild}` (up to three
      levels deep in practice, matching LaTeX `makeidx`'s own
      `\index{primary!secondary!tertiary}` convention) nests related
      entries together instead of listing every term flat.
    - **Code-styled terms**: backticks around the last segment - or,
      combined with sub-entries, around just the last segment of a
      hierarchical path - mark a command/code term: it displays inline in
      a real `<code>` element, and the generated index entry renders the
      same way.
    - A term can be a markdown link or contain nested emphasis/code -
      confirmed directly neither needs special handling, since a term
      isn't exempted from Python-Markdown's own later inline-pattern
      passes the way `\ref{id}`/`\cite{id}`/`\gls{id}` are.
- New `prodockit.pdf.index`: the two-pass build (a term's own page number
  can only be known once WeasyPrint has already laid the PDF out once)
  behind `pdf_include_index`/`pdf_index_title` (both off/unset by
  default) - a traditional, two-column, letter-headed index page
  (matching this project's own cover page hero graphic colour),
  alphabetised ignoring leading punctuation (so `--set-upstream option`
  files under "S", not a separate symbols section), with consecutive
  pages collapsed into an en-dash range (`67–70`). Requires the new
  optional `pymupdf` dependency - `pip install prodockit[index]`.
- Fixed a real bug found while writing tests: code-styling a non-last
  segment of a hierarchical term - never a supported combination, but
  this shouldn't have corrupted anything either - used to leak a raw
  Python-Markdown internal stash placeholder into the generated index
  instead of failing gracefully - a real rendered PDF would have shown a
  nonsense category label instead of "Git".

## 0.5.0 (2026-07-19)

- New `prodockit.pdf.source_bundle`: bundles every text/source file
  `.gitignore` doesn't exclude into a separate `source_bundle.pdf` at a
  project's own top-level directory - 8pt Courier, wrapped lines, each
  file starting its own page, a running header (`site_name` on the left,
  that page's own file path on the right), and a "Page N of M" footer.
  Off by default; set `pdf_source_bundle = true` under `[project.extra]`
  to turn it on. Independent of the rest of `prodockit.pdf` - there's no
  Markdown involved, so it skips Pandoc entirely and hands a small,
  self-contained HTML document straight to WeasyPrint. File discovery
  shells out to `git ls-files --cached --others --exclude-standard`
  rather than reimplementing `.gitignore`'s own matching rules; text/
  binary filtering is content-based, not by file extension.
- Docs: this site's own header now shows a PDF download icon next to
  "view" (an `overrides/partials/actions.html` override, linking to that
  page's own per-page PDF) instead of a "Download this page as PDF" text
  link at the top of the page - removed from every page that had one.
  Since the new icon is template markup rather than Markdown content, it
  also no longer shows up inside the PDF itself (no `.web-only` CSS trick
  needed, unlike the link it replaces).

## 0.4.2 (2026-07-19)

- Docs: matched more of this site's own theme config to
  [prodockit-userguide](https://github.com/buckwem/prodockit-userguide)'s -
  the header's repo link now shows the actual GitHub logo instead of
  Zensical's default Git icon; the "View source of this page" button now
  shows an eye icon instead of a generic file icon; every admonition
  (e.g. the "tip" callout in `citations.md`) now uses the same custom
  FontAwesome icon set userguide uses instead of Zensical's own bundled
  defaults - this also feeds into `prodockit.pdf`'s own admonition icons,
  so PDF output picks it up too; added the matching theme features
  userguide already had (`content.tabs.link` in particular actually
  affects this project's own tabbed content); and swapped the palette
  toggle icons to match userguide's own light/dark convention.
- No functional (Python package) changes.

## 0.4.1 (2026-07-18)

- Docs: reworked this site's own chrome to match
  [prodockit-userguide](https://github.com/buckwem/prodockit-userguide)'s -
  a new split hero cover page ("Home"), reusing that project's own logo/
  favicon/illustration assets; top-level nav moved to a top tab bar with
  the right-hand page TOC merged into the left sidebar instead; the
  previous cover page's own prose moved to a new "Introduction" page.
- Fixed a real bug found along the way: `zensical.toml`'s own `copyright`
  was a triple-quoted, multi-line TOML string - `prodockit.pdf` substitutes
  it verbatim into a CSS `content: "..."` string for the PDF's running
  footer, and the embedded newline silently broke that declaration,
  dropping the whole footer with no error (this site's own PDF footer had
  no copyright text at all). Fixed to a single-line string, and switched
  `&copy;` to a literal `©` character - a CSS content string doesn't
  decode HTML entities either.
- Fixed the deploy workflow missing a per-page PDF build step for the new
  Introduction page (its own "Download this page as PDF" link 404'd), and
  that page's leftover PDF link (still the old cover page's, pointing at
  the whole-site PDF) to the same per-page convention every other content
  page already uses.
- No functional (Python package) changes.

## 0.4.0 (2026-07-18)

- New `pdf_double_sided` option: a duplex-printing layout for book/
  handbook-style documents printed and bound on both sides. Verso (left-
  hand) and recto (right-hand) pages mirror their header/footer content
  and page margins (new `pdf_margin_inner`/`pdf_margin_outer`, replacing
  `pdf_margin_left`/`_right` in this mode) via CSS Paged Media's `@page
  :left`/`:right` selectors - chapter title and page number always on the
  outer, fore-edge corner; site name and copyright always on the inner,
  spine-side corner, whichever physical side that is for a given page.
  Every numbered heading now starts its own recto page (`break-before:
  recto`, auto-inserting a blank page as needed - confirmed directly this
  needs no Python-side page-counting logic at all), and a
  `prodockit-table-rotated` landscape page's own rotation direction now
  alternates by its final page position (270 degrees on recto, 90 on
  verso - the spine sits on the opposite physical side either way).
- New `recto_title` front matter key: overrides a page's own running
  header text with a shorter title, from the *next* page onward (the
  heading's own page still shows its full title - confirmed directly this
  is a consequence of CSS `string()`'s "first value on this page wins"
  default policy) - useful for a chapter title too long to fit
  comfortably in the header, with or without `pdf_double_sided`.
- Off by default: a single-sided build is completely unchanged.

## 0.3.1 (2026-07-18)

- Docs: renamed `glossary.md`'s heading to "Acronyms and Glossary" and
  `citations.md`'s to "Citations or References" (and their matching nav
  labels); added a flow diagram to `bibliography.md`'s Requirements
  section (and fixed a real, unrelated gap found along the way - this
  docs site had no Mermaid `custom_fences` config at all, so a plain
  ` ```mermaid ` fence never rendered as a diagram anywhere on the site);
  switched the citation-style example to `harvard-cite-them-right.csl`;
  added an admonition pointing from `prodockit.citations` to
  `prodockit.bibliography`; and noted `prodockit.bibliography`'s own
  independent Pandoc invocation in `prodockit.pdf`'s "Limitations and
  workarounds".
- Docs: updated `README.md` (and so PyPI's own project page description)
  to include `prodockit.tables`/`prodockit.bibliography`, and to mention
  sideways tables/`.web-only`/`.pdf-only` under PDF generation - it had
  gone stale since both extensions shipped in 0.3.0.
- No functional changes.

## 0.3.0 (2026-07-18)

- New `prodockit.bibliography` extension: an alternative to
  `prodockit.citations` for a `.bib`-backed reference list instead of a
  hand-authored one. Define sources in a BibTeX/BibLaTeX `.bib` file, cite
  them with the same `\cite{id}` syntax, and get the resolved citation text
  and a full, auto-generated reference list formatted in any Citation
  Style Language (CSL) style (APA, IEEE, Harvard, ...) via Pandoc's own
  `--citeproc` - confirmed directly against real Pandoc output rather than
  reimplementing citation formatting, and rejected an actual LaTeX/biblatex
  toolchain as a new hard dependency along the way. Makes `pandoc` a
  required dependency for this extension specifically, including for a
  website-only build with no PDF. New `docs/extensions/bibliography.md`
  includes a "References and Bibliography" comparison of this,
  `prodockit.citations`, and what `prodockit-template`/`prodockit-userguide`
  currently do.
- New sideways (90-degree anticlockwise) tables in the PDF: wrap a table
  and its own caption in `<div class="prodockit-table-rotated" markdown="1">`
  to print it on its own landscape-sized page(s), spanning multiple pages
  with a repeated heading row exactly like any other table. Confirmed
  directly that a CSS `transform: rotate()` doesn't work for this (clips
  the table to one page and loses its heading row) - the actual rotation
  is applied afterwards via a `/Rotate` post-process on the finished PDF
  (new `prodockit.pdf.rotate` module, new `pypdf` dependency).
- `.web-only` content is now hidden in every PDF build automatically, via
  `prodockit.pdf.css`'s own always-included stylesheet - no project-side
  CSS needed any more. `.pdf-only` is documented as a one-line, centrally-
  sourced snippet instead (`prodockit` has no way to reach into a
  project's own website stylesheet), in a new "Web-only / PDF-only
  content" section in the PDF generation docs.

## 0.2.0 (2026-07-18)

- New `prodockit.tables` extension: gives a table column a percentage or
  fixed width via a `width` attribute already attachable to a header cell
  with `attr_list` - no new syntax. Column-width distribution beyond what's
  explicitly given is left to CSS's own `table-layout: fixed` algorithm
  rather than computed in Python. Ships with the matching CSS in
  `prodockit.pdf`'s generated stylesheet, and documents the equivalent rule
  a project's own website theme needs (see the new
  [Tables](../extensions/tables.md) docs page).
- New `prodockit pdf --markdown-file`/`-m` option: builds a PDF from a
  single markdown file instead of the whole `nav`, using the same
  `zensical.toml` settings as a full build.
- `prodockit.pdf`'s generated table CSS now draws a full grey 0.5pt grid -
  outer border and internal row *and* column lines (there was previously
  no line between columns at all) - and reads a project's own
  `extra_css` (from `zensical.toml`), so a project-specific `@media print`
  rule (e.g. hiding a website-only "Download PDF" link/button) also
  applies in the PDF.
- `prodockit.citations`: a resolved `\cite{id}` link now always gets
  `class="prodockit-cite-resolved"` (previously no class at all),
  matching `prodockit.refs`/`prodockit.glossary`'s existing convention of a
  stable class for both the resolved and unresolved case.
- Docs: added a "CSS hooks" section to `refs.md`/`citations.md`/
  `glossary.md` (`headings.md` already had one), documenting every class/
  attribute each extension itself emits; replaced the docs site's "edit
  this page" link with "view this page" (a `content.action.view` link to
  the raw source rather than a GitHub edit form); added a whole-site PDF
  download button on the front page and a per-page download link on every
  other page, both built via the new `--markdown-file` option above.
- Fixed `prodockit.__version__` reporting a stale `"0.10.0"` (left over
  from before the `zendoc`→`prodockit` rename) instead of matching this
  package's actual, `pyproject.toml`-declared version.

## 0.1.1 (2026-07-17)

- Docs: reworded the package intro on the docs site and README (dropped
  the `pymdown-extensions` comparison, added a mention of the website
  macros and a one-line "kit for professional documentation" summary) -
  no functional changes.

## 0.10.0 (2026-07-15)

- New `prodockit.zensical_macros`: Jinja variables/macros for Zensical's own
  macros plugin - `{{ word_count }}` (site-wide prose word count, excluding
  the cover page and any page flagged `exclude_from_word_count: true`),
  `{{ repo_url }}` (git-detected repository URL), `{{ site_name }}`, and
  `heading_counter_reset(page)`/`reference_style()`/`acronym_style()`/
  `glossary_style()` macros. Add it alongside a project's own `macros.py`
  via `zensical.toml`'s `modules = ["prodockit.zensical_macros"]` - or use it
  alone if the project has no macros of its own.
- New `prodockit.wordcount`: the generic prose word-count utility
  (`count_words()`/`compute_word_count()`) behind both `prodockit.pdf`'s
  `{WORDCOUNT}`-style cover-page use and `prodockit.zensical_macros`'
  `{{ word_count }}` - previously duplicated independently by each
  downstream project needing both.
- New `prodockit.settings`: `flatten_nav()`, `heading_numbering_enabled()`, and
  `reference_style_values()` - the `project.extra.*` reading shared by
  `prodockit.pdf.config` and `prodockit.zensical_macros`, so the two agree on one
  set of fallback defaults instead of each hand-maintaining its own copy.
  `prodockit.pdf.config.build_pdf_from_zensical_config()` now uses these too
  (previously inlined), and its `pdf_math_dir` setting is now created
  automatically if configured to a directory that doesn't already exist
  (matching the auto-detected default's existing behaviour).

## 0.9.0 (2026-07-15)

- New `prodockit pdf` command: builds a complete PDF with no Python required,
  reading everything - nav, docs directory, fonts, page size, and all
  PDF-specific settings - from the project's own `zensical.toml`, the same
  way `zensical build`/`zensical serve` do. Installing `prodockit` now
  registers a `prodockit` console script (`pip install prodockit` is enough - no
  separate build script to write). See the new `prodockit.pdf.config` module
  (`build_pdf_from_zensical_config()`) for the config-to-`build_pdf()`
  orchestration this wraps: nav-tree flattening, per-page `is_appendix`
  front-matter detection, and auto-detection of a local `mmdc`
  (Mermaid) binary and MathJax `tex2svg` script, so a typical project
  needs no extra configuration beyond what it likely already has.
- `build_pdf()` gained `include_table_of_contents`/`table_of_contents_title`
  parameters (both used automatically by `prodockit pdf`): a generated table
  of contents is now inserted by default, right after a cover page if one
  is marked `is_index=True`, or at the very start otherwise.
- Rewrote the [PDF generation](../pdf.md) docs page around the `prodockit pdf`
  command as the primary, and for most projects only necessary, way to use
  `prodockit.pdf` - `build_pdf()` and the individual pipeline pieces are now
  documented as the advanced, scripting-your-own-pipeline path.

## 0.8.0 (2026-07-15)

- New `prodockit.pdf.build_pdf()`: a one-call convenience wrapper around the
  rest of `prodockit.pdf` - hand it a list of already-rendered pages
  (`prodockit.pdf.Page`) and where to write the PDF, and it fixes up each
  page's HTML, generates the Lua filter and CSS, concatenates everything,
  and runs `pandoc`/WeasyPrint for you. Takes `output_path` (the PDF's own
  destination path) plus font/page-size/margin/header-footer/reference-
  style/numbering/math parameters, all with sensible defaults. Raises the
  new `prodockit.pdf.PdfBuildError` (with the underlying `pandoc` exit code
  and stderr attached) if the build fails, rather than failing silently.
  `prodockit.pdf.html`/`.lua`/`.css`/`.icons`/`.mermaid` remain directly
  importable if you need more control over how the pieces fit together.
- Rewrote the [PDF generation](../pdf.md) docs page around `build_pdf()` as
  the primary documented way to use `prodockit.pdf`, leading with a short,
  practical quick-start example rather than the implementation-level detail
  of how Pandoc/WeasyPrint's own quirks are worked around (that detail is
  still there, now further down, for anyone who wants it).

## 0.7.0 (2026-07-15)

- New `prodockit.pdf`: a Pandoc/WeasyPrint pipeline for building a standalone
  PDF from Zensical-rendered HTML - not a Python-Markdown extension (no
  `markdown.extensions` entry point), a plain function library, since a PDF
  build pipeline isn't a Markdown syntax extension:
    - `prodockit.pdf.html`: `fix_up_page_html()` and link/anchor/image helpers
      - fixes up one page's already-rendered HTML for Pandoc's own reader/
        writer quirks (attribute loss on `<p>`, raw `<svg>` not surviving
        the round trip to WeasyPrint, footnote/caption structural
        mismatches, cross-page link rewriting for a concatenated multi-page
        PDF, and more).
    - `prodockit.pdf.lua`: `build_lua_filter()` - chapter/appendix numbering,
      caption chapter-prefix numbering, tabbed-set reconstruction, and
      MathJax pre-rendering, generated as a parameterized Lua filter.
    - `prodockit.pdf.css`: `build_css()` - the compiled CSS a PDF needs on top
      of a project's own website stylesheet, including WeasyPrint-specific
      page-break tuning for headings, paragraphs, tables, code blocks,
      figures/captions, admonitions, and grid cards.
    - `prodockit.pdf.icons` / `prodockit.pdf.mermaid`: admonition icon resolution
      and Mermaid diagram pre-rendering, as standalone helpers.
  - Fixed a real bug found while writing tests: the iframe→"Watch Video"
    admonition link builder stripped the video id from every single
    conversion (a replace-then-split ordering removed the just-added
    `?v=...` too) - now produces a working YouTube watch link.
  - No formal, versioned public API surface yet (see prodockit-extension#7) -
    import whatever's needed directly, the same informal way as the rest of
    this package.
  - New dependency: `beautifulsoup4` (>= 4.12).
- Broadened the package's own description: prodockit is now framed as a family
  of extensions for Zensical needed for professional and academic
  documentation, rather than "Python-Markdown extensions" specifically -
  `prodockit.pdf` isn't one, and the framing was due to broaden anyway now
  that PDF generation is in scope alongside cross-references/citations/
  glossary.

## 0.6.0 (2026-07-14)

- `prodockit.headings`: new `numbering="continuous"` option (Zensical only) -
  `h1` numbering carries on from wherever the previous nav page left off,
  instead of restarting at 1 on every page. Fixes `\ref{id}` showing the
  wrong number for a heading on a different page (it previously always
  showed that page's own per-document number, not the number actually
  displayed on the page - see zendoc-template#89).
- New `appendix_attr` option (default `is_appendix`): a page whose front
  matter sets this flag is numbered with a letter instead - "A", "A.1",
  "A.1.1" - and doesn't consume a number from the numeric sequence, so
  later pages aren't left with a gap. Letters are assigned sequentially in
  nav order.
- New public `prodockit.headings.prescan(appendix_attr="is_appendix")`
  function: returns the same `(start_counts, appendix_letters)` pre-scan
  `HeadingsExtension` uses internally, for a consuming project's own build
  tooling (e.g. a template macro driving a presentational CSS
  counter-reset) to stay in sync automatically rather than re-deriving the
  same page-order/heading-count logic independently.

## 0.5.1 (2026-07-14)

- `prodockit.glossary`: a resolved `\gls{id}` now always renders with
  `class="prodockit-gls"` (previously it had no class at all), matching
  `prodockit.refs`' always-present base class. The unresolved case now
  renders `class="prodockit-gls prodockit-gls-unresolved"` (previously just
  `prodockit-gls-unresolved`, missing the base class), so a stylesheet has
  one stable hook (`.prodockit-gls`) regardless of resolution state, with
  `.prodockit-gls-unresolved` layered on top only when needed.

## 0.5.0 (2026-07-14)

- New `prodockit.glossary` extension: define a term once via `attr_list` (an
  id plus a `data-term` short display string), then insert it by id from
  anywhere with `\gls{id}`, which resolves to the term's own text, linked
  to its definition - e.g. `\gls{css}` → `CSS`. Unlike `prodockit.citations`'
  `\cite{id}` (which generates new bracketed citation text), `\gls{id}`
  inserts the term's own registered text in place - closer to LaTeX's
  `glossaries` package.
- One shared `GlossaryRegistry` covers both acronym-style and
  glossary-style entries - they're the same kind of thing (an id with a
  short display text), so acronym and glossary pages can reference each
  other, or be referenced from any other page, with no special wiring.
- Supports forward references within a document, an `unresolved` marker
  (`?` by default) for an unknown id, and the same automatic Zensical
  cross-page registry sharing and nav pre-scan (for citing/using a term
  before its defining page has been converted) that `prodockit.citations` got
  in 0.4.0.
- Refactored the nav pre-scan logic (previously private to
  `prodockit.citations`) into a shared, generic
  `prodockit._zensical.preseed_attr_from_nav` helper, since `prodockit.glossary`
  needed the identical scan.

## 0.4.0 (2026-07-14)

Fixes found migrating a real multi-page site's references page to
`prodockit.citations` for real - all discovered by actually building a
real multi-page site, not just single-document tests:

- **Fixed a real correctness bug**: `prodockit.refs`/`prodockit.citations` were
  emitting a bare `#id` fragment for *every* resolved link, including a
  cross-page one - which only works by coincidence in a single concatenated
  PDF document, but 404s on an actual multi-page website (an `#id` fragment
  only navigates within the *current* page). Both now emit a real relative
  link (e.g. `references.md#id`, correctly adjusted for the citing page's
  own directory depth) when the target is on a different page, which
  Zensical already knows how to rewrite into the right clean URL - the
  same way a hand-typed cross-page Markdown link already works.
- New: `prodockit.citations` pre-scans every page in a Zensical build's nav
  for citation definitions before any page is actually converted, so citing
  a source *before* it's defined - the common case, since a references page
  is usually kept at the end of nav as an appendix - resolves correctly in
  a single `zensical build` pass, rather than only working from
  `zensical serve`'s live-reload. New `CitationRegistry.preseed()` method
  backs this; a real registration always supersedes a preseeded stub.
- `RefsExtension` gained a `source` option (mirroring `HeadingsExtension`'s),
  needed for the same-page-vs-cross-page link decision above.
- Fixed the nav pre-scan matching a citation-definition attr_list example
  shown literally inside a fenced code block in documentation - it now
  skips fenced content, the same protection `CitationDefTreeprocessor`
  already gets for free from the real Python-Markdown parser.

## 0.3.0 (2026-07-14)

- New `prodockit.citations` extension: define a source once via `attr_list`
  (an id plus a `data-cite-text` short display string), then cite it by key
  from anywhere with `\cite{id}` (or `\cite{id1,id2,...}` for multiple),
  auto-generating a bracketed, linked citation - `[Skoulikari, 2023]` -
  instead of hand-typing the link and text at every citation site.
- Supports forward references within a document, an `unresolved` marker
  (`?` by default) for an unknown key, and the same automatic Zensical
  cross-page registry sharing (with soft-fail on key collisions) that
  `prodockit.headings`/`prodockit.refs` got in 0.2.0.
- Auto-generating the references page's own listing from structured
  bibliographic data isn't built yet - see the extension's docs for the
  current scope.
- Fixed the `zensical.toml` installation examples in the docs: nested
  `[project.markdown_extensions.prodockit.headings]` tables don't work
  (Zensical only hoists the `pymdownx`/`zensical` namespaces that way) -
  the quoted-key form (`[project.markdown_extensions."prodockit.headings"]`)
  is required.

## 0.2.0 (2026-07-14)

- `prodockit.headings`/`prodockit.refs` now share their registry automatically
  under Zensical, without any explicit `registry`/`source` configuration:
  each extension detects Zensical's per-page rendering context and derives
  a stable `source` from the page's own path, fixing cross-page `\ref{id}`
  references not resolving.
- A heading id collision across two different sources, when detected via
  this automatic Zensical sharing, now logs a warning and keeps the first
  registration instead of raising `DuplicateIdError` - so two unrelated
  pages that happen to share a heading title (e.g. both have an "Overview"
  section) no longer break the build. Explicitly-shared registries (the
  manual multi-page pattern) still raise on a collision, unchanged.
- Fixed an extension-ordering bug: `prodockit.headings` and `prodockit.refs` now
  find and share each other's registry regardless of which order they're
  listed in - previously, only `prodockit.headings`-then-`prodockit.refs` worked
  reliably, and Zensical's own TOML-to-extension-list conversion doesn't
  preserve list order at all.

## 0.1.0 (2026-07-14)

Initial release.

- `prodockit.headings`: heading ids and hierarchical section numbering,
  backed by a shared `IdRegistry`.
- `prodockit.refs`: `\ref{id}` section cross-references, resolving to the
  target's current section number, including forward references within a
  document and across a shared registry.
- Documentation site built with Zensical, published at
  [buckwem.github.io/prodockit-extension](https://buckwem.github.io/prodockit-extension/).
