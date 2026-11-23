# シンタックス定義（JSON）の書き方

kolang の文法の骨格は固定です（[kolang.md](kolang.md)）。区切りの記号は**トークン名**で書かれていて、シンタックス定義の JSON は、そのトークン名に**正規表現**を割り当てます。ここでは JSON の全キーと、トークンの意味、読み書きの規則をまとめます。

実例は `kolang/syntaxes/` の `pylike.json`（Python 風）、`ja.json`（日本語風）、`lisplike.json`（Lisp 風）、`jslike.json`（JavaScript 風）、`pslike.json`（PostScript 風）です。

## 置き場所と使い方

- `kolang/syntaxes/NAME.json` に置くと、`NAME` という名前で使えます（`kolang --list` に出ます）。
- 任意の場所の JSON も、パスを指定して使えます（`kolang conv -f ./my.json -t ja`、`kolang --show ./my.json`）。
- Python からは `load_syntax("NAME")` または `syntax_from_dict(dict)` です。
- 文字コードは UTF-8 です。

書いたら、まず `kolang --show NAME` で、書き方の例が思いどおりに出るか確認します。そのシンタックスで書けない構文があれば、例の場所に理由が出ます。

## 複数のシンタックスを重ねる（カスケード）

シンタックスの指定は `BASE:OVERLAY(グループ,…)` の形で、ベースの一部だけを別のシンタックスに差し替えられます。`kolang --show`、`-f`、`-t`、`load_syntax` のどれにも書けます。

```
kolang conv -f pylike -t 'ja:jslike(assign,block,funcapp)'
```

- 左がベースで、`:` でいくつでもつなげられます（左から順に重ねる）。
- 括弧のグループだけを OVERLAY から取り込みます。グループは、JSON の `tokens` のグループ（`block` `if` など）が単位です。取り込んだグループは、そのトークンも `キー.emit` も OVERLAY のものになります。括弧を省くと全部の置き換えです。
- `block` は `layout` `toplevel` も一緒に取り込みます（インデントと `{ }` は別の配置のため）。indent から none に変わるときは、`space` に改行を足します。
- 結果は 1 つのシンタックスです。検査（`emit` の整合など）も同じように行われます。

| グループ | 取り込むもの |
|---|---|
| `comment` | `comment` グループ（`comment_begin` `comment_end`） |
| `block` | `block_*`、`layout` `toplevel` |
| `assign` `append` `inc` `dec` `if` `else` `repeat` `return` | 同名の `*_*` トークン |
| `break` | `break` |
| `def` | `def_*` `params_*` `param_*` |
| `condition` | `ne` `lt` `gt` `le` `ge` `eq` の全部（個別にも書ける） |
| `literal` | `true` `false` `none` |
| `list` | `list_*` |
| `neg` | `neg_*`（符号の反転） |
| `grouping` | `grouping_*`（式の括弧） |
| `index` | `index_*` と `index` |
| `quote` | `lexical.quote`（`begin` `end`）と `lexical.characters` |
| `funcapp`（`call`） | `call_*` `arg_*` と `call`（引数と名前の順。JSON では `tokens.funcapp` に `order` ごと書く） |
| `name` `number` `string` | 同名の `lexical` |
| `space` | `space` `word_segment` `tight_before` |
| `stdlib` | `stdlib`（標準ライブラリ関数の名前） |

注意: 取り込んだ記号どうしが衝突しないかは、作る人が確かめます（`kolang --show` で例が書けるか見る）。読み込み時に、衝突を検査して警告（`UserWarning`）を出します（読み込みは続きます。`load_syntax(..., verify=False)` で止められます）。まず構造検査で、原因を名指しします: ①indent なのに `if_end` などが空でない、②none で `block_end` が空なのに `if_end` `repeat_end` `def_end` も空（本体の終わりが決まらない）、③コメントの記号に他のトークンがマッチする、④名前が記号（`--` など）を飲み込む。lisplike のように各形が `)` で閉じるシンタックスと、閉じが空のシンタックス（indent など）を混ぜると、①②になります。構造検査で見つからないカスケードは、`snippet.SNIPPETS`（AST のスニペット）を出力 → パースして、戻らないものを知らせます。

## 全体の形

```jsonc
{
  "name": "mylang",                // 省略するとファイル名
  "description": "説明",            // kolang --list に出る
  "layout": "indent",              // "indent" | "none"（省略時は "none"）
  "continuation": "else\\b",       // layout が indent のときだけ
  "space": " +",                   // 省略時は " +"
  "word_segment": "[A-Za-z0-9_]",  // 省略可
  "index": "postfix",              // "postfix"（既定）| "prefix"
  "toplevel": "block",             // "block"（既定）| "bare"（layout が none のとき）
  "tight_before": "\\)",           // 省略可
  "tokens":  { "...": "..." },     // 必須。グループにまとめて書く（下の「トークン」）
  "lexical": { "...": "..." },     // 必須
  "reserved": ["print"],           // 省略可
  "stdlib": { "print": "表示" }  // 省略可。標準ライブラリ関数の名前（標準名 → 名前）
}
```

JSON の文字列の中では、正規表現のバックスラッシュを二重にします。`\(` は `"\\("`、改行は `"\\n"` です。正規表現は Python の `re` のものです。

## トークン（`tokens`）

トークンは、**グループにまとめて**書きます。グループ名 + `_` + キーが、トークン名です（`block` グループの `begin` は `block_begin`）。`キー.emit` は、そのトークンの出力用の文字列です（後述）。`true` `false` `none` `break` は、グループに入らず、文字列で書きます。これがカスケード（`ja:jslike(block)`）の取り込みの単位です。

```jsonc
"tokens": {
  "comment": { "begin": "#", "end": "(?=\\n)|\\Z" },
  "block":   { "begin": ":", "sep": ";", "sep.emit": "; ", "end": "" },
  "if":      { "begin": "if", "begin.emit": "if ", "then": ":", "end": "" },
  "funcapp": { "order": "func_first", "begin": "", "name_end": "\\(", "end": "\\)",
               "arg_sep": ",|(?=\\))", "arg_sep.emit": [", ", ","] },   // order: "func_first"（既定）| "args_first"
  "true": "True"
}
```

以下、トークン名は `block_begin` のように、平らな名前で書きます。

**すべてのトークンを定義します**（足りないものがあると、そのトークンを使う規則を組み立てるときに `token 'xxx' is not defined` になります）。空文字列 `""` も有効です。何も書かない記号に使います（Python 風の `assign_begin` など）。

各トークンは、文法の中で次の位置に現れます。正確な文法は [kolang.md](kolang.md) です。

### ブロック

| トークン | 位置 |
|---|---|
| `block_begin` `block_sep` `block_end` | `block_begin (文 block_sep)* block_end`。文は必ず `block_sep` で終わる |

### 文

| 文 | トークン列 |
|---|---|
| 代入 | `assign_begin 変数 assign_op 式 assign_end` |
| 追加 | `append_begin 式 append_sep 式 append_end` |
| 増やす | `inc_begin 変数 inc_end` |
| 減らす | `dec_begin 変数 dec_end` |
| if | `if_begin 条件 if_then ブロック (else_begin ブロック else_end)? if_end` |
| くり返す | `repeat_begin 式 repeat_do ブロック repeat_end` |
| 抜ける | `break`（単一のトークン） |
| 関数定義 | `def_begin 名前 def_name_end params_begin (名前 param_sep)* params_end ブロック def_end` |
| 戻り値 | `return_begin 式 return_end` |

増やす・減らすは 1 ずつです。`inc_end` などに、`+= 1` の「1」まで含めます。

### 条件

比較ごとに `X_begin 式 X_sep 式 X_end` です。`X` は次のとおりです。

| `X` | 比較 |
|---|---|
| `ne` | `!=` |
| `lt` | `<` |
| `gt` | `>` |
| `le` | `<=` |
| `ge` | `>=` |
| `eq` | `==` |

### 式

| 式 | トークン |
|---|---|
| 真偽値・none | `true` `false` `none` |
| リスト | `list_begin (式 list_sep)* list_end` |
| 式の括弧 | `grouping_begin 式 grouping_end`。**省略できる**トークン。AST は中の式そのまま。ja は `(` `)`（添字の `の(` `)番目` と合わせて `aの((x)におけるlenの値)番目`）。`call_begin` と同じ `(` でも、関数呼び出しを先に試して、だめなら括弧と読む |
| 符号の反転 | `neg_begin 式 neg_end`（`-X`）。**省略できる**トークンで、`neg_begin` が無いシンタックスは `-X` を読み書きしない（書き出しは `UnparseError`）。pylike・ja・jslike は `-`（`neg_end` は空）、lisplike は `(neg X)`、`neg_begin` が空なら後置（pslike の `x neg`。式のあとに `neg_end` を畳み込む）（`neg` は予約語）。数字（`number`）は符号を含まないので、`-1` は `Neg(Num(1))` |
| 関数呼び出し | `call_begin 名前 call_name_end (式 arg_sep)* call_end`（`order` が `"args_first"` のときは `call_begin (式 arg_sep)* call_name_end 名前 call_end`） |
| 配列の添字 | `index_begin` `index_end`（`index_sep` は `prefix` のとき）。下の「配列の添字」を参照 |
| 特殊な名前 | `quote_begin 文字列 quote_end`。`lexical.letters` に合わない名前を書く囲み |

### コメント

`tokens` の `comment` グループに `begin` と `end` を書きます（`comment_begin` `comment_end`。両方そろえる。片方だけだとエラー）。どちらも書かなければ、コメントのないシンタックスです。

- コメントは、`comment_begin` から最短で `comment_end` までです（`.*?` で DOTALL）。
- 行末で終わる形は `"comment_end": "(?=\\n)|\\Z"` です（改行そのものは読み飛ばしの側が読みます）。
- `/* ... */` のような形は `"comment_begin": "/\\*"`、`"end": "\\*/"` です。

### 区切りトークン（`*_sep`）の書き方

`(式 sep)*` のように、区切りは**要素ごとに**付きます。つまり最後の要素のあとにも区切りが付きます。そこで、閉じ記号の直前なら空にマッチする、という先読みの枝を足します。

| 形 | 書き方 |
|---|---|
| `[1, 2]`（カンマ区切り、末尾のカンマも可） | `",|(?=\\])"` |
| `(list 1 2)`（空白区切り） | `""` |
| 末尾にも必須 | `","` |

`list_sep` `arg_sep` `param_sep` に使います。出力のときは、最後の要素のあとは空の枝を採り、それ以外は最初の枝を採ります。

## 字句（`lexical`）

4 つとも必須です。

| キー | 意味 |
|---|---|
| `letters` | 名前。`"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*"` のように、**最長一致で名前全体にマッチする**形で書く。`_` は引用の記号なので、先頭と末尾には置かない（`x_` が名前になると、`_` を読めなくなる） |
| `number` | 数。`.` を含めば小数、含まなければ整数として読む |
| `string` | 文字列リテラル。引用符で囲む形（下記） |
| `quote` | 名前を囲む記号 `{"begin": "_", "end": "_"}`。内部では `quote_begin` `quote_end` のトークン（全シンタックスで原則 pylike と同じ `_`）。`tokens` に書いても読める |
| `characters` | `quote_begin` と `quote_end` の中身。`"[^_\\n]+"` のように、`quote_end` を含まない形で書く |

### 文字列リテラル

- 両端の 1 文字が引用符です。選択（`"..."|'...'`）なら、最初の枝の両端が書き出し時の引用符になります。
- 値は、両端の 1 文字を外して、`\n` `\t` `\r` `\0` と、それ以外の `\x`（→ `x`）を解いたものです。
- 書き出しでは、`\` と、終わりの引用符と、改行などをエスケープし直します。
- 例: `"\"(?:[^\"\\\\\\n]|\\\\.)*\""`。これは正規表現 `"(?:[^"\\\n]|\\.)*"` です。

## 固定の書き方（シンタックスでは変えられないもの）

doctest 風の例は、`>>> 式` の次の行に JSON の答えです（`>>>` と答えは固定。式も全シンタックスで pylike の書き方。`f(x, y)` か変数だけ）。答えの行は生の文字列として読むので、`space` やコメントの設定は関係しません。`>>>` の行の末尾にコメントは書けません。

## 空白・コメント・語の区切り

### 読み方

このパーサは、字句解析器を持たず、トークンの正規表現を位置から直接マッチさせます（トークンごとに先読みが使えます）。

1. **トークンの前で、空白とコメントを読み飛ばす**（`space` と、`comment_begin`〜`comment_end`）。`characters` だけは読み飛ばさない。
2. トークンの正規表現を、その位置から `match` する。**空にマッチしてもよい**。
3. **語の区切りの規則**（`word_segment`）を調べる。

### 語の区切り（`word_segment`）

語を作る 1 文字の正規表現です（例: `[A-Za-z0-9_]`）。

> トークンの**最後の文字**が `word_segment` にマッチし、**すぐ後ろの文字**も `word_segment` にマッチするときは、そこでトークンを切れない（空白が必要）。

これで、`if` と `ifx`、`return1`、`1y` を区別できます。トークンの正規表現に `\b` を書く必要はありません。

- 記号どうし、記号と語は、空白なしで続けて書けます（`x=1`、`f(1,2)`）。
- 日本語の助詞や漢字を `word_segment` に含めなければ、`xに1を代入` のように空白なしで書けます。
- 省略すると、この規則は使いません。
- 規則に反したとき、エラーの期待に `space` が出ます。

### 空白（`space`）

トークンの前で読み飛ばす空白の正規表現です。既定は半角スペース 1 個以上（`" +"`）です。

- 複数の空白は 1 つの正規表現にまとめます（`"[ 　]+"` は半角と全角のスペース）。
- タブや改行を許すときは、ここに入れます（`"[ \\t\\r\\n]+"`。Lisp 風）。
- `layout` が `indent` のときは、改行はこの設定に関係なく読み飛ばされます。

## 配置（`layout`）

### `"none"`（既定）

テキストをそのまま読みます。ブロックは `block_begin` `block_sep` `block_end` の記号で表します（`{` `;` `}` など）。空の記号（`""`）でもかまいません（Lisp 風）。プログラム全体は 1 つのブロックです。

### `"indent"`

インデントでブロックを表します。読む前に、行の並びを仮想トークンに置き換えます。

| 仮想トークン | 意味 | 割り当てるトークン |
|---|---|---|
| `@INDENT` | インデントが深くなった | `block_begin` |
| `@NEWLINE` | 同じ深さの次の行 | `block_sep` |
| `@DEDENT` | インデントが浅くなった | `block_end` |

```jsonc
"block": { "begin": "@INDENT", "sep": "@NEWLINE", "end": "@DEDENT" }
```

`@...` は、`indent` のときだけ、トークンの値全体として書けます（正規表現とは混ぜられない）。

- 最上位は `block_begin` と `block_end` なしの文の並びです。
- 空行は無視します。コメントだけの行は、インデントの計算に加えません。
- インデントはスペースとタブの文字数（タブは 4 とみなす）です。浅くなるときは、すでにあるインデントの深さに戻る必要があります（違うとエラー）。
- ブロックを開く文（`if` や `def`）の見出しの最後に、`if_then` や `params_end` で `:` などを書きます。そのあとに改行して、インデントを深くします。
- **コメントは 1 行で閉じる**ものだけです（複数行のコメントは扱えません）。
- ブロックの**あと**に付くトークン（`if_end` `else_end` `repeat_end` `def_end`）は、**空**にしてください（書き出せなくなります）。

### `continuation`

`indent` のとき、ブロックの終わり（`@DEDENT`）と次の行のあいだに、区切り（`@NEWLINE`）を入れない行頭の正規表現です。`else` のように、`if` の続きになる行に使います。

**省略できます**: 省略すると `else_begin` を使います（語で終わるときは、後ろに語が続かないことも見ます）。`else` のトークンを差し替えても連動するので、普通は書かなくて構いません。

```jsonc
"continuation": "else\\b"        // pylike
"continuation": "そうでなければ"   // ja
```

## 最上位（`toplevel`）

| 値 | 意味 |
|---|---|
| `"block"`（既定） | `layout` が `none` のとき、プログラム全体を `block_begin`〜`block_end` で包む（Lisp 風の `""` はこれ） |
| `"bare"` | 最上位は `block_begin` `block_end` なしの文の並びだけ。JavaScript 風など、`{ }` で全体を括らない形用。`indent` は常にこの形 |

`bare` のとき、書き出しは最上位の文を 1 行に 1 つ書きます。

## 関数呼び出し（`tokens.funcapp`）

`funcapp` グループに、`begin` `name_end` `end`（内部名 `call_*`）、引数の区切り `arg_sep`、並び順 `order` をまとめて書きます（`order` は省略すると `func_first`）。

### 順序（`order`）

| 値 | 例 | 並び |
|---|---|---|
| `"func_first"`（既定） | `f(x, y)` | `call_begin` 名前 `call_name_end` 引数 `call_end` |
| `"args_first"` | `(x, y)におけるfの値`（ja） | `call_begin` 引数 `call_name_end` 名前 `call_end`（`call_name_end` は引数と名前のあいだ） |

AST は同じ `Call(func, args)` で、シンタックス間の変換でも順序が入れ替わります。

## 配列の添字（`index`）

| 値 | 形 | 使うトークン |
|---|---|---|
| `"postfix"`（既定） | `x[i]` | `index_begin` が対象と添字のあいだ、`index_end`（`index_begin` が空なら空白を許す。pslike の `a 1 get`） |
| `"prefix"` | `(get x i)` | `index_begin` が先頭、`index_sep` が対象と添字のあいだ、`index_end` |

`prefix` のときは、`(get ...)` を関数呼び出しより先に試します（`(f x i)` と読まないため）。`(getx ...)` のように、`index_begin` の後ろに語の文字が続くものは、語の区切りの規則で添字になりません。

## 標準ライブラリ関数の名前（`stdlib`）

kolang には演算子も `print` もありません。出力や四則演算は、標準ライブラリの**関数**で書きます（`kolang/stdlib.py`。最初の実装は Python のもの）。

| 標準名 | 働き |
|---|---|
| `print` | 出力 |
| `add` `sub` `mul` `div` | 四則演算（`+` `-` `*` `/`。`add` は文字列・リストの連結にも使える） |
| `int` `str` `float` `bool` | 型の変換（Python の `int()` `str()` `float()` `bool()`） |
| `mod` `pow` | 剰余（`%`）、べき乗（`**`。2 引数） |
| `abs` `chr` `len` `list` `max` `min` `ord` `range` `repr` `reversed` `round` `sorted` `sum` | Python の同名の組み込み関数 |

シンタックスの JSON のトップレベルに `stdlib` オブジェクトを置き、標準名をキーに、**そのシンタックスでの名前**を書くと、関数の名前を変えられます。書かなかったものは標準名のままです。

```jsonc
"stdlib": {
  "print": "表示",
  "add": "たし算"
}
```

実例は、`ja.json`（`表示` `足し算` `引き算` `掛け算` `割り算` `余り` `べき乗` `整数化` `文字列化` `小数化` `ブール化`）です。`pylike.json` などは、標準名のままを明示しています（`"stdlib": {"print": "print", ...}`）。

- 名前は、`lexical.letters` に合う（かつ予約語でない）か、`lexical.characters` に合う（`quote_begin`〜`quote_end` で囲んで呼ぶ）ものにします。上の `たし算` は漢字を含むので、日本語風では `_たし算_(1, 2)` のように書きます。
- `stdlib` で定義した名前は、**関数呼び出しの関数名の位置**では、`letters` に合わない名前（漢字など）でも引用なしで書けます（`(1)における表示の値`）。パーサは stdlib の名前を先に試し、出力器も引用せずに書きます。変数など、ほかの位置では今までどおり引用（`_表示_`）が要ります。
- 読み込み時に検査します（`ValueError`）: `stdlib` のキーが標準名にない関数、書けない名前、名前の重複（`print` を `len` にする、など）。
- 評価器（`kolang run`）が、この名前で関数を並べます。パースには関係しません（AST には書いた名前が入ります）。
- **変換では、関数名も書き換わります**（`kolang conv -f pylike -t ja` で `print(x)` → `表示（x）`）。標準ライブラリ関数の呼び出しと、関数名の参照だけです。
  - プログラムが同じ名前を自分で定義している（関数・引数・代入される変数）ときは、自作の名前なので書き換えません（Python と同じく、自作が標準を隠す）。
  - 書き換えた名前が、プログラムの自作の名前とぶつかるとき（pylike の `add(1, 2)` を ja にするのに、自作の `足し算` がある、など）は、意味が変わるので `UnparseError` です。使われていない名前は、ぶつかっても構いません。
  - 書き換えたくないときは、`kolang --no-rename`、Python からは `convert(..., rename=False)` です。
  - `--show` の例も、そのシンタックスの名前で出ます。
- 自分で同じ名前の関数を定義すると、そちらが優先されます（Python と同じく、ローカルが組み込みを隠す）。
- カスケード（`ja:jslike(...)`）では、`stdlib` グループ（`stdlib` キー）で取り込めます。取り込まなければ、ベースの名前のままです（`ja:jslike(assign,block,funcapp)` の関数名は `表示` など）。

## 予約語（自動抽出）

トークンの正規表現の**先頭にある固定文字列**のうち、`lexical.letters` の全体にマッチするものが、自動で予約語になります。

| トークンの正規表現 | 予約語 |
|---|---|
| `"if"` | `if` |
| `"else *:"` | `else` |
| `"for +_ +in +range\\("` | `for` |
| `"\\(set"` | （なし。先頭が `(`） |
| `"もし"` | （なし。`letters` の形でない） |

予約語は、名前（変数・関数・引数）にできません。同じ文字列を使いたい名前は、`quote_begin`〜`quote_end` で囲めます。追加したい語があれば、`"reserved": ["print"]` に書きます。

## 出力用のキー

読み込みには関係なく、書き出し（変換、`--show`）にだけ使います。

### `emit`

グループの中に、トークンのキーの隣へ `"キー.emit": "出力する文字列"` と書きます。省略したトークンは、正規表現から作った文字列を使います。

```jsonc
"assign": { "op": "=", "op.emit": " = " },        // x = 1
"param":  { "sep": ",", "sep.emit": ", " },       // (a, b)
"if":     { "begin": "if", "begin.emit": "if " }  // if x
```

- 正規表現から作る文字列は、選択なら最初の枝、繰り返しなら最小回数、文字クラスなら最初の 1 文字です。先読みとアンカーは文字を作りません（`=(?!=)` → `=`、`else *:` → `else:`、`" +"` → `" "`）。
- `emit` の文字列は、前後の半角スペースを除いたものが、そのトークンの正規表現に**全体マッチ**する必要があります（読み込み時に検査され、違うとエラー）。つまり、**空白を足すためのもの**です。
- 値は、**候補の配列**にもできます（`"sep.emit": [", ", ","]`）。各候補が、正規表現に全体マッチする必要があります。出力のとき、**最初の候補が既定**です。`kolang --random-emit SEED`（`convert(..., random_emit=SEED)`）で seed を与えたときだけ、候補から seed つきで選びます（同じ seed なら同じ結果）。
- 最後の要素のあとの区切りは、空の枝があれば空になります（`emit` は使われません）。
- 語の文字どうしが隣り合うときは、`emit` がなくても空白が 1 つ入ります（`if` と `x`）。

### `tight_before`

この正規表現にマッチする文字（1 文字目）の直前では、行末の空白を落とします。閉じ括弧用です。

```jsonc
"tight_before": "\\)"      // (list ) → (list)
```

### 出力の整形

- `indent` では、1 文 1 行で、4 スペースずつインデントします。
- `none` で `space` が改行にマッチするときは、最上位の文を 1 行に 1 つ書きます（入れ子の中は 1 行のまま）。
- コメントは、書き出し先に `comment_begin`〜`comment_end` があれば、その記号で書き直します（なければ捨てます）。

## 検査（読み込み時）

次の場合は、読み込み時に `ValueError` になります。

- `layout` が `indent` / `none` 以外、`index` が `postfix` / `prefix` 以外、`call` が `func_first` / `args_first` 以外
- `@...` を `indent` 以外で使った、または `@INDENT` `@NEWLINE` `@DEDENT` 以外の `@...`
- `comment_begin` と `comment_end` の片方だけがある
- `lexical` に `letters` `number` `string` `characters` が足りない
- どれかの正規表現が不正（キー名つきで報告されます）
- `キー.emit` が、未定義のトークンを指す、正規表現にマッチしない、値が、文字列でも、空でない文字列の配列でもない

## 作るときの注意

- **`<` と `<=`、`=` と `==`**: 条件は `ne` `lt` `gt` `le` `ge` `eq` の順に試し、**選択は順序つき**です。`<=` に `lt_sep` の `<` がマッチしないよう、`"<(?!=)"` のように先読みで除きます。代入の `=` も `"=(?!=)"` にします。
- **先頭が空のトークン**: Python 風では `assign_begin` や `ne_begin` が空です。どの文かは、そのあとの記号で決まります。パーサがバックトラックして、選択肢を順に試します。
- **選択肢の順**: 文は代入・追加・増やす・減らす・if・くり返す・抜ける・関数定義・戻り値の順です。式は、文字列・数・真偽値・none・リスト・（prefix の添字）・関数呼び出し・変数の順です。同じ書き出しで始まる構文があるときは、この順に注意します（`(list ...)` は関数呼び出しより先に読まれる、など）。
- **予約語の取りこぼし**: 括弧などで始まるトークン（Lisp 風の `\(set`）は、予約語になりません。名前と衝突しない書き方かを確認します。
- **名前の文字**: `letters` に漢字やひらがなを入れると、助詞や述語を名前の一部として読んでしまいます（日本語風は英数字だけにし、それ以外は `_` で囲む）。
- **`kolang --show` を使う**: 新しく作ったら、`kolang --show ./my.json` で全構文の例を出し、`kolang conv -f pylike -t ./my.json` で変換して、読み直せるか確かめます。変換は、書き出した結果を読み直して、AST が同じか確かめます（違うと `UnparseError`）。
