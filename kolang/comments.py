"""コメントを AST の文に付ける（パーサの後処理）と、取り出す。

解析中に集めたもの:
  ctx.comments  {位置: 本文}  空白として読み飛ばしたコメント
  ctx.starts    {id(ノード): (開始位置, ノード)}  文の開始位置

コメントの付け方（位置は変換後のテキストのもの）:
  同じ行で、すでに始まっている文があれば   → その文の trailing
  それ以外は、次に始まる文があれば          → その文の leading
  次の文がなければ                         → プログラムの trailing（Block.trailing）

else の行のコメントなど、見出しをもたない行のコメントは、次の文の leading になる。
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import replace
from typing import Iterator

from . import ast as K
from .combinators import Context


def child_blocks(stmt: K.Stmt) -> list:
    if isinstance(stmt, K.If):
        return [stmt.body] + ([stmt.else_body] if stmt.else_body is not None else [])
    if isinstance(stmt, (K.Repeat, K.FuncDef)):
        return [stmt.body]
    return []


def walk(block: K.Block) -> Iterator[K.Stmt]:
    """ブロック内のすべての文を、出てくる順に返す。"""
    for stmt in block.stmts:
        yield stmt
        for child in child_blocks(stmt):
            yield from walk(child)


def attach_comments(program: K.Block, ctx: Context) -> K.Block:
    if not ctx.comments:
        return program
    ordered = sorted(((ctx.starts[id(s)][0], i, s) for i, s in enumerate(walk(program))),
                     key=lambda t: t[:2])
    starts = [t[0] for t in ordered]
    stmts = [t[2] for t in ordered]
    text = ctx.text

    leading: dict = {}
    trailing: dict = {}
    tail: list = []
    for pos in sorted(ctx.comments):
        body = ctx.comments[pos]
        i = bisect_left(starts, pos) - 1                 # pos より前に始まった最後の文
        own_line = text[text.rfind("\n", 0, pos) + 1:pos].strip() == ""
        if not own_line and i >= 0 and "\n" not in text[starts[i]:pos]:
            key = id(stmts[i])
            trailing[key] = f"{trailing[key]} {body}" if key in trailing else body
            continue
        j = bisect_right(starts, pos)                    # pos より後に始まる最初の文
        if j < len(stmts):
            leading.setdefault(id(stmts[j]), []).append(body)
        else:
            tail.append(body)

    def rebuild_block(block: K.Block) -> K.Block:
        return replace(block, stmts=tuple(rebuild(s) for s in block.stmts))

    def rebuild(stmt: K.Stmt) -> K.Stmt:
        changes: dict = {}
        if isinstance(stmt, K.If):
            changes["body"] = rebuild_block(stmt.body)
            if stmt.else_body is not None:
                changes["else_body"] = rebuild_block(stmt.else_body)
        elif isinstance(stmt, (K.Repeat, K.FuncDef)):
            changes["body"] = rebuild_block(stmt.body)
        lead, trail = leading.get(id(stmt)), trailing.get(id(stmt))
        if lead or trail is not None:
            changes["comments"] = K.Comments(tuple(lead or ()), trail)
        return replace(stmt, **changes) if changes else stmt

    return replace(rebuild_block(program), trailing=tuple(tail))


def collect_comments(program: K.Block) -> list:
    """[(leading, trailing), ...] を文の出てくる順に、最後にプログラムの trailing を返す。"""
    return [(s.comments.leading, s.comments.trailing) for s in walk(program)] + [program.trailing]
