"""カバレッジ: プログラムが使っている構文（AST のノード）と標準ライブラリ関数の回数を数える。

`kolang cov FILE.ko...`。お手本（examples/）が、構文と標準ライブラリを漏れなくカバーしているかを見る。
構文は AST のノードの種類で数える。比較（Compare）は演算子ごとに数える（`Compare(==)`）。
標準ライブラリは、呼び出し（Call）のうち標準の関数のものを、標準名（pylike の名前）で数える。
プログラムが自分で定義した同名の関数は数えない。doctest の式は数えない。
"""

from __future__ import annotations

import dataclasses
from collections import Counter

from . import ast as K
from .stdlib import NAMES as STDLIB_NAMES
from .syntax import Syntax
from .unparser import defined_names

# 数える構文の一覧（0 回のものも表に出すため）。Compare は演算子ごと。
NODE_KINDS: tuple = (
    "Assign", "Append", "Inc", "Dec", "If", "Else", "Repeat", "Break", "FuncDef", "Return", "CallStmt",
    *(f"Compare({op})" for op in K.COMPARE_OPS),
    "Var", "Index", "Str", "Num", "Bool", "NoneLit", "ListLit", "Neg", "Call",
)


def count_program(program: K.Block, syntax: Syntax) -> tuple:
    """（構文の回数, 標準ライブラリの回数）。どちらも Counter。"""
    to_std = {local: std for std, local in syntax.function_names.items()}
    mine = defined_names(program)
    nodes: Counter = Counter()
    stdlib: Counter = Counter()

    def walk(node, bare_call=False) -> None:
        if isinstance(node, tuple):
            for x in node:
                walk(x)
        elif isinstance(node, K.Doctest):
            nodes["Doctest"] += 1                          # 中は数えない
        elif dataclasses.is_dataclass(node) and not isinstance(node, K.Comments):
            if isinstance(node, K.Compare):
                nodes[f"Compare({node.op})"] += 1
            elif isinstance(node, K.If):
                nodes["If"] += 1
                if node.else_body is not None:
                    nodes["Else"] += 1
            elif isinstance(node, K.Call):
                if not bare_call:                          # CallStmt の中の Call は、CallStmt で数えた
                    nodes["Call"] += 1
                if node.func in to_std and node.func not in mine:
                    stdlib[to_std[node.func]] += 1
            elif not isinstance(node, K.Block):
                nodes[type(node).__name__] += 1
            for f in dataclasses.fields(node):
                if f.name != "comments":
                    walk(getattr(node, f.name), bare_call=isinstance(node, K.CallStmt))

    walk(program)
    return nodes, stdlib


def format_table(title: str, counts: Counter, kinds) -> str:
    lines = [title]
    for k in kinds:
        n = counts.get(k, 0)
        lines.append(f"  {k:<16}{n:>6}" + ("" if n else "  ← 未使用"))
    used = sum(1 for k in kinds if counts.get(k, 0))
    lines.append(f"  カバー {used}/{len(kinds)}")
    return "\n".join(lines)


def report(nodes: Counter, stdlib: Counter) -> str:
    return (format_table("構文（AST）", nodes, NODE_KINDS) + "\n\n"
            + format_table("標準ライブラリ", stdlib, STDLIB_NAMES) + "\n")
