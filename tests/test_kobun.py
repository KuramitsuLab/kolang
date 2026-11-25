"""古文帳（kobun）: 平安のかな文学ふうのシンタックス。"""

import unittest

from kolang import ast as K
from kolang.kofile import split_ko
from kolang.parser import parse
from kolang.syntax import collisions, load_syntax
from kolang.unparser import convert


class Kobun(unittest.TestCase):
    def test_no_collisions(self):
        self.assertEqual(collisions(load_syntax("kobun", verify=False), True), [])

    def test_text(self):
        src = "x = 1\nxs.append(x)\nif x == 1:\n    print(x)\nelse:\n    x += 1\n"
        out = convert(src, "pylike", "kobun")
        self.assertEqual(out.splitlines()[0], "xを1とす")
        self.assertEqual(out.splitlines()[1], "xをxsにくはふ")
        self.assertIn("もしxが1にひとしきときは ここより", out)
        self.assertIn("さらずは ここより", out)
        self.assertIn("(x)をもちゐるしめすのあたひ", out)

    def test_round_trip_with_pylike(self):
        for path in ("kolang/examples/syntax_tour.ko", "examples/gcd.ko"):
            with open(path, encoding="utf-8") as f:
                spec, code = split_ko(f.read())
            back = convert(convert(code, spec, "kobun"), "kobun", "pylike")
            self.assertEqual(parse(back, "pylike"), parse(code, spec))

    def test_assign_reads_target_first(self):
        self.assertEqual(parse("xを1とす", "kobun").stmts, (K.Assign(K.Var("x"), K.Num(1)),))


if __name__ == "__main__":
    unittest.main()
