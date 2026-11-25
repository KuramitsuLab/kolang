"""万葉仮名（manyo）: 日本語の音を漢字で書くシンタックス。"""

import unittest

from kolang import ast as K
from kolang.kofile import split_ko
from kolang.parser import parse
from kolang.syntax import collisions, load_syntax
from kolang.unparser import convert


class Manyo(unittest.TestCase):
    def test_no_collisions(self):
        self.assertEqual(collisions(load_syntax("manyo", verify=False), True), [])

    def test_text(self):
        src = "x = 1\nxs.append(x)\nif x == 1:\n    print(x)\nelse:\n    x += 1\n"
        out = convert(src, "pylike", "manyo")
        self.assertEqual(out.splitlines()[0], "x袁1登須")
        self.assertEqual(out.splitlines()[1], "x袁xs迩久波布")
        self.assertIn("毛斯x賀1迩比登斯岐登岐波 己許与理", out)
        self.assertIn("佐良受波 己許与理", out)
        self.assertIn("(x)袁毛知韋流斯米須能阿多比", out)

    def test_round_trip_with_pylike(self):
        for path in ("kolang/examples/syntax_tour.ko", "examples/gcd.ko"):
            with open(path, encoding="utf-8") as f:
                spec, code = split_ko(f.read())
            back = convert(convert(code, spec, "manyo"), "manyo", "pylike")
            self.assertEqual(parse(back, "pylike"), parse(code, spec))

    def test_assign_reads_target_first(self):
        self.assertEqual(parse("x袁1登須", "manyo").stmts, (K.Assign(K.Var("x"), K.Num(1)),))


if __name__ == "__main__":
    unittest.main()
