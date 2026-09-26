"""When Windows blocks the offline voice (Smart App Control), or any voice fails, the app never crashes: it uses
the computer's own German voice, or carries on without sound and says how to get it back."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from app import audio

BLOCKED = ImportError("DLL load failed while importing espeakbridge: An Application Control policy has blocked this file.")


def bare_audio(**settings) -> audio.Audio:
    a = audio.Audio.__new__(audio.Audio)
    a.settings = {"voice": "de_DE-thorsten-medium", "word_speed": 1.0, "text_speed": 1.0, **settings}
    a.sd, a.voice, a.sysvoice, a.problems, a._cache = object(), None, None, [], {}
    return a


class FakeSystemVoice:
    name = "Microsoft Katja"

    def speak(self, text, speed):
        return np.zeros(1600, np.float32), 16000


class BlockedPiper(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        (folder / "de_DE-thorsten-medium.onnx").write_bytes(b"x")
        voice = types.SimpleNamespace(synthesize=mock.Mock(side_effect=BLOCKED))
        piper = types.ModuleType("piper")
        piper.PiperVoice = types.SimpleNamespace(load=lambda model: voice)
        config = types.ModuleType("piper.config")
        config.SynthesisConfig = lambda **kw: types.SimpleNamespace(**kw)
        for patcher in (mock.patch.dict(sys.modules, {"piper": piper, "piper.config": config}),
                        mock.patch("app.audio.VOICES_DIR", folder)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_students_error_falls_back_to_the_system_voice(self):
        a = bare_audio()
        with mock.patch("app.sysvoice.open_voice", return_value=FakeSystemVoice()):
            a._init_voice()
        self.assertTrue(a.can_speak)
        self.assertIsNone(a.voice)
        self.assertIn("Windows blocked the offline German voice", a.problems[0])
        self.assertIn("Microsoft Katja", a.problems[0])
        samples, rate = a.synthesize("Hallo", 1.0)
        self.assertEqual(rate, 16000)

    def test_without_a_system_voice_it_carries_on_silently_and_says_how_to_fix_it(self):
        a = bare_audio()
        with mock.patch("app.sysvoice.open_voice", side_effect=RuntimeError("no German Windows voice is installed")), \
                mock.patch("app.sysvoice.install_hint", return_value="add Windows' German voice"):
            a._init_voice()
        self.assertFalse(a.can_speak)
        self.assertIn("add Windows' German voice", a.problems[0])
        self.assertFalse(a.say("Hallo"))  # no crash, just no sound

    def test_piper_only_setting_doesnt_try_the_system_voice(self):
        a = bare_audio(voice_engine="piper")
        with mock.patch("app.sysvoice.open_voice") as system:
            a._init_voice()
        system.assert_not_called()
        self.assertFalse(a.can_speak)


class FailingMidLesson(unittest.TestCase):
    def test_a_voice_that_fails_later_switches_itself_off(self):
        a = bare_audio()
        a.sysvoice = types.SimpleNamespace(name="x", speak=mock.Mock(side_effect=RuntimeError("the Windows voice stopped")))
        self.assertFalse(a.say("Hallo"))
        self.assertFalse(a.can_speak)
        self.assertIn("carries on without sound", a.problems[-1])
        self.assertFalse(a.say_lines([("", "Hallo")]))


class Blocked(unittest.TestCase):
    def test_recognises_windows_blocking(self):
        self.assertTrue(audio.blocked(BLOCKED))
        self.assertFalse(audio.blocked(ValueError("bad model")))


if __name__ == "__main__":
    unittest.main()
