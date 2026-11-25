"""シンタックス定義（JSON）の読み込み。

空白・コメント・語の区切りの取り決め:

  space          空白の正規表現（既定は半角スペース 1 個以上）。
  comment_begin  コメントの始まり ┐ tokens に書く。comment_begin から最短で comment_end まで。
  comment_end    コメントの終わり ┘ どちらかがなければコメントなし。
                 コメントの本文は AST に残り、変換先のコメントの記号で書き直される。
                 行末で終わる形（comment_end が (?=\n) など）で layout が "none" のときは、
                 変換先の space が改行を読み飛ばせる必要がある。
  word_segment   語を作る 1 文字の正規表現（例 [A-Za-z0-9_]）。トークンが語の文字で終わり、
                 すぐ後ろにも語の文字が続くときは、空白が必須（そこでトークンを切れない）。
                 省略すると、この規則は使わない。

予約語:
  tokens の正規表現の先頭にある固定文字列のうち、名前（lexical.letters）の形をしたものを
  自動で予約語にする（例: "if", "else *:" → if, else）。JSON の "reserved" は追加分。

最上位（toplevel）の書き方（layout が none のとき。indent は常に "bare"）:
  "block"（既定）  プログラム全体を block_begin 〜 block_end で包む
  "bare"           block_begin / block_end なしの、文の並びだけ（JavaScript 風など）

配列の添字（index）の書き方:
  "postfix"（既定）  <variable> index_begin <expression> index_end            x[i]
  "prefix"           index_begin <variable> index_sep <expression> index_end  (get x i)
                     prefix では index_begin が先頭、index_sep が対象と添字のあいだ。

関数呼び出し（call）の書き方:
  "func_first"（既定）  call_begin <名前> call_name_end <引数,...> call_end     f(x, y)
  "args_first"         call_begin <引数,...> call_name_end <名前> call_end     (x, y)におけるfの値
                       args_first では call_name_end が引数と名前のあいだ。

代入（assign）の書き方（tokens.assign.order）:
  "target_first"（既定）  assign_begin <変数> assign_op <式> assign_end     xに1を代入
  "value_first"         assign_begin <式> assign_op <変数> assign_end     1をxに代入

追加（append）の書き方（tokens.append.order）:
  "target_first"（既定）  append_begin <対象> append_sep <値> append_end     xsに1を追加
  "value_first"         append_begin <値> append_sep <対象> append_end     1をxsに追加

出力（unparser）用:
  emit           トークン名 → 出力する文字列。省略したトークンは、正規表現から作った例を使う。
                 空白を足して見た目を整えるために使う（正規表現にマッチする必要がある）。
  tight_before   この正規表現にマッチする文字（例 \\)）の直前では、行末の空白を落とす。
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from .regexgen import leading_literal, sample
from .stdlib import NAMES as STDLIB_NAMES, local_names

# layout が "indent" のとき、トークンに書ける仮想トークン。
# 字句解析の前に、インデントの変化をこれらの 1 文字に置き換える（layout.py）。
NEWLINE, INDENT, DEDENT = "\x01", "\x02", "\x03"
VIRTUAL = {"@NEWLINE": NEWLINE, "@INDENT": INDENT, "@DEDENT": DEDENT}

# doctest 風の例の目印。シンタックスの JSON では変えられない。
DOCTEST_PROMPT = ">>>"

LEXICAL_KEYS = ("letters", "number", "string", "characters")
SYNTAX_DIR = Path(__file__).parent / "syntaxes"


@dataclass(frozen=True)
class Syntax:
    name: str
    layout: str                    # "indent" | "none"
    space: str                     # 空白の正規表現
    comment_begin: Optional[str]
    comment_end: Optional[str]
    word_segment: Optional[str]
    continuation: Optional[str]    # indent のとき、直前の DEDENT のあとに区切りを入れない行頭（else など）
    tokens: dict
    lexical: dict
    reserved: frozenset
    emit: dict
    index: str = "postfix"         # "postfix" | "prefix"
    call: str = "func_first"       # "func_first"（f(x)）| "args_first"（(x)におけるfの値）
    assign: str = "target_first"   # "target_first"（xに1を代入）| "value_first"（1をxに代入）
    append: str = "target_first"   # "target_first"（xsに1を追加）| "value_first"（1をxsに追加）
    toplevel: str = "block"        # "block"（block_begin〜block_end で包む）| "bare"（文の並びだけ）
    tight_before: Optional[str] = None
    stdlib: dict = field(default_factory=dict)   # 標準ライブラリ関数の名前の変更（標準名 → このシンタックスでの名前）。JSON では "stdlib": {標準名: 名前}

    @property
    def function_names(self) -> dict:
        """標準名 → このシンタックスでの名前（変更のないものは標準名のまま）。"""
        return local_names(self.stdlib)

    @property
    def skip_pattern(self) -> str:
        """トークンの前で読み飛ばすもの: 空白 | コメント | （indent なら）改行。"""
        parts = []
        if self.space:
            parts.append(f"(?:{self.space})")
        if self.comment_begin and self.comment_end:
            # comment_body 群は、コメントの本文を取り出すための名前（Context.skip が読む）。
            parts.append(f"(?:{self.comment_begin})(?P<comment_body>(?s:.*?))(?:{self.comment_end})")
        if self.layout == "indent":
            # 改行のあとには必ず仮想トークンが付くので、改行そのものは読み飛ばしてよい。
            parts.append("\\n")
        return "|".join(parts)


# カスケード（"jalike:jslike(assign,block)"）で、シンタックスから取り込める単位。
# tokens: トークン名、prefix: トークン名の接頭辞、keys: トップレベルのキー、lexical: lexical のキー。
GROUPS = {
    "comment": {"tokens": ("comment_begin", "comment_end")},
    # block は配置（layout）と一緒に読む。インデントと { } は別の配置なので。
    "block": {"prefix": ("block_",), "keys": ("layout", "toplevel")},
    "assign": {"prefix": ("assign_",), "keys": ("assign",)},
    "append": {"prefix": ("append_",), "keys": ("append",)},
    "inc": {"prefix": ("inc_",)},
    "dec": {"prefix": ("dec_",)},
    "if": {"prefix": ("if_",)},
    "else": {"prefix": ("else_",)},
    "repeat": {"prefix": ("repeat_",)},
    "break": {"tokens": ("break",)},
    "def": {"prefix": ("def_", "params_", "param_")},
    "return": {"prefix": ("return_",)},
    "condition": {"prefix": ("ne_", "lt_", "gt_", "le_", "ge_", "eq_")},
    "literal": {"tokens": ("true", "false", "none")},
    "list": {"prefix": ("list_",)},
    "neg": {"prefix": ("neg_",)},
    "grouping": {"prefix": ("grouping_",)},
    "index": {"prefix": ("index_",), "keys": ("index",)},
    "quote": {"prefix": ("quote_",), "lexical": ("characters",)},
    "funcapp": {"prefix": ("call_", "arg_"), "keys": ("call",)},
    "name": {"lexical": ("letters",)},
    "number": {"lexical": ("number",)},
    "string": {"lexical": ("string",)},
    "space": {"keys": ("space", "word_segment", "tight_before")},
    "stdlib": {"keys": ("stdlib",)},      # トップレベルの "stdlib": {"print": ...}
}
GROUPS["call"] = GROUPS["funcapp"]      # 別名
for _g in ("ne", "lt", "gt", "le", "ge", "eq"):
    GROUPS[_g] = {"prefix": (f"{_g}_",)}


def flatten_tokens(data: dict) -> dict:
    """JSON の tokens / emit を、内部の平らな形（"block_begin": ...）にした辞書を返す。

    JSON ではグループにまとめて書く:
        "tokens": {"block": {"begin": "\\{", "sep": ";?", "sep.emit": ";", "end": "\\}"}, "true": "true", ...}
    グループ名 + "_" + キーが、トークン名になる。
    例外は "funcapp"（関数呼び出し）: begin / name_end / end が call_*、arg_sep が arg_sep、order がトップの "call"。"キー.emit" は、そのトークンの出力用の文字列。
    文字列の値は、グループに入らないトークン（true / break など）。平らな形のままの辞書も、そのまま通す。
    """
    tokens, emit = {}, dict(data.get("emit", {}))
    extra = {}
    for key, value in data["tokens"].items():
        if not isinstance(value, dict):
            tokens[key] = value
            continue
        for sub, pattern in value.items():
            if key in ("assign", "append") and sub == "order":
                extra[key] = pattern           # 代入・追加の並び順は、トップの "assign" / "append"
            elif key == "funcapp":
                # funcapp は call_*（begin / name_end / end）と arg_sep、並び順 order（= トップの call）を 1 つにまとめた書き方
                if sub == "order":
                    extra["call"] = pattern
                    continue
                name = sub[:-5] if sub.endswith(".emit") else sub
                full = name if name.startswith("arg_") else f"call_{name}"
                if sub.endswith(".emit"):
                    emit[full] = pattern
                else:
                    tokens[full] = pattern
            elif sub.endswith(".emit"):
                emit[f"{key}_{sub[:-5]}"] = pattern
            else:
                tokens[f"{key}_{sub}"] = pattern
    out = {**data, **extra, "tokens": tokens}
    lexical = data.get("lexical")
    if isinstance(lexical, dict) and isinstance(lexical.get("quote"), dict):
        # lexical.quote は、内部では quote_begin / quote_end のトークン
        out["lexical"] = {k: v for k, v in lexical.items() if k != "quote"}
        for sub, pattern in lexical["quote"].items():
            tokens[f"quote_{sub}"] = pattern
    if emit or "emit" in data:
        out["emit"] = emit
    return out


def _read_json(source) -> dict:
    path = Path(source)
    if not (path.suffix == ".json" or path.parent != Path(".")):
        path = SYNTAX_DIR / f"{source}.json"
    data = flatten_tokens(json.loads(path.read_text(encoding="utf-8")))
    data.setdefault("name", path.stem)
    data["_label"] = str(path)
    return data


def _overlay(base: dict, over: dict, groups: Optional[list], label: str) -> dict:
    """base のうち、groups（None なら全部）だけを over で置き換えた辞書を返す。"""
    if groups is None:
        return dict(over)
    unknown = [g for g in groups if g not in GROUPS]
    if unknown:
        raise ValueError(f"{label}: unknown group {unknown} (available: {', '.join(sorted(GROUPS))})")
    out = {**base, "tokens": dict(base["tokens"]), "lexical": dict(base["lexical"]),
           "emit": dict(base.get("emit", {}))}
    for g in groups:
        spec = GROUPS[g]
        names = [n for n in over["tokens"]
                 if n in spec.get("tokens", ()) or n.startswith(spec.get("prefix", ()))]
        # 取り込み元に無いトークンは、置き換え先からも消す（足りないままにしない）
        for n in [n for n in out["tokens"]
                  if n in spec.get("tokens", ()) or n.startswith(spec.get("prefix", ()))]:
            del out["tokens"][n]
            out["emit"].pop(n, None)
        for n in names:
            out["tokens"][n] = over["tokens"][n]
            if n in over.get("emit", {}):
                out["emit"][n] = over["emit"][n]
        for k in spec.get("keys", ()):
            if k in over:
                out[k] = over[k]
            else:
                out.pop(k, None)
        for k in spec.get("lexical", ()):
            out["lexical"][k] = over["lexical"][k]
    # indent では改行が読み飛ばされるが、none では空白に改行が要る（jalike・pylike のような半角・全角スペースだけの空白に足す）。
    if out.get("layout", "none") == "none":
        space = out.get("space", " +")
        if not re.fullmatch(f"(?:{space})+", "\n"):
            out["space"] = f"{space}|[\\t\\r\\n]+"
    out["reserved"] = sorted(set(base.get("reserved", ())) | set(over.get("reserved", ())))
    return out


def _is_path(text: str) -> bool:
    return Path(text).suffix == ".json" and Path(text).exists()


def load_syntax(source: Union[str, Path], verify: bool = True) -> Syntax:
    """名前（syntaxes/<名前>.json）、JSON ファイルのパス、またはカスケードから読み込む。

    カスケード: "jalike:jslike(assign,block,funcapp)" は、jalike をベースに、jslike の
    assign / block / funcapp のグループだけを取り込む。":" でいくつでもつなげる。
    グループを省略した "jalike:jslike" は、jslike で全部置き換える（= jslike）。

    検査（`verify=False` で止める）。問題があれば警告（UserWarning）を出し、読み込みは続ける。
      1. 構造検査（structure.problems）: トークンの定義だけを見て、衝突の原因を名指しする。
      2. 1 で何も見つからなかったカスケードは、`snippet.SNIPPETS` を出力 → パースして、戻らないものを知らせる。
    """
    text = str(source)
    cascade = is_cascade(text)
    if not cascade:
        data = _read_json(source)
        syn = syntax_from_dict(data, data.pop("_label"))
    else:
        parts = text.split(":")
        data = _read_json(parts[0].strip())
        data.pop("_label")
        for part in parts[1:]:
            m = re.fullmatch(r"\s*([^()]+?)\s*(?:\((.*)\))?\s*", part)
            if not m:
                raise ValueError(f"{text!r}: cannot read {part!r} (expected NAME or NAME(group,...))")
            groups = [g.strip() for g in m.group(2).split(",") if g.strip()] if m.group(2) is not None else None
            over = _read_json(m.group(1))
            over.pop("_label")
            data = _overlay(data, over, groups, text)
        data["name"] = text
        data["description"] = "カスケード: " + text
        syn = syntax_from_dict(data, text)
    if verify:
        _warn_collisions(syn, text, cascade)
    return syn


def is_cascade(source: Union[str, Path]) -> bool:
    """source がカスケード（"jalike:jslike(assign)"）の書き方か。"""
    text = str(source)
    return ":" in text and not _is_path(text)


def collisions(syn: Syntax, cascade: bool) -> list:
    """区切りの衝突の一覧（文章のリスト。なければ空）。load_syntax の検査と `kolang check` が使う。

    構造検査（structure.problems）で見つからなかったカスケードだけ、スニペットの往復も調べる。
    """
    from .structure import problems
    found = problems(syn)
    if not found and cascade:
        from .snippet import failures
        found = [f"{name}: {why}" for name, why in failures(syn)]
        if found:
            found.insert(0, f"スニペット {len(found)} 件が、出力 → パースで元の AST に戻らない")
    return found


def _warn_collisions(syn: Syntax, label: str, cascade: bool) -> None:
    found = collisions(syn, cascade)
    if found:
        lines = "\n".join(f"  {line}" for line in found)
        warnings.warn(f"{label}: 区切りが衝突している\n{lines}", UserWarning, stacklevel=3)


def syntax_from_dict(data: dict, label: str = "<dict>") -> Syntax:
    layout = data.get("layout", "none")
    if layout not in ("indent", "none"):
        raise ValueError(f"{label}: unknown layout {layout!r}")

    data = flatten_tokens(data)
    tokens = dict(data["tokens"])
    comment_begin = tokens.pop("comment_begin", None)
    comment_end = tokens.pop("comment_end", None)
    if bool(comment_begin) != bool(comment_end):
        raise ValueError(f"{label}: comment_begin and comment_end must be given together")

    for name, pattern in tokens.items():
        if pattern.startswith("@"):
            if layout != "indent" or pattern not in VIRTUAL:
                raise ValueError(f"{label}: token {name!r}: {pattern!r} is not allowed here")
            tokens[name] = VIRTUAL[pattern]

    lexical = data["lexical"]
    missing = [k for k in LEXICAL_KEYS if k not in lexical]
    if missing:
        raise ValueError(f"{label}: lexical is missing {missing}")

    index = data.get("index", "postfix")
    if index not in ("postfix", "prefix"):
        raise ValueError(f"{label}: unknown index style {index!r}")
    call = data.get("call", "func_first")
    if call not in ("func_first", "args_first"):
        raise ValueError(f"{label}: unknown call style {call!r}")
    assign = data.get("assign", "target_first")
    if assign not in ("target_first", "value_first"):
        raise ValueError(f"{label}: unknown assign style {assign!r}")
    append = data.get("append", "target_first")
    if append not in ("target_first", "value_first"):
        raise ValueError(f"{label}: unknown append style {append!r}")
    toplevel = data.get("toplevel", "block")
    if toplevel not in ("block", "bare"):
        raise ValueError(f"{label}: unknown toplevel style {toplevel!r}")
    tight_before = data.get("tight_before")

    space = data.get("space", " +")
    word_segment = data.get("word_segment")
    continuation = data.get("continuation")
    if continuation is None and layout == "indent" and tokens.get("else_begin"):
        # 既定は else_begin（else の行頭）。取り込んだグループに合わせて、いつも else と連動する。
        continuation = tokens["else_begin"]
        if word_segment and re.fullmatch(word_segment, sample(continuation)[-1:] or " "):
            continuation = f"(?:{continuation})(?!{word_segment})"
    patterns = {**tokens, **lexical, "space": space,
                "comment_begin": comment_begin or "", "comment_end": comment_end or "",
                "word_segment": word_segment or "", "continuation": continuation or "",
                "tight_before": tight_before or ""}
    for key, pattern in patterns.items():
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"{label}: bad regex in {key!r}: {e}") from None

    emit = dict(data.get("emit", {}))
    for name, texts in emit.items():
        if name not in tokens:
            raise ValueError(f"{label}: emit: unknown token {name!r}")
        # 文字列、または候補の配列（最初が既定。2 つ目以降は random_emit のとき選ばれる）
        choices = texts if isinstance(texts, list) else [texts]
        if not choices or not all(isinstance(t, str) for t in choices):
            raise ValueError(f"{label}: emit: {name!r}: must be a string or a non-empty list of strings")
        for text in choices:
            if not re.fullmatch(tokens[name], text.strip(" ")):
                raise ValueError(f"{label}: emit: {text!r} does not match token {name!r}")

    reserved = extract_reserved(tokens, lexical["letters"]) | frozenset(data.get("reserved", ()))
    stdlib = data.get("stdlib", {})
    if not isinstance(stdlib, dict):
        raise ValueError(f"{label}: stdlib must be an object")
    check_stdlib(stdlib, lexical, reserved, label)

    return Syntax(
        name=data.get("name", label),
        layout=layout,
        space=space,
        comment_begin=comment_begin,
        comment_end=comment_end,
        word_segment=word_segment,
        continuation=continuation,
        tokens=tokens,
        lexical=lexical,
        reserved=reserved,
        emit=emit,
        index=index,
        call=call,
        assign=assign,
        append=append,
        toplevel=toplevel,
        tight_before=tight_before,
        stdlib=stdlib,
    )


def check_stdlib(stdlib: dict, lexical: dict, reserved: frozenset, label: str) -> None:
    """stdlib の名前の変更を検査する: 標準名があること、呼べる名前であること、重複がないこと。"""
    unknown = [k for k in stdlib if k not in STDLIB_NAMES]
    if unknown:
        raise ValueError(f"{label}: stdlib: unknown function {unknown} (available: {', '.join(STDLIB_NAMES)})")
    for std, name in stdlib.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"{label}: stdlib.{std}: the name must be a non-empty string")
        plain = re.fullmatch(lexical["letters"], name) and name not in reserved
        if not (plain or re.fullmatch(lexical["characters"], name)):
            raise ValueError(f"{label}: stdlib.{std}: {name!r} cannot be written as a name in this syntax")
    names = list(local_names(stdlib).values())
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f"{label}: stdlib: duplicate names {dup}")


def extract_reserved(tokens: dict, letters: str) -> frozenset:
    """トークンの正規表現の先頭にある固定文字列のうち、名前の形をしたものを予約語とする。"""
    words = (leading_literal(pattern) for pattern in tokens.values())
    return frozenset(w for w in words if w and re.fullmatch(letters, w))
