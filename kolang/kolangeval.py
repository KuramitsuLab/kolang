"""kolangeval.jsonl の評価。`kolang eval SYNTAX`。

各問の `pylike`（正解コード）を SYNTAX に変換し、変換後のコードを読み直して、`doctest` で動作を確かめる。
コードを作る部分は `Solver`（問題と SYNTAX を受け取ってコードを返す関数）で差し替えられる。
将来は、モデルに `prompt` を渡して SYNTAX のコードを生成する Solver を作れば、同じ採点でテストできる。
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from .combinators import ParseError
from .parser import make_parser, parse
from .syntax import Syntax
from .unparser import convert, defined_names

DEFAULT_FILE = Path(__file__).resolve().parent / "kolangeval.jsonl"

# 問題（jsonl の 1 行）と、評価するシンタックスから、そのシンタックスのコードを返す。
Solver = Callable[[dict, Syntax], str]


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
    except Exception as e:                           # noqa: BLE001  変換・生成・構文の失敗は、不合格の理由にする
        return Result(task, False, reason=f"{type(e).__name__}: {e}".splitlines()[0])
    interp = PyEval(stdout=io.StringIO(), syntax=syntax)
    reason = ""
    try:
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


def evaluate(syntax: Syntax, problems: Iterable[dict], solver: Solver = reference_solver) -> list:
    return [check(p, syntax, solver) for p in problems]
