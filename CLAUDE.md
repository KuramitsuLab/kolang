# CLAUDE.md

kolang（こ言語）の作業メモ。続きを始めるときは、まずここを読む。

## これは何か

シンタックス可変言語。文法の骨格は固定で、区切りの記号（`block_begin` `if_then` などのトークン名）を、JSON の正規表現で差し替える。Python 風・日本語風・Lisp 風・JavaScript 風が同じ AST になる。パーサ、出力器（シンタックス間の変換）、コメントの保持、`kolang` コマンドまで実装済み。評価器は `pyeval.py`（Python 互換、Visitor）がある。`kolang run FILE [-f SYNTAX]` で実行（`-c CODE` は文字列から。FILE なしで端末なら対話モード = `repl.py`。パイプなら標準入力をプログラムとして読む）、`kolang conv FILE [-f SYNTAX] -t SYNTAX` で変換できる（`.md`、またはブロックが 2 個以上の `.ko` は、文書中の ```` ```シンタックス ```` ブロックを全部変換して文章を残す。`cli.py` の `convert_document`、`kofile.map_blocks`。読めない info string のブロックは触らない。`-t` なしは検査だけ）。`kolang show_ebnf SYNTAX` は、`kolang.md` の規則をそのシンタックスの記号で書いた BNF を出す（`ebnf.show_ebnf`）。`kolang show_snippet SYNTAX [NAME...]` は、`snippet.SNIPPETS` をそのシンタックスで書いて表示する（`snippet.show_snippets`。カスケードの衝突の原因を目で見る用。`--list` で名前の一覧）`kolang check SYNTAX [-i FILE] [-t ID...] [-d N...] [-q] [--no-eval]`（`-d` は difficulty で絞る）は、区切りの衝突の検査（`syntax.collisions(syn, True)`。構造検査 + スニペットの往復。読み込み時の警告と同じ）のあと、`kolang/kolangeval.jsonl` の `pylike` を SYNTAX に変換して読み直し、`doctest` で動作を確かめる（`kolangeval.py` の `check` / `evaluate`。`pylike` のない問題は SKIP で分母に入れない。コードを作る部分は `Solver(problem, syntax) -> code` で差し替えられる。既定は `reference_solver`。`kolang eval SYNTAX --model M` は、モデルに `prompt` を渡す Solver を使う（`--model` 必須）。終了コード 0 全合格 / 1 衝突か不合格あり）。`kolang cov FILE.ko... [-f SYNTAX]` は、構文（AST のノードの種類。比較は演算子ごと）と標準ライブラリ関数の使用回数を全ファイル合計で数え、0 回も表に出す（`cov.py` の `count_program` / `report`。doctest の式と自作の同名関数は数えない。`examples/` のカバー確認用）。`kolang pass@1 FILE.ko... [--total N]` は、`.ko` と同名の `.doctest` を実行して pass@1 を出す（`cli.py` の `check_problem` / `pass_command`。合格 = 実行がエラーなく終わり、doctest が 1 件以上あって全件一致。`--total 164` で分母を HumanEval の総数にする。終了コード 0 全合格 / 1 不合格あり）。HumanEval の記録は `humaneval.md`（`humaneval.jsonl`、移植 `humaneval/NNN.{ko,doctest}`、prompt から kolang で書いた `humaneval_gen/NNN.{ko,doctest}`。`kolang pass@1 humaneval/*.ko humaneval_gen/*.ko --total 164` で 162/164）（`cli.py` の `run_program` → `pyeval.execute`。終了コード 0 成功 / 1 実行時エラーか doctest の不一致）。

- 文法: `kolang.md`（トークン名と規則の定義。仕様の正）
- 使い方: `README.md`（コマンド・実行・Python API・シンタックスの作り方・カスケードと衝突検査・仕組み・制約）
- LLM との親和度の測り方: `modelppl.md`（結果は `modelppl.csv`）
- JSON の書き方: `syntax.md`（全キー、トークンの位置、読み書きの規則）
- ライセンス: MIT（`LICENSE`。著作権者は `KuramitsuLab`）

## 作業ルール

- 応答とドキュメントは**日本語**。コード中のコメントも日本語。
- テスト: `python3 -m unittest discover -s tests -t .`（現在 339 件、すべて通る。2 件はスキップ）。変更したら必ず実行する。
- git リポジトリ。リモートは https://github.com/KuramitsuLab/kolang（public、ブランチ `main`）。HumanEval 系（`humaneval/` `humaneval_gen/` `humaneval.jsonl` `humaneval.md` `pyhumaneval*`）は、いったん公開しないので `.gitignore` に入れてある（手元には残す。履歴からも消した）。コミットや push はユーザーに頼まれたときだけ行う（公開されるので、push の前に確認する）。
- `kolang` コマンドは、ユーザーの環境にはインストールしていない（`pip install -e .` は未実行）。動作確認は、スクラッチパッドの venv か `python3 -m kolang` で行った。
- `kolang modelppl` は torch / transformers と HF モデル（既定 `Qwen/Qwen2.5-Coder-1.5B-Instruct`、キャッシュ済み）が要る。実測は約 1 分。`modelppl.csv` はプロジェクト直下に置いてあり、実行すると上書きされる。テストの `test_modelppl` は偽の採点関数なのでモデル不要（表が標準出力に出る）。
- これは**研究用**。完璧を求めない（粗くてもよいので先に結果を出す）。
- `kolang eval --model` の結果は `results/`（`.gitignore` 済み）に出る。モデルは HF（torch / transformers）か、`claude-` で始まれば Anthropic API（`ANTHROPIC_API_KEY`。API は課金されるので、回す前に一言伝える）。
- 一時ファイルはスクラッチパッドに置く。プロジェクト内に `*.egg-info` を残さない。

## ユーザーの要望（これまでに出たもの）

- パーサは**パーサコンビネータ風**で、あとで**改変しやすく**。**バックトラックする**。
- 構文定義（JSON）の拡張は自由にしてよい（`index` や `if_end` の位置は、この許可で拡張した）。
- 空白は半角スペース 1 個以上かコメント。語の区切りは `word_segment` で決める。
- 日本語版は、助詞と述語がひらがな・漢字、名前は英数字（カタカナは名前に使わない）。ブロックは `『` `』`（layout none・toplevel bare）、括弧・読点は半角（`(` `)` `,`）、関数呼び出しは `(x, y)におけるfの値`、添字は `Aの(i)番目`。

## 構成

```
kolang/
  ast.py          AST（frozen dataclass）。コメントは Stmt.comments / Block.trailing（比較の対象外）
  syntax.py       JSON の読み込みと検証、予約語の自動抽出、skip の正規表現の組み立て
  layout.py       indent レイアウト: インデント → 仮想トークン（\x01 NEWLINE, \x02 INDENT, \x03 DEDENT）
  combinators.py  Parser / alt / seq / many / opt / where / Forward / regex / track / eof。Context
  parser.py       文法の本体（build_grammar）。1 規則 1 ブロック。make_parser / parse
  comments.py     コメントを文に付ける（後処理）と、collect_comments
  regexgen.py     正規表現 → 固定文字列・出力例・引用符（re._parser を使う）
  unparser.py     AST → ソース。make_unparser / unparse / convert（読み直して AST を検証）
  cli.py          kolang コマンド（--list / --show / show_snippet / show_ebnf / conv / run / modelppl）
  stdlib.py       標準ライブラリ関数（print、四則演算 add/sub/mul/div、len など。Python のもの）。標準名の表
  pyeval.py       評価器。Visitor（visit_XXX）。Python 互換。`python3 -m kolang.pyeval FILE [-f SYNTAX]`
  structure.py    構造検査 problems(syntax): トークン定義だけを見て、読み書きできない組み合わせを文章で返す
  snippet.py      カスケード検査用の AST スニペット（SNIPPETS。40 個）と failures(syntax)、表示用の show_snippets(syntax, names)
  repl.py         `kolang run` の対話モード。1 行ずつ読んで、読めたら実行（変数は持ち越す）。読めなければ `... ` で続きを待つ（空行で打ち切り、構文エラーを表示）。indent は複合文を空行まで待つ
  cov.py          `kolang cov`。AST のノード（Compare は演算子ごと）と標準ライブラリ関数の使用回数
  kolangeval.py   `kolang check` / `kolang eval --model`。隣の kolangeval.jsonl（問題 164 問。`__file__` から読む）の pylike の正解を変換 → 読み直し → doctest。pylike のない問題はスキップして分母に入れない。Solver を差し替えるとモデルの生成も採点できる。`--model NAME [--context FILE] [-o OUT.jsonl]` は `make_claude_generator`（`--model claude-…`。Anthropic API。新しいモデルは prefill が 400 なので書き出しはユーザーメッセージの指示。`.` は `-` にする。トークン数は usage、キャッシュ分を含む）/ `make_hf_generator`（HF のチャットテンプレート、context = system、prompt = user、貪欲。返答の書き出し = ``` と `entry_header`（正解の entry_point の関数定義の、本体より前）を先に置いて続きを生成）で生の出力を得る → `extract_code` → `evaluate_recorded` が 1 問 1 行の jsonl（出力先の既定は `default_output_name` = `results/kolangeval_<syntax>_<model>[_d<N>].jsonl`（`-d` の指定は `_d1` / `_d1_3`）、`-o -` で標準出力）（task_id / model / syntax / prompt / output / input_tokens / output_tokens（`Generation`: str にトークン数を添える。ただの str なら null）/ code / doctest{ok,passed,total} / error_message）を出す。context は `build_context`（FILE そのまま、なければ `kolang/examples/*.ko` を SYNTAX に変換）。examples は package-data に入れてある
  modelppl.py     シンタックスと LLM の親和度。SNIPPETS を各シンタックスで出力 → HF モデルで NLL / PPL / bpc。`kolang modelppl`（`python3 -m kolang.modelppl` も可）。`kolang modelppl SYNTAX... [--model M]` が `modelppl.csv`（列 model, syntax, NLL, tokens, PPL, bpc。(model, syntax) で置き換え・追記）に書く。説明は `modelppl.md`。torch・transformers は遅延 import。テストは偽の採点関数
  kofile.py       .ko ファイル（1 行目 ```シンタックス 〜 閉じの ``` までがコード）。split_ko / join_ko / map_blocks（文書中の全ブロックを書き換える）
  ebnf.py         show_ebnf(syntax): kolang.md の規則を、そのシンタックスの記号で書いた BNF（`kolang show_ebnf`）
  doctestexpr.py  doctest の式（全シンタックスで pylike の `f(x, y)` か変数）の読み書きと、標準関数の名前の書き換え（localize / delocalize）
  examples.py     --show の例（Python 風の例を対象シンタックスへ変換して表示）
  syntaxes/       pylike.json / jalike.json / lisplike.json / jslike.json / pslike.json（PostScript 風。後置記法）/ ainu.json（アイヌ語ふう・カタカナ。草稿。基本語彙以外は作語で話者の確認が要る。標準関数は print（ヌカレ）だけ改名）/ manyo.json（万葉仮名。kobun の語を音仮名の漢字にしたもの）/ kobun.json（古文帳。歴史的仮名遣い。assign は target_first、append と funcapp は value_first / args_first） / kansai.json（関西弁。ほな〜おしまい。assign は value_first、funcapp は args_first `(a, b)をgcdにやらしたやつ`）/ okinawa.json（沖縄語ふう。草稿で、語彙は話者の確認が要る。名前を `ん` で終えない = 助詞 `んかい` と続くため） / jagal.json（ギャル語。indent レイアウト。`ワンチャン〜だったらさ`、`1をxにしちゃう`、`(a, b)をgcdにお願いしたやつ`） / enlike.json（英語版。indent レイアウト。`set x to 1`、`if x is less than 3:`、`repeat 3 times:`、`define f(a, b):`、比較は `is equal to` など。標準関数は英語のフルネーム（`subtract` `length` など）、自作の名前とぶつかりやすい `str` `mul` だけ `to_text` `times_of`） / latin.json（ラテン語版。indent レイアウト・ASCII のみ。命令法。`pone 1 in x`（value_first）、`si x est minor quam 3:`、`itera 3 vices:`、`munus f(a, b):`、標準関数もラテン語（`scribe` `adde` `longitudo` など）。語彙は話者の確認が要る） / mathlike.json（数学記号版。indent レイアウト。キーワードも標準関数名も記号だけ（アルファベットなし）。名前（変数・自作の関数）だけ英数字。`x ← 1`、`xs ⊞ 4`、`x ↑`、`⊢ x < 3 ⇒`、`⊬ ⇒`、`⟳ 3 ⇒`、`≝ f(a, b) ⇒`、`↩`、`⊤ ⊥ ∅`、標準関数は `+(a, b)` `⎙(x)` `#(xs)` など） / godel.json（ゲーデル版。pylike のトークンを素数のゲーデル数 `§2`（=）`§13`（if）… に置き換えたもの。数値リテラルと区別するため `§` を付ける。同じ字面は同じ数、ただし添字の `[` `]` はリストと分けて `§107` `§109`、コメントは `§127`。数字は word_segment なので、`§2` と `§23` の区別は語の区切りに任せる。`§5` の先読みだけ `(?![0-9])` が要る。添字の `[` は変数の直後に空白なしで書く `x§107 0 §109`。名前・標準関数名は pylike のまま）
lib/              kolang で定義した関数（join split slice sort any all など 22 個）。lib/NAME.ko + lib/NAME.doctest。標準ライブラリに足さず、kolang で書けるものはここに置く（リストを縮める pop / remove / clear は、使われないので標準ライブラリにも持たない）。`kolang pass@1 lib/*.ko`、`tests/test_lib.py`（Python のメソッドとの差分テスト）。import のしくみはなく、使う側が定義を先頭にコピーする（HumanEval の .ko は、変換時に取り込む）。ASCII だけ・index は見つからないと -1 などの違いは `humaneval.md`
tests/            test_lib / test_modelppl / test_kofile / test_pylike / test_jalike / test_convert / test_comments / test_lisp / test_js / test_cascade / test_pyeval / test_doctest / test_stdlib / test_rename / test_cli / test_cascade_matrix / test_neg / test_structure / test_ps / test_enlike / test_latin / test_mathlike / test_godel
```

## 設計の要点（コードを読む前に知っておくこと）

- **字句解析器はない**。トークンの正規表現を、位置から直接マッチさせる（scannerless）。トークンの前で、空白とコメントを読み飛ばす。空マッチも成功。
- **語の区切り**: トークンの最後の文字が `word_segment` で、すぐ後ろも `word_segment` なら失敗（`Context.needs_space`）。`\b` は JSON に書かない。
- **バックトラック**は PEG の順序つき選択。選択肢の順が意味を持つ（文、条件、式）。式は `string, number, boolean, none, list, (prefix の index), funcapp, variable`。
- **indent レイアウト**: `layout.py` が、行ごとに `"\n"` + 仮想トークンを挟む。`continuation`（`else` など）の行の前では、最後の `@NEWLINE` を省く。コメントだけの行は、`"\n" + 本文 + "\n"` として本文に残す（コメントを拾うため）。最上位は `block_begin` / `block_end` なしの文の並び。
- **左再帰**: postfix の添字（`x[i]`）は、繰り返しにして畳み込む。prefix（`(get x i)`）は Forward で再帰。
- **コメント**: `Context.skip` が読み飛ばしたコメントを `ctx.comments`（位置→本文）に、`track()` が文の開始位置を `ctx.starts` に記録する。構文解析のあとで `attach_comments` が付ける。同じ行で始まった文があれば trailing、なければ次の文の leading、次がなければ `Block.trailing`。
- **unparser**: トークンは `emit`（JSON、空白を足す用）か、`regexgen.sample`（正規表現から作る）で出力。区切りの最後の要素は、空の枝があれば空にする。`Mark.NL/IN/OUT` と `Raw`（コメント）を挟んだ部品の列を `render` で組み立てる。
- **字句（`lexical`）は全シンタックスで原則 pylike と同じ**: `number` `string`（`"…"` と `'…'`）`quote`（begin / end とも `_`）`characters`（`[^_\n]+`）。`letters` は `[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*`（先頭と末尾に `_` を置かない。`x_` が名前になると引用の `_` を読めず、構造検査が衝突として報告する）。jalike も同じ（カタカナは名前に使わない。標準名は漢字で、関数名の位置だけ引用なしで書ける）。JSON の `lexical.quote` は、`flatten_tokens` が内部の `quote_begin` / `quote_end` トークンに移す（`tokens` に書いても読める。カスケードの `quote` グループ）。パーサは引用の記号に語の区切り（`boundary`）を適用せず、出力器は `_名前_` を 1 つの部品にする。**`_` で始まる名前は書けない**（`n回くり返す` が束縛する `_` も、プログラムからは参照できない）。名前を引用で書くのは `_合計_`（jalike）。
- **JSON のトークン**: `tokens` はグループにまとめて書く（`"block": {"begin": ..., "sep.emit": ";"}`）。`flatten_tokens`（`syntax.py`）が、読み込みの最初に内部の平らな形（`block_begin`、`emit` も平ら）に直す。パーサ・出力器・カスケードの中身は平らな名前のまま。グループ名 = トークン名の `_` より前（`true` `false` `none` `break` だけは文字列）。
- **emit の候補**: `キー.emit` は文字列か配列。配列は `make_unparser(random_emit=seed)` / `convert(random_emit=)` / CLI `--random-emit SEED` のときだけ `random.Random(seed).choice`、なければ最初。seed 0 も有効（`is not None`）。
- **カスケード**: `load_syntax("jalike:jslike(assign,block,funcapp)")`。`syntax.py` の `GROUPS`（トークン名の接頭辞でグループ化）で、JSON の辞書の段階で重ねてから検査する。`block` は layout なども連れていき、indent→none では space に改行を足す。
- **カスケードの衝突検査**: `load_syntax` は、読み込んだシンタックスを検査して、問題があれば `UserWarning`（「区切りが衝突している」＋原因の一覧）を出す。読み込みは続ける。`verify=False` で検査しない。(1) **構造検査** `structure.problems(syn)`（単独のシンタックスにも行う）: ①indent なのに `if_end` `else_end` `repeat_end` `def_end` が空でない、②none で `block_end` が空なのに `if_end` `repeat_end` `def_end` も空（本体の終わりが決まらず、次の文が本体に入る）、③コメントの記号に他のトークンがマッチする（`;`）、④名前（`letters`）が記号を飲み込む（`x--`）。(2) (1) で何も見つからなかった**カスケード**だけ、`snippet.SNIPPETS`（AST。構文ごとの単体に加え、配列の添字・リスト・関数呼び出し・符号の反転・append・doctest などの組み合わせを含む。足すときは名前 x y z f g a b、負の `Num`・空のブロックは使わない。`Index` の対象は変数か添字だけ）を出力 → パースして、戻らないものを知らせる（`snippet.failures(syntax)` が `[(名前, 理由)]`）。(2) は読むたびに全スニペットを往復するので遅い。`tests/test_cascade_matrix.py`: `CASCADES` の組み合わせは常に検査（警告なし）。指定した組み合わせだけ見るなら `python3 -m tests.test_cascade_matrix "jalike:jslike(block)" ...`（NG なら理由を出し、終了コード 1）。全順列（744 通り）は `KOLANG_MATRIX=1`（約 52 通りが衝突するのでスキップが既定。`test_structure` は、全順列で「構造検査が見つける ⇔ スニペットが戻らない」が一致することを確かめる）。
- **符号の反転**: `Neg(operand)`（`neg_begin <expression> neg_end`、`-X`）。`Num` は非負のままで、`-1` は `Neg(Num(1))`、負の `Num` は `UnparseError`。トークンは**省略可**（`neg_begin` が無いシンタックスはパースしない・出力は `UnparseError`）。pylike / jalike / jslike は `-`（`neg_end` 空）、lisplike は `(neg X)`（予約語 `neg`）。式の選択肢は `…, list, (prefix の index), neg, funcapp, variable`。pyeval は Python の単項マイナス。
- **toplevel**: `layout: none` の最上位は既定で `block_begin〜block_end` で包む。`"toplevel": "bare"`（jslike）なら文の並びだけ（indent と同じ）。
- **文法を拡張した箇所**（`kolang.md` に反映済み）: `if_end` は `else` のあと。添字は postfix / prefix（`index_sep` が prefix で増える）。

- **pyeval**: 値は Python のオブジェクトそのもので、演算も Python に任せる（エラーの種類とメッセージも Python と同じ）。`tests/test_pyeval.py` は、同じソースを Python で `exec` した結果（出力・エラー・グローバル変数）と比べる。意味の核（`lookup` `bind` `compare` `truth` `count_of` `call` `make_builtins`）は別メソッドで、継承して上書きする。Python と同じ点: 関数内の代入はローカル（`UnboundLocalError`）、`n回くり返す` は `for _ in range(n)` なので `_` に束縛する、`break`/`return` の置き場所は実行前に `PySyntaxError`、再帰の深さは 1000。
- **標準ライブラリ**: 演算子も `print` もなく、関数で書く（`add(1, 2)`、`print(x)`）。`stdlib.py` の `make_stdlib()` が「標準名 → Python の関数」の表（四則演算・組み込み関数。`input` `repr` `reversed` `pop` `remove` `clear` は使われないので持たない。kolang で書けるものは標準ライブラリに足さず、`lib/` に kolang で定義する）。シンタックスの JSON のトップレベルのキー `"stdlib": {"print": "プリント"}`（標準名 → 名前のオブジェクト）で、そのシンタックスでの名前に変えられる（`Syntax.stdlib` / `.function_names`。読み込み時に検査）。PyEval が `make_builtins` で、変更後の名前で並べる。パースには関係しない（AST は書いた名前のまま）。**変換では関数名も書き換える**: `unparser.rename_stdlib`（`convert` の `rename=True`、CLI は `--no-rename` で止める）が、Call と Var の名前を src の名前 → 標準名 → dst の名前に直す。プログラムが自分で定義した名前（`defined_names`: 関数・引数・代入）は書き換えない。書き換え後の名前が自作とぶつかったら `UnparseError`（使われていない名前は判定しない）。`jalike.json` は全関数に漢字の名前（表示・足し算・引き算・長さ・範囲・合計・整列・文字コード・四捨五入・四捨五入など 22 個）。`letters` に合わない名前でも、**関数呼び出しの関数名の位置では引用なしで書ける**（パーサは `stdlib` の名前を先に試し、出力器は引用しない。変数などほかの位置は `_表示_` と引用）。カスケードは、合成後の `stdlib` の名前を使う（`test_cascade_refers_to_stdlib_names`）、pylike / jslike / lisplike は標準名のままを明示。カスケード（`stdlib` グループ = `stdlib` キー）はベースの名前を引き継ぐ。
- **doctest 風の例**: `>>> 式` の次の行に JSON の答え。記号（`>>>`）は固定で、`syntax.py` の `DOCTEST_PROMPT`。**式は全シンタックスで pylike の書き方**（`doctestexpr.py`）で、関数呼び出し `f(x, y)` か変数（添字つき含む）だけ。行末までを切り出して、pylike の式パーサ（`build_grammar(entry="expression")`）で別に読む。標準関数の名前は pylike の名前（標準名）で書き、`localize_doctests`（parse 後）が AST の名前（jalike なら 足し算）にし、出力器は `delocalize_doctests` で戻す（`rename_stdlib(doctest_only=True)`。自作の同名は書き換えない）。別ファイルの `.doctest` を読むときは、CLI が `parse(..., defined_names(本体))` で本体の自作の名前を渡す。AST は `Doctest(expr, answer)`（answer は JSON を読んだ値）。indent レイアウトでは、`layout.py` が答えの行を仮想トークンなしで前の行の続きにする。パーサは答えを生の文字列で読み（`>>>` の行末のコメントは不可）、JSON でなければ `ParseError`。出力器は答えを `json.dumps` で書き、`block_sep` は付けない。pyeval は `interp.doctests`（`DoctestResult`）に結果を残し、外れても続行する。照合は `answer_matches`（型まで厳密: 1 と true と 1.0 は別）。
- **`.ko` ファイル**: 拡張子 `.ko`。1 行目が ` ```jalike:jslike(assign) ` のようなシンタックス指定（カスケード可）、閉じの ` ``` の行までがコードで、後ろは読まない。CLI は `.ko` なら `-f` 不要（あれば `-f` が優先）。`-o x.ko` で出力すると ` ```dst ` で包む。`kolang run x.ko` は、同じフォルダに `x.doctest` があれば、プログラムが成功したあとに続けて実行する（同じ評価器なので、変数・関数が見える。中身はフェンスなしの、`.ko` と同じシンタックスのコード。`execute(..., then=)`）。エラーの行番号はコード部分の先頭が 1（フェンス行の分ずれない）。
- **関数呼び出しの順序**: `tokens.funcapp`（`begin` `name_end` `end` `arg_sep` `order`）にまとめて書く。`order` は `"func_first"`（既定、`f(x)`）| `"args_first"`（読み込みの `flatten_tokens` が、`call_*` `arg_sep` と内部のトップレベル `call` に直す）。jalike は args_first で `(x, y)におけるfの値`（`call_begin="("` `call_name_end=")における"` `call_end="の値"`。args_first では `call_name_end` が引数と名前のあいだ）。AST は同じ `Call`。パーサ・出力器が `Syntax.call` で並びを切り替える。カスケードでは `funcapp` グループが `call` キーも連れていく。
- **式の括弧**: トークン `grouping_begin` / `grouping_end`（省略可。jalike は半角の `(` `)`）。AST に残らない（中の式そのもの）。funcapp を先に試し、だめなら括弧と読む（jalike は `call_begin` も `(`）。出力器は括弧を自動では足さない。jalike の添字は `index_begin="の("` `index_end=")番目"` で、括弧を含めて書く（`aの(i)番目`）。
- **呼び出し文**: `CallStmt`。`(` で始まるトークンは予約語にならないので、lisplike.json に `reserved` を明示してある（`(else …)` が呼び出し文と読まれないように）。

## 既知の制約・割り切り

- 関数呼び出しは、式としても、文（`CallStmt`。戻り値は捨てる）としても書ける。
- doctest の式は、関数呼び出しか変数だけ（`>>> 1` `>>> [1, 2]` は不可）。`>>>` の行末のコメントも不可。`UnparseError` / `ParseError`。
- `else` の行のコメントは、`else` の中の最初の文の leading に移る。ブロック末尾のコメントは、次の文の leading になる。空行は保持しない。
- indent レイアウトのコメントは、1 行で閉じるものだけ。インデントは半角スペースとタブ（タブは 4）。
- indent の出力では、`if_end` `else_end` `repeat_end` `def_end` が空である必要がある。
- `none` レイアウトの出力（改行できる形式）は、`block_begin` でインデントを深くし、文ごと（`block_sep` のあと）に改行し、`block_end` の前で浅くする（`unparser.block`）。`block_begin` も `block_end` も空（lisplike）なら 1 行のまま。インデント幅は `INDENT_UNIT`。改行できない形式（space が改行にマッチしない）も 1 行のまま。
- 負の `Num`（`Neg(Num)` で書く）、空のブロック、引用できない名前は `UnparseError`。
- 動作は Python 3.10 以上が前提（`kw_only` の dataclass）。3.11 で確認。

- カスケードの既知の衝突（`KOLANG_MATRIX=1` で確認。744 通り中 52 通り、すべて lisplike が絡み、すべて構造検査が見つける）: lisplike は block が空で、各形が `)` で閉じる。indent の `block` や、`if_end` などが空のシンタックスと混ぜると、閉じがなくなって次の文が本体に入る（AST が変わる）か、出力できない。`;` はコメント（lisplike）と `block_sep`（jslike）が重なる。どれも記号の衝突なので直せず、警告で知らせる。直した分（`CASCADES` に入っている）: `continuation` を `else_begin` から導く（JSON の `continuation` は上書き用）、行頭の部品の先頭の空白を落とす、none の空白に改行を足す（indent 以外がベースでも）、後置の添字 `[` は変数の直後だけ（空白があれば別の式）。

## 測定の記録（`kolang eval --model`。prompt + examples 変換 + entry_point のヘッダ固定）

- `claude-haiku-5.5`（pass@1。結果は `results/`）: d=1 は pylike 29/29・jalike 25/29、d=4（33 問）は pylike 27/33・jalike 28/33。Qwen2.5-Coder-1.5B は d=1 で pylike 2/29・jalike 2/29（kolang を書けない）。
- 失敗の原因（Haiku）: ①jalike の添字の括弧忘れ（`lのi番目` → 正しくは `lの(i)番目`。d=1 の失敗 4 問中 3 問）、②pylike で条件に比較がない（`if started:` `if is_prime(x):`。d=4 の失敗 6 問中 5 問）、③標準ライブラリにない関数（`isinstance` 相当、`md5`）。
- 手を入れるなら: examples に ①②の例を足す／jalike の `aのi番目` も読めるようにする（方針の変更なので要相談）／条件を真偽値だけでも書けるようにする／`isinstance` を足す。

## 次にやること（候補）


1. 足りない関数を増やす（`floordiv`、`set` `isinstance` `ceil` `floor` `filter` など。`humaneval.md` の「変換できない問題の原因」が、足りない順）。まず `lib/` に kolang で書けないか考え、書けないものだけ `stdlib.py` の表に足す。
2. `LICENSE` の著作権者を、ユーザーに確認して直す。
3. lisplike の整形（`(if c` の本体を改行・インデントする。begin / end が空なので、今は 1 行）。
4. 新しいシンタックスの追加（ブレース形式など）。`kolang --show` / `kolang show_snippet` と変換テストで確認する。
5. modelppl の拡張（`--random-emit` の版を並べる、複数モデルを一括で回す、スニペットごとの CSV）。
6. （任意）コメントの付き方の改善（else の行、ブロック末尾をインデントで判定）。
