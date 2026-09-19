"""Quitting in the middle of a lesson keeps the work that was already done."""
import random
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app import profile as profile_module, reading, ui, warmup
from app.answers import WRONG, check_english
from app.config import load_settings
from app.content import Book, Content, Unit, Word
from app.profile import Profile
from app.ui import QuitSession, console

TODAY = date(2026, 9, 17)


def make_ctx(tmp: str, **settings) -> SimpleNamespace:
    words = {f"w{i}": Word(id=f"w{i}", bank="daily", de=f"das Wort{i}", en=[f"word {i}"], pos="noun", rank=i)
             for i in range(12)}
    units = [Unit(n=i, de=f"Satz {i}.", en=f"Sentence {i}.", part=i) for i in (1, 2)]
    book = Book(id="b", title="Buch", author="A", year=1900, level="B1", intro_en="", units=units,
                total_parts=2, short_title="Buch")
    return SimpleNamespace(settings={**load_settings(), **settings}, content=Content(words, [book]),
                           profile=Profile(Path(tmp) / "kid.json", {"name": "Kid"}),
                           audio=SimpleNamespace(can_speak=False, problems=[]),
                           rng=random.Random(1), today=TODAY, step="")


class QuitMidLesson(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        for target, value in (("app.ui.clear", lambda: None), ("app.ui.keys", lambda options: ""),
                              ("app.warmup.show_card", lambda *a: None)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_warmup_counts_when_quitting_during_second_chances(self):
        ctx = make_ctx(self.tmp)

        def quiz(ctx, word, direction, second_chance=False):
            if second_chance:
                raise QuitSession
            return WRONG

        with mock.patch("app.warmup.quiz", quiz), console.capture():
            with self.assertRaises(QuitSession):
                warmup.run_warmup(ctx)
        self.assertEqual(ctx.profile.day(TODAY)["warmups"], 1)
        self.assertEqual(ctx.profile.streak(TODAY), 1)

    def test_typed_translation_kept_when_quitting_at_the_self_grade(self):
        ctx = make_ctx(self.tmp, reading_tasks={"en2de": 1})
        with mock.patch("app.ui.ask_multiline", lambda prompt: "Satz eins."), \
                mock.patch("app.reading._self_grade", mock.Mock(side_effect=QuitSession)), console.capture():
            with self.assertRaises(QuitSession):
                reading.run_reading(ctx)
        journal = ctx.profile.read_journal(None)
        self.assertEqual([(e["answer"], e["self_grade"]) for e in journal], [("Satz eins.", "not graded")])
        self.assertEqual(ctx.profile.book_state("b")["next"], 2)
        self.assertEqual(ctx.profile.day(TODAY)["units"], 1)


class EnglishAnswers(unittest.TestCase):
    go = Word(id="t", bank="daily", de="gehen", en=["to go", "to walk"], pos="verb")

    def test_other_short_verb_is_not_a_typo(self):
        self.assertEqual(check_english("to do", self.go).outcome, WRONG)

    def test_listing_several_guesses_is_wrong(self):
        self.assertEqual(check_english("to be / to have / to go", self.go).outcome, WRONG)


class DamagedFiles(unittest.TestCase):
    def test_damaged_profile_and_journal_line_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(profile_module, "PROFILES_DIR", Path(tmp)):
            good = Profile.open_or_create("Anna")
            good.add_journal({"task": "de2en"})
            with good.journal_path.open("a", encoding="utf-8") as f:
                f.write('{"task": "en2')  # cut off mid-save
            (Path(tmp) / "ben.json").write_bytes(b"")
            damaged = []
            self.assertEqual([p.name for p in Profile.list_all(damaged)], ["Anna"])
            self.assertEqual([p.name for p in damaged], ["ben.json"])
            self.assertEqual(len(good.read_journal(None)), 1)


class HeldEnter(unittest.TestCase):
    """A held-down Enter sends many empty lines: they must not answer (and so skip) a question."""

    def typed(self, *lines):
        return mock.patch("app.ui._read", mock.Mock(side_effect=list(lines)))

    def test_empty_lines_do_not_answer(self):
        with self.typed("", "", "", "der Hund"), console.capture():
            self.assertEqual(ui.ask_answer("German:"), "der Hund")

    def test_question_mark_means_dont_know(self):
        with self.typed("", "?"), console.capture():
            self.assertEqual(ui.ask_answer("German:"), "")

    def test_translation_ignores_leading_empty_lines(self):
        with self.typed("", "", "Der Hund", "bellt.", "", ""), console.capture():
            self.assertEqual(ui.ask_multiline("Translate:"), "Der Hund\nbellt.")

    def test_translation_question_mark_skips(self):
        with self.typed("", "?"), console.capture():
            self.assertEqual(ui.ask_multiline("Translate:"), "")

    def drain_with(self, keys_at):
        """Run a _Drain over polls at the given times; True in keys_at means a key was waiting."""
        buzz, clock = mock.Mock(), iter(t for t, _ in keys_at)
        waiting = iter(k for _, k in keys_at)
        with mock.patch.object(ui, "BUZZ", [buzz]), mock.patch.object(ui, "_last_key", [0.0]), \
                mock.patch("app.ui.time.monotonic", lambda: next(clock)), \
                mock.patch("app.ui.key_pressed", lambda: next(waiting)), \
                mock.patch("app.ui._enter_held", lambda: False), mock.patch("app.ui.flush_input", lambda: None):
            drain = ui._Drain()
            for _ in keys_at:
                drain.keys_waiting()
        return buzz.call_count

    def test_one_early_press_is_quiet(self):
        self.assertEqual(self.drain_with([(10.0, True), (10.5, False)]), 0)

    def test_held_enter_buzzes_once(self):
        self.assertEqual(self.drain_with([(10.0, True), (10.03, True), (10.06, True), (10.09, True)]), 1)


if __name__ == "__main__":
    unittest.main()
