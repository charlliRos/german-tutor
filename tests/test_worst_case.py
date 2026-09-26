"""The app keeps working on the most locked-down or bare computer: no sound library, no voice, no speech checker,
no picture renderer, a speaker or microphone that dies mid-lesson, or an unexpected error."""
import sys
import tempfile
import types
import unittest
from unittest import mock

from app import audio, exam_practice, exams, main, warmup
from app.answers import CORRECT
from app.ui import console
from tests.test_exams import RAW
from tests.test_flows import make_ctx

# Importing any of these fails, as if Windows blocked them or they have no build for this computer.
BLOCKED = {name: None for name in ("sounddevice", "piper", "piper.config", "vosk", "resvg_py")}


class WorstCase(unittest.TestCase):
    def test_everything_optional_missing_still_runs_a_lesson(self):
        with mock.patch.dict(sys.modules, BLOCKED):
            a = audio.Audio({"voice": "x", "speech_check": True, "word_speed": 1, "text_speed": 1,
                             "voice_engine": "piper"})
            self.assertFalse(a.can_speak or a.can_record)
            self.assertTrue(a.problems)  # it says what's missing
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            ctx = make_ctx(tmp.name)
            ctx.audio = a
            with mock.patch("app.ui.keys", lambda o: next((k for k in o if k not in ("", "?", "0", "t")), "")), \
                    mock.patch("app.ui.timed_keys", return_value=""), mock.patch("app.ui.clear"), \
                    mock.patch("app.ui.pause"), mock.patch("app.ui.ask", return_value=""), \
                    mock.patch("app.ui.ask_multiline", return_value="Liebe Anna, danke! Viele Grüße"), \
                    mock.patch("app.warmup.show_card"), mock.patch("app.warmup.quiz", return_value=CORRECT), \
                    console.capture():
                warmup.run_warmup(ctx)
                exam = exams._exam(RAW)
                for part in exam.parts:
                    exam_practice.do_part(ctx, exam, part)
                main.picture_check(ctx)
            self.assertEqual(ctx.profile.day(ctx.today)["warmups"], 1)
            self.assertEqual(set(ctx.profile.data["exams"]["t-01"]), {p.id for p in exam.parts})


class DevicesFailingMidLesson(unittest.TestCase):
    def audio_with(self, sd):
        a = audio.Audio.__new__(audio.Audio)
        a.settings, a.sd, a.problems, a.has_mic, a.last_peak = {}, sd, [], True, 0.0
        return a

    def test_speakers_that_stop_working_switch_sound_off(self):
        sd = types.SimpleNamespace(PortAudioError=OSError, play=mock.Mock(side_effect=RuntimeError("device gone")))
        a = self.audio_with(sd)
        self.assertFalse(a.play([0.0], 16000))
        self.assertIsNone(a.sd)
        self.assertIn("speakers stopped working", a.problems[0])

    def test_a_microphone_that_fails_gives_an_empty_recording(self):
        sd = types.SimpleNamespace(query_devices=mock.Mock(side_effect=RuntimeError("no input")))
        a = self.audio_with(sd)
        recording, rate = a.record_seconds(3)
        self.assertEqual(recording.size, 0)
        self.assertFalse(a.has_mic)


class Crashes(unittest.TestCase):
    def test_an_unexpected_error_is_logged_calmly(self):
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            with mock.patch("app.config.ROOT", Path(tmp)), console.capture() as out:
                try:
                    raise ZeroDivisionError("a bug")
                except ZeroDivisionError:
                    main.crash_note()
            log = (Path(tmp) / "data" / "crash.log").read_text(encoding="utf-8")
        self.assertIn("ZeroDivisionError: a bug", log)
        self.assertIn("Your progress is saved", out.get())
        self.assertNotIn("Traceback", out.get())


if __name__ == "__main__":
    unittest.main()
