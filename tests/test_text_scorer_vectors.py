"""The typed-answer scorer against its test vectors (tests/vectors/text_scorer.json, docs/TEXT_SCORER_SPEC.md).
The vectors are the durable part: another implementation (e.g. a no_std Rust one) must pass the same file."""
import json
import unittest
from pathlib import Path

from app.answers import OTHER_WORD, check_english, check_german, real_english, real_german
from app.content import Word

VECTORS = Path(__file__).parent / "vectors" / "text_scorer.json"


def _word(raw: dict, n: int = 0) -> Word:
    return Word(id=f"v{n}", bank="daily", de=raw["de"], en=raw["en"], pos=raw.get("pos", "other"),
                de_alt=raw.get("de_alt", []))


class TextScorerVectors(unittest.TestCase):
    def test_every_vector(self):
        cases = json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 25)
        self.assertEqual(len({c["id"] for c in cases}), len(cases), "vector ids must be unique")
        for case in cases:
            with self.subTest(case["id"]):
                word = _word(case["word"])
                bank = [word, *(_word(b, n) for n, b in enumerate(case.get("bank", []), 1))]
                if case["scorer"] == "german":
                    check = check_german(case["submitted"], word, real_german(bank))
                else:
                    check = check_english(case["submitted"], word, real_english(bank))
                self.assertEqual(check.outcome, case["verdict"], case["why"])
                if "overridable" in case:
                    self.assertEqual(check.overridable, case["overridable"])
                self.assertEqual(check.message == OTHER_WORD, case.get("other_word", False))

    def test_both_verdict_directions_are_covered(self):
        """A vector file of only 'correct' cases would pass a scorer that accepts everything."""
        cases = json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]
        for scorer in ("german", "english"):
            self.assertEqual({c["verdict"] for c in cases if c["scorer"] == scorer}, {"correct", "almost", "wrong"})


if __name__ == "__main__":
    unittest.main()
