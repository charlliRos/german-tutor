"""A stop in the middle of a text asks first; a stop on a dictation's last screen doesn't repeat it."""
import tempfile
import unittest
from unittest import mock

from app import reading, resume, ui
from app.ui import QuitSession, console
from tests.test_flows import make_ctx


class StopInAText(unittest.TestCase):
    def write(self, typed, key):
        lines = iter(typed)
        with mock.patch("app.ui.ask_answer", lambda prompt, on_idle=None: next(lines)), \
                mock.patch("app.ui._read", lambda *a, **k: next(lines)), \
                mock.patch("app.ui.keys", lambda options: key), console.capture():
            return ui.ask_multiline("Your text:")

    def test_q_in_the_middle_keeps_the_text_when_they_keep_writing(self):
        self.assertEqual(self.write(["Hallo Anna,", "q", "wie geht's?", "", ""], ""), "Hallo Anna,\nwie geht's?")

    def test_q_then_stop_really_stops(self):
        with self.assertRaises(QuitSession):
            self.write(["Hallo Anna,", "q"], "s")


class StopAfterADictation(unittest.TestCase):
    def test_a_stop_on_the_last_screen_records_the_look_back_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            book = ctx.content.books[0]
            unit = book.units[0]
            item = {"sessions_left": 1, "due_days": [], "misses": 0}
            ctx.profile.data["paragraph_reviews"][f"{book.id}:{unit.n}"] = item

            def keys(options):
                if "hear it again" in options.values():
                    raise QuitSession
                return ""

            with mock.patch("app.reading._review_task", lambda ctx, last: "dictation"), \
                    mock.patch("app.ui.ask_answer", lambda prompt, on_idle=None: unit.de), \
                    mock.patch("app.ui.keys", keys), mock.patch("app.ui.clear", lambda: None), \
                    mock.patch("app.reading.hear", lambda *a, **k: None), console.capture():
                with self.assertRaises(QuitSession):
                    reading.review(ctx, book, unit, item, 1, 1)
            day = ctx.profile.day(ctx.today)
            self.assertEqual((day.get("dictations"), day.get("reviews")), (1, 1))  # counted once
            self.assertIn(f"{book.id}:{unit.n}", resume.part(ctx, "reading")["looked_back"])  # not asked again


if __name__ == "__main__":
    unittest.main()
