"""AST からソースを作る（パーサの逆）。別のシンタックスで書き出せば、変換になる。

規則は parser.py と同じ順で並べてある。トークンは次のどちらかで出力する。
  1. JSON の "emit" に書かれた文字列（空白を足して整えたいとき）。配列なら候補で、
     random_emit（seed）が与えられたときだけ choice し、なければ常に最初
  2. 正規表現から作った例（regexgen.sample）
区切りトークンが空にマッチできる場合（`,|(?=\\))` など）、最後の要素のあとは空にする。
語の文字どうしが隣り合うときは、語の区切りの規則に従って空白を 1 つ入れる。
"""

from __future__ import annotations

import dataclasses
import enum
import json
import random
import re
from pathlib import Path
from typing import Callable, Optional, Union

from . import ast as K
from .combinators import ParseError
from .doctestexpr import delocalize_doctests, write_doctest_expression
from .parser import ESCAPES, make_parser
from .regexgen import sample, string_delimiters
from .syntax import DOCTEST_PROMPT, Syntax, load_syntax

INDENT_UNIT = "    "
COMPARE_PREFIX = {"!=": "ne", "<": "lt", ">": "gt", "<=": "le", ">=": "ge", "==": "eq"}
_ESCAPE_OUT = {**{v: "\\" + k for k, v in ESCAPES.items()}, "\\": "\\\\"}


class UnparseError(ValueError):
    pass


class Mark(enum.Enum):
    """出力の途中に挟む印（改行とインデント）。"""
    NL = "newline"
    IN = "indent"
    OUT = "dedent"


class Raw(str):
    """コメントの文字列。語の区切りの規則を使わず、同じ行にあれば空白 1 つで続ける。"""


def make_unparser(syntax: Union[str, Path, Syntax] = "pylike",
                  random_emit: Optional[int] = None) -> Callable[[K.Block], str]:
    syn = syntax if isinstance(syntax, Syntax) else load_syntax(syntax)
    indent_layout = syn.layout == "indent"
    letters = re.compile(syn.lexical["letters"])
    characters = re.compile(syn.lexical["characters"])
    number_rx = re.compile(syn.lexical["number"])
    string_rx = re.compile(syn.lexical["string"])
    word = re.compile(syn.word_segment) if syn.word_segment else None
    tight = re.compile(syn.tight_before) if syn.tight_before else None
    space = sample(syn.space) or " "
    rng = random.Random(random_emit) if random_emit is not None else None

    # ---- トークン -------------------------------------------------------------
    def tok(name: str, last: bool = False) -> str:
        if name not in syn.tokens:
            raise UnparseError(f"token {name!r} is not defined in syntax {syn.name!r}")
        pattern = syn.tokens[name]
        if last and sample(pattern, prefer_empty=True) == "":
            return ""
        if name not in syn.emit:
            return sample(pattern)
        choices = syn.emit[name]
        if isinstance(choices, str):
            return choices
        return rng.choice(choices) if rng else choices[0]

    sep_optional = re.fullmatch(syn.tokens["block_sep"], "") is not None \
        if not syn.tokens["block_sep"].startswith("@") else False

    def statement_end(s, pieces: list) -> list:
        """文のあとの block_sep。省略できる区切りは、文が block_end で終わるなら書かない（}; にしない）。"""
        if isinstance(s, K.Doctest):                 # doctest 風の例は、答えの行で終わる（区切りは付けない）
            return []
        end = tok("block_end")
        tail = [x for x in pieces if x != ""]
        if sep_optional and end and tail and tail[-1] == end:
            return []
        return [tok("block_sep")]

    def trailer(name: str, last: bool = False) -> str:
        """ブロックのあとに付くトークン。indent レイアウトでは空でなければ書けない。"""
        text = tok(name, last)
        if indent_layout and text:
            raise UnparseError(f"token {name!r} must be empty in the indent layout")
        return text

    def seplist(items, emit_item, sep: str) -> list:
        out: list = []
        for i, item in enumerate(items):
            out += emit_item(item)
            out.append(tok(sep, last=i == len(items) - 1))
        return out

    # ---- コメント -------------------------------------------------------------
    # 書き出し先にコメントの記号がなければ、コメントは捨てる。
    c_begin = sample(syn.comment_begin) if syn.comment_begin and syn.comment_end else None
    c_end = sample(syn.comment_end) if c_begin is not None else ""
    # コメントのあとで改行できるなら、改行する（前の行か同じ行かの区別を、読み直しても保つため）。
    # 改行を読み飛ばせない（space が改行にマッチしない）形式では、/* */ のようにそのまま続ける。
    # 行末で終わる形のコメント（c_end が空）は、改行しないと次の文字を飲み込む。
    can_break = indent_layout or bool(re.fullmatch(f"(?:{syn.space})+", "\n"))
    break_after = can_break or not c_end

    def comment_text(line: str) -> Raw:
        return Raw(" ".join(x for x in (c_begin, line, c_end) if x))

    def lines_of(body: str) -> list:
        return [l.strip() for l in body.split("\n")]     # 複数行のコメントは 1 行ずつ

    def leading_comments(texts) -> list:
        """文の前に置くコメント。1 行 1 件。"""
        if c_begin is None:
            return []
        out: list = []
        for body in texts:
            for line in lines_of(body):
                # 改行できる形式では、前の文と同じ行にならないよう、コメントを行頭に置く
                out += [*([Mark.NL] if break_after else []), comment_text(line),
                        *([Mark.NL] if break_after else [])]
        return out

    def trailing_comment(body) -> list:
        """文と同じ行に置くコメント。複数行なら 1 行につなぐ。"""
        if c_begin is None or body is None:
            return []
        joined = " ".join(l for l in lines_of(body) if l)
        return [comment_text(joined), *([Mark.NL] if not indent_layout and break_after else [])]

    # ---- 名前・リテラル -------------------------------------------------------
    std_names = frozenset(syn.function_names.values())

    def func_ident(name: str) -> list:
        """関数名: stdlib の名前は引用なしで書く。"""
        return [name] if name in std_names else ident(name)

    def ident(name: str) -> list:
        if letters.fullmatch(name) and name not in syn.reserved:
            return [name]
        if characters.fullmatch(name):
            return [tok("quote_begin") + name + tok("quote_end")]      # 1 つの部品（記号と名前のあいだに空白を入れない）
        raise UnparseError(f"cannot write the name {name!r} in syntax {syn.name!r}")

    open_quote, close_quote = string_delimiters(syn.lexical["string"])

    def string(value: str) -> list:
        body = "".join(_ESCAPE_OUT.get(c, "\\" + c if c == close_quote else c) for c in value)
        text = open_quote + body + close_quote
        if not string_rx.fullmatch(text):
            raise UnparseError(f"cannot write the string {value!r} in syntax {syn.name!r}")
        return [text]

    def num(value) -> list:
        text = repr(value) if isinstance(value, float) else str(value)
        if not number_rx.fullmatch(text):
            raise UnparseError(f"cannot write the number {text} in syntax {syn.name!r}")
        return [text]

    # ---- 式 -----------------------------------------------------------------
    def expr(e) -> list:
        if isinstance(e, K.Var):
            return ident(e.name)
        if isinstance(e, K.Index):
            if syn.index == "prefix":
                return [tok("index_begin"), *expr(e.target), tok("index_sep"),
                        *expr(e.index), tok("index_end")]
            return [*expr(e.target), tok("index_begin"), *expr(e.index), tok("index_end")]
        if isinstance(e, K.Str):
            return string(e.value)
        if isinstance(e, K.Num):
            return num(e.value)
        if isinstance(e, K.Bool):
            return [tok("true" if e.value else "false")]
        if isinstance(e, K.NoneLit):
            return [tok("none")]
        if isinstance(e, K.ListLit):
            return [tok("list_begin"), *seplist(e.items, expr, "list_sep"), tok("list_end")]
        if isinstance(e, K.Neg):
            if "neg_begin" not in syn.tokens:
                raise UnparseError(f"syntax {syn.name!r} has no neg_begin token (cannot write -X)")
            return [tok("neg_begin"), *expr(e.operand), tok("neg_end")]
        if isinstance(e, K.Call):
            if syn.call == "args_first":
                return [tok("call_begin"), *seplist(e.args, expr, "arg_sep"), tok("call_name_end"),
                        *func_ident(e.func), tok("call_end")]
            return [tok("call_begin"), *func_ident(e.func), tok("call_name_end"),
                    *seplist(e.args, expr, "arg_sep"), tok("call_end")]
        raise UnparseError(f"not an expression: {e!r}")

    def condition(c: K.Compare) -> list:
        p = COMPARE_PREFIX[c.op]
        return [tok(f"{p}_begin"), *expr(c.left), tok(f"{p}_sep"), *expr(c.right), tok(f"{p}_end")]

    # ---- 文 -----------------------------------------------------------------
    def stmt(s) -> list:
        """文のトークン列。同じ行のコメント t は、見出し（複合文）または文の末尾に置く。"""
        t = trailing_comment(s.comments.trailing)
        if isinstance(s, K.Assign):
            first, second = (s.value, s.target) if syn.assign == "value_first" else (s.target, s.value)
            return [tok("assign_begin"), *expr(first), tok("assign_op"),
                    *expr(second), tok("assign_end"), *t]
        if isinstance(s, K.Append):
            first, second = (s.value, s.target) if syn.append == "value_first" else (s.target, s.value)
            return [tok("append_begin"), *expr(first), tok("append_sep"),
                    *expr(second), tok("append_end"), *t]
        if isinstance(s, K.Inc):
            return [tok("inc_begin"), *expr(s.target), tok("inc_end"), *t]
        if isinstance(s, K.Dec):
            return [tok("dec_begin"), *expr(s.target), tok("dec_end"), *t]
        if isinstance(s, K.If):
            out = [tok("if_begin"), *condition(s.cond), tok("if_then"), *t, *block(s.body)]
            if s.else_body is not None:
                out += [tok("else_begin"), *block(s.else_body), trailer("else_end")]
            # else があれば if_end の空の枝を優先（pslike: `c {a} {b} ifelse`、else なしは `c {a} if`）
            return [*out, trailer("if_end", last=s.else_body is not None)]
        if isinstance(s, K.Repeat):
            return [tok("repeat_begin"), *expr(s.count), tok("repeat_do"), *t,
                    *block(s.body), trailer("repeat_end")]
        if isinstance(s, K.Break):
            return [tok("break"), *t]
        if isinstance(s, K.FuncDef):
            return [tok("def_begin"), *ident(s.name), tok("def_name_end"), tok("params_begin"),
                    *seplist(s.params, ident, "param_sep"), tok("params_end"), *t,
                    *block(s.body), trailer("def_end")]
        if isinstance(s, K.Return):
            return [tok("return_begin"), *expr(s.value), tok("return_end"), *t]
        if isinstance(s, K.Doctest):
            # 答えは次の行。そのあとも改行して、次の文を別の行にする。
            # 式は、どのシンタックスでも pylike の書き方（doctestexpr.py）
            return [DOCTEST_PROMPT + " ", write_doctest_expression(s.expr), Mark.NL,
                    json.dumps(s.answer, ensure_ascii=False), Mark.NL]
        if isinstance(s, K.CallStmt):
            return [*expr(s.call), *t]
        raise UnparseError(f"not a statement: {s!r}")

    def annotated(s) -> list:
        """前の行のコメント + 文。"""
        return [*leading_comments(s.comments.leading), *stmt(s)]

    # ---- <block> ------------------------------------------------------------
    def lines(stmts) -> list:
        """indent レイアウト: 1 文 1 行。"""
        out: list = []
        for s in stmts:
            out += [*annotated(s), Mark.NL]
        return out

    def block(b: K.Block) -> list:
        if indent_layout:
            if not b.stmts:
                raise UnparseError("an empty block cannot be written in the indent layout")
            return [Mark.IN, Mark.NL, *lines(b.stmts), Mark.OUT]
        begin, end = tok("block_begin"), tok("block_end")
        # 改行できる形式で、ブロックの記号があるなら整形する: begin でインデントを深くし、
        # 文（と block_sep）ごとに改行し、end の前でインデントを浅くする。
        # lisplike のように begin も end も空なら、閉じは if_end などの `)` に任せて 1 行のまま。
        pretty = can_break and bool(begin or end)
        out = [begin]
        if pretty and b.stmts:
            out += [Mark.IN, Mark.NL]
        for s in b.stmts:
            body = annotated(s)
            out += [*body, *statement_end(s, body), *([Mark.NL] if pretty else [])]
        if pretty and b.stmts:
            out.append(Mark.OUT)
        return [*out, end]

    # ---- 組み立て -----------------------------------------------------------
    def render(pieces: list) -> str:
        done: list = []
        cur, level = "", 0
        for p in pieces:
            if p is Mark.NL:
                if cur.strip(" "):
                    done.append(cur.rstrip(" "))
                cur = ""
            elif p is Mark.IN:
                level += 1
            elif p is Mark.OUT:
                level -= 1
            elif isinstance(p, Raw):
                cur = f"{cur} {p}" if cur else INDENT_UNIT * level + p
            elif p:
                if not cur:
                    p = p.lstrip(" ")        # 行頭の空白は、インデントの深さを狂わせる
                    if p:
                        cur = INDENT_UNIT * level + p
                else:
                    if tight and tight.match(p[0]):
                        cur = cur.rstrip(" ")        # 閉じ括弧の前の空白は落とす
                    gap = space if word and cur and word.fullmatch(cur[-1]) and word.match(p[0]) else ""
                    cur += gap + p
        if cur.strip(" "):
            done.append(cur.rstrip(" "))
        return "\n".join(done) + ("\n" if done and can_break else "")

    def unparse(program: K.Block) -> str:
        program = delocalize_doctests(program, syn)      # doctest の式の標準関数の名前は、pylike の名前で書く
        if indent_layout:
            pieces = lines(program.stmts)
        elif can_break or syn.toplevel == "bare":
            # 改行できる形式では、最上位の文を 1 行に 1 つ書く（入れ子の中は 1 行のまま）
            bare = syn.toplevel == "bare"
            pieces = [] if bare else [tok("block_begin")]
            for s in program.stmts:
                body = annotated(s)
                pieces += [*body, *statement_end(s, body), Mark.NL]
            if not bare:
                pieces.append(tok("block_end"))
        else:
            pieces = block(program)
        return render([*pieces, *leading_comments(program.trailing)])   # 末尾のコメント

    unparse.expression = lambda e: render(expr(e)).strip()      # 式 1 つだけを書く（doctest の式用）
    return unparse


def unparse(program: K.Block, syntax: Union[str, Path, Syntax] = "pylike",
            random_emit: Optional[int] = None) -> str:
    return make_unparser(syntax, random_emit)(program)


def defined_names(program: K.Block) -> set:
    """プログラムが自分で定義している名前（関数・引数・代入される変数）。"""
    from .comments import walk
    names: set = set()
    for s in walk(program):
        if isinstance(s, K.FuncDef):
            names.add(s.name)
            names.update(s.params)
        elif isinstance(s, (K.Assign, K.Inc, K.Dec)) and isinstance(s.target, K.Var):
            names.add(s.target.name)
    return names


def rename_stdlib(program: K.Block, src: Syntax, dst: Syntax, doctest_only: bool = False,
                   defined=()) -> K.Block:
    """標準ライブラリ関数の名前を、src の名前から dst の名前に書き換えた木を返す。

    書き換えるのは、関数の呼び出しと、関数名の参照（Var）。プログラムが同じ名前を自分で定義しているものは、
    自作の名前なので書き換えない（Python と同じく、自作が標準を隠す）。
    defined は、別のところで定義された自作の名前（別ファイルの .doctest が、本体の名前を知るため）。
    doctest_only なら、doctest 風の例の式の中だけを書き換える（doctestexpr.py）。
    書き換えた名前が、プログラムの自作の名前とぶつかるときは UnparseError。
    """
    to_std = {local: std for std, local in src.function_names.items()}
    to_dst = dst.function_names
    mine = defined_names(program) | set(defined)

    def rename(name: str) -> str:
        """使われている名前を、dst での名前にする（標準の関数でなければ、そのまま）。"""
        if name not in to_std or name in mine:
            return name
        new = to_dst[to_std[name]]
        if new != name and new in mine:
            raise UnparseError(f"cannot rename {to_std[name]!r} ({name!r} -> {new!r}): "
                               f"the program defines its own {new!r}")
        return new

    def walk(node, active):
        if isinstance(node, K.Call):
            return K.Call(rename(node.func) if active else node.func, tuple(walk(a, active) for a in node.args))
        if isinstance(node, K.Var):
            return K.Var(rename(node.name)) if active else node
        if isinstance(node, K.Doctest):
            return dataclasses.replace(node, expr=walk(node.expr, True))      # 答え（JSON）は触らない
        if isinstance(node, tuple):
            return tuple(walk(x, active) for x in node)
        if dataclasses.is_dataclass(node) and not isinstance(node, K.Comments):
            changes = {f.name: walk(getattr(node, f.name), active) for f in dataclasses.fields(node)
                       if f.name != "comments"}
            return dataclasses.replace(node, **changes)
        return node

    return walk(program, not doctest_only)


def convert(source: str, src: Union[str, Path, Syntax], dst: Union[str, Path, Syntax],
            check: bool = True, rename: bool = True, random_emit: Optional[int] = None) -> str:
    """src シンタックスのソースを dst シンタックスに書き換える。

    check=True なら、書き出した結果を dst で読み直して AST が同じか確かめる。
    rename=True なら、標準ライブラリ関数の名前も、dst の名前（JSON の stdlib）に書き換える（rename_stdlib）。
    random_emit に seed を渡すと、emit の候補（配列）から seed つきで選ぶ。None なら常に最初の候補。
    コメントは AST に残らないので、変換すると消える。
    """
    src_syn = src if isinstance(src, Syntax) else load_syntax(src)
    dst_syn = dst if isinstance(dst, Syntax) else load_syntax(dst)
    tree = make_parser(src_syn)(source)
    if rename:
        tree = rename_stdlib(tree, src_syn, dst_syn)
    text = make_unparser(dst_syn, random_emit)(tree)
    if check:
        try:
            again = make_parser(dst_syn)(text)
        except ParseError as e:
            raise UnparseError(f"the output does not parse in {dst_syn.name!r}: {e}\n{text}") from e
        if again != tree:
            raise UnparseError(f"the output does not round-trip in {dst_syn.name!r}:\n{text}")
    return text
