"""シンタックスの BNF（kolang show_ebnf）。

kolang.md の規則を、そのシンタックスの記号に置き換えて出す。書き方は kolang.md と同じ
（`<名前> ::= …`、`( … )*`、`?`、`|`、`#` コメント）。

- 記号は、出力器が書く文字列（`emit` があればその最初、なければ正規表現から作った例）。
  空の記号は書かない。indent レイアウトの仮想トークンは NEWLINE / INDENT / DEDENT。
- 記号が固定の文字列でない（`,|(?=\\))` など）ものは、最後に正規表現を載せる。
- 省略できる記号（neg / grouping）がないシンタックスは、その規則を出さない。
- 選択（`|`）は、パーサが試す順に並べる（PEG の順序つき選択）。
"""

from __future__ import annotations

import json
import re
from typing import Union

from .regexgen import sample
from .syntax import DEDENT, DOCTEST_PROMPT, INDENT, NEWLINE, Syntax, load_syntax

VIRTUAL_NAMES = {NEWLINE: "NEWLINE", INDENT: "INDENT", DEDENT: "DEDENT"}


def _quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def show_ebnf(syntax: Union[str, Syntax]) -> str:
    syn = syntax if isinstance(syntax, Syntax) else load_syntax(syntax)

    def text_of(name: str) -> str:
        """記号の書き方（出力器と同じ）。空なら ""。"""
        pattern = syn.tokens[name]
        if pattern in VIRTUAL_NAMES:
            return pattern
        emit = syn.emit.get(name)
        if emit is not None:
            return (emit if isinstance(emit, str) else emit[0]).strip(" ")
        return sample(pattern).strip(" ")

    def tok(name: str) -> str:
        """文法の中に書く形: 引用符つきの文字列。空の記号と、未定義の記号は ""。"""
        if name not in syn.tokens:
            return ""
        text = text_of(name)
        if not text:
            return ""
        return VIRTUAL_NAMES.get(text, None) or _quote(text)

    def seq(*parts: str) -> str:
        return " ".join(p for p in parts if p)

    def many(item: str, sep: str) -> str:
        """`(要素 区切り)*`。区切りが空なら `要素*`。"""
        return f"({seq(item, sep)})*" if sep else f"{item}*"

    def rule(name: str, *alts, note: str = "") -> list:
        head = f"<{name}> ::="
        if len(alts) == 1 and not note:
            return [f"{head}", f"  {alts[0]}"]
        out = [head + (f"   # {note}" if note else "")]
        for i, a in enumerate(alts):
            text, comment = a if isinstance(a, tuple) else (a, "")
            out.append(f"  {'| ' if i else '  '}{text}" + (f"   # {comment}" if comment else ""))
        return out

    E, V, B, I = "<expression>", "<variable>", "<block>", "<identifier>"
    lines: list = [f"# {syn.name} の BNF（kolang.md の規則を、このシンタックスの記号で書いたもの）"]
    notes = ["indent レイアウト: NEWLINE / INDENT / DEDENT は、行の変わり目とインデントの変化（仮想トークン）"
             if syn.layout == "indent" else "空白と改行は、記号のあいだで読み飛ばす"]
    if syn.comment_begin and syn.comment_end:
        notes.append(f"コメント: {_quote(sample(syn.comment_begin))} から（正規表現 /{syn.comment_end}/ まで）。読み飛ばして、文に付ける")
    notes.append("選択（|）は上から順に試す。空の記号は書いていない")
    lines += [f"# {n}" for n in notes] + [""]

    # ---- プログラム・ブロック ----------------------------------------------------
    item = f"(<doctest> | {seq('<statement>', tok('block_sep'))})*"
    if syn.layout == "indent" or syn.toplevel == "bare":
        lines += rule("program", item, note="最上位は block の括りなし、文の並びだけ")
    else:
        lines += rule("program", B)
    lines.append("")
    lines += rule("block", seq(tok("block_begin"), item, tok("block_end")))
    lines.append("")
    lines += rule("doctest", seq(_quote(DOCTEST_PROMPT), "<pylike の f(x, y) か変数>", "改行", "<JSON の値>", "改行"),
                  note="式はどのシンタックスでも pylike の書き方（関数呼び出しか変数だけ）。答えは次の行に JSON を 1 つ。記号は固定")
    lines.append("")

    # ---- 文 -----------------------------------------------------------------
    lines += rule(
        "statement",
        (seq(tok("assign_begin"), V, tok("assign_op"), E, tok("assign_end")), "代入"),
        (seq(tok("append_begin"), E, tok("append_sep"), E, tok("append_end")), "追加する"),
        (seq(tok("inc_begin"), V, tok("inc_end")), "増やす"),
        (seq(tok("dec_begin"), V, tok("dec_end")), "減らす"),
        "<if>", "<repeat>", "<break>", "<funcdef>", "<return>",
        ("<funcapp>", "呼び出しだけの文。戻り値は捨てる"))
    lines.append("")
    lines += rule("if", seq(tok("if_begin"), "<condition>", tok("if_then"), B, "<else>?", tok("if_end")))
    lines.append("")
    conditions = [(seq(tok(f"{p}_begin"), E, tok(f"{p}_sep"), E, tok(f"{p}_end")), op)
                  for p, op in (("ne", "X != Y"), ("lt", "X < Y"), ("gt", "X > Y"),
                                ("le", "X <= Y"), ("ge", "X >= Y"), ("eq", "X == Y"))]
    lines += rule("condition", *conditions)
    lines.append("")
    lines += rule("else", seq(tok("else_begin"), B, tok("else_end")))
    lines.append("")
    lines += rule("repeat", seq(tok("repeat_begin"), E, tok("repeat_do"), B, tok("repeat_end")))
    lines.append("")
    lines += rule("break", tok("break"))
    lines.append("")
    lines += rule("funcdef", seq(tok("def_begin"), I, tok("def_name_end"), tok("params_begin"),
                                 many(I, tok("param_sep")), tok("params_end"), B, tok("def_end")))
    lines.append("")
    lines += rule("return", seq(tok("return_begin"), E, tok("return_end")))
    lines.append("")

    # ---- 式 -----------------------------------------------------------------
    if syn.call == "args_first":
        funcapp = seq(tok("call_begin"), many(E, tok("arg_sep")), tok("call_name_end"), I, tok("call_end"))
        call_note = "引数が先（call: args_first）"
    else:
        funcapp = seq(tok("call_begin"), I, tok("call_name_end"), many(E, tok("arg_sep")), tok("call_end"))
        call_note = ""
    expr_alts = [("<string>", "文字列"), ("<number>", "数"), "<boolean>", "<none>", "<list>"]
    if syn.index == "prefix":
        expr_alts.append((seq(tok("index_begin"), V, tok("index_sep"), E, tok("index_end")), "配列の添字（prefix）"))
    if "neg_begin" in syn.tokens:
        expr_alts.append((seq(tok("neg_begin"), E, tok("neg_end")), "符号の反転"))
    expr_alts.append(("<funcapp>", "関数呼び出し"))
    if "grouping_begin" in syn.tokens:
        expr_alts.append(("<grouping>", "式の括弧。中の式そのまま"))
    expr_alts.append(V)
    lines += rule("expression", *expr_alts)
    lines.append("")
    lines += rule("boolean", tok("true"), tok("false"))
    lines.append("")
    lines += rule("none", tok("none"))
    lines.append("")
    lines += rule("list", seq(tok("list_begin"), many(E, tok("list_sep")), tok("list_end")))
    lines.append("")
    if syn.index == "prefix":
        lines += rule("variable", I)
    else:
        lines += rule("variable", I, (seq(V, tok("index_begin"), E, tok("index_end")), "配列の添字（postfix）"))
    lines.append("")
    lines += rule("identifier", ("<letters>", "名前"),
                  (seq(tok("quote_begin"), "<characters>", tok("quote_end")), "引用した名前"))
    lines.append("")
    if "grouping_begin" in syn.tokens:
        lines += rule("grouping", seq(tok("grouping_begin"), E, tok("grouping_end")))
        lines.append("")
    lines += rule("funcapp", funcapp, note=call_note)
    lines.append("")

    # ---- 字句 ---------------------------------------------------------------
    lines.append("# 字句（正規表現）")
    for name in ("letters", "number", "string", "characters"):
        lines.append(f"<{name}>".ljust(14) + f"::= /{syn.lexical[name]}/")

    # ---- 記号の正規表現（固定の文字列でないものだけ） -----------------------------------
    odd = []
    for name, pattern in syn.tokens.items():
        text = text_of(name)
        if text and pattern not in VIRTUAL_NAMES and re.sub(r"\\(.)", r"\1", pattern) != text:
            odd.append((name, pattern))
    if odd:
        lines += ["", "# 記号の正規表現（上の文法では、書き出す形を示した）"]
        width = max(len(n) for n, _ in odd)
        lines += [f"{n.ljust(width)} = /{p}/" for n, p in odd]
    if "block_sep" in syn.tokens and not text_of("block_sep"):
        lines += ["", "# block_sep は空（文は記号なしで続く）"]
    return "\n".join(lines).rstrip("\n") + "\n"
