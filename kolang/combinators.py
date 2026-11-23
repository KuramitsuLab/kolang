"""小さなパーサコンビネータ（バックトラック付き）。

パーサは `(ctx, pos) -> (値, 新しい位置) | None` という関数で、None は失敗。
位置は不変なので、失敗した選択肢を捨てて次へ進むだけでバックトラックになる（PEG と同じ意味論）。

    alt(a, b)    順序つき選択。a が失敗したら同じ位置から b を試す
    seq(a, b)    連接。値は tuple
    many(a)      0 回以上の繰り返し（貪欲）
    opt(a)       あってもなくてもよい（なければ None）
    where(a, f)  値が条件 f を満たすときだけ成功
    Forward      再帰する規則の前方宣言
    p.map(f)     値を変換
    p.apply(f)   tuple の値を f(*値) に渡す
    p.pick(i, j) tuple の値から必要な要素だけ取り出す
    p.memo()     (位置ごとの) 結果をキャッシュする
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

Result = Optional[tuple[Any, int]]


class ParseError(Exception):
    def __init__(self, message: str, line: Optional[int] = None, col: Optional[int] = None):
        self.message = message
        self.line = line
        self.col = col
        where = f"{line}:{col}: " if line is not None else ""
        super().__init__(where + message)


class Context:
    """1 回の解析で共有する状態（入力、空白の読み飛ばし、最遠の失敗位置）。"""

    def __init__(self, text: str, skip: str = "", word: str = ""):
        self.text = text
        self._skip = re.compile(skip) if skip else None
        self._word = re.compile(word) if word else None
        self.farthest = 0
        self.expected: set[str] = set()
        self._memo: dict = {}
        self.comments: dict = {}    # {位置: 本文}  読み飛ばしたコメント（skip の正規表現の comment_body 群）
        self.starts: dict = {}      # {id(値): (開始位置, 値)}  track() で記録した文の開始位置

    def skip(self, pos: int) -> int:
        if self._skip is not None:
            while True:
                m = self._skip.match(self.text, pos)
                if m is None or m.end() == pos:
                    break
                body = m.groupdict().get("comment_body")
                if body is not None:
                    self.comments[m.start()] = body.strip()
                pos = m.end()
        return pos

    def needs_space(self, token: str, end: int) -> bool:
        """語の区切りの規則。token が語の文字（word_segment）で終わり、
        すぐ後ろにも語の文字が続くなら、空白が必要（＝ここでトークンを切れない）。"""
        w = self._word
        return bool(w and token and w.fullmatch(token[-1])
                    and end < len(self.text) and w.match(self.text, end))

    def fail(self, pos: int, expected: str) -> None:
        """失敗を記録する。エラーメッセージには最も先まで進んだ失敗を使う。"""
        if pos > self.farthest:
            self.farthest, self.expected = pos, {expected}
        elif pos == self.farthest:
            self.expected.add(expected)
        return None


class Parser:
    def __init__(self, fn: Callable[[Context, int], Result], name: str = "parser"):
        self.fn = fn
        self.name = name

    def __call__(self, ctx: Context, pos: int) -> Result:
        return self.fn(ctx, pos)

    def map(self, f: Callable[[Any], Any]) -> "Parser":
        def run(ctx: Context, pos: int) -> Result:
            r = self(ctx, pos)
            return None if r is None else (f(r[0]), r[1])
        return Parser(run, self.name)

    def apply(self, f: Callable[..., Any]) -> "Parser":
        return self.map(lambda v: f(*v))

    def pick(self, *indexes: int) -> "Parser":
        if len(indexes) == 1:
            i = indexes[0]
            return self.map(lambda v: v[i])
        return self.map(lambda v: tuple(v[i] for i in indexes))

    def memo(self) -> "Parser":
        key = object()

        def run(ctx: Context, pos: int) -> Result:
            k = (key, pos)
            if k not in ctx._memo:
                ctx._memo[k] = self(ctx, pos)
            return ctx._memo[k]
        return Parser(run, self.name)


class Forward(Parser):
    """再帰する規則用。先に作っておき、あとで define() で中身を与える。"""

    def __init__(self, name: str = "forward"):
        super().__init__(self._run, name)
        self.target: Optional[Parser] = None

    def _run(self, ctx: Context, pos: int) -> Result:
        if self.target is None:
            raise RuntimeError(f"Forward {self.name!r} is not defined")
        return self.target(ctx, pos)

    def define(self, parser: Parser) -> Parser:
        self.target = parser
        return parser


def track(parser: Parser) -> Parser:
    """成功した値の開始位置（先頭の空白・コメントを除く）を ctx.starts に記録する。"""
    def run(ctx: Context, pos: int) -> Result:
        r = parser(ctx, pos)
        if r is not None:
            ctx.starts[id(r[0])] = (ctx.skip(pos), r[0])   # 値も持っておき、id の再利用を防ぐ
        return r
    return Parser(run, parser.name)


def regex(pattern: str, name: Optional[str] = None, skip: bool = True,
          boundary: bool = True) -> Parser:
    """正規表現トークン。空マッチも成功。

    skip=True      先に空白・コメントを読み飛ばす
    boundary=True  語の区切りの規則（Context.needs_space）を適用する
    """
    rx = re.compile(pattern)
    label = name or pattern

    def run(ctx: Context, pos: int) -> Result:
        if skip:
            pos = ctx.skip(pos)
        m = rx.match(ctx.text, pos)
        if m is None:
            return ctx.fail(pos, label)
        if boundary and ctx.needs_space(m.group(), m.end()):
            return ctx.fail(m.end(), "space")
        return m.group(), m.end()
    return Parser(run, label)


def eof() -> Parser:
    def run(ctx: Context, pos: int) -> Result:
        pos = ctx.skip(pos)
        if pos != len(ctx.text):
            return ctx.fail(pos, "end of input")
        return None, pos
    return Parser(run, "eof")


def seq(*parsers: Parser) -> Parser:
    def run(ctx: Context, pos: int) -> Result:
        values = []
        for p in parsers:
            r = p(ctx, pos)
            if r is None:
                return None
            value, pos = r
            values.append(value)
        return tuple(values), pos
    return Parser(run, "seq")


def alt(*parsers: Parser) -> Parser:
    def run(ctx: Context, pos: int) -> Result:
        for p in parsers:
            r = p(ctx, pos)
            if r is not None:
                return r
        return None
    return Parser(run, "alt")


def many(parser: Parser) -> Parser:
    """0 回以上。位置が進まない成功（空マッチだけ）は無限ループを避けるため打ち切る。"""
    def run(ctx: Context, pos: int) -> Result:
        values = []
        while True:
            r = parser(ctx, pos)
            if r is None or r[1] == pos:
                break
            values.append(r[0])
            pos = r[1]
        return values, pos
    return Parser(run, "many")


def opt(parser: Parser) -> Parser:
    def run(ctx: Context, pos: int) -> Result:
        r = parser(ctx, pos)
        return (None, pos) if r is None else r
    return Parser(run, "opt")


def where(parser: Parser, predicate: Callable[[Any], bool], expected: str) -> Parser:
    def run(ctx: Context, pos: int) -> Result:
        r = parser(ctx, pos)
        if r is None:
            return None
        if not predicate(r[0]):
            return ctx.fail(ctx.skip(pos), expected)
        return r
    return Parser(run, expected)
