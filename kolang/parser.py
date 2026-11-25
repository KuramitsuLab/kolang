"""kolang.md の文法をパーサコンビネータで書いたもの。

文法の規則は build_grammar() の中に 1 規則 1 ブロックで並べてある。
区切りトークンの正規表現は Syntax（JSON）から取るので、ここにはどんな記号も書かない。
文法を変えるときは、該当する規則のブロックを直す。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Union

from . import ast as K
from .combinators import (Context, Forward, Parser, ParseError, alt, eof, many,
                          opt, regex, seq, track, where)
from .comments import attach_comments
from .layout import apply_layout
from .doctestexpr import localize_doctests, read_doctest_expression
from .syntax import DOCTEST_PROMPT, Syntax, load_syntax

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}


def string_value(token: str) -> str:
    """文字列トークンの両端の引用符 1 文字を外し、\\n などを解く。引用形式を変えるならここ。"""
    return re.sub(r"\\(.)", lambda m: ESCAPES.get(m.group(1), m.group(1)), token[1:-1])


def number_value(token: str) -> Union[int, float]:
    return float(token) if "." in token else int(token)


def build_grammar(syn: Syntax, entry: str = "program") -> Parser:
    """文法の本体。entry="expression" なら、式 1 つ（と終わり）だけを読むパーサを返す（doctest の式用）。"""
    def T(name: str) -> Parser:
        """区切りトークン。"""
        if name not in syn.tokens:
            raise KeyError(f"token {name!r} is not defined in syntax {syn.name!r}")
        return regex(syn.tokens[name], name)

    def comma_list(item: Parser, sep: str) -> Parser:
        """(item sep)*  → item の list"""
        return many(seq(item, T(sep)).pick(0))

    expression = Forward("expression")
    block = Forward("block")
    statement = Forward("statement")

    # ---- <identifier> ---------------------------------------------------
    plain_name = where(regex(syn.lexical["letters"], "identifier"),
                       lambda s: s not in syn.reserved, "identifier")
    # 引用の記号は区切りなので、語の区切りの規則（boundary）は適用しない（_x_ の _ は語の文字）
    quoted_name = seq(regex(syn.tokens["quote_begin"], "quote_begin", boundary=False),
                      regex(syn.lexical["characters"], "characters", skip=False, boundary=False),
                      regex(syn.tokens["quote_end"], "quote_end", boundary=False)).pick(1)
    identifier = alt(plain_name, quoted_name)
    # 関数呼び出しの関数名: stdlib で定義された名前は、引用なしでそのまま書ける（表示(x) など）。長い名前を先に試す。
    std_names = sorted(set(syn.function_names.values()), key=len, reverse=True)
    func_name = (alt(regex("|".join(re.escape(n) for n in std_names), "stdlib_name"), identifier)
                 if std_names else identifier)

    # ---- <variable> ----------------------------------------------------------
    # 添字の書き方は 2 通り（syntax.index）。
    #   postfix  x[i]      左再帰（<variable> index ...）になるので、繰り返しにして畳み込む。
    #   prefix   (get x i) 再帰は右側なので、そのまま書ける。
    index_first: list = []        # 式の選択肢のうち、funcapp より先に試すもの
    if syn.index == "prefix":
        variable = Forward("variable")
        index = seq(T("index_begin"), variable, T("index_sep"), expression, T("index_end")
                    ).pick(1, 3).apply(K.Index)
        variable.define(alt(index, identifier.map(K.Var)))
        index_first.append(index)   # (get x i) を、関数呼び出し (f x i) と読まない
    else:
        def fold_index(name: str, indexes: list) -> K.Variable:
            v: K.Variable = K.Var(name)
            for i in indexes:
                v = K.Index(v, i)
            return v

        variable = seq(identifier,
                       # 添字の `[` は、変数のすぐ後ろ（空白なし）。`(append x [1])` の `x [1]` を添字と読まない。
                       many(seq(regex(syn.tokens["index_begin"], "index_begin",
                             # index_begin が空にマッチするシンタックス（pslike: a 1 get）は、空白を許す
                             skip=re.fullmatch(syn.tokens["index_begin"], "") is not None),
                                expression, T("index_end")).pick(1))
                       ).apply(fold_index)

    # ---- 式 -----------------------------------------------------------------
    string = regex(syn.lexical["string"], "string").map(string_value).map(K.Str)
    number = regex(syn.lexical["number"], "number").map(number_value).map(K.Num)
    boolean = alt(T("true").map(lambda _: K.Bool(True)),
                  T("false").map(lambda _: K.Bool(False)))
    none = T("none").map(lambda _: K.NoneLit())
    list_ = seq(T("list_begin"), comma_list(expression, "list_sep"), T("list_end")
                ).pick(1).map(lambda xs: K.ListLit(tuple(xs)))
    if syn.call == "args_first":
        funcapp = seq(T("call_begin"), comma_list(expression, "arg_sep"), T("call_name_end"),
                      func_name, T("call_end")
                      ).pick(3, 1).apply(lambda f, args: K.Call(f, tuple(args)))
    else:
        funcapp = seq(T("call_begin"), func_name, T("call_name_end"),
                      comma_list(expression, "arg_sep"), T("call_end")
                      ).pick(1, 3).apply(lambda f, args: K.Call(f, tuple(args)))

    # 符号の反転 -X。neg_begin の無いシンタックスでは使えない（省略可のトークン）。
    # neg_begin が空にマッチするシンタックス（pslike の `x neg`）は後置: 式のあとに neg_end を畳み込む。
    neg_first: list = []
    neg_postfix = "neg_begin" in syn.tokens and re.fullmatch(syn.tokens["neg_begin"], "") is not None
    if "neg_begin" in syn.tokens and not neg_postfix:
        neg_first.append(seq(T("neg_begin"), expression, T("neg_end")).pick(1).map(K.Neg))

    # 式の括弧（grouping_begin 式 grouping_end）。AST は中の式そのまま。省略可のトークン。
    # funcapp と記号が重なっても（jalike の「（」）、funcapp を先に試して、だめなら括弧と読む。
    grouping_after: list = []
    if "grouping_begin" in syn.tokens:
        grouping_after.append(seq(T("grouping_begin"), expression, T("grouping_end")).pick(1))

    # 順序つき選択なので、funcapp は variable より先（f(x) の f を変数と読まない）。
    primary = alt(string, number, boolean, none, list_, *index_first, *neg_first, funcapp, *grouping_after, variable)
    if neg_postfix:
        def fold_neg(e, negs: list):
            for _ in negs:
                e = K.Neg(e)
            return e
        primary = seq(primary, many(T("neg_end"))).apply(fold_neg)
    expression.define(primary.memo())
    if entry == "expression":
        return seq(expression, eof()).pick(0)

    # ---- <condition> ----------------------------------------------------
    def compare(prefix: str, op: str) -> Parser:
        return seq(T(f"{prefix}_begin"), expression, T(f"{prefix}_sep"), expression,
                   T(f"{prefix}_end")).pick(1, 3).apply(lambda l, r: K.Compare(op, l, r))

    condition = alt(compare("ne", "!="), compare("lt", "<"), compare("gt", ">"),
                    compare("le", "<="), compare("ge", ">="), compare("eq", "=="))

    # ---- 文 -----------------------------------------------------------------
    # 代入・増減の左辺は <variable>（<expression> の部分集合）で受ける。
    if syn.assign == "value_first":
        assign = seq(T("assign_begin"), expression, T("assign_op"), variable, T("assign_end")
                     ).pick(3, 1).apply(K.Assign)
    else:
        assign = seq(T("assign_begin"), variable, T("assign_op"), expression, T("assign_end")
                     ).pick(1, 3).apply(K.Assign)
    if syn.append == "value_first":
        append = seq(T("append_begin"), expression, T("append_sep"), expression, T("append_end")
                     ).pick(3, 1).apply(K.Append)
    else:
        append = seq(T("append_begin"), expression, T("append_sep"), expression, T("append_end")
                     ).pick(1, 3).apply(K.Append)
    inc = seq(T("inc_begin"), variable, T("inc_end")).pick(1).map(K.Inc)
    dec = seq(T("dec_begin"), variable, T("dec_end")).pick(1).map(K.Dec)

    else_ = seq(T("else_begin"), block, T("else_end")).pick(1)
    # if_end は else のあと（Lisp の (if c then (else ...)) で、最後の ")" を if_end にするため）
    if_ = seq(T("if_begin"), condition, T("if_then"), block, opt(else_), T("if_end")
              ).pick(1, 3, 4).apply(K.If)
    repeat = seq(T("repeat_begin"), expression, T("repeat_do"), block, T("repeat_end")
                 ).pick(1, 3).apply(K.Repeat)
    break_ = T("break").map(lambda _: K.Break())
    funcdef = seq(T("def_begin"), identifier, T("def_name_end"), T("params_begin"),
                  comma_list(identifier, "param_sep"), T("params_end"), block, T("def_end")
                  ).pick(1, 4, 6).apply(lambda name, params, body: K.FuncDef(name, tuple(params), body))
    return_ = seq(T("return_begin"), expression, T("return_end")).pick(1).map(K.Return)

    # track: 文の開始位置を記録する（コメントを文に付けるため。comments.py）
    statement.define(track(alt(assign, append, inc, dec, if_, repeat, break_, funcdef, return_,
                                 funcapp.map(K.CallStmt))))

    # ---- <block> ------------------------------------------------------------
    # doctest 風の例: `>>> 式` の次の行に、答え（JSON を 1 値）。記号は固定（syntax の JSON では変えない）。
    # 答えの行は生の文字列として読む（空白・コメントの読み飛ばしなし）。block_sep は取らない（任意で 1 つ読む）。
    def json_value(text: str):
        try:
            return True, json.loads(text)
        except ValueError:
            return False, None

    answer = where(regex(r"[ \t]*[^\n]*", "JSON answer", skip=False, boundary=False
                         ).map(lambda t: t.strip()),
                   lambda t: json_value(t)[0], "JSON answer")
    # 式は、どのシンタックスでも pylike の書き方（f(x, y) か変数）で読む（doctestexpr.py）。そのシンタックスの名前への
    # 書き換え（標準関数の名前）は、構文解析のあと（make_parser）。
    doctest_expr = where(regex(r"[ \t]*[^\n]*", "doctest expression", skip=False, boundary=False
                               ).map(lambda t: t.strip()),
                         lambda t: read_doctest_expression(t) is not None,
                         "doctest expression (f(x, y) or variable, in pylike)"
                         ).map(read_doctest_expression)
    doctest = track(seq(regex(re.escape(DOCTEST_PROMPT), repr(DOCTEST_PROMPT), boundary=False),
                        doctest_expr,
                        regex(r"[ \t]*\r?\n", "newline", skip=False, boundary=False),
                        answer, opt(T("block_sep"))
                        ).pick(1, 3).apply(lambda e, a: K.Doctest(e, json_value(a)[1])))

    statements = many(alt(doctest, seq(statement, T("block_sep")).pick(0)))
    block.define(seq(T("block_begin"), statements, T("block_end")
                     ).pick(1).map(lambda ss: K.Block(tuple(ss))))

    # ---- プログラム全体 ---------------------------------------------------------
    # インデント方式（と toplevel が bare のとき）の最上位には block_begin / block_end がないので、文の並びだけ読む。
    if syn.layout == "indent" or syn.toplevel == "bare":
        body = statements.map(lambda ss: K.Block(tuple(ss)))
    else:
        body = block
    return seq(body, eof()).pick(0)


def make_parser(syntax: Union[str, Path, Syntax] = "pylike") -> Callable[[str], K.Block]:
    """シンタックスを 1 度だけ読み込んで、文字列 → AST の関数を返す。"""
    syn = syntax if isinstance(syntax, Syntax) else load_syntax(syntax)
    grammar = build_grammar(syn)

    def parse(source: str, defined=()) -> K.Block:
        """defined: 別のところ（本体）で定義された名前。.doctest だけを読むとき、doctest の式で自作を優先する。"""
        layout = apply_layout(source, syn)
        ctx = Context(layout.text, syn.skip_pattern, syn.word_segment)
        result = grammar(ctx, 0)
        if result is None:
            line, col, text = layout.locate(ctx.farthest)
            expected = ", ".join(sorted(ctx.expected))
            raise ParseError(f"expected {expected}\n  {text}\n  {' ' * (col - 1)}^", line, col)
        return localize_doctests(attach_comments(result[0], ctx), syn, defined)
    return parse


def parse(source: str, syntax: Union[str, Path, Syntax] = "pylike", defined=()) -> K.Block:
    return make_parser(syntax)(source, defined)
