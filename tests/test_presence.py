"""Finding each other on the Wi-Fi: who's online, "… just finished" news, challenges."""
import json
import socket
import time
import unittest
from unittest import mock

from app import presence

TODAY = "2026-09-20"


def summary(**kw):
    return {"date": TODAY, "warmups": 0, "words": 0, "right": 0, "paragraphs": 0, "minutes": 0, "streak": 0, **kw}


def packet(peer_id="ben1", name="Ben", status="on the menu", today=None, **extra):
    return json.dumps({"app": presence.APP, "v": presence.VERSION, "id": peer_id, "name": name, "status": status,
                       "today": today or summary(), "duel_port": 50505, **extra}).encode()


class News(unittest.TestCase):
    def setUp(self):
        self.p = presence.Presence("Anna")
        self.p.today = summary()

    def test_online_and_just_finished(self):
        self.p.receive(packet(), "192.168.1.7")
        self.assertEqual([(o["name"], o["ip"]) for o in self.p.online()], [("Ben", "192.168.1.7")])
        self.assertEqual(self.p.take_news(), [])  # nothing done yet: no news
        self.p.receive(packet(today=summary(warmups=1, words=40, right=38, minutes=14, streak=6)), "192.168.1.7")
        news = self.p.take_news()
        self.assertEqual(len(news), 1)
        self.assertIn("Ben just finished a warm-up: 38 of 40 words right · 14 min · 6 days in a row. Your turn!", news[0])
        self.p.receive(packet(today=summary(warmups=1, words=40, right=38, paragraphs=1)), "192.168.1.7")
        self.assertIn("just finished a new paragraph", self.p.take_news()[0])
        self.assertEqual(self.p.take_news(), [])  # news is shown once

    def test_someone_who_practised_before_we_met(self):
        self.p.receive(packet(today=summary(warmups=1, words=20, right=15)), "10.0.0.3")
        self.assertIn("Ben has practised today already: 15 of 20 words right", self.p.take_news()[0])

    def test_other_days_and_rubbish_are_ignored(self):
        self.p.receive(packet(today={**summary(warmups=3), "date": "2026-09-19"}), "10.0.0.3")
        self.assertEqual(self.p.take_news(), [])
        for bad in (b"not json", b"[1]", json.dumps({"app": "other"}).encode(), packet(name=""),
                    packet(peer_id=self.p.id), packet(today=summary(warmups="lots"))):
            self.p.receive(bad, "10.0.0.3")
        self.assertEqual(self.p.take_news(), [])

    def test_results_stay_after_they_go_offline(self):
        self.p.receive(packet(today=summary(warmups=1, words=10, right=9)), "10.0.0.3")
        self.p.receive(packet(status="offline", today=summary(warmups=1, words=10, right=9)), "10.0.0.3")
        self.assertEqual(self.p.online(), [])
        self.assertEqual(self.p.seen_today["Ben"]["right"], 9)

    def test_gone_after_a_while(self):
        self.p.receive(packet(), "10.0.0.3")
        later = time.monotonic() + presence.GONE_AFTER + 1
        with mock.patch("app.presence.time.monotonic", lambda: later):
            self.assertEqual(self.p.online(), [])


class Challenges(unittest.TestCase):
    def test_challenge_accept_and_not_again(self):
        ben = presence.Presence("Ben")
        ben.today = summary()
        invite = {"id": "inv1", "to": ben.id}
        ben.receive(packet(peer_id="anna1", name="Anna", invite=invite), "192.168.1.5")
        self.assertIn("Anna challenges you to a duel", ben.take_news()[0])
        [pending] = ben.pending_invites()
        self.assertEqual((pending["name"], pending["ip"], pending["port"]), ("Anna", "192.168.1.5", 50505))
        with mock.patch.object(ben, "_announce"):
            accepted = ben.answer("inv1", True)
        self.assertEqual(accepted["ip"], "192.168.1.5")
        self.assertEqual(ben.message()["reply"], {"id": "inv1", "accept": True})
        ben.receive(packet(peer_id="anna1", name="Anna", invite=invite), "192.168.1.5")  # still announced
        self.assertEqual(ben.pending_invites(), [])  # but not asked again

    def test_the_challenger_hears_the_answer(self):
        anna = presence.Presence("Anna")
        anna.receive(packet(), "192.168.1.7")
        with mock.patch.object(anna, "_announce"):
            invite_id = anna.challenge("ben1")
        self.assertEqual(anna.message()["invite"], {"id": invite_id, "to": "ben1"})
        self.assertIsNone(anna.challenge_answer(invite_id))
        anna.receive(packet(reply={"id": invite_id, "accept": False}), "192.168.1.7")
        self.assertIs(anna.challenge_answer(invite_id), False)

    def test_challenges_for_someone_else_are_ignored(self):
        ben = presence.Presence("Ben")
        ben.receive(packet(peer_id="anna1", name="Anna", invite={"id": "x", "to": "someone-else"}), "10.0.0.2")
        self.assertEqual(ben.pending_invites(), [])


class OverTheNetwork(unittest.TestCase):
    def test_two_apps_find_each_other(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]
        with mock.patch.object(presence, "ANNOUNCE_EVERY", 0.3):
            anna, ben = presence.Presence("Anna", port=port), presence.Presence("Ben", port=port)
            if anna.start() or ben.start():
                self.skipTest("no network to broadcast on")
            try:
                ben.set_today(summary(warmups=1, words=5, right=5))
                deadline = time.monotonic() + 5
                while not anna.online() and time.monotonic() < deadline:
                    time.sleep(0.1)
                if not anna.online():
                    self.skipTest("this network doesn't pass broadcasts (e.g. no network adapter)")
                self.assertEqual(anna.online()[0]["name"], "Ben")
            finally:
                anna.stop()
                ben.stop()


class Describe(unittest.TestCase):
    def test_describe(self):
        self.assertEqual(presence.describe("Ben", summary(words=40, right=38, paragraphs=2, minutes=14, streak=1)),
                         "38 of 40 words right · 2 paragraphs · 14 min · 1 day in a row")
        self.assertEqual(presence.describe("Ben", summary()), "just started")


if __name__ == "__main__":
    unittest.main()
