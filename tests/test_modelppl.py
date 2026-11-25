"""modelppl のテスト。モデルは使わず、文字数に比例する偽の採点関数で確かめる。"""

import contextlib
import csv
import io
import math
import os
import tempfile
import unittest

from kolang.modelppl import measure, summarize, format_report, main
from kolang.cli import main as cli_main
from kolang.snippet import SNIPPETS


def fake_scorer(text):
    return 2.0 * len(text), len(text.split()) + 1      # NLL は文字数の 2 倍、トークンは語数 + 1


class TestModelPpl(unittest.TestCase):
    def test_measure(self):
        rs = measure(["pylike", "jalike"], fake_scorer, ["assign", "sequence"])
        self.assertEqual(len(rs), 4)
        for r in rs:
            self.assertIsNone(r.error)
            self.assertEqual(r.chars, len(r.text))
            self.assertAlmostEqual(r.nll, 2.0 * r.chars)
            self.assertAlmostEqual(r.ppl, math.exp(r.nll / r.tokens))

    def test_unknown_snippet(self):
        with self.assertRaises(KeyError):
            measure(["pylike"], fake_scorer, ["nope"])

    def test_summary_uses_common_snippets(self):
        syns = ["pylike", "jalike"]
        rs = measure(syns, fake_scorer, list(SNIPPETS))
        rows = summarize(rs, syns)
        self.assertEqual(rows[0]["snippets"], rows[1]["snippets"])
        self.assertIn("NLL", format_report(rs, syns))

    def test_main(self):
        self.assertEqual(main(["--no-csv", "pylike", "--snippets", "assign"], scorer=fake_scorer), 0)
        self.assertEqual(main(["--no-csv", "--snippets", "nope", "pylike"], scorer=fake_scorer), 2)
        self.assertEqual(main(["--no-csv"], scorer=fake_scorer), 2)       # SYNTAX が要る

    def rows(self, path):
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_csv_columns_and_upsert(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "modelppl.csv")
            self.assertEqual(main(["--csv", path, "-m", "A", "pylike", "jalike"], scorer=fake_scorer), 0)
            rows = self.rows(path)
            self.assertEqual(list(rows[0]), ["model", "syntax", "NLL", "tokens", "PPL", "bpc"])
            self.assertEqual([(r["model"], r["syntax"]) for r in rows], [("A", "pylike"), ("A", "jalike")])
            r = rows[0]
            self.assertAlmostEqual(float(r["PPL"]), math.exp(float(r["NLL"]) / int(r["tokens"])), places=2)
            # 別モデルは行が増え、同じ (model, syntax) は置き換わる
            main(["--csv", path, "-m", "B", "pylike"], scorer=fake_scorer)
            main(["--csv", path, "-m", "A", "pylike"], scorer=fake_scorer)
            self.assertEqual([(r["model"], r["syntax"]) for r in self.rows(path)],
                             [("A", "pylike"), ("A", "jalike"), ("B", "pylike")])

    def test_csv_old_format_is_migrated(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "m.csv")
            with open(path, "w", encoding="utf-8") as f:
                f.write("syntax,NLL,tok,char,PPL,bpc\npylike,1.0,2,3,4.0,5.0\n")
            main(["--csv", path, "-m", "X", "jalike"], scorer=fake_scorer)
            rows = self.rows(path)
            self.assertEqual([(r["model"], r["syntax"], r["tokens"]) for r in rows[:1]],
                             [("Qwen/Qwen2.5-Coder-1.5B-Instruct", "pylike", "2")])
            self.assertEqual(rows[1]["model"], "X")

    def test_subcommand(self):
        from kolang import modelppl
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.csv")
            orig = modelppl.make_hf_scorer
            modelppl.make_hf_scorer = lambda *a, **k: fake_scorer
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = cli_main(["modelppl", "--csv", path, "pylike"])
            finally:
                modelppl.make_hf_scorer = orig
            self.assertEqual(code, 0)
            self.assertEqual([r["syntax"] for r in self.rows(path)], ["pylike"])


if __name__ == "__main__":
    unittest.main()
