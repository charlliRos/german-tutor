"""Item versions: every content edit is recorded with its tier, ids are never reused, paragraphs never renumbered."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.versions import compare, current_items, load_versions, save_versions, update

DAY1, DAY2 = date(2026, 9, 25), date(2026, 9, 26)
WORD = {"id": "d-0001", "de": "die Brücke", "de_alt": [], "en": ["bridge"], "pos": "noun", "topic": "town",
        "level": "A2", "rank": 900, "example_de": "Die Brücke ist alt.", "example_en": "The bridge is old."}
TEXT = "Plötzlich wachte sie auf. Es war halb drei. Sie überlegte, warum sie aufgewacht war."


class ContentFolder(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for sub in ("vocab", "books", "verbs"):
            (self.root / sub).mkdir()
        self.versions = self.root / "item_versions.json"
        self.write(WORD, TEXT)

    def write(self, word: dict, text: str, second: str | None = None) -> None:
        (self.root / "vocab" / "daily_test.json").write_text(json.dumps({"bank": "daily", "words": [word]}),
                                                             encoding="utf-8")
        units = [{"n": 1, "de": text, "en": "Suddenly she woke up.", "explain_en": "…", "words": []}]
        if second:
            units.append({"n": 2, "de": second, "en": "…", "explain_en": "…", "words": []})
        (self.root / "books" / "01_b.json").write_text(json.dumps({"id": "b", "units": units}), encoding="utf-8")

    def current(self) -> dict:
        return current_items(self.root / "vocab", self.root / "books", self.root / "verbs")

    def record(self, today: date) -> list:
        recorded = load_versions(self.versions)
        changes, refusals = compare(recorded, self.current())
        self.assertEqual(refusals, [])
        save_versions(update(recorded, self.current(), changes, today), self.versions)
        return changes

    def test_first_run_records_everything_as_new(self):
        self.assertEqual(sorted(self.record(DAY1)), [("b#1", "new"), ("d-0001", "new")])
        self.assertEqual(compare(load_versions(self.versions), self.current()), ([], []))

    def test_an_example_edit_is_presentation_and_a_new_meaning_is_answer(self):
        self.record(DAY1)
        self.write({**WORD, "example_de": "Die Brücke ist sehr alt."}, TEXT)
        self.assertEqual(self.record(DAY2), [("d-0001", "presentation")])
        self.write({**WORD, "example_de": "Die Brücke ist sehr alt.", "en": ["bridge", "jetty"]}, TEXT)
        self.assertEqual(self.record(DAY2), [("d-0001", "answer")])
        entry = load_versions(self.versions)["d-0001"]
        self.assertEqual(entry["v"], 3)
        self.assertEqual([h["tier"] for h in entry["history"]], ["presentation", "answer"])

    def test_a_removed_item_is_retired_not_forgotten(self):
        self.record(DAY1)
        self.write({**WORD, "id": "d-0002"}, TEXT)
        self.assertEqual(sorted(self.record(DAY2)), [("d-0001", "retired"), ("d-0002", "new")])
        self.assertEqual(load_versions(self.versions)["d-0001"]["retired"], DAY2.isoformat())

    def test_a_typo_fix_in_a_paragraph_is_fine(self):
        self.record(DAY1)
        self.write(WORD, TEXT.replace("halb drei", "halb Drei"))
        self.assertEqual(compare(load_versions(self.versions), self.current()), ([("b#1", "answer")], []))

    def test_renumbered_paragraphs_are_refused(self):
        self.record(DAY1)
        # A paragraph inserted at the front: the old first paragraph becomes number 2.
        self.write(WORD, "Ganz am Anfang stand ein neuer Absatz, den es vorher nicht gab, mit anderem Text.", TEXT)
        changes, refusals = compare(load_versions(self.versions), self.current())
        self.assertEqual(len(refusals), 1)
        self.assertIn("b#1", refusals[0])


class ShippedContent(unittest.TestCase):
    def test_item_versions_are_up_to_date(self):
        """A content edit without `python tools/item_versions.py --update` fails here."""
        changes, refusals = compare(load_versions(), current_items())
        self.assertEqual(refusals, [])
        self.assertEqual(changes, [], "run python tools/item_versions.py --update")
        self.assertGreater(len(load_versions()), 8000)  # positive control: the file was really read


if __name__ == "__main__":
    unittest.main()
