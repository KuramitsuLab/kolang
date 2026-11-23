import unittest

from kolang import convert, load_syntax, parse
from tests.test_convert import SAMPLES

C = "ja:jslike(assign,block,funcapp)"


class Cascade(unittest.TestCase):
    def test_tokens_come_from_each_syntax(self):
        syn = load_syntax(C)
        ja, js = load_syntax("ja"), load_syntax("jslike")
        for name in ("assign_op", "assign_end", "block_begin", "block_sep", "call_name_end", "arg_sep"):
            self.assertEqual(syn.tokens[name], js.tokens[name], name)
        for name in ("append_end", "if_then", "list_begin", "true"):
            self.assertEqual(syn.tokens[name], ja.tokens[name], name)
        self.assertEqual(syn.layout, "none")
        self.assertEqual(syn.toplevel, "bare")
        self.assertEqual(syn.string if hasattr(syn, "string") else syn.lexical["string"], ja.lexical["string"])

    def test_parse_and_convert(self):
        text = convert("x = [1, 2]\nif x == 1:\n    y = f(x)\n", "pylike", C)
        self.assertEqual(text, "x = 【1, 2】;\nもしxが1と等しいなら{\n    y = f(x);\n}\n")
        self.assertEqual(parse(text, C), parse("x = [1, 2]\nif x == 1:\n    y = f(x)\n", "pylike"))

    def test_roundtrip_samples(self):
        for name, source in SAMPLES:
            with self.subTest(source=source):
                convert(convert(source, name, C), C, name)

    def test_chain_and_plain(self):
        self.assertEqual(load_syntax("ja:jslike").tokens, load_syntax("jslike").tokens)
        syn = load_syntax("pylike:ja(literal):lisplike(break)")
        self.assertEqual((syn.tokens["true"], syn.tokens["none"], syn.tokens["break"]), ("真", "無", "\\(break\\)"))

    def test_unknown_group(self):
        with self.assertRaises(ValueError):
            load_syntax("ja:jslike(zzz)")


if __name__ == "__main__":
    unittest.main()
