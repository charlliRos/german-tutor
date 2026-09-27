"""Clearer verb and grammar screens: a missing word may be typed whole or as just the missing letters (and
sometimes nothing is missing), the past-tense card shows an example, word order names the first word."""
import random
import tempfile
import unittest
from unittest import mock

from app import grammar, verbs
from app.answers import CORRECT, WRONG
from app.content import Verb
from app.ui import console
from tests.test_flows import make_ctx


def article(sentence: str, answer: str) -> grammar.Item:
    return next(i for i in grammar.article_items(sentence) if i.answer.strip("„“") == answer)


class MissingWord(unittest.TestCase):
    def test_the_whole_word_counts(self):
        self.assertEqual(grammar.check(article("Ich fahre mit dem Bus.", "dem"), "dem")[0], CORRECT)
        self.assertEqual(grammar.check(article("Ich habe einen Hund.", "einen"), "einen")[0], CORRECT)

    def test_just_the_missing_letters_count(self):
        item = article("Ich fahre mit dem Bus.", "dem")
        self.assertEqual(item.shown.split()[3], "d___")
        self.assertEqual(grammar.check(item, "em")[0], CORRECT)
        self.assertEqual(grammar.check(article("Ich habe einen Hund.", "einen"), "en")[0], CORRECT)
        self.assertEqual(grammar.check(article("Der Hund schläft.", "Der"), "er")[0], CORRECT)
        self.assertEqual(grammar.check(article("Der Hund schläft.", "Der"), "Er")[0], CORRECT)  # capitals as before

    def test_nothing_missing_the_word_as_it_is_counts(self):
        item = article("Dein Hund ist so süß!", "Dein")
        self.assertTrue(item.shown.startswith("Dein___"))
        self.assertEqual(grammar.check(item, "Dein")[0], CORRECT)
        self.assertEqual(grammar.check(item, "dein")[0], CORRECT)
        self.assertEqual(grammar.check(item, "Deine")[0], WRONG)

    def test_a_wrong_answer_is_still_wrong(self):
        item = article("Ich fahre mit dem Bus.", "dem")
        for answer in ("den", "en", "er", "m", "d"):
            self.assertEqual(grammar.check(item, answer)[0], WRONG, answer)
        der = article("Der Hund schläft.", "Der")
        for answer in ("ie", "as", "die", "D"):
            self.assertEqual(grammar.check(der, answer)[0], WRONG, answer)

    def test_an_opening_quote_keeps_the_missing_letters_working(self):
        item = article("Er sagt: „Der Hund ist müde.“", "Der")
        self.assertEqual(grammar.check(item, "er")[0], CORRECT)
        self.assertEqual(grammar.check(item, "Der")[0], CORRECT)

    def test_the_whole_adjective_still_counts_for_an_ending(self):
        item = grammar.ending_items("Ich habe einen neuen Laptop.", {"neu"})[0]
        self.assertEqual(grammar.check(item, "en")[0], CORRECT)
        self.assertEqual(grammar.check(item, "neuen")[0], CORRECT)


class Screens(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = make_ctx(tmp.name)
        for target in ("app.ui.clear", "app.grammar.sfx.play", "app.verbs.sfx.play", "app.grammar.hear",
                       "app.verbs.hear", "app.ui.pause"):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def screen(self, item):
        with mock.patch("app.ui.ask_answer", return_value="") as ask, \
                mock.patch("app.ui.timed_keys", return_value=""), console.capture() as out:
            grammar.question(self.ctx, item, "Grammar 1 of 1")
        return " ".join(out.get().split()), ask.call_args[0][0]

    def test_the_missing_word_instruction_says_both_ways_and_nothing_missing(self):
        text, prompt = self.screen(article("Dein Hund ist so süß!", "Dein"))
        self.assertIn("type the whole word (dem, einen …) or just the missing letters", text)
        self.assertIn("Sometimes nothing is missing: then type the word as it is.", text)
        self.assertNotIn("Missing", prompt)

    def test_word_order_says_the_first_word(self):
        item = grammar.order_item("Morgen fahren wir nach Berlin.", random.Random(1))
        text, _ = self.screen(item)
        self.assertIn("type the whole sentence, starting with „Morgen“.", text)

    def card(self, inf, past, perfect):
        self.ctx.content.verbs = {inf: Verb(inf, "x", past, perfect)}
        with mock.patch("app.ui.ask_answer", return_value=past) as ask, console.capture() as out:
            verbs.card(self.ctx, f"{inf}|past", "Verb 1 of 1")
        return " ".join(out.get().split()), ask.call_args[0][0]

    def test_the_past_card_shows_an_example_with_another_verb(self):
        text, prompt = self.card("gehen", "ging", "ist gegangen")
        self.assertIn("Type the past tense (er/sie/es form), e.g. machen → er machte, kommen → er kam.", text)
        self.assertEqual(prompt, "er/sie/es (past tense):")

    def test_never_the_asked_verb_as_the_example(self):
        text, _ = self.card("kommen", "kam", "ist gekommen")
        self.assertIn("e.g. machen → er machte, spielen → er spielte.", text)
        self.assertEqual(verbs.past_example("machen"), "kommen → er kam, spielen → er spielte")


if __name__ == "__main__":
    unittest.main()
