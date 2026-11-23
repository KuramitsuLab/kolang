"""シンタックスと LLM の親和度を測る。

同じ AST（`snippet.SNIPPETS`）を各シンタックスで出力し、言語モデルでパープレキシティ（PPL）を求める。
シンタックスごとにトークン数が違うので、PPL（1 トークンあたり）だけでは比べにくい。
そこで次の 3 つを並べる。同じ AST の比較では、**total NLL（nats）**がいちばん公平。

    NLL   : 負の対数尤度の合計（nats）。小さいほどモデルにとって「ありそうな」コード
    tok   : トークン数
    PPL   : exp(NLL / tok)
    bpc   : bits per char = NLL / (文字数 * ln 2)。トークナイザの違いをならした指標

    python3 -m kolang.modelppl                              pylike ja lisplike jslike を既定モデルで
    python3 -m kolang.modelppl -m allenai/OLMo-2-0425-1B -s pylike ja "ja:jslike(assign)"
    python3 -m kolang.modelppl --snippets assign,index --show   出力したコードも見る
    python3 -m kolang.modelppl --json out.json              結果を JSON でも保存
    kolang modelppl                                         同じ（サブコマンド）

結果は CSV（既定 modelppl.csv）にも書く。詳しくは modelppl.md。

torch / transformers は計測するときだけ読む（import は遅延）。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import math
import sys
from dataclasses import dataclass, asdict
from typing import Callable, Optional, Sequence

from .snippet import SNIPPETS
from .syntax import load_syntax
from .unparser import unparse

DEFAULT_SYNTAXES = ("pylike", "ja", "lisplike", "jslike")
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"

# 1 つのテキストを採点する関数: text → (NLL の合計 nats, 予測したトークン数)
Scorer = Callable[[str], "tuple[float, int]"]


@dataclass
class Result:
    syntax: str
    snippet: str
    chars: int = 0
    tokens: int = 0
    nll: float = 0.0
    error: Optional[str] = None       # 出力できなかったときの理由（そのときは他は 0）
    text: str = ""

    @property
    def ppl(self) -> float:
        return math.exp(self.nll / self.tokens) if self.tokens else float("nan")

    @property
    def bpc(self) -> float:
        return self.nll / (self.chars * math.log(2)) if self.chars else float("nan")


def make_hf_scorer(model_name: str = DEFAULT_MODEL, device: Optional[str] = None) -> Scorer:
    """Hugging Face の因果言語モデルで採点する関数を作る。

    先頭に BOS（なければ EOS）を 1 つ置き、最初のトークンも予測の対象にする。
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if device is None:
        device = ("cuda" if torch.cuda.is_available()
                  else "mps" if torch.backends.mps.is_available() else "cpu")
    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name).to(device).eval()
    start = tok.bos_token_id if tok.bos_token_id is not None else tok.eos_token_id
    if start is None:
        raise RuntimeError(f"{model_name}: BOS も EOS もないトークナイザは未対応")

    @torch.no_grad()
    def score(text: str):
        ids = tok(text, add_special_tokens=False)["input_ids"]
        if not ids:
            return 0.0, 0
        ids = [start] + ids
        x = torch.tensor([ids], device=device)
        logits = model(x).logits[0, :-1].float()
        logp = torch.log_softmax(logits, dim=-1)
        target = x[0, 1:]
        nll = -logp.gather(1, target[:, None]).sum().item()
        return nll, len(ids) - 1

    return score


def measure(syntaxes: Sequence[str], scorer: Scorer,
            snippets: Optional[Sequence[str]] = None) -> "list[Result]":
    """各シンタックス × 各スニペットを出力して採点する。出力できないものは error に理由を入れる。"""
    names = list(snippets) if snippets else list(SNIPPETS)
    unknown = [n for n in names if n not in SNIPPETS]
    if unknown:
        raise KeyError(f"知らないスニペット: {', '.join(unknown)}（--list-snippets で一覧）")
    out = []
    for spec in syntaxes:
        syn = load_syntax(spec, verify=False)
        for name in names:
            try:
                text = unparse(SNIPPETS[name], syn)
            except Exception as e:
                out.append(Result(spec, name, error=f"{type(e).__name__}: {str(e).splitlines()[0]}"))
                continue
            nll, n = scorer(text)
            out.append(Result(spec, name, len(text), n, nll, text=text))
    return out


def summarize(results: Sequence[Result], syntaxes: Sequence[str]) -> "list[dict]":
    """シンタックスごとの集計。全シンタックスで出力できたスニペットだけを使う（条件をそろえる）。"""
    ok = {s: {r.snippet: r for r in results if r.syntax == s and r.error is None} for s in syntaxes}
    common = set.intersection(*(set(d) for d in ok.values())) if ok else set()
    rows = []
    for s in syntaxes:
        rs = [ok[s][n] for n in common]
        nll, tok, chars = (sum(getattr(r, k) for r in rs) for k in ("nll", "tokens", "chars"))
        rows.append({
            "syntax": s, "snippets": len(rs), "nll": nll, "tokens": tok, "chars": chars,
            "ppl": math.exp(nll / tok) if tok else float("nan"),
            "bpc": nll / (chars * math.log(2)) if chars else float("nan"),
            "skipped": len([r for r in results if r.syntax == s and r.error]),
        })
    return rows


def format_report(results: Sequence[Result], syntaxes: Sequence[str], show: bool = False) -> str:
    lines = []
    if show:
        for r in results:
            lines.append(f"--- {r.syntax} / {r.snippet}" + (f"  [出力不可: {r.error}]" if r.error else
                         f"  NLL={r.nll:.1f} tok={r.tokens} PPL={r.ppl:.2f}"))
            if not r.error:
                lines.append(r.text)
        lines.append("")
    rows = summarize(results, syntaxes)
    w = max(len(s) for s in syntaxes)
    lines.append(f"{'syntax':<{w}}  {'n':>3}  {'NLL':>9}  {'tok':>6}  {'chars':>6}  {'PPL':>8}  {'bpc':>6}  skip")
    for r in sorted(rows, key=lambda r: r["nll"]):
        lines.append(f"{r['syntax']:<{w}}  {r['snippets']:>3}  {r['nll']:>9.1f}  {r['tokens']:>6}  "
                     f"{r['chars']:>6}  {r['ppl']:>8.2f}  {r['bpc']:>6.3f}  {r['skipped']}")
    lines.append("（NLL 順。n・NLL・PPL は全シンタックスで出力できたスニペットだけの合計。NLL が小さいほど親和度が高い）")
    return "\n".join(lines)


CSV_DEFAULT = "modelppl.csv"
CSV_COLUMNS = ("NLL", "tok", "char", "PPL", "bpc")     # 第一カラム syntax のあとに書く列


def read_csv(path: str) -> "tuple[list, list]":
    """CSV を (ヘッダ, 行の辞書のリスト) で返す。第一カラムがシンタックス。空の行は捨てる。"""
    with open(path, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
    if not rows:
        return ["syntax"], []
    header = [h.strip() for h in rows[0]]
    return header, [dict(zip(header, r)) for r in rows[1:] if r[0].strip()]


def write_csv(path: str, header: Sequence[str], rows: Sequence[dict], summary: Sequence[dict]) -> None:
    """第一カラムのシンタックスごとに、NLL tok char PPL bpc を埋めて書く。ほかの列はそのまま残す。"""
    by = {r["syntax"]: r for r in summary}
    header = list(header)
    for c in CSV_COLUMNS:
        if c not in header:
            header.append(c)
    key = header[0]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for row in rows:
            r = by[row[key].strip()]
            row = dict(row, **{"NLL": f"{r['nll']:.2f}", "tok": r["tokens"], "char": r["chars"],
                               "PPL": f"{r['ppl']:.3f}", "bpc": f"{r['bpc']:.4f}"})
            w.writerow([row.get(h, "") for h in header])


def main(argv: Optional[Sequence[str]] = None, scorer: Optional[Scorer] = None,
         prog: str = "modelppl") -> int:
    ap = argparse.ArgumentParser(prog=prog, description="シンタックスごとの LLM パープレキシティを測る")
    ap.add_argument("-s", "--syntaxes", nargs="+", default=None,
                    help="シンタックス名（カスケード可: ja:jslike(assign)）。"
                         "既定は CSV の第一カラム。CSV がなければ pylike ja lisplike jslike")
    ap.add_argument("--csv", default=CSV_DEFAULT, metavar="FILE",
                    help=f"結果の CSV（既定 {CSV_DEFAULT}）。あれば第一カラムのシンタックスを測って埋め、なければ新規作成")
    ap.add_argument("--no-csv", action="store_true", help="CSV を読み書きしない")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL, help="Hugging Face のモデル名（既定 Qwen/Qwen2.5-Coder-1.5B-Instruct）")
    ap.add_argument("--device", default=None, help="cpu / cuda / mps（既定は自動）")
    ap.add_argument("--snippets", default=None, help="スニペット名をカンマ区切りで（既定は全部）")
    ap.add_argument("--list-snippets", action="store_true", help="スニペット名の一覧を出して終わる")
    ap.add_argument("--show", action="store_true", help="出力したコードと、スニペットごとの値も出す")
    ap.add_argument("--json", metavar="FILE", help="スニペットごとの結果を JSON に保存")
    args = ap.parse_args(argv)

    if args.list_snippets:
        print("\n".join(SNIPPETS))
        return 0
    names = args.snippets.split(",") if args.snippets else None

    header, rows = ["syntax"], []
    if not args.no_csv and os.path.exists(args.csv):
        header, rows = read_csv(args.csv)
    syntaxes = [r[header[0]].strip() for r in rows]
    for sp in (args.syntaxes or ([] if syntaxes else DEFAULT_SYNTAXES)):    # -s は CSV にない分を足す
        if sp not in syntaxes:
            syntaxes.append(sp)
            rows.append({header[0]: sp})
    if not syntaxes:
        print("エラー: 測るシンタックスがない", file=sys.stderr)
        return 2
    if scorer is None:
        print(f"モデルを読み込み中: {args.model}", file=sys.stderr)
        scorer = make_hf_scorer(args.model, args.device)
    try:
        results = measure(syntaxes, scorer, names)
    except KeyError as e:
        print(f"エラー: {e.args[0]}", file=sys.stderr)
        return 2
    print(format_report(results, syntaxes, args.show))
    if not args.no_csv:
        write_csv(args.csv, header, rows, summarize(results, syntaxes))
        print(f"CSV: {args.csv}", file=sys.stderr)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([{**asdict(r), "ppl": r.ppl, "bpc": r.bpc} for r in results],
                      f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
