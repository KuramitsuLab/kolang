import unittest

from kolang.cli import main
from kolang.kolangeval import check, evaluate, load_problems
from kolang.syntax import load_syntax


class KolangEvalTest(unittest.TestCase):
    def test_reference_passes(self):
        problems = [p for p in load_problems() if p["task_id"] in ("HumanEval/0", "HumanEval/1")]
        for name in ("pylike", "ja", "jslike"):
            self.assertTrue(all(r.ok for r in evaluate(load_syntax(name), problems)), name)

    def test_custom_solver_wrong_code_fails(self):
        p = load_problems()[0]
        r = check(p, load_syntax("pylike"), lambda prob, syn: f"def {prob['entry_point']}(a, b):\n    return True\n")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "doctest が 3 件不一致")

    def test_unparsable_code_fails(self):
        p = load_problems()[0]
        self.assertFalse(check(p, load_syntax("pylike"), lambda prob, syn: "def (").ok)

    def test_cli(self):
        self.assertEqual(main(["eval", "ja", "-t", "0"]), 0)


if __name__ == "__main__":
    unittest.main()


class TestModelEval(unittest.TestCase):
    """--model の部品。モデルは偽の Solver に置き換える。"""

    def test_context_from_examples(self):
        from kolang.kolangeval import build_context
        from kolang.syntax import load_syntax
        for name in ("pylike", "ja", "lisplike", "jslike"):
            ctx = build_context(load_syntax(name))
            self.assertIn("```" + name, ctx)
            self.assertIn("fizzbuzz", ctx)

    def test_context_snippet(self):
        from kolang.kolangeval import build_context
        from kolang.syntax import load_syntax
        base = build_context(load_syntax("ja"))
        ctx = build_context(load_syntax("ja"), "snippet")
        self.assertTrue(ctx.startswith(base))
        self.assertIn("# snippet: assign", ctx)
        self.assertGreater(len(ctx), len(base))

    def test_context_file(self):
        import tempfile
        from kolang.kolangeval import build_context
        from kolang.syntax import load_syntax
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("説明")
        self.assertEqual(build_context(load_syntax("ja"), f.name), "説明")

    def test_extract_code(self):
        from kolang.kolangeval import extract_code
        self.assertEqual(extract_code("先頭\n```pylike\ndef f(x):\n    return x\n```\n後ろ"), "def f(x):\n    return x\n")
        self.assertEqual(extract_code("x = 1"), "x = 1\n")

    def test_records(self):
        import json
        from kolang.kolangeval import Generation, evaluate_recorded, reference_solver
        from kolang.syntax import load_syntax
        syn = load_syntax("ja")
        ps = load_problems()[:3]
        fence = lambda p, s: "説明\n```ja\n" + reference_solver(p, s) + "```\n"
        recs = list(evaluate_recorded(syn, ps, fence, "fake"))
        self.assertEqual([r["task_id"] for r in recs], [p["task_id"] for p in ps])
        for r, p in zip(recs, ps):
            json.dumps(r, ensure_ascii=False)
            self.assertEqual(list(r), ["task_id", "model", "syntax", "prompt", "output",
                                       "input_tokens", "output_tokens", "code", "doctest", "error_message"])
            self.assertEqual((r["model"], r["syntax"], r["prompt"]), ("fake", "ja", p["prompt"]))
            self.assertTrue(r["output"].startswith("説明"))
            self.assertNotIn("```", r["code"])
            self.assertTrue(r["doctest"]["ok"])
            self.assertEqual(r["doctest"]["passed"], r["doctest"]["total"])
            self.assertIsNone(r["error_message"])
        self.assertEqual((recs[0]["input_tokens"], recs[0]["output_tokens"]), (None, None))
        counted = list(evaluate_recorded(syn, ps[:1], lambda p, s: Generation(fence(p, s), 10, 20), "fake"))[0]
        self.assertEqual((counted["input_tokens"], counted["output_tokens"]), (10, 20))
        self.assertTrue(counted["doctest"]["ok"])
        bad = list(evaluate_recorded(syn, ps[:1], lambda p, s: "ここは壊れている", "fake"))[0]
        self.assertFalse(bad["doctest"]["ok"])
        self.assertEqual(bad["output"], "ここは壊れている")
        self.assertIn("ParseError", bad["error_message"])

    def test_entry_header(self):
        from kolang.kolangeval import entry_header
        from kolang.syntax import load_syntax
        p = {"entry_point": "f", "pylike": "def g(a):\n    return a\ndef f(x, y):\n    return add(x, y)\n"}
        want = {"pylike": "def f(x, y):\n    ", "ja": "関数 f(x, y)とは『\n    ",
                "jslike": "function f(x, y) {\n    ", "lisplike": "(def f (x y) "}
        for name, head in want.items():
            self.assertEqual(entry_header(p, load_syntax(name)), head, name)
        self.assertEqual(entry_header({"entry_point": "zz", "pylike": p["pylike"]}, load_syntax("ja")), "")
        self.assertEqual(entry_header({"entry_point": "f"}, load_syntax("ja")), "")

    def test_default_output_name(self):
        from kolang.kolangeval import default_output_name
        from kolang.syntax import load_syntax
        self.assertEqual(default_output_name(load_syntax("ja"), "Qwen/Qwen2.5-Coder-1.5B-Instruct"),
                         "results/kolangeval_ja_Qwen_Qwen2.5-Coder-1.5B-Instruct.jsonl")
        self.assertEqual(default_output_name(load_syntax("ja:jslike(assign)"), "claude-haiku-5.5"),
                         "results/kolangeval_ja_jslike_assign_claude-haiku-5.5.jsonl")

    def test_default_output_name_difficulty(self):
        from kolang.kolangeval import default_output_name
        from kolang.syntax import load_syntax
        ja = load_syntax("ja")
        self.assertEqual(default_output_name(ja, "claude-haiku-5.5", [1]), "results/kolangeval_ja_claude-haiku-5.5_d1.jsonl")
        self.assertEqual(default_output_name(ja, "m", [3, 1, 1]), "results/kolangeval_ja_m_d1_3.jsonl")
        self.assertEqual(default_output_name(ja, "m", None), "results/kolangeval_ja_m.jsonl")

    def test_is_claude(self):
        from kolang.kolangeval import is_claude
        self.assertTrue(is_claude("claude-haiku-5.5"))
        self.assertFalse(is_claude("Qwen/Qwen2.5-Coder-1.5B-Instruct"))
