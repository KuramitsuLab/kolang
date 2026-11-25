import unittest

from kolang import ast as K
from kolang import convert, load_syntax, parse, unparse
from kolang.unparser import UnparseError

SRC = "x = -1\ny = --z[2]\nw = [-1.5, -f(-x)]\nif -x < -1:\n    x += 1\n"
TREE = K.Block((
    K.Assign(K.Var("x"), K.Neg(K.Num(1))),
    K.Assign(K.Var("y"), K.Neg(K.Neg(K.Index(K.Var("z"), K.Num(2))))),
    K.Assign(K.Var("w"), K.ListLit((K.Neg(K.Num(1.5)), K.Neg(K.Call("f", (K.Neg(K.Var("x")),)))))),
    K.If(K.Compare("<", K.Neg(K.Var("x")), K.Neg(K.Num(1))), K.Block((K.Inc(K.Var("x")),))),
))


class Negation(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse(SRC, "pylike"), TREE)

    def test_number_stays_non_negative(self):
        (stmt,) = parse("x = -1\n", "pylike").stmts
        self.assertEqual(stmt.value, K.Neg(K.Num(1)))      # Num(-1) ではない

    def test_all_syntaxes(self):
        for name in ("pylike", "jalike", "jslike", "lisplike"):
            with self.subTest(syntax=name):
                self.assertEqual(parse(unparse(TREE, name), name), TREE)

    def test_text(self):
        self.assertEqual(convert("x = -y\n", "pylike", "lisplike"), "(set x (neg y))\n")
        self.assertEqual(convert("(set x (neg (neg 1)))", "lisplike", "jalike"), "--1をxに代入\n")
        self.assertEqual(convert("x = -1\n", "pylike", "jslike"), "x = -1;\n")

    def test_negative_num_literal_is_not_writable(self):
        with self.assertRaises(UnparseError):
            unparse(K.Block((K.Assign(K.Var("x"), K.Num(-1)),)), "pylike")

    def test_neg_is_optional_in_a_syntax(self):
        data = load_syntax("pylike")
        tokens = {k: v for k, v in data.tokens.items() if not k.startswith("neg_")}
        from dataclasses import replace
        syn = replace(data, tokens=tokens)
        with self.assertRaises(UnparseError):
            unparse(TREE, syn)

    def test_lisp_neg_is_reserved(self):
        self.assertIn("neg", load_syntax("lisplike").reserved)


if __name__ == "__main__":
    unittest.main()
