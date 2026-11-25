"""pyeval の結果が,同じソースを Python で実行したときと同じか確かめる。"""

import contextlib
import io
import unittest

from kolang import parse
from kolang.pyeval import PyEval, PySyntaxError, run


def by_python(source):
    out, ns = io.StringIO(), {}
    err = None
    try:
        code = compile(source, "<test>", "exec")
        with contextlib.redirect_stdout(out):
            exec(code, ns)
    except Exception as e:                      # noqa: BLE001
        err = (type(e).__name__, str(e))
    return out.getvalue(), err, ns


def by_kolang(source):
    out = io.StringIO()
    err = None
    interp = None
    try:
        interp = run(source, stdout=out)
    except Exception as e:                      # noqa: BLE001
        err = (type(e).__name__, str(e))
    return out.getvalue(), err, interp


def plain(values):
    return {k: v for k, v in values.items() if not callable(v) and not k.startswith("__")}


class Compat(unittest.TestCase):
    def same(self, source, message=True):
        py_out, py_err, ns = by_python(source)
        ko_out, ko_err, interp = by_kolang(source)
        self.assertEqual(ko_out, py_out)
        if message:
            self.assertEqual(ko_err, py_err)
        else:
            self.assertEqual(ko_err and ko_err[0], py_err and py_err[0])
        if interp is not None and py_err is None:
            self.assertEqual(plain(interp.globals.vars), plain(ns))
        return py_out, py_err

    def test_negation(self):
        out, _ = self.same("x = -3\ny = --x\nz = [-1, -2.5]\nprint(x, y, -z[0], -z[1], -x)\n"
                           "if -x > -1:\n    print(-x)\n")
        self.assertEqual(out, "-3 -3 1 2.5 3\n3\n")
        self.same('print(-"a")\n')              # TypeError も Python と同じ
        self.same("print(-None)\n")

    def test_arithmetic_free_basics(self):
        out, _ = self.same(
            "x = 1\n"
            "x += 1\n"
            "x -= 1\n"
            "x += 1\n"
            "y = 2.5\n"
            "y += 1\n"
            "print(x, y, None, True, False)\n"
            "if x < y:\n"
            "    print('lt')\n"
            "if x == 2:\n"
            "    print('eq')\n"
            "if x != 2:\n"
            "    print('ne')\n"
            "else:\n"
            "    print('not ne')\n"
            "if 'a' < 'b':\n"
            "    print('str')\n")
        self.assertEqual(out, "2 3.5 None True False\nlt\neq\nnot ne\nstr\n")

    def test_lists_and_index(self):
        self.same(
            "xs = [1, [2, 3], 'a']\n"
            "xs.append(4)\n"
            "xs[1][0] = 9\n"
            "xs[3] += 1\n"
            "xs[0] -= 1\n"
            "ys = xs\n"
            "ys.append(5)\n"
            "print(xs, len(xs), xs[1][1], xs[3])\n")

    def test_if_else_and_comparisons(self):
        self.same(
            "def sign(n):\n"
            "    if n < 5:\n"
            "        return 'small'\n"
            "    else:\n"
            "        if n == 5:\n"
            "            return 'five'\n"
            "        return 'big'\n"
            "print(sign(0), sign(5), sign(9))\n")

    def test_loops_and_break(self):
        self.same(
            "n = 0\n"
            "for _ in range(10):\n"
            "    n += 1\n"
            "    if n == 4:\n"
            "        break\n"
            "print(n)\n"
            "for _ in range(3):\n"
            "    for _ in range(2):\n"
            "        n += 1\n"
            "print(n)\n")


    def test_functions_recursion_closure(self):
        self.same(
            "def count(c):\n"
            "    c[0] += 1\n"
            "    if c[0] == 20:\n"
            "        return c[0]\n"
            "    return count(c)\n"
            "def make():\n"
            "    k = 10\n"
            "    def inner(a):\n"
            "        return [k, a]\n"
            "    return inner\n"
            "f = make()\n"
            "print(f(1), count([0]))\n"
            "def noret():\n"
            "    x = 1\n"
            "print(noret())\n")

    def test_globals_are_readable_from_functions(self):
        self.same(
            "g = [1]\n"
            "def f():\n"
            "    g.append(2)\n"
            "    return g[0]\n"
            "print(f(), g)\n")

    def test_assignment_in_function_is_local(self):
        self.same(
            "x = 1\n"
            "def f():\n"
            "    x = 2\n"
            "    return x\n"
            "print(f(), x)\n")

    def test_unbound_local(self):
        _, err = self.same("x = 1\ndef f():\n    x += 1\n    return x\nprint(f())\n")
        self.assertEqual(err[0], "UnboundLocalError")
        _, err = self.same("def f():\n    y = x\n    x = 1\n    return y\nf()\n")
        self.assertEqual(err[0], "UnboundLocalError")

    def test_errors_match_python(self):
        for src, kind in [
            ("print(x)\n", "NameError"),
            ("xs = [1]\nprint(xs[3])\n", "IndexError"),
            ("xs = [1]\nxs[2] = 1\n", "IndexError"),
            ("x = 1\nx.append(2)\n", "AttributeError"),
            ("x = 'a' + 1\n", None),
            ("for _ in range(2.5):\n    pass1 = 1\n", "TypeError"),
            ("x = 1\nif x < 'a':\n    x = 2\n", "TypeError"),
            ("x = 1\nx()\n", "TypeError"),
            ("def f(a, b):\n    return a\nf(1)\n", "TypeError"),
            ("def f(a):\n    return a\nf(1, 2)\n", "TypeError"),
            ("def f():\n    return 1\nf(1)\n", "TypeError"),
            ("def f(a, b, c):\n    return a\nf()\n", "TypeError"),
        ]:
            with self.subTest(src=src):
                if kind is None:           # 'a' + 1 は構文として読めない（式の演算子がない）
                    continue
                _, err = self.same(src)
                self.assertEqual(err[0], kind)

    def test_recursion_error(self):
        self.same("def f(n):\n    return f(n)\nf(1)\n", message=False)
        _, err = self.same("def f(n):\n    if n == 0:\n        return 0\n    return f(n)\nf(1)\n",
                           message=False)
        self.assertEqual(err[0], "RecursionError")

    def test_deep_but_legal_recursion(self):
        # 深さ 900 は Python でも通る
        out, err = self.same(
            "def f(c):\n"
            "    c[0] += 1\n"
            "    if c[0] == 900:\n"
            "        return c[0]\n"
            "    return f(c)\n"
            "print(f([0]))\n")
        self.assertEqual((out, err), ("900\n", None))

    def test_builtins(self):
        self.same("xs = [3, 1, 2]\nprint(sorted(xs), max(xs), min(xs), sum(xs), abs(1), str(5), int('7'))\n")

    def test_shadowing_a_builtin(self):
        self.same("len = [1]\nprint(len)\n")

    def test_string_and_none(self):
        self.same("s = 'a\\nb'\nprint(s, len(s))\nif None == None:\n    print('none')\n")


class Static(unittest.TestCase):
    def test_break_outside_loop(self):
        with self.assertRaises(PySyntaxError):
            run("break\n")
        with self.assertRaises(PySyntaxError):
            run("for _ in range(1):\n    def f():\n        break\n")

    def test_return_outside_function(self):
        with self.assertRaises(PySyntaxError):
            run("return 1\n")

    def test_nothing_runs_before_the_check(self):
        out = io.StringIO()
        with self.assertRaises(PySyntaxError):
            run("print(1)\nbreak\n", stdout=out)
        self.assertEqual(out.getvalue(), "")


class Adjustable(unittest.TestCase):
    def test_override_a_semantic_hook(self):
        class Lenient(PyEval):
            def lookup(self, name):                 # 未定義の変数は None にする
                try:
                    return super().lookup(name)
                except NameError:
                    return None

        out = io.StringIO()
        interp = Lenient(stdout=out)
        interp.run(parse("print(zzz)\n", "pylike"))
        self.assertEqual(out.getvalue(), "None\n")

    def test_other_syntax(self):
        out = io.StringIO()
        run("xs = [1,2];\n3をxsに追加;\nprint(xs);\n", "jalike:jslike(assign,block,funcapp,stdlib)", stdout=out)
        self.assertEqual(out.getvalue(), "[1, 2, 3]\n")


if __name__ == "__main__":
    unittest.main()
