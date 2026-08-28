---
icon: lucide/info
---

{{ heading_counter_reset(page) }}

# About prodockit

This section is for anyone evaluating or using prodockit who needs to
understand its scope, dependencies, support, release history, or legal terms.

\index{prodockit} is a Python package for professional and academic documentation
built with [Zensical](https://zensical.org/). It adds Markdown extensions,
website macros, PDF generation, output checks, and project-management commands
without requiring a document author to build those pieces independently.

## Understand the foundation

prodockit builds on Python-Markdown, Zensical, and
[PyMdown Extensions](https://facelessuser.github.io/pymdown-extensions/).
PyMdown Blocks is a direct foundation, not merely a compatible syntax:
`prodockit.steps` and `prodockit.tree` are implemented with its Blocks API and
use the same slash-fenced container model as PyMdown's own blocks. Installing
prodockit therefore installs `pymdown-extensions` too.

This relationship lets prodockit add specialised document blocks while
retaining the nesting, configuration, and rendering conventions familiar to
Zensical authors. Start with [Numbered steps](../extensions/steps.md) or
[Directory trees](../extensions/tree.md) to see the shared model in use.

## Know the project family

| Project | Role |
|---|---|
| [prodockit-extensions](https://github.com/buckwem/prodockit-extensions) | The Python package, command-line tools, implementation, tests, and this technical reference |
| [prodockit-template](https://github.com/buckwem/prodockit-template) | The maintained starting project, including annotated GitHub and GitLab publishing automation |
| [prodockit-userguide](https://github.com/buckwem/prodockit-userguide) | The task-based guide for people creating and publishing documents with the template |
/// table-caption | <
    attrs: {id: tab-about-index-know-the-project-family}

Know the project family
///

The template is maintained on GitHub and synchronised to the University of
Surrey's GitLab for student use. Projects created from it use the same
prodockit package documented here.

## Choose where to continue

| Page | Use it for |
|---|---|
| [Get started](../introduction.md) | Install prodockit and build a first local site |
| [Authoring reference](../authoring.md) | Add document features, macros, PDFs, and command-line tools |
| [Publish a document](../publishing.md) | Update and deploy a website and its outputs |
| [Support and compatibility](support.md) | Check maturity, supported versions, platforms, and known constraints |
| [Release notes](changelog.md) | See the implemented capability summary and short, user-relevant upgrade notes |
| [Licence](license.md) | Read the MIT License governing use, modification, and redistribution |
/// table-caption | <
    attrs: {id: tab-about-index-choose-where-to-continue}

Choose where to continue
///

Repository maintainers should use [Maintain prodockit](../project-maintenance.md).
Developers changing the package itself should use
[Contributor internals](../devcons/devcons.md).
