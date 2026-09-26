"""Examiner-style writing checks: length, points, greeting and closing, linking words, capitals, spelling."""
import unittest

from app import writing_check
from app.content import Content, Word
from app.exams import Part


def content():
    words = [Word("hund", "daily", "der Hund", ["dog"], "noun"), Word("party", "daily", "die Party", ["party"], "noun"),
             Word("kommen", "daily", "kommen", ["come"], "verb"), Word("krank", "daily", "krank", ["ill"], "adj"),
             Word("leider", "daily", "leider", ["unfortunately"], "adv"), Word("danke", "daily", "danke", ["thanks"], "other"),
             Word("einladung", "daily", "die Einladung", ["invitation"], "noun"), Word("naechst", "daily", "nächste", ["next"], "adj"),
             Word("woche", "daily", "die Woche", ["week"], "noun"), Word("treffen", "daily", "treffen", ["meet"], "verb"),
             Word("feiern", "daily", "feiern", ["celebrate"], "verb"), Word("sein", "daily", "sein", ["to be"], "verb")]
    return Content({w.id: w for w in words}, [])


PART = Part(id="schreiben-1", skill="writing", title_de="Schreiben", words=[20, 30], kind="informal",
            points=["Dank", "Absage mit Grund", "Vorschlag"],
            point_keywords=[["danke"], ["leider", "kann nicht"], ["nächste woche", "vielleicht"]])


class WritingCheck(unittest.TestCase):
    def test_a_good_email_passes_everything(self):
        text = ("Liebe Anna,\ndanke für die Einladung. Leider kann ich nicht kommen, weil ich krank bin. "
                "Vielleicht treffen wir uns nächste Woche? Dann feiern wir, denn ich habe auch einen Hund.\nViele Grüße\nTom")
        result = writing_check.check(text.replace("\\n", "\n"), PART, "A2", content())
        self.assertEqual(result.points_found, [True, True, True])
        self.assertTrue(all(c.ok for c in result.checks), [(c.label, c.detail) for c in result.checks if not c.ok])

    def test_problems_are_named(self):
        text = "danke für die einladung. ich kommen nicht zu der party mit mein hundd"
        checks = {c.label: c for c in writing_check.check(text, PART, "B1", content()).checks}
        self.assertFalse(checks["Length"].ok)
        self.assertIn("greeting missing", checks["Greeting and closing"].detail)
        self.assertIn("einladung", checks["Nouns with a capital"].detail)
        self.assertIn("hundd", checks["Spelling (words the app doesn't know)"].detail)
        self.assertFalse(checks["Linking words"].ok)
        self.assertIn("1 of 3 found", checks["The task's points"].detail)  # only "danke"; no reason, no suggestion

    def test_formal_messages_use_sie(self):
        formal = Part(id="s3", skill="writing", title_de="S", words=[5, 10], kind="formal", points=[])
        checks = {c.label for c in writing_check.check("Sehr geehrte Frau Berg, kannst du mir helfen? Mit freundlichen Grüßen",
                                                       formal, "B1", content()).checks if not c.ok}
        self.assertIn("Formal: Sie, not du", checks)


class GrammarAndStyle(unittest.TestCase):
    def labels(self, text, level="B1"):
        return {c.label: c for c in writing_check.check(text, PART, level, content())}

    def test_comma_and_verb_position_after_weil(self):
        checks = {c.label: c for c in writing_check.check("Ich komme nicht weil ich bin krank.", PART, "B1", content()).checks}
        self.assertIn("weil", checks["Comma before weil / dass / wenn …"].detail)
        self.assertFalse(checks["Verb at the end after weil / dass …"].ok)
        good = {c.label: c for c in writing_check.check("Ich komme nicht, weil ich krank bin.", PART, "B1", content()).checks}
        self.assertTrue(good["Comma before weil / dass / wenn …"].ok)
        self.assertTrue(good["Verb at the end after weil / dass …"].ok)

    def test_ob_inside_a_word_is_not_a_conjunction(self):
        checks = {c.label: c for c in writing_check.check("Ich wohne oben im Haus.", PART, "B1", content()).checks}
        self.assertTrue(checks["Comma before weil / dass / wenn …"].ok)

    def test_a_greeting_and_closing_point_needs_both(self):
        part = Part(id="s", skill="writing", title_de="S", words=[5, 10], kind="formal", points=["Anrede und Gruß"],
                    point_keywords=[["#greeting_closing"]])
        self.assertEqual(writing_check.check("Guten Tag, ich komme nicht.", part, "B1", content()).points_found, [False])
        both = "Sehr geehrte Frau Berg,\nich komme nicht.\nMit freundlichen Grüßen"
        self.assertEqual(writing_check.check(both, part, "B1", content()).points_found, [True])

    def test_repeated_words_and_forgiving_points(self):
        text = ("Hallo Anna, danke, danke, danke für die Party. Die Party war toll, die Party war lang und die Party war laut. "
                "Leider kan ich nicht nochmal kommen. Vielleicht nächste Woche. Viele Grüße")
        checks = {c.label: c for c in writing_check.check(text, PART, "A2", content()).checks}
        self.assertIn("party (4×)", checks["Different words"].detail)
        self.assertEqual(writing_check.points_found("Entschuldigung, ich bin krank", [["entschuldig"]]), [True])


if __name__ == "__main__":
    unittest.main()
