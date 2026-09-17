import unittest
from datetime import date

from app import srs
from app.answers import ALMOST, CORRECT, WRONG, check_english, check_german, normalize
from app.content import Word, is_duplicate


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


class Duplicates(unittest.TestCase):
    def test_same_german_different_meaning_is_kept(self):
        seen = {}
        self.assertFalse(is_duplicate(seen, "gerade", ["straight", "just"]))
        self.assertFalse(is_duplicate(seen, "gerade", ["even"]))
        self.assertTrue(is_duplicate(seen, "gerade", ["straight"]))


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
        settings = {"warmup_words": 5, "new_words_per_day": 10, "bank_shares": {"daily": 0.5, "stem": 0.5}}
        reviews, new = srs.plan_session(states, words, settings, self.today)
        self.assertEqual(reviews, ["d9"])
        self.assertEqual(sorted(new), ["d0", "d1", "s0", "s1"])

    def test_small_bank_gets_its_share_and_empty_banks_are_topped_up(self):
        words = {f"d{i}": Word(f"d{i}", "daily", f"w{i}", ["x"], "verb", rank=i) for i in range(20)}
        words |= {f"a{i}": Word(f"a{i}", "admin", f"a{i}", ["x"], "verb", rank=i) for i in range(20)}
        shares = {"daily": 0.75, "stem": 0.1, "admin": 0.25}
        picked = srs.pick_new_words({}, words, 8, shares)
        self.assertEqual(sum(w.startswith("a") for w in picked), 2)
        self.assertEqual(len(picked), 8)


class ReviewFixes(unittest.TestCase):
    def test_steady_noise_recording_does_not_crash(self):
        import numpy as np
        from app.audio import _tidy
        rate = 16000
        hum = (0.05 * np.sin(np.arange(3 * rate) * 2 * np.pi * 50 / rate)).astype(np.float32)
        self.assertGreater(_tidy(hum, rate).size, 0)
        self.assertEqual(_tidy(np.zeros(rate, np.float32), rate).size, 0)

    def test_zero_share_bank_gets_nothing_while_others_have_words(self):
        words = {f"d{i}": Word(f"d{i}", "daily", f"w{i}", ["x"], "verb", rank=i) for i in range(30)}
        words |= {f"a{i}": Word(f"a{i}", "admin", f"a{i}", ["x"], "verb", rank=i) for i in range(30)}
        picked = srs.pick_new_words({}, words, 20, {"daily": 0.5, "stem": 0.3, "admin": 0})
        self.assertTrue(all(w.startswith("d") for w in picked))
        topped_up = srs.pick_new_words({}, {k: v for k, v in words.items() if k.startswith("a")}, 3,
                                       {"daily": 1, "admin": 0})
        self.assertEqual(len(topped_up), 3)

    def test_reading_task_with_no_usable_weight(self):
        import random
        from types import SimpleNamespace
        from app.reading import _choose_task
        ctx = SimpleNamespace(settings={"reading_tasks": {"read_aloud": 1, "de2en": 0, "en2de": 0}},
                              audio=SimpleNamespace(can_speak=False), rng=random.Random(1))
        self.assertIn(_choose_task(ctx), {"de2en", "en2de"})

    def test_profiles_streak_and_names(self):
        import tempfile
        from pathlib import Path
        from app import profile as prof
        old_dir = prof.PROFILES_DIR
        prof.PROFILES_DIR = Path(tempfile.mkdtemp())
        try:
            juergen, joergen = prof.Profile.open_or_create("Jürgen"), prof.Profile.open_or_create("Jörgen")
            self.assertNotEqual(juergen.path, joergen.path)
            self.assertEqual(prof.Profile.open_or_create("jürgen").path, juergen.path)
            a, b = prof.Profile.open_or_create("???"), prof.Profile.open_or_create("!!!")
            self.assertNotEqual(a.path, b.path)
            today = date(2026, 1, 10)
            juergen.day(today)  # just looking must not count as practice
            self.assertEqual(juergen.streak(today), 0)
            juergen.count(today, words=1)
            self.assertEqual(juergen.streak(today), 1)
        finally:
            prof.PROFILES_DIR = old_dir

    def test_translating_a_skipped_unit_keeps_positions(self):
        import json
        import tempfile
        from pathlib import Path
        from app.content import load_content
        root = Path(tempfile.mkdtemp())
        (root / "vocab").mkdir()
        (root / "books").mkdir()
        units = [{"n": 1, "de": "Eins.", "en": "One."}, {"n": 2, "de": "Zwei.", "en": ""},
                 {"n": 3, "type": "summary", "en": "Meanwhile."}, {"n": 4, "de": "Vier.", "en": "Four."}]
        (root / "books" / "01_t.json").write_text(json.dumps({"id": "t", "units": units}), encoding="utf-8")
        book = load_content(root / "vocab", root / "books").books[0]
        self.assertEqual([(u.n, u.part) for u in book.units], [(1, 1), (3, 0), (4, 3)])
        self.assertEqual(book.next_unit(2).n, 3)
        self.assertEqual(book.total_parts, 3)


if __name__ == "__main__":
    unittest.main()
