# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""zendoc: a family of independent Python-Markdown extensions for section
cross-references and bibliography/citation handling, in the spirit of
pymdown-extensions - each is its own extension, enabled separately:

- ``zendoc.headings`` - heading ids and hierarchical section numbers.
- ``zendoc.refs`` - ``\\ref{id}`` section cross-references.

Built for use with Zensical (https://zensical.org/) - enable an extension in
`zensical.toml` the same way as a built-in or pymdownx one. A standard
Python-Markdown extension with no Zensical-specific dependency, so it also
works with MkDocs or any other Python-Markdown-based tool.

See https://buckwem.github.io/zendoc-extension/ for documentation.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
