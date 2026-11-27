"""kolangeval.jsonl の評価。`kolang eval SYNTAX`。

各問の `pylike`（正解コード）を SYNTAX に変換し、変換後のコードを読み直して、`doctest` で動作を確かめる。
コードを作る部分は `Solver`（問題と SYNTAX を受け取ってコードを返す関数）で差し替えられる。
将来は、モデルに `prompt` を渡して SYNTAX のコードを生成する Solver を作れば、同じ採点でテストできる。
"""

from __future__ import annotations

import io
import json
import os
import re
import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from .combinators import ParseError
from .parser import make_parser, parse
from .syntax import Syntax
from .unparser import convert, defined_names

DEFAULT_FILE = Path(__file__).resolve().parent / "kolangeval.jsonl"
EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
SPEC_DIR = Path(__file__).resolve().parent / "spec"
RESULTS_DIR = "results"
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"

# 問題（jsonl の 1 行）と、評価するシンタックスから、そのシンタックスのコードを返す。
Solver = Callable[[dict, Syntax], str]
class FatalGenerationError(ValueError):
    """認証の失敗など、何問やっても直らないエラー。不合格にせず、評価を止める。"""


class Generation(str):
    """モデルの返答（生の出力）に、トークン数を添えたもの。ただの str でも Generator の返り値にできる（数は null）。"""
    input_tokens: Optional[int] = None      # 入力（チャットテンプレートと書き出しを含む）
    output_tokens: Optional[int] = None     # 新しく生成した分

    def __new__(cls, text: str, input_tokens: Optional[int] = None, output_tokens: Optional[int] = None):
        self = super().__new__(cls, text)
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        return self


# 問題と syntax から、モデルの返答（生の出力。コードは extract_code で取り出す）を返す。
Generator = Callable[[dict, Syntax], str]


@dataclass
class Result:
    task_id: str
    ok: bool
    passed: int = 0
    total: int = 0
    reason: str = ""
    skipped: bool = False        # 正解（pylike）がない問題。採点せず、分母にも入れない


def load_problems(path=DEFAULT_FILE) -> list:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def reference_solver(problem: dict, syntax: Syntax) -> str:
    """正解の pylike コードを、syntax に変換する（モデルを使わない既定の Solver）。"""
    return convert(problem["pylike"], "pylike", syntax)


def spec_path(name: str) -> Optional[Path]:
    """`--context` の名前 → `kolang/spec/NAME.md`（`.md` 付きでも可）。なければ None。"""
    f = SPEC_DIR / (name if name.endswith(".md") else name + ".md")
    return f if f.is_file() else None


def convert_spec(text: str, syntax: Syntax) -> str:
    """仕様の文書の ```シンタックス ブロック（pylike など）を、syntax に変換する（文章は残す。読めないブロックは触らない）。"""
    from .kofile import map_blocks

    def one(spec: str, code: str):
        try:
            return syntax.name, convert(code, spec, syntax)
        except Exception:
            return None
    return map_blocks(text, one)[0].rstrip()


def build_context(syntax: Syntax, path: Optional[str] = None) -> str:
    """モデルに渡す言語の説明（コンテキスト）。

    path はコンマ区切りの項目の並びで、最初に examples（`kolang/examples/*.ko` を syntax に変換）を置き、
    項目を指定の順に足す。項目は次のどれか:
    - `none`: 何も足さない（`none` だけなら空のコンテキスト。システムメッセージなし）。
    - `snippet`: `snippet.SNIPPETS`（そのシンタックスで書けないものは省く）。
    - `ebnf`: `show_ebnf` の BNF。
    - 存在するファイルのパス: 中身をそのまま使う（単独なら examples も足さず、その中身だけ）。
    - NAME: `kolang/spec/NAME.md` の ```pylike などのブロックを syntax に変換したもの。
    """
    items = [x.strip() for x in path.split(",") if x.strip()] if path else []
    if items == ["none"]:
        return ""
    if len(items) == 1 and Path(items[0]).is_file():
        return Path(items[0]).read_text(encoding="utf-8")
    from .kofile import join_ko, split_ko
    parts = []
    if "none" not in items:
        parts.append("以下は kolang のコードの例です。同じ書き方でコードを書いてください。")
        for f in sorted(EXAMPLES_DIR.glob("*.ko")):
            spec, code = split_ko(f.read_text(encoding="utf-8"))
            parts.append(f"# {f.name}\n" + join_ko(syntax.name, convert(code, spec, syntax)).rstrip())
    for item in items:
        if item == "none":
            continue
        if item == "snippet":
            from .snippet import SNIPPETS
            from .unparser import UnparseError, unparse
            parts.append("以下は、構文ごとの小さな例です。")
            for label, tree in SNIPPETS.items():
                try:
                    text = unparse(tree, syntax)
                except UnparseError:
                    continue
                parts.append(f"# snippet: {label}\n" + join_ko(syntax.name, text).rstrip())
        elif item == "ebnf":
            from .ebnf import show_ebnf
            parts.append("以下は、このシンタックスの文法（BNF）です。\n" + show_ebnf(syntax).rstrip())
        elif Path(item).is_file():
            parts.append(Path(item).read_text(encoding="utf-8").rstrip())
        elif spec_path(item):
            parts.append(convert_spec(spec_path(item).read_text(encoding="utf-8"), syntax))
        else:
            raise OSError(f"{item}: snippet / ebnf / none / ファイル / kolang/spec/{item}.md のどれでもありません")
    return "\n\n".join(parts)


def extract_code(text: str) -> str:
    """モデルの出力から ``` で囲まれたコードを取り出す（囲みがなければそのまま）。"""
    m = re.search(r"```[^\n]*\n(.*?)(?:```|\Z)", text, re.S)
    return (m.group(1) if m else text).strip("\n") + "\n"


def entry_header(problem: dict, syntax: Syntax) -> str:
    """正解（pylike）の entry_point の関数定義の、本体より前の部分を syntax で書いたもの。

    本体の先頭だけが違う 2 つの FuncDef を出力して、共通の接頭辞を取る（空白で終わらなければ、直前の空白まで戻す）。
    正解がない・entry_point の定義がなければ空。
    """
    import os
    from . import ast as K
    from .unparser import unparse
    if not problem.get("pylike"):
        return ""
    fd = next((s for s in parse(problem["pylike"], "pylike").stmts
               if isinstance(s, K.FuncDef) and s.name == problem.get("entry_point")), None)
    if fd is None:
        return ""
    texts = [unparse(K.Block((K.FuncDef(fd.name, fd.params, K.Block((stmt,))),)), syntax)
             for stmt in (K.Return(K.Num(0)), K.Assign(K.Var("x"), K.Num(0)))]
    head = os.path.commonprefix(texts)
    return head if not head or head[-1].isspace() else head[:head.rfind(" ") + 1]


def make_hf_generator(model_name: str = DEFAULT_MODEL, context: str = "", device: Optional[str] = None,
                      max_new_tokens: int = 1024) -> Generator:
    """Hugging Face のモデルで返答（生の出力）を作る関数。context をシステムメッセージ、prompt をユーザーメッセージにする。

    返り値の先頭は、こちらで書いておいた書き出し（``` とヘッダ）。コードは `extract_code` で取り出す。"""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if device is None:
        device = ("cuda" if torch.cuda.is_available()
                  else "mps" if torch.backends.mps.is_available() else "cpu")
    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name).to(device).eval()

    @torch.no_grad()
    def generate(problem: dict, syntax: Syntax) -> str:
        messages = ([{"role": "system", "content": context}] if context else [])
        messages.append({"role": "user", "content": problem["prompt"]})
        # 返答の書き出し（``` と entry_point の関数定義のヘッダ）はこちらで書いておき、続きを生成させる
        prefill = f"```{syntax.name}\n" + entry_header(problem, syntax)
        text = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False) + prefill
        ids = tok(text, return_tensors="pt", add_special_tokens=False).to(device)
        out = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False,
                             pad_token_id=tok.pad_token_id or tok.eos_token_id)
        n_in = ids["input_ids"].shape[1]
        return Generation(prefill + tok.decode(out[0, n_in:], skip_special_tokens=True),
                          n_in, out.shape[1] - n_in)

    return generate


def default_output_name(syntax: Syntax, model: str, difficulty: Optional[Iterable[int]] = None) -> str:
    """jsonl の既定の出力先 results/kolangeval_<syntax>_<model>[_d<N>].jsonl。

    ファイル名に使えない文字は _ にする。difficulty（-d）の指定があれば _d1、複数なら _d1_3 のように付ける。"""
    import re as _re
    safe = lambda t: _re.sub(r"[^A-Za-z0-9._-]+", "_", t).strip("_")
    d = "".join(f"_d{n}" if i == 0 else f"_{n}" for i, n in enumerate(sorted(set(difficulty)))) if difficulty else ""
    return f"{RESULTS_DIR}/kolangeval_{safe(syntax.name)}_{safe(model)}{d}.jsonl"


def is_claude(model_name: str) -> bool:
    return model_name.startswith("claude")


def make_claude_generator(model_name: str, context: str = "", max_tokens: int = 16000) -> Generator:
    """Anthropic API（Claude）で返答を作る関数。`claude-haiku-5.5` のように . で書いても `claude-haiku-5-5` にする。

    新しいモデルは assistant の書き出し（prefill）を受け付けない（400）ので、書き出す内容（``` とヘッダ）は
    ユーザーメッセージの指示として渡す。temperature は既定のまま（モデルによっては変更できない）。
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError("環境変数 ANTHROPIC_API_KEY が設定されていません。"
                         "export ANTHROPIC_API_KEY=sk-ant-... のように設定してから実行してください")
    import anthropic
    model_id = model_name.replace(".", "-")
    client = anthropic.Anthropic()

    def generate(problem: dict, syntax: Syntax) -> str:
        opening = f"```{syntax.name}\n" + entry_header(problem, syntax)
        user = (problem["prompt"] + "\n\nWrite your answer as a single code block. "
                "Begin the code block exactly like this, then continue from there:\n" + opening)
        kwargs = {"system": [{"type": "text", "text": context, "cache_control": {"type": "ephemeral"}}]} if context else {}
        try:
            msg = client.messages.create(model=model_id, max_tokens=max_tokens,
                                         messages=[{"role": "user", "content": user}], **kwargs)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise FatalGenerationError(
                "Anthropic API の認証に失敗しました（ANTHROPIC_API_KEY が無効です）。"
                "正しいキーを export ANTHROPIC_API_KEY=sk-ant-... で設定してから実行してください") from e
        u = msg.usage
        n_in = u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
        return Generation("".join(b.text for b in msg.content if b.type == "text"), n_in, u.output_tokens)

    return generate


def to_record(problem: dict, result: Result, syntax: Syntax, model: Optional[str],
              output: str, code: str) -> dict:
    """jsonl の 1 行。output は生の出力（input_tokens / output_tokens はモデルが数えたとき）、code は取り出したコード、error_message は失敗の理由（なければ null）。"""
    return {"task_id": result.task_id, "model": model, "syntax": syntax.name,
            "prompt": problem["prompt"], "output": str(output),
            "input_tokens": getattr(output, "input_tokens", None),
            "output_tokens": getattr(output, "output_tokens", None), "code": code,
            "doctest": {"ok": result.ok, "passed": result.passed, "total": result.total},
            "error_message": result.reason or None}


TIME_LIMIT = 30   # 1 問の実行（プログラム + doctest）の制限時間（秒）


@contextmanager
def time_limit(seconds: int = TIME_LIMIT):
    """seconds 秒を超えたら TimeoutError。signal.alarm なので、Unix のメインスレッドだけ（それ以外は制限なし）。"""
    if not hasattr(signal, "SIGALRM") or threading.current_thread() is not threading.main_thread():
        yield
        return

    def on_alarm(signum, frame):
        raise TimeoutError(f"{seconds} 秒を超えた")
    old = signal.signal(signal.SIGALRM, on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def check(problem: dict, syntax: Syntax, solver: Solver = reference_solver) -> Result:
    """1 問を、コードの用意 → 読み込み → 実行 → doctest の順に確かめる。"""
    from .pyeval import PyEval
    task = problem["task_id"]
    if not problem.get("pylike") and solver is reference_solver:
        return Result(task, False, reason="正解の pylike コードがない", skipped=True)
    try:
        code = solver(problem, syntax)
        program = parse(code, syntax)
        # doctest の式は全シンタックスで pylike の書き方。標準関数の名前は parse が syntax の名前にする
        then = parse(problem["doctest"], syntax, defined_names(program))
    except FatalGenerationError:
        raise
    except Exception as e:                           # noqa: BLE001  変換・生成・構文の失敗は、不合格の理由にする
        return Result(task, False, reason=f"{type(e).__name__}: {e}".splitlines()[0])
    interp = PyEval(stdout=io.StringIO(), syntax=syntax)
    reason = ""
    try:
        with time_limit():
            interp.run(program)
            interp.run(then)
    except Exception as e:                           # noqa: BLE001
        reason = f"{'SyntaxError' if isinstance(e, SyntaxError) else type(e).__name__}: {e}"
    total = len(interp.doctests)
    passed = sum(1 for d in interp.doctests if d.ok)
    if not reason and total == 0:
        reason = "doctest がない"
    elif not reason and passed < total:
        reason = f"doctest が {total - passed} 件不一致"
    return Result(task, not reason, passed, total, reason)


def evaluate_recorded(syntax: Syntax, problems: Iterable[dict], generate: Generator,
                      model: Optional[str] = None) -> Iterable[dict]:
    """1 問ずつ、生成 → コードの取り出し → 採点して、jsonl の行（dict）を返す。"""
    for p in problems:
        outputs = []

        def solver(problem, syn, _outputs=outputs):
            _outputs.append(generate(problem, syn))
            return extract_code(_outputs[-1])
        result = check(p, syntax, solver)
        output = outputs[0] if outputs else ""
        yield to_record(p, result, syntax, model, output, extract_code(output) if outputs else "")


def evaluate(syntax: Syntax, problems: Iterable[dict], solver: Solver = reference_solver) -> list:
    return [check(p, syntax, solver) for p in problems]
