import io
import unittest
import warnings
from contextlib import redirect_stdout

from kolang import ParseError, convert, load_syntax, parse
from kolang import ast as K
from kolang.pyeval import execute
from kolang.snippet import failures
from tests.test_convert import SAMPLES

PS = (
    "/f [a b] {a return} def\n"
    "/s 0 def\n"
    "3 {/s inc} repeat\n"
    "s 3 eq {xs \"ok\" append} {/s [1 2] def exit} ifelse\n"
)

PY = (
    "def f(a, b):\n"
    "    return a\n"
    "s = 0\n"
    "for _ in range(3):\n"
    "    s += 1\n"
    "if s == 3:\n"
    "    xs.append(\"ok\")\n"
    "else:\n"
    "    s = [1, 2]\n"
    "    break\n"
)


def ps(src):
    return parse(src, "pslike")


class Parsing(unittest.TestCase):
    def test_same_ast_as_pylike(self):
        self.assertEqual(ps(PS), parse(PY, "pylike"))

    def test_if_without_else(self):
        (stmt,) = ps("x 1 lt {/x inc} if").stmts
        self.assertIsNone(stmt.else_body)
        (stmt,) = ps("x 1 lt {/x inc} {/x dec} ifelse").stmts
        self.assertIsNotNone(stmt.else_body)

    def test_postfix_index_allows_spaces(self):
        (stmt,) = ps("/y a 1 get 2 get def").stmts
        self.assertEqual(stmt.value, K.Index(K.Index(K.Var("a"), K.Num(1)), K.Num(2)))
        # get が続かなければ、別々の要素
        (stmt,) = ps("/y [a b] def").stmts
        self.assertEqual(stmt.value, K.ListLit((K.Var("a"), K.Var("b"))))

    def test_index_as_assignment_target(self):
        (stmt,) = ps("/x 1 get 2 def").stmts
        self.assertEqual(stmt.target, K.Index(K.Var("x"), K.Num(1)))

    def test_postfix_neg(self):
        (stmt,) = ps("/y x neg neg def").stmts
        self.assertEqual(stmt.value, K.Neg(K.Neg(K.Var("x"))))
        (stmt,) = ps("/y 1 neg def").stmts
        self.assertEqual(stmt.value, K.Neg(K.Num(1)))
        (stmt,) = ps("/y a 1 get neg def").stmts
        self.assertEqual(stmt.value, K.Neg(K.Index(K.Var("a"), K.Num(1))))

    def test_call_uses_mark(self):
        (stmt,) = ps("/y mark 1 mark 2 3 /g exec /f exec def").stmts
        self.assertEqual(stmt.value, K.Call("f", (K.Num(1), K.Call("g", (K.Num(2), K.Num(3))))))
        (stmt,) = ps("mark x /print exec").stmts
        self.assertEqual(stmt, K.CallStmt(K.Call("print", (K.Var("x"),))))

    def test_comment(self):
        prog = ps("% 見出し\n/x 1 def % 末尾\n")
        self.assertEqual(len(prog.stmts), 1)

    def test_reserved_words_are_not_names(self):
        for src in ("/get 1 def", "/neg 1 def", "/ifelse 1 def"):
            with self.subTest(src=src):
                with self.assertRaises(ParseError):
                    ps(src)

    def test_syntax_error(self):
        with self.assertRaises(ParseError):
            ps("/x def")


class Conversion(unittest.TestCase):
    def test_samples_roundtrip(self):
        for src_name, src in SAMPLES:
            with self.subTest(src=src_name, head=src[:20]):
                tree = parse(src, src_name)
                out = convert(src, src_name, "pslike")
                self.assertEqual(parse(out, "pslike"), tree)
                back = convert(out, "pslike", src_name)
                self.assertEqual(parse(back, src_name), tree)

    def test_output_forms(self):
        out = convert("if x < 1:\n    x += 1\nelse:\n    x -= 1\ny = -x\nz = a[1]\n", "pylike", "pslike")
        self.assertEqual(out, "x 1 lt {\n    /x inc\n} {\n    /x dec\n} ifelse\n/y x neg def\n/z a 1 get def\n")

    def test_stdlib_names_kept(self):
        self.assertEqual(convert("print(add(1, 2))", "pylike", "pslike").strip(),
                         "mark mark 1 2 /add exec /print exec")


class Snippets(unittest.TestCase):
    def test_all_snippets_roundtrip(self):
        self.assertEqual(failures(load_syntax("pslike")), [])

    def test_loads_without_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            load_syntax("pslike")


class Running(unittest.TestCase):
    def test_factorial(self):
        src = ("/f [n] {\n  n 1 le {1 return} {mark n mark mark n 1 /sub exec /f exec /mul exec return} ifelse\n} def\n"
               "mark mark 5 /f exec /print exec\n")
        out = io.StringIO()
        with redirect_stdout(out):
            execute(ps(src))
        self.assertEqual(out.getvalue(), "120\n")


if __name__ == "__main__":
    unittest.main()
