"""Verbs, grammar, placement and the first run: fixes from the drill bug hunt."""
import json
import tempfile
import unittest
from unittest import mock

from app import grammar, main, placement, verbs
from app.answers import ALMOST
from app.content import Content, Verb, Word
from app.ui import QuitSession, console
from tests.test_flows import make_ctx
from tests.test_placement import ctx_with_bank


def sentence_ctx(tmp, sentences):
    ctx = make_ctx(tmp)
    words = {f"w{i}": Word(f"w{i}", "daily", f"das Wort{i}", ["x"], "noun", example_de=s, example_en="x")
             for i, s in enumerate(sentences)}
    ctx.content = Content(words, [])
    ctx.profile.data["vocab"] = {wid: {"box": 1} for wid in words}
    return ctx


class GrammarFillsIn(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name

    def test_a_focus_kind_with_no_sentences_lets_the_others_fill_in(self):
        ctx = sentence_ctx(self.tmp, ["Ich fahre mit dem Bus.", "Er kommt aus der Schule.",
                                      "Wir gehen heute ins Kino."])  # no adjectives: no ending questions
        self.assertEqual(len(grammar.make_items(ctx, 3, focus=["ending"])), 3)

    def test_without_a_focus_a_missing_kind_doesnt_stop_the_rest(self):
        ctx = sentence_ctx(self.tmp, ["Ich fahre mit dem Bus.", "Er kommt aus der Schule.",
                                      "Sie liest das Buch heute."])
        self.assertEqual(len(grammar.make_items(ctx, 3)), 3)


class SameParticiple(unittest.TestCase):
    def test_gefallen_without_the_helper_is_almost_not_a_form_of_fallen(self):
        fallen = Verb("fallen", "to fall", "fiel", "ist gefallen")
        gefallen = Verb("gefallen", "to please", "gefiel", "hat gefallen")
        others = {"gefallen": "fallen", "ist gefallen": "fallen", "hat gefallen": "gefallen"}
        check = verbs.check_form("gefallen", gefallen, "perfect", "hat gefallen", others)
        self.assertEqual(check.outcome, ALMOST)
        self.assertIn("hat gefallen", check.message)
        check = verbs.check_form("hat gefallen", fallen, "perfect", "ist gefallen", others)
        self.assertEqual(check.outcome, ALMOST)  # the helper is sein
        self.assertIn("ist gefallen", check.message)


class FirstRun(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        patcher = mock.patch("app.ui.clear")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_quitting_during_the_placement_questions_keeps_the_level(self):
        ctx = ctx_with_bank(self.tmp)
        with mock.patch("app.ui.keys", lambda options: ""), \
                mock.patch("app.placement.ask", lambda ctx, word, *a: "correct" if word.rank <= 500 else "wrong"), \
                mock.patch("app.placement._probes", side_effect=QuitSession), console.capture():
            with self.assertRaises(QuitSession):
                placement.run(ctx)
        saved = json.loads(ctx.profile.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["placement"]["band"], "A1")
        self.assertTrue(any(s.get("seeded") for s in saved["vocab"].values()))

    def test_stopping_the_welcome_still_asks_about_german(self):
        ctx = make_ctx(self.tmp)
        ctx.profile.is_new = True
        ctx.profile.data["target"] = "A2"
        ctx.presence = None
        with mock.patch("app.main.welcome", side_effect=QuitSession), mock.patch("app.ui.keys", lambda o: "p"), \
                mock.patch("app.main.placement.run") as run, mock.patch("app.ui.ask", side_effect=QuitSession), \
                mock.patch("app.ui.start_clock"), console.capture():
            with self.assertRaises(QuitSession):
                main.menu(ctx)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class QuoteBeforeTheArticle(unittest.TestCase):
    def test_the_hint_keeps_its_first_letter_after_an_opening_quote(self):
        from app.grammar import article_items
        self.assertEqual([i.shown for i in article_items("Er sagte: „Der Hund bellt laut.“")],
                         ["Er sagte: „D___ Hund bellt laut.“"])
