import unittest

from kolang import ParseError, parse
from kolang import ast as K


def ja(src):
    return parse(src, "ja")


def py(src):
    return parse(src, "pylike")


x, y = K.Var("x"), K.Var("y")


class SameAstAsPylike(unittest.TestCase):
    """同じ意味のプログラムは,シンタックスが違っても同じ AST になる。"""

    def check(self, ja_src, py_src):
        self.assertEqual(ja(ja_src), py(py_src))

    def test_program(self):
        self.check(
            "※ 関数と繰り返しと分岐\n"
            "関数 add(a,b)とは『\n"
            "    aを返す\n"
            "』\n"
            "sに0を代入\n"
            "3回くり返す『\n"
            "    sを増やす\n"
            "    sを減らす\n"
            "』\n"
            "もしsが3と等しいなら『\n"
            "    xsに\"ok\"を追加\n"
            "』そうでなければ『\n"
            "    sに【1,2】を代入\n"
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
        self.check("xに【真,偽,無,\"a # b\"】を代入",
                   'x = [True, False, None, "a # b"]')
        self.check("rに(1,(y)におけるgの値)におけるfの値を代入", "r = f(1, g(y))")
        self.check("xの(0)番目の(y)番目に2.5を代入", "x[0][y] = 2.5")
        self.check("xに【】を代入\nyに()におけるfの値を代入", "x = []\ny = f()")

    def test_call_is_args_first(self):
        from kolang.unparser import convert
        self.assertEqual(convert("print(add(1, 2))\n", "pylike", "ja"),
                         "((1, 2)における足し算の値)における表示の値\n")
        self.assertEqual(convert("((1,2)における足し算の値)における表示の値\n", "ja", "lisplike"),
                         "(print (add 1 2))\n")

    def test_grouping(self):
        from kolang.unparser import convert
        # 添字の括弧は index_begin / index_end が持つ。式の括弧は AST に残らない
        self.assertEqual(convert("a = x[len(x)]\n", "pylike", "ja"), "aにxの((x)におけるlenの値)番目を代入\n")
        self.check("aにxの((x)におけるlenの値)番目を代入", "a = x[len(x)]")
        self.check("aにxの(0)番目を代入", "a = x[0]")
        self.check("yに(z)を代入", "y = z")

    def test_nested_blocks(self):
        self.check(
            "関数 f(n)とは『\n"
            "    n回くり返す『\n"
            "        もしnが1以下なら『nを返す』\n"
            "        そうでなければ『nを減らす』\n"
            "    』\n"
            "    無を返す\n"
            "』\n"
            "fに1を代入\n",
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
        self.assertEqual(ja("xに1を代入").stmts, (K.Assign(x, K.Num(1)),))

    def test_spaces_and_fullwidth_spaces_are_ok(self):
        self.assertEqual(ja("x　に  1 を代入").stmts, (K.Assign(x, K.Num(1)),))

    def test_katakana_and_quoted_names(self):
        # カタカナは名前に使えないので、引用する（stdlib の名前だけは関数名の位置で引用なしで書ける）
        self.assertEqual(ja("_カウンタ_を増やす").stmts, (K.Inc(K.Var("カウンタ")),))
        with self.assertRaises(ParseError):
            ja("カウンタを増やす")
        self.assertEqual(ja("_合計 金額_に1を代入").stmts,
                         (K.Assign(K.Var("合計 金額"), K.Num(1)),))

    def test_comment(self):
        self.assertEqual(ja("xに1を代入※ 後ろにコメント\n※ 行全体\n").stmts,
                         (K.Assign(x, K.Num(1)),))

    def test_word_chars_need_space(self):
        with self.assertRaises(ParseError):
            ja("xに1aを代入")

    def test_error_names_the_missing_token(self):
        with self.assertRaises(ParseError) as cm:
            ja("もしxがy以下『抜ける』")
        self.assertIn("if_then", cm.exception.message)
        self.assertEqual(cm.exception.line, 1)


if __name__ == "__main__":
    unittest.main()
