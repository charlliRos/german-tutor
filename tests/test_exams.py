"""Exam practice: exam files are checked, answers marked, results kept, and every answer logged."""
import tempfile
import unittest
from unittest import mock

from app import attempts, exam_practice, exams
from app.ui import console
from tests.test_flows import make_ctx

RAW = {
    "id": "t-01", "level": "A2", "style": "Goethe-Zertifikat A2", "title": "Test exam",
    "parts": [
        {"id": "lesen-1", "skill": "reading", "title_de": "Lesen, Teil 1", "minutes": 5,
         "texts": [{"id": "t1", "title": "Das Fest", "de": "Das Stadtfest ist am Samstag. Der Eintritt ist frei."}],
         "items": [
             {"id": "1", "type": "mc", "text": "t1", "question": "Das Fest ist am …",
              "options": {"a": "Freitag", "b": "Samstag", "c": "Sonntag"}, "answer": "b", "explain_en": "Samstag."},
             {"id": "2", "type": "tf", "text": "t1", "question": "Der Eintritt kostet 5 Euro.", "answer": "falsch",
              "explain_en": "It's free."},
         ]},
        {"id": "lesen-2", "skill": "reading", "title_de": "Lesen, Teil 2", "none_allowed": True,
         "texts": [{"id": "a", "title": "Fahrradkurs", "de": "Lerne Fahrräder reparieren."},
                   {"id": "b", "title": "Kochkurs", "de": "Wir kochen italienisch."}],
         "items": [
             {"id": "3", "type": "match", "question": "Tom möchte Pizza machen.", "answer": "b", "explain_en": "b."},
             {"id": "4", "type": "match", "question": "Lea möchte schwimmen.", "answer": "x", "explain_en": "None."},
         ]},
        {"id": "hoeren-1", "skill": "listening", "title_de": "Hören, Teil 1", "plays": 2,
         "texts": [{"id": "t1", "lines": [{"who": "Frau", "de": "Kommst du mit ins Kino?"},
                                          {"who": "Mann", "de": "Ja, gern."}]}],
         "items": [{"id": "1", "type": "yesno", "text": "t1", "question": "Geht der Mann mit?", "answer": "ja",
                    "explain_en": "He says gern."}]},
        {"id": "schreiben-1", "skill": "writing", "title_de": "Schreiben, Teil 1", "task_de": "Schreib an Anna.",
         "task_en": "Write to Anna.", "points": ["Dank", "Zeit", "Frage"], "words": [20, 30],
         "model_de": "Liebe Anna, danke …"},
    ],
}


class Checking(unittest.TestCase):
    def test_the_sample_is_fine(self):
        self.assertEqual(exams.check_exam(RAW, "t"), [])

    def test_mistakes_are_found(self):
        bad = {**RAW, "parts": [{**RAW["parts"][0], "items": [
            {**RAW["parts"][0]["items"][0], "answer": "d"},
            {**RAW["parts"][0]["items"][1], "text": "t9"},
            {"id": "1", "type": "mc", "question": "?", "options": {"a": "x", "b": "y"}, "answer": "a", "explain_en": "."},
        ]}, {**RAW["parts"][1], "none_allowed": False}]}
        problems = " | ".join(exams.check_exam(bad, "t"))
        for expected in ("answer 'd'", "text 't9'", "duplicate item id", "mc needs options a, b, c", "answer 'x'"):
            self.assertIn(expected, problems)

    def test_marking(self):
        exam = exams._exam(RAW)
        tf, match = exam.parts[0].items[1], exam.parts[1].items[1]
        self.assertTrue(exams.is_right(tf, "f"))
        self.assertFalse(exams.is_right(tf, "r"))
        self.assertTrue(exams.is_right(match, "x"))
        self.assertIn("x", exams.choices(match, exam.parts[1]))
        self.assertTrue(exams.passed(3, 5))
        self.assertFalse(exams.passed(2, 5))


class Doing(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        self.exam = exams._exam(RAW)
        for target in ("app.ui.clear", "app.exam_practice.sfx.play"):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_with(self, part, answers, **patches):
        queue = list(answers)

        def keys(options):
            return queue.pop(0) if ("?" in options or "y" in options) and queue else ""

        with mock.patch("app.ui.keys", keys), console.capture() as out:
            if part.skill == "writing":
                exam_practice.writing(self.ctx, self.exam, part)
            else:
                exam_practice.run_part(self.ctx, self.exam, part)
        return out.get()

    def test_reading_is_marked_saved_and_logged(self):
        part = self.exam.parts[0]
        out = self.run_with(part, ["b", "r"])  # right, wrong
        self.assertIn("1 of 2", out)
        self.assertIn("It's free.", out)  # the explanation of the mistake
        saved = self.ctx.profile.data["exams"]["t-01"]["lesen-1"]
        self.assertEqual((saved["score"], saved["max"], saved["best"], saved["tries"]), (1, 2, 1, 1))
        logged = [e for e in attempts.read(self.ctx.profile) if e["type"] == "attempt"]
        self.assertEqual([(e["item"], e["response"], e["score"]["correct"]) for e in logged],
                         [("t-01.lesen-1.1", "b", True), ("t-01.lesen-1.2", "r", False)])
        self.assertEqual(logged[0]["competency"], "exam.reading")
        self.run_with(part, ["a", "f"])  # a worse try doesn't lower the best
        self.assertEqual(self.ctx.profile.data["exams"]["t-01"]["lesen-1"]["best"], 1)

    def test_dont_know_is_no_response_not_wrong(self):
        self.run_with(self.exam.parts[1], ["?", "x"])
        logged = [e for e in attempts.read(self.ctx.profile) if e["type"] == "attempt"]
        self.assertEqual(logged[0]["score"], attempts.no_response("don't know"))
        self.assertTrue(logged[1]["score"]["correct"])

    def test_listening_without_sound_shows_the_recording(self):
        out = self.run_with(self.exam.parts[2], ["j"])
        self.assertIn("Kommst du mit ins Kino?", out)
        self.assertEqual(self.ctx.profile.data["exams"]["t-01"]["hoeren-1"]["score"], 1)

    def test_listening_match_reads_only_the_conversation(self):
        raw = {**RAW, "parts": [{"id": "hoeren-2", "skill": "listening", "title_de": "Hören, Teil 2", "plays": 1,
                                 "texts": [{"id": "talk", "lines": [{"who": "Tom", "de": "Am Montag spiele ich Fußball."}]},
                                           {"id": "a", "de": "Fußball"}, {"id": "b", "de": "Kino"}],
                                 "items": [{"id": "1", "type": "match", "text": "talk", "question": "Montag",
                                            "answer": "a", "explain_en": "Fußball."}]}]}
        self.assertEqual(exams.check_exam(raw, "t"), [])
        self.exam = exams._exam(raw)
        part = self.exam.parts[0]
        self.assertEqual(list(exams.choices(part.items[0], part)), ["a", "b"])
        self.ctx.audio.can_speak = True
        heard = []
        with mock.patch("app.exam_practice.hear", lambda ctx, text, slow=True: heard.append(text)),                 mock.patch("app.exam_practice.hear_lines", lambda ctx, lines: heard.append(" ".join(l["de"] for l in lines))):
            self.run_with(part, ["a"])
        self.assertEqual(heard, ["Am Montag spiele ich Fußball."])
        self.assertEqual(self.ctx.profile.data["exams"]["t-01"]["hoeren-2"]["score"], 1)

    def test_listening_with_sound_allows_one_replay(self):
        self.ctx.audio.can_speak = True
        heard = []
        with mock.patch("app.exam_practice.hear", lambda ctx, text, slow=True: heard.append(text)),                 mock.patch("app.exam_practice.hear_lines", lambda ctx, lines: heard.append(" ".join(l["de"] for l in lines))):
            self.run_with(self.exam.parts[2], [exam_practice.REPLAY, "n"])
        self.assertEqual(len(heard), 2)  # played once, heard again once (plays = 2)
        self.assertIn("Ja, gern.", heard[0])
        self.assertEqual(self.ctx.profile.data["exams"]["t-01"]["hoeren-1"]["score"], 0)

    def test_writing_is_self_checked_against_the_points(self):
        text = "Liebe Anna, vielen Dank für die Einladung. Ich komme um drei Uhr. Soll ich etwas mitbringen? Tschüss"
        with mock.patch("app.ui.ask_multiline", lambda prompt: text):
            out = self.run_with(self.exam.parts[3], ["y", "y", "n"])
        self.assertIn("2 of 3 points covered", out)
        (event,) = [e for e in attempts.read(self.ctx.profile) if e["type"] == "attempt"]
        self.assertEqual((event["item"], event["grader"], event["score"]["kind"], event["score"]["raw"]),
                         ("t-01.schreiben-1", attempts.SELF, "estimated", 2))
        self.assertEqual(event["response"], text)


class ShippedExams(unittest.TestCase):
    def test_every_exam_file_is_valid(self):
        loaded, problems = exams.load_exams()
        self.assertEqual(problems, [])
        self.assertEqual({e.level for e in loaded}, {"A2", "B1"})  # positive control: the files were read
        for exam in loaded:
            self.assertTrue(exam.skill_parts("reading") and exam.skill_parts("listening"), exam.id)
            self.assertTrue(all(link["url"].startswith("https://") for link in exam.official_practice), exam.id)


class ParentReport(unittest.TestCase):
    def test_best_scores_per_skill_against_the_pass_mark(self):
        import json
        from pathlib import Path
        from app import report
        from app.profile import Profile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "exams"
            folder.mkdir()
            (folder / "t.json").write_text(json.dumps(RAW), encoding="utf-8")
            real = exams.load_exams
            result = lambda score, best, total: {"score": score, "max": total, "best": best, "last": "", "tries": 1}  # noqa: E731
            done = {"t-01": {"lesen-1": result(1, 2, 2), "lesen-2": result(1, 1, 2), "schreiben-1": result(2, 2, 3)}}
            with mock.patch("app.exams.load_exams", lambda: real(folder)):
                lines = report._exam_lines(Profile(Path(tmp) / "k.json", {"name": "K", "exams": done}))
                partial = report._exam_lines(Profile(Path(tmp) / "k.json", {"name": "K", "exams": {
                    "t-01": {"lesen-1": result(0, 0, 2)}}}))
        self.assertEqual(lines, ["A2 Test exam: Lesen 3/4 [good]pass[/] · Schreiben: 1 task(s) done"])
        self.assertEqual(partial, ["A2 Test exam: Lesen 0/2 (some parts)"])  # no pass/fail on half a module


class Voices(unittest.TestCase):
    def test_speakers_get_voices_they_can_be_told_apart_by(self):
        from app.speaking import voices_for
        self.assertEqual(voices_for(["Frau", "Mann"]), {"Frau": "high", "Mann": ""})
        self.assertEqual(voices_for(["Tom", "Lena", "Jonas", "Sophie"]),
                         {"Tom": "", "Lena": "high", "Jonas": "low", "Sophie": "higher"})
        self.assertEqual(voices_for(["Moderatorin", "Herr Brandt"]), {"Moderatorin": "high", "Herr Brandt": ""})

    def test_a_voice_keeps_normal_speed_and_changes_pitch(self):
        from types import SimpleNamespace
        import numpy as np
        from app import audio
        a = audio.Audio.__new__(audio.Audio)
        a._cache = {}
        a._synthesis_config = lambda length_scale: SimpleNamespace(length_scale=length_scale)
        # A fake voice: 1 second of sound per unit of length_scale at 22050 Hz.
        a.voice = SimpleNamespace(synthesize=lambda text, config: [SimpleNamespace(
            sample_rate=22050, audio_float_array=np.zeros(int(22050 * config.length_scale), np.float32))])
        plain, plain_rate = a.synthesize("Hallo", 1.0)
        high, high_rate = a.synthesize("Hallo", 1.0, "high")
        self.assertAlmostEqual(len(high) / high_rate, len(plain) / plain_rate, delta=0.08)  # same length
        self.assertGreater(high_rate, plain_rate)  # played faster than it was made: higher pitch

if __name__ == "__main__":
    unittest.main()
