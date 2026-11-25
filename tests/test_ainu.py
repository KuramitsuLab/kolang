"""アイヌ語ふう（ainu。草稿）。カタカナ表記・動詞が文末。"""

import unittest

from kolang import ast as K
from kolang.kofile import split_ko
from kolang.parser import parse
from kolang.syntax import collisions, load_syntax
from kolang.unparser import convert


class Ainu(unittest.TestCase):
    def test_no_collisions(self):
        self.assertEqual(collisions(load_syntax("ainu", verify=False), True), [])

    def test_text(self):
        out = convert("x = 1\nxs.append(x)\nif x == 1:\n    print(x)\nelse:\n    x += 1\n", "pylike", "ainu")
        lines = out.splitlines()
        self.assertEqual(lines[0], "x 1ネカㇻ")
        self.assertEqual(lines[1], "xウンxsカシレ")
        self.assertIn("xネワ1コラチヤクン オアシ", out)
        self.assertIn("ソモヤクン オアシ", out)
        self.assertIn("(x)ウンヌカレイェ", out)

    def test_round_trip_with_pylike(self):
        for path in ("kolang/examples/syntax_tour.ko", "examples/gcd.ko"):
            with open(path, encoding="utf-8") as f:
                spec, code = split_ko(f.read())
            back = convert(convert(code, spec, "ainu"), "ainu", "pylike")
            self.assertEqual(parse(back, "pylike"), parse(code, spec))

    def test_assign(self):
        self.assertEqual(parse("x 1ネカㇻ", "ainu").stmts, (K.Assign(K.Var("x"), K.Num(1)),))


if __name__ == "__main__":
    unittest.main()
