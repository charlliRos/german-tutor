"""Finding each other on the Wi-Fi: who's online, "… just finished" news, challenges."""
import json
import socket
import time
import unittest
from unittest import mock

from app import presence

TODAY = "2026-09-20"
YESTERDAY = "2026-09-19"


def summary(**kw):
    return {"warmups": 0, "words": 0, "right": 0, "paragraphs": 0, "minutes": 0, **kw}


def packet(peer_id="ben1", name="Ben", status="on the menu", days=None, streak=0, **extra):
    return json.dumps({"app": presence.APP, "v": presence.VERSION, "id": peer_id, "name": name, "status": status,
                       "today": TODAY, "streak": streak, "days": days if days is not None else {TODAY: summary()},
                       "duel_port": 50505, **extra}).encode()


class News(unittest.TestCase):
    def setUp(self):
        self.p = presence.Presence("Anna")
        self.p.today = {"date": TODAY, **summary()}

    def test_online_and_just_finished(self):
        self.p.receive(packet(), "192.168.1.7")
        self.assertEqual([(o["name"], o["ip"]) for o in self.p.online()], [("Ben", "192.168.1.7")])
        self.assertEqual(self.p.take_news(), [])  # nothing done yet: no news
        self.p.receive(packet(days={TODAY: summary(warmups=1, words=40, right=38, minutes=14)}, streak=6),
                       "192.168.1.7")
        news = self.p.take_news()
        self.assertEqual(len(news), 1)
        self.assertIn("Ben just finished a warm-up: 38 of 40 words right · 14 min · 6 days in a row. Your turn!", news[0])
        self.p.receive(packet(days={TODAY: summary(warmups=1, words=40, right=38, paragraphs=1)}), "192.168.1.7")
        self.assertIn("just finished a new paragraph", self.p.take_news()[0])
        self.p.receive(packet(days={TODAY: summary(warmups=1, words=40, right=38, paragraphs=1)}), "192.168.1.7")
        self.assertEqual(self.p.take_news(), [])  # the same state again: no news again

    def test_someone_who_practised_before_we_met(self):
        self.p.receive(packet(days={YESTERDAY: summary(warmups=1, words=9, right=9),
                                    TODAY: summary(warmups=1, words=20, right=15)}), "10.0.0.3")
        news = self.p.take_news()
        self.assertEqual(len(news), 1)  # first meeting: today only, not the whole week
        self.assertIn("Ben has practised today already: 15 of 20 words right", news[0])

    def test_catching_up_after_being_away(self):
        # We met Ben on the 17th; the profile kept that. Now, on the 20th, Ben tells us about the 19th too.
        self.p.remember({"Ben": {"2026-09-17": summary(warmups=1, words=10, right=8)}}, ["10.0.0.3"])
        self.p.receive(packet(days={"2026-09-17": summary(warmups=1, words=10, right=8),
                                    YESTERDAY: summary(warmups=1, words=30, right=27, paragraphs=1)}), "10.0.0.3")
        news = self.p.take_news()
        self.assertEqual(len(news), 1)
        self.assertIn("While you were away, Ben practised on Sat 19 Sep: 27 of 30 words right · 1 paragraph", news[0])
        friends, addresses, _ = self.p.keep()
        self.assertEqual(friends["Ben"][YESTERDAY]["right"], 27)  # kept for next time
        self.assertEqual(addresses, ["10.0.0.3"])

    def test_wrong_dates_and_rubbish_are_ignored(self):
        self.p.receive(packet(days={"2026-09-21": summary(warmups=3)}), "10.0.0.3")  # a day in the future
        self.p.receive(packet(days={TODAY: summary(warmups="lots")}), "10.0.0.4")
        self.assertEqual(self.p.take_news(), [])
        for bad in (b"not json", b"[1]", json.dumps({"app": "other"}).encode(), packet(name=""),
                    packet(peer_id=self.p.id), packet(days="nonsense"), packet(days={TODAY: [1, 2]})):
            self.p.receive(bad, "10.0.0.3")
        self.assertEqual(self.p.take_news(), [])

    def test_results_stay_after_they_go_offline(self):
        self.p.receive(packet(days={TODAY: summary(warmups=1, words=10, right=9)}), "10.0.0.3")
        self.p.receive(packet(status="offline", days={TODAY: summary(warmups=1, words=10, right=9)}), "10.0.0.3")
        self.assertEqual(self.p.online(), [])
        self.assertEqual(self.p.friends_today()["Ben"]["right"], 9)

    def test_addresses_are_remembered_and_sent_to(self):
        self.p.receive(packet(), "192.168.1.7")
        sent = []
        self.p.sock = mock.Mock(sendto=lambda data, target: sent.append(target[0]))
        self.p._announce()
        self.assertEqual(sent, ["255.255.255.255", "192.168.1.7"])

    def test_gone_after_a_while(self):
        self.p.receive(packet(), "10.0.0.3")
        later = time.monotonic() + presence.GONE_AFTER + 1
        with mock.patch("app.presence.time.monotonic", lambda: later):
            self.assertEqual(self.p.online(), [])


class Challenges(unittest.TestCase):
    def test_challenge_accept_and_not_again(self):
        ben = presence.Presence("Ben")
        ben.today = {"date": TODAY, **summary()}
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


def challenge(**kw):
    return {"id": "ch1", "from": "Anna", "to": "Ben", "created": TODAY, "answers": {},
            "questions": [{"direction": "en2de", "word": {"id": "w1", "de": "der Hund", "en": ["dog"], "pos": "noun"}},
                          {"direction": "de2en", "word": {"id": "w2", "de": "die Katze", "en": ["cat"], "pos": "noun"}}],
            **kw}


def app_for(name):
    p = presence.Presence(name)
    p.today = {"date": TODAY, **summary()}
    p._announce = lambda: None  # no network in these tests
    return p


def announce(sender, receiver, ip="192.168.1.9"):
    """What `receiver` hears when `sender` announces."""
    receiver.receive(json.dumps(sender.message()).encode(), ip)


class AsyncChallenges(unittest.TestCase):
    RIGHT = [{"answer": "der Hund", "seconds": 1.0}, {"answer": "cat", "seconds": 1.0}]  # 300 points
    HALF = [{"answer": "der Hund", "seconds": 1.0}, {"answer": "?", "seconds": 1.0}]    # 150 points

    def test_anna_plays_closes_the_app_and_ben_still_gets_it_later(self):
        anna = app_for("Anna")
        anna.add_challenge(challenge())
        anna.record_answers("ch1", self.RIGHT)
        # Anna closes the app: the profile keeps the challenge. Next time she opens it, it's sent again.
        friends, addresses, kept = anna.keep()
        anna = app_for("Anna")
        anna.remember(friends, addresses, kept)
        ben = app_for("Ben")
        announce(anna, ben)
        self.assertIn("Anna challenges you: 2 words, Anna scored 300. Beat it!", ben.take_news()[0])
        [waiting] = ben.to_play()
        self.assertEqual(waiting["id"], "ch1")
        announce(anna, ben)
        self.assertEqual(ben.take_news(), [])  # heard again: no news again
        ben.record_answers("ch1", self.HALF)
        self.assertEqual(ben.to_play(), [])
        self.assertEqual(presence.challenge_result(ben.my_challenges()[0], "Ben"), "Anna 300 · you 150: Anna wins!")
        announce(ben, anna)
        self.assertEqual(anna.take_news(), ["Ben played your challenge: Ben 150 · you 300: you win!"])

    def test_answers_are_written_once(self):
        ben = app_for("Ben")
        announce_raw = lambda c: ben.receive(packet(peer_id="anna1", name="Anna", challenges=[c]), "10.0.0.2")  # noqa: E731
        announce_raw(challenge(answers={"Anna": self.HALF}))
        announce_raw(challenge(answers={"Anna": self.RIGHT}))  # a changed score later: ignored
        self.assertEqual(presence.challenge_score(ben.my_challenges()[0], "Anna"), 150)

    def test_other_kids_and_broken_challenges_are_ignored(self):
        ben = app_for("Ben")
        broken = [challenge(to="Carla"), challenge(questions="x"), challenge(questions=[{"word": 1}]),
                  challenge(answers={"Anna": [{"answer": 5, "seconds": 1}]}), challenge(id=""), "nonsense"]
        ben.receive(packet(peer_id="anna1", name="Anna", challenges=broken), "10.0.0.2")
        self.assertEqual((ben.my_challenges(), ben.take_news()), ([], []))

    def test_old_challenges_are_not_offered(self):
        ben = app_for("Ben")
        ben.receive(packet(peer_id="anna1", name="Anna", challenges=[challenge(created="2026-09-01")]), "10.0.0.2")
        self.assertEqual((ben.to_play(), ben.take_news()), ([], []))


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
                ben.set_today({"date": TODAY, **summary(warmups=1, words=5, right=5), "streak": 1})
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
        self.assertEqual(presence.describe("Ben", summary(words=40, right=38, paragraphs=2, minutes=14) | {"streak": 1}),
                         "38 of 40 words right · 2 paragraphs · 14 min · 1 day in a row")
        self.assertEqual(presence.describe("Ben", summary()), "just started")


if __name__ == "__main__":
    unittest.main()
