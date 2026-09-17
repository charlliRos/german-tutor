import unittest
from datetime import date

from app import srs
from app.answers import ALMOST, CORRECT, WRONG, check_english, check_german, normalize
from app.content import Word


def word(de, en, pos="noun", **kw):
    return Word(id="t", bank="daily", de=de, en=en, pos=pos, **kw)


class GermanAnswers(unittest.TestCase):
    bruecke = word("die Brücke", ["bridge"])

    def test_exact_and_umlaut_spelling(self):
        self.assertEqual(check_german("die Brücke", self.bruecke).outcome, CORRECT)
        self.assertEqual(check_german("DIE BRUECKE", self.bruecke).outcome, CORRECT)

    def test_missing_article_is_almost(self):
        self.assertEqual(check_german("Brücke", self.bruecke).outcome, ALMOST)

    def test_wrong_article_is_wrong(self):
        self.assertEqual(check_german("der Brücke", self.bruecke).outcome, WRONG)

    def test_typo_is_almost(self):
        self.assertEqual(check_german("die Brüke", self.bruecke).outcome, ALMOST)

    def test_reflexive_verb(self):
        freuen = word("sich freuen", ["to be happy"], pos="verb")
        self.assertEqual(check_german("freuen", freuen).outcome, ALMOST)

    def test_alternatives_and_empty(self):
        handy = word("das Handy", ["mobile phone"], de_alt=["das Mobiltelefon"])
        self.assertEqual(check_german("das Mobiltelefon", handy).outcome, CORRECT)
        self.assertEqual(check_german("", handy).outcome, WRONG)

    def test_short_words_are_not_typos(self):
        haus = word("das Haus", ["house"])
        self.assertEqual(check_german("das Maus", haus).outcome, WRONG)


class EnglishAnswers(unittest.TestCase):
    def test_prefixes_are_optional(self):
        gehen = word("gehen", ["to go", "to walk"], pos="verb")
        self.assertEqual(check_english("walk", gehen).outcome, CORRECT)
        self.assertEqual(check_english("To Go!", gehen).outcome, CORRECT)
        self.assertEqual(check_english("the house", word("das Haus", ["house"])).outcome, CORRECT)

    def test_slash_alternatives_and_typos(self):
        w = word("das Handy", ["mobile phone/cell phone"])
        self.assertEqual(check_english("cell phone", w).outcome, CORRECT)
        self.assertEqual(check_english("mobile phnoe", w).outcome, ALMOST)

    def test_normalize(self):
        self.assertEqual(normalize("  Wie geht's?  "), "wie gehts")
        self.assertEqual(normalize("E-Mail"), "email")


class SpacedRepetition(unittest.TestCase):
    today = date(2026, 1, 10)

    def test_boxes_move(self):
        s = srs.new_state()
        srs.apply_result(s, CORRECT, self.today)
        self.assertEqual((s["box"], s["due"]), (1, "2026-01-11"))
        srs.apply_result(s, CORRECT, self.today)
        self.assertEqual((s["box"], s["due"]), (2, "2026-01-13"))
        srs.apply_result(s, WRONG, self.today)
        self.assertEqual((s["box"], s["due"]), (1, "2026-01-11"))

    def test_plan_prefers_reviews_and_mixes_banks(self):
        words = {f"d{i}": Word(f"d{i}", "daily", f"w{i}", ["x"], "verb", rank=i) for i in range(10)}
        words |= {f"s{i}": Word(f"s{i}", "stem", f"s{i}", ["x"], "verb", rank=i) for i in range(10)}
        states = {"d9": {"box": 2, "due": "2026-01-01"}}
        settings = {"warmup_words": 5, "new_words_per_day": 10, "stem_share": 0.5}
        reviews, new = srs.plan_session(states, words, settings, self.today)
        self.assertEqual(reviews, ["d9"])
        self.assertEqual(new, ["d0", "d1", "s0", "s1"])


if __name__ == "__main__":
    unittest.main()
