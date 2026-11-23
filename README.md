# kolang（こ言語）

**書き方（シンタックス）を選べる言語。** 文法の骨格は固定で、区切りの記号を JSON の正規表現で差し替えると、Python 風・日本語風・Lisp 風・JavaScript 風など、好きな見た目で同じプログラムを書けます。

```
# Python 風                      ※ 日本語風                       ; Lisp 風
def add(a, b):                  関数 add(a, b)とは               (def add (a b) (return a))
    return a                        aを返す
s = 0                           sに0を代入                         (set s 0)
for _ in range(3):              3回くり返す                        (repeat 3 (inc s))
    s += 1                          sを増やす
y = x[0]                        yにxの(0)番目を代入                  (set y (get x 0))
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
kolang show_ebnf ja                 そのシンタックスの BNF（kolang.md の規則を、そのシンタックスの記号で）
kolang show_example ja [NAME...]   スニペット（検査用の AST）をそのシンタックスで表示（--list で名前の一覧）
kolang conv prog.py -f pylike -t ja   シンタックスを変換（ファイルなしなら標準入力、-o で出力先）
kolang conv prog.ko -t ja             .ko なら -f は不要
kolang conv prog.py -f pylike         構文チェックだけ（-t を省略）
kolang run prog.py [-f pylike]     実行する（ファイルなしなら標準入力）
kolang run prog.ko                 .ko ファイルを実行する（シンタックスは 1 行目で指定）
kolang modelppl [-s SYNTAX...]     シンタックスと LLM の親和度を測り、modelppl.csv に書く
```

- シンタックスは、名前（`--list` に出るもの）、JSON ファイルのパス、またはカスケード（後述）で指定します。`python -m kolang ...` でも同じです。
- 変換では、標準ライブラリ関数の名前も書き換わります。止めるには `--no-rename` です。
- `*.emit` に候補の配列を書くと、`--random-emit SEED` のときだけ候補から選びます（省略すると常に最初）。
- `.ko` ファイルは、1 行目に ` ```ja:jslike(assign) ` のようにシンタックスを書き、閉じの ` ``` ` までをコードとして読みます（`-f` は不要）。`kolang run x.ko` は、同じフォルダに `x.doctest`（フェンスなし、同じシンタックスのコードに、`>>> f(x)` と答えを並べたもの）があれば、続けてテストします。本体で定義した名前（関数・変数）が見えます。`-o out.ko` で変換結果を `.ko` 形式で書けます。
- `kolang modelppl` は、`modelppl.csv` の第一カラム `syntax` のシンタックスについて、`NLL, tok, char, PPL, bpc` を計算して埋めます（ファイルがなければ、4 つの組み込みシンタックスで新規作成）。既定のモデルは `Qwen/Qwen2.5-Coder-1.5B-Instruct`（`-m` で変更）。詳しくは [modelppl.md](modelppl.md)。
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
| `abs` `chr` `input` `len` `list` `max` `min` `ord` `range` `repr` `reversed` `round` `sorted` `sum` | Python の同名の組み込み関数 |

関数の名前は、シンタックスの JSON の `stdlib`（`{"print": "表示"}` の形）で変えられます。`ja.json` は漢字です（`表示` `足し算` `引き算` `掛け算` `割り算` `余り` `べき乗` `整数化` `文字列化` `小数化` `ブール化`）。

```
$ echo 'print(add(1, 2))' | kolang conv -f pylike -t ja
表示（足し算（1、2））
```

自分で同じ名前の関数を定義すると、そちらが優先され、変換でも書き換えません。書き換えた名前が自作の名前とぶつかるときは `UnparseError` です。

### doctest 風の例

`>>> 式` の次の行に、答えを JSON の値で書きます。`>>>` と答えの書き方は固定です。式も**どのシンタックスでも pylike の書き方**で、関数呼び出し `f(x, y)` か変数（`x[0]` も可）だけです（引数は pylike の式）。シンタックスを変えても、doctest はそのまま読めます。実行すると答え合わせをして、外れても続けます。

```
>>> f([1, "a", None], x[0])
[1, "a", null]
```

標準関数は pylike の名前（標準名）で書きます。ja で読むと `add` は `足し算` になります（プログラムが同じ名前を自分で定義していれば、そちらが優先。`.doctest` の別ファイルでも、本体の自作の名前が優先）。

型まで厳密に比べます（`1` と `true` と `1.0` は別）。

## Python から使う

```python
import kolang
from kolang.pyeval import run

tree = kolang.parse("x = [1, 2]\n", "pylike")          # → AST（kolang.ast）
kolang.unparse(tree, "ja")                              # → "xに【1, 2】を代入\n"
kolang.convert("print(1)\n", "pylike", "ja")            # → "表示（1）\n"
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
| `ja` | 日本語風。ブロックは `『 』`。名前は英数字、漢字などは `_` で囲む（`_合計_`） |
| `lisplike` | Lisp 風。S 式。配列の添字は `(get x i)` |
| `jslike` | JavaScript 風。`{ }` と `;`（省略可）、`xs.push(1)`、`x++`、`function`。最上位は括らない |

## 言語の骨格

文法は [kolang.md](kolang.md) にあります。

- **文**: 代入、追加、増やす、減らす、if / else、くり返す（n 回）、抜ける、関数定義、戻り値、関数呼び出し、doctest 風の例
- **式**: 変数、配列の添字、文字列、数、真偽値、none、リスト、関数呼び出し、符号の反転（`-x`。`neg_begin` が無いシンタックスでは使えない）
- **条件**: `!=` `<` `>` `<=` `>=` `==`
- 区切りの記号は `block_begin`、`if_then` のような**トークン名**で書かれていて、それぞれが正規表現です。シンタックス定義の JSON は、トークンを**グループ**（`block` `if` など）にまとめて、`"block": {"begin": ..., "sep": ...}` のように書きます（グループ名 + `_` + キーがトークン名）。グループが、カスケードの取り込みの単位です。

## シンタックスを作る

`kolang/syntaxes/` に JSON を置きます（または JSON のパスを直接指定します）。`pylike.json`、`ja.json`、`lisplike.json`、`jslike.json` が実例です。全キーの詳しい書き方は [syntax.md](syntax.md) にあります。

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

`kolang show_example 名前` は、カスケードの検査に使うスニペット（`kolang/snippet.py` の `SNIPPETS`。入れ子・連続した区切りなど、衝突しやすい形）を、そのシンタックスで書いて表示します。`--show` より細かい形（添字の中の関数呼び出し、`-` の連続など）が見られ、カスケードでも使えます（`kolang show_example "ja:pylike(funcapp)"`）。名前を渡すと、そのスニペットだけ表示します（`kolang show_example ja index_by_call`）。そのシンタックスで書けないものは、理由つきで知らせます。

`kolang show_ebnf 名前` は、`kolang.md` の規則を、そのシンタックスの記号に置き換えた BNF を表示します（空の記号は省き、`call` の順序・添字の形・`toplevel`・省略可の `neg` / `grouping` の有無も反映します。固定の文字列でない記号は、最後に正規表現を載せます）。カスケードも指定できます。

### カスケード（一部だけ差し替える）

シンタックスの指定を `ベース:取り込み元(グループ,…)` と書くと、ベースのうち、指定したグループだけを取り込み元のものに差し替えます。`:` でいくつでもつなげられ、左から順に重ねます。

```
kolang conv -f pylike -t 'ja:jslike(assign,block,funcapp,stdlib)'
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
| `kolang/modelppl.py` | LLM の NLL / PPL でシンタックスの親和度を測る（`kolang modelppl`） |
| `kolang/cli.py` / `examples.py` | `kolang` コマンド / `--show` の例（`show_example` は `snippet.show_snippets`、`show_ebnf` は `ebnf.py`） |

## テスト

```
python3 -m unittest discover -s tests -t .
```

評価器のテスト（`tests/test_pyeval.py`）は、同じソースを Python で実行した結果と比べます。`tests/test_modelppl.py` は、モデルを使わず偽の採点関数で確かめます。

カスケードの全順列（744 通り）の検査は遅いので、既定ではスキップします（`KOLANG_MATRIX=1`）。特定の組み合わせだけなら `python3 -m tests.test_cascade_matrix "ja:jslike(block)"` です。

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
