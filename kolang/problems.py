"""`kolang problems`: `kolang eval --model` の結果（results/*.jsonl）を、問題ごとに集計して CSV にする。"""
import csv
import io
import json
import re
from collections import Counter, defaultdict
from typing import Iterable, List

COLUMNS = ["task_id", "runs", "passed", "pass_rate", "parse_error", "name_error",
           "doctest_mismatch", "other_error", "no_code", "top_reason"]


def classify(rec: dict) -> tuple:
    """失敗の (種別, 理由) を返す。合格なら ("", "")。理由は位置・件数を落として数えやすくする。"""
    dt = rec.get("doctest") or {}
    if dt.get("ok"):
        return "", ""
    msg = str(rec.get("error_message") or "").strip()
    if not rec.get("code"):
        return "no_code", msg or "コードを取り出せない"
    first = msg.splitlines()[0] if msg else "不明"
    if first.startswith("ParseError"):
        return "parse_error", re.sub(r"^ParseError: \d+:\d+: ", "ParseError: ", first)
    if first.startswith("NameError"):
        return "name_error", first
    if first.startswith("doctest"):
        return "doctest_mismatch", "doctest の不一致"
    return "other_error", first


def cell(results: List[str]) -> str:
    """1 回なら "OK" か失敗の種別。複数回なら "合格数/回数"。"""
    if len(results) == 1:
        return results[0]
    return f"{results.count('OK')}/{len(results)}"


def task_key(task_id: str):
    m = re.search(r"(\d+)$", task_id)
    return (int(m.group(1)) if m else 10**9, task_id)


def load_records(paths: Iterable[str]) -> List[dict]:
    recs = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    recs.append(json.loads(line))
    return recs


def summarize(recs: List[dict]) -> List[dict]:
    groups = defaultdict(list)
    for r in recs:
        groups[r["task_id"]].append(r)
    rows = []
    for tid in sorted(groups, key=task_key):
        rs = groups[tid]
        kinds, reasons = Counter(), Counter()
        per_syn = defaultdict(list)    # シンタックス → 各試行の結果（"OK" か失敗の種別）
        for r in rs:
            kind, reason = classify(r)
            per_syn[r.get("syntax", "")].append(kind or "OK")
            if kind:
                kinds[kind] += 1
                reasons[reason] += 1
        passed = len(rs) - sum(kinds.values())
        top = "; ".join(f"{n}x {reason}" for reason, n in reasons.most_common(3))
        rows.append({
            "task_id": tid, "runs": len(rs), "passed": passed,
            "pass_rate": f"{passed / len(rs):.3f}",
            **{k: kinds.get(k, 0) for k in ("parse_error", "name_error", "doctest_mismatch", "other_error", "no_code")},
            "top_reason": top,
            **{syn: cell(res) for syn, res in per_syn.items()},
        })
    return rows


def to_csv(rows: List[dict]) -> str:
    buf = io.StringIO()
    syntaxes = sorted({k for r in rows for k in r} - set(COLUMNS))
    w = csv.DictWriter(buf, fieldnames=COLUMNS + syntaxes, restval="", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
