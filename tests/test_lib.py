"""lib/ の関数（kolang で書いた join / split / slice など）を、Python のメソッドと突き合わせる。

lib/NAME.ko は NAME という関数だけを定義し、NAME.doctest に例がある。
各 .ko の先頭に取り込んで使うので、lib 同士は呼び合わない。
"""

import glob
import json
import os
import random
import re
import tempfile
import unittest

from kolang.cli import check_problem, load_program
from kolang.kofile import split_ko

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
NAMES = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(LIB, "*.ko")))


def lit(v):
    """値を pylike の式にする。"""
    if v is None: return "None"
    if v is True: return "True"
    if v is False: return "False"
    if isinstance(v, int): return ("-" if v < 0 else "") + str(abs(v))
    if isinstance(v, str): return json.dumps(v)
    return "[" + ", ".join(lit(x) for x in v) + "]"


class Layout(unittest.TestCase):
    def test_files(self):
        self.assertGreaterEqual(len(NAMES), 22)
        for name in NAMES:
            with self.subTest(name=name):
                self.assertTrue(os.path.isfile(os.path.join(LIB, name + ".doctest")))

    def test_each_defines_its_own_function_and_calls_no_other_lib(self):
        for name in NAMES:
            with self.subTest(name=name):
                _, program, _ = load_program(os.path.join(LIB, name + ".ko"), None)
                self.assertEqual(re.findall(r"FuncDef\(.*?name='(\w+)'", repr(program))[:1], [name])
                called = set(re.findall(r"Call\(func='(\w+)'", repr(program)))
                self.assertEqual(called & (set(NAMES) - {name}), set(), name)

    def test_doctests_pass(self):
        for name in NAMES:
            with self.subTest(name=name):
                ok, passed, total, reason = check_problem(os.path.join(LIB, name + ".ko"))
                self.assertTrue(ok, (name, passed, total, reason))


class Differential(unittest.TestCase):
    """乱数の入力で、本物の Python の結果と同じになるか。"""

    def run_cases(self, name, cases):
        """cases: [(準備の文の列, 呼び出しの式, 答え)]"""
        with open(os.path.join(LIB, name + ".ko"), encoding="utf-8") as f:
            _, code = split_ko(f.read())
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ko")
            with open(path, "w", encoding="utf-8") as f:
                f.write("```pylike\n" + code + "```\n")
            lines = []
            for prep, expr, answer in cases:
                lines += prep + [f">>> {expr}", json.dumps(answer)]
            with open(os.path.join(d, "t.doctest"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            ok, passed, total, reason = check_problem(path)
        self.assertEqual((passed, reason), (total, ""), (name, reason))

    def strings(self, rng, n, alphabet="aAbB1 ,\t-x"):
        return ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8))) for _ in range(n)]

    def pure(self, name, f, args_list):
        self.run_cases(name, [([], f"{name}({', '.join(lit(a) for a in args)})", f(*args)) for args in args_list])

    def test_character_tests_and_case(self):
        ss = self.strings(random.Random(0), 40)
        for name, f in [("lower", str.lower), ("upper", str.upper), ("swapcase", str.swapcase),
                        ("isalpha", str.isalpha), ("isdigit", str.isdigit), ("isupper", str.isupper),
                        ("islower", str.islower), ("strip", str.strip), ("words", str.split)]:
            with self.subTest(name=name):
                self.pure(name, f, [[s] for s in ss])

    def test_strings_with_a_pattern(self):
        rng = random.Random(1)
        ss = self.strings(rng, 40, "ab,")
        pats = [p for p in self.strings(rng, 60, "ab,") if p][:40]
        pairs = list(zip(ss, pats))
        for name, f in [("split", str.split), ("startswith", str.startswith), ("endswith", str.endswith),
                        ("count", str.count)]:
            with self.subTest(name=name):
                self.pure(name, f, [list(p) for p in pairs])
        with self.subTest(name="replace"):
            self.pure("replace", str.replace, [[s, p, "XY"] for s, p in pairs])
        with self.subTest(name="index"):
            self.pure("index", str.index, [[s, p] for s, p in pairs if p in s])
        with self.subTest(name="index_not_found"):         # Python は ValueError。lib は -1
            self.pure("index", lambda s, p: -1, [["abc", "z"]])

    def test_join_and_lists(self):
        rng = random.Random(2)
        self.pure("join", lambda sep, xs: sep.join(xs),
                  [[sep, self.strings(rng, rng.randint(0, 4))] for sep in ("", "-", ", ")] * 4)
        lists = [[rng.randint(-3, 3) for _ in range(rng.randint(0, 6))] for _ in range(30)]
        self.pure("any", any, [[x] for x in lists])
        self.pure("all", all, [[x] for x in lists])
        self.pure("count", lambda xs, x: xs.count(x), [[x, rng.randint(-3, 3)] for x in lists])
        self.pure("index", lambda xs, x: xs.index(x), [[x, x[0]] for x in lists if x])
        # 変更する関数: 呼んだあとの変数を見る
        for name, f in [("sort", list.sort), ("reverse", list.reverse)]:
            cases = []
            for x in lists:
                y = list(x); f(y)
                cases.append(([f"xs = {lit(x)}", f"{name}(xs)"], "xs", y))
            with self.subTest(name=name):
                self.run_cases(name, cases)
        cases = []
        for x in lists[:12]:
            y = lists[-1 - lists.index(x)]
            cases.append(([f"xs = {lit(x)}", f"extend(xs, {lit(y)})"], "xs", x + y))
        self.run_cases("extend", cases)

    def test_slice(self):
        rng = random.Random(3)
        bound = lambda: rng.choice([None, None, -7, -3, -1, 0, 1, 2, 4, 9])
        step = lambda: rng.choice([None, 1, 2, 3, -1, -2, -3])
        seqs = [list(range(rng.randint(0, 7))) for _ in range(30)] + self.strings(rng, 30, "abcdef")
        args = [[s, bound(), bound(), step()] for s in seqs for _ in range(2)]
        self.pure("slice", lambda s, a, b, c: s[a:b:c], args)


if __name__ == "__main__":
    unittest.main()
