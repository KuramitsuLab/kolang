import copy
import json
import unittest

from kolang import ParseError, convert, load_syntax, parse, syntax_from_dict
from kolang import ast as K
from kolang.comments import collect_comments
from kolang.syntax import SYNTAX_DIR, flatten_tokens
from tests.test_convert import SAMPLES

LISP = (
    "(def add (a b) (return a))\n"
    "(set s 0)\n"
    "(repeat 3 (inc s))\n"
    "(if (== s 3) (append xs \"ok\") (else (set s (list 1 2)) (break)))\n"
)

PY = (
    "def add(a, b):\n"
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


def lisp(src):
    return parse(src, "lisplike")


class Parsing(unittest.TestCase):
    def test_same_ast_as_pylike(self):
        self.assertEqual(lisp(LISP), parse(PY, "pylike"))

    def test_index_is_an_index_not_a_call(self):
        (stmt,) = lisp("(set y (get (get x 0) i))").stmts
        self.assertEqual(stmt.value, K.Index(K.Index(K.Var("x"), K.Num(0)), K.Var("i")))
        # (getx ...) は get ではないので、関数呼び出し
        (stmt,) = lisp("(set y (getx x 0))").stmts
        self.assertEqual(stmt.value, K.Call("getx", (K.Var("x"), K.Num(0))))

    def test_index_as_assignment_target(self):
        (stmt,) = lisp("(set (get x 1) 2)").stmts
        self.assertEqual(stmt.target, K.Index(K.Var("x"), K.Num(1)))
        (stmt,) = lisp("(inc (get x i))").stmts
        self.assertEqual(stmt, K.Inc(K.Index(K.Var("x"), K.Var("i"))))

    def test_if_with_and_without_else(self):
        (a,) = lisp("(if (< x 1) (break))").stmts
        self.assertIsNone(a.else_body)
        (b,) = lisp("(if (<= x 1) (break) (else (inc x) (break)))").stmts
        self.assertEqual(b.cond.op, "<=")
        self.assertEqual(len(b.else_body.stmts), 2)

    def test_all_comparisons(self):
        for op in ("!=", "<", ">", "<=", ">=", "=="):
            with self.subTest(op=op):
                (stmt,) = lisp(f"(if ({op} x y) (break))").stmts
                self.assertEqual(stmt.cond, K.Compare(op, K.Var("x"), K.Var("y")))

    def test_lists_calls_and_literals(self):
        (stmt,) = lisp('(set x (list 1 (list) "a b" true false nil (f) (g 1 2)))').stmts
        self.assertEqual(stmt.value, K.ListLit((
            K.Num(1), K.ListLit(), K.Str("a b"), K.Bool(True), K.Bool(False), K.NoneLit(),
            K.Call("f"), K.Call("g", (K.Num(1), K.Num(2))))))

    def test_free_whitespace_and_comments(self):
        src = (
            "; head\n"
            "(def f (n)   ; header\n"
            "  (repeat n\n"
            "    (inc n))\n"
            "  (return n))\n"
        )
        tree = lisp(src)
        self.assertEqual(tree.stmts[0].body.stmts[1], K.Return(K.Var("n")))
        self.assertEqual(collect_comments(tree)[0], (("head",), "header"))

    def test_hyphenated_and_quoted_names(self):
        # `-` は名前に使えない（jslike の `x--` と衝突するため）。使うなら | | で引用する。
        (stmt,) = lisp("(set _my-var_ _a b_)").stmts
        self.assertEqual(stmt, K.Assign(K.Var("my-var"), K.Var("a b")))
        self.assertEqual(convert("my_var = 1\n", "pylike", "lisplike"), "(set my_var 1)\n")
        with self.assertRaises(ParseError):
            lisp("(set my-var 1)")

    def test_call_statement(self):
        tree = lisp("(print 1 x)\n(set (get xs 0) (f))")
        self.assertEqual(tree.stmts[0], K.CallStmt(K.Call("print", (K.Num(1), K.Var("x")))))
        self.assertEqual(convert("(print 1)", "lisplike", "pylike"), "print(1)\n")

    def test_word_boundaries(self):
        for src in ("(set x1)", "(set x 1y)"):
            with self.subTest(src=src):
                with self.assertRaises(ParseError):
                    lisp(src)

    def test_reserved_words_come_from_tokens(self):
        self.assertEqual(load_syntax("lisplike").reserved,
                         {"true", "false", "nil", "set", "append", "inc", "dec", "if", "else",
                          "repeat", "break", "def", "return", "list", "get", "neg"})

    def test_empty_and_comment_only(self):
        self.assertEqual(lisp(""), K.Block())
        self.assertEqual(lisp("; nothing\n").trailing, ("nothing",))


class Output(unittest.TestCase):
    def test_pylike_to_lisp(self):
        self.assertEqual(convert(PY, "pylike", "lisplike"), LISP)

    def test_lisp_to_pylike(self):
        self.assertEqual(convert(LISP, "lisplike", "pylike"), PY)

    def test_arrays(self):
        self.assertEqual(
            convert("y = x[0][1]\nz = f(1, g(y), [])\nx[a[0]] = [1, [2]]\n", "pylike", "lisplike"),
            "(set y (get (get x 0) 1))\n"
            "(set z (f 1 (g y) (list)))\n"
            "(set (get x (get a 0)) (list 1 (list 2)))\n")

    def test_comments(self):
        text = convert("# a\nx = 1 # b\nif x == 1: # c\n    break\n# d\n", "pylike", "lisplike")
        self.assertEqual(lisp(text).stmts[1].comments.trailing, "c")
        self.assertEqual(collect_comments(lisp(text)),
                         collect_comments(parse("# a\nx = 1 # b\nif x == 1: # c\n    break\n# d\n")))

    def test_every_sample_round_trips_through_lisp(self):
        for name, source in SAMPLES:
            with self.subTest(src=name, head=source[:20]):
                text = convert(source, name, "lisplike")
                self.assertEqual(lisp(text), parse(source, name))
                back = convert(text, "lisplike", name)
                self.assertEqual(parse(back, name), parse(source, name))
                self.assertEqual(collect_comments(lisp(text)), collect_comments(parse(source, name)))


class SyntaxDefinition(unittest.TestCase):
    @staticmethod
    def data():
        return copy.deepcopy(json.loads((SYNTAX_DIR / "lisplike.json").read_text(encoding="utf-8")))

    def test_unknown_index_style(self):
        data = self.data()
        data["index"] = "infix"
        with self.assertRaises(ValueError):
            syntax_from_dict(data)

    def test_prefix_index_needs_index_sep(self):
        data = self.data()
        data = flatten_tokens(data)
        data["tokens"].pop("index_sep")
        data["emit"].pop("index_sep")
        with self.assertRaises(KeyError):
            parse("(set x 1)", syntax_from_dict(data))


if __name__ == "__main__":
    unittest.main()
