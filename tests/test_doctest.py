import io
import unittest

from kolang import ParseError, convert, parse
from kolang import ast as K
from kolang.pyeval import PyEval, run

SYNTAXES = ("pylike", "jalike", "lisplike", "jslike", "jalike:jslike(assign,block,funcapp)")

PY = (
    "def add(a, b):\n"
    "    return a\n"
    ">>> add(1, 2)\n"
    "1\n"
    "xs = [1, 'a']\n"
    ">>> xs\n"
    "[1, \"a\"]\n"
    ">>> add(None, 1)\n"
    "null\n"
    "if xs == xs:\n"
    "    >>> add(1, 2)\n"
    "    1\n"
    "    x = 1\n"
)


class Parsing(unittest.TestCase):
    def test_pylike(self):
        tree = parse(">>> f(1)\n[1, null, true, \"a\"]\nx = 1\n", "pylike")
        self.assertEqual(tree.stmts[0], K.Doctest(K.Call("f", (K.Num(1),)), [1, None, True, "a"]))
        self.assertEqual(tree.stmts[1], K.Assign(K.Var("x"), K.Num(1)))

    def test_answer_formatting_does_not_matter(self):
        self.assertEqual(parse(">>> x\n[1,2]\n", "pylike"), parse(">>> x\n[ 1 , 2 ]\n", "pylike"))

    def test_scalars(self):
        for text, value in [("3", 3), ("2.5", 2.5), ("true", True), ("null", None), ('"s"', "s"), ("{}", {})]:
            with self.subTest(text=text):
                self.assertEqual(parse(f">>> x\n{text}\n", "pylike").stmts[0].answer, value)

    def test_answer_is_not_a_comment_or_statement(self):
        tree = parse('>>> x\n"a # b"\n', "pylike")
        self.assertEqual(tree.stmts[0].answer, "a # b")

    def test_invalid_json(self):
        for src in (">>> x\nTrue\n", ">>> x\nx = 1\n", ">>> x\n"):
            with self.subTest(src=src):
                with self.assertRaises(ParseError):
                    parse(src, "pylike")

    def test_nested_and_indented_answer(self):
        tree = parse("def f():\n    >>> g()\n      5\n    return 1\n", "pylike")
        self.assertEqual(tree.stmts[0].body.stmts[0], K.Doctest(K.Call("g"), 5))
        self.assertEqual(tree.stmts[0].body.stmts[1], K.Return(K.Num(1)))

    def test_lisp_and_js_forms(self):
        # doctest の式は、シンタックスが何でも pylike の書き方
        self.assertEqual(parse(">>> f(1)\n2\n(set x 1)", "lisplike").stmts,
                         (K.Doctest(K.Call("f", (K.Num(1),)), 2), K.Assign(K.Var("x"), K.Num(1))))
        self.assertEqual(parse(">>> f(1)\n2\nx = 1;\n", "jslike").stmts,
                         (K.Doctest(K.Call("f", (K.Num(1),)), 2), K.Assign(K.Var("x"), K.Num(1))))

    def test_expression_is_pylike_in_every_syntax(self):
        for name in SYNTAXES:
            with self.subTest(name=name):
                tree = parse(">>> f(x, [1, 'a'], g(-2))\n1\n>>> xs[0]\n1\n", name)
                self.assertEqual(tree.stmts[0].expr, K.Call("f", (K.Var("x"), K.ListLit((K.Num(1), K.Str("a"))),
                                                                K.Call("g", (K.Neg(K.Num(2)),)))))
                self.assertEqual(tree.stmts[1].expr, K.Index(K.Var("xs"), K.Num(0)))

    def test_only_a_call_or_a_variable(self):
        for expr in ("1", "None", "True", "'a'", "[1, 2]", "-x", "f(1) g(2)", "(f 1)", "f(1", ""):
            for name in ("pylike", "jalike", "lisplike"):
                with self.subTest(expr=expr, name=name):
                    with self.assertRaises(ParseError):
                        parse(f">>> {expr}\n1\n", name)

    def test_not_writable(self):
        from kolang.unparser import UnparseError, unparse
        with self.assertRaises(UnparseError):
            unparse(K.Block((K.Doctest(K.Num(1), 1),)), "pylike")

    def test_comments_around(self):
        tree = parse("# a\n>>> x\n1\n# b\ny = 1 # c\n", "pylike")
        self.assertEqual(tree.stmts[0].comments.leading, ("a",))
        self.assertEqual(tree.stmts[1].comments.leading, ("b",))
        self.assertEqual(tree.stmts[1].comments.trailing, "c")


class Convert(unittest.TestCase):
    def test_every_syntax_round_trips(self):
        base = parse(PY, "pylike")
        for name in SYNTAXES:
            with self.subTest(name=name):
                text = convert(PY, "pylike", name)
                self.assertEqual(parse(text, name), base)
                self.assertEqual(convert(text, name, "pylike"), convert(PY, "pylike", "pylike"))

    def test_answer_is_always_json(self):
        text = convert(">>> f(1)\n[1,\"あ\",null,true]\n", "pylike", "jalike")
        self.assertEqual(text, ">>> f(1)\n[1, \"あ\", null, true]\n")       # 式は変わらない（pylike のまま）


class Evaluate(unittest.TestCase):
    def results(self, source, syntax="pylike"):
        interp = run(source, syntax, stdout=io.StringIO())
        return [d.ok for d in interp.doctests]

    def test_pass_and_fail(self):
        self.assertEqual(self.results(
            "xs = [1, 'a', None]\n>>> xs\n[1, \"a\", null]\n>>> xs\n[1, \"b\", null]\n"), [True, False])

    def test_strict_types(self):
        f = "def f(a):\n    return a\n"
        self.assertEqual(self.results(f + ">>> f(True)\n1\n>>> f(1)\ntrue\n>>> f(1)\n1.0\n>>> f(1.0)\n1.0\n>>> f([True])\n[1]\n"),
                         [False, False, False, True, False])

    def test_runs_in_order_and_keeps_going(self):
        out = io.StringIO()
        interp = run("x = 1\n>>> x\n2\nprint('after')\nx += 1\n>>> x\n2\n", stdout=out)
        self.assertEqual([d.ok for d in interp.doctests], [False, True])
        self.assertEqual(out.getvalue(), "after\n")

    def test_in_function_and_other_syntax(self):
        self.assertEqual(self.results("def f(a):\n    >>> a\n    5\n    return a\nf(5)\nf(6)\n"), [True, False])
        self.assertEqual(self.results("(set x (list 1 2))\n>>> x\n[1, 2]\n", "lisplike"), [True])

    def test_standard_names_work_in_every_syntax(self):
        # jalike では add は「足し算」。doctest は pylike の名前（標準名）で書ける
        for name in SYNTAXES:
            with self.subTest(name=name):
                self.assertEqual(self.results(convert("x = 1\n>>> add(x, 2)\n3\n>>> sub(x, 2)\n3\n", "pylike", name), name),
                                 [True, False])
        self.assertEqual(parse(">>> add(1, 2)\n3\n", "jalike").stmts[0].expr, K.Call("足し算", (K.Num(1), K.Num(2))))

    def test_own_function_hides_the_standard_name(self):
        text = convert("def add(a):\n    return a\n>>> add(5)\n5\n", "pylike", "jalike")
        self.assertEqual(self.results(text, "jalike"), [True])
        self.assertEqual(parse(text, "jalike").stmts[1].expr, K.Call("add", (K.Num(5),)))

    def test_override_matching(self):
        class Loose(PyEval):
            def answer_matches(self, value, answer):
                return value == answer

        interp = Loose(stdout=io.StringIO())
        interp.run(parse("x = True\n>>> x\n1\n", "pylike"))
        self.assertTrue(interp.doctests[0].ok)


if __name__ == "__main__":
    unittest.main()
