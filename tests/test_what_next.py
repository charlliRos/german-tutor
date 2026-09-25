"""What next: exam misses feed the daily practice, exam parts come back, grammar leans to the frontier."""
import tempfile
import unittest
from datetime import date
from unittest import mock

from app import attempts, exam_practice, exams, grammar, srs
from app.content import Content, Word
from app.ui import console
from tests.test_exams import RAW
from tests.test_flows import TODAY, make_ctx


class ExamFeedback(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        words = {"fest": Word("fest", "daily", "das Stadtfest", ["city festival"], "noun", rank=900),
                 "tag": Word("tag", "daily", "der Samstag", ["Saturday"], "noun", rank=300),
                 "frei": Word("frei", "daily", "frei", ["free"], "adj", rank=400)}
        self.ctx.content = Content(words, [])
        self.ctx.profile.data["vocab"]["tag"] = {**srs.new_state(), "box": 4, "due": "2026-10-20"}
        self.exam = exams._exam(RAW)
        for target in ("app.ui.clear", "app.exam_practice.sfx.play"):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_part(self, answers):
        queue = list(answers)
        with mock.patch("app.ui.keys", lambda o: queue.pop(0) if "?" in o and queue else ""), console.capture() as out:
            exam_practice.run_part(self.ctx, self.exam, self.exam.parts[0])
        return out.get()

    def test_a_miss_brings_the_texts_words_back(self):
        out = self.run_part(["a", "r"])  # both wrong
        self.assertIn("come back in your next warm-up", out)
        tag = self.ctx.profile.data["vocab"]["tag"]
        self.assertEqual((tag["box"], tag["due"]), (1, "2026-09-18"))       # known word: tomorrow, box 1
        self.assertEqual(self.ctx.profile.data["reading_words"][:2], ["frei", "fest"])  # new words first in line
        self.assertEqual(attempts.rebuild(attempts.read(self.ctx.profile))["vocab"], self.ctx.profile.data["vocab"])

    def test_all_right_changes_nothing(self):
        self.run_part(["b", "f"])
        self.assertEqual(self.ctx.profile.data["vocab"]["tag"]["box"], 4)
        self.assertEqual(self.ctx.profile.data["reading_words"], [])

    def test_a_failed_part_is_due_in_3_days_a_passed_one_in_16(self):
        self.run_part(["a", "r"])
        self.assertEqual(self.ctx.profile.data["exams"]["t-01"]["lesen-1"]["due"], "2026-09-20")
        self.run_part(["b", "f"])
        self.assertEqual(self.ctx.profile.data["exams"]["t-01"]["lesen-1"]["due"], "2026-10-03")
        self.ctx.today = date(2026, 10, 3)
        self.assertEqual([p.id for _, p in exam_practice.due_parts(self.ctx, [self.exam])], ["lesen-1"])


class GrammarFocus(unittest.TestCase):
    def test_focus_kinds_get_about_70_percent(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ctx = make_ctx(tmp.name)
        sentences = ["Ich fahre mit dem Bus.", "Das ist ein neues Auto.", "Wir gehen heute ins Kino.",
                     "Sie hat einen roten Hut.", "Er kommt aus der Schule.", "Das ist eine kleine Stadt."]
        words = {f"w{i}": Word(f"w{i}", "daily", f"das Wort{i}", ["x"], "noun", example_de=s, example_en="x")
                 for i, s in enumerate(sentences * 5)}
        words |= {"neu": Word("neu", "daily", "neu", ["new"], "adj"), "rot": Word("rot", "daily", "rot", ["red"], "adj"),
                  "klein": Word("klein", "daily", "klein", ["small"], "adj")}
        ctx.content = Content(words, [])
        ctx.profile.data["vocab"] = {wid: {"box": 2} for wid in words if wid.startswith("w")}
        items = grammar.make_items(ctx, 6, focus=["ending"])
        self.assertGreaterEqual(sum(i.kind == "ending" for i in items), 3)
        self.assertEqual(grammar.make_items(ctx, 3, focus=None)[0].kind, "article")  # no focus: the usual mix


class TodaysExamPart(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        self.exam = exams._exam(RAW)

    def test_order_untried_first_writing_last_then_due_then_weakest(self):
        pick = lambda: exam_practice.todays_part(self.ctx, [self.exam])[1].id  # noqa: E731
        self.assertEqual(pick(), "lesen-1")
        done = exam_practice.progress(self.ctx).setdefault("t-01", {})
        result = lambda best, total, due="2026-12-01": {"score": best, "max": total, "best": best, "last": "", "tries": 1, "due": due}  # noqa: E731
        done.update({"lesen-1": result(2, 2), "lesen-2": result(1, 2), "hoeren-1": result(1, 1)})
        self.assertEqual(pick(), "schreiben-1")                 # the only one not tried yet
        done["schreiben-1"] = result(3, 3)
        self.assertEqual(pick(), "lesen-2")                     # all tried: the weakest (1 of 2)
        done["hoeren-1"]["due"] = "2026-09-01"
        self.assertEqual(pick(), "hoeren-1")                    # due again comes first

    def test_the_goal_picks_the_exam(self):
        b1 = exams._exam({**RAW, "id": "t-b1", "level": "B1"})
        self.ctx.profile.data["target"] = "C1"
        self.assertEqual(exam_practice.exam_for_goal(self.ctx, [self.exam, b1]).id, "t-b1")
        self.ctx.profile.data["target"] = "A2"
        self.assertEqual(exam_practice.exam_for_goal(self.ctx, [self.exam, b1]).id, "t-01")

    def test_the_daily_part_reports_its_score(self):
        with mock.patch("app.exam_practice.load_exams", return_value=([self.exam], [])),                 mock.patch("app.ui.keys", lambda o: {"b": "b", "r": "f"}.get(next((k for k in o if k in "br"), ""), "")),                 mock.patch("app.ui.clear"), mock.patch("app.exam_practice.sfx.play"), console.capture():
            line = exam_practice.run_daily(self.ctx)
        self.assertEqual(line, "Exam practice: A2 Lesen, Teil 1: 2 of 2")


if __name__ == "__main__":
    unittest.main()
