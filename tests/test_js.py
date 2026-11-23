import json
import unittest

from kolang import convert, load_syntax, parse, syntax_from_dict
from kolang import ast as K
from kolang.syntax import SYNTAX_DIR
from tests.test_convert import SAMPLES

JS = (
    "function add(a, b) {\n"
    "    return a;\n"
    "}\n"
    "s = 0;\n"
    "for (let _ = 0; _ < 3; _++) {\n"
    "    s++;\n"
    "}\n"
    "if (s === 3) {\n"
    "    xs.push(\"ok\");\n"
    "} else {\n"
    "    s = [1, 2];\n"
    "    break;\n"
    "}\n"
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


class JsLike(unittest.TestCase):
    def test_toplevel_is_bare(self):
        self.assertEqual(load_syntax("jslike").toplevel, "bare")
        self.assertEqual(load_syntax("pylike").toplevel, "block")
        self.assertEqual(parse("x = 1;", "jslike").stmts[0].value, K.Num(1))

    def test_semicolon_is_optional(self):
        a = parse("x = 1\nif (x === 1) { x++ } else { x-- }\ny = [1, 2]\n", "jslike")
        b = parse("x = 1;\nif (x === 1) { x++; } else { x--; };\ny = [1, 2];\n", "jslike")
        self.assertEqual(a, b)

    def test_loose_equality_is_accepted(self):
        self.assertEqual(parse("if (a == b) { break }", "jslike"), parse("if (a === b) { break }", "jslike"))

    def test_comments(self):
        tree = parse("// a\nx = 1; // b\n", "jslike")
        self.assertEqual(len(tree.stmts), 1)

    def test_convert(self):
        self.assertEqual(convert(PY, "pylike", "jslike"), JS)
        self.assertEqual(convert(JS, "jslike", "pylike"), PY)

    def test_roundtrip_samples(self):
        for name, source in SAMPLES:
            with self.subTest(name=name):
                text = convert(source, name, "jslike")
                convert(text, "jslike", name)

    def test_unknown_toplevel(self):
        data = json.loads((SYNTAX_DIR / "jslike.json").read_text(encoding="utf-8"))
        data["toplevel"] = "x"
        with self.assertRaises(ValueError):
            syntax_from_dict(data)


if __name__ == "__main__":
    unittest.main()
