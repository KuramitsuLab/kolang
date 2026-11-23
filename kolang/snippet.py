"""シンタックスの組み合わせ（カスケード）を検査するための、AST のスニペット。

構文要素ごとに 1 つ以上。入れ子や、区切りが続く形など、衝突しやすいものを含める。
各スニペットは Block で、`SNIPPETS[名前]` から取れる。
これを出力 → パースして、元の AST に戻れば、そのシンタックスで衝突していない。
名前は x y z f g a b（ja でも使える英字）。負の数・空のブロックは出力できないので使わない。
"""

from __future__ import annotations

from . import ast as K

x, y, z = K.Var("x"), K.Var("y"), K.Var("z")
one, two = K.Num(1), K.Num(2)


def B(*stmts):
    return K.Block(tuple(stmts))


# 構文要素ごとに 1 つ以上。入れ子・連続した区切りなど、衝突しやすい形を含める。
SNIPPETS = {
    "assign": B(K.Assign(x, one)),
    "literals": B(K.Assign(x, K.ListLit((K.Bool(True), K.Bool(False), K.NoneLit(), K.Num(1.5), K.Str("a"))))),
    "string_quotes": B(K.Assign(x, K.Str('a"b\\c\n'))),
    "string_spaces": B(K.Assign(x, K.Str("a b  c"))),
    "empty_list": B(K.Assign(x, K.ListLit())),
    "nested_list": B(K.Assign(x, K.ListLit((K.ListLit((one,)), K.ListLit(()), two)))),
    "index": B(K.Assign(K.Index(K.Index(y, one), x), K.Index(z, two))),
    "neg": B(K.Assign(x, K.Neg(one)), K.Assign(y, K.Neg(K.Neg(K.Index(z, two)))),
             K.Assign(x, K.ListLit((K.Neg(K.Num(1.5)), K.Neg(K.Call("f", (K.Neg(x),)))))),
             K.If(K.Compare("<", K.Neg(x), K.Neg(one)), B(K.Inc(x)))),
    # ---- 配列（添字・リスト）と、ほかの構文の組み合わせ
    "index_assign_call": B(K.Assign(K.Index(x, one), K.Call("f", (y,))),
                           K.Assign(K.Index(K.Index(x, y), K.Index(z, one)), K.ListLit((one, two)))),
    "index_in_args": B(K.CallStmt(K.Call("f", (K.Index(x, one), K.Call("g", (K.Index(y, two),)), K.Index(K.Index(z, x), y))))),
    "index_by_call": B(K.Assign(x, K.Index(y, K.Call("f", (one,)))),
                       K.Assign(K.Index(x, K.Call("g", (K.Index(y, one), z))), one)),
    "index_by_call": B(K.Assign(x, K.Index(y, K.Call("f", (z,)))), K.Assign(K.Index(x, K.Call("f", (one, two))), one)),
    "index_by_neg": B(K.Assign(x, K.Index(y, K.Neg(one))), K.Assign(K.Index(x, K.Neg(y)), K.Neg(K.Index(z, one)))),
    "index_in_list": B(K.Assign(x, K.ListLit((K.Index(y, one), K.ListLit((K.Index(z, two),)), K.Call("f", (x,)))))),
    "list_in_args": B(K.CallStmt(K.Call("f", (K.ListLit((one, two)), K.ListLit(()), K.ListLit((K.ListLit((x,)),))))),
                      K.Assign(x, K.Call("f", (K.ListLit((K.Call("g", (one,)), y)),)))),
    "call_in_call": B(K.Assign(x, K.Call("f", (K.Call("g", (K.Call("h", ()),)), K.Call("g", (one, two)))))),
    "append_index": B(K.Append(K.Index(x, one), K.Index(y, two)), K.Append(K.Index(K.Index(x, y), z), K.Call("f", (one,))),
                      K.Append(x, K.ListLit((K.Index(y, one),)))),
    "append_call_value": B(K.Append(x, K.Call("f", (K.Index(y, one), z)))),
    "inc_dec_index": B(K.Inc(K.Index(K.Index(x, one), y)), K.Dec(K.Index(x, K.Index(y, one)))),
    "compare_index_call": B(K.If(K.Compare("==", K.Index(x, one), K.Call("f", (K.Index(y, two),))),
                                 B(K.Assign(K.Index(x, one), K.Index(y, two))),
                                 B(K.Append(x, K.Call("g", (z,)))))),
    "repeat_by_index_call": B(K.Repeat(K.Index(x, one), B(K.Inc(K.Index(y, one)))),
                              K.Repeat(K.Call("f", (K.Index(x, two),)), B(K.Break()))),
    "return_index_list": B(K.FuncDef("f", ("a",), B(K.Return(K.ListLit((K.Index(K.Var("a"), one), K.Call("g", (K.Var("a"),))))))),
                           K.FuncDef("g", ("a", "b"), B(K.Assign(K.Index(K.Var("a"), K.Var("b")), one),
                                                        K.Return(K.Index(K.Var("a"), K.Var("b")))))),
    "doctest_index_call": B(K.Assign(x, K.ListLit((one, two))),
                            K.Doctest(K.Index(x, one), 2),
                            K.Doctest(K.Call("f", (K.Index(x, one), K.ListLit((one,)))), [2, 1])),
    "append_in_loop": B(K.Assign(x, K.ListLit()),
                        K.Repeat(two, B(K.Append(x, K.Call("f", (K.Index(x, one),))), K.Inc(K.Index(y, one))))),
    "append": B(K.Append(x, K.ListLit((one,)))),
    "inc_dec": B(K.Inc(x), K.Dec(x), K.Dec(K.Index(y, one))),
    "call_expr": B(K.Assign(x, K.Call("f", (one, K.Call("g", (y,)), K.ListLit())))),
    "call_noargs": B(K.Assign(x, K.Call("f"))),
    "call_stmt": B(K.CallStmt(K.Call("f", (x, two)))),
    "compare": B(*(K.If(K.Compare(op, x, one), B(K.Inc(x))) for op in K.COMPARE_OPS)),
    "if_else": B(K.If(K.Compare("==", x, one), B(K.Inc(x)), B(K.Dec(x)))),
    "if_nested": B(K.If(K.Compare("<", x, y), B(K.If(K.Compare(">", x, one), B(K.Inc(x)), B(K.Dec(x)))), B(K.Inc(y)))),
    "if_in_else": B(K.If(K.Compare("<", x, y), B(K.Inc(x)), B(K.If(K.Compare(">", x, y), B(K.Inc(y))))),
                    K.Assign(z, one)),
    "repeat": B(K.Repeat(two, B(K.Inc(x), K.Break()))),
    "repeat_nested": B(K.Repeat(x, B(K.Repeat(two, B(K.Inc(x))), K.Inc(y)))),
    "def": B(K.FuncDef("f", (), B(K.Return(one)))),
    "def_params": B(K.FuncDef("f", ("a", "b"), B(K.Assign(x, K.Var("a")), K.Return(K.Var("b"))))),
    "def_nested": B(K.FuncDef("f", ("a",), B(K.If(K.Compare("==", K.Var("a"), one), B(K.Return(one))), K.Return(two))),
                    K.CallStmt(K.Call("f", (one,)))),
    "doctest": B(K.Assign(x, one), K.Doctest(x, 1)),
    "doctest_list": B(K.Doctest(K.Call("f", (K.ListLit((one, K.Str("a"))),)), [1, "a"])),
    "sequence": B(K.Assign(x, one), K.Assign(y, two), K.Inc(x), K.CallStmt(K.Call("f", (x,)))),
}


def failures(syntax) -> list:
    """syntax（Syntax）で全スニペットを 出力 → パース し、戻らなかったものを [(名前, 理由)] で返す。"""
    from .parser import parse            # syntax.py から呼ばれるので、読み込みは遅らせる
    from .unparser import unparse
    bad = []
    for label, tree in SNIPPETS.items():
        try:
            text = unparse(tree, syntax)
            back = parse(text, syntax)
        except Exception as e:
            bad.append((label, f"{type(e).__name__}: {str(e).splitlines()[0]}"))
            continue
        if back != tree:
            bad.append((label, f"AST が変わった。出力:\n{text}"))
    return bad


def show_snippets(syntax, names=None) -> str:
    """スニペット（names が None なら全部）を syntax で出力した文章。`kolang show_example`。

    書けないスニペットは、理由を添えて知らせる。名前が違うときは ValueError。
    """
    from .unparser import UnparseError, unparse
    names = list(SNIPPETS) if not names else list(names)
    unknown = [n for n in names if n not in SNIPPETS]
    if unknown:
        raise ValueError(f"スニペットが見つかりません: {', '.join(unknown)}（名前: {' '.join(SNIPPETS)}）")
    lines = [syntax.name, ""]
    for label in names:
        lines.append(f"■ {label}")
        try:
            text = unparse(SNIPPETS[label], syntax).rstrip("\n")
        except UnparseError as e:
            text = f"(このシンタックスでは書けません: {str(e).splitlines()[0]})"
        lines += [f"  {line}" if line else "" for line in text.split("\n")]
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


__all__ = ["SNIPPETS", "failures", "show_snippets"]
