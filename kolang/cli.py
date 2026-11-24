"""kolang コマンド。

    kolang --list                          使えるシンタックスの一覧
    kolang --show lisplike                 書き方の例
    kolang show_example ja [NAME...]       スニペット（カスケード検査用の AST。snippet.py）をそのシンタックスで表示
    kolang show_ebnf ja                    そのシンタックスの BNF（kolang.md の規則を、そのシンタックスの記号で）
    kolang conv prog.py -f pylike -t ja    シンタックスの変換（ファイルなしなら標準入力、-o で出力先）
    kolang conv prog.ko -t ja              .ko なら -f は不要（1 行目で指定）
    kolang conv prog.py -f pylike          構文チェックだけ（-t を省略）
    kolang run prog.ko                     .ko は 1 行目の ```シンタックス で指定（-f は不要）。
                                           同じ名前の prog.doctest があれば、続けてテストする
    kolang pass@1 humaneval/*.ko           .ko と .doctest を実行して pass@1 を計算する（--total 164 で分母を指定）
    kolang eval SYNTAX [-i FILE]           kolangeval.jsonl の正解（pylike）を SYNTAX に変換し、doctest で動作を確かめる
                                           （--model NAME [--context FILE] [-o OUT.jsonl] でモデルの生成を採点）
    kolang modelppl [-s SYNTAX...]         シンタックスと LLM の親和度（NLL / PPL）。modelppl.csv を埋める
    kolang run prog.py [-f pylike]         実行する（Python 互換。doctest 風の例は答え合わせ）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from .combinators import ParseError
from .examples import show
from .kofile import is_ko, join_ko, split_ko
from .parser import make_parser, parse
from .syntax import SYNTAX_DIR, Syntax, load_syntax
from .unparser import convert


DOCTEST_EXTENSION = ".doctest"


class CliError(Exception):
    pass


def read_source(path: Optional[str]) -> str:
    if path is None:
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_program(path: Optional[str], spec: Optional[str]) -> tuple:
    """（コード, シンタックスの指定）。`.ko` は 1 行目の指定を使う（-f があれば -f が優先）。"""
    text = read_source(path)
    if is_ko(path):
        ko_spec, text = split_ko(text)
        spec = spec or ko_spec
    return text, spec


def load(name: str) -> Syntax:
    try:
        return load_syntax(name)
    except FileNotFoundError:
        raise CliError(f"シンタックスが見つかりません: {name!r}（kolang --list で一覧を表示）") from None


def add_convert_options(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("file", nargs="?", help="入力ファイル（省略すると標準入力）")
    ap.add_argument("-f", "--from", dest="src", metavar="SYNTAX",
                    help="入力のシンタックス（.ko ファイルなら不要。あれば -f が優先）")
    ap.add_argument("-t", "--to", dest="dst", metavar="SYNTAX",
                    help="出力のシンタックス（省略すると構文チェックだけ行う）")
    ap.add_argument("--no-rename", action="store_true",
                    help="変換で、標準ライブラリ関数の名前（print など）を書き換えない")
    ap.add_argument("--random-emit", "--random_emit", dest="random_emit", type=int, metavar="SEED",
                    help="emit に候補（配列）があるとき、SEED で選ぶ（省略すると常に最初）")
    ap.add_argument("-o", "--output", metavar="FILE",
                    help="出力先のファイル（省略すると標準出力。.ko なら ```シンタックス で包む）")


def build_conv_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kolang conv",
        description="シンタックスを変換する。-t を省略すると、構文チェックだけ行う。",
    )
    add_convert_options(ap)
    return ap


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kolang",
        description="kolang（こ言語）: 書き方（シンタックス）を選べる言語。"
                    "書き方の表示と、シンタックス間の変換ができる。",
        epilog="スニペットの表示は `kolang show_example SYNTAX`、BNF は `kolang show_ebnf SYNTAX`。変換は `kolang conv FILE -t SYNTAX`（kolang conv -h）、実行は `kolang run FILE [-f SYNTAX]`（kolang run -h）。\nシンタックスは、名前（kolang --list に出るもの）か、JSON ファイルのパスで指定する。",
    )
    ap.add_argument("--list", action="store_true", help="使えるシンタックスの一覧を表示する")
    ap.add_argument("--show", metavar="SYNTAX", help="シンタックスの書き方の例を表示する")
    return ap


def list_syntaxes() -> str:
    rows = []
    for path in sorted(SYNTAX_DIR.glob("*.json")):
        description = json.loads(path.read_text(encoding="utf-8")).get("description", "")
        rows.append((path.stem, description))
    width = max((len(n) for n, _ in rows), default=0)
    return "".join(f"{name:<{width}}  {desc}\n" for name, desc in rows)


def run(args: argparse.Namespace, ap: argparse.ArgumentParser) -> int:
    if args.list:
        sys.stdout.write(list_syntaxes())
        return 0
    if args.show:
        sys.stdout.write(show(load(args.show)))
        return 0
    ap.print_help()
    return 2


def convert_command(args: argparse.Namespace, ap: argparse.ArgumentParser) -> int:
    if args.src is None and not is_ko(args.file):
        ap.error("入力のシンタックスを -f/--from で指定してください（.ko ファイルなら不要）")

    source, spec = read_program(args.file, args.src)
    src = load(spec)
    if args.dst is None:
        tree = make_parser(src)(source)
        print(f"OK: {len(tree.stmts)} 個の文")
        return 0
    text = convert(source, src, load(args.dst), rename=not args.no_rename,
                   random_emit=args.random_emit)
    if args.output:
        if is_ko(args.output):
            text = join_ko(args.dst, text)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


def build_run_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kolang run",
        description="プログラムを実行する（Python 互換の評価器）。"
                    "doctest 風の例（>>> 式 の次の行に JSON の答え）があれば、答え合わせをする。",
        epilog="終了コード: 0 成功 / 1 実行時エラーか doctest の不一致 / 2 使い方の誤り。",
    )
    ap.add_argument("file", nargs="?", help="プログラム（省略すると標準入力）")
    ap.add_argument("-f", "--from", dest="src", metavar="SYNTAX", default=None,
                    help="シンタックス（既定: .ko ならファイルの 1 行目、それ以外は pylike）。名前、JSON のパス、カスケード（ja:jslike(assign,block)）")
    return ap


def load_program(path: Optional[str], spec: Optional[str]) -> tuple:
    """（シンタックス, プログラム, then）。`.ko` に同じ名前の `.doctest` があれば then に読む。"""
    from .unparser import defined_names
    source, spec = read_program(path, spec)
    syn = load(spec or "pylike")
    program = parse(source, syn)
    then = None
    if is_ko(path):
        doctest_path = os.path.splitext(path)[0] + DOCTEST_EXTENSION
        if os.path.isfile(doctest_path):         # 同じ名前の .doctest があれば、続けてテストする
            with open(doctest_path, encoding="utf-8") as f:
                then = parse(f.read(), syn, defined_names(program))   # 本体の自作の名前を見る
    return syn, program, then


def run_program(args: argparse.Namespace) -> int:
    from .pyeval import execute
    syn, program, then = load_program(args.file, args.src)
    return execute(program, syntax=syn, then=then)


def check_problem(path: str) -> tuple:
    """1 問を実行して（合格か, doctest の合格数, doctest の件数, 理由）を返す。

    合格 = 構文解析と実行が成功し、doctest が 1 件以上あって、すべて一致。プログラムの出力は捨てる。
    """
    import io
    from .pyeval import PyEval
    try:
        syn, program, then = load_program(path, None)
    except (CliError, ParseError, ValueError, KeyError, OSError) as e:
        return False, 0, 0, f"読めない: {e}"
    interp = PyEval(stdout=io.StringIO(), syntax=syn)
    reason = ""
    try:
        interp.run(program)
        if then is not None:
            interp.run(then)
    except Exception as e:                           # noqa: BLE001  Python と同じ形で理由にする
        reason = f"{'SyntaxError' if isinstance(e, SyntaxError) else type(e).__name__}: {e}"
    total = len(interp.doctests)
    passed = sum(1 for d in interp.doctests if d.ok)
    if not reason and total == 0:
        reason = "doctest がない"
    elif not reason and passed < total:
        reason = f"doctest が {total - passed} 件不一致"
    return not reason, passed, total, reason


def build_pass_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kolang pass@1",
        description="`.ko` と、同じ名前の `.doctest` を実行して、pass@1（合格した問題の割合）を計算する。"
                    "合格 = 実行がエラーなく終わり、doctest が 1 件以上あって、すべて一致。",
        epilog="終了コード: 0 すべて合格 / 1 不合格がある / 2 使い方の誤り。",
    )
    ap.add_argument("files", nargs="+", metavar="FILE.ko", help="問題のファイル（humaneval/*.ko など）")
    ap.add_argument("--total", type=int, metavar="N",
                    help="分母（問題の総数）。既定はファイルの数。変換できていない問題も数えるとき（HumanEval は 164）")
    return ap


def pass_command(args: argparse.Namespace) -> int:
    results = [(path, *check_problem(path)) for path in args.files]
    for path, ok, passed, total, reason in results:
        mark = "PASS" if ok else "FAIL"
        print(f"{mark}  {path}  doctest {passed}/{total}" + (f"  {reason}" if reason else ""))
    n_pass = sum(1 for r in results if r[1])
    denominator = args.total if args.total is not None else len(results)
    if denominator < len(results):
        raise CliError(f"--total {denominator} がファイルの数 {len(results)} より小さい")
    print(f"pass@1 = {n_pass}/{denominator} = {n_pass / denominator:.1%}" if denominator else "pass@1 = n/a（問題がない）")
    return 0 if n_pass == len(results) else 1


def build_cov_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kolang cov",
        description="`.ko` が使っている構文（AST のノード。比較は演算子ごと）と標準ライブラリ関数の回数を、"
                    "全ファイル合計で数える。0 回のものも表に出す。doctest の式は数えない。",
    )
    ap.add_argument("files", nargs="+", metavar="FILE", help="プログラム（examples/*.ko など）")
    ap.add_argument("-f", "--from", dest="src", metavar="SYNTAX",
                    help="シンタックス（既定: .ko ならファイルの 1 行目、それ以外は pylike）")
    return ap


def cov_command(args: argparse.Namespace) -> int:
    from collections import Counter
    from .cov import count_program, report
    nodes: Counter = Counter()
    stdlib: Counter = Counter()
    for path in args.files:
        syn, program, _ = load_program(path, args.src)
        n, s = count_program(program, syn)
        nodes.update(n)
        stdlib.update(s)
    sys.stdout.write(report(nodes, stdlib))
    return 0


def build_eval_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kolang eval",
        description="kolangeval.jsonl の各問の正解コード（pylike）を SYNTAX に変換し、読み直して、"
                    "doctest で動作を確かめる。pass@1（合格した問題の割合）を出す。",
        epilog="終了コード: 0 すべて合格 / 1 不合格がある / 2 使い方の誤り。",
    )
    ap.add_argument("syntax", metavar="SYNTAX", help="名前、JSON のパス、カスケード（ja:jslike(assign,block)）")
    ap.add_argument("-i", "--input", metavar="FILE", help="問題の jsonl（既定: kolang/kolangeval.jsonl）")
    ap.add_argument("-t", "--task", metavar="ID", nargs="+",
                    help="この問題だけ評価する（HumanEval/0 または 0）")
    ap.add_argument("-d", "--difficulty", metavar="N", type=int, nargs="+",
                    help="この difficulty の問題だけ評価する（1〜5）")
    ap.add_argument("-q", "--quiet", action="store_true", help="不合格の問題だけ表示する")
    ap.add_argument("--model", metavar="NAME",
                    help="このモデル（Hugging Face。claude- で始まれば Anthropic API。要 ANTHROPIC_API_KEY）に prompt を渡してコードを生成し、採点する。結果は jsonl で出す")
    ap.add_argument("--context", metavar="FILE",
                    help="モデルに渡す言語の説明（--model のとき）。なければ kolang/examples/*.ko を SYNTAX に変換して使う")
    ap.add_argument("-o", "--output", metavar="FILE", help="jsonl の出力先（--model のとき。既定: results/kolangeval_<syntax>_<model>[_d<N>].jsonl。- なら標準出力）")
    return ap


def eval_command(args: argparse.Namespace) -> int:
    from .kolangeval import DEFAULT_FILE, evaluate, load_problems
    syn = load(args.syntax)
    problems = load_problems(args.input or DEFAULT_FILE)
    if args.difficulty:
        problems = [p for p in problems if p.get("difficulty") in args.difficulty]
        if not problems:
            raise CliError(f"difficulty {args.difficulty} の問題がありません")
    if args.task:
        wanted = {t if "/" in t else f"HumanEval/{t}" for t in args.task}
        problems = [p for p in problems if p["task_id"] in wanted]
        if not problems:
            raise CliError(f"問題が見つかりません: {' '.join(args.task)}")
    if args.model:
        return eval_model_command(args, syn, problems)
    if args.context or args.output:
        raise CliError("--context と --output は --model と一緒に使います")
    results = evaluate(syn, problems)
    for r in results:
        if r.ok and args.quiet:
            continue
        print(f"{'SKIP' if r.skipped else 'PASS' if r.ok else 'FAIL'}  {r.task_id}  doctest {r.passed}/{r.total}"
              + (f"  {r.reason}" if r.reason else ""))
    scored = [r for r in results if not r.skipped]          # 正解がない問題は分母に入れない
    n_pass = sum(r.ok for r in scored)
    skipped = len(results) - len(scored)
    print(f"pass@1 = {n_pass}/{len(scored)} = {n_pass / len(scored):.1%}  ({syn.name})"
          + (f"  スキップ {skipped}" if skipped else ""))
    return 0 if n_pass == len(scored) else 1


def eval_model_command(args: argparse.Namespace, syn: Syntax, problems: list) -> int:
    """モデルでコードを生成して採点し、1 問 1 行の jsonl を出す。要約は標準エラーへ。"""
    from .kolangeval import build_context, evaluate_recorded, default_output_name, is_claude, make_claude_generator, make_hf_generator
    try:
        context = build_context(syn, args.context)
    except OSError as e:
        raise CliError(f"--context を読めません: {e}")
    generate = (make_claude_generator if is_claude(args.model) else make_hf_generator)(args.model, context)
    path = args.output or default_output_name(syn, args.model, args.difficulty)
    if path != "-":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    out = sys.stdout if path == "-" else open(path, "w", encoding="utf-8")
    n_pass = scored = 0
    try:
        for rec in evaluate_recorded(syn, problems, generate, args.model):
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            scored += 1
            n_pass += rec["doctest"]["ok"]
    finally:
        if out is not sys.stdout:
            out.close()
    if out is not sys.stdout:
        print(f"出力: {path}", file=sys.stderr)
    print(f"pass@1 = {n_pass}/{scored} = {n_pass / max(scored, 1):.1%}  ({syn.name}, {args.model})", file=sys.stderr)
    return 0 if n_pass == scored else 1


def build_show_example_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kolang show_example",
        description="スニペット（カスケードの検査に使う AST。kolang/snippet.py）を、シンタックスで書いて表示する。",
    )
    ap.add_argument("syntax", metavar="SYNTAX", help="名前、JSON のパス、カスケード（ja:jslike(assign,block)）")
    ap.add_argument("names", nargs="*", metavar="NAME", help="表示するスニペット（省略すると全部）")
    ap.add_argument("--list", action="store_true", help="スニペットの名前の一覧を表示する")
    return ap


def show_example_command(args: argparse.Namespace) -> int:
    from .snippet import SNIPPETS, show_snippets
    if args.list:
        sys.stdout.write("".join(f"{name}\n" for name in SNIPPETS))
        return 0
    sys.stdout.write(show_snippets(load(args.syntax), args.names))
    return 0


def build_show_ebnf_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kolang show_ebnf",
        description="シンタックスの BNF を表示する（kolang.md の規則を、そのシンタックスの記号で書いたもの）。",
    )
    ap.add_argument("syntax", metavar="SYNTAX", help="名前、JSON のパス、カスケード（ja:jslike(assign,block)）")
    return ap


def show_ebnf_command(args: argparse.Namespace) -> int:
    from .ebnf import show_ebnf
    sys.stdout.write(show_ebnf(load(args.syntax)))
    return 0


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        if argv and argv[0] == "run":
            return run_program(build_run_parser().parse_args(argv[1:]))
        if argv and argv[0] == "pass@1":
            return pass_command(build_pass_parser().parse_args(argv[1:]))
        if argv and argv[0] == "cov":
            return cov_command(build_cov_parser().parse_args(argv[1:]))
        if argv and argv[0] == "eval":
            return eval_command(build_eval_parser().parse_args(argv[1:]))
        if argv and argv[0] == "modelppl":
            from .modelppl import main as modelppl_main      # torch 系は測るときだけ読む
            return modelppl_main(argv[1:], prog="kolang modelppl")
        if argv and argv[0] == "show_example":
            return show_example_command(build_show_example_parser().parse_args(argv[1:]))
        if argv and argv[0] == "show_ebnf":
            return show_ebnf_command(build_show_ebnf_parser().parse_args(argv[1:]))
        if argv and argv[0] == "conv":
            ap = build_conv_parser()
            return convert_command(ap.parse_args(argv[1:]), ap)
        ap = build_parser()
        args = ap.parse_args(argv)
        return run(args, ap)
    except (CliError, ParseError, ValueError, KeyError, OSError) as e:
        print(f"kolang: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
