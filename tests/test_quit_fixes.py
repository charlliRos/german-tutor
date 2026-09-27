"""Quitting at awkward moments, and small text fixes: nothing is repeated, lost or counted twice."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app import attempts, exam_practice, goals, main, reading, report, resume
from app.content import Book, Content, Unit, Word
from app.profile import Profile
from app.ui import QuitSession, console
from tests.test_flows import TODAY, make_ctx

SENTENCE = "Der alte Mann ging langsam nach Hause."
ENGLISH = "The old man walked slowly home."


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.keys = []
        for target, value in (("app.ui.clear", lambda: None),
                              ("app.ui.keys", lambda options: (self.keys.append(options), "")[1]),
                              ("app.reading.hear", lambda *a, **k: None), ("app.ui.side_by_side", lambda *a: None)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def one_book(self, ctx, units):
        book = Book(id="b", title="Buch", author="A", year=1900, level="B1", intro_en="", units=units,
                    total_parts=len(units), short_title="Buch")
        ctx.content.books = [book]
        return book


class ProveItOnALookBack(Base):
    def test_a_failed_prove_it_on_the_last_review_day_brings_it_back(self):
        ctx = make_ctx(self.tmp)
        unit = Unit(n=1, de=SENTENCE, en=ENGLISH, part=1, sentence_pairs=[(SENTENCE, ENGLISH)])
        book = self.one_book(ctx, [unit])
        item = {"book": "b", "n": 1, "learned": "2026-08-01", "sessions_left": 0, "due_days": [TODAY.isoformat()],
                "last_task": "read_aloud"}
        ctx.profile.data["paragraph_reviews"]["b:1"] = item
        ctx.rng.random = lambda: 0.0  # always a prove-it
        ctx.rng.choice = lambda seq: "de2en" if "de2en" in seq else seq[0]
        typed = iter([ENGLISH, "Katze Hund Baum Haus"])  # the translation right, the prove-it wrong
        with mock.patch("app.ui.keys", lambda o: "2" if "2" in o else ""), \
                mock.patch("app.ui.ask_answer", lambda prompt: next(typed)), console.capture() as out:
            reading.review(ctx, book, unit, item, 1, 1)
        self.assertIn("comes back next session", out.get())
        self.assertIn("b:1", ctx.profile.data["paragraph_reviews"])        # not dropped
        self.assertEqual(ctx.profile.day(TODAY).get("paragraphs_learned", 0), 0)
        self.assertEqual([u.n for _, u, _ in reading.due_reviews(ctx)], [1])  # due again next session


class ResumedLookBack(Base):
    def test_a_resumed_look_back_keeps_the_limit_and_the_numbering(self):
        ctx = make_ctx(self.tmp, paragraph_reviews_per_session=3, units_per_day=1)
        units = [Unit(n=i, de=f"Satz {i}.", en=f"Sentence {i}.", part=i) for i in range(1, 12)]
        book = self.one_book(ctx, units)
        ctx.profile.book_state("b")["next"] = 9
        for n in range(1, 9):
            reading._schedule_reviews(ctx, book, units[n - 1])
        headings, calls = [], {"n": 0}
        real_review = reading.review

        def review(ctx, book, unit, item, i, total):
            calls["n"] += 1
            if calls["n"] == 3:
                raise QuitSession
            headings.append((i, total))
            return real_review(ctx, book, unit, item, i, total)

        translate = lambda ctx, book, unit, direction, heading, review=False: {"self_grade": "mostly right"}
        with mock.patch("app.reading._translate", translate), mock.patch("app.reading._read_aloud", lambda *a: True), \
                mock.patch("app.reading._look_back_task", lambda *a: (True, "")), \
                mock.patch("app.reading.review", review), console.capture():
            with self.assertRaises(QuitSession):
                reading.run_reading(ctx)
            reading.run_reading(ctx)
        self.assertEqual(headings, [(1, 3), (2, 3), (3, 3)])
        self.assertEqual(ctx.profile.day(TODAY)["reviews"], 3)
        self.assertIn({"": "carry on"}, self.keys)  # told why it carries on, not wiped straight away


class ProveItInANewParagraph(Base):
    def run_twice(self, quit_at):
        ctx = make_ctx(self.tmp)
        unit = Unit(n=1, de=SENTENCE, en=ENGLISH, part=1, sentence_pairs=[(SENTENCE, ENGLISH)])
        self.one_book(ctx, [unit, Unit(n=2, de="Satz zwei ist hier.", en="Sentence two is here.", part=2)])
        ctx.rng.random = lambda: 0.0
        log = []

        def prove(ctx, book, unit, about):
            log.append("prove")
            if log.count("prove") == quit_at:
                raise QuitSession
            return True

        def typed(prompt):
            log.append("translate")
            return ENGLISH if "English" in prompt else SENTENCE

        with mock.patch("app.ui.keys", lambda o: "2" if "2" in o else ""), mock.patch("app.ui.ask_multiline", typed), \
                mock.patch("app.reading.prove_it", prove), mock.patch("app.reading._read_aloud", lambda *a: True), \
                console.capture():
            with self.assertRaises(QuitSession):
                reading.run_reading(ctx)
            reading.run_reading(ctx)
        return ctx, log

    def test_quitting_in_the_prove_it_after_round_3_doesnt_repeat_round_3(self):
        ctx, log = self.run_twice(quit_at=2)
        self.assertEqual(log, ["translate", "prove", "translate", "prove"])
        self.assertEqual([e["task"] for e in ctx.profile.read_journal(None)], ["de2en", "en2de"])
        self.assertEqual(ctx.profile.book_state("b")["next"], 2)

    def test_quitting_in_the_prove_it_after_round_1_doesnt_repeat_round_1(self):
        ctx, log = self.run_twice(quit_at=1)
        self.assertEqual(log, ["translate", "prove", "translate", "prove"])
        self.assertEqual([e["task"] for e in ctx.profile.read_journal(None)], ["de2en", "en2de"])


class RestartedBook(Base):
    def test_starting_a_book_again_doesnt_carry_on_another_paragraph(self):
        ctx = make_ctx(self.tmp)
        book = self.one_book(ctx, [Unit(n=i, de=f"Satz {i}.", en=f"Sentence {i}.", part=i) for i in range(1, 10)])
        resume.bookmark(ctx)["reading"] = {"book": "b", "n": 5, "rounds_done": 1, "first": {"task": "de2en", "unit": 5}}
        ctx.profile.book_state("b")["next"] = 1  # "start again from the beginning"
        log = []

        def translate(ctx, book, unit, direction, heading, review=False):
            log.append((unit.n, heading))
            return {"self_grade": "mostly right"}

        with mock.patch("app.reading._translate", translate), mock.patch("app.reading._read_aloud", lambda *a: True), \
                console.capture():
            reading.lesson(ctx, book)
        self.assertEqual(log, [(1, "Round 1 of 3"), (1, "Round 3 of 3")])

    def test_carrying_on_a_paragraph_waits_for_a_key(self):
        ctx = make_ctx(self.tmp)
        book = ctx.content.books[0]
        resume.bookmark(ctx)["reading"] = {"book": "b", "n": 1, "rounds_done": 1, "first": {"task": "de2en"}}
        translate = lambda ctx, book, unit, direction, heading, review=False: {"self_grade": "mostly right"}
        with mock.patch("app.reading._translate", translate), mock.patch("app.reading._read_aloud", lambda *a: True), \
                console.capture() as out:
            reading.lesson(ctx, book)
        self.assertIn("round 2", out.get())
        self.assertIn({"": "carry on"}, self.keys)


class ExamPartDoneThenQuit(Base):
    def test_quitting_on_the_results_doesnt_give_a_second_part(self):
        ctx = make_ctx(self.tmp)
        ctx.profile.data["target"] = "A2"
        parts = []

        def results(ctx, exam, part, *a):
            parts.append(part.id)
            raise QuitSession

        with mock.patch("app.exam_practice._ask", lambda *a, **k: ""), mock.patch("app.exam_practice._results", results), \
                mock.patch("app.exam_practice.show_pictures", lambda *a: False), console.capture():
            resume.set_part(ctx, "lesson", "exam")
            with self.assertRaises(QuitSession):
                exam_practice.run_daily(ctx)
            line = exam_practice.run_daily(ctx)
        self.assertEqual(len(parts), 1)
        self.assertIn("0 of 5", line)
        self.assertIsNone(resume.part(ctx, "exam_done"))

    def test_the_weakest_part_isnt_one_done_today(self):
        ctx = make_ctx(self.tmp)
        exams = exam_practice.load_exams()[0]
        exam = exams[0]
        ctx.profile.data["target"] = exam.level
        later = "2099-01-01"
        done = {p.id: {"score": 5, "max": 5, "best": 5, "last": "2026-01-01", "tries": 1, "due": later}
                for p in exam.parts}
        done[exam.parts[0].id].update(best=0, score=0, last=TODAY.isoformat())
        done[exam.parts[1].id].update(best=1, score=1)
        ctx.profile.data["exams"] = {exam.id: done}
        self.assertEqual(exam_practice.todays_part(ctx, exams)[1].id, exam.parts[1].id)


class ExamTexts(Base):
    def test_a_learner_below_every_exam_gets_the_lowest(self):
        ctx = make_ctx(self.tmp)
        ctx.profile.data["target"] = "A1"
        exams = [SimpleNamespace(level="A2"), SimpleNamespace(level="B1")]
        self.assertEqual(exam_practice.exam_for_goal(ctx, exams).level, "A2")

    def test_the_intro_doesnt_say_nothing_is_saved(self):
        ctx = make_ctx(self.tmp)
        exam = exam_practice.load_exams()[0][0]
        part = exam.parts[0]
        with mock.patch("app.exam_practice._example", lambda *a: None), console.capture() as out:
            exam_practice._intro(ctx, exam, part)
        text = " ".join(out.get().split())
        self.assertNotIn("nothing is saved", text)
        self.assertIn("carry on here later today", text)

    def test_the_menu_error_names_every_option(self):
        ctx = make_ctx(self.tmp)
        ctx.profile.data["target"] = "A2"
        ctx.presence = None
        with mock.patch("app.ui.ask", side_effect=["x", QuitSession]), mock.patch("app.ui.start_clock"), \
                console.capture() as out:
            with self.assertRaises(QuitSession):
                main.menu(ctx)
        numbers = [k for k in main.MENU if k.isdigit()]
        self.assertIn(f"Pick 1–{numbers[-1]}", out.get())


class GoalAndTopics(Base):
    def test_quitting_at_the_topics_asks_the_goal_again(self):
        ctx = make_ctx(self.tmp)
        with mock.patch("app.ui.ask", side_effect=QuitSession), console.capture():
            with self.assertRaises(QuitSession):
                goals.choose(ctx)
        self.assertNotIn("target", ctx.profile.data)


class ClaimsInTheReport(Base):
    def test_grammar_and_verb_claims_are_readable(self):
        profile = Profile(Path(self.tmp) / "anna.json", {"name": "Anna"})
        for item, task in (("w1|grammar.ending", "ending"), ("gehen|past", "past")):
            attempts.note("x", "wrong", task=task)
            attempts.record(profile, TODAY, item=item, item_version="v", competency="grammar.x", subcompetency=task,
                            context="warmup", score=attempts.right_or_wrong(True), grader=attempts.GRADER,
                            claimed_correct=True)
        content = Content({"w1": Word("w1", "daily", "der Bahnhof", ["station"], "noun")}, [])
        with mock.patch("app.claims.REVIEWED_FILE", Path(self.tmp) / "reviewed.json"):
            text = " ".join(report.claim_lines(profile, content))
        self.assertIn("der Bahnhof · grammar: ending", text)
        self.assertIn("gehen (past)", text)
        self.assertNotIn("|", text)


if __name__ == "__main__":
    unittest.main()
