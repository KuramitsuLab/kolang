"""シンタックスと LLM の親和度を測る。

同じ AST（`snippet.SNIPPETS`）を各シンタックスで出力し、言語モデルでパープレキシティ（PPL）を求める。
シンタックスごとにトークン数が違うので、PPL（1 トークンあたり）だけでは比べにくい。
そこで次の 3 つを並べる。同じ AST の比較では、**total NLL（nats）**がいちばん公平。

    NLL   : 負の対数尤度の合計（nats）。小さいほどモデルにとって「ありそうな」コード
    tok   : トークン数
    PPL   : exp(NLL / tok)
    bpc   : bits per char = NLL / (文字数 * ln 2)。トークナイザの違いをならした指標

    kolang modelppl pylike jalike lisplike jslike           既定モデルで
    kolang modelppl -m allenai/OLMo-2-0425-1B pylike "jalike:jslike(assign)"
    kolang modelppl pylike --snippets assign,index --show   出力したコードも見る
    kolang modelppl pylike --json out.json                  結果を JSON でも保存
    python3 -m kolang.modelppl SYNTAX...                    同じ

結果は CSV（既定 modelppl.csv。列は model, syntax, NLL, tokens, PPL, bpc）に書く。詳しくは modelppl.md。

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
from .syntax import SYNTAX_DIR, load_syntax
from .unparser import unparse

DEFAULT_SYNTAXES = ("pylike", "jalike", "lisplike", "jslike")
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
CSV_COLUMNS = ("model", "syntax", "NLL", "tokens", "PPL", "bpc")


def read_csv(path: str) -> "list[dict]":
    """CSV の行（辞書）を返す。model 列のない古い形式は、既定モデルで測ったものとして読む。"""
    with open(path, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("syntax") or "").strip()]
    for r in rows:
        if not r.get("model"):
            r["model"] = DEFAULT_MODEL
        if not r.get("tokens"):
            r["tokens"] = r.get("tok", "")
    return rows


def write_csv(path: str, model: str, summary: Sequence[dict]) -> None:
    """(model, syntax) をキーに、model, syntax, NLL, tokens, PPL, bpc を書く。
    すでにある行は置き換え、ほかのモデル・シンタックスの行はそのまま残す。"""
    rows = read_csv(path) if os.path.exists(path) else []
    for r in summary:
        new = {"model": model, "syntax": r["syntax"], "NLL": f"{r['nll']:.2f}", "tokens": r["tokens"],
               "PPL": f"{r['ppl']:.3f}", "bpc": f"{r['bpc']:.4f}"}
        for i, old in enumerate(rows):
            if old["model"] == model and old["syntax"].strip() == r["syntax"]:
                rows[i] = new
                break
        else:
            rows.append(new)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for row in rows:
            w.writerow([row.get(c, "") for c in CSV_COLUMNS])


def expand_all(specs: Sequence[str]) -> "list[str]":
    """`all` を、syntaxes/ の全シンタックス（名前順）に置き換える。重複は落とす。"""
    out: "list[str]" = []
    for spec in specs:
        out += [p.stem for p in sorted(SYNTAX_DIR.glob("*.json"))] if spec == "all" else [spec]
    return list(dict.fromkeys(out))


def main(argv: Optional[Sequence[str]] = None, scorer: Optional[Scorer] = None,
         prog: str = "modelppl") -> int:
    ap = argparse.ArgumentParser(prog=prog, description="シンタックスごとの LLM パープレキシティを測る")
    ap.add_argument("syntaxes", nargs="*", metavar="SYNTAX",
                    help="シンタックス名（カスケード可: jalike:jslike(assign)）。複数なら全部で出力できたスニペットだけで比べる。"
                         "`all` は syntaxes/ の全シンタックス")
    ap.add_argument("--csv", default=CSV_DEFAULT, metavar="FILE",
                    help=f"結果の CSV（既定 {CSV_DEFAULT}。列は {', '.join(CSV_COLUMNS)}）。(model, syntax) の行を置き換え、なければ足す")
    ap.add_argument("--no-csv", action="store_true", help="CSV に書かない")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Hugging Face のモデル名（既定 {DEFAULT_MODEL}）")
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
    syntaxes = expand_all(args.syntaxes)
    if not syntaxes:
        print("エラー: SYNTAX を指定する（例: kolang modelppl pylike jalike）", file=sys.stderr)
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
        write_csv(args.csv, args.model, summarize(results, syntaxes))
        print(f"CSV: {args.csv}", file=sys.stderr)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([{**asdict(r), "ppl": r.ppl, "bpc": r.bpc} for r in results],
                      f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
