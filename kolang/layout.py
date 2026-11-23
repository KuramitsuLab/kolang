"""インデントを仮想トークンに置き換える前処理（layout が "indent" のとき）。

物理行ごとに、直前の行との関係で次の文字列を挟む。いずれも先頭に "\\n" が付く。

    深くなった   INDENT                      （block_begin）
    同じ         NEWLINE                     （block_sep）
    浅くなった   NEWLINE、そのあと 1 段ごとに DEDENT NEWLINE   （block_end, block_sep）
                 ただし最後の NEWLINE は、行頭が continuation（else など）なら入れない
    入力の終わり NEWLINE、残りの段ごとに DEDENT NEWLINE

ただし、doctest 風の例（>>> で始まる行）の次の行は答えなので、仮想トークンを挟まず、前の行の続きにする。

こうして文は常に block_sep で終わり、ブロックは block_begin ... block_end で囲まれる。
"""

from __future__ import annotations

import re
from bisect import bisect_right

from .combinators import ParseError
from .syntax import DEDENT, DOCTEST_PROMPT, INDENT, NEWLINE, Syntax


class Layout:
    """変換後のテキストと、その位置から元の行・桁を引く表。"""

    def __init__(self, text: str, entries: list, lines: list):
        self.text = text
        self._entries = entries or [(0, 1, 0)]   # (変換後の行頭オフセット, 元の行番号, インデント幅)
        self._offsets = [e[0] for e in self._entries]
        self._lines = lines

    def locate(self, offset: int) -> tuple:
        i = max(bisect_right(self._offsets, offset) - 1, 0)
        start, lineno, indent = self._entries[i]
        col = indent + max(offset - start, 0) + 1
        line = self._lines[lineno - 1] if lineno - 1 < len(self._lines) else ""
        return lineno, col, line


def apply_layout(source: str, syn: Syntax) -> Layout:
    lines = source.splitlines()

    if syn.layout != "indent":
        entries, offset = [], 0
        for n, piece in enumerate(source.splitlines(keepends=True), 1):
            entries.append((offset, n, 0))
            offset += len(piece)
        return Layout(source, entries, lines)

    blank = re.compile(f"(?:{syn.skip_pattern})*")   # 空白・コメントだけ（改行は skip_pattern が読む）
    continuation = re.compile(syn.continuation) if syn.continuation else None
    out: list = []
    entries: list = []
    stack = [0]
    length = 0
    started = False

    def put(s: str) -> None:
        nonlocal length
        out.append(s)
        length += len(s)

    answer_next = False
    for lineno, raw in enumerate(lines, 1):
        body = raw.lstrip(" \t")
        if answer_next:                    # >>> の次の行は答え（JSON）。仮想トークンなしで、そのまま置く
            answer_next = False
            put("\n")
            entries.append((length, lineno, len(raw) - len(body)))
            put(body)
            continue
        if not body.strip():               # 空行は無視
            continue
        indent = len(raw[: len(raw) - len(body)].expandtabs(4))
        if blank.fullmatch(body + "\n"):   # コメントだけの行（コメントは行内で閉じる前提）
            # インデントの計算には加えず、空白として本文にそのまま残す（コメントを拾うため）。
            put("\n")
            entries.append((length, lineno, indent))
            put(body)
            put("\n")
            continue

        if not started:
            if indent:
                raise ParseError("unexpected indent", lineno, indent + 1)
            started = True
        else:
            put("\n")
            if indent > stack[-1]:
                put(INDENT)
                stack.append(indent)
            else:
                put(NEWLINE)
                popped = 0
                while indent < stack[-1]:
                    stack.pop()
                    popped += 1
                if indent != stack[-1]:
                    raise ParseError("inconsistent dedent", lineno, indent + 1)
                for i in range(popped):
                    put(DEDENT)
                    last = i == popped - 1
                    if not (last and continuation and continuation.match(body)):
                        put(NEWLINE)

        entries.append((length, lineno, indent))
        put(body)
        answer_next = body.startswith(DOCTEST_PROMPT)

    if started:
        put("\n" + NEWLINE)
        for _ in range(len(stack) - 1):
            put(DEDENT)
            put(NEWLINE)
    return Layout("".join(out), entries, lines)
