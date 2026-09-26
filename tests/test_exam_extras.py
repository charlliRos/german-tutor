"""Worked examples, the speaking section, and the real exam files' new parts."""
import tempfile
import unittest
from unittest import mock

import numpy as np

from app import attempts, exam_practice, exams
from app.ui import console
from tests.test_exams import RAW
from tests.test_flows import make_ctx

SPEAKING = {"id": "sprechen-1", "skill": "speaking", "title_de": "Sprechen, Teil 1", "tasks": [
    {"id": "1", "card_title": "Freizeit", "card": ["Sport?"], "prompt_de": "Frag nach Sport.",
     "partner_de": "Was machst du gern?", "seconds": 10, "min_words": 4,
     "keywords": [["sport"], ["spielst", "machst"]], "model_de": "Welchen Sport machst du gern?"}]}


class Examples(unittest.TestCase):
    def test_a_match_example_may_not_use_a_scored_answer(self):
        bad = {**RAW, "parts": [{**RAW["parts"][1], "example": {"type": "match", "question": "?", "answer": "b",
                                                                 "explain_en": "."}}]}
        self.assertIn("also the answer of a scored item", " ".join(exams.check_exam(bad, "t")))
        ok = {**RAW, "parts": [{**RAW["parts"][1], "example": {"type": "match", "question": "?", "answer": "a",
                                                                "explain_en": "."}}]}
        self.assertEqual(exams.check_exam(ok, "t"), [])

    def test_the_example_is_shown_with_its_answer_and_not_scored(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ctx = make_ctx(tmp.name)
        raw = {**RAW, "parts": [{**RAW["parts"][0], "example": {
            "type": "tf", "text": "t1", "question": "Das Fest ist am Samstag.", "answer": "richtig",
            "explain_en": "It says Samstag."}}]}
        exam = exams._exam(raw)
        queue = ["b", "f"]
        with mock.patch("app.ui.keys", lambda o: queue.pop(0) if "?" in o and queue else ""), \
                mock.patch("app.ui.clear"), mock.patch("app.exam_practice.sfx.play"), console.capture() as out:
            exam_practice.run_part(ctx, exam, exam.parts[0])
        self.assertIn("Lösung: richtig", out.get())
        logged = [e["item"] for e in attempts.read(ctx.profile) if e["type"] == "attempt"]
        self.assertEqual(logged, ["t-01.lesen-1.1", "t-01.lesen-1.2"])  # the example isn't in the log


class Speaking(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        self.exam = exams._exam({**RAW, "parts": [SPEAKING]})
        self.assertEqual(exams.check_exam({**RAW, "parts": [SPEAKING]}, "t"), [])

    def run_speaking(self, heard, keys=lambda o: ""):
        spoken = []
        self.ctx.audio = mock.Mock(can_record=True, can_check_speech=True, can_speak=True, problems=[])
        self.ctx.audio.heard.return_value = heard
        with mock.patch("app.ui.keys", keys), mock.patch("app.ui.timed_keys", return_value=""), mock.patch("app.ui.clear"), \
                mock.patch("app.speaking.record_for", return_value=(np.ones(10), 16000)), \
                mock.patch("app.exam_practice.hear", lambda ctx, text, slow=True, voice="": spoken.append((text, voice))), \
                console.capture() as out:
            exam_practice.speaking(self.ctx, self.exam, self.exam.parts[0])
        return out.get(), spoken

    def test_a_good_answer_gets_both_points_and_the_partner_speaks_first_in_another_voice(self):
        out, spoken = self.run_speaking("welchen sport machst du am liebsten")
        self.assertEqual(spoken[0], ("Was machst du gern?", "high"))
        self.assertIn("Welchen Sport machst du gern?", out)  # the model answer is shown
        saved = self.ctx.profile.data["exams"]["t-01"]["sprechen-1"]
        self.assertEqual((saved["score"], saved["max"]), (2, 2))
        (event,) = [e for e in attempts.read(self.ctx.profile) if e["type"] == "attempt"]
        self.assertEqual((event["competency"], event["grader"], event["response"]),
                         ("exam.speaking", "gtutor.speaking/1", "welchen sport machst du am liebsten"))

    def test_too_short_and_off_topic_gets_nothing(self):
        self.run_speaking("ja")
        self.assertEqual(self.ctx.profile.data["exams"]["t-01"]["sprechen-1"]["score"], 0)

    def test_without_a_microphone_it_is_a_self_check(self):
        self.ctx.audio = mock.Mock(can_record=False, can_check_speech=False, can_speak=False, problems=[])
        with mock.patch("app.ui.keys", lambda o: "y" if "y" in o else ""), mock.patch("app.ui.ask"), \
                mock.patch("app.ui.timed_keys", return_value=""), mock.patch("app.ui.clear"), console.capture():
            exam_practice.speaking(self.ctx, self.exam, self.exam.parts[0])
        (event,) = [e for e in attempts.read(self.ctx.profile) if e["type"] == "attempt"]
        self.assertEqual((event["score"]["kind"], event["grader"]), ("estimated", attempts.SELF))


class SpeakingRetryAndHints(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        self.exam = exams._exam({**RAW, "parts": [SPEAKING]})
        self.ctx.audio = mock.Mock(can_record=True, can_check_speech=True, can_speak=True, problems=[])

    def test_try_again_keeps_the_best_try(self):
        self.ctx.audio.heard.side_effect = ["ja", "welchen sporz machst du gern"]  # 2nd try: sport misheard, still counts
        choices = iter(["a", ""])
        with mock.patch("app.ui.keys", lambda o: ""), mock.patch("app.ui.timed_keys", lambda o, s: next(choices)),                 mock.patch("app.ui.clear"), mock.patch("app.speaking.record_for", return_value=(np.ones(9), 16000)),                 mock.patch("app.exam_practice.hear"), console.capture():
            exam_practice.speaking(self.ctx, self.exam, self.exam.parts[0])
        self.assertEqual(self.ctx.profile.data["exams"]["t-01"]["sprechen-1"]["score"], 2)
        self.assertEqual(len([e for e in attempts.read(self.ctx.profile) if e["type"] == "attempt"]), 2)  # both tries logged

    def test_hints_for_a_missing_verb_and_a_question(self):
        from app.content import Content, Word
        self.ctx.content = Content({"machen": Word("machen", "daily", "machen", ["do"], "verb"),
                                    "sport": Word("sport", "daily", "der Sport", ["sport"], "noun")}, [])
        task = exams.SpeakingTask(id="1", prompt_de="Stell eine Frage zum Thema Sport.", model_de="Machst du Sport?")
        self.assertEqual(len(exam_practice.speaking_hints(self.ctx, task, "sport sport")), 2)  # no verb, not a question
        self.assertEqual(exam_practice.speaking_hints(self.ctx, task, "machst du sport"), [])
        self.assertEqual(exam_practice.speaking_hints(self.ctx, task, "wann machst du sport"), [])


class ShippedExtras(unittest.TestCase):
    def test_every_reading_and_listening_part_has_an_example_and_both_exams_have_speaking(self):
        for exam in exams.load_exams()[0]:
            for part in exam.parts:
                if part.skill in ("reading", "listening"):
                    self.assertIsNotNone(part.example, f"{exam.id} {part.id}")
                if part.skill == "writing":
                    self.assertTrue(part.kind and len(part.point_keywords) == len(part.points), f"{exam.id} {part.id}")
            self.assertEqual(len(exam.skill_parts("speaking")), 3, exam.id)


if __name__ == "__main__":
    unittest.main()
