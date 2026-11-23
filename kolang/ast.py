"""kolang の抽象構文木（AST）。

kolang.md の非終端記号に対応するノードを定義する。
区切りトークン（block_begin など）は構文の表層であり、AST には現れない。

コメントは文（Stmt）の `comments` と、プログラムの Block.trailing に持つ。
どちらも比較（==）の対象外なので、コメントが違っても同じプログラムなら等しい。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union


# ---------------------------------------------------------------- 式 <expression>

@dataclass(frozen=True)
class Var:
    """<identifier> 変数参照。"""
    name: str


@dataclass(frozen=True)
class Index:
    """<variable> index_begin <expression> index_end  配列の添字 X[i]。"""
    target: "Variable"
    index: "Expression"


@dataclass(frozen=True)
class Str:
    """<string> 文字列。"""
    value: str


@dataclass(frozen=True)
class Num:
    """<number> 数値。整数なら int、小数なら float。"""
    value: Union[int, float]


@dataclass(frozen=True)
class Bool:
    """<boolean> true / false。"""
    value: bool


@dataclass(frozen=True)
class NoneLit:
    """<none> None。"""


@dataclass(frozen=True)
class ListLit:
    """<list> リスト。"""
    items: tuple["Expression", ...] = ()


@dataclass(frozen=True)
class Call:
    """<funcapp> 関数呼び出し。"""
    func: str
    args: tuple["Expression", ...] = ()


@dataclass(frozen=True)
class Neg:
    """neg_begin <expression> neg_end  符号の反転 -X。-1 は Neg(Num(1))（Num は非負のまま）。"""
    operand: "Expression"


# <variable> は代入・増減の左辺になれる式。
Variable = Union[Var, Index]
Expression = Union[Var, Index, Str, Num, Bool, NoneLit, ListLit, Neg, Call]


# ---------------------------------------------------------------- 条件 <condition>

COMPARE_OPS = ("!=", "<", ">", "<=", ">=", "==")


@dataclass(frozen=True)
class Compare:
    """<condition> 比較。op は COMPARE_OPS のいずれか。"""
    op: str
    left: Expression
    right: Expression

    def __post_init__(self) -> None:
        if self.op not in COMPARE_OPS:
            raise ValueError(f"unknown compare op: {self.op!r}")


# ---------------------------------------------------------------- コメント

@dataclass(frozen=True)
class Comments:
    """文に付くコメント。本文は、コメントの記号を除いて前後の空白を落としたもの。

    leading   文の前の行にあるコメント（1 行 1 件）
    trailing  文と同じ行の後ろにあるコメント。if や def などでは見出しの行。
    """
    leading: tuple[str, ...] = ()
    trailing: Optional[str] = None


NO_COMMENTS = Comments()


# ---------------------------------------------------------------- 文 <statement>

@dataclass(frozen=True)
class Stmt:
    """文の基底。comments は比較の対象外（キーワード専用）。"""
    comments: Comments = field(default=NO_COMMENTS, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True)
class Assign(Stmt):
    """代入 (X = 1)。"""
    target: Variable
    value: Expression


@dataclass(frozen=True)
class Append(Stmt):
    """追加する (X.append(1))。"""
    target: Expression
    value: Expression


@dataclass(frozen=True)
class Inc(Stmt):
    """増やす (X += 1)。"""
    target: Variable


@dataclass(frozen=True)
class Dec(Stmt):
    """減らす (X -= 1)。"""
    target: Variable


@dataclass(frozen=True)
class If(Stmt):
    """<if>。else_body は <else> がなければ None。"""
    cond: Compare
    body: "Block"
    else_body: Union["Block", None] = None


@dataclass(frozen=True)
class Repeat(Stmt):
    """<repeat> n回くり返す。"""
    count: Expression
    body: "Block"


@dataclass(frozen=True)
class Break(Stmt):
    """<break> 抜ける。"""


@dataclass(frozen=True)
class FuncDef(Stmt):
    """<funcdef> 関数定義。"""
    name: str
    params: tuple[str, ...]
    body: "Block"


@dataclass(frozen=True)
class Return(Stmt):
    """<return> 戻り値。"""
    value: Expression


@dataclass(frozen=True)
class CallStmt(Stmt):
    """<funcapp> を文として書いたもの (print(x))。戻り値は捨てる。"""
    call: Call


@dataclass(frozen=True)
class Doctest(Stmt):
    """doctest 風の例 (>>> 式 の次の行に答え)。answer は JSON の値（読み込んだもの）。

    `>>>` と答えの書き方は固定で、シンタックスの JSON では変えられない。
    """
    expr: Expression
    answer: Any


Statement = Union[Assign, Append, Inc, Dec, If, Repeat, Break, FuncDef, Return, CallStmt, Doctest]


# ---------------------------------------------------------------- <block>

@dataclass(frozen=True)
class Block:
    """<block> 文の並び。

    trailing は、最後の文より後ろにあるコメント（プログラム全体の Block だけが持つ）。
    """
    stmts: tuple[Statement, ...] = ()
    trailing: tuple[str, ...] = field(default=(), compare=False, repr=False)


# プログラム全体は <block> として扱う。
Program = Block
