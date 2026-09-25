"""Placement: bands answered well seed their words at box 2 (checked once over two weeks); it stops when
words get too hard; the answer log reproduces the seed."""
import tempfile
import unittest
from datetime import date
from unittest import mock

from app import attempts, placement, srs
from app.answers import CORRECT, WRONG
from app.content import Content, Word
from app.ui import console
from tests.test_flows import TODAY, make_ctx


def ctx_with_bank(tmp):
    ctx = make_ctx(tmp)
    words = {f"r{r}": Word(f"r{r}", "daily", f"das Wort{r}", [f"word {r}"], "noun", rank=r) for r in range(1, 5001, 7)}
    ctx.content = Content(words, [])
    return ctx


class Placement(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = ctx_with_bank(tmp.name)
        self.asked = []
        for target, value in (("app.ui.clear", None), ("app.ui.keys", lambda options: ""),
                              ("app.placement._probes", lambda ctx: {"der_die_das": [0, 0], "grammar": [0, 0]})):
            patcher = mock.patch(target, value) if value else mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def kid_who_knows(self, top_rank):
        def ask(ctx, word, direction, heading):
            self.asked.append(word.rank)
            return CORRECT if word.rank <= top_rank else WRONG
        with mock.patch("app.placement.ask", ask), console.capture():
            return placement.run(self.ctx)

    def test_an_a2_kid_is_placed_and_seeded(self):
        band = self.kid_who_knows(1000)
        self.assertEqual(band, "A2")
        vocab = self.ctx.profile.data["vocab"]
        seeded = {wid for wid, s in vocab.items() if s.get("seeded")}
        self.assertEqual(seeded, {w.id for w in self.ctx.content.words.values() if w.rank <= 1000})
        self.assertTrue(all(s["box"] == placement.SEED_BOX for s in vocab.values()))
        dues = sorted({s["due"] for s in vocab.values()})
        self.assertEqual((dues[0], len(dues)), ("2026-09-18", placement.SPREAD_DAYS))  # spread over two weeks
        # It stopped after two hard bands: nothing from the last band was asked.
        self.assertLessEqual(max(self.asked), 3500)
        self.assertEqual(self.ctx.profile.data["placement"]["band"], "A2")

    def test_the_answer_log_reproduces_the_seed(self):
        self.kid_who_knows(500)
        self.assertEqual(attempts.rebuild(attempts.read(self.ctx.profile))["vocab"], self.ctx.profile.data["vocab"])

    def test_a_beginner_gets_nothing_seeded(self):
        self.assertEqual(self.kid_who_knows(0), "A1")
        self.assertEqual(self.ctx.profile.data["vocab"], {})
        self.assertLessEqual(len(self.asked), 2 * placement.PER_BUCKET)  # two hard bands, then it stops

    def test_words_already_started_keep_their_box(self):
        self.ctx.profile.data["vocab"]["r1"] = {**srs.new_state(), "box": 4, "due": "2026-10-01"}
        self.kid_who_knows(1000)
        self.assertEqual(self.ctx.profile.data["vocab"]["r1"]["box"], 4)

    def test_a_seeded_word_right_once_is_learned_wrong_once_is_back_to_box_1(self):
        self.kid_who_knows(200)
        state = dict(self.ctx.profile.data["vocab"]["r1"])
        right, wrong = dict(state), dict(state)
        srs.apply_result(right, CORRECT, date(2026, 9, 20))
        srs.apply_result(wrong, WRONG, date(2026, 9, 20))
        self.assertEqual((right["box"], wrong["box"]), (srs.LEARNED_BOX, 1))


if __name__ == "__main__":
    unittest.main()
