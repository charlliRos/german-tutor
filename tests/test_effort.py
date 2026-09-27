"""Effort in the warm-up: right answers in a row make it shorter; guesses and many "?" make it longer."""
import tempfile
import unittest
from unittest import mock

from app import warmup
from app.answers import CORRECT, WRONG, looks_random
from app.ui import console
from tests.test_flows import make_ctx


class Guesses(unittest.TestCase):
    def test_keyboard_mashing_and_lazy_answers_are_guesses(self):
        for answer in ("asdf", "sdfghj", "xxxx", "qwrtz", "k", "dog"):
            self.assertTrue(looks_random(answer, "der Hund" if answer != "dog" else "the house", cue="dog"), answer)

    def test_honest_mistakes_are_not_guesses(self):
        for answer, expected in (("der Hunt", "der Hund"), ("die Katze", "der Hund"), ("schwer", "leicht"),
                                 ("house", "the dog"), ("tv", "der Fernseher"), ("", "der Hund"),
                                 ("100", "hundred"), ("die Großstadt", "das Dorf"), ("das Fitnessstudio", "das Kino"),
                                 ("die SMS", "der Brief"), ("bzw.", "oder"), ("shh", "quiet"), ("Pst!", "Ruhe")):
            self.assertFalse(looks_random(answer, expected, cue="dog"), answer)
        # A word from the word list is an honest try, even when it looks like mashing.
        self.assertFalse(looks_random("Wert", "der Preis", real=frozenset({"wert", "der wert"})))
        self.assertTrue(looks_random("wert", "der Preis"))


class Effort(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        for target, value in (("app.ui.clear", lambda: None), ("app.ui.keys", lambda options: ""),
                              ("app.ui.pause", lambda *a, **k: None), ("app.warmup.show_card", lambda *a: None),
                              ("app.warmup.hear", lambda *a, **k: None),
                              ("app.warmup.repeat_until_right", lambda ctx, words: None)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_warmup(self, answer):
        """answer(n, word, kind) -> (outcome, skipped, guessed) for the n-th question."""
        asked = []

        def ask_word(ctx, word, kind, second_chance=False):
            outcome, skipped, guessed = answer(len(asked), word, kind)
            asked.append((word.id, kind))
            warmup.LAST_TRY.update(skipped=skipped, guessed=guessed)
            return outcome

        with mock.patch("app.warmup.ask_word", ask_word), console.capture():
            warmup.run_warmup(self.ctx)
        return asked

    def test_a_guess_brings_the_word_back_once(self):
        asked = self.run_warmup(lambda n, word, kind: (WRONG, False, n == 0))
        first = asked[0][0]
        self.assertEqual([k for w, k in asked if w == first], [asked[0][1], "again"])
        self.assertEqual(sum(k == "again" for _, k in asked), 1)  # a guess on the "again" question isn't doubled

    def test_three_skips_in_a_row_bring_the_word_back(self):
        asked = self.run_warmup(lambda n, word, kind: (WRONG, n < 3, False))
        self.assertEqual(sum(k == "again" for _, k in asked), 1)  # only the third "?" in a row
        self.assertIn((asked[2][0], "again"), asked)

    def test_quitting_on_the_look_again_screen_never_asks_the_word_twice(self):
        from app import resume
        from app.ui import QuitSession

        def keys(options):
            if "I've got it" in options.values():
                raise QuitSession
            return ""

        with mock.patch("app.ui.keys", keys), self.assertRaises(QuitSession):
            self.run_warmup(lambda n, word, kind: (WRONG, n < 3, False))
        mark = resume.part(self.ctx, "warmup")
        queued = [w for w, _ in mark["queue"]]
        self.assertEqual(self.ctx.profile.day(self.ctx.today)["words"], 3)  # three answers, counted once
        self.assertEqual(mark["queue_total"] - len(mark["queue"]), 3)       # the bookmark is past all three
        self.assertEqual([k for _, k in mark["queue"]].count("again"), 1)   # and the "again" question is kept
        self.assertEqual(len(queued), len(set(queued)))                     # no word comes twice

    def test_a_missed_again_question_neither_repeats_twice_nor_counts_twice(self):
        repeats = []
        with mock.patch("app.warmup.repeat_until_right", lambda ctx, words: repeats.extend(w.id for w in words)):
            asked = self.run_warmup(lambda n, word, kind: (WRONG, False, n == 0))
        first = asked[0][0]
        self.assertEqual(repeats.count(first), 1)
        self.assertEqual(self.ctx.profile.data["vocab"][first]["wrong"], 1)  # the "again" miss doesn't add one

    def test_right_in_a_row_drops_practice_questions(self):
        queue = [("a", "review"), ("b", "practice"), ("c", "new"), ("d", "practice"), ("e", "review")]
        self.assertTrue(warmup._drop_practice(queue))
        self.assertEqual([w for w, _ in queue], ["a", "b", "c", "e"])  # the last "strengthen" question goes
        self.assertFalse(warmup._drop_practice([("a", "review")]))
        # A whole warm-up of words to strengthen, all right: every fifth answer takes one away.
        for wid in self.ctx.content.words:
            self.ctx.profile.data["vocab"][wid] = {"box": 3, "due": "2099-01-01", "last": "2026-01-01",
                                                   "seen": 3, "right": 3, "wrong": 0}
        asked = self.run_warmup(lambda n, word, kind: (CORRECT, False, False))
        practice = len(self.ctx.content.words)
        self.assertLess(len(asked), practice)
        self.assertGreaterEqual(len(asked), practice - practice // warmup.STREAK - 1)


if __name__ == "__main__":
    unittest.main()
