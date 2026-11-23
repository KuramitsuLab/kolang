"""Python 互換の評価器（Visitor パターン）。

pylike.json で書いたプログラムが、Python で実行したときと同じ結果になる。
値は Python のオブジェクトそのもの（int / float / str / bool / None / list）で、
演算は Python の演算に任せる。だから、エラーの種類とメッセージも Python と同じになる。

セマンティクスを調整するには、PyEval を継承して、次のメソッドを上書きする。

    visit_XXX       AST ノードごとの評価（XXX は ast.py のクラス名）
    lookup / bind   変数の参照と束縛（スコープの規則）
    compare         比較
    truth           条件の真偽
    count_of        くり返しの回数
    call            関数呼び出し
    make_builtins   標準ライブラリ関数（stdlib.py の表を、シンタックスで決めた名前で並べる）

使い方:

    from kolang.pyeval import run
    run("x = 1\\nprint(add(x, 1))\\n")         # pylike で書いたもの。print や add は標準ライブラリ関数
    python3 -m kolang.pyeval prog.py [-f pylike]

doctest 風の例（`>>> 式` の次の行に JSON の答え）は、実行して照合し、結果を interp.doctests に残す。
合わなくても実行は続ける（Python の doctest と同じ）。
"""

from __future__ import annotations

import json
import operator
import sys
from typing import Any, Callable, Optional

from . import ast as K
from .stdlib import local_names, make_stdlib
from .syntax import Syntax, load_syntax

COMPARE = {
    "==": operator.eq, "!=": operator.ne,
    "<": operator.lt, ">": operator.gt, "<=": operator.le, ">=": operator.ge,
}


# ---------------------------------------------------------------- Visitor の土台

class Visitor:
    """ノードのクラス名で visit_XXX に振り分ける。"""

    def visit(self, node: Any) -> Any:
        method = getattr(self, f"visit_{type(node).__name__}", None)
        if method is None:
            return self.generic_visit(node)
        return method(node)

    def generic_visit(self, node: Any) -> Any:
        raise NotImplementedError(f"{type(self).__name__} cannot visit {type(node).__name__}")


# ---------------------------------------------------------------- 静的な検査

class PySyntaxError(SyntaxError):
    """Python なら、実行する前にコンパイルで失敗するもの。"""


def assigned_names(body: K.Block) -> set[str]:
    """関数の中で束縛される名前（Python では、これが関数のローカル変数になる）。

    代入・増減の左辺の変数、くり返しの `_`、入れ子の関数の名前。入れ子の関数の中身は見ない。
    """
    names: set[str] = set()

    def walk(block: K.Block) -> None:
        for s in block.stmts:
            if isinstance(s, (K.Assign, K.Inc, K.Dec)) and isinstance(s.target, K.Var):
                names.add(s.target.name)
            elif isinstance(s, K.FuncDef):
                names.add(s.name)
            elif isinstance(s, K.Repeat):
                names.add("_")
                walk(s.body)
            elif isinstance(s, K.If):
                walk(s.body)
                if s.else_body is not None:
                    walk(s.else_body)

    walk(body)
    return names


class Checker(Visitor):
    """`break` がくり返しの外、`return` が関数の外にないか。Python はコンパイル時に弾く。"""

    def check(self, program: K.Block) -> None:
        self.block(program, loop=False, func=False)

    def block(self, b: K.Block, loop: bool, func: bool) -> None:
        for s in b.stmts:
            self.statement(s, loop, func)

    def statement(self, s: Any, loop: bool, func: bool) -> None:
        if isinstance(s, K.Break) and not loop:
            raise PySyntaxError("'break' outside loop")
        if isinstance(s, K.Return) and not func:
            raise PySyntaxError("'return' outside function")
        if isinstance(s, K.If):
            self.block(s.body, loop, func)
            if s.else_body is not None:
                self.block(s.else_body, loop, func)
        elif isinstance(s, K.Repeat):
            self.block(s.body, True, func)
        elif isinstance(s, K.FuncDef):
            self.block(s.body, False, True)     # 関数の中では、外のくり返しは効かない


# ---------------------------------------------------------------- スコープと関数

class Scope:
    """変数の置き場。assigned は関数のローカル変数の名前（モジュールでは None）。"""

    def __init__(self, parent: Optional["Scope"] = None, assigned: Optional[frozenset] = None):
        self.vars: dict[str, Any] = {}
        self.parent = parent
        self.assigned = assigned


class Function:
    """kolang の関数（クロージャ）。Python の関数と同じく、呼ぶたびに新しいスコープを作る。"""

    def __init__(self, interp: "PyEval", node: K.FuncDef, scope: Scope):
        self.interp, self.node, self.scope = interp, node, scope
        self.assigned = frozenset(assigned_names(node.body)) | frozenset(node.params)
        self.__name__ = node.name

    def __call__(self, *args: Any) -> Any:
        params = self.node.params
        if len(args) != len(params):
            raise TypeError(self.arity_message(len(args)))
        local = Scope(self.scope, self.assigned)
        local.vars.update(zip(params, args))
        return self.interp.run_body(self.node.body, local)

    def arity_message(self, given: int) -> str:
        params, name = self.node.params, self.node.name
        if given < len(params):
            missing = params[given:]
            names = [f"'{p}'" for p in missing]
            if len(names) > 1:
                names = [", ".join(names[:-1]) + (", " if len(names) > 2 else " ") + "and " + names[-1]]
            s = "" if len(missing) == 1 else "s"
            return f"{name}() missing {len(missing)} required positional argument{s}: {names[0]}"
        n = len(params)
        takes = f"{n} positional argument" + ("" if n == 1 else "s")
        return f"{name}() takes {takes} but {given} {'was' if given == 1 else 'were'} given"

    def __repr__(self) -> str:
        return f"<function {self.node.name}>"


class DoctestResult:
    """doctest 風の例 1 件の結果。"""

    def __init__(self, node: K.Doctest, value: Any, ok: bool):
        self.node, self.value, self.ok = node, value, ok

    def __repr__(self) -> str:
        return f"<doctest {'ok' if self.ok else 'FAILED'}: got {self.value!r}, expected {self.node.answer!r}>"


class BreakSignal(Exception):
    pass


class ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


# ---------------------------------------------------------------- 評価器

class PyEval(Visitor):
    def __init__(self, stdout=None, max_depth: int = 1000, syntax: Optional[Syntax] = None):
        self.stdout = stdout if stdout is not None else sys.stdout
        self.max_depth = max_depth          # Python の既定の再帰の深さに合わせる
        # 標準ライブラリ関数の名前は、シンタックスの JSON（stdlib）で決まる。
        self.function_names = (syntax.function_names if syntax else local_names({}))
        self.depth = 0
        self.doctests: list = []             # DoctestResult（実行した順）
        self.builtins = self.make_builtins()
        self.globals = Scope()
        self.scope = self.globals

    # ---- 標準ライブラリ関数 -------------------------------------------------------
    def make_builtins(self) -> dict[str, Callable]:
        """名前 → 関数。名前は、このシンタックスでの名前（標準名ではない）。"""
        return {self.function_names[std]: f for std, f in make_stdlib(self.stdout).items()}

    # ---- 実行 -------------------------------------------------------------------
    def run(self, program: K.Block) -> None:
        Checker().check(program)
        old = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old, self.max_depth * 40))
        try:
            self.visit_Block(program)
        finally:
            sys.setrecursionlimit(old)

    def run_body(self, body: K.Block, scope: Scope) -> Any:
        """関数の本体を、新しいスコープで実行して、戻り値を返す（return がなければ None）。"""
        self.depth += 1
        if self.depth > self.max_depth:
            self.depth -= 1
            raise RecursionError("maximum recursion depth exceeded")
        saved, self.scope = self.scope, scope
        try:
            self.visit_Block(body)
            return None
        except ReturnSignal as r:
            return r.value
        finally:
            self.scope = saved
            self.depth -= 1

    # ---- 変数 -------------------------------------------------------------------
    def lookup(self, name: str) -> Any:
        scope, first = self.scope, True
        while scope is not None:
            if name in scope.vars:
                return scope.vars[name]
            if scope.assigned is not None and name in scope.assigned:
                if first:
                    raise UnboundLocalError(
                        f"cannot access local variable '{name}' where it is not associated with a value")
                raise NameError(
                    f"cannot access free variable '{name}' where it is not associated with a value"
                    " in enclosing scope")
            scope, first = scope.parent, False
        if name in self.builtins:
            return self.builtins[name]
        raise NameError(f"name '{name}' is not defined")

    def bind(self, name: str, value: Any) -> None:
        """名前への代入。Python と同じく、いつも今のスコープ（ローカル）に束縛する。"""
        self.scope.vars[name] = value

    # ---- 意味の核（調整しやすいように分けてある）----------------------------------
    def compare(self, op: str, left: Any, right: Any) -> Any:
        return COMPARE[op](left, right)

    def truth(self, value: Any) -> bool:
        return bool(value)

    def count_of(self, value: Any) -> range:
        """`n回くり返す` は、Python の `for _ in range(n)` と同じ。"""
        return range(value)

    def answer_matches(self, value: Any, answer: Any) -> bool:
        """doctest 風の例の答え（JSON の値）と、式の値が合うか。型まで厳密に比べる（1 と true と 1.0 は別）。"""
        if isinstance(answer, bool) or isinstance(value, bool):
            return type(value) is type(answer) and value == answer
        if isinstance(answer, list):
            return (type(value) is list and len(value) == len(answer)
                    and all(self.answer_matches(v, a) for v, a in zip(value, answer)))
        return type(value) is type(answer) and value == answer

    def call(self, func: Any, args: list) -> Any:
        return func(*args)

    # ---- 文 ---------------------------------------------------------------------
    def visit_Block(self, b: K.Block) -> None:
        for s in b.stmts:
            self.visit(s)

    def visit_Assign(self, s: K.Assign) -> None:
        value = self.visit(s.value)                  # Python は、右辺 → 左辺の順
        self.store(s.target, value)

    def visit_Append(self, s: K.Append) -> None:
        method = getattr(self.visit(s.target), "append")   # x.append(v): 属性 → 引数の順
        method(self.visit(s.value))

    def visit_Inc(self, s: K.Inc) -> None:
        self.augment(s.target, 1)

    def visit_Dec(self, s: K.Dec) -> None:
        self.augment(s.target, -1)

    def visit_If(self, s: K.If) -> None:
        if self.truth(self.visit(s.cond)):
            self.visit_Block(s.body)
        elif s.else_body is not None:
            self.visit_Block(s.else_body)

    def visit_Repeat(self, s: K.Repeat) -> None:
        for i in self.count_of(self.visit(s.count)):
            self.bind("_", i)                        # Python の `for _ in range(n)` は、_ に束縛する
            try:
                self.visit_Block(s.body)
            except BreakSignal:
                break

    def visit_Break(self, s: K.Break) -> None:
        raise BreakSignal()

    def visit_FuncDef(self, s: K.FuncDef) -> None:
        self.bind(s.name, Function(self, s, self.scope))

    def visit_Return(self, s: K.Return) -> None:
        raise ReturnSignal(self.visit(s.value))

    def visit_Doctest(self, s: K.Doctest) -> None:
        value = self.visit(s.expr)
        ok = self.answer_matches(value, s.answer)
        self.doctests.append(DoctestResult(s, value, ok))

    def visit_CallStmt(self, s: K.CallStmt) -> None:
        self.visit(s.call)                           # 戻り値は捨てる

    # ---- 代入先 -----------------------------------------------------------------
    def store(self, target: K.Variable, value: Any) -> None:
        if isinstance(target, K.Var):
            self.bind(target.name, value)
        else:                                        # x[i] = v: 対象 → 添字の順
            container = self.visit(target.target)
            container[self.visit(target.index)] = value

    def augment(self, target: K.Variable, delta: int) -> None:
        """x += 1 / x -= 1。x[i] の対象と添字は 1 度だけ評価する。"""
        if isinstance(target, K.Var):
            self.bind(target.name, self.lookup(target.name) + delta)
        else:
            container = self.visit(target.target)
            i = self.visit(target.index)
            container[i] = container[i] + delta

    # ---- 条件・式 -----------------------------------------------------------------
    def visit_Compare(self, c: K.Compare) -> Any:
        return self.compare(c.op, self.visit(c.left), self.visit(c.right))

    def visit_Var(self, e: K.Var) -> Any:
        return self.lookup(e.name)

    def visit_Index(self, e: K.Index) -> Any:
        target = self.visit(e.target)
        return target[self.visit(e.index)]

    def visit_Str(self, e: K.Str) -> str:
        return e.value

    def visit_Num(self, e: K.Num) -> Any:
        return e.value

    def visit_Bool(self, e: K.Bool) -> bool:
        return e.value

    def visit_NoneLit(self, e: K.NoneLit) -> None:
        return None

    def visit_ListLit(self, e: K.ListLit) -> list:
        return [self.visit(x) for x in e.items]

    def visit_Neg(self, e: K.Neg) -> Any:
        return -self.visit(e.operand)                # Python の単項マイナス

    def visit_Call(self, e: K.Call) -> Any:
        func = self.lookup(e.func)                   # 関数 → 引数の順
        return self.call(func, [self.visit(a) for a in e.args])


# ---------------------------------------------------------------- 入口

def run(source: str, syntax: Any = "pylike", **options) -> PyEval:
    """ソースを読んで実行する。実行後の評価器を返す（.globals.vars で変数を見られる）。"""
    from .parser import parse
    syn = syntax if isinstance(syntax, Syntax) else load_syntax(syntax)
    interp = PyEval(syntax=syn, **options)
    interp.run(parse(source, syn))
    return interp


def execute(program: K.Block, stdout=None, stderr=None, syntax: Optional[Syntax] = None,
            then: Optional[K.Block] = None) -> int:
    """プログラムを実行して、終了コードを返す（0: 成功、1: 実行時エラーか doctest の不一致）。

    実行時エラーは、Python と同じ `種類: 本文` の形で stderr に出す。
    doctest 風の例があれば、外れたものと件数を stderr に出す。
    `then` は、プログラムが成功したあとに、同じ評価器（同じ変数・関数）で続けて実行する（.doctest）。
    """
    stderr = stderr if stderr is not None else sys.stderr
    interp = PyEval(stdout=stdout, syntax=syntax)
    code = 0
    try:
        interp.run(program)
        if then is not None:
            interp.run(then)
    except Exception as e:                           # noqa: BLE001  Python と同じく、種類と本文を出す
        kind = "SyntaxError" if isinstance(e, SyntaxError) else type(e).__name__
        print(f"{kind}: {e}", file=stderr)
        code = 1
    failed = [(n, d) for n, d in enumerate(interp.doctests, 1) if not d.ok]
    for n, d in failed:
        print(f"doctest #{n} failed: expected {json.dumps(d.node.answer, ensure_ascii=False)}, "
              f"got {d.value!r}", file=stderr)
    if interp.doctests:
        print(f"doctest: {len(interp.doctests) - len(failed)} passed, {len(failed)} failed", file=stderr)
    return 1 if failed else code


def main(argv: Optional[list] = None) -> int:
    import argparse
    from .parser import parse
    ap = argparse.ArgumentParser(prog="python3 -m kolang.pyeval", description="kolang の Python 互換の評価器")
    ap.add_argument("file", nargs="?", help="プログラム（省略すると標準入力）")
    ap.add_argument("-f", "--from", dest="syntax", default="pylike", help="シンタックス（既定: pylike）")
    args = ap.parse_args(argv)
    from .cli import read_source
    source = read_source(args.file)
    syn = load_syntax(args.syntax)
    return execute(parse(source, syn), syntax=syn)


if __name__ == "__main__":
    sys.exit(main())
