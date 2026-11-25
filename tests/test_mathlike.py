"""数学記号版（mathlike）。"""

import unittest

from kolang import ast as K
from kolang.kofile import split_ko
from kolang.parser import parse
from kolang.syntax import collisions, load_syntax
from kolang.unparser import convert


class Mathlike(unittest.TestCase):
    def test_no_collisions(self):
        self.assertEqual(collisions(load_syntax("mathlike", verify=False), True), [])

    def test_text(self):
        src = "x = 1\nxs.append(x)\nif x == 1:\n    print(x)\nelse:\n    x += 1\n"
        out = convert(src, "pylike", "mathlike")
        self.assertEqual(out.splitlines()[0], "x ← 1")
        self.assertEqual(out.splitlines()[1], "xs ⊞ x")
        self.assertIn("⊢ x = 1 ⇒", out)
        self.assertIn("x ↑", out)

    def test_round_trip_with_pylike(self):
        for path in ("kolang/examples/syntax_tour.ko", "examples/gcd.ko"):
            with open(path, encoding="utf-8") as f:
                spec, code = split_ko(f.read())
            back = convert(convert(code, spec, "mathlike"), "mathlike", "pylike")
            self.assertEqual(parse(back, "pylike"), parse(code, spec))

    def test_assign(self):
        self.assertEqual(parse("x ← 1", "mathlike").stmts, (K.Assign(K.Var("x"), K.Num(1)),))


if __name__ == "__main__":
    unittest.main()
