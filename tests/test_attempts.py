"""The answer log: every answer is appended, and the boxes can be rebuilt from the log alone."""
import itertools
import json
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

from app import attempts, genders, reading, warmup
from app.answers import ALMOST, CORRECT, WRONG
from app.ui import console
from tests.test_flows import TODAY, make_ctx


class AnswerLog(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        for target, value in (("app.ui.clear", lambda: None), ("app.ui.keys", lambda options: ""),
                              ("app.ui.pause", lambda *a, **k: None), ("app.warmup.show_card", lambda *a: None)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _warmup(self, ctx, outcomes):
        cycle = itertools.cycle(outcomes)

        def quiz(ctx, word, direction, second_chance=False):
            outcome = CORRECT if second_chance else next(cycle)
            attempts.note(f"answer for {word.id}", outcome, task=direction)
            return outcome

        with mock.patch("app.warmup.quiz", quiz), console.capture():
            warmup.run_warmup(ctx)

    def test_boxes_rebuild_from_the_log_alone(self):
        ctx = make_ctx(self.tmp)
        self._warmup(ctx, [CORRECT, WRONG, ALMOST])
        ctx.today = TODAY + timedelta(days=1)  # a second day: reviews and new words on top of the first
        self._warmup(ctx, [WRONG, CORRECT])
        events = attempts.read(ctx.profile)
        self.assertEqual(events[0]["type"], "baseline")
        rebuilt = attempts.rebuild(events)
        self.assertTrue(ctx.profile.data["vocab"])
        self.assertEqual(rebuilt["vocab"], ctx.profile.data["vocab"])

    def test_the_boxes_from_before_the_log_are_its_baseline(self):
        ctx = make_ctx(self.tmp)
        ctx.profile.data["vocab"]["w0"] = {"box": 4, "due": TODAY.isoformat(), "seen": 9, "right": 8, "wrong": 1,
                                           "last": "2026-09-01"}
        before = json.loads(json.dumps(ctx.profile.data["vocab"]))
        self._warmup(ctx, [CORRECT])
        events = attempts.read(ctx.profile)
        self.assertEqual(events[0]["vocab"], before)
        self.assertEqual(attempts.rebuild(events)["vocab"], ctx.profile.data["vocab"])
        # Positive control: without the baseline, the rebuild is different (w0 started from nothing).
        self.assertNotEqual(attempts.rebuild(events[1:])["vocab"], ctx.profile.data["vocab"])

    def test_every_typed_answer_is_kept_with_its_response_and_grader(self):
        ctx = make_ctx(self.tmp)
        self._warmup(ctx, [WRONG])
        answers = [e for e in attempts.read(ctx.profile) if e["type"] == "attempt"]
        scheduled = [e for e in answers if e.get("schedule")]
        repeats = [e for e in answers if e["context"] == "warmup.repeat"]
        self.assertEqual(len(scheduled), len(ctx.profile.data["vocab"]))
        self.assertEqual(len(repeats), len(scheduled))  # every wrong word came back once, then was right
        for e in answers:
            self.assertEqual(e["grader"], attempts.GRADER)
            self.assertEqual(e["response"], f"answer for {e['item']}")
            self.assertIn(e["task"], ("en2de", "de2en"))
            self.assertIn(e["competency"], attempts.COMPETENCIES)
        self.assertEqual({e["score"]["label"] for e in scheduled}, {WRONG})

    def test_overridden_answer_keeps_the_machine_verdict(self):
        ctx = make_ctx(self.tmp)

        def quiz(ctx, word, direction, second_chance=False):
            attempts.note("my own answer", WRONG, task=direction)
            return CORRECT if second_chance else warmup.ONCE_MORE

        with mock.patch("app.warmup.quiz", quiz), console.capture():
            warmup.run_warmup(ctx)
        first = next(e for e in attempts.read(ctx.profile) if e.get("schedule"))
        self.assertEqual((first["counted"], first["machine_verdict"], first["claimed_correct"]),
                         (CORRECT, WRONG, True))

    def test_self_graded_translation_is_an_estimate_never_a_machine_grade(self):
        ctx = make_ctx(self.tmp)
        with mock.patch("app.ui.ask_multiline", lambda prompt: "Sentence 1." if "English" in prompt else "Satz 1."), \
                mock.patch("app.ui.side_by_side", lambda *a: None), \
                mock.patch("app.reading._self_grade", lambda ctx, text: "mostly right"), console.capture():
            reading.lesson(ctx, ctx.content.books[0])
        translations = [e for e in attempts.read(ctx.profile) if e.get("competency", "").startswith(("reading.", "writing."))]
        self.assertTrue(translations)
        for e in translations:
            self.assertEqual(e["grader"], attempts.SELF)
            self.assertEqual(e["score"]["kind"], "estimated")
            self.assertTrue(e["score"]["needs_review"])
            self.assertEqual(e["item"], "b#1")

    def test_gender_answers_rebuild_too(self):
        ctx = make_ctx(self.tmp, genders_per_day=3)
        for wid in ("w0", "w1", "w2"):
            ctx.profile.data["vocab"][wid] = {"box": 1, "due": None, "seen": 1, "right": 1, "wrong": 0, "last": None}
        answers = itertools.cycle(["1", "3"])  # der (wrong), das (right)
        with mock.patch("app.ui.ask_answer", lambda prompt: next(answers)), \
                mock.patch("app.genders.hear", lambda *a, **k: None), console.capture():
            result = genders.run_genders(ctx, first_today=True)
        self.assertEqual(result.total, 3)
        events = attempts.read(ctx.profile)
        self.assertEqual(attempts.rebuild(events)["genders"], ctx.profile.data["genders"])
        self.assertEqual([e["response"] for e in events if e["type"] == "attempt"], ["der", "das", "der"])


if __name__ == "__main__":
    unittest.main()
