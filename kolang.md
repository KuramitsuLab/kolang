kolang（こ言語）の仕様（修正版）

シンタックス可変言語
 block_begin, if_then など、小文字の名前（snake_case）は終端記号（区切りトークン）で、それぞれが正規表現。
 同じ名前は同じ正規表現を表す。意図しない衝突を避けるため、別の役割には別の名前を使う。
 空白・改行の扱いは、各トークンの正規表現の側で定める。

<block> ::=
  block_begin (<statement> block_sep)* block_end

<doctest> ::=
  ">>>" <expression> 改行 <JSON の値> 改行
  # doctest 風の例。`>>>` と答えの書き方は固定（シンタックスの JSON では変えない）。
  # 式は、どのシンタックスでも pylike の書き方で、関数呼び出し `f(x, y)` か変数（`x[0]` を含む）だけ。引数は pylike の式。
  # 標準関数の名前は pylike の名前（標準名）で書き、読むとそのシンタックスの名前になる（ja の add → 足し算）。
  # 答えは次の行に、JSON の値を 1 つ（生の文字列として読む）。
  # <statement> ではなく、<block> の文の並びの中に置ける（block_sep は付けても付けなくてもよい）

<statement> ::=
    assign_begin <expression> assign_op <expression> assign_end        # 代入 (X = 1)
  | append_begin <expression> append_sep <expression> append_end       # 追加する (X.append(1))
  | inc_begin <variable> inc_end                                       # 増やす (X += 1)
  | dec_begin <variable> dec_end                                       # 減らす (X -= 1)
  | <if>
  | <repeat>
  | <break>
  | <funcdef>
  | <return>
  | <funcapp>                                                          # 呼び出しだけの文 (print(x))。戻り値は捨てる

<if> ::=
  if_begin <condition> if_then <block> <else>? if_end # if（if_end は else のあと。Lisp の (if c ... (else ...)) の最後の ")" のため）

<condition> ::=
    ne_begin <expression> ne_sep <expression> ne_end # X != Y
  | lt_begin <expression> lt_sep <expression> lt_end # X < Y
  | gt_begin <expression> gt_sep <expression> gt_end # X > Y
  | le_begin <expression> le_sep <expression> le_end # X <= Y
  | ge_begin <expression> ge_sep <expression> ge_end # X >= Y
  | eq_begin <expression> eq_sep <expression> eq_end # X == Y

<else> ::=
  else_begin <block> else_end # そうでなければ

<repeat> ::=
  repeat_begin <expression> repeat_do <block> repeat_end # n回くり返す

<break> ::=
  break # 抜ける（単一トークン）

<funcdef> ::=
  def_begin <identifier> def_name_end params_begin (<identifier> param_sep)* params_end <block> def_end
  # def_begin 関数名の前, def_name_end 関数名の後, params_begin 引数リスト開始,
  # param_sep 各引数の後, params_end 引数リスト終了, def_end 定義の終わり

<return> ::=
  return_begin <expression> return_end

<expression> ::=
    <variable>
  | <string>   # 文字列
  | <number>   # 数字の文字
  | <boolean>
  | <none>
  | <list>
  | neg_begin <expression> neg_end   # 符号の反転 -X（省略可のトークン。neg_begin が無いシンタックスでは使えない）
  | <funcapp>

<boolean> ::=
    true    # True
  | false   # False

<none> ::=
  none # None

<list> ::=
  list_begin (<expression> list_sep)* list_end

<variable> ::=
    <identifier>
  | <variable> index_begin <expression> index_end              # 配列の添字 X[i]       （index: "postfix"、既定）
  | index_begin <variable> index_sep <expression> index_end    # 配列の添字 (get X i)  （index: "prefix"）
  # どちらの形を使うかは、シンタックス定義（JSON）の "index" で決める。

<identifier> ::=
    <letters>                              # 英数字_
  | quote_begin <characters> quote_end     # それ以外の特殊文字

<grouping> ::=                                   # 省略可。式 = 中の式そのまま
  grouping_begin <expression> grouping_end

<funcapp> ::=
  call_begin <identifier> call_name_end (<expression> arg_sep)* call_end
  # JSON の "call": "args_first" では引数が先: call_begin (<expression> arg_sep)* call_name_end <identifier> call_end

# 字句レベルの定義（正規表現）
<letters>    ::= [A-Za-z0-9_]+
<characters> ::= quote_end を含まない任意の文字列（quote_end にマッチするまでの最短一致）
<number>     ::= [0-9]+ ( . [0-9]+ )?     # 符号は含まない（-1 は neg_begin 1 neg_end）
<string>     ::= 区切り記号は言語定義（シンタックス）側で割り当てる任意の引用形式（既定: "..."）
