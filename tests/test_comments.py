import copy
import json
import unittest

from kolang import convert, load_syntax, parse, syntax_from_dict, unparse
from kolang import ast as K
from kolang.comments import collect_comments
from kolang.syntax import SYNTAX_DIR

PY = (
    "# head\n"
    "\n"
    "x = 1  # tail\n"
    "if x == 1: # header\n"
    "    # lead\n"
    "    y = 2\n"
    "# before else\n"
    "else: # on else\n"
    "    y = 3\n"
    "for _ in range(2): # loop\n"
    "    x += 1\n"
    "def f(a): # func\n"
    "    return a # ret\n"
    "# end 1\n"
    "# end 2\n"
)

# ブロックは 『 』。コメントのある行は改行で終わるので、その続きは次の行から。
JA = (
    "※ head\n"
    "xに1を代入 ※ tail\n"
    "もしxが1と等しいなら ※ header\n"
    "『\n"
    "    ※ lead\n"
    "    yに2を代入\n"
    "』そうでなければ『\n"
    "    ※ before else\n"
    "    ※ on else\n"
    "    yに3を代入\n"
    "』\n"
    "2回くり返す ※ loop\n"
    "『\n"
    "    xを増やす\n"
    "』\n"
    "関数 f(a)とは ※ func\n"
    "『\n"
    "    aを返す ※ ret\n"
    "』\n"
    "※ end 1\n"
    "※ end 2\n"
)


def comments(source, syntax):
    return collect_comments(parse(source, syntax))


class Attach(unittest.TestCase):
    def test_leading_trailing_and_tail(self):
        tree = parse(PY, "pylike")
        first, second, third, fourth = tree.stmts
        self.assertEqual(first.comments, K.Comments(("head",), "tail"))
        self.assertEqual(second.comments, K.Comments((), "header"))
        self.assertEqual(second.body.stmts[0].comments, K.Comments(("lead",), None))
        # else の行のコメントは、見出しがないので、else の中の最初の文の leading になる
        self.assertEqual(second.else_body.stmts[0].comments,
                         K.Comments(("before else", "on else"), None))
        self.assertEqual(third.comments.trailing, "loop")
        self.assertEqual(fourth.comments.trailing, "func")
        self.assertEqual(fourth.body.stmts[0].comments.trailing, "ret")
        self.assertEqual(tree.trailing, ("end 1", "end 2"))

    def test_comments_do_not_affect_equality(self):
        self.assertEqual(parse("x = 1 # a\n"), parse("# b\nx = 1\n"))
        self.assertEqual(parse("x = 1 # a\n").stmts[0], K.Assign(K.Var("x"), K.Num(1)))

    def test_only_comments(self):
        tree = parse("# a\n\n# b\n")
        self.assertEqual(tree, K.Block())
        self.assertEqual(tree.trailing, ("a", "b"))

    def test_comment_marker_inside_string_is_not_a_comment(self):
        tree = parse('x = "a # b"\n')
        self.assertEqual(collect_comments(tree), [((), None), ()])

    def test_comment_between_header_and_block_goes_to_first_statement(self):
        tree = parse("if x == 1:\n# between\n    y = 1\n")
        self.assertEqual(tree.stmts[0].body.stmts[0].comments.leading, ("between",))

    def test_empty_comment(self):
        self.assertEqual(parse("#\nx = 1 #\n").stmts[0].comments, K.Comments(("",), ""))

    def test_japanese_syntax(self):
        self.assertEqual(comments(JA, "ja"), comments(PY, "pylike"))


class Convert(unittest.TestCase):
    def test_pylike_to_ja(self):
        # else の行のコメントは else の中の最初の文の前に移る（見出しにコメントを持てないため）
        self.assertEqual(convert(PY, "pylike", "ja"), JA)

    def test_ja_to_pylike_keeps_comments_but_normalizes_spacing(self):
        text = convert(JA, "ja", "pylike")
        self.assertEqual(comments(text, "pylike"), comments(JA, "ja"))
        self.assertIn("x = 1 # tail\n", text)

    def test_round_trip_keeps_everything(self):
        for source, name, other in ((PY, "pylike", "ja"), (JA, "ja", "pylike")):
            there = convert(source, name, other)
            back = convert(there, other, name)
            self.assertEqual(comments(back, name), comments(source, name))

    def test_target_without_comments_drops_them(self):
        data = json.loads((SYNTAX_DIR / "ja.json").read_text(encoding="utf-8"))
        data["tokens"].pop("comment")
        plain = syntax_from_dict(data)
        self.assertEqual(convert("# a\nx = 1 # b\n", "pylike", plain), "xに1を代入\n")

    def test_multiline_comment_becomes_lines_or_joins(self):
        tree = K.Block((K.Assign(K.Var("x"), K.Num(1),
                                 comments=K.Comments(("a\nb",), "c\nd")),))
        self.assertEqual(unparse(tree, "pylike"), "# a\n# b\nx = 1 # c d\n")


class BlockCommentSyntax(unittest.TestCase):
    """レイアウト "none",/* ... */ のコメント。"""

    @staticmethod
    def syntax():
        data = copy.deepcopy(json.loads((SYNTAX_DIR / "pylike.json").read_text(encoding="utf-8")))
        data.update(name="brace", layout="none", space="[ \\n]+")
        data.pop("continuation", None)
        data["tokens"].update(block_begin="\\{", block_sep=";", block_end="\\}",
                              comment_begin="/\\*", comment_end="\\*/")
        return syntax_from_dict(data)

    def test_round_trip(self):
        brace = self.syntax()
        text = convert(PY, "pylike", brace)
        self.assertIn("/* head */", text)
        self.assertEqual(comments(text, brace), comments(PY, "pylike"))
        self.assertEqual(comments(convert(text, brace, "ja"), "ja"), comments(PY, "pylike"))

    def test_multiline_block_comment_to_pylike(self):
        brace = self.syntax()
        tree = parse("/* one\n   two */ { x = 1; }", brace)
        self.assertEqual(tree.stmts[0].comments.leading, ("one\n   two",))
        self.assertEqual(unparse(tree, "pylike"), "# one\n# two\nx = 1\n")


if __name__ == "__main__":
    unittest.main()
