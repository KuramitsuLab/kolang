"""シンタックスごとの書き方の例（kolang --show）。

例は Python 風の短いプログラムで持ち、表示するシンタックスへ変換して見せる。
そのため、JSON を書いた新しいシンタックスでも、同じ形の例がすぐ出る。
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from .regexgen import sample
from .syntax import Syntax, load_syntax
from .unparser import UnparseError, convert

# (見出し, Python 風のソース, コメントの記号が要るか)
EXAMPLES = [
    ("コメント", "# コメント\nx = 1 # 行末のコメント", True),
    ("代入", "x = 1", False),
    ("文字列・真偽値・None", 's = "text"\nb = True\nc = False\nn = None', False),
    ("リスト", "xs = [1, 2, 3]", False),
    ("符号の反転", "x = -1\ny = -xs[0]", False),
    ("配列の添字", "y = xs[0]\nxs[1] = 5", False),
    ("追加する", "xs.append(4)", False),
    ("増やす・減らす", "x += 1\nx -= 1", False),
    ("if / else", "if x < 3:\n    x += 1\nelse:\n    x -= 1", False),
    ("比較", "if a != b:\n    break\nif a < b:\n    break\nif a > b:\n    break\n"
             "if a <= b:\n    break\nif a >= b:\n    break\nif a == b:\n    break", False),
    ("くり返す", "for _ in range(3):\n    x += 1", False),
    ("抜ける", "for _ in range(3):\n    if x == 2:\n        break", False),
    ("関数の定義と呼び出し", "def add(a, b):\n    return a\nr = add(1, 2)\nprint(r)", False),
    ("doctest 風の例（式と、次の行に JSON の答え）", ">>> add(1, 2)\n3\n>>> f([1, \"a\", None])\n[1, \"a\", null]", False),
    ("特殊な名前", "_my var_ = 1", False),
]


def show(syntax: Union[str, Path, Syntax]) -> str:
    """シンタックスの説明と、書き方の例を文字列にして返す。"""
    syn = syntax if isinstance(syntax, Syntax) else load_syntax(syntax)
    has_comment = bool(syn.comment_begin and syn.comment_end)
    lines = [syn.name, ""]

    notes = ["ブロックはインデントで表す" if syn.layout == "indent"
             else "ブロックは記号で囲む（インデントは意味を持たない）"]
    notes.append(f"コメントは {sample(syn.comment_begin)} から" if has_comment else "コメントはない")
    if syn.reserved:
        notes.append("予約語: " + " ".join(sorted(syn.reserved)))
    lines += [f"  {n}" for n in notes] + [""]

    for title, source, needs_comment in EXAMPLES:
        if needs_comment and not has_comment:
            continue
        lines.append(f"■ {title}")
        try:
            text = convert(source, "pylike", syn).rstrip("\n")
        except UnparseError as e:
            text = f"(このシンタックスでは書けません: {str(e).splitlines()[0]})"
        lines += [f"  {line}" if line else "" for line in text.split("\n")]
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
