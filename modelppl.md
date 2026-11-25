# modelppl — シンタックスと LLM の親和度を測る

同じプログラム（AST）を、シンタックスごとに出力し、言語モデルがそのコードをどれだけ「ありそう」と思うかを測る。
値が小さいほど、モデルにとって書きやすい（読みやすい）シンタックスといえる。

- 実装: `kolang/modelppl.py`（テスト: `tests/test_modelppl.py`）
- 入力: `kolang/snippet.py` の `SNIPPETS`（40 個。構文ごとの単体と、入れ子・組み合わせ）
- 既定のモデル: `Qwen/Qwen2.5-Coder-1.5B-Instruct`（`-m` で変える）
- 依存: `torch` と `transformers`（測るときだけ読む）

## 使い方

```
kolang modelppl pylike jalike lisplike jslike   # 4 つのシンタックスを既定モデルで測る
kolang modelppl all                             # syntaxes/ の全シンタックス（名前順に展開。他の指定と併用も可）
kolang modelppl pylike "jalike:jslike(assign)"  # カスケードも可
kolang modelppl -m allenai/OLMo-2-0425-1B pylike  # モデルを変える（--model）
kolang modelppl pylike --snippets assign,index --show  # 一部のスニペットだけ。出力したコードも表示
kolang modelppl pylike --json out.json          # スニペットごとの結果を JSON に保存
kolang modelppl pylike --no-csv                 # CSV に書かない
kolang modelppl --list-snippets                 # スニペット名の一覧
python3 -m kolang.modelppl ...                  # 同じ（サブコマンドなしでも呼べる）
```

| 引数・オプション | 意味 |
|---|---|
| `SYNTAX...` | 測るシンタックス（1 個以上。必須） |
| `-m, --model` | Hugging Face のモデル名 |
| `--device` | `cpu` / `cuda` / `mps`（既定は自動） |
| `--csv FILE` | 結果の CSV（既定 `modelppl.csv`） |
| `--no-csv` | CSV に書かない |
| `--snippets` | スニペット名をカンマ区切りで（既定は全部） |
| `--show` | 出力したコードと、スニペットごとの値も表示 |
| `--json FILE` | スニペットごとの結果を JSON で保存 |

## CSV（modelppl.csv）

列は `model, syntax, NLL, tokens, PPL, bpc`。

```
model,syntax,NLL,tokens,PPL,bpc
Qwen/Qwen2.5-Coder-1.5B-Instruct,pylike,2820.27,754,42.116,2.7945
Qwen/Qwen2.5-Coder-1.5B-Instruct,jalike,5094.57,1337,45.171,4.2217
```

- キーは `(model, syntax)`。同じ組があれば置き換え、なければ末尾に足す。ほかのモデル・シンタックスの行はそのまま残る。
- 古い形式（`syntax,NLL,tok,char,PPL,bpc`）は、既定モデルの結果として読み、次の書き込みで新しい列に直す。
- 値は、そのとき一緒に指定したシンタックスの全部で出力できたスニペットだけの合計。比べたいシンタックスは同じ実行で測る。
- 読めないシンタックス名（存在しない・カスケードの書き方が違う）はエラーで止まる。

## 指標

トークナイザによって、同じコードでもトークン数が違う。PPL（1 トークンあたり）だけでは比べにくいので、4 つを並べる。

| 列 | 意味 |
|---|---|
| `NLL` | 負の対数尤度の合計（nats）。**同じ AST どうしの比較では、いちばん公平** |
| `tok` | モデルが予測したトークン数 |
| `char` | 出力したコードの文字数 |
| `PPL` | `exp(NLL / tok)`。1 トークンあたりの perplexity |
| `bpc` | `NLL / (char × ln 2)`。1 文字あたりのビット数。トークナイザの違いをならした指標 |

CSV の値は、**全シンタックスで出力できたスニペットだけ**の合計で求める（条件をそろえるため）。
あるシンタックスが一部のスニペットを出力できないと（負の数、空のブロックなど）、その分は全シンタックスから外れる。
外れた数は標準出力の表の `skip` 列に出る。

## 測り方

1. スニペット（AST）を `unparse` でシンタックスの文字列にする。
2. 先頭に BOS（なければ EOS）を 1 トークン置く。最初のトークンも予測の対象にする。
3. モデルに通して、各トークンの対数尤度を足す（NLL）。
4. スニペットごとの値を、シンタックスごとに合計する。

スニペットは 1 つずつ別々に測る（前のスニペットを文脈にしない）。

## 結果の読み方（Qwen2.5-Coder-1.5B-Instruct、全 40 スニペット）

| シンタックス | NLL | tok | char | PPL | bpc |
|---|---|---|---|---|---|
| pylike | 2823.8 | 754 | 1456 | 42.31 | 2.798 |
| jslike | 3120.3 | 748 | 1416 | 64.81 | 3.179 |
| lisplike | 3190.0 | 854 | 1846 | 41.90 | 2.493 |
| jalike | 4547.8 | 1052 | 1322 | 75.41 | 4.963 |

- NLL は pylike が最小。pylike が最小だったスニペットは 40 個中 34 個。
- lisplike は PPL と bpc が最良だが、括弧と定型語でトークン数・文字数が増えるため。総量（NLL）では pylike に負ける。
- jalike は文字数が最少なのに、トークン数は最多。日本語と全角記号が細かく分割される。

## 注意

- スニペットは `x` `y` `f` と数字だけの人工コード。実際のプログラムでの親和度とは限らない。
- Python に有利なのは、学習データに Python が多いためとも考えられる。
- 文脈なしの短いコードなので、PPL は先頭トークンの影響を受けやすい。傾向は NLL と bpc で見る。
- Instruct モデルを、チャットの形式にせず生のコードで採点している。
- 値はモデルの種類・バージョンで変わる。比べるときは同じモデルで測る。
