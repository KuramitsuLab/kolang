import copy
import json
import unittest
from pathlib import Path

from kolang import (ParseError, UnparseError, convert, load_syntax, parse, syntax_from_dict,
                    unparse)
from kolang import ast as K
from kolang.regexgen import leading_literal, sample, string_delimiters
from kolang.syntax import SYNTAX_DIR

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

JA = (
    "関数 add(a, b)とは『\n"
    "    aを返す\n"
    "』\n"
    "sに0を代入\n"
    "3回くり返す『\n"
    "    sを増やす\n"
    "』\n"
    "もしsが3と等しいなら『\n"
    "    xsに\"ok\"を追加\n"
    "』そうでなければ『\n"
    "    sに【1, 2】を代入\n"
    "    抜ける\n"
    "』\n"
)

# どちらの書き方でも通る、いろいろな構文のプログラム（シンタックス名, ソース）。
SAMPLES = [
    ("pylike", PY),
    ("ja", JA),
    ("pylike", 'x = [True, False, None, "a\\"b\\\\c\\n", 1.5]\n'
               "y[0][x] = f(1, g(x), [])\n"
               "z.append(h())\n"
               "if x != y:\n    x -= 1\n"
               "if x < y:\n    x -= 1\n"
               "if x > y:\n    x -= 1\n"
               "if x <= y:\n    x -= 1\n"
               "if x >= y:\n    x -= 1\n"
               "def f():\n    n = 2\n    for _ in range(n):\n        if n == 1:\n            return n\n"
               "        else:\n            n -= 1\n    return None\n"),
    ("pylike", "_合計 金額_ = 1\n_カウンタ_ += 1\n"),
    ("ja", "_合計_に【真,偽,無】を代入\n_カウンタ_を増やす\nxの(0)番目の(y)番目に (1,2)におけるfの値を代入\n"),
]


class RoundTrip(unittest.TestCase):
    def test_every_pair_keeps_the_ast(self):
        for src_name, source in SAMPLES:
            tree = parse(source, src_name)
            for dst_name in ("pylike", "ja"):
                with self.subTest(src=src_name, dst=dst_name, head=source[:20]):
                    text = convert(source, src_name, dst_name)
                    self.assertEqual(parse(text, dst_name), tree)

    def test_there_and_back_again(self):
        for source in (PY, JA):
            tree = parse(source, "pylike" if source is PY else "ja")
            there = convert(source, "pylike" if source is PY else "ja",
                            "ja" if source is PY else "pylike")
            back = convert(there, "ja" if source is PY else "pylike",
                           "pylike" if source is PY else "ja")
            self.assertEqual(parse(back, "pylike" if source is PY else "ja"), tree)


class Output(unittest.TestCase):
    def test_pylike_to_ja(self):
        self.assertEqual(convert(PY, "pylike", "ja"), JA)

    def test_ja_to_pylike(self):
        self.assertEqual(convert(JA, "ja", "pylike"), PY)

    def test_comments_are_converted(self):
        self.assertEqual(convert("x = 1 # c\n", "pylike", "ja"), "xに1を代入 ※ c\n")

    def test_names_are_quoted_when_the_target_cannot_write_them(self):
        self.assertEqual(convert("_合計_に1を代入\n", "ja", "pylike"), "_合計_ = 1\n")
        self.assertEqual(convert("_if_ = 1\n", "pylike", "ja"), "ifに1を代入\n")
        self.assertEqual(convert("ifに1を代入\n", "ja", "pylike"), "_if_ = 1\n")

    def test_unparse_directly(self):
        tree = K.Block((K.Assign(K.Var("x"), K.Str('a"b')),))
        self.assertEqual(unparse(tree, "pylike"), 'x = "a\\"b"\n')
        self.assertEqual(unparse(tree, "ja"), "xに\"a\\\"b\"を代入\n")


class Errors(unittest.TestCase):
    def test_unwritable_things(self):
        for node, msg in [
            (K.Assign(K.Var("x"), K.Num(-1)), "number"),
            (K.Assign(K.Var("a b_c"), K.Num(1)), "name"),
            (K.If(K.Compare("<", K.Var("x"), K.Num(1)), K.Block()), "empty block"),
        ]:
            with self.subTest(msg=msg):
                with self.assertRaises(UnparseError) as cm:
                    unparse(K.Block((node,)), "pylike")
                self.assertIn(msg, str(cm.exception))

    def test_parse_error_passes_through(self):
        with self.assertRaises(ParseError):
            convert("x = = 1", "pylike", "ja")


class Reserved(unittest.TestCase):
    def test_extracted_from_token_regexes(self):
        self.assertEqual(
            load_syntax("pylike").reserved,
            {"if", "else", "for", "def", "return", "break", "True", "False", "None"})
        # 日本語版の語は名前の形ではない（ひらがな・漢字）ので、予約語にならない
        self.assertEqual(load_syntax("ja").reserved, frozenset())

    def test_extra_reserved_words_in_json(self):
        data = json.loads((SYNTAX_DIR / "pylike.json").read_text(encoding="utf-8"))
        data["reserved"] = ["print"]
        syn = syntax_from_dict(data)
        self.assertIn("print", syn.reserved)
        with self.assertRaises(ParseError):
            parse("print = 1", syn)


class BraceSyntax(unittest.TestCase):
    """レイアウトが "none" のシンタックスでも,変換できる。"""

    @staticmethod
    def brace_syntax():
        data = json.loads((SYNTAX_DIR / "pylike.json").read_text(encoding="utf-8"))
        data = copy.deepcopy(data)
        data.update(name="brace", layout="none")
        data.pop("continuation", None)
        data["tokens"].update(block_begin="\\{", block_sep=";", block_end="\\}")
        return syntax_from_dict(data)

    def test_round_trip(self):
        brace = self.brace_syntax()
        for src_name, source in SAMPLES[:3]:
            with self.subTest(head=source[:20]):
                text = convert(source, src_name, brace)
                self.assertEqual(parse(text, brace), parse(source, src_name))
                self.assertEqual(parse(convert(text, brace, "ja"), "ja"), parse(source, src_name))

    def test_text(self):
        brace = self.brace_syntax()
        self.assertEqual(convert("if x < 1:\n    break\nelse:\n    x = 1\n", "pylike", brace),
                         "{if x < 1:{break;}else:{x = 1;};}")


class RegexTools(unittest.TestCase):
    def test_leading_literal(self):
        self.assertEqual(leading_literal("else *:"), "else")
        self.assertEqual(leading_literal("for +_ +in"), "for")
        self.assertEqual(leading_literal(",|(?=\\))"), "")
        self.assertEqual(leading_literal("\\.append\\("), ".append(")

    def test_sample(self):
        self.assertEqual(sample("for +_ +in +range\\("), "for _ in range(")
        self.assertEqual(sample("else *:"), "else:")
        self.assertEqual(sample("=(?!=)"), "=")
        self.assertEqual(sample(",|(?=\\))"), ",")
        self.assertEqual(sample(",|(?=\\))", prefer_empty=True), "")
        self.assertEqual(sample("[ 　]+"), " ")

    def test_string_delimiters(self):
        self.assertEqual(string_delimiters("\"(?:[^\"]|\\\\.)*\"|'(?:[^']|\\\\.)*'"), ('"', '"'))
        self.assertEqual(string_delimiters("『(?:[^』])*』"), ("『", "』"))


if __name__ == "__main__":
    unittest.main()


class RandomEmit(unittest.TestCase):
    """emit の候補（配列）: seed があるときだけ choice,なければ常に最初。"""

    @staticmethod
    def syntax(choices):
        data = json.loads((SYNTAX_DIR / "pylike.json").read_text(encoding="utf-8"))
        data["tokens"]["funcapp"]["arg_sep.emit"] = choices
        return syntax_from_dict(data)

    def test_first_choice_without_seed(self):
        syn = self.syntax([", ", ","])
        self.assertEqual(convert("print(1, 2, 3)\n", "pylike", syn), "print(1, 2, 3)\n")

    def test_seed_is_reproducible_and_picks_others(self):
        syn = self.syntax([", ", ","])
        src = "print(1, 2, 3, 4, 5, 6)\n"
        outs = {s: convert(src, "pylike", syn, random_emit=s) for s in range(8)}   # 読み直しの検査つき
        self.assertEqual(outs[3], convert(src, "pylike", syn, random_emit=3))
        self.assertGreater(len(set(outs.values())), 1)

    def test_each_choice_must_match_the_token(self):
        with self.assertRaises(ValueError):
            self.syntax([", ", "; "])
        with self.assertRaises(ValueError):
            self.syntax([])
