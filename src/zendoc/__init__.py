# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

from zendoc.extension import ZendocExtension, makeExtension
from zendoc.registry import DuplicateIdError, HeadingRecord, IdRegistry

__version__ = "0.1.0.dev0"

__all__ = [
    "DuplicateIdError",
    "HeadingRecord",
    "IdRegistry",
    "ZendocExtension",
    "makeExtension",
    "__version__",
]
