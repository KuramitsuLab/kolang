import contextlib
import copy
import io
import json
import os
import tempfile
import unittest

from kolang import load_syntax, syntax_from_dict
from kolang.cli import main
from kolang.pyeval import run
from kolang.unparser import convert
from kolang.syntax import SYNTAX_DIR

PYLIKE = json.loads((SYNTAX_DIR / "pylike.json").read_text(encoding="utf-8"))
JA = json.loads((SYNTAX_DIR / "ja.json").read_text(encoding="utf-8"))


def with_stdlib(base, stdlib):
    data = copy.deepcopy(base)
    data["stdlib"] = dict(stdlib)
    return syntax_from_dict(data, "<test>")


def output(source, syntax="pylike"):
    out = io.StringIO()
    run(source, syntax, stdout=out)
    return out.getvalue()


class Arithmetic(unittest.TestCase):
    def test_four_operations(self):
        self.assertEqual(output("print(add(1, 2), sub(1, 2), mul(3, 4), div(1, 2), div(6, 3))\n"),
                         "3 -1 12 0.5 2.0\n")

    def test_conversions_are_pythons(self):
        src = ('print(int("7"), int(2.9), int(True), float("1.5"), float(2), str(12), str(None), '
               'str([1, "a"]), bool(0), bool([]), bool("x"))\n')
        self.assertEqual(output(src), "7 2 1 1.5 2.0 12 None [1, 'a'] False False True\n")
        self.assertEqual(output('print(add("n=", str(5)))\n'), "n=5\n")
        for bad, py in [('int("x")', 'int("x")'), ('float("a")', 'float("a")'), ('int(None)', 'int(None)')]:
            with self.subTest(src=bad):
                try:
                    eval(py)
                except Exception as e:                   # noqa: BLE001
                    expected = (type(e), str(e))
                with self.assertRaises(expected[0]) as cm:
                    run(f"x = {bad}\n")
                self.assertEqual(str(cm.exception), expected[1])

    def test_conversions_in_japanese(self):
        self.assertEqual(output("((\"n=\",((\"5\")における整数化の値)における文字列化の値)における足し算の値,(0)におけるブール化の値,(2)における小数化の値)における表示の値\n", "ja"),
                         "n=5 False 2.0\n")

    def test_mod_and_pow(self):
        self.assertEqual(output("print(mod(7, 3), mod(5, 5), mod(7.5, 2), pow(2, 10), pow(2, 0.5))\n"),
                         "1 0 1.5 1024 1.4142135623730951\n")
        self.assertEqual(output("print(mod('a%s', 'b'))\n"), "ab\n")        # Python の % と同じ（文字列の書式）

    def test_mod_and_pow_errors_are_pythons(self):
        for src, py in [("mod(1, 0)", "1 % 0"), ("pow(0, sub(0, 1))", "0 ** -1"), ("mod(1, 'a')", "1 % 'a'")]:
            with self.subTest(src=src):
                try:
                    eval(py)
                except Exception as e:                   # noqa: BLE001
                    expected = (type(e), str(e))
                with self.assertRaises(expected[0]) as cm:
                    run(f"x = {src}\n")
                self.assertEqual(str(cm.exception), expected[1])

    def test_same_as_python_operators(self):
        self.assertEqual(output("print(add('a', 'b'), add([1], [2]), mul('ab', 2), add(0.5, 1))\n"),
                         "ab [1, 2] abab 1.5\n")

    def test_errors_are_pythons(self):
        for src, py in [("div(1, 0)", "1 / 0"), ("add(1, 'a')", "1 + 'a'"), ("sub('a', 1)", "'a' - 1")]:
            with self.subTest(src=src):
                try:
                    eval(py)
                except Exception as e:                   # noqa: BLE001
                    expected = (type(e), str(e))
                with self.assertRaises(expected[0]) as cm:
                    run(f"x = {src}\n")
                self.assertEqual(str(cm.exception), expected[1])

    def test_nested_calls(self):
        self.assertEqual(output("print(mul(add(1, 2), sub(5, 1)))\n"), "12\n")

    def test_user_definition_shadows_stdlib(self):
        self.assertEqual(output("def add(a, b):\n    return 'mine'\nprint(add(1, 2))\n"), "mine\n")


class Rename(unittest.TestCase):
    def test_default_names(self):
        syn = load_syntax("pylike")
        self.assertEqual(syn.function_names["print"], "print")
        self.assertEqual(syn.function_names["len"], "len")       # JSON に書いていないものも、標準名のまま

    def test_shipped_syntaxes(self):
        ja = load_syntax("ja").function_names
        self.assertEqual([ja[n] for n in ("print", "add", "sub", "mul", "div", "mod", "pow")],
                         ["表示", "足し算", "引き算", "掛け算", "割り算", "余り", "べき乗"])
        self.assertEqual([ja[n] for n in ("int", "str", "float", "bool")],
                         ["整数化", "文字列化", "小数化", "ブール化"])
        for name in ("pylike", "jslike", "lisplike"):
            self.assertEqual(load_syntax(name).function_names["print"], "print")

    def test_japanese_program(self):
        src = ("xに(1,2)における足し算の値を代入\n"
               "((x,(8,2)における割り算の値)における掛け算の値,(x,1)における引き算の値)における表示の値\n")
        self.assertEqual(output(src, "ja"), "12.0 2\n")

    def test_plain_ja_cascade_keeps_japanese_names(self):
        # ベースの ja の名前を引き継ぐ。jslike の名前に変えたいときは stdlib グループも取り込む。
        self.assertEqual(output("表示(1);\n", "ja:jslike(assign,block,funcapp)"), "1\n")
        self.assertEqual(output("print(1);\n", "ja:jslike(assign,block,funcapp,stdlib)"), "1\n")

    def test_rename(self):
        syn = with_stdlib(PYLIKE, {"print": "out", "add": "plus"})
        self.assertEqual(output("out(plus(1, 2))\n", syn), "3\n")
        with self.assertRaises(NameError):             # 元の名前は使えない
            run("print(1)\n", syn)
        self.assertEqual(output("out(sub(3, 1))\n", syn), "2\n")    # 変えていないものはそのまま

    def test_rename_in_japanese_syntax(self):
        # 表示 も たし算 も漢字を含むが、関数名の位置では引用なしでも書ける（「」で囲んでも読める）。
        syn = with_stdlib(JA, {"print": "表示", "add": "たし算"})
        self.assertEqual(output("((1,2)における_たし算_の値)における表示の値\n", syn), "3\n")
        self.assertEqual(output("(【1,2】)における表示の値\n", syn), "[1, 2]\n")

    def test_cascade_refers_to_stdlib_names(self):
        # カスケードでも、合成後の stdlib の名前（漢字）を、関数名として引用なしで読み書きできる。
        for spec, src in [
            ("ja", "((1,2)における足し算の値)における表示の値\n"),
            ("ja:jslike(assign,block,funcapp)", "表示(足し算(1, 2));\n"),           # stdlib はベース（ja）のまま
            ("jslike:ja(stdlib)", "表示(足し算(1, 2));\n"),                      # 名前だけ ja、呼び出しは jslike
            ("jslike:ja(funcapp,stdlib)", "((1,2)における足し算の値)における表示の値;\n"),
        ]:
            with self.subTest(spec=spec):
                self.assertEqual(output(src, spec), "3\n")
                self.assertEqual(convert("print(add(1, 2))\n", "pylike", spec).replace(" ", ""), src.replace(" ", ""))

    def test_cascade_without_stdlib_group_keeps_base_names(self):
        # stdlib グループを取り込まなければ、jslike の標準名（print）は使えず、ベースの名前になる。
        with self.assertRaises(NameError):
            run("print(1);\n", load_syntax("ja:jslike(assign,block,funcapp)"))

    def test_stdlib_name_can_be_a_function_name_without_quotes(self):
        # stdlib で定義した名前は、漢字でも、関数名の位置では引用なしで書ける（読み書きとも）。
        syn = with_stdlib(JA, {"print": "表示", "add": "足し算"})
        self.assertEqual(output("((1,2)における足し算の値)における表示の値\n", syn), "3\n")
        self.assertEqual(output("(1)における_表示_の値\n", syn), "1\n")     # 引用も読める
        self.assertEqual(convert("print(add(1, 2))\n", "pylike", syn),
                         "((1, 2)における足し算の値)における表示の値\n")

    def test_function_names_has_every_stdlib_function(self):
        names = load_syntax("pylike").function_names
        for std in ("print", "add", "sub", "mul", "div", "len", "range"):
            self.assertIn(std, names)

    def test_user_function_with_a_renamed_name(self):
        syn = with_stdlib(PYLIKE, {"print": "show"})
        self.assertEqual(output("def print(x):\n    return x\nshow(print(1))\n", syn), "1\n")


class Validation(unittest.TestCase):
    def bad(self, stdlib):
        with self.assertRaises(ValueError) as cm:
            with_stdlib(PYLIKE, stdlib)
        return str(cm.exception)

    def test_unknown_function(self):
        self.assertIn("unknown function", self.bad({"printt": "x"}))

    def test_name_must_be_writable(self):
        self.assertIn("cannot be written", self.bad({"print": "a b_c"}))     # 引用もできない名前
        self.assertIn("non-empty", self.bad({"print": ""}))

    def test_quoted_names_are_allowed(self):
        syn = with_stdlib(PYLIKE, {"print": "if", "add": "my fn"})          # 予約語や空白入りは、_..._ で呼ぶ
        self.assertEqual(output("_if_(_my fn_(1, 2))\n", syn), "3\n")

    def test_duplicates(self):
        self.assertIn("duplicate", self.bad({"print": "len"}))
        self.assertIn("duplicate", self.bad({"add": "x", "sub": "x"}))


class Cascade(unittest.TestCase):
    def test_stdlib_group(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "over.json")
            data = copy.deepcopy(PYLIKE)
            data["stdlib"] = {"print": "out"}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            syn = load_syntax(f"pylike:{path}(stdlib)")
            self.assertEqual(syn.function_names["print"], "out")
            self.assertEqual(load_syntax(f"{path}:pylike(comment)").function_names["print"], "out")
            self.assertEqual(load_syntax(f"{path}:pylike(stdlib)").function_names["print"], "print")


class Cli(unittest.TestCase):
    def test_run_uses_the_renamed_function(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mine.json")
            data = copy.deepcopy(PYLIKE)
            data["stdlib"] = {"print": "out", "add": "plus"}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            src = os.path.join(d, "p.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("out(plus(1, 2))\n")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["run", src, "-f", path])
            self.assertEqual((code, out.getvalue(), err.getvalue()), (0, "3\n", ""))


class LibFunctionsAreNotInStdlib(unittest.TestCase):
    """join / split / sort / slice などは lib/ に kolang で定義している（tests/test_lib.py）。
    リストを縮める pop / remove / clear は、使われないので標準ライブラリに持たない。"""

    def test_not_in_stdlib(self):
        from kolang.stdlib import NAMES
        for name in ("join", "split", "slice", "sort", "any", "all", "lower", "input", "repr", "reversed", "pop", "remove", "clear"):
            self.assertNotIn(name, NAMES)


if __name__ == "__main__":
    unittest.main()
