"""シンタックスの構造検査。トークンの定義だけを見て、読み書きできなくなる組み合わせを見つける。

カスケード（ja:lisplike(if) など）で、別々のシンタックスの記号を混ぜたときに起きる衝突が主な対象。
スニペットを出力 → パースする検査（snippet.failures）より速く、原因を名指しできる。
見つかった問題は文章のリスト（空なら問題なし）で返す。
"""

from __future__ import annotations

import re

from .regexgen import sample
from .syntax import Syntax

# 本体（block）を持つ形。X_end で閉じる。
BLOCK_FORMS = ("if", "else", "repeat", "def")


def _empty_ok(pattern: str) -> bool:
    return re.fullmatch(pattern, "") is not None


def problems(syn: Syntax) -> list:
    out: list = []
    tokens = syn.tokens

    # 1. indent では、ブロックのあとに付くトークンは空でなければならない（インデントが閉じを表すので）。
    if syn.layout == "indent":
        for form in BLOCK_FORMS:
            name = f"{form}_end"
            if name in tokens and not _empty_ok(tokens[name]):
                out.append(f"layout が indent なのに {name} が空でない（{tokens[name]!r}）。"
                           f"indent のときは、{'・'.join(f'{f}_end' for f in BLOCK_FORMS)} を空にする")

    # 2. none で block_end が空だと、本体はどこまでも続く。閉じ（X_end）が空だと、次の文が本体に入ってしまう。
    if syn.layout == "none" and "block_end" in tokens and _empty_ok(tokens["block_end"]):
        for form in ("if", "repeat", "def"):
            name = f"{form}_end"
            if name in tokens and _empty_ok(tokens[name]):
                out.append(f"block_end が空なのに {name} も空で、{form} の本体の終わりが決まらない"
                           f"（次の文が本体に入る）。{name} に閉じの記号が要る")

    # 3. コメントの記号と同じ文字列に、ほかのトークンがマッチする（コメントの始まりと区別できない）。
    if syn.comment_begin:
        try:
            head = sample(syn.comment_begin)
        except ValueError:
            head = ""
        for name, pattern in tokens.items():
            if name.startswith("comment_") or pattern.startswith("\x01") or not head:
                continue
            m = re.match(pattern, head)
            if m and m.end() > 0:
                out.append(f"コメントの記号 {head!r} に {name}（{pattern!r}）もマッチする")

    # 4. 名前（letters）が、語の区切りのない記号（`--` など）を飲み込む。
    letters = syn.lexical.get("letters")
    if letters:
        seen = set()
        for name, pattern in tokens.items():
            try:
                text = sample(pattern)
            except ValueError:
                continue
            # `else` のように名前として始まるトークンは、語の区切りの規則で区別されるので対象外
            if not text or text in seen or pattern.startswith("\x01") or re.match(letters, text):
                continue
            seen.add(text)
            if re.fullmatch(letters, "x" + text):
                out.append(f"名前（letters）が {name} の {text!r} を飲み込む（x{text} が 1 つの名前になる）")
    return out
