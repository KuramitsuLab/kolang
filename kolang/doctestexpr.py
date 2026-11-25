"""doctest 風の例（`>>> 式`）の式は、どのシンタックスでも pylike の書き方で書く。

書けるのは、関数呼び出し `f(x, y)`（引数は pylike の式）か、変数（添字つき `x[0]` を含む）だけ。
こうしておけば、シンタックスを変えても同じ doctest がそのまま読める。

標準ライブラリ関数の名前だけは、書き方（pylike の名前 = 標準名）と、AST の名前（そのシンタックスでの名前）が違いうる
（jalike の `add` ↔ `足し算`）。構文解析のあとで localize_doctests が、AST の名前にする。出力器は逆（delocalize）。
プログラムが同じ名前を自分で定義しているものは、自作なので書き換えない（rename_stdlib と同じ）。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from . import ast as K
from .syntax import Syntax, load_syntax


@lru_cache(maxsize=None)
def pylike_syntax() -> Syntax:
    return load_syntax("pylike", verify=False)


@lru_cache(maxsize=None)
def _expression_parser():
    from .parser import build_grammar         # parser.py が、この module を読み込むので、あとで import する
    return build_grammar(pylike_syntax(), entry="expression")


@lru_cache(maxsize=4096)
def read_doctest_expression(text: str) -> Optional[K.Expression]:
    """pylike の書き方で、関数呼び出しか変数を読む。読めなければ None。"""
    from .combinators import Context
    syn = pylike_syntax()
    result = _expression_parser()(Context(text, syn.skip_pattern, syn.word_segment), 0)
    if result is None or not isinstance(result[0], (K.Call, K.Var, K.Index)):
        return None
    return result[0]


def write_doctest_expression(e: K.Expression) -> str:
    """pylike の書き方で、式を文字列にする。関数呼び出しか変数でなければ UnparseError。"""
    from .unparser import UnparseError, make_unparser
    if not isinstance(e, (K.Call, K.Var, K.Index)):
        raise UnparseError(f"a doctest expression must be a function call or a variable: {e!r}")
    return _expression_writer()(e)


@lru_cache(maxsize=None)
def _expression_writer():
    from .unparser import make_unparser
    return make_unparser(pylike_syntax()).expression


def localize_doctests(program: K.Block, syn: Syntax, defined=()) -> K.Block:
    """doctest の式の標準関数の名前を、pylike の名前から syn の名前にする。defined は別ファイルで定義された自作の名前。"""
    from .unparser import rename_stdlib
    if syn.function_names == pylike_syntax().function_names:
        return program
    return rename_stdlib(program, pylike_syntax(), syn, doctest_only=True, defined=defined)


def delocalize_doctests(program: K.Block, syn: Syntax) -> K.Block:
    """localize_doctests の逆（syn の名前から pylike の名前へ）。"""
    from .unparser import rename_stdlib
    if syn.function_names == pylike_syntax().function_names:
        return program
    return rename_stdlib(program, syn, pylike_syntax(), doctest_only=True)
