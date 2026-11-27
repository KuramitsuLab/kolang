import json
import os
import tempfile
import unittest

from kolang.cli import main
from kolang.problems import classify, summarize, to_csv


def rec(tid, syn, ok, err=None, code="x"):
    return {"task_id": tid, "syntax": syn, "model": "m", "code": code,
            "doctest": {"ok": ok, "passed": 0, "total": 1}, "error_message": err}


class ProblemsTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify(rec("a", "s", True)), ("", ""))
        self.assertEqual(classify(rec("a", "s", False, "ParseError: 3:4: expected x"))[0], "parse_error")
        self.assertEqual(classify(rec("a", "s", False, "NameError: name 'md5' is not defined"))[0], "name_error")
        self.assertEqual(classify(rec("a", "s", False, "doctest が 2 件不一致"))[0], "doctest_mismatch")
        self.assertEqual(classify(rec("a", "s", False, None, code=None))[0], "no_code")

    def test_summarize_and_cli(self):
        recs = [rec("HumanEval/10", "p", True), rec("HumanEval/10", "j", False, "ParseError: 1:1: expected y"),
                rec("HumanEval/2", "p", True)]
        rows = summarize(recs)
        self.assertEqual([r["task_id"] for r in rows], ["HumanEval/2", "HumanEval/10"])
        self.assertEqual(rows[1]["pass_rate"], "0.500")
        self.assertEqual(rows[1]["parse_error"], 1)
        self.assertTrue(to_csv(rows).startswith("task_id,runs"))
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "r.jsonl"), os.path.join(d, "o.csv")
            with open(src, "w") as f:
                f.write("\n".join(json.dumps(r) for r in recs))
            self.assertEqual(main(["problems", src, "-o", out]), 0)
            self.assertIn("HumanEval/10", open(out).read())


if __name__ == "__main__":
    unittest.main()
