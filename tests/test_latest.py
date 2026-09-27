"""gtutor --latest: update first, then start (again as a new process when the app changed)."""
import unittest
from unittest import mock

from app import update
from app.ui import console


class Latest(unittest.TestCase):
    def run_latest(self, versions, update_code=0):
        versions = iter(versions)
        with mock.patch("app.update.version", lambda: next(versions)), \
                mock.patch("app.update.run_update", lambda: update_code), \
                mock.patch("app.update.subprocess.run", return_value=mock.Mock(returncode=7)) as run, \
                console.capture():
            return update.start_latest(["--latest", "--profile", "ben"]), run

    def test_changed_app_starts_again_as_a_new_process(self):
        code, run = self.run_latest(["aaa", "bbb"])
        self.assertEqual(code, 7)
        self.assertEqual(run.call_args[0][0][-2:], ["--profile", "ben"])  # without --latest: no loop

    def test_up_to_date_or_offline_starts_right_here(self):
        self.assertIsNone(self.run_latest(["aaa", "aaa"])[0])
        self.assertIsNone(self.run_latest(["aaa"], update_code=1)[0])  # no internet: the version that's here
        self.assertIsNone(self.run_latest(["", ""])[0])                # not a git copy


if __name__ == "__main__":
    unittest.main()
