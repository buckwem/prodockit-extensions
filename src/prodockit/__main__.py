# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""``python -m prodockit``, the same tool as the ``prodockit``/``pdk`` scripts.

Bootstrap runs prodockit commands of its own - ``sync-repo`` when it
repoints a clone, ``init-mathjax`` when it installs MathJax - and looking
those up on ``PATH`` fails whenever the prodockit driving the setup was
launched from a virtual environment that is not itself on ``PATH``
(prodockit-extensions#371). Going through ``sys.executable -m prodockit``
finds the prodockit that is *already running*, whatever ``PATH`` holds.
"""

from prodockit.cli import main

if __name__ == "__main__":  # pragma: no cover - only ever run as a subprocess
    main()
