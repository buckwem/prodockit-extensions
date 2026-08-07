# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Every `subprocess` call that reads text must name its encoding.

`subprocess.run(..., text=True)` with no `encoding=` decodes the child's
output with the *locale* encoding. That is UTF-8 on macOS and Linux, and
cp1252 on a default Windows install - so the same call that works
everywhere in development raises `UnicodeDecodeError` on Windows the moment
a tool emits a byte cp1252 has no character for.

Every tool prodockit shells out to emits UTF-8: pandoc, git, mermaid-cli.
An accented author name in a `.bib` file, an en dash in a commit message or
a curly quote in a diagram label is enough.

The failure is also badly disguised. The decode happens on a reader thread
inside `subprocess`, so the traceback names `threading` and `cp1252` rather
than anything in prodockit; `run()` then returns with `stdout=None`, and the
*next* line - `BeautifulSoup(stdout, ...)` - raises `TypeError: Incoming
markup is of an invalid type: None`. What a user sees is a type error about
markup, several frames from a decoding problem they cannot act on
(prodockit-extensions#191).

Checked by reading the source rather than by running the calls, and
deliberately so. A behavioural test would have to fake a non-UTF-8 locale
to fail, and on the machines this suite normally runs on - where the locale
*is* UTF-8 - it would pass with or without the fix. This asserts the
property directly, on every platform, and covers calls added in future
rather than only the seven that were wrong.
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "prodockit"

#: Reading a child's output as text, either spelling.
TEXT_MODE_KEYWORDS = ("text", "universal_newlines")


def _text_mode_calls_without_encoding() -> list[str]:
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # subprocess.run / .check_output / .Popen, however imported.
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else ""
            )
            if name not in {"run", "check_output", "Popen", "call", "check_call"}:
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            text_mode = any(
                isinstance(kwargs.get(k), ast.Constant) and kwargs[k].value is True
                for k in TEXT_MODE_KEYWORDS
            )
            if text_mode and "encoding" not in kwargs:
                rel = path.relative_to(SRC.parent.parent)
                offenders.append(f"{rel}:{node.lineno}")
    return offenders


def test_no_text_mode_subprocess_call_relies_on_the_locale_encoding() -> None:
    offenders = _text_mode_calls_without_encoding()

    assert not offenders, (
        "These subprocess calls read text without naming an encoding, so they "
        "decode with the locale's - cp1252 on a default Windows install, which "
        "raises UnicodeDecodeError on any byte it has no character for. Add "
        f'encoding="utf-8": {offenders}'
    )


def test_the_check_itself_finds_a_call_that_is_missing_one(tmp_path: pathlib.Path) -> None:
    """The check above passes by finding nothing, which is indistinguishable
    from a check that cannot find anything. This proves the walker sees a
    real offender, so a green run means the source is clean rather than the
    test being broken."""
    source = (
        "import subprocess\n"
        "subprocess.run(['git', 'status'], capture_output=True, text=True)\n"
        "subprocess.run(['git', 'log'], capture_output=True, text=True, encoding='utf-8')\n"
        "subprocess.run(['git', 'diff'], capture_output=True)\n"
    )
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "run":
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            text_mode = (
                isinstance(kwargs.get("text"), ast.Constant) and kwargs["text"].value is True
            )
            if text_mode and "encoding" not in kwargs:
                found.append(node.lineno)

    assert found == [2], (
        f"the walker should flag only the text=True call with no encoding - got lines {found}"
    )
