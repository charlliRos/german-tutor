"""Claims ("my answer was right too") are collected, shown to the parent, and an accepted one teaches the word bank."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from app import attempts, claims, report
from app.answers import CORRECT, WRONG, check_english
from app.content import Content, Word
from app.profile import Profile
from app.ui import console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import review_claims  # noqa: E402

DAY = date(2026, 9, 26)


def claim(profile, item, task, response, **extra):
    attempts.note(response, WRONG, task=task)
    attempts.record(profile, DAY, item=item, item_version="v", competency="vocabulary.recognition",
                    subcompetency="daily/x", context="warmup.review", score=attempts.graded(CORRECT),
                    grader=attempts.GRADER, schedule="result", store="vocab", counted=CORRECT, claimed_correct=True, **extra)


class Review(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "vocab").mkdir()
        (self.root / "verbs").mkdir()
        self.vocab = self.root / "vocab" / "daily_test.json"
        self.vocab.write_text(json.dumps({"bank": "daily", "words": [
            {"id": "d-1", "de": "aufwachen", "en": ["to wake up"], "pos": "verb"}]}, indent=2) + "\n", encoding="utf-8")
        self.anna = Profile(self.root / "anna.json", {"name": "Anna"})
        self.ben = Profile(self.root / "ben.json", {"name": "Ben"})
        claim(self.anna, "d-1", "de2en", "to awaken")
        claim(self.ben, "d-1", "de2en", "To Awaken")
        claim(self.anna, "d-1", "en2de", "erwachen")
        patcher = mock.patch("app.claims.REVIEWED_FILE", self.root / "claims_reviewed.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_claims_are_collected_across_kids_most_frequent_first(self):
        found = claims.collect([self.anna, self.ben])
        self.assertEqual([(c.response, c.count, sorted(c.kids)) for c in found],
                         [("to awaken", 2, ["Anna", "Ben"]), ("erwachen", 1, ["Anna"])])

    def test_an_accepted_answer_is_known_from_then_on(self):
        english, german = claims.collect([self.anna, self.ben])
        self.assertTrue(claims.accept(english, vocab_dir=self.root / "vocab", verbs_dir=self.root / "verbs"))
        self.assertTrue(claims.accept(german, vocab_dir=self.root / "vocab", verbs_dir=self.root / "verbs"))
        word = json.loads(self.vocab.read_text(encoding="utf-8"))["words"][0]
        self.assertEqual((word["en"], word["de_alt"]), (["to wake up", "to awaken"], ["erwachen"]))
        self.assertEqual(check_english("to awaken", Word("d-1", "daily", "aufwachen", word["en"], "verb")).outcome, CORRECT)
        claims.accept(english, vocab_dir=self.root / "vocab", verbs_dir=self.root / "verbs")  # twice: added once
        self.assertEqual(json.loads(self.vocab.read_text(encoding="utf-8"))["words"][0]["en"].count("to awaken"), 1)

    def test_reviewed_claims_are_not_asked_again(self):
        first = claims.collect([self.anna, self.ben])[0]
        claims.save_reviewed({first.key: "rejected"})
        self.assertEqual([c.response for c in claims.collect([self.anna, self.ben])], ["erwachen"])

    def test_the_parent_report_lists_them(self):
        content = Content({"d-1": Word("d-1", "daily", "aufwachen", ["to wake up"], "verb")}, [])
        lines = report.claim_lines(self.anna, content)
        self.assertIn("aufwachen", " ".join(lines))
        self.assertIn("to awaken", " ".join(lines))

    def test_export_then_apply_decisions(self):
        out = self.root / "claims.json"
        content = Content({"d-1": Word("d-1", "daily", "aufwachen", ["to wake up"], "verb")}, [])
        with mock.patch("review_claims.Profile.list_all", return_value=[self.anna, self.ben]), \
                mock.patch("review_claims.load_content", return_value=content), \
                mock.patch("app.claims.VOCAB_DIR", self.root / "vocab"), mock.patch("app.claims.VERBS_DIR", self.root / "verbs"), \
                mock.patch("builtins.print"), \
                mock.patch("item_versions.main") as versions:
            review_claims.main(["--export", str(out)])
            rows = json.loads(out.read_text(encoding="utf-8"))
            rows[0]["decision"], rows[1]["decision"] = "accept", "reject"
            out.write_text(json.dumps(rows), encoding="utf-8")
            review_claims.main(["--apply", str(out)])
        self.assertEqual(json.loads(self.vocab.read_text(encoding="utf-8"))["words"][0]["en"], ["to wake up", "to awaken"])
        self.assertEqual(sorted(claims.load_reviewed().values()), ["accepted", "rejected"])
        versions.assert_called_once_with(["--update"])


if __name__ == "__main__":
    unittest.main()
