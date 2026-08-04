# Development considerations {: #devcons-introduction }

The rest of these docs cover authoring: the syntax each extension adds and
what it renders to. This section covers everything around that - building a
prodockit site, publishing it, checking what got published, and knowing
where the sharp edges are.

They are grouped together because they share a failure mode. Almost nothing
here breaks loudly. The PDF pipeline shells out to external binaries, reads
undocumented Zensical internals, and resolves cross-page references from a
registry built during the render - and when any of that goes wrong, the
usual result is a build that succeeds and publishes something subtly wrong:
a diagram that reached the PDF as raw source, a reference that resolved to
`??`, a deploy that reported success and was never served. A green build is
weak evidence, which is why these pages spend as much time on what to check
as on what to configure.

In the order you would set them up:

1. **[Continuous integration](continuous-integration.md)** - what the build
   actually needs, working recipes for both GitHub Actions and GitLab CI,
   and the traps that catch almost everyone at least once.
2. **[Repository metadata](repo-metadata.md)** - keeping your repo links,
   brand icon and README badges in step with whichever git remote you
   actually publish from, so forking or mirroring doesn't leave stale ones
   behind.
3. **[Version pinning and drift](pinning-drift.md)** - pinning the versions
   of Zensical, WeasyPrint and the runner image the build renders with, and
   watching for a newer release that would actually change what gets
   published.

Then, once it builds:

4. **[Testing your built site](testing.md)** - pytest fixtures pointing at
   your own built site and PDF, plus ready-made checks for the failure modes
   every prodockit project shares. This is the part that turns "it built"
   into "it built correctly".
5. **[Zensical coupling](zensical-coupling.md)** - every undocumented
   Zensical API prodockit depends on, with call sites and why each is
   needed. Read it before taking a Zensical upgrade, and after one breaks
   something.
6. **[Limitations and workarounds](limitations.md)** - what prodockit does
   not do, what it cannot do, and what it does differently between the
   website and the PDF. Worth reading once before you hit any of it.
