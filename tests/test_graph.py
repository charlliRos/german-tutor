"""The skill graph: mastery from boxes and answers, states, readiness, what's next, and why stuck."""
import unittest
from datetime import date

from app import graph
from app.content import Content, Word

TODAY = date(2026, 9, 25)


def answer(competency, sub, correct):
    return {"type": "attempt", "competency": competency, "subcompetency": sub,
            "score": {"kind": "dichotomous", "correct": correct}}


GRAMMAR = [
    graph.Node("gram:A1.gender", "grammar", "A1", "Noun gender", scored_from=[{"competency": "grammar.noun_gender"}]),
    graph.Node("gram:A1.accusative", "grammar", "A1", "Accusative", requires=["gram:A1.gender"],
               scored_from=[{"competency": "grammar.case_articles", "subcompetency": "article*"}]),
    graph.Node("gram:A2.adjective", "grammar", "A2", "Adjective endings", requires=["gram:A1.accusative"],
               scored_from=[{"competency": "grammar.adjective_endings", "subcompetency": "ending*"}]),
    graph.Node("gram:A2.dative_verbs", "grammar", "A2", "Verbs with dative", requires=["gram:A1.accusative"]),
]


class Graph(unittest.TestCase):
    def setUp(self):
        words = {f"f{i}": Word(f"f{i}", "daily", f"w{i}", ["x"], "noun", level="A1", topic="food") for i in range(10)}
        words |= {f"s{i}": Word(f"s{i}", "stem", f"s{i}", ["x"], "noun", level="B2", topic="physics") for i in range(5)}
        self.nodes = graph.build(Content(words, []), [], GRAMMAR)

    def test_word_sets_come_from_level_and_topic(self):
        self.assertEqual(len(self.nodes["vocab:A1/food"].items), 10)
        self.assertIn("vocab:stem/physics", self.nodes)
        self.assertFalse(graph.everyday(self.nodes["vocab:stem/physics"]))

    def test_word_strength_decays_when_overdue_and_leeches_are_capped(self):
        self.assertEqual(graph.item_strength({"box": 5, "due": "2026-09-20"}, TODAY), 0.9)
        self.assertEqual(graph.item_strength({"box": 5, "due": "2026-07-01"}, TODAY), 0.45)  # 86 days over 35
        self.assertEqual(graph.item_strength({"box": 2, "wrong": 6, "due": "2026-09-26"}, TODAY), 0.35)

    def test_grammar_mastery_states_and_locking(self):
        events = [answer("grammar.noun_gender", "-ung", True)] * 25 + [answer("grammar.case_articles", "article", i % 2 == 0)
                                                                          for i in range(12)]
        states = graph.mastery(self.nodes, {}, events, TODAY)
        self.assertEqual(states["gram:A1.gender"].state, "solid")
        self.assertEqual(states["gram:A1.accusative"].state, "practising")
        self.assertAlmostEqual(states["gram:A1.accusative"].mastery, 0.5, delta=0.1)
        self.assertEqual(states["gram:A2.adjective"].state, "locked")  # accusative isn't solid yet
        self.assertEqual(graph.frontier(self.nodes, states, "A2"), ["gram:A1.accusative"])

    def test_self_grades_are_claimed_never_mastery(self):
        events = [{"type": "attempt", "competency": "grammar.noun_gender", "subcompetency": "x",
                   "score": {"kind": "estimated", "raw": 2, "max": 2}}] * 30
        st = graph.mastery(self.nodes, {}, events, TODAY)["gram:A1.gender"]
        self.assertEqual((st.mastery, st.answers, st.claimed), (0.0, 0, 1.0))

    def test_rusty_when_it_was_solid_and_slips(self):
        events = [answer("grammar.noun_gender", "x", True)] * 30 + [answer("grammar.noun_gender", "x", False)] * 20
        self.assertEqual(graph.mastery(self.nodes, {}, events, TODAY)["gram:A1.gender"].state, "rusty")

    def test_readiness_leaves_out_what_has_no_data(self):
        vocab = {f"f{i}": {"box": 6, "due": "2026-10-30"} for i in range(10)}
        states = graph.mastery(self.nodes, vocab, [], TODAY)
        ready = graph.readiness(self.nodes, states, "A2")
        self.assertEqual((ready["vocab"], ready["grammar"], ready["total"]), (1.0, None, 1.0))

    def test_stuck_names_the_weakest_prerequisite(self):
        events = ([answer("grammar.noun_gender", "x", True)] * 25
                  + [answer("grammar.case_articles", "article", False)] * 12
                  + [answer("grammar.adjective_endings", "ending", i % 3 == 0) for i in range(25)])
        states = graph.mastery(self.nodes, {}, events, TODAY)
        blocks = graph.stuck(self.nodes, states, {"days": {}}, TODAY)
        self.assertEqual([b["node"].id for b in blocks], ["gram:A2.adjective"])
        self.assertEqual(blocks[0]["because"][0].id, "gram:A1.accusative")
        self.assertIn("Accusative", graph.suggestion(blocks[0]))


if __name__ == "__main__":
    unittest.main()
