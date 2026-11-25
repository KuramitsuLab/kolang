"""関西弁（kansai）。"""

import unittest

from kolang import ast as K
from kolang.kofile import split_ko
from kolang.parser import parse
from kolang.syntax import collisions, load_syntax
from kolang.unparser import convert


class Kansai(unittest.TestCase):
    def test_no_collisions(self):
        self.assertEqual(collisions(load_syntax("kansai", verify=False), True), [])

    def test_text(self):
        src = "x = 1\nxs.append(x)\nif x == 1:\n    print(x)\nelse:\n    x += 1\n"
        out = convert(src, "pylike", "kansai")
        self.assertEqual(out.splitlines()[0], "1をxに入れとく")
        self.assertEqual(out.splitlines()[1], "xをxsに放り込む")
        self.assertIn("もしxが1と一緒なんやったら ほな", out)
        self.assertIn("そやなかったら ほな", out)
        self.assertIn("(x)をしゃべるにやらしたやつ", out)

    def test_round_trip_with_pylike(self):
        for path in ("kolang/examples/syntax_tour.ko", "examples/gcd.ko"):
            with open(path, encoding="utf-8") as f:
                spec, code = split_ko(f.read())
            back = convert(convert(code, spec, "kansai"), "kansai", "pylike")
            self.assertEqual(parse(back, "pylike"), parse(code, spec))

    def test_assign_reads_value_first(self):
        self.assertEqual(parse("1をxに入れとく", "kansai").stmts, (K.Assign(K.Var("x"), K.Num(1)),))


if __name__ == "__main__":
    unittest.main()
