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


class PreparedPronunciations(unittest.TestCase):
    """With Piper's pronunciation helper blocked, the real voice still speaks, from the prepared file."""

    def setUp(self):
        from app.config import VOICES_DIR
        if not (VOICES_DIR / "de_DE-thorsten-medium.onnx").exists():
            self.skipTest("the Piper voice isn't downloaded here")

    def test_the_real_voice_speaks_with_its_helper_blocked(self):
        import piper.voice
        a = bare_audio(voice="de_DE-thorsten-medium")
        with mock.patch.object(piper.voice.PiperVoice, "phonemize", side_effect=BLOCKED):
            problem = a._init_piper()
            self.assertEqual(problem, "")        # no problem to report: the voice works
            samples, rate = a.synthesize("Ich bin heute zu spät aufgewacht.", 1.0)
        self.assertGreater(len(samples) / rate, 1.0)  # real speech, over a second long

    def test_the_prepared_file_covers_the_content(self):
        """New content without `python tools/phoneme_cache.py` fails here (words still work, sentences sound better)."""
        from app.content import load_content
        from app.exams import load_exams
        from app.phonemes import PhonemeCache, speech_texts
        cache = PhonemeCache.load()
        self.assertIsNotNone(cache)
        self.assertGreaterEqual(cache.coverage(speech_texts(load_content(), load_exams()[0])), 0.99,
                                "run python tools/phoneme_cache.py")

class SpeechCheckFallback(unittest.TestCase):
    def test_a_blocked_speech_checker_falls_back_to_windows_recognition(self):
        from app import listen
        fake = object()
        with mock.patch("app.listen.MODEL_DIR", Path(".")),                 mock.patch("app.listen.Listener", side_effect=ImportError("An Application Control policy has blocked this file.")),                 mock.patch("app.listen.os.name", "nt"), mock.patch("app.sysrecognize.WindowsRecognizer", return_value=fake):
            self.assertEqual(listen.load(), (fake, ""))

    def test_without_windows_recognition_it_says_what_to_add(self):
        from app import listen
        with mock.patch("app.listen.MODEL_DIR", Path(".")),                 mock.patch("app.listen.Listener", side_effect=ImportError("An Application Control policy has blocked this file.")),                 mock.patch("app.listen.os.name", "nt"),                 mock.patch("app.sysrecognize.WindowsRecognizer", side_effect=RuntimeError("no German recognizer")):
            listener, problem = listen.load()
        self.assertIsNone(listener)
        self.assertIn("Windows blocked the speech checker", problem)
        self.assertIn("German speech pack", problem)


class PreparedPictures(unittest.TestCase):
    def test_every_picture_has_a_ready_made_png_and_it_is_used_when_the_renderer_is_blocked(self):
        from app import pictures
        svgs = sorted(pictures.IMAGES_DIR.rglob("*.svg"))
        self.assertTrue(svgs)
        missing = [str(s) for s in svgs if not s.with_suffix(".png").exists()]
        self.assertEqual(missing, [], "run python tools/render_pictures.py")
        pictures.render.cache_clear()
        with mock.patch.dict(sys.modules, {"resvg_py": None}):
            pixels = pictures.render(str(svgs[0]), 40)
        pictures.render.cache_clear()
        self.assertEqual(pixels.shape[1], 40)


if __name__ == "__main__":
    unittest.main()
