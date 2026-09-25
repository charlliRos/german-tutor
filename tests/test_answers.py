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

    SETTINGS = {"bank_shares": {"daily": 0.5, "stem": 0.5}, "warmup_start": 10, "warmup_max": 200,
                "warmup_growth": 0.52, "new_word_share": 0.25, "min_new_words": 3}

    def test_warmup_fits_the_time_budget(self):
        self.assertEqual(srs.warmup_size(self.SETTINGS, 25), 45)          # 15 min at 20 s a question
        self.assertEqual(srs.warmup_size(self.SETTINGS, 25, 10.0), 90)    # a fast kid gets more
        self.assertEqual(srs.warmup_size(self.SETTINGS, 5), 10)           # never under warmup_start
        self.assertEqual(srs.warmup_size(self.SETTINGS, 300, 5.0), 200)   # never over warmup_max
        saturday, monday = date(2026, 9, 26), date(2026, 9, 28)
        budget = {"session_minutes": {"weekday": 25, "weekend": 40}}
        self.assertEqual((srs.session_minutes(budget, {}, monday), srs.session_minutes(budget, {}, saturday)), (25, 40))
        self.assertEqual(srs.session_minutes(budget, {"session_minutes": 15}, saturday), 15)

    def test_due_words_that_dont_fit_wait_and_are_counted(self):
        words = {f"d{i}": Word(f"d{i}", "daily", f"w{i}", ["x"], "verb", rank=i) for i in range(100)}
        states = {f"d{i}": {"box": 2, "due": "2026-01-01", "last": "2025-12-29"} for i in range(80)}
        plan = srs.plan_session(states, words, self.SETTINGS, self.today, size=45, new_allowed=10)
        self.assertEqual((len(plan.reviews), len(plan.new), plan.waiting), (45, 0, 35))

    def test_plan_mixes_new_reviews_and_practice(self):
        words = {f"d{i}": Word(f"d{i}", "daily", f"w{i}", ["x"], "verb", rank=i) for i in range(30)}
        words |= {f"s{i}": Word(f"s{i}", "stem", f"s{i}", ["x"], "verb", rank=i) for i in range(30)}
        # Day 1: nothing started, so the whole warm-up is new words.
        plan = srs.plan_session({}, words, self.SETTINGS, self.today, size=10, new_allowed=3)
        self.assertEqual((len(plan.new), len(plan.reviews), len(plan.practice)), (10, 0, 0))
        # Later: 12 due, 5 started but not due, room for 10 -> the reviews fill it: no new words today.
        states = {f"d{i}": {"box": 1, "due": f"2026-01-0{1 + i % 9}", "last": "2026-01-01"} for i in range(12)}
        states |= {f"s{i}": {"box": 2, "due": "2026-02-01", "last": "2026-01-05"} for i in range(5)}
        plan = srs.plan_session(states, words, self.SETTINGS, self.today, size=10, new_allowed=3)
        self.assertEqual((len(plan.new), len(plan.reviews), len(plan.practice)), (0, 10, 0))
        # Room for 14: 12 reviews, then new words take what is left (2 of the 3 allowed).
        plan = srs.plan_session(states, words, self.SETTINGS, self.today, size=14, new_allowed=3)
        self.assertEqual((len(plan.new), len(plan.reviews), len(plan.practice)), (2, 12, 0))
        self.assertTrue(set(plan.new).isdisjoint(states))
        # Extra practice later the same day: due words, then weakest started words, then (only because
        # too few words have been started yet) topped up with new words to fill the warm-up.
        plan = srs.plan_session(states, words, self.SETTINGS, self.today, size=20, new_allowed=0)
        self.assertEqual((len(plan.new), len(plan.reviews), len(plan.practice)), (3, 12, 5))
        plan = srs.plan_session(states, words, self.SETTINGS, self.today, size=15, new_allowed=0)
        self.assertEqual((len(plan.new), len(plan.reviews), len(plan.practice)), (0, 12, 3))

    def test_the_goal_caps_the_level_and_topics_go_first(self):
        from app import goals
        words = {f"w{i}": Word(f"w{i}", "daily", f"w{i}", ["x"], "verb", rank=i,
                               level="A1" if i < 50 else "B2", topic="sport" if i % 10 == 9 else "basics")
                 for i in range(1000)}
        allowed = goals.allowed_words(words, {"target": "A2"})
        self.assertEqual(len(allowed), 50 + 200)  # its levels, plus the next 200 most common words
        plan = srs.plan_session({}, words, self.SETTINGS, self.today, size=10, new_allowed=10,
                                allowed=allowed, topics=("sport",))
        self.assertEqual(plan.new[:5], ["w9", "w19", "w29", "w39", "w49"])  # sport first, among common words
        far = {"w999": Word("w999", "daily", "x", ["x"], "verb", rank=999, topic="sport")}
        plan = srs.plan_session({}, words | far, self.SETTINGS, self.today, size=3, new_allowed=3, topics=("sport",))
        self.assertNotIn("w999", plan.new)  # a rare favourite-topic word doesn't jump the queue
        self.assertIsNone(goals.allowed_words(words, {"target": "C1"}))
        self.assertEqual(goals.settings_for({"bank_shares": {"daily": 1}}, {"target": "A2"})["bank_shares"]["daily"], 0.9)

    def test_new_words_per_day_are_capped(self):
        self.assertEqual(srs.new_word_cap(self.SETTINGS, 10), 3)
        self.assertEqual(srs.new_word_cap(self.SETTINGS, 40), 10)
        self.assertEqual(srs.new_word_cap(self.SETTINGS, 200), 15)  # not 50

    def test_a_year_of_practice_keeps_the_backlog_small(self):
        """Simulated daily warm-ups (right 85% of the time): due words don't pile up unreviewed."""
        import random
        from datetime import timedelta
        from app.config import DEFAULTS
        rng = random.Random(7)
        # A bank as big as the real one (the old scheduler left ~7,000 words overdue after a year here).
        words = {f"d{i}": Word(f"d{i}", "daily", f"w{i}", ["x"], "verb", rank=i) for i in range(9000)}
        settings = {**DEFAULTS, "bank_shares": {"daily": 1.0}}
        states: dict = {}
        day = self.today
        for n in range(365):
            size = srs.warmup_size(settings, 25)
            plan = srs.plan_session(states, words, settings, day, size, srs.new_word_cap(settings, size))
            for wid in plan.new + plan.reviews:
                srs.apply_result(states.setdefault(wid, srs.new_state()), CORRECT if rng.random() < 0.85 else WRONG, day)
            day += timedelta(days=1)
        overdue = sum(1 for s in states.values() if s["due"] and s["due"] < day.isoformat())
        self.assertLess(overdue, 2 * srs.warmup_size(settings, 25))  # at most ~a day's reviews wait, never a pile
        self.assertGreater(len(states), 1300)  # positive control: ~1,500 words in a year at 25 min a day

    def test_practice_does_not_promote_but_a_miss_demotes(self):
        s = {"box": 3, "due": "2026-02-01"}
        srs.apply_practice(s, CORRECT, self.today)
        self.assertEqual((s["box"], s["due"]), (3, "2026-02-01"))
        srs.apply_practice(s, WRONG, self.today)
        self.assertEqual((s["box"], s["due"]), (1, "2026-01-11"))

    def test_small_bank_gets_its_share_and_empty_banks_are_topped_up(self):
        words = {f"d{i}": Word(f"d{i}", "daily", f"w{i}", ["x"], "verb", rank=i) for i in range(20)}
        words |= {f"a{i}": Word(f"a{i}", "admin", f"a{i}", ["x"], "verb", rank=i) for i in range(20)}
        shares = {"daily": 0.75, "stem": 0.1, "admin": 0.25}
        picked = srs.pick_new_words({}, words, 8, shares)
        self.assertEqual(sum(w.startswith("a") for w in picked), 2)
        self.assertEqual(len(picked), 8)


class UxFixes(unittest.TestCase):
    def test_missing_umlaut_is_almost_with_hint(self):
        tuer = word("die Tür", ["door"])
        for answer in ("die Tur", "Tur"):
            check = check_german(answer, tuer)
            self.assertEqual(check.outcome, ALMOST)
            self.assertIn("ue", check.message)
        self.assertEqual(check_german("die Tuer", tuer).outcome, CORRECT)
        self.assertEqual(check_german("schon", word("schön", ["beautiful"], pos="adj")).outcome, ALMOST)
        wrong_article = check_german("der Tür", tuer)
        self.assertEqual(wrong_article.outcome, WRONG)
        self.assertFalse(wrong_article.overridable)
        self.assertFalse(check_german("", tuer).overridable)

    def test_multiline_keeps_single_blank_lines(self):
        from unittest import mock
        from app import ui
        typed = iter(["She woke up.", "", "It was late.", "", ""])
        with mock.patch.object(ui, "_read", lambda prompt, *a: next(typed)):
            self.assertEqual(ui.ask_multiline("x"), "She woke up.\nIt was late.")

    def test_streak_counts_finished_work_only(self):
        import tempfile
        from pathlib import Path
        from app import profile as prof
        p = prof.Profile(Path(tempfile.mkdtemp()) / "t.json", {})
        today = date(2026, 1, 10)
        p.count(today, words=3, new=2)
        self.assertEqual(p.streak(today), 0)
        p.count(today, warmups=1)
        self.assertEqual((p.streak(today), p.practice_days(today), p.practice_days(date(2026, 1, 11))), (1, 0, 1))


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

    def test_look_back_task_changes_and_survives_zero_weights(self):
        import random
        from types import SimpleNamespace
        from app.reading import _review_task
        ctx = SimpleNamespace(settings={"reading_tasks": {"read_aloud": 1, "de2en": 1, "en2de": 1}},
                              audio=SimpleNamespace(can_speak=True), rng=random.Random(1))
        self.assertTrue(all(_review_task(ctx, "en2de") != "en2de" for _ in range(20)))
        self.assertIn("dictation", {_review_task(ctx, "") for _ in range(40)})  # added even if config.json lacks it
        ctx.settings["reading_tasks"] = {"read_aloud": 0, "de2en": 0, "en2de": 0, "dictation": 0, "shadow": 0}
        self.assertEqual(_review_task(ctx, "de2en"), "de2en")
        ctx.audio.can_speak = False
        ctx.settings["reading_tasks"] = {"dictation": 1}
        self.assertNotEqual(_review_task(ctx, ""), "dictation")  # no voice, no listening

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
            juergen.count(today, units=1)
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
