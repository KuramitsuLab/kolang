"""正規表現を読み解く小道具。トークンの正規表現から、次の 3 つを取り出す。

    leading_literal(p)    先頭の固定文字列（予約語の抽出に使う）
    sample(p)             p にマッチする文字列を 1 つ作る（出力用）
    string_delimiters(p)  文字列リテラルの開始・終了の文字

対応するのは、リテラル、文字クラス、繰り返し、グループ、選択、先読み・アンカー。
それ以外（後方参照など）は ValueError にする。
"""

from __future__ import annotations

try:                                     # Python 3.11+
    from re import _constants as C
    from re import _parser as P
except ImportError:                      # それ以前
    import sre_constants as C            # type: ignore
    import sre_parse as P                # type: ignore


def leading_literal(pattern: str) -> str:
    """パターンの先頭に並んだ固定文字列。例: 'else *:' → 'else'、',|(?=\\))' → ''。"""
    out = []
    for op, av in P.parse(pattern):
        if op == C.LITERAL:
            out.append(chr(av))
        else:
            break
    return "".join(out)


def sample(pattern: str, prefer_empty: bool = False) -> str:
    """マッチする文字列を作る。選択は最初の枝、繰り返しは最小回数を採る。
    prefer_empty=True のときは、空にマッチする枝（先読みだけの枝など）があればそれを採る。"""
    return _gen(P.parse(pattern), prefer_empty)


def string_delimiters(pattern: str) -> tuple:
    """文字列リテラルの正規表現から (開始, 終了) を取る。選択なら最初の枝を見る。"""
    items = list(P.parse(pattern))
    if len(items) == 1 and items[0][0] == C.BRANCH:
        items = list(items[0][1][1][0])
    if len(items) >= 2 and items[0][0] == C.LITERAL and items[-1][0] == C.LITERAL:
        return chr(items[0][1]), chr(items[-1][1])
    raise ValueError(f"cannot find string delimiters in {pattern!r}")


def _gen(items, prefer_empty: bool) -> str:
    out = []
    for op, av in items:
        if op == C.LITERAL:
            out.append(chr(av))
        elif op == C.IN:
            out.append(_first_of_class(av))
        elif op in (C.MAX_REPEAT, C.MIN_REPEAT):
            low, _high, sub = av
            out.append(_gen(sub, prefer_empty) * low)
        elif op == C.SUBPATTERN:
            out.append(_gen(av[-1], prefer_empty))
        elif op == C.BRANCH:
            alts = [_gen(a, prefer_empty) for a in av[1]]
            out.append("" if prefer_empty and "" in alts else alts[0])
        elif op in (C.ASSERT, C.ASSERT_NOT, C.AT):
            pass                         # 先読み・アンカーは文字を作らない
        else:
            raise ValueError(f"unsupported regex element: {op}")
    return "".join(out)


def _first_of_class(members) -> str:
    for op, av in members:
        if op == C.LITERAL:
            return chr(av)
        if op == C.RANGE:
            return chr(av[0])
    raise ValueError("unsupported character class")
