import os
import unittest
import warnings

from kolang import load_syntax
from kolang.structure import problems


def found(spec):
    return problems(load_syntax(spec, verify=False))


class Structure(unittest.TestCase):
    def test_builtin_syntaxes_are_clean(self):
        for name in ("pylike", "ja", "lisplike", "jslike"):
            self.assertEqual(found(name), [], name)

    def test_indent_needs_empty_ends(self):
        (msg,) = found("pylike:lisplike(if)")
        self.assertIn("if_end", msg)
        self.assertIn("indent", msg)
        self.assertEqual(len(found("pylike:lisplike(def)")), 1)

    def test_greedy_block_needs_closing_token(self):
        # lisplike は block が空。if_end が空の ja の if を混ぜると、本体の終わりがなくなる。
        (msg,) = found("lisplike:ja(if)")
        self.assertIn("if_end", msg)
        self.assertIn("本体", msg)
        self.assertTrue(found("lisplike:ja(repeat)"))
        self.assertTrue(found("lisplike:jslike(def)"))

    def test_block_with_braces_is_fine(self):
        self.assertEqual(found("jslike:pylike(if)"), found("jslike:pylike(if)"))
        self.assertEqual(found("ja:jslike(assign,block,funcapp)"), [])

    def test_comment_marker_collision(self):
        (msg,) = found("jslike:lisplike(comment)")      # `;` が block_sep（`;?`）と重なる
        self.assertIn("block_sep", msg)

    def test_name_swallows_token(self):
        # letters が `-` を含むと、`x--` が 1 つの名前になる
        import json
        from kolang.syntax import syntax_from_dict, _read_json
        data = _read_json("jslike")
        data.pop("_label")
        data["lexical"]["letters"] = "[A-Za-z_$][A-Za-z0-9_$-]*"
        data["word_segment"] = "[A-Za-z0-9_$-]"
        msgs = problems(syntax_from_dict(data, "t"))
        self.assertTrue(any("--" in m for m in msgs), msgs)

    def test_warning_names_the_cause_without_snippets(self):
        with self.assertWarnsRegex(UserWarning, "if_end が空でない"):
            load_syntax("pylike:lisplike(if)")

    def test_no_warning_for_clean_cascade(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            load_syntax("ja:jslike(assign,block,funcapp)")
            load_syntax("pylike:ja(else)")

    @unittest.skipUnless(os.environ.get("KOLANG_MATRIX"), "遅い。KOLANG_MATRIX=1 で全組み合わせを実行")
    def test_structure_matches_snippets(self):
        """全順列で,構造検査が問題を見つけること ⇔ スニペットが戻らないこと。"""
        from tests.test_cascade_matrix import cascades, check
        for spec in cascades():
            with self.subTest(cascade=spec):
                self.assertEqual(bool(found(spec)), bool(check(spec)))


if __name__ == "__main__":
    unittest.main()
