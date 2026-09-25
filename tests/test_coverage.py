"""Coverage: how much of a text a kid knows, and the gate that opens books when they're readable."""
import tempfile
import unittest
from unittest import mock

from app import coverage, reading
from app.content import Book, Content, Unit, Verb, Word
from app.ui import console
from tests.test_flows import make_ctx


def bank():
    words = [Word("hund", "daily", "der Hund", ["dog"], "noun", rank=500, plural="die Hunde"),
             Word("aufwachen", "daily", "aufwachen", ["to wake up"], "verb", rank=800),
             Word("fahren", "daily", "fahren", ["to drive"], "verb", rank=300),
             Word("gehen", "daily", "gehen", ["to go"], "verb", rank=150),
             Word("gross", "daily", "groß", ["big"], "adj", rank=400),
             Word("garten", "daily", "der Garten", ["garden"], "noun", rank=900, plural="die Gärten")]
    content = Content({w.id: w for w in words}, [])
    content.verbs = {"gehen": Verb("gehen", "to go", "ging", "ist gegangen")}
    return content


class Forms(unittest.TestCase):
    def test_inflected_forms_find_their_word(self):
        content = bank()
        text = "Die großen Hunde fährt. Er wachte auf und ging in den Garten. Sie ist aufgewacht."
        known = {wid: {"box": 2} for wid in ("hund", "aufwachen", "fahren", "gehen", "gross", "garten")}
        cov = coverage.text_coverage(content, known, text)
        self.assertEqual(cov.unmatched, [])   # every word matched: forms, separable verb, ging, function words
        self.assertEqual(cov.share, 1.0)

    def test_unknown_words_are_listed_most_common_first(self):
        cov = coverage.text_coverage(bank(), {}, "Der Hund fährt in den Garten.")
        self.assertEqual(cov.unknown, ["fahren", "hund", "garten"])
        self.assertEqual(cov.state, "locked")

    def test_states(self):
        self.assertEqual(coverage.Coverage(0.96).state, "open")
        self.assertEqual(coverage.Coverage(0.92).state, "teach")
        self.assertEqual(coverage.Coverage(0.5).state, "locked")

    def test_names_are_not_counted(self):
        units = [Unit(n=i, de=f"Lena sieht den Hund. Lena lacht {i}.", en="", part=i) for i in range(1, 5)]
        book = Book(id="b", title="B", author="", year=2026, level="A1", intro_en="", units=units)
        self.assertIn("lena", coverage.names(book, bank()))


class Gate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        content = bank()
        hard = Book(id="hard", title="Hard", author="", year=1900, level="C1", intro_en="",
                    units=[Unit(n=1, de="Der Hund fährt in den Garten.", en="x", part=1)], total_parts=1)
        easy = Book(id="easy", title="Easy", author="", year=2026, level="A1", intro_en="",
                    units=[Unit(n=1, de="Ich bin hier. Das ist gut.", en="x", part=1)], total_parts=1)
        content.books = [hard, easy]
        self.ctx.content = content

    def test_a_new_kid_starts_with_a_book_they_can_read(self):
        self.assertEqual(reading.current_book(self.ctx).id, "easy")

    def test_a_book_already_started_stays_open(self):
        self.ctx.profile.book_state("hard")["next"] = 1
        self.ctx.profile.data["current_book"] = "hard"
        self.assertEqual(reading.current_book(self.ctx).id, "hard")

    def test_missing_words_are_taught_first_and_queued(self):
        with mock.patch("app.ui.keys", return_value=""), mock.patch("app.ui.clear"), console.capture() as out:
            reading._words_you_need(self.ctx, self.ctx.content.books[0])
        self.assertIn("der Hund", out.get())
        self.assertEqual(self.ctx.profile.data["reading_words"], ["fahren", "hund", "garten"])


if __name__ == "__main__":
    unittest.main()
