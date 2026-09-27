"""The "your mic is very quiet" warning: only when the words weren't heard, and not for normal laptop mics."""
import unittest
from types import SimpleNamespace
from unittest import mock

from app import speaking
from app.audio import QUIET_PEAK


def ctx(peak: float, checking: bool = True):
    audio = SimpleNamespace(last_peak=peak, can_record=True, can_check_speech=checking)
    return SimpleNamespace(audio=audio)


class QuietMic(unittest.TestCase):
    def warned(self, c, heard: bool) -> bool:
        with mock.patch.object(speaking.console, "print") as out:
            speaking._quiet_warning(c, heard)
        return any("very quiet" in str(call) for call in out.call_args_list)

    def test_a_normal_laptop_mic_is_not_quiet(self):
        self.assertLess(QUIET_PEAK, 0.05)
        self.assertFalse(self.warned(ctx(0.05), heard=False))

    def test_heard_words_mean_the_mic_is_fine(self):
        self.assertFalse(self.warned(ctx(0.01), heard=True))

    def test_very_quiet_and_not_heard_warns(self):
        self.assertTrue(self.warned(ctx(0.01), heard=False))

    def test_without_a_speech_check_it_warns_once(self):
        c = ctx(0.01, checking=False)
        self.assertTrue(self.warned(c, heard=False))
        self.assertFalse(self.warned(c, heard=False))


if __name__ == "__main__":
    unittest.main()
