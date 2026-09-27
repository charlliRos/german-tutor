"""Carry on where you stopped: a kid who leaves mid-lesson carries on from there, not from the start."""
import tempfile
import unittest
from unittest import mock

from app import reading, resume, warmup
from app.answers import CORRECT
from app.ui import QuitSession, console
from tests.test_flows import make_ctx


class ResumeWarmup(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        for target, value in (("app.ui.clear", lambda: None), ("app.ui.keys", lambda options: ""),
                              ("app.ui.pause", lambda *a, **k: None), ("app.warmup.show_card", lambda *a: None)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_warmup(self, quit_after=None):
        asked = []

        def quiz(ctx, word, direction, second_chance=False):
            if not second_chance:
                if quit_after is not None and len(asked) == quit_after:
                    raise QuitSession
                asked.append(word.id)
            return CORRECT

        with mock.patch("app.warmup.quiz", quiz), console.capture():
            try:
                warmup.run_warmup(self.ctx)
            except QuitSession:
                pass
        return asked

    def test_leaving_mid_warmup_carries_on_with_the_rest(self):
        first = self.run_warmup(quit_after=3)
        self.assertEqual(len(first), 3)
        mark = resume.part(self.ctx, "warmup")
        total = mark["queue_total"]
        self.assertEqual(len(mark["queue"]), total - 3)
        self.assertFalse(self.ctx.profile.day(self.ctx.today).get("warmups"))
        rest = self.run_warmup()
        self.assertEqual(len(rest), total - 3)      # only the questions still to come
        self.assertFalse(set(first) & set(rest))    # nothing asked twice
        self.assertEqual(self.ctx.profile.day(self.ctx.today)["warmups"], 1)
        self.assertEqual(self.ctx.profile.day(self.ctx.today)["words"], total)
        self.assertIsNone(resume.today(self.ctx))   # the bookmark is gone once it's done

    def test_another_days_bookmark_is_ignored(self):
        self.run_warmup(quit_after=3)
        self.ctx.profile.data["resume"]["date"] = "2000-01-01"
        self.assertIsNone(resume.part(self.ctx, "warmup"))


class ResumeParagraph(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        self.book = self.ctx.content.books[0]
        for target, value in (("app.ui.clear", lambda: None), ("app.ui.keys", lambda options: ""),
                              ("app.reading._replay_until_enter", lambda *a: None),
                              ("app.reading._explain", lambda *a: None),
                              ("app.reading._words_you_need", lambda *a: None), ("app.reading.hear", lambda *a, **k: None)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_leaving_in_round_two_carries_on_at_round_two(self):
        translations = []

        def translate(ctx, book, unit, direction, heading, review=False):
            translations.append(direction)
            return {"answer": "x", "self_grade": "mostly right"}

        aloud = {"quit": True, "calls": 0}

        def read_aloud(ctx, book, unit, heading):
            aloud["calls"] += 1
            if aloud["quit"]:
                aloud["quit"] = False
                raise QuitSession
            return True

        with mock.patch("app.reading._translate", translate), mock.patch("app.reading._read_aloud", read_aloud), \
                console.capture():
            with self.assertRaises(QuitSession):
                reading.lesson(self.ctx, self.book)
            self.assertEqual(translations, ["de2en"])
            self.assertEqual(resume.part(self.ctx, "reading")["rounds_done"], 1)
            self.assertTrue(reading.lesson(self.ctx, self.book))
        self.assertEqual(translations, ["de2en", "en2de"])  # round 1 isn't done again
        self.assertEqual(aloud["calls"], 2)                  # round 2 again (it was left in the middle)
        self.assertEqual(self.ctx.profile.book_state(self.book.id)["next"], 2)
        self.assertEqual(resume.part(self.ctx, "reading")["rounds_done"], 0)


if __name__ == "__main__":
    unittest.main()
