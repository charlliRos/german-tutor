"""After an answer the next question starts by itself, and recording starts without pressing Enter."""
import tempfile
import unittest
from unittest import mock

import numpy as np

from app import speaking, ui, warmup
from app.answers import WRONG, Check
from app.content import Word
from app.ui import console
from tests.test_flows import make_ctx

TERMINAL = mock.patch.object(type(console), "is_terminal", new_callable=mock.PropertyMock, return_value=True)


class TimedKeys(unittest.TestCase):
    def test_goes_on_by_itself_when_no_key_is_pressed(self):
        with TERMINAL, mock.patch("app.ui.key_pressed", return_value=False), \
                mock.patch("app.ui._enter_held", return_value=False), mock.patch("app.ui.keys") as keys, console.capture():
            self.assertEqual(ui.timed_keys({"": "next", "o": "my answer was right too"}, 0.05), "")
        keys.assert_not_called()

    def test_a_key_stops_the_clock_and_asks(self):
        ui._last_key[0] = 0.0
        with TERMINAL, mock.patch("app.ui.key_pressed", return_value=True), \
                mock.patch("app.ui._enter_held", return_value=False), \
                mock.patch("app.ui.keys", return_value="o") as keys, console.capture() as out:
            self.assertEqual(ui.timed_keys({"": "next", "o": "my answer was right too"}, 5), "o")
        keys.assert_called_once()
        self.assertIn("o = my answer was right too", out.get())


class NoEnterNeeded(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)

    def test_recording_starts_after_a_countdown_not_an_enter(self):
        self.ctx.audio = mock.Mock(last_peak=1.0)
        self.ctx.audio.record_seconds.return_value = (np.ones(100), 16000)
        with mock.patch("app.ui.ask") as ask, mock.patch("app.speaking.time.sleep"), \
                mock.patch("app.sfx.play") as beep, console.capture():
            recording = speaking._record(self.ctx, "die Brücke", long_text=False)
        ask.assert_not_called()
        beep.assert_called_once_with(self.ctx.audio, "go")
        self.assertIsNotNone(recording)

    def test_a_wrong_answer_goes_on_to_the_next_question_by_itself(self):
        word = Word("w1", "daily", "die Brücke", ["bridge"], "noun")
        with mock.patch("app.ui.keys") as keys, mock.patch("app.warmup.sfx.play"), console.capture():
            outcome = warmup._result(self.ctx, word, "die Brucke", Check(WRONG, "x"), False, "", "en2de")
        self.assertEqual(outcome, WRONG)
        keys.assert_not_called()


if __name__ == "__main__":
    unittest.main()
