"""The OLR export (tools/export_olr.py): stable ids, known competencies, provenance, and the answer log mapped
onto OLR's score kinds."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from app import attempts
from app.profile import Profile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import export_olr  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class ExportContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        with mock.patch("builtins.print"):
            export_olr.main(["--out", cls.tmp.name])
        cls.out = Path(cls.tmp.name)
        cls.items = read_jsonl(cls.out / "items.jsonl")
        cls.books = read_jsonl(cls.out / "books.jsonl")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ids_are_unique_and_competencies_known(self):
        ids = [i["id"] for i in self.items]
        self.assertGreater(len(ids), 15000)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({i["competency"] for i in self.items} - set(attempts.COMPETENCIES), set())

    def test_exam_questions_are_choice_items_with_a_valid_key(self):
        exam = [i for i in self.items if i["competency"] in ("exam.reading", "exam.listening")]
        for item in exam:
            self.assertEqual(item["key"]["scoring"], "exact_option")
            self.assertIn(item["key"]["option"], [o["id"] for o in item["options"]], item["id"])

    def test_gender_questions_use_olrs_built_in_choice_scorer(self):
        genders = [i for i in self.items if i["competency"] == "grammar.noun_gender"]
        self.assertTrue(genders)
        for item in genders:
            self.assertEqual(item["key"]["scoring"], "exact_option")
            self.assertIn(item["key"]["option"], [o["id"] for o in item["options"]])

    def test_every_book_says_why_it_is_public_domain(self):
        classics = [b for b in self.books if b["rights"].get("basis") != "written for this app"]
        self.assertEqual(len(classics), 10)
        for book in classics:
            rights = book["rights"]
            self.assertTrue(rights["source_edition"], book["id"])
            self.assertIsInstance(rights["author_died"], int, book["id"])
            self.assertIn("ID", rights["life_plus_70_jurisdictions"])
            paragraphs = [u for u in book["units"] if u["kind"] == "paragraph"]
            self.assertTrue(all(u["id"] == f"{book['id']}#{u['n']}" for u in paragraphs))

    def test_rights_dates(self):
        self.assertEqual(export_olr.rights({"author_died": 1924, "year": 1915}, date(2026, 9, 25))
                         ["us_public_domain_now"], True)
        late = export_olr.rights({"author_died": 1935, "year": 1931}, date(2026, 9, 25))
        self.assertEqual((late["public_domain_now"], late["us_public_domain_now"], late["us_public_domain_from"]),
                         (True, False, "2027-01-01"))
        self.assertFalse(export_olr.rights({"author_died": 1960, "year": 1950}, date(2026, 9, 25))["public_domain_now"])


class ExportAnswers(unittest.TestCase):
    def test_score_kinds_map_onto_olrs_closed_union(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Profile(Path(tmp) / "kid.json", {"name": "Kid"})
            day = date(2026, 9, 25)
            common = {"item_version": "x", "competency": "vocabulary.production", "subcompetency": "daily/x",
                      "context": "test"}
            attempts.note("gut", "correct", task="en2de")
            attempts.record(profile, day, item="d-1", score=attempts.graded("correct"), grader=attempts.GRADER, **common)
            attempts.note("Satz", task="de2en")
            attempts.record(profile, day, item="b#1", score=attempts.self_graded("nailed it"), grader=attempts.SELF,
                            **common)
            attempts.record(profile, day, item="b#1", score=attempts.no_response("skipped"), grader=attempts.GRADER,
                            **common)
            attempts.record(profile, day, item="d-1|grammar.article", score=attempts.right_or_wrong(False),
                            grader=attempts.GRADER, **common)
            exported = [export_olr.export_attempt(e) for e in attempts.read(profile) if e["type"] == "attempt"]
        self.assertEqual([next(iter(e["score"] or {"unmapped": 0})) for e in exported],
                         ["Polytomous", "Estimated", "unmapped", "Dichotomous"])
        # "Didn't answer" is left unmapped with the reason, never turned into a wrong answer.
        self.assertIsNone(exported[2]["score"])
        self.assertEqual(exported[2]["unmapped"]["reason"], "skipped")
        self.assertEqual(exported[0]["item"], "d-1.en2de")
        self.assertEqual(exported[1]["item"], "b#1")
        self.assertEqual(exported[1]["score"]["Estimated"]["grader"], attempts.SELF)
        self.assertTrue(exported[1]["score"]["Estimated"]["needs_review"])


if __name__ == "__main__":
    unittest.main()
