import unittest

from kolang import ParseError, parse
from kolang import ast as K


def jalike(src):
    return parse(src, "jalike")


def py(src):
    return parse(src, "pylike")


x, y = K.Var("x"), K.Var("y")


class SameAstAsPylike(unittest.TestCase):
    """同じ意味のプログラムは,シンタックスが違っても同じ AST になる。"""

    def check(self, ja_src, py_src):
        self.assertEqual(jalike(ja_src), py(py_src))

    def test_program(self):
        self.check(
            "※ 関数と繰り返しと分岐\n"
            "関数 add(a,b)とは『\n"
            "    aを返す\n"
            "』\n"
            "0をsに代入\n"
            "3回くり返す『\n"
            "    sを増やす\n"
            "    sを減らす\n"
            "』\n"
            "もしsが3と等しいなら『\n"
            "    \"ok\"をxsに追加\n"
            "』そうでなければ『\n"
            "    [1,2]をsに代入\n"
            "    抜ける\n"
            "』\n",
            "# 関数と繰り返しと分岐\n"
            "def add(a, b):\n"
            "    return a\n"
            "s = 0\n"
            "for _ in range(3):\n"
            "    s += 1\n"
            "    s -= 1\n"
            "if s == 3:\n"
            "    xs.append(\"ok\")\n"
            "else:\n"
            "    s = [1, 2]\n"
            "    break\n")

    def test_all_comparisons(self):
        for ja_end, op in [("と等しくない", "!="), ("より小さい", "<"), ("より大きい", ">"),
                           ("以下", "<="), ("以上", ">="), ("と等しい", "==")]:
            with self.subTest(op=op):
                self.check(f"もしxがy{ja_end}なら『抜ける』", f"if x {op} y:\n    break")

    def test_expressions(self):
        self.check("[真,偽,無,\"a # b\"]をxに代入",
                   'x = [True, False, None, "a # b"]')
        self.check("(1,(y)におけるgの値)におけるfの値をrに代入", "r = f(1, g(y))")
        self.check("2.5をxの(0)番目の(y)番目に代入", "x[0][y] = 2.5")
        self.check("[]をxに代入\n()におけるfの値をyに代入", "x = []\ny = f()")

    def test_call_is_args_first(self):
        from kolang.unparser import convert
        self.assertEqual(convert("print(add(1, 2))\n", "pylike", "jalike"),
                         "((1, 2)における足し算の値)における表示の値\n")
        self.assertEqual(convert("((1,2)における足し算の値)における表示の値\n", "jalike", "lisplike"),
                         "(print (add 1 2))\n")

    def test_grouping(self):
        from kolang.unparser import convert
        # 添字の括弧は index_begin / index_end が持つ。式の括弧は AST に残らない
        self.assertEqual(convert("a = x[len(x)]\n", "pylike", "jalike"), "xの((x)における長さの値)番目をaに代入\n")
        self.check("xの((x)におけるfの値)番目をaに代入", "a = x[f(x)]")
        self.check("xの(0)番目をaに代入", "a = x[0]")
        self.check("(z)をyに代入", "y = z")

    def test_nested_blocks(self):
        self.check(
            "関数 f(n)とは『\n"
            "    n回くり返す『\n"
            "        もしnが1以下なら『nを返す』\n"
            "        そうでなければ『nを減らす』\n"
            "    』\n"
            "    無を返す\n"
            "』\n"
            "1をfに代入\n",
            "def f(n):\n"
            "    for _ in range(n):\n"
            "        if n <= 1:\n"
            "            return n\n"
            "        else:\n"
            "            n -= 1\n"
            "    return None\n"
            "f = 1\n")


class JapaneseSpecifics(unittest.TestCase):
    def test_no_spaces_needed(self):
        self.assertEqual(jalike("1をxに代入").stmts, (K.Assign(x, K.Num(1)),))

    def test_spaces_and_fullwidth_spaces_are_ok(self):
        self.assertEqual(jalike("1　を  x に代入").stmts, (K.Assign(x, K.Num(1)),))

    def test_katakana_and_quoted_names(self):
        # カタカナは名前に使えないので、引用する（stdlib の名前だけは関数名の位置で引用なしで書ける）
        self.assertEqual(jalike("_カウンタ_を増やす").stmts, (K.Inc(K.Var("カウンタ")),))
        with self.assertRaises(ParseError):
            jalike("カウンタを増やす")
        self.assertEqual(jalike("1を_合計 金額_に代入").stmts,
                         (K.Assign(K.Var("合計 金額"), K.Num(1)),))

    def test_comment(self):
        self.assertEqual(jalike("1をxに代入※ 後ろにコメント\n※ 行全体\n").stmts,
                         (K.Assign(x, K.Num(1)),))

    def test_word_chars_need_space(self):
        with self.assertRaises(ParseError):
            jalike("1aをxに代入")

    def test_error_names_the_missing_token(self):
        with self.assertRaises(ParseError) as cm:
            jalike("もしxがy以下『抜ける』")
        self.assertIn("if_then", cm.exception.message)
        self.assertEqual(cm.exception.line, 1)


if __name__ == "__main__":
    unittest.main()
