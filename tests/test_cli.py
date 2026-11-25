import contextlib
import io
import os
import sys
import tempfile
import unittest

from kolang.cli import main


def run(*argv, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(list(argv))
            except SystemExit as e:          # argparse の終了
                code = e.code
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


class Show(unittest.TestCase):
    def test_show_lisplike(self):
        code, out, _ = run("--show", "lisplike")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("lisplike\n"))
        for line in ("(set x 1)", "(set y (get xs 0))", "(append xs 4)",
                     "(if (< x 3) (inc x) (else (dec x)))", "; コメント", "(def add (a b) (return a))"):
            self.assertIn(line, out)
        self.assertIn("予約語: append break dec def else false get if inc list neg nil repeat return set true", out)

    def test_show_ja_and_pylike(self):
        _, out, _ = run("--show", "ja")
        self.assertIn("  xに1を代入", out)
        self.assertIn("  ※ コメント", out)
        _, out, _ = run("--show", "pylike")
        self.assertIn("  x = 1", out)
        self.assertIn("  for _ in range(3):\n      x += 1", out)

    def test_every_builtin_syntax_can_show_every_example(self):
        for name in ("pylike", "ja", "lisplike", "jslike"):
            with self.subTest(name=name):
                code, out, _ = run("--show", name)
                self.assertEqual(code, 0)
                self.assertNotIn("書けません", out)

    def test_show_snippet(self):
        from kolang.snippet import SNIPPETS
        code, out, _ = run("show_snippet", "ja")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("ja\n"))
        for name in SNIPPETS:
            self.assertIn(f"■ {name}\n", out)
        self.assertNotIn("書けません", out)

    def test_show_snippet_selected_and_errors(self):
        code, out, _ = run("show_snippet", "lisplike", "assign", "index")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("■"), 2)
        self.assertIn("(set x 1)", out)
        code, _, err = run("show_snippet", "ja", "nope")
        self.assertEqual(code, 1)
        self.assertIn("nope", err)
        code, out, _ = run("show_snippet", "ja", "--list")
        self.assertEqual(code, 0)
        self.assertIn("assign\n", out)

    def test_show_ebnf(self):
        code, out, _ = run("show_ebnf", "ja")
        self.assertEqual(code, 0)
        for line in ('"『" (<doctest> | <statement>)* "』"',          # ブロックは 『 』（空の block_sep は書かない）
                     '<variable> "に" <expression> "を代入"',
                     '"(" (<expression> ",")* ")における" <identifier> "の値"',   # call: args_first
                     '<variable> "の(" <expression> ")番目"',
                     '"-" <expression>', '<grouping>'):
            self.assertIn(line, out)
        _, out, _ = run("show_ebnf", "lisplike")
        self.assertIn('"(" <identifier> <expression>* ")"', out)
        self.assertNotIn("<grouping>", out)                         # 括弧のないシンタックスは出さない
        _, out, _ = run("show_ebnf", "pylike")
        self.assertIn("INDENT (<doctest> | <statement> NEWLINE)* DEDENT", out)
        for name in ("pylike", "ja", "lisplike", "jslike", "ja:jslike(block)"):
            self.assertEqual(run("show_ebnf", name)[0], 0)
        self.assertEqual(run("show_ebnf", "nope")[0], 1)

    def test_show_unknown(self):
        code, out, err = run("--show", "nope")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("nope", err)

    def test_list(self):
        code, out, _ = run("--list")
        self.assertEqual(code, 0)
        for name in ("pylike", "ja", "lisplike", "jslike"):
            self.assertIn(name, out)


class Run(unittest.TestCase):
    def test_run_stdin(self):
        code, out, err = run("run", stdin="xs = [1]\nxs.append(2)\nprint(xs)\n")
        self.assertEqual((code, out, err), (0, "[1, 2]\n", ""))

    def test_run_file_and_syntax(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("(set x 1)\n(print x)\n")
            self.assertEqual(run("run", path, "-f", "lisplike")[:2], (0, "1\n"))
            code, out, _ = run("run", "-f", "ja:jslike(assign,block,funcapp,stdlib)",
                              stdin="x = 【1】;\nprint(x);\n")
            self.assertEqual((code, out), (0, "[1]\n"))

    def test_runtime_error(self):
        code, out, err = run("run", stdin="print(1)\nprint(zz)\n")
        self.assertEqual((code, out), (1, "1\n"))
        self.assertEqual(err, "NameError: name 'zz' is not defined\n")

    def test_static_error_runs_nothing(self):
        code, out, err = run("run", stdin="print(1)\nbreak\n")
        self.assertEqual((code, out, err), (1, "", "SyntaxError: 'break' outside loop\n"))

    def test_parse_error(self):
        code, out, err = run("run", stdin="x = \n")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("kolang: "))

    def test_doctest(self):
        code, out, err = run("run", stdin="x = 1\n>>> x\n1\n>>> x\n2\n")
        self.assertEqual(code, 1)
        self.assertIn("doctest #2 failed: expected 2, got 1", err)
        self.assertIn("doctest: 1 passed, 1 failed", err)
        self.assertEqual(run("run", stdin="x = 1\n>>> x\n1\n")[:3], (0, "", "doctest: 1 passed, 0 failed\n"))

    def test_unknown_syntax_and_missing_file(self):
        self.assertEqual(run("run", "-f", "nope", stdin="")[0], 1)
        self.assertEqual(run("run", "/no/such/file")[0], 1)

    def test_run_help(self):
        code, out, _ = run("run", "-h")
        self.assertEqual(code, 0)
        self.assertIn("kolang run", out)


class PassAt1(unittest.TestCase):
    def make(self, d, name, code, doctest=None):
        path = os.path.join(d, name + ".ko")
        with open(path, "w", encoding="utf-8") as f:
            f.write("```pylike\n" + code + "```\n")
        if doctest is not None:
            with open(os.path.join(d, name + ".doctest"), "w", encoding="utf-8") as f:
                f.write(doctest)
        return path

    def test_cov(self):
        code = ("def add(a, b):\n    return a\n"                         # 自作の add は標準として数えない
                "if 1 == 2:\n    print(add(1, 2))\nelse:\n    print(mul(2, 3))\n"
                "xs = []\nxs.append(len(xs))\nprint(1)\n>>> len(xs)\n1\n")
        with tempfile.TemporaryDirectory() as d:
            a = self.make(d, "a", code)
            rc, out, _ = run("cov", a)
            self.assertEqual(rc, 0)
            row = {l.split()[0]: l.split()[1] for l in out.splitlines() if len(l.split()) >= 2 and l.split()[1].isdigit()}
            self.assertEqual((row["Compare(==)"], row["Compare(<)"], row["If"], row["Else"]), ("1", "0", "1", "1"))
            self.assertEqual((row["CallStmt"], row["Call"], row["Append"]), ("3", "3", "1"))   # CallStmt 内の Call は二重に数えない
            self.assertEqual((row["print"], row["mul"], row["len"], row["add"]), ("3", "1", "1", "0"))
            self.assertIn("← 未使用", out)
            self.assertEqual(run("cov", a, a)[1].count("Compare(==)"), 1)

    def test_pass_at_1(self):
        body = "def f(x):\n    return add(x, 1)\nprint(f(1))\n"
        with tempfile.TemporaryDirectory() as d:
            a = self.make(d, "a", body, ">>> f(1)\n2\n")                  # 合格（print の出力は出ない）
            b = self.make(d, "b", body, ">>> f(1)\n3\n")                  # doctest の不一致
            c = self.make(d, "c", body)                                    # doctest がない
            e = self.make(d, "e", "print(zz)\n", ">>> zz\n1\n")           # 実行時エラー
            code, out, _ = run("pass@1", a, b, c, e)
            self.assertEqual(code, 1)
            lines = out.splitlines()
            self.assertEqual(lines[0], f"PASS  {a}  doctest 1/1")
            self.assertIn("doctest が 1 件不一致", lines[1])
            self.assertIn("doctest がない", lines[2])
            self.assertIn("NameError", lines[3])
            self.assertEqual(lines[4], "pass@1 = 1/4 = 25.0%")
            self.assertEqual(run("pass@1", a, "--total", "10")[:2], (0, f"PASS  {a}  doctest 1/1\npass@1 = 1/10 = 10.0%\n"))
            self.assertEqual(run("pass@1", a, "--total", "0")[0], 1)

    def test_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            bad = self.make(d, "bad", "x = \n")
            code, out, _ = run("pass@1", bad, os.path.join(d, "none.ko"))
            self.assertEqual(code, 1)
            self.assertEqual(out.count("FAIL"), 2)
            self.assertIn("pass@1 = 0/2 = 0.0%", out)


class Convert(unittest.TestCase):
    def test_stdin_to_stdout(self):
        code, out, _ = run("conv", "-f", "pylike", "-t", "lisplike", stdin="x = [1, 2]\n")
        self.assertEqual((code, out), (0, "(set x (list 1 2))\n"))

    def test_file_and_output_file(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "a.ja"), os.path.join(d, "a.py")
            with open(src, "w", encoding="utf-8") as f:
                f.write("※ 注\nxに1を代入\n")
            code, out, _ = run("conv", src, "--from", "ja", "--to", "pylike", "-o", dst)
            self.assertEqual((code, out), (0, ""))
            with open(dst, encoding="utf-8") as f:
                self.assertEqual(f.read(), "# 注\nx = 1\n")

    def test_check_only(self):
        code, out, _ = run("conv", "-f", "pylike", stdin="x = 1\ny = 2\n")
        self.assertEqual((code, out), (0, "OK: 2 個の文\n"))

    def test_syntax_given_as_json_path(self):
        from kolang.syntax import SYNTAX_DIR
        code, out, _ = run("conv", "-f", "pylike", "-t", str(SYNTAX_DIR / "ja.json"), stdin="x = 1\n")
        self.assertEqual((code, out), (0, "xに1を代入\n"))

    def test_errors(self):
        code, out, err = run("conv", "-f", "pylike", "-t", "ja", stdin="x = = 1\n")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("1:5", err)
        code, _, err = run("conv", "-f", "pylike", "-t", "nope", stdin="x = 1\n")
        self.assertEqual(code, 1)
        self.assertIn("nope", err)
        code, _, err = run("conv", "missing.py", "-f", "pylike")
        self.assertEqual(code, 1)

    def test_no_arguments_shows_help(self):
        code, out, _ = run()
        self.assertEqual(code, 2)
        self.assertIn("--show", out)

    def test_file_without_from_is_an_error(self):
        code, _, err = run("conv", "-t", "ja", stdin="x = 1\n")
        self.assertEqual(code, 2)
        self.assertIn("--from", err)


if __name__ == "__main__":
    unittest.main()


class Conv(unittest.TestCase):
    """サブコマンド kolang conv。conv を省いた古い書き方はない。"""

    def test_old_style_without_conv_is_gone(self):
        self.assertEqual(run("-f", "pylike", "-t", "ja", stdin="x = 1\n")[0], 2)

    def test_conv_stdin(self):
        code, out, _ = run("conv", "-f", "pylike", "-t", "ja", stdin="x = 1\n")
        self.assertEqual((code, out), (0, "xに1を代入\n"))

    def test_conv_ko_needs_no_from(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "p.ko"), os.path.join(d, "q.ko")
            with open(src, "w", encoding="utf-8") as f:
                f.write("```pylike\nx = 1\n```\n")
            self.assertEqual(run("conv", src, "-t", "ja")[:2], (0, "xに1を代入\n"))
            self.assertEqual(run("conv", src, "-t", "ja", "-o", dst)[0], 0)
            with open(dst, encoding="utf-8") as f:
                self.assertEqual(f.read(), "```ja\nxに1を代入\n```\n")

    def test_conv_check_only_and_missing_from(self):
        self.assertEqual(run("conv", "-f", "pylike", stdin="x = 1\n")[:2], (0, "OK: 1 個の文\n"))
        self.assertEqual(run("conv", "-t", "ja", stdin="x = 1\n")[0], 2)

    def test_conv_help(self):
        code, out, _ = run("conv", "-h")
        self.assertEqual(code, 0)
        self.assertIn("kolang conv", out)
