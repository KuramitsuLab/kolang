import copy
import io
import json
import unittest

from kolang import UnparseError, convert, load_syntax, parse, syntax_from_dict
from kolang import ast as K
from kolang.pyeval import run
from kolang.syntax import SYNTAX_DIR
from tests.test_cli import run as run_cli

PROG = (
    "x = add(1, 2)\n"
    "print(mul(x, 4), div(x, 2), sub(x, 1), len([1]))\n"
    ">>> sub(10, x)\n"
    "7\n"
)
JA = "xに(1, 2)における足し算の値を代入\n((x, 4)における掛け算の値, (x, 2)における割り算の値, (x, 1)における引き算の値, (【1】)における長さの値)における表示の値\n>>> sub(10, x)\n7\n"


def output(source, syntax):
    out = io.StringIO()
    interp = run(source, syntax, stdout=out)
    return out.getvalue(), [d.ok for d in interp.doctests]


class Rename(unittest.TestCase):
    def test_pylike_to_ja_and_back(self):
        self.assertEqual(convert(PROG, "pylike", "ja"), JA)
        self.assertEqual(convert(JA, "ja", "pylike"), PROG)

    def test_unchanged_names_stay(self):
        # 日本語名を持たない名前（自作の名前）は、そのまま
        self.assertEqual(convert("x = foo(y)\n", "pylike", "ja"), "xに(y)におけるfooの値を代入\n")
        self.assertEqual(convert("x = len(y)\n", "pylike", "ja"), "xに(y)における長さの値を代入\n")

    def test_the_converted_program_runs_the_same(self):
        self.assertEqual(output(PROG, "pylike"), output(convert(PROG, "pylike", "ja"), "ja"))
        for name in ("lisplike", "jslike", "ja:jslike(assign,block,funcapp)"):
            with self.subTest(name=name):
                self.assertEqual(output(convert(PROG, "pylike", name), name), output(PROG, "pylike"))

    def test_every_pair_keeps_the_program(self):
        names = ("pylike", "ja", "lisplike", "jslike", "ja:jslike(assign,block,funcapp)",
                 "pylike:ja(stdlib)")
        for a in names:
            text = convert(PROG, "pylike", a)
            for b in names:
                with self.subTest(a=a, b=b):
                    self.assertEqual(parse(convert(text, a, b), b), parse(convert(PROG, "pylike", b), b))
                    self.assertEqual(convert(convert(text, a, b), b, "pylike"), PROG)

    def test_name_references_are_renamed(self):
        self.assertEqual(convert("f = print\n", "pylike", "ja"), "fに_表示_を代入\n")

    def test_doctest_expression_is_renamed_but_not_the_answer(self):
        text = convert(">>> add(1, 2)\n\"add\"\n", "pylike", "ja")
        self.assertEqual(text, ">>> add(1, 2)\n\"add\"\n")

    def test_comments_survive(self):
        text = convert("# a\nprint(1) # b\n", "pylike", "ja")
        self.assertEqual(text, "※ a\n(1)における表示の値 ※ b\n")


class UserDefinitions(unittest.TestCase):
    def test_own_function_is_not_renamed(self):
        src = "def add(a, b):\n    return a\nx = add(1, 2)\nprint(x)\n"
        text = convert(src, "pylike", "ja")
        self.assertEqual(text, "関数 add(a, b)とは『\n    aを返す\n』\nxに(1, 2)におけるaddの値を代入\n(x)における表示の値\n")
        self.assertEqual(convert(text, "ja", "pylike"), src)

    def test_own_variable_or_param_is_not_renamed(self):
        self.assertEqual(convert("print = 1\nx = print\n", "pylike", "ja"), "printに1を代入\nxにprintを代入\n")
        self.assertEqual(convert("def f(print):\n    return print\n", "pylike", "ja"),
                         "関数 f(print)とは『\n    printを返す\n』\n")

    def test_collision_is_an_error(self):
        src = "_足し算_ = 1\nx = add(1, 2)\n"                 # add は ja で 足し算 になるが、自作の 足し算 がある
        with self.assertRaises(UnparseError) as cm:
            convert(src, "pylike", "ja")
        self.assertIn("足し算", str(cm.exception))

    def test_no_collision_if_the_name_is_unused(self):
        self.assertEqual(convert("_足し算_ = 1\n", "pylike", "ja"), "_足し算_に1を代入\n")

    def test_rename_false(self):
        self.assertEqual(convert("print(1)\n", "pylike", "ja", rename=False), "(1)におけるprintの値\n")


class Quoting(unittest.TestCase):
    def test_a_name_that_needs_quotes(self):
        data = json.loads((SYNTAX_DIR / "ja.json").read_text(encoding="utf-8"))
        data = copy.deepcopy(data)
        data["stdlib"] = {**data["stdlib"], "add": "たし算"}                      # 漢字を含むが、関数名の位置では引用なしで書ける
        syn = syntax_from_dict(data, "<test>")
        text = convert("x = add(1, 2)\n", "pylike", syn)
        self.assertEqual(text, "xに(1, 2)におけるたし算の値を代入\n")
        self.assertEqual(convert(text, syn, "pylike"), "x = add(1, 2)\n")


class Cli(unittest.TestCase):
    def test_default_renames(self):
        self.assertEqual(run_cli("conv", "-f", "pylike", "-t", "ja", stdin="print(1)\n")[:2], (0, "(1)における表示の値\n"))

    def test_no_rename(self):
        self.assertEqual(run_cli("conv", "-f", "pylike", "-t", "ja", "--no-rename", stdin="print(1)\n")[:2],
                         (0, "(1)におけるprintの値\n"))


class Show(unittest.TestCase):
    def test_examples_use_the_syntax_names(self):
        from kolang.examples import show
        out = show("ja")
        self.assertIn("(r)における表示の値", out)
        self.assertNotIn("におけるprintの値", out)


if __name__ == "__main__":
    unittest.main()
