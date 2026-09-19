"""Quitting in the middle of a lesson keeps the work that was already done."""
import random
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app import profile as profile_module, reading, ui, verbs, warmup
from app.answers import WRONG, check_english
from app.config import load_settings
from app.content import Book, Content, Unit, Verb, Word
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
        ctx = make_ctx(self.tmp)
        with mock.patch("app.ui.ask_multiline", lambda prompt: "Satz eins."), \
                mock.patch("app.reading._self_grade", mock.Mock(side_effect=QuitSession)), console.capture():
            with self.assertRaises(QuitSession):
                reading.run_reading(ctx)
        journal = ctx.profile.read_journal(None)
        self.assertEqual([(e["answer"], e["self_grade"]) for e in journal], [("Satz eins.", "not graded")])
        # All 3 rounds weren't done: the same paragraph starts again next time.
        self.assertEqual(ctx.profile.book_state("b")["next"], 1)
        self.assertEqual(ctx.profile.day(TODAY).get("units", 0), 0)


class Repetition(unittest.TestCase):
    """A new paragraph in 3 rounds, then look backs in the next 2 sessions and on days 1, 3, 7, 16, 35."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        units = [Unit(n=i, de=f"Satz {i}.", en=f"Sentence {i}.", part=i, word_ids=[f"w{i}"]) for i in range(1, 60)]
        book = Book(id="b", title="Buch", author="A", year=1900, level="B1", intro_en="", units=units,
                    total_parts=59, short_title="Buch")
        self.ctx = make_ctx(tmp.name)
        self.ctx.content.books = [book]
        self.grade = "mostly right"
        self.log = []

        def translate(ctx, book, unit, direction, heading, review=False):
            self.log.append((unit.part, "look back" if review else heading))
            return {"self_grade": self.grade}

        def read_aloud(ctx, book, unit, heading):
            self.log.append((unit.part, "look back" if heading.startswith("Look") else heading))

        for target, value in (("app.ui.clear", lambda: None), ("app.ui.keys", lambda options: ""),
                              ("app.reading._translate", translate), ("app.reading._read_aloud", read_aloud)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def session(self, day: int) -> list:
        self.ctx.today = TODAY + timedelta(days=day)
        self.log = []
        with console.capture():
            reading.run_reading(self.ctx)
        return self.log

    def test_new_paragraph_has_three_rounds_and_queues_its_words(self):
        self.assertEqual(self.session(0), [(1, "Round 1 of 3"), (1, "Round 2 of 3"), (1, "Round 3 of 3")])
        self.assertEqual(self.ctx.profile.data["reading_words"], ["w1"])
        self.assertEqual(self.ctx.profile.day(TODAY)["units"], 1)

    def test_session_three_repeats_sessions_one_and_two_after_the_new_paragraph(self):
        self.session(0)
        self.assertEqual(self.session(1)[3:], [(1, "look back")])
        self.assertEqual(self.session(2)[:3], [(3, "Round 1 of 3"), (3, "Round 2 of 3"), (3, "Round 3 of 3")])
        self.assertEqual(self.log[3:], [(1, "look back"), (2, "look back")])

    def test_review_days_then_learned(self):
        self.session(0)
        looked_back = [day for day in range(1, 40) if (1, "look back") in self.session(day)]
        # sessions 1 and 2 (days 1, 2), then days 3, 7, 16, 35
        self.assertEqual(looked_back, [1, 2, 3, 7, 16, 35])
        self.assertNotIn("b:1", self.ctx.profile.data["paragraph_reviews"])

    def test_needs_work_comes_back_next_session(self):
        self.ctx.settings["reading_tasks"] = {"read_aloud": 0, "de2en": 1, "en2de": 1}  # graded look backs only
        self.session(0)
        self.grade = "needs work"
        self.session(1)
        self.grade = "mostly right"
        self.assertIn((1, "look back"), self.session(2))
        self.assertEqual(self.ctx.profile.data["paragraph_reviews"]["b:1"]["sessions_left"], 1)


class RepeatUntilRight(unittest.TestCase):
    def test_missed_and_almost_words_come_back_until_right(self):
        from app.answers import ALMOST
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            a, b = ctx.content.words["w1"], ctx.content.words["w2"]
            answers = {"w1": [WRONG, ALMOST, warmup.AUTO_NEXT], "w2": [warmup.AUTO_NEXT]}
            asked = []

            def quiz(ctx, word, direction, second_chance=False):
                asked.append(word.id)
                return answers[word.id].pop(0)

            with mock.patch("app.ui.clear", lambda: None), mock.patch("app.warmup.quiz", quiz), console.capture():
                warmup.repeat_until_right(ctx, [a, b])
            self.assertEqual(sorted(asked), ["w1", "w1", "w1", "w2"])


class ListenAndType(unittest.TestCase):
    def test_marks_words_right_slipped_and_missing(self):
        text, score = reading.mark_words("Der Hunt bellt", "Der Hund bellt laut.")
        self.assertEqual(score, (1 + 0.5 + 1 + 0) / 4)
        self.assertEqual(reading.mark_words("der hund bellt laut", "Der Hund bellt laut.")[1], 1.0)
        self.assertEqual(reading.mark_words("Muede", "Müde!")[1], 1.0)  # ue for ü is fine

    def test_look_back_counts_only_when_mostly_right(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            ctx.audio.can_speak = True
            unit = Unit(n=1, de="Der Hund bellt heute sehr laut.", en="The dog barks loudly today.", part=1)
            book = ctx.content.books[0]
            for typed, expected in (("Der Hund bellt heute sehr laut", True), ("Der Hund", False), ("?", False)):
                with mock.patch("app.ui._read", mock.Mock(side_effect=[typed])), \
                        mock.patch("app.reading.hear", lambda *a, **k: None), mock.patch("app.ui.clear", lambda: None), \
                        mock.patch("app.ui.keys", lambda options: ""), console.capture():
                    self.assertEqual(reading._dictation(ctx, book, unit, "Look back"), expected, typed)


class SentenceLookBack(unittest.TestCase):
    def run_look_back(self, grades, typed="My answer."):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp, look_back_sentences=2)
            pairs = [("Der Hund bellt laut.", "The dog barks loudly."), ("–", "–"),
                     ("Die Katze schläft jetzt.", "The cat is asleep now."), ("Wir gehen nach Hause.", "We go home.")]
            unit = Unit(n=1, de=" ".join(d for d, _ in pairs), en="…", part=1, sentence_pairs=pairs)
            grades = iter(grades)
            with mock.patch("app.ui._read", lambda *a, **k: typed), mock.patch("app.ui.clear", lambda: None), \
                    mock.patch("app.ui.keys", lambda options: ""), \
                    mock.patch("app.reading._self_grade", lambda *a: next(grades)), console.capture():
                ok = reading._sentence_look_back(ctx, ctx.content.books[0], unit, "de2en", "Look back")
            return ok, ctx.profile.read_journal(None)

    def test_two_sentences_in_a_row_skipping_bits_of_punctuation(self):
        ok, journal = self.run_look_back(["mostly right", "nailed it"])
        self.assertTrue(ok)
        self.assertEqual(len(journal), 2)
        self.assertTrue(all(e["reference"] != "–" and e["review"] for e in journal))

    def test_one_needs_work_means_it_comes_back(self):
        self.assertFalse(self.run_look_back(["nailed it", "needs work"])[0])
        self.assertFalse(self.run_look_back([], typed="?")[0])

    def test_no_sentence_pairs_falls_back_to_the_paragraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            unit = ctx.content.books[0].units[0]
            self.assertIsNone(reading._sentence_look_back(ctx, ctx.content.books[0], unit, "en2de", "Look back"))


class BookSentences(unittest.TestCase):
    def test_sentences(self):
        from app.content import sentences
        self.assertEqual(sentences("Er kam z. B. spät. »Wo warst du?« fragte sie.\nAugust 1904"),
                         ["Er kam z. B. spät.", "»Wo warst du?« fragte sie.", "August 1904"])

    def test_the_word_in_its_book_sentence(self):
        from app.content import story_sentence
        text = "Er war traurig. Sie traute sich nicht. Die Staatsanwälte kamen."
        self.assertEqual(story_sentence("sich trauen", text), "Sie traute sich nicht.")
        self.assertEqual(story_sentence("der Staatsanwalt", text), "Die Staatsanwälte kamen.")
        self.assertEqual(story_sentence("gehen", text), "")

    def test_card_shows_the_book_sentence(self):
        word = Word(id="x", bank="reading", de="der Hund", en=["dog"], pos="noun",
                    story_de="Der Hund bellt.", story_from="Buch")
        with console.capture() as cap:
            console.print(warmup.word_details(word))
        self.assertIn("in the book", cap.get())
        self.assertIn("Der Hund bellt.", cap.get())


class IrregularVerbs(unittest.TestCase):
    gehen = Verb(inf="gehen", en="to go", past="ging", perfect="ist gegangen")

    def test_past_forms(self):
        self.assertEqual(self.gehen.past_forms, ["ging", "gingst", "gingen", "gingt"])
        self.assertEqual(Verb("halten", "to hold", "hielt", "hat gehalten").past_forms,
                         ["hielt", "hieltest", "hielten", "hieltet"])

    def test_checking_forms(self):
        from app.answers import ALMOST, CORRECT
        check = lambda answer, kind, expected: verbs.check_form(answer, self.gehen, kind, expected).outcome  # noqa: E731
        self.assertEqual(check("gingen", "past", "gingen"), CORRECT)
        self.assertEqual(check("ging", "past", "gingen"), ALMOST)  # right verb, wrong person
        self.assertEqual(check("gehte", "past", "ging"), WRONG)
        self.assertEqual(check("er ist gegangen", "perfect", "ist gegangen"), CORRECT)
        self.assertEqual(check("gegangen", "perfect", "ist gegangen"), ALMOST)
        self.assertEqual(check("hat gegangen", "perfect", "ist gegangen"), ALMOST)

    def test_verbs_join_once_read_and_misses_repeat(self):
        from app.content import VerbHit
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            ctx.content.verbs = {"gehen": self.gehen}
            ctx.content.verb_hits = {"gehen": [VerbHit("b", 1, "Er ging nach Hause.", "ging", "past")]}
            self.assertEqual(verbs.plan(ctx, True), [])  # paragraph 1 not read yet
            ctx.profile.book_state("b")["next"] = 2
            self.assertEqual(verbs.plan(ctx, True), ["gehen|past", "gehen|perfect"])
            typed = iter(["gehte", "ist gegangen", "ging"])  # past wrong, perfect right, then past again
            with mock.patch("app.ui._read", lambda *a, **k: next(typed)), mock.patch("app.ui.clear", lambda: None), \
                    mock.patch("app.ui.keys", lambda options: ""), console.capture() as cap:
                ctx.rng = random.Random(0)
                result = verbs.run_verbs(ctx, True)
            self.assertEqual((result.right, result.total), (1, 2))
            self.assertIn("Er _____ nach Hause.", cap.get())
            self.assertEqual(ctx.profile.data["verbs"]["gehen|perfect"]["box"], 1)
            self.assertEqual(verbs.plan(ctx, False), [])  # nothing due today any more


class RestartBook(unittest.TestCase):
    def test_start_a_half_read_book_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            ctx.profile.book_state("b")["next"] = 2
            with mock.patch("app.ui.ask", lambda prompt: "1"), mock.patch("app.ui.keys", lambda options: "s"), \
                    console.capture():
                reading.choose_book(ctx)
            self.assertEqual(ctx.profile.book_state("b")["next"], 1)


class ReadingWordsInWarmup(unittest.TestCase):
    def test_key_words_of_read_paragraphs_come_first_in_the_next_warmup(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            ctx.profile.data["reading_words"] = ["w11", "w10"]
            seen = []
            with mock.patch("app.ui.clear", lambda: None), mock.patch("app.ui.keys", lambda options: ""), \
                    mock.patch("app.warmup.show_card", lambda ctx, word, i, total: seen.append(word.id)), \
                    mock.patch("app.warmup.quiz", lambda *a, **k: warmup.AUTO_NEXT), console.capture():
                warmup.run_warmup(ctx)
            self.assertEqual(seen[:2], ["w11", "w10"])
            self.assertEqual(ctx.profile.data["reading_words"], [])

    def test_known_key_words_come_back_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            ctx.profile.data["vocab"]["w3"] = {"box": 4, "due": "2099-01-01", "seen": 5, "right": 5, "wrong": 0,
                                               "last": "2026-09-01"}
            ctx.profile.data["reading_words"] = ["w3"]
            asked = []
            quiz = lambda ctx, word, *a, **k: asked.append(word.id) or warmup.AUTO_NEXT  # noqa: E731
            with mock.patch("app.ui.clear", lambda: None), mock.patch("app.ui.keys", lambda options: ""), \
                    mock.patch("app.warmup.show_card", lambda *a: None), mock.patch("app.warmup.quiz", quiz), \
                    console.capture():
                warmup.run_warmup(ctx)
            self.assertEqual(asked.count("w3"), 1)
            self.assertEqual(ctx.profile.data["vocab"]["w3"]["box"], 4)  # extra practice: stays on schedule


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
