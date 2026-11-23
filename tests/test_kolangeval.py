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
