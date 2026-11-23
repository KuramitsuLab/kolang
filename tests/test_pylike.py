import unittest

from kolang import ParseError, parse
from kolang import ast as K


def prog(src):
    return parse(src, "pylike")


def one(src):
    (stmt,) = prog(src).stmts
    return stmt


x, y = K.Var("x"), K.Var("y")


class StatementTests(unittest.TestCase):
    def test_assign(self):
        self.assertEqual(one("x = 1\n"), K.Assign(x, K.Num(1)))

    def test_assign_index_and_nested(self):
        self.assertEqual(one("x[0][y] = 2.5"),
                         K.Assign(K.Index(K.Index(x, K.Num(0)), y), K.Num(2.5)))

    def test_append(self):
        self.assertEqual(one("x.append(1)"), K.Append(x, K.Num(1)))

    def test_inc_dec(self):
        self.assertEqual(one("x += 1"), K.Inc(x))
        self.assertEqual(one("x -= 1"), K.Dec(x))

    def test_break_and_return(self):
        self.assertEqual(one("break"), K.Break())
        self.assertEqual(one("return None"), K.Return(K.NoneLit()))

    def test_comment_and_blank_lines(self):
        src = "# head\n\nx = 1  # tail\n\n   # indented comment\ny = 2\n"
        self.assertEqual(prog(src).stmts, (K.Assign(x, K.Num(1)), K.Assign(y, K.Num(2))))

    def test_empty_program(self):
        self.assertEqual(prog(""), K.Block())
        self.assertEqual(prog("# nothing\n"), K.Block())


class ExpressionTests(unittest.TestCase):
    def value(self, src):
        return one(f"x = {src}").value

    def test_literals(self):
        self.assertEqual(self.value('"a b"'), K.Str("a b"))
        self.assertEqual(self.value("'q\\'q\\n'"), K.Str("q'q\n"))
        self.assertEqual(self.value("True"), K.Bool(True))
        self.assertEqual(self.value("False"), K.Bool(False))
        self.assertEqual(self.value("None"), K.NoneLit())
        self.assertEqual(self.value("12"), K.Num(12))

    def test_list(self):
        self.assertEqual(self.value("[]"), K.ListLit())
        self.assertEqual(self.value("[1, [2], y]"),
                         K.ListLit((K.Num(1), K.ListLit((K.Num(2),)), y)))
        self.assertEqual(self.value("[1, 2,]"), K.ListLit((K.Num(1), K.Num(2))))

    def test_call(self):
        self.assertEqual(self.value("f()"), K.Call("f"))
        self.assertEqual(self.value("f(1, g(y))"), K.Call("f", (K.Num(1), K.Call("g", (y,)))))

    def test_quoted_identifier(self):
        self.assertEqual(one("_a b_ = 1"), K.Assign(K.Var("a b"), K.Num(1)))

    def test_reserved_word_is_not_a_name(self):
        with self.assertRaises(ParseError):
            prog("if = 1")


class CompareTests(unittest.TestCase):
    def test_all_operators(self):
        for op in ("!=", "<", ">", "<=", ">=", "=="):
            with self.subTest(op=op):
                stmt = one(f"if x {op} y:\n    break")
                self.assertEqual(stmt.cond, K.Compare(op, x, y))


class BlockTests(unittest.TestCase):
    def test_if_else(self):
        src = "if x < 1:\n    y = 1\n    y += 1\nelse:\n    y = 2\nx = 0\n"
        first, second = prog(src).stmts
        self.assertEqual(first, K.If(
            K.Compare("<", x, K.Num(1)),
            K.Block((K.Assign(y, K.Num(1)), K.Inc(y))),
            K.Block((K.Assign(y, K.Num(2)),))))
        self.assertEqual(second, K.Assign(x, K.Num(0)))

    def test_if_without_else_then_dedent(self):
        src = "if x == 1:\n    y = 1\ny = 2"
        self.assertEqual(prog(src).stmts[0].else_body, None)
        self.assertEqual(len(prog(src).stmts), 2)

    def test_repeat(self):
        self.assertEqual(one("for _ in range(3):\n    x += 1"),
                         K.Repeat(K.Num(3), K.Block((K.Inc(x),))))

    def test_def_and_nested_dedent(self):
        src = (
            "def f(a, b):\n"
            "    for _ in range(a):\n"
            "        if a > b:\n"
            "            return a\n"
            "        else:\n"
            "            return b\n"
            "    return None\n"
            "r = f(1, 2)\n"
        )
        func, call = prog(src).stmts
        a, b = K.Var("a"), K.Var("b")
        inner_if = K.If(K.Compare(">", a, b),
                        K.Block((K.Return(a),)), K.Block((K.Return(b),)))
        self.assertEqual(func, K.FuncDef("f", ("a", "b"), K.Block((
            K.Repeat(a, K.Block((inner_if,))),
            K.Return(K.NoneLit())))))
        self.assertEqual(call, K.Assign(K.Var("r"), K.Call("f", (K.Num(1), K.Num(2)))))

    def test_def_without_params(self):
        self.assertEqual(one("def f():\n    return 1"),
                         K.FuncDef("f", (), K.Block((K.Return(K.Num(1)),))))

    def test_tab_indent(self):
        self.assertEqual(one("if x == 1:\n\tbreak").body, K.Block((K.Break(),)))


class SpaceAndCommentTests(unittest.TestCase):
    def test_no_space_needed_next_to_symbols(self):
        self.assertEqual(one("x=1"), K.Assign(x, K.Num(1)))
        self.assertEqual(one("if x<1:\n    break").cond, K.Compare("<", x, K.Num(1)))
        self.assertEqual(one("x.append(f(1,2))"),
                         K.Append(x, K.Call("f", (K.Num(1), K.Num(2)))))

    def test_many_spaces(self):
        self.assertEqual(one("x   =    [ 1 ,  2 ]"),
                         K.Assign(x, K.ListLit((K.Num(1), K.Num(2)))))

    def test_space_required_between_word_chars(self):
        for src in ("return1", "x = 1y", "if x == 1y:\n    break", "x = Truex y"):
            with self.subTest(src=src):
                with self.assertRaises(ParseError):
                    prog(src)
        # 語の文字で始まる名前は、キーワードの接頭辞でも名前として読める
        self.assertEqual(one("x = Truex").value, K.Var("Truex"))
        self.assertEqual(one("iffy = 1").target, K.Var("iffy"))

    def test_space_is_required_in_error(self):
        with self.assertRaises(ParseError) as cm:
            prog("x = 1y")
        self.assertIn("space", cm.exception.message)
        self.assertEqual((cm.exception.line, cm.exception.col), (1, 6))

    def test_comment_ends_at_line_end(self):
        src = "x = 1# no space needed\nif x == 1: # after header\n    y = 2 # tail\n"
        first, second = prog(src).stmts
        self.assertEqual(first, K.Assign(x, K.Num(1)))
        self.assertEqual(second.body, K.Block((K.Assign(y, K.Num(2)),)))

    def test_comment_inside_string_is_text(self):
        self.assertEqual(one('x = "a # b"').value, K.Str("a # b"))

    def test_tab_is_not_a_space(self):
        with self.assertRaises(ParseError):
            prog("x =\t1")


class ErrorTests(unittest.TestCase):
    def test_error_position(self):
        with self.assertRaises(ParseError) as cm:
            prog("x = 1\ny = = 2\n")
        self.assertEqual(cm.exception.line, 2)
        self.assertEqual(cm.exception.col, 5)

    def test_bad_indent(self):
        with self.assertRaises(ParseError):
            prog("  x = 1")
        with self.assertRaises(ParseError):
            prog("if x == 1:\n        y = 1\n    y = 2")

    def test_missing_colon(self):
        with self.assertRaises(ParseError):
            prog("if x == 1\n    y = 1")


if __name__ == "__main__":
    unittest.main()
