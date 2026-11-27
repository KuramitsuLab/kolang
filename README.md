# kolang（こ言語）

**書き方（シンタックス）を選べる言語。** 文法の骨格は固定で、区切りの記号を JSON の正規表現で差し替えると、Python 風・日本語風・Lisp 風・JavaScript 風など、好きな見た目で同じプログラムを書けます。

```
# Python 風                      ※ 日本語風                       ; Lisp 風
def add(a, b):                  関数 add(a, b)とは               (def add (a b) (return a))
    return a                        aを返す
s = 0                           0をsに代入                         (set s 0)
for _ in range(3):              3回くり返す                        (repeat 3 (inc s))
    s += 1                          sを増やす
y = x[0]                        xの(0)番目をyに代入                  (set y (get x 0))
```

どれも同じ AST になります。できること:

- **変換**: シンタックス間の変換（コメントも保持。標準ライブラリ関数の名前も書き換え）
- **実行**: Python 互換の評価器（`kolang run`）。標準ライブラリは関数で、名前をシンタックスごとに変えられる
- **doctest 風の例**: `>>> f(x, y)` の次の行に JSON の答え（式はどのシンタックスでも pylike の書き方）
- **カスケード**: 複数のシンタックスを重ねて、一部だけ差し替える。区切りが衝突する組み合わせは、読み込み時に警告
- **LLM との親和度**: 同じプログラムを各シンタックスで出力し、言語モデルの NLL / PPL を測る（`kolang modelppl`、[modelppl.md](modelppl.md)）

## インストール

Python 3.10 以上が必要です。依存ライブラリはありません（`kolang modelppl` だけ、`torch` と `transformers` が要ります）。

```
pip install -e .
pip install torch transformers     # kolang modelppl を使うときだけ
```

## コマンド

```
kolang --list                      使えるシンタックスの一覧
kolang --show lisplike             書き方の例を表示
kolang show_ebnf jalike                そのシンタックスの BNF（kolang.md の規則を、そのシンタックスの記号で）
kolang show_snippet jalike [NAME...]   スニペット（検査用の AST）をそのシンタックスで表示（--list で名前の一覧）
kolang conv prog.py -f pylike -t jalike   シンタックスを変換（ファイルなしなら標準入力、-o で出力先）
kolang conv prog.ko -t jalike             .ko なら -f は不要
kolang conv prog.py -f pylike         構文チェックだけ（-t を省略）
kolang conv doc.md -t jalike              .md の ```pylike などのブロックを全部変換（文章はそのまま）
kolang run prog.py [-f pylike]     実行する（ファイルなしなら標準入力）
kolang run prog.ko                 .ko ファイルを実行する（シンタックスは 1 行目で指定）
kolang run -c 'print(1)' [-f SYNTAX]  ファイルなしで、文字列のプログラムを実行する（python -c と同じ）
kolang run [-f SYNTAX]             ファイルなしで端末から起動すると、対話モード（パイプなら標準入力をプログラムとして読む）
kolang cov examples/*.ko           構文（AST のノード）と標準ライブラリ関数の使用回数を数える
kolang check SYNTAX [-t ID...] [-d N...] [-q] [--no-eval]  区切りの衝突（カスケード）の検査と、評価問題（kolangeval.jsonl）の正解を SYNTAX に変換して doctest で確かめる
kolang eval SYNTAX --model NAME [--context FILE] [-o OUT.jsonl]  モデルにコードを生成させて採点（結果は jsonl）
kolang modelppl SYNTAX|all... [-m MODEL] シンタックスと LLM の親和度を測り、modelppl.csv に書く
```

- シンタックスは、名前（`--list` に出るもの）、JSON ファイルのパス、またはカスケード（後述）で指定します。`python -m kolang ...` でも同じです。
- 変換では、標準ライブラリ関数の名前も書き換わります。止めるには `--no-rename` です。
- `*.emit` に候補の配列を書くと、`--random-emit SEED` のときだけ候補から選びます（省略すると常に最初）。
- `.ko` ファイルは、1 行目に ` ```jalike:jslike(assign) ` のようにシンタックスを書き、閉じの ` ``` ` までをコードとして読みます（`-f` は不要）。`kolang run x.ko` は、同じフォルダに `x.doctest`（フェンスなし、同じシンタックスのコードに、`>>> f(x)` と答えを並べたもの）があれば、続けてテストします。本体で定義した名前（関数・変数）が見えます。`-o out.ko` で変換結果を `.ko` 形式で書けます。
- `kolang conv` は、**文書の中の複数のコードブロック**も変換できます。入力が `.md`、または ```` ```シンタックス ```` のブロックが 2 個以上ある `.ko` で `-t` を付けると、各ブロックを変換し（開きのフェンスも `-t` のシンタックスに書き換わる）、ブロックの外の文章はそのまま出力します。info string がシンタックスとして読めないブロック（```` ```python ```` ```` ```bash ```` など）は触りません。`-f` があれば、info string のあるブロックすべてを `-f` で読みます。`-t` を省略すると各ブロックが読めるかだけ検査し（`OK: N 個のコードブロック`）、変換できるブロックが 1 つもなければエラーです。ブロックが 1 個だけの `.ko` は従来どおり（コードだけを出力。`-o x.ko` なら ```` ```dst ```` で包む）です。
- `kolang cov FILE...` は、プログラムが使っている構文と標準ライブラリ関数の回数を、全ファイル合計で数えます（`.ko` なら `-f` は不要、ほかは `-f SYNTAX`、既定は pylike）。構文は AST のノードの種類で数え、比較は演算子ごと（`Compare(==)`）です。標準ライブラリは標準名（pylike の名前）で数え、jalike など別のシンタックスで書いても同じ名前に集まります。0 回のものも `← 未使用` と出し、最後に `カバー n/m` を表示するので、`examples/` のお手本が構文と標準ライブラリを漏れなく使っているかの確認に使えます。doctest の式と、プログラムが自作した同名の関数は数えません。
- `kolang check SYNTAX` は、シンタックス（カスケードも）の検査です。(1) 区切りの衝突: 構造検査と、`snippet.SNIPPETS` の出力 → パースの往復（読み込み時の警告と同じ検査。`OK` か `NG` と原因の一覧を表示）。(2) `kolang/kolangeval.jsonl`（HumanEval から作った 164 問。`prompt` `doctest` `pylike`（正解コード）など）の `pylike` を SYNTAX に変換して読み直し、`doctest` で動作を確かめて pass@1 を出します。`-i FILE` で別の jsonl、`-t 0 1` で問題を絞り、`-d 1`（`difficulty` が 1 の問題だけ。複数可）でも絞り、`-q` で不合格だけ表示し、`--no-eval` で (1) だけ行います。`pylike` のない問題は `SKIP` とし、分母に入れません。終了コードは 0 が全合格、1 が衝突か不合格あり。

- `kolang eval SYNTAX --model NAME` は、モデルに評価問題を解かせて採点します（`--model` が必須。`-i` `-t` `-d` は `check` と同じ）。Python からは `kolang.kolangeval` の `evaluate(syntax, problems, solver)` で、`solver(problem, syntax) -> code` を差し替えると、変換の代わりにモデルが生成したコードを採点できます。

  `--model NAME`（Hugging Face のモデル。torch / transformers が要る。`claude-` で始まる名前は Anthropic API で呼ぶ。`ANTHROPIC_API_KEY` が要り、`claude-haiku-5.5` のように `.` で書いても `claude-haiku-5-5` として扱う。Claude には書き出しの固定を assistant の prefill でなくユーザーメッセージの指示で渡し、temperature は指定しない）を付けると、正解の変換の代わりに、モデルに各問の `prompt` を渡してコードを生成させ、同じ採点をします。システムメッセージに入れる言語の説明は `--context`（既定 `guide`。examples は入れない）で、コンマ区切りで順に並べます。項目は `NAME`（`kolang/spec/NAME.md` の ```` ```pylike ```` ブロックを SYNTAX に変換したもの。`guide` / `3shots` など）、`snippet`（`snippet.SNIPPETS`。構文ごとの小さな例。`kolang show_snippet` と同じもの。SYNTAX で書けないものは省く）、`ebnf`（`kolang show_ebnf SYNTAX` の BNF）、FILE（存在するファイルの中身をそのまま）で、`none` なら空（システムメッセージなし）です。例: `--context 3shots,ebnf`。生成は貪欲（`do_sample=False`、最大 1024 トークン）で、出力の ``` で囲まれたコードを取り出します。結果は 1 問 1 行の jsonl（`task_id` `model` `syntax` `context`（`--context` の指定。なければ null）`prompt` `output`（モデルの生の出力）`input_tokens`（入力。チャットテンプレートと書き出しを含む）`output_tokens`（新しく生成した分）`code`（取り出したコード）`doctest`（`ok` `passed` `total`）`error_message`（失敗の理由。なければ null））で、`-o FILE`（既定は `results/<context>/kolangeval_<syntax>_<model>.jsonl`（`<context>` は `--context` の指定で、コンマは `_` になる。例: `3shots,ebnf` → `results/3shots_ebnf/`。フォルダは自動で作る。`-d 1` なら `_d1`、`-d 1 3` なら `_d1_3` が付く）。英数字と `.` `_` `-` 以外は `_` にする。`-o -` なら標準出力）に出し、pass@1 の要約は標準エラーに出ます。`--context` と `-o` は `--model` のときだけ使えます。
- `kolang modelppl SYNTAX...` は（`all` で組み込みの全シンタックス）、指定したシンタックスの `NLL, tokens, PPL, bpc` を計算し、`modelppl.csv`（列は `model, syntax, NLL, tokens, PPL, bpc`）に書きます。既定のモデルは `Qwen/Qwen2.5-Coder-1.5B-Instruct`（`--model` で変更）。詳しくは [modelppl.md](modelppl.md)。
- `kolang run` の終了コードは、0 が成功、1 が実行時エラーか doctest の不一致、2 が使い方の誤りです。

## 実行する

出力も四則演算も、標準ライブラリの**関数**で書きます（kolang には演算子がありません）。

```python
def add3(a, b, c):
    return add(add(a, b), c)

x = add3(1, 2, 3)
print(x, mul(x, 2))          # 6 12
xs = [1, 2]
xs.append(x)
print(xs)                    # [1, 2, 6]

>>> mod(x, 4)
2
```

```
$ kolang run prog.py
6 12
[1, 2, 6]
doctest: 1 passed, 0 failed
```

評価器は Python 互換です。同じソースを Python で実行したときと、出力・エラーの種類とメッセージ・変数が同じになるように作ってあります（値は Python のオブジェクトで、演算も Python に任せています）。

- 関数の中の代入はローカルです。代入の前に読むと `UnboundLocalError` です。
- `n回くり返す` は `for _ in range(n)` と同じで、`_` に束縛します。
- `break` と `return` の置き場所は、実行する前に検査します（`SyntaxError`）。
- 再帰の深さの上限は 1000 です。

### 標準ライブラリ

| 標準名 | 働き |
|---|---|
| `print` | 出力 |
| `add` `sub` `mul` `div` `mod` `pow` | `+` `-` `*` `/` `%` `**`（`add` は文字列・リストの連結、`mul` は繰り返しにも使える） |
| `int` `str` `float` `bool` | 型の変換 |
| `abs` `chr` `len` `list` `max` `min` `ord` `range` `round` `sorted` `sum` | Python の同名の組み込み関数 |

関数の名前は、シンタックスの JSON の `stdlib`（`{"print": "表示"}` の形）で変えられます。`jalike.json` は漢字です（`表示` `足し算` `引き算` `掛け算` `割り算` `余り` `べき乗` `整数化` `文字列化` `小数化` `ブール化`）。

```
$ echo 'print(add(1, 2))' | kolang conv -f pylike -t jalike
表示（足し算（1、2））
```

自分で同じ名前の関数を定義すると、そちらが優先され、変換でも書き換えません。書き換えた名前が自作の名前とぶつかるときは `UnparseError` です。

### doctest 風の例

`>>> 式` の次の行に、答えを JSON の値で書きます。`>>>` と答えの書き方は固定です。式も**どのシンタックスでも pylike の書き方**で、関数呼び出し `f(x, y)` か変数（`x[0]` も可）だけです（引数は pylike の式）。シンタックスを変えても、doctest はそのまま読めます。実行すると答え合わせをして、外れても続けます。

```
>>> f([1, "a", None], x[0])
[1, "a", null]
```

標準関数は pylike の名前（標準名）で書きます。jalike で読むと `add` は `足し算` になります（プログラムが同じ名前を自分で定義していれば、そちらが優先。`.doctest` の別ファイルでも、本体の自作の名前が優先）。

型まで厳密に比べます（`1` と `true` と `1.0` は別）。

## Python から使う

```python
import kolang
from kolang.pyeval import run

tree = kolang.parse("x = [1, 2]\n", "pylike")          # → AST（kolang.ast）
kolang.unparse(tree, "jalike")                              # → "[1, 2]をxに代入\n"
kolang.convert("print(1)\n", "pylike", "jalike")            # → "表示（1）\n"
interp = run("x = add(1, 2)\n>>> x\n3\n")              # 実行。interp.globals.vars、interp.doctests
```

| 関数 | 役割 |
|---|---|
| `parse(source, syntax)` / `make_parser(syntax)` | ソース → AST |
| `unparse(tree, syntax)` / `make_unparser(syntax)` | AST → ソース |
| `convert(source, src, dst, check=True, rename=True)` | シンタックスの変換。`check` は、書き出した結果を読み直して AST が同じか確かめる。`rename` は、標準ライブラリ関数の名前の書き換え |
| `load_syntax(name_or_path)` / `syntax_from_dict(dict)` | シンタックス定義の読み込み |
| `kolang.pyeval.run(source, syntax)` / `PyEval` | 実行。`PyEval` は Visitor（`visit_XXX`）で、継承してセマンティクスを調整できる |
| `ParseError` / `UnparseError` | 構文エラー（行・桁つき）/ 書き出せないもの |

評価器を調整するには、`PyEval` を継承して、`lookup` `bind` `compare` `truth` `count_of` `call` `answer_matches` `make_builtins` などを上書きします。

## 組み込みのシンタックス

| 名前 | 特徴 |
|---|---|
| `pylike` | Python 風。インデントでブロックを表す |
| `jalike` | 日本語風。ブロックは `『 』`。名前は英数字、漢字などは `_` で囲む（`_合計_`） |
| `lisplike` | Lisp 風。S 式。配列の添字は `(get x i)` |
| `jslike` | JavaScript 風。`{ }` と `;`（省略可）、`xs.push(1)`、`x++`、`function`。最上位は括らない |
| `pslike` | PostScript 風。後置記法 |
| `kobun` | 古文帳。歴史的仮名遣い。平安のかな文学ふう |
| `manyo` | 万葉仮名。kobun の語を音仮名の漢字で書く |
| `kansai` | 関西弁。`ほな〜おしまい` |
| `jagal` | ギャル語。インデントでブロックを表す |
| `ainu` | アイヌ語ふう（カタカナ）。草稿で、語彙は話者の確認が要る |
| `okinawa` | 沖縄語ふう。草稿で、語彙は話者の確認が要る |
| `enlike` | 英語版。インデント。`set x to 1`、`if x is less than 3:`、`repeat 3 times:` |
| `latin` | ラテン語版。インデント、ASCII のみ。`pone 1 in x`、`si x est minor quam 3:`。語彙は話者の確認が要る |
| `mathlike` | 数学記号版。キーワードも標準関数名も記号だけ。`x ← 1`、`⊢ x < 3 ⇒`、`≝ f(a, b) ⇒` |
| `godel` | ゲーデル版。pylike のトークンを素数のゲーデル数で書く。`§2`（`=`）、`§13`（`if`） |
| `cobollike` | COBOL 風。大文字の英語、文はピリオドで終える。`MOVE 1 TO x.`、`END-IF.` |

一覧と説明は `kolang --list` でも見られます。

## 言語の骨格

文法は [kolang.md](kolang.md) にあります。

- **文**: 代入、追加、増やす、減らす、if / else、くり返す（n 回）、抜ける、関数定義、戻り値、関数呼び出し、doctest 風の例
- **式**: 変数、配列の添字、文字列、数、真偽値、none、リスト、関数呼び出し、符号の反転（`-x`。`neg_begin` が無いシンタックスでは使えない）
- **条件**: `!=` `<` `>` `<=` `>=` `==`
- 区切りの記号は `block_begin`、`if_then` のような**トークン名**で書かれていて、それぞれが正規表現です。シンタックス定義の JSON は、トークンを**グループ**（`block` `if` など）にまとめて、`"block": {"begin": ..., "sep": ...}` のように書きます（グループ名 + `_` + キーがトークン名）。グループが、カスケードの取り込みの単位です。

## シンタックスを作る

`kolang/syntaxes/` に JSON を置きます（または JSON のパスを直接指定します）。上の表のシンタックスが実例です（まず `pylike.json`、indent なら `enlike.json`、none なら `jslike.json` や `cobollike.json` が読みやすい）。全キーの詳しい書き方は [syntax.md](syntax.md) にあります。

```jsonc
{
  "name": "mylang",
  "layout": "indent",              // "indent": インデントでブロック / "none": 記号で囲む
  "space": " +",                   // 空白の正規表現
  "word_segment": "[A-Za-z0-9_]",  // 語を作る 1 文字
  "stdlib": { "print": "print" },  // 標準ライブラリ関数の名前（省略すると標準名）
  "tokens": {                      // グループ → {キー: 正規表現}（全トークンが必要。空文字も可）
    "comment": { "begin": "#", "end": "(?=\\n)|\\Z" },
    "if": { "begin": "if", "begin.emit": "if ", "then": ":", "end": "" },
    "funcapp": { "begin": "", "name_end": "\\(", "end": "\\)", "arg_sep": ",|(?=\\))", "arg_sep.emit": [", ", ","] },   // emit は候補の配列も可（最初が既定）
    "true": "True", "...": "..."
  },
  "lexical": { "letters": "...", "number": "...", "string": "...", "characters": "..." }
}
```

| キー | 意味 |
|---|---|
| `layout` | `indent` なら、字句解析の前にインデントを仮想トークン（`@INDENT` `@NEWLINE` `@DEDENT`）に置き換える。最上位は文の並びだけを読む |
| `toplevel` | `layout` が `none` のとき、`block`（既定。全体を `block_begin`〜`block_end` で包む）か `bare`（文の並びだけ） |
| `continuation` | indent のとき、直前のブロックの終わりと区切りを入れない行頭（`else` など）。省略すると `else_begin` |
| `space` | トークンの前で読み飛ばす空白 |
| `tokens` の `comment` グループ（`begin` / `end`） | コメント。始まりから最短で終わりまで。両方そろえる（省略するとコメントなし） |
| `word_segment` | トークンが語の文字で終わり、すぐ後ろにも語の文字が続くときは、空白が必須（`if x` と `ifx` の区別）。省略すると使わない |
| `index` | `postfix`（既定、`x[i]`）か `prefix`（`(get x i)`） |
| `lexical` | 名前・数・文字列の字句。`characters` は `quote_begin`〜`quote_end` の中身 |
| `キー.emit`（グループの中） | そのトークンの出力する文字列（または候補の配列）。空白を足して整える（正規表現にマッチする必要がある）。配列は `--random-emit SEED` のときだけ選ぶ |
| `tight_before` | この文字の直前では行末の空白を落とす（閉じ括弧など） |
| `reserved` | 追加の予約語（省略可） |
| `stdlib` | 標準ライブラリ関数の、このシンタックスでの名前（`{標準名: 名前}`） |

**予約語は自動で抽出**されます。トークンの正規表現の先頭にある固定文字列のうち、名前（`lexical.letters`）の形をしたものです（`"else *:"` → `else`）。`(` で始まるトークン（Lisp 風の `\(set`）は予約語にならないので、必要なら `reserved` に書きます。

`kolang --show 名前` で、作ったシンタックスの書き方の例を確認できます（Python 風の例を、そのシンタックスへ変換して表示します）。

`kolang show_snippet SYNTAX [NAME...]` は、カスケードの検査に使うスニペット（`kolang/snippet.py` の `SNIPPETS`。入れ子・連続した区切りなど、衝突しやすい形）を、そのシンタックスで書いて表示します。`--show` より細かい形（添字の中の関数呼び出し、`-` の連続など）が見られ、カスケードでも使えます（`kolang show_snippet "jalike:pylike(funcapp)"`）。名前を渡すと、そのスニペットだけ表示します（`kolang show_snippet jalike index_by_call`）。そのシンタックスで書けないものは、理由つきで知らせます。

`kolang show_ebnf SYNTAX` は、`kolang.md` の規則を、そのシンタックスの記号に置き換えた BNF を表示します（空の記号は省き、`call` の順序・添字の形・`toplevel`・省略可の `neg` / `grouping` の有無も反映します。固定の文字列でない記号は、最後に正規表現を載せます）。見出しと注釈は、モデルに渡しやすいよう簡単な英語で書きます（記号そのものはシンタックスの文字のまま。例: `<expression> "を" <variable> "に代入"   # assignment (assign: value_first)`）。カスケードも指定できます。

### カスケード（一部だけ差し替える）

シンタックスの指定を `ベース:取り込み元(グループ,…)` と書くと、ベースのうち、指定したグループだけを取り込み元のものに差し替えます。`:` でいくつでもつなげられ、左から順に重ねます。

```
kolang conv -f pylike -t 'jalike:jslike(assign,block,funcapp,stdlib)'
```

これは、日本語風をベースに、代入・ブロック・関数呼び出し・標準ライブラリ関数の名前だけを JavaScript 風にしたものです。グループは、`assign` `block` `funcapp` `if` `condition` `literal` `list` `index` `quote` `def` `comment` `space` `stdlib` などです（全部は [syntax.md](syntax.md)）。`block` は `layout` も一緒に取り込みます。

組み合わせによっては、区切りが衝突して、読み書きできなくなります（たとえば Lisp 風は `)` で閉じるので、インデント方式の `block` と混ぜると本体の終わりが決まりません）。`load_syntax` は読み込むときに検査して、問題があれば `UserWarning` を出します（読み込みは続けます。`verify=False` で検査しません）。

- **構造検査**（`kolang/structure.py`）: トークンの定義だけを見て、読み書きできない組み合わせを文章で知らせる。単独のシンタックスにも行う。
- **スニペット検査**（`kolang/snippet.py`）: 構造検査で見つからなかったカスケードについて、40 個の AST を出力 → 読み直し、戻らないものを知らせる。

## 仕組み

```
ソース ─ layout ─▶ テキスト ─ parser ─▶ AST ◀─ comments ─ （コメント）
         (indent)    (scannerless)       │
                                         ├─ unparser ─▶ ソース（別のシンタックス）
                                         └─ pyeval ───▶ 実行（stdlib の関数）
```

| ファイル | 役割 |
|---|---|
| `kolang/ast.py` | AST（dataclass）。コメントは比較（`==`）の対象外 |
| `kolang/syntax.py` | JSON の読み込み・検証、予約語の抽出、カスケード |
| `kolang/layout.py` | インデント → 仮想トークンへの置き換え |
| `kolang/combinators.py` | パーサコンビネータ（PEG 風の順序つき選択、バックトラック、最遠の失敗位置でエラー表示） |
| `kolang/parser.py` | 文法。1 規則 1 ブロックで並べてあり、文法を変えるときはここを直す |
| `kolang/comments.py` | コメントを文に付ける（同じ行 → trailing、それ以外 → 次の文の leading） |
| `kolang/regexgen.py` | 正規表現から固定文字列・出力例・引用符を取り出す |
| `kolang/unparser.py` | AST → ソース。標準ライブラリ関数名の書き換え（`rename_stdlib`）もここ |
| `kolang/stdlib.py` | 標準ライブラリ関数の表（Python のもの）。関数を足すときはここ |
| `kolang/pyeval.py` | 評価器（Visitor）。Python 互換 |
| `kolang/structure.py` / `snippet.py` | カスケードの衝突検査（構造検査 / AST スニペットの往復） |
| `kolang/kofile.py` | `.ko` ファイル（1 行目にシンタックス指定）の読み書き |
| `kolang/kolangeval.py` | 評価問題（隣の `kolangeval.jsonl`）の採点（`kolang check` / `kolang eval --model`）。Solver を差し替えるとモデルの生成も採点できる（`--model` は `make_hf_generator` / `build_context` / `evaluate_recorded`） |
| `kolang/cov.py` | 構文（AST のノード）と標準ライブラリ関数の使用回数（`kolang cov`） |
| `kolang/modelppl.py` | LLM の NLL / PPL でシンタックスの親和度を測る（`kolang modelppl`） |
| `kolang/cli.py` / `examples.py` | `kolang` コマンド / `--show` の例（`show_snippet` は `snippet.show_snippets`、`show_ebnf` は `ebnf.py`） |

## テスト

```
python3 -m unittest discover -s tests -t .
```

評価器のテスト（`tests/test_pyeval.py`）は、同じソースを Python で実行した結果と比べます。`tests/test_modelppl.py` は、モデルを使わず偽の採点関数で確かめます。

カスケードの全順列（744 通り）の検査は遅いので、既定ではスキップします（`KOLANG_MATRIX=1`）。特定の組み合わせだけなら `python3 -m tests.test_cascade_matrix "jalike:jslike(block)"` です。

## 制約

- 演算子（`+` など）、文字列・リストのスライスはありません。必要なら標準ライブラリの関数を足します。負の数は、数の一部ではなく符号の反転（`-1` は `Neg(1)`）で書きます。
- 評価器は、`while` や例外処理など、文法にないものは実行できません。再帰は書けますが、終了条件には比較（`if` の条件）と `sub` などを使います。
- 変換での関数名の書き換えは、標準ライブラリ関数の名前だけです。プログラムが自分で定義した名前は書き換えません。
- コメントは、同じ行の文か次の文に付きます。`else` の行のコメントは、`else` の中の最初の文の前に移ります。空行は保持しません。
- インデント方式では、コメントは 1 行で閉じる形のみ扱えます。インデントに使えるのは半角スペースとタブです。
- doctest 風の例の式は、関数呼び出しか変数だけです（`>>> 1` や `>>> [1, 2]` は不可。`f(...)` か変数に包む）。`>>>` の行の末尾にコメントは書けません。エラーを答えにすることもできません。
- 空のブロックや、書けない名前、負の `Num`（`Neg` を使う）を書き出そうとすると `UnparseError` になります。
- カスケードの既知の衝突（Lisp 風と、インデント方式や `if_end` などが空のシンタックスの組み合わせ、`;` の重なりなど）は、警告で知らせるだけで、直せません。

## ライセンス

[MIT License](LICENSE)
