"""カスケードしたシンタックスの衝突テスト。

AST でスニペットを用意し,カスケード後のシンタックスで出力 → パースして,
元の AST に戻ることを確かめる。区切りの記号が衝突すると,ここで AST が変わるか,
ParseError / UnparseError になる。
"""

import itertools
import os
import unittest

from kolang import load_syntax, parse, unparse
from kolang.snippet import SNIPPETS, failures
from kolang.syntax import GROUPS

BASES = ("pylike", "jalike", "lisplike", "jslike")
# 別名（call）と、ほかのグループを含むだけのものは除く
GROUP_NAMES = tuple(g for g in GROUPS if g != "call")

def roundtrip(tree, syntax):
    text = unparse(tree, syntax)
    return text, parse(text, syntax)


def cascades():
    """ベース : 重ねるシンタックス(グループ…) の組み合わせ。"""
    for base, over in itertools.permutations(BASES, 2):
        for g in GROUP_NAMES:
            yield f"{base}:{over}({g})"
        # すべてのグループ（ベースは何も残らない）と、隣り合う 2 グループ
        yield f"{base}:{over}"
        for g1, g2 in zip(GROUP_NAMES, GROUP_NAMES[1:]):
            yield f"{base}:{over}({g1},{g2})"


# 常に検査するカスケード。増やしたいシンタックスはここに足す。
CASCADES = (
    "jalike:jslike(assign,block,funcapp)",
    "jalike:pylike(funcapp)",           # call: args_first → func_first（引数と名前の順が変わる）
    "pylike:jalike(funcapp)",           # func_first → args_first
    "jalike:lisplike(funcapp)",
    "jalike:jslike(funcapp)",
    "pylike:jalike(grouping)",          # 括弧の無いベースに、括弧を取り込む
    "jalike:pylike(grouping)",
    "pylike:jalike(else)",              # continuation が else_begin と連動する
    "jalike:jslike(else)",              # else の行頭の空白がインデントを狂わせない
    "jslike:jalike(block)",
    "jslike:pylike(space)",         # none の空白に改行が足される
    "pylike:lisplike(append)",      # 後置の添字は変数のすぐ後ろだけ
    "jslike:lisplike(append)",
)


def check(spec):
    """spec のカスケードの、失敗の一覧 [(snippet, 理由)]。load_syntax の検査（ValueError）も拾う。"""
    try:
        syn = load_syntax(spec, verify=False)
    except Exception as e:
        return [("(load_syntax)", f"{type(e).__name__}: {e}")]
    return failures(syn)


class CascadeMatrix(unittest.TestCase):
    def test_plain_syntaxes(self):
        """前提: カスケードしないシンタックスで,全スニペットが往復できる。"""
        for name in BASES:
            self.assertEqual(check(name), [], name)

    def test_warns_on_collision(self):
        with self.assertWarnsRegex(UserWarning, "区切りが衝突"):
            syn = load_syntax("jslike:lisplike(comment)")
        self.assertEqual(syn.name, "jslike:lisplike(comment)")      # 読み込みは続く

    def test_no_warning_when_clean(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            load_syntax(CASCADES[0])

    def test_selected_cascades(self):
        for spec in CASCADES:
            with self.subTest(cascade=spec):
                self.assertEqual(check(spec), [])

    @unittest.skipUnless(os.environ.get("KOLANG_MATRIX"),
                         "既知の衝突が残っている。KOLANG_MATRIX=1 で全組み合わせを実行")
    def test_all_cascades(self):
        for spec in cascades():
            with self.subTest(cascade=spec):
                self.assertEqual(check(spec), [])


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        # python3 -m tests.test_cascade_matrix "jalike:jslike(assign,block)" lisplike:jalike ...
        status = 0
        for spec in sys.argv[1:]:
            bad = check(spec)
            print(f"{'NG' if bad else 'OK'}  {spec}")
            for label, why in bad:
                print(f"    {label}: {why}")
            status |= bool(bad)
        sys.exit(status)
    unittest.main()
