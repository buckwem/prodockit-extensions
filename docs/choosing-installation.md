---
icon: lucide/signpost
---

{{ heading_counter_reset(page) }}

# Choose your install

Prodockit supports four installation paths. Choose the one that matches the
document and level of automation you have; the paths are alternatives rather
than stages to complete in sequence.

## Choose an installation path

\ref{fig-installation-approaches} asks about each route in section order: build
your first site, upgrade an existing site, build a template site, or perform
the installation manually.

<!-- Adapted from prodockit-userguide. The canonical editable source for this figure is tools/documentation-diagrams/2.1-installation-approaches.drawio. -->
![Decision tree for choosing Build your first site, Upgrade existing site, Build a template site, or Build site manually](assets/diagrams/2.1-installation-approaches.png){ .documentation-diagram }
/// figure-caption
    attrs: {id: fig-installation-approaches}

Choose the Prodockit installation approach
///

The four routes below compare their starting points and results in the same
order as the following sections.

<div class="grid cards installation-route-grid" markdown>

-   :lucide-rocket:{ .lg .middle } __Build or update a site__

    ---

    **Starting point:** an empty directory and no Zensical site.

    Create the Python environment, install Zensical, and prove that its local
    preview and strict build work. Then use Adoption to add Prodockit's
    authoring components, PDF support, and selected renderers without using
    the report template.

    [:octicons-arrow-right-24: Open section 4](getting-started.md){ .md-button .md-button--primary .installation-route-button }

-   :lucide-package-plus:{ .lg .middle } __Upgrade existing site__

    ---

    **Starting point:** an established Zensical site that you want to keep.

    Adoption inspects the project, aligns it with Prodockit's supported
    toolchain, and adds the standard authoring components and styles. It keeps
    the site's content, design decisions, Git history, remotes, editor, and
    publishing workflow rather than turning it into a template project.

    [:octicons-arrow-right-24: Open section 5](adopt.md){ .md-button .md-button--primary .installation-route-button }

-   :lucide-rocket:{ .lg .middle } __Build a template site__

    ---

    **Starting point:** a new computer, no existing site, or a project that
    should use the maintained report template.

    Bootstrap guides and verifies the machine setup, Git host, repository,
    project environment, build tools, and publishing configuration. The
    resulting site starts from `prodockit-template` and can later receive its
    maintained template updates.

    [:octicons-arrow-right-24: Open section 6](devcons/bootstrap.md){ .md-button .md-button--primary .installation-route-button }

-   :lucide-book-open:{ .lg .middle } __Build site manually__

    ---

    **Starting point:** a project whose author wants direct control of every
    installation decision and command.

    Prepare and verify the machine, repository, editor, Python environment,
    Zensical configuration, renderers, website, PDF, and source bundle
    yourself. This manual installation route explains all dependencies but
    does not use Bootstrap or Adoption to orchestrate them.

    [:octicons-arrow-right-24: Open section 7](manual-install.md){ .md-button .md-button--primary .installation-route-button }

</div>

These routes are alternatives, not stages in a longer sequence. Choose only
one. In particular, do not run Bootstrap merely because an adopted or manually
built project later needs PDF support.

Every route starts with [Prepare to install](installation.md). That shared
preparation establishes the supported Python and a setup environment in the
directory holding your repositories. Your chosen route then explains when to
enter or create the project and activate its project-specific environment.
