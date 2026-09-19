"""Duel over the local network: scoring, the connection, and a whole round between two players."""
import random
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

from app import duel, lan
from app.answers import ALMOST, CORRECT, WRONG
from app.ui import console
from tests.test_flows import make_ctx


def question(de="der Hund", en=("dog",), direction="en2de"):
    return {"word": {"id": "x", "bank": "daily", "de": de, "en": list(en), "pos": "noun", "de_alt": []},
            "direction": direction}


class Scoring(unittest.TestCase):
    def test_points(self):
        self.assertEqual(duel.points(CORRECT, 1.0), 150)   # fast: full bonus
        self.assertEqual(duel.points(CORRECT, 30.0), 100)  # slow: no bonus
        self.assertEqual(duel.points(ALMOST, 1.0), 50)
        self.assertEqual(duel.points(WRONG, 1.0), 0)

    def test_score_uses_the_normal_answer_checks(self):
        qs = [question(), question(direction="de2en")]
        self.assertEqual(duel.score(qs, [{"answer": "der Hund", "seconds": 1}, {"answer": "dog", "seconds": 1}]), 300)
        self.assertEqual(duel.score(qs, [{"answer": "Hund", "seconds": 1}]), 50)  # article missing: almost
        self.assertEqual(duel.score(qs, [{"answer": 5}, "nonsense", {"seconds": "x"}]), 0)  # broken answers: 0

    def test_results_and_draw(self):
        qs = [question()]
        right, nothing = [{"answer": "der Hund", "seconds": 1}], [{"answer": "", "seconds": 1}]
        self.assertEqual(duel.results(("A", "B"), qs, (nothing, right))["winner"], "B")
        self.assertIsNone(duel.results(("A", "B"), qs, (right, right))["winner"])

    def test_shared_words_first_then_common_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            picked = duel.pick_questions(ctx.content, {"w5", "w6", "w7"}, {"w6", "w7", "w8"}, random.Random(1), 4)
            ids = [q["word"]["id"] for q in picked]
            self.assertEqual(len(ids), 4)
            self.assertTrue({"w6", "w7"} <= set(ids))
            self.assertTrue(all(q["direction"] in ("en2de", "de2en") for q in picked))

    def test_board_fits_on_the_screen(self):
        width = console.width
        console.width = 60
        try:
            lines = duel.board_lines(duel.Standing(5, 10, 850), duel.Standing(7, 10, 790), "Gustav")
        finally:
            console.width = width
        self.assertEqual(len(lines), 4)
        self.assertTrue(all(len(line) < 60 for line in lines))
        self.assertIn("Score: 850", lines[1])
        self.assertIn("Progress: 70%", lines[2])

    def test_nonsense_progress_is_ignored(self):
        s = duel.Standing()
        self.assertFalse(s.update({"type": "progress", "done": "many"}))
        self.assertTrue(s.update({"type": "progress", "done": 3, "total": 10, "score": 300}))


class Connection(unittest.TestCase):
    def pair(self):
        a, b = socket.socketpair()
        return lan.Connection(a), b

    def test_messages_and_broken_lines(self):
        conn, other = self.pair()
        other.sendall(b'{"type": "progress", "done": 1}\nnot json\n[1, 2]\n{"no": "type"}\n\n{"type": "ping"}\n')
        self.assertEqual(conn.receive(2)["type"], "progress")
        self.assertEqual(conn.receive(2)["type"], "ping")
        self.assertEqual(conn.bad_messages, 3)
        self.assertTrue(conn.send({"type": "bye"}))
        self.assertIn(b'"bye"', other.recv(100))
        other.close()
        self.assertEqual(conn.receive(2)["type"], lan.CLOSED)

    def test_too_many_broken_lines_ends_it(self):
        conn, other = self.pair()
        other.sendall(b"garbage\n" * (lan.MAX_BAD_MESSAGES + 5))
        message = conn.receive(2)
        self.assertEqual(message["type"], lan.CLOSED)
        self.assertIn("understand", message["reason"])
        other.close()

    def test_join_errors(self):
        with self.assertRaises(lan.LanError) as refused:
            lan.join("127.0.0.1", free_port())  # Windows takes ~2 s to refuse a local connection
        self.assertIn("Nobody is hosting", str(refused.exception))
        with self.assertRaises(lan.LanError) as internet:
            lan.join("8.8.8.8")
        self.assertIn("local network", str(internet.exception))
        self.assertTrue(lan.local_address("192.168.1.23") and lan.local_address("10.0.0.5"))
        self.assertFalse(lan.local_address("8.8.8.8") or lan.local_address("not an ip"))

    def test_the_result_is_shown_even_if_goodbye_comes_right_after(self):
        conn, other = self.pair()
        rnd = duel.Round(None, conn, [question()], "Gustav", "Hanna")
        other.sendall(b'{"type": "result", "names": ["Hanna", "Gustav"], "scores": [1, 0], "winner": "Hanna"}\n'
                      b'{"type": "bye"}\n')
        time.sleep(0.3)
        with console.capture():
            self.assertEqual(rnd.wait_for("result", "waiting")["winner"], "Hanna")
        self.assertEqual(rnd.gone, "Hanna ended the duel")
        other.close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WholeDuel(unittest.TestCase):
    """Host and guest in two threads over a real local connection: the host answers right, the guest doesn't."""

    def test_host_and_join(self):
        port = free_port()
        shown = {}

        def ask(self, i, q):
            if threading.current_thread().name == "host":
                return q["word"]["de"] if q["direction"] == "en2de" else q["word"]["en"][0]
            return ""

        def keys(options):
            return "q" if threading.current_thread().name == "host" and "q" in options else ""

        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            host_ctx, guest_ctx = make_ctx(tmp1), make_ctx(tmp2)
            host_ctx.profile.data["name"], guest_ctx.profile.data["name"] = "Hanna", "Gustav"
            with mock.patch.object(duel, "COUNTDOWN", 0), mock.patch.object(duel, "FEEDBACK_SECONDS", 0), \
                    mock.patch.object(duel.Round, "ask", ask), mock.patch("app.ui.keys", keys), \
                    mock.patch("app.ui.clear", lambda: None), mock.patch("app.ui.key_pressed", lambda: False), \
                    mock.patch("app.duel.show_results",
                               lambda result, me: shown.__setitem__(threading.current_thread().name, result)), \
                    console.capture():
                host = threading.Thread(target=duel.run_host, args=(host_ctx, port), name="host")
                host.start()
                time.sleep(0.5)
                guest = threading.Thread(target=duel.run_join, args=(guest_ctx, "127.0.0.1", port), name="guest")
                guest.start()
                host.join(30)
                guest.join(30)
        self.assertFalse(host.is_alive() or guest.is_alive())
        self.assertEqual(shown["host"], shown["guest"])  # the host's result, the same on both screens
        self.assertEqual(shown["host"]["names"], ["Hanna", "Gustav"])
        self.assertEqual(shown["host"]["winner"], "Hanna")
        self.assertGreaterEqual(shown["host"]["scores"][0], 10 * 100)
        self.assertEqual(shown["host"]["scores"][1], 0)


if __name__ == "__main__":
    unittest.main()
