"""der/die/das, grammar from sentences, example-sentence questions and the speech check."""
import random
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from app import genders, grammar, sentences, speaking, warmup
from app.answers import ALMOST, CORRECT, WRONG
from app.content import Word
from app.listen import said_it
from app.ui import console
from tests.test_flows import TODAY, make_ctx


def word(de, en, pos="noun", **kw):
    return Word(id=kw.pop("id", "t"), bank="daily", de=de, en=en, pos=pos, **kw)


class Typed:
    """Patch the prompts: answers are taken from the list, in order."""

    def __init__(self, *answers):
        self.patch = mock.patch("app.ui._read", mock.Mock(side_effect=list(answers)))

    def __enter__(self):
        for target, value in (("app.ui.clear", lambda: None), ("app.ui.keys", lambda options: ""),
                              ("app.ui.pause", lambda *a, **k: None)):
            p = mock.patch(target, value)
            p.start()
            self.__dict__.setdefault("others", []).append(p)
        self.patch.start()
        self.capture = console.capture()
        self.capture.__enter__()
        return self

    def __exit__(self, *exc):
        self.capture.__exit__(*exc)
        self.patch.stop()
        for p in self.others:
            p.stop()


class Gaps(unittest.TestCase):
    def test_the_word_in_its_sentence_form(self):
        wolf = word("der Wolf", ["wolf"], plural="die Wölfe", example_de="In Deutschland gibt es wieder Wölfe.")
        gap = sentences.find_gap(wolf)
        self.assertEqual(gap.form, "Wölfe")
        self.assertEqual(gap.blanked, "In Deutschland gibt es wieder _____.")
        self.assertEqual(sentences.check_gap("Woelfe", gap, wolf).outcome, CORRECT)
        self.assertEqual(sentences.check_gap("Wolf", gap, wolf).outcome, ALMOST)  # right word, wrong form
        self.assertEqual(sentences.check_gap("Hund", gap, wolf).outcome, WRONG)

    def test_verbs_and_capitals(self):
        gehen = word("gehen", ["to go"], pos="verb", example_de="Gehst du heute ins Kino?")
        self.assertEqual(sentences.find_gap(gehen).form, "Gehst")
        self.assertEqual(sentences.check_gap("gehst", sentences.find_gap(gehen), gehen).outcome, CORRECT)

    def test_no_gap_for_phrases_or_missing_forms(self):
        self.assertIsNone(sentences.find_gap(word("Keine Ahnung.", ["no idea"], pos="phrase",
                                                  example_de="Keine Ahnung, wo er ist.")))
        self.assertIsNone(sentences.find_gap(word("gehen", ["to go"], pos="verb", example_de="Er ging nach Hause.")))


class Genders(unittest.TestCase):
    def test_which_nouns_are_drilled(self):
        self.assertTrue(genders.eligible(word("der Tisch", ["table"], plural="die Tische")))
        self.assertFalse(genders.eligible(word("die Leute", ["people"], plural="die Leute")))  # plural only
        self.assertFalse(genders.eligible(word("der Joghurt", ["yoghurt"], de_alt=["das Joghurt"])))  # both
        self.assertFalse(genders.eligible(word("der alte Sack", ["old git"])))
        self.assertFalse(genders.eligible(word("schnell", ["fast"], pos="adj")))

    def test_rule_tip_only_when_the_noun_follows_it(self):
        self.assertIn("-ung are always die", genders.rule_tip("Zeitung", "die"))
        self.assertEqual(genders.rule_tip("Name", "der"), "")  # -e is often die, but not here: no tip
        self.assertIn("-chen", genders.rule_tip("Mädchen", "das"))

    def ctx_with_started_nouns(self, tmp):
        ctx = make_ctx(tmp, genders_per_day=2)
        for wid in ("w0", "w1", "w2"):
            ctx.profile.data["vocab"][wid] = {"box": 1, "due": "2099-01-01"}
        return ctx

    def test_new_cards_are_started_nouns_then_misses_repeat_until_right(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self.ctx_with_started_nouns(tmp)
            self.assertEqual(genders.plan(ctx, first_today=True), ["w0", "w1"])  # most common first, 2 a day
            self.assertEqual(genders.plan(ctx, first_today=False), [])
            # das Wort: wrong (der), right (3); then the repeat: wrong again (die), right (das)
            with Typed("der", "3", "2", "das"):
                result = genders.run_genders(ctx, first_today=True)
                genders.repeat_genders(ctx, result.missed)
            self.assertEqual((result.total, result.right, len(result.missed)), (2, 1, 1))
            self.assertEqual(ctx.profile.day(TODAY)["genders"], 2)
            self.assertEqual(set(ctx.profile.data["genders"]), {"w0", "w1"})


class Grammar(unittest.TestCase):
    def test_article_gaps_with_a_case_tip(self):
        items = grammar.article_items("Ich fahre mit dem Bus zur Schule.")
        self.assertEqual([(i.shown, i.answer) for i in items], [("Ich fahre mit d___ Bus zur Schule.", "dem")])
        self.assertIn("dative", items[0].tip)
        self.assertEqual(grammar.check(items[0], "Dem")[0], CORRECT)
        self.assertEqual(grammar.check(items[0], "den")[0], WRONG)

    def test_ein_words_and_not_verbs(self):
        items = grammar.article_items("Mein Bruder hat einen neuen Laptop.")
        self.assertEqual([i.answer for i in items], ["Mein", "einen"])
        self.assertEqual(grammar.article_items("Was meinen Sie dazu?"), [])  # meinen = to mean

    def test_adjective_endings(self):
        items = grammar.ending_items("Ich habe einen neuen Laptop.", {"neu"})
        self.assertEqual([(i.shown, i.answer) for i in items], [("Ich habe einen neu___ Laptop.", "en")])
        self.assertEqual(grammar.check(items[0], "neuen")[0], CORRECT)  # the whole word counts too
        self.assertEqual(grammar.ending_items("Er ist sehr müde heute.", {"müde"}), [])  # no noun after it

    def test_word_order(self):
        item = grammar.order_item("Morgen fahren wir nach Berlin.", random.Random(1))
        self.assertTrue(item.shown.startswith("Morgen …"))
        self.assertEqual(grammar.check(item, "Morgen fahren wir nach Berlin")[0], CORRECT)
        self.assertEqual(grammar.check(item, "fahren wir nach Berlin")[0], CORRECT)  # the given word left out
        outcome, message = grammar.check(item, "Morgen wir fahren nach Berlin.")
        self.assertEqual(outcome, WRONG)
        self.assertIn("order", message)
        self.assertIsNone(grammar.order_item("Ja, klar.", random.Random(1)))

    def test_a_round_in_the_warmup(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp, grammar_per_day=3)
            ctx.content.words["w0"].example_de = "Ich fahre mit dem Bus zur Schule."
            ctx.profile.data["vocab"]["w0"] = {"box": 1}
            items = grammar.make_items(ctx, 3)
            self.assertTrue(items)
            with Typed(*[i.answer for i in items]):
                result = grammar.run_grammar(ctx, first_today=True)
            self.assertEqual((result.right, result.total), (len(items), len(items)))
            self.assertEqual(grammar.run_grammar(ctx, first_today=False).total, 0)


class SpeechCheck(unittest.TestCase):
    def test_said_it(self):
        self.assertTrue(said_it("der regenschirm", "der Regenschirm"))
        self.assertTrue(said_it("regenschirm", "der Regenschirm"))  # the article isn't needed
        self.assertTrue(said_it("regen schirm", "der Regenschirm"))  # heard as two words
        self.assertFalse(said_it("guten morgen", "der Regenschirm"))
        self.assertFalse(said_it("", "der Regenschirm"))
        self.assertFalse(said_it("der", "der Regenschirm"))  # a small word alone doesn't count
        self.assertTrue(said_it("ich habe heute keine zeit", "Ich habe heute keine Zeit für Hausaufgaben."))
        self.assertFalse(said_it("wir gehen ins kino", "Ich habe heute keine Zeit für Hausaufgaben."))

    def speak(self, heard, must_say=True):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            ctx.audio = SimpleNamespace(can_record=True, can_check_speech=True, can_speak=True,
                                        heard=lambda *a: heard)
            with mock.patch("app.speaking._record", lambda *a: ("audio", 16000)), \
                    mock.patch("app.speaking._play_both", lambda *a: None), \
                    mock.patch("app.ui.keys", lambda options: ""), console.capture():
                said = speaking.speak_and_compare(ctx, "der Regenschirm", must_say=must_say)
            return said, ctx.profile.day(TODAY)

    def test_speaking_counts_only_when_heard(self):
        self.assertEqual(self.speak("der regenschirm"), (True, {"speaking": 1, "speaking_heard": 1, "words": 0,
                         "right": 0, "almost": 0, "new": 0, "units": 0, "warmups": 0}))
        said, day = self.speak("")
        self.assertFalse(said)
        self.assertEqual(day["speaking_heard"], 0)
        self.assertEqual(self.speak("", must_say=False), (False, {}))  # practice only: not counted

    def test_no_checker_means_no_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp)
            ctx.audio = SimpleNamespace(can_record=True, can_check_speech=False, can_speak=True)
            with mock.patch("app.speaking._record", lambda *a: ("audio", 16000)), \
                    mock.patch("app.speaking._play_both", lambda *a: None), \
                    mock.patch("app.ui.keys", lambda options: ""), console.capture():
                self.assertTrue(speaking.speak_and_compare(ctx, "der Regenschirm", must_say=True))

    def test_warmup_speaking_turn_not_heard_becomes_a_typed_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = make_ctx(tmp, speak_chance=1.0)
            ctx.audio = SimpleNamespace(can_speak=True, can_record=True, can_check_speech=True, problems=[])
            ctx.profile.data["vocab"]["w0"] = {"box": 2, "due": TODAY.isoformat(), "seen": 1, "right": 1,
                                               "wrong": 0, "last": "2026-09-10"}
            asked = []
            with mock.patch("app.warmup.read_aloud", lambda ctx, w: False), \
                    mock.patch("app.warmup.ask_word", lambda ctx, w, kind: asked.append(w.id) or CORRECT), \
                    mock.patch("app.warmup.show_card", lambda *a: None), mock.patch("app.warmup.hear", lambda *a, **k: None), \
                    mock.patch("app.ui.clear", lambda: None), mock.patch("app.ui.keys", lambda options: ""), \
                    mock.patch("app.ui.pause", lambda *a, **k: None), console.capture():
                result = warmup.run_warmup(ctx)
            self.assertIn("w0", asked)
            self.assertEqual(result.spoken, 0)


if __name__ == "__main__":
    unittest.main()
