---
icon: lucide/code-xml
---

# Contributor internals {: #devcons-introduction }

These \index{contributor internals} are for developers contributing code to prodockit or reviewing a
change that touches its internal design. It is not required reading for a
document author or for a maintainer following the operational release
runbook.

The beginner and authoring sections explain how to write with prodockit.
[Publish a document](../publishing.md) is for a document author producing and
deploying a website and PDF. [Maintain prodockit](../project-maintenance.md)
is for maintainers of the prodockit repository reviewing its automation,
pins, tests, and package releases.

These contributor notes explain the implementation behind both audiences:
which Zensical internals the package relies on and which limitations are
deliberate rather than undocumented features.

They are grouped together because they share a failure mode. Almost nothing
here breaks loudly. The PDF pipeline shells out to external binaries, reads
undocumented Zensical internals, and resolves cross-page references from a
registry built during the render - and when any of that goes wrong, the
usual result is a build that succeeds and publishes something subtly wrong:
a diagram that reached the PDF as raw source, a reference that resolved to
`??`, a deploy that reported success and was never served. A green build is
weak evidence, which is why these pages spend as much time on what to check
as on what to configure.

Read these after the public task guides when you need to change the package
itself:

1. **[Development and code map](development.md)** - install an editable
   checkout, run the contributor checks, and find the code responsible for a
   feature.
2. **[Extension integration](extension-internals.md)** - shared registries,
   cross-page pre-scans, bibliography delegation, index passes, and block
   output contracts.
3. **[PDF pipeline and API](pdf-internals.md)** - the render pipeline, Python
   entry points, internal modules, and error boundaries.
4. **[Bootstrap design](bootstrap-internals.md)** - the check, plan, apply,
   recheck model and the ordering constraints behind machine setup.
5. **[Zensical coupling](zensical-coupling.md)** - undocumented Zensical APIs
   prodockit depends on. Read it before taking a Zensical upgrade.
6. **[Implementation limitations](limitations.md)** - known platform,
   extension, PDF, and macro constraints and the reason for each workaround.
