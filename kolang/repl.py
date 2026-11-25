"""対話モード。`kolang run`（ファイルなし・端末のとき）。

1 行ずつ読み、読めたら実行する（変数・関数は次の入力へ持ち越す）。読めなければ続きの行を待つ
（`... ` のプロンプト）。空行で打ち切り、そのときまだ読めなければ構文エラーを表示する。
複数行の入力は、indent レイアウトでは空行まで待つ（`else` などの続きを書けるように）。
Ctrl-D で終了、Ctrl-C で書きかけを捨てる。
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from .combinators import ParseError
from .parser import parse
from .pyeval import PyEval
from .syntax import Syntax

PROMPT = ">>> "
CONTINUE_PROMPT = "... "


def repl(syntax: Syntax, read: Optional[Callable[[str], str]] = None, stdout=None, stderr=None) -> int:
    """対話モード。read(prompt) は 1 行を返す（EOFError で終了）。既定は input。"""
    read = read or input
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    interp = PyEval(stdout=stdout, syntax=syntax)
    wait_blank = syntax.layout == "indent"          # indent は、空行で複合文の終わりとする
    lines: list = []
    while True:
        try:
            line = read(CONTINUE_PROMPT if lines else PROMPT)
        except EOFError:
            print(file=stdout)
            return 0
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt", file=stderr)
            lines = []
            continue
        if not lines and not line.strip():
            continue
        lines.append(line)
        blank = not line.strip()
        try:
            program = parse("\n".join(lines) + "\n", syntax)
        except ParseError as e:
            if not blank:
                continue                             # 続きの行を待つ
            print(f"SyntaxError: {e}", file=stderr)
            lines = []
            continue
        if len(lines) > 1 and wait_blank and not blank:
            continue
        lines = []
        run_one(interp, program, stderr)


def run_one(interp: PyEval, program, stderr) -> None:
    """1 回分を実行する。エラーは Python と同じ `種類: 本文` で表示し、続行する。"""
    seen = len(interp.doctests)
    try:
        interp.run(program)
    except Exception as e:                           # noqa: BLE001
        kind = "SyntaxError" if isinstance(e, SyntaxError) else type(e).__name__
        print(f"{kind}: {e}", file=stderr)
    for d in interp.doctests[seen:]:
        if not d.ok:
            print(f"doctest failed: got {d.value!r}", file=stderr)
