import os
import tempfile
import unittest

from kolang.kofile import KoFileError, join_ko, split_ko
from tests.test_cli import run


class Split(unittest.TestCase):
    def test_split(self):
        spec, code = split_ko("```ja:jslike(assign)\nx = 1;\n```\n後ろは読まない\n")
        self.assertEqual(spec, "ja:jslike(assign)")
        self.assertEqual(code, "x = 1;\n")

    def test_errors(self):
        for bad in ("x = 1\n", "```\nx\n```\n", "```pylike\nx = 1\n"):
            with self.assertRaises(KoFileError):
                split_ko(bad)

    def test_join_roundtrip(self):
        self.assertEqual(split_ko(join_ko("pylike", "x = 1\n")), ("pylike", "x = 1\n"))


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name, text):
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_run_ko(self):
        path = self.write("a.ko", "```pylike\nprint(add(1, 2))\n```\n")
        code, out, _ = run("run", path)
        self.assertEqual((code, out), (0, "3\n"))

    def test_check_and_convert_ko(self):
        path = self.write("a.ko", "```pylike\nx = 1\n```\n")
        self.assertEqual(run("conv", path)[0], 0)
        out_path = os.path.join(self.dir.name, "b.ko")
        self.assertEqual(run("conv", path, "-t", "ja", "-o", out_path)[0], 0)
        with open(out_path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("```ja\n") and text.endswith("\n```\n"))
        self.assertEqual(run("run", out_path)[0], 0)

    def test_missing_fence(self):
        path = self.write("a.ko", "x = 1\n")
        code, _, err = run("run", path)
        self.assertEqual(code, 1)
        self.assertIn("```", err)

    def test_sibling_doctest(self):
        path = self.write("a.ko", "```pylike\ndef f(x):\n    return x\ny = 5\n```\n")
        self.write("a.doctest", ">>> f(1)\n1\n>>> y\n5\n")
        code, _, err = run("run", path)
        self.assertEqual(code, 0)
        self.assertIn("2 passed, 0 failed", err)
        self.write("a.doctest", ">>> y\n6\n")
        code, _, err = run("run", path)
        self.assertEqual(code, 1)
        self.assertIn("1 failed", err)

    def test_sibling_doctest_sees_own_names(self):
        # ja の標準名 add は「足し算」だが、本体が add を定義していれば、.doctest の add は自作
        from kolang import convert
        body = convert("def add(a):\n    return a\n", "pylike", "ja")
        path = self.write("a.ko", f"```ja\n{body}```\n")
        self.write("a.doctest", ">>> add(5)\n5\n")
        code, _, err = run("run", path)
        self.assertEqual((code, "1 passed, 0 failed" in err), (0, True))

    def test_no_doctest_if_program_fails(self):
        path = self.write("a.ko", "```pylike\nx = boom\n```\n")
        self.write("a.doctest", ">>> y\n1\n")
        code, _, err = run("run", path)
        self.assertEqual(code, 1)
        self.assertNotIn("doctest:", err)
