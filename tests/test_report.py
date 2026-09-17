import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from app import profile as profile_module, report, ui
from app.profile import Profile


class PracticeTime(unittest.TestCase):
    def test_long_pause_counts_as_idle_limit(self):
        with mock.patch("app.ui.time.monotonic", side_effect=[0, 10, 10 + 3600]):
            ui.start_clock()
            ui._tick()  # an answer after 10 s
            self.assertEqual(ui.clock_seconds(), 10 + ui.IDLE_LIMIT)  # then an hour away

    def test_time_only_added_on_practised_days(self):
        p = Profile(Path("x.json"), {"name": "x"})
        today = date(2026, 9, 17)
        p.add_time(today, 120)
        self.assertEqual(p.data["days"], {})
        p.count(today, words=1)
        p.add_time(today, 120)
        p.add_time(today, 60)
        self.assertEqual(p.day(today)["seconds"], 180)


class Report(unittest.TestCase):
    def test_report_for_one_kid(self):
        today = date.today()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(profile_module, "PROFILES_DIR", Path(tmp)):
            kid = Profile.open_or_create("Anna")
            kid.count(today, words=12, right=9, units=1)
            kid.add_time(today, 900)
            kid.count(today - timedelta(days=40), words=5)
            kid.data["vocab"]["missing-word"] = {"box": 1, "wrong": 7, "right": 0}  # not in the bank: ignored
            kid.save()
            kid.add_journal({"date": f"{today}T10:00", "book": "nope", "unit": 3, "task": "de2en",
                             "answer": "The dog runs.", "self_grade": "mostly right"})
            before = kid.path.read_bytes()
            with ui.console.capture() as out:
                self.assertEqual(report.run_report("anna"), 0)
                self.assertEqual(report.run_report("Ben"), 1)
            text = out.get()
            self.assertIn("1 of 7 days · 15 min", text)
            self.assertIn("The dog runs.", text)
            self.assertIn("Anna hasn't missed any words yet.", text)
            self.assertIn("Anna's last 5 translations", text)
            self.assertIn("No profile called Ben.", text)
            self.assertEqual(kid.path.read_bytes(), before)  # the report changes nothing


if __name__ == "__main__":
    unittest.main()
