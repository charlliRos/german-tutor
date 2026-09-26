"""The "my answer was right too" option: on its own line, offered on warm-up words (also in the repeat rounds),
verbs and grammar; a claim counts, and is logged next to the check's verdict."""
import tempfile
import unittest
from unittest import mock

from app import attempts, grammar, warmup
from app.answers import WRONG, Check
from app.content import Word
from app.ui import console
from tests.test_flows import make_ctx

WORD = Word("w1", "daily", "aufwachen", ["to wake up"], "verb")


class Claims(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        for target in ("app.ui.clear", "app.warmup.sfx.play", "app.grammar.sfx.play"):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def result(self, second_chance, key):
        with mock.patch("app.ui.timed_keys", return_value=key), console.capture() as out:
            outcome = warmup._result(self.ctx, WORD, "to awake", Check(WRONG), second_chance, "", "de2en")
        return outcome, " ".join(out.get().split())

    def test_the_option_has_its_own_line(self):
        outcome, text = self.result(False, "")
        self.assertIn("[o] My answer was right too", text)
        self.assertEqual(outcome, WRONG)

    def test_offered_in_the_repeat_rounds_too(self):
        outcome, text = self.result(True, "o")
        self.assertIn("My answer was right too", text)
        self.assertEqual(outcome, warmup.ONCE_MORE)

    def test_a_claim_in_the_repeat_round_ends_the_repeats_and_is_logged(self):
        with mock.patch("app.warmup.quiz", side_effect=[warmup.ONCE_MORE]) as quiz, console.capture():
            warmup.repeat_until_right(self.ctx, [WORD])
        self.assertEqual(quiz.call_count, 1)  # not asked again
        (event,) = [e for e in attempts.read(self.ctx.profile) if e["type"] == "attempt"]
        self.assertTrue(event["claimed_correct"])

    def test_not_offered_for_a_wrong_article(self):
        with mock.patch("app.ui.timed_keys", return_value=""), console.capture() as out:
            warmup._result(self.ctx, WORD, "der Brücke", Check(WRONG, "wrong article", overridable=False), False, "", "en2de")
        self.assertNotIn("My answer was right too", out.get())

    def test_grammar_word_order_can_be_claimed(self):
        item = grammar.Item("order", "Heute gehe ich ins Kino.", "Heute … [ gehe / ich / ins Kino ]", "Heute gehe ich ins Kino.")
        with mock.patch("app.ui.ask_answer", return_value="Ich gehe heute ins Kino."), \
                mock.patch("app.ui.timed_keys", return_value="o"), mock.patch("app.grammar.hear"), console.capture() as out:
            outcome = grammar.question(self.ctx, item, "Grammar 1 of 1")
        self.assertEqual(outcome, "correct")
        self.assertIn("My answer was right too", out.get())


if __name__ == "__main__":
    unittest.main()
