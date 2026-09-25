"""Words that keep slipping away (leeches), capital letters, and speaking from memory."""
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

from app import attempts, srs, warmup
from app.answers import ALMOST, CORRECT, WRONG, check_german
from app.content import Word
from app.ui import console
from tests.test_flows import TODAY, make_ctx


class Parking(unittest.TestCase):
    def test_eight_misses_park_a_word_for_30_days_then_four_more(self):
        state = srs.new_state()
        day = date(2026, 1, 1)
        for n in range(1, 13):
            srs.apply_result(state, WRONG, day)
            expected = srs.PARK_DAYS if n in (8, 12) else 1
            self.assertEqual(date.fromisoformat(state["due"]) - day, timedelta(days=expected), f"miss {n}")
        self.assertEqual(state["parks"], 2)
        self.assertTrue(srs.parked(state, day + timedelta(days=5)))
        self.assertFalse(srs.parked(state, day + timedelta(days=31)))

    def test_leech(self):
        self.assertTrue(srs.is_leech({"wrong": 4, "box": 1}))
        self.assertFalse(srs.is_leech({"wrong": 3, "box": 1}))
        self.assertFalse(srs.is_leech({"wrong": 9, "box": 3}))  # learned in the end: not a leech any more

    def test_parking_rebuilds_from_the_log(self):
        """Parking is part of apply_result, so the answer log reproduces it."""
        events = [{"type": "attempt", "schedule": "result", "store": "vocab", "item": "w", "counted": WRONG,
                   "date": "2026-01-01"} for _ in range(8)]
        self.assertEqual(attempts.rebuild(events)["vocab"]["w"]["due"], "2026-01-31")


class Capitals(unittest.TestCase):
    hund = Word("n1", "daily", "der Hund", ["dog"], "noun")

    def test_lowercase_noun_is_almost_with_the_reason(self):
        check = check_german("der hund", self.hund)
        self.assertEqual(check.outcome, ALMOST)
        self.assertIn("capital", check.message)
        self.assertEqual(check_german("der Hund", self.hund).outcome, CORRECT)
        self.assertEqual(check_german("DER HUND", self.hund).outcome, CORRECT)


class LeechInTheWarmup(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        self.word = Word("w1", "daily", "die Brücke", ["bridge"], "noun", example_de="Die Brücke ist alt.",
                         example_en="The bridge is old.")

    def test_a_leech_gets_the_sentence_cue(self):
        self.ctx.profile.data["vocab"]["w1"] = {"box": 1, "wrong": 5, "due": TODAY.isoformat()}
        with mock.patch("app.warmup.gap_quiz", return_value=CORRECT) as gap, \
                mock.patch("app.warmup.quiz", return_value=CORRECT) as quiz:
            warmup.ask_word(self.ctx, self.word, "review")
        gap.assert_called_once()
        quiz.assert_not_called()

    def test_the_memory_hook_is_asked_once_and_shown_on_the_card(self):
        with mock.patch("app.ui.ask", return_value="Brücke: a brick bridge") as ask, console.capture():
            warmup.ask_hook(self.ctx, self.word)
            warmup.ask_hook(self.ctx, self.word)
        self.assertEqual(ask.call_count, 1)
        with console.capture() as out:
            console.print(warmup.word_details(self.word, warmup.hook_for(self.ctx, self.word)))
        self.assertIn("a brick bridge", out.get())


class SayBeforeSee(unittest.TestCase):
    def test_the_german_is_hidden_until_after_speaking(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ctx = make_ctx(tmp.name)
        word = Word("w1", "daily", "die Brücke", ["bridge"], "noun")
        calls = []
        with console.capture() as capture:
            with mock.patch("app.warmup.speak_and_compare", lambda ctx, text, **kw: calls.append(kw) or True):
                warmup.read_aloud(ctx, word)
        self.assertEqual(calls, [{"must_say": True, "reveal": True}])  # the German is shown after speaking
        self.assertIn("bridge", capture.get())
        self.assertNotIn("Brücke", capture.get())  # read_aloud itself never shows the German


if __name__ == "__main__":
    unittest.main()
