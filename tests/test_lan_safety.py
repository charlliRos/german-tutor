"""Anyone on the Wi-Fi can send announcements and duel messages: nothing they send may crash the app, mess up
the screen, or make it keep unbounded amounts of data."""
import json
import unittest
from unittest import mock

from app import duel, lan, presence, ui
from app.ui import console
from tests.test_presence import TODAY, packet, summary


class CleanText(unittest.TestCase):
    def test_control_and_format_characters_are_removed(self):
        self.assertEqual(lan.clean_text("Ben\x1b[2J\x1b]0;hacked\x07", 30), "Ben [2J ]0;hacked")
        self.assertEqual(lan.clean_text("Max‮evil", 30), "Max evil")  # right-to-left override
        self.assertEqual(lan.clean_text("  Anna \n Lena ", 30), "Anna Lena")
        self.assertEqual(lan.clean_text("Jürgen 😀", 30), "Jürgen 😀")  # letters and emoji stay
        self.assertEqual(lan.clean_text(["not", "text"], 30), "")
        self.assertEqual(len(lan.clean_text("x" * 500, 30)), 30)

    def test_deeply_nested_json_is_ignored_not_an_error(self):
        self.assertIsNone(lan.parse(b"[" * 60000))
        self.assertIsNone(lan.parse(b"\xff\xfe"))
        self.assertEqual(lan.parse(b'{"a": 1}'), {"a": 1})  # positive control


class HostileAnnouncements(unittest.TestCase):
    def setUp(self):
        self.p = presence.Presence("Anna")
        self.p.today = {"date": TODAY, **summary()}

    def test_escape_codes_in_a_name_never_reach_the_screen(self):
        self.p.receive(packet(name="Ben\x1b[2J", status="\x1b]0;x\x07reading"), "192.168.1.7")
        (peer,) = self.p.online()
        self.assertNotIn("\x1b", peer["name"] + peer["status"])

    def test_markup_in_a_name_doesnt_crash_the_duel_menu(self):
        self.p.receive(packet(name="[/x] Max [bold]"), "192.168.1.7")
        ctx = mock.Mock(presence=self.p)
        ctx.presence.to_play = lambda: []
        with mock.patch("app.ui._read", lambda prompt: ""), mock.patch("app.ui.clear"), console.capture() as out:
            duel.menu(ctx)
        self.assertIn("[/x] Max [bold]", out.get())

    def test_nested_junk_doesnt_stop_listening(self):
        self.p.receive(b"[" * 60000, "192.168.1.7")  # ignored, no exception
        self.p.receive(packet(), "192.168.1.7")
        self.assertEqual([o["name"] for o in self.p.online()], ["Ben"])

    def test_a_flood_of_fake_players_is_capped(self):
        for n in range(200):
            self.p.receive(packet(peer_id=f"fake{n}", name=f"Kid{n}", days={TODAY: summary(warmups=1)}),
                           "192.168.1.9")
        self.assertLessEqual(len(self.p.peers), presence.MAX_PEERS)
        self.assertLessEqual(len(self.p.friends), presence.MAX_FRIENDS)
        self.assertIn("Kid199", self.p.friends)  # the newest are kept

    def test_a_flood_of_challenges_is_capped(self):
        questions = [{"direction": "en2de", "word": {"de": "das Haus", "en": ["house"]}}]
        for n in range(100):
            challenges = [{"id": f"c{n}-{k}", "from": "Ben", "to": "Anna", "created": TODAY, "questions": questions}
                          for k in range(presence.MAX_SENT_CHALLENGES)]
            self.p.receive(packet(challenges=challenges), "192.168.1.7")
        self.assertLessEqual(len(self.p.challenges), presence.MAX_CHALLENGES_PER_KID)

    def test_challenge_words_are_cleaned(self):
        questions = [{"direction": "de2en", "word": {"de": "das Haus\x1b[31m", "en": ["house\x07"]}}]
        self.p.receive(packet(challenges=[{"id": "c1", "from": "Ben", "to": "Anna", "created": TODAY,
                                           "questions": questions}]), "192.168.1.7")
        word = self.p.challenges["c1"]["questions"][0]["word"]
        self.assertEqual((word["de"], word["en"]), ("das Haus [31m", ["house"]))


class HostileDuelHost(unittest.TestCase):
    def test_broken_questions_are_refused(self):
        self.assertIsNone(presence.clean_questions([{"direction": "en2de"}]))
        self.assertIsNone(presence.clean_questions([{"direction": "en2de", "word": {"de": "Haus", "en": "house"}}]))
        self.assertIsNone(presence.clean_questions([]))
        ok = presence.clean_questions([{"direction": "en2de", "word": {"de": "das Haus", "en": ["house"],
                                                                        "example_de": "Das Haus\x1b[2J ist alt."}}])
        self.assertEqual(ok[0]["word"]["example_de"], "Das Haus [2J ist alt.")
        duel.grade(ok[0], "das Haus")  # usable by the game

    def test_broken_results_are_refused(self):
        good = {"names": ["Anna", "Ben"], "scores": [1200, 900], "winner": "Anna"}
        self.assertEqual(duel.clean_result(good)["winner"], "Anna")
        self.assertEqual(duel.clean_result({**good, "names": [1, 2], "winner": None})["names"], ["Player 1", "Player 2"])
        self.assertIsNone(duel.clean_result({**good, "scores": ["a", 1]}))
        self.assertIsNone(duel.clean_result({**good, "winner": "Mallory"}))
        self.assertIsNone(duel.clean_result({**good, "scores": [1]}))

    def test_a_strange_line_ends_the_duel_cleanly(self):
        conn = lan.Connection.__new__(lan.Connection)
        conn.inbox, conn.bad_messages, conn.last_heard = __import__("queue").Queue(), 0, 0
        conn._handle_line(b"[" * 60000)
        conn._handle_line(json.dumps({"type": "ping"}).encode())
        self.assertEqual((conn.bad_messages, conn.inbox.get_nowait()["type"]), (1, "ping"))


class SharingIsOptIn(unittest.TestCase):
    def ctx(self, setting, **data):
        from app.profile import Profile
        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return mock.Mock(settings={"share_on_wifi": setting},
                         profile=Profile(Path(tmp.name) / "kid.json", {"name": "Kid", **data}))

    def test_each_kid_is_asked_once(self):
        from app.main import sharing_allowed
        ctx = self.ctx("ask")
        with mock.patch("app.ui.keys", return_value="n") as keys, mock.patch("app.ui.clear"), console.capture():
            self.assertFalse(sharing_allowed(ctx))
            self.assertFalse(sharing_allowed(ctx))
        self.assertEqual(keys.call_count, 1)
        self.assertIs(ctx.profile.data["share_on_wifi"], False)

    def test_yes_turns_it_on(self):
        from app.main import sharing_allowed
        with mock.patch("app.ui.keys", return_value="y"), mock.patch("app.ui.clear"), console.capture():
            self.assertTrue(sharing_allowed(self.ctx("ask")))

    def test_the_parents_setting_wins_without_asking(self):
        from app.main import sharing_allowed
        with mock.patch("app.ui.keys") as keys:
            self.assertFalse(sharing_allowed(self.ctx(False, share_on_wifi=True)))
            self.assertTrue(sharing_allowed(self.ctx(True, share_on_wifi=False)))
        keys.assert_not_called()

    def test_default_is_ask(self):
        from app.config import DEFAULTS
        self.assertEqual(DEFAULTS["share_on_wifi"], "ask")


if __name__ == "__main__":
    unittest.main()
