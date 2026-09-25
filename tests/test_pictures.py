"""Pictures in the terminal: SVG rendered to pixels, shown as sixel or coloured blocks, with a fallback."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rich.console import Console

from app import exams, pictures

SQUARE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10">'
          '<rect width="10" height="10" fill="#ff0000"/><rect x="10" width="10" height="10" fill="#0000ff"/></svg>')


class Rendering(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.svg = Path(tmp.name) / "sq.svg"
        self.svg.write_text(SQUARE, encoding="utf-8")

    def test_svg_becomes_pixels_without_an_image_library(self):
        px = pictures.render(str(self.svg), 40)
        self.assertEqual(px.shape, (20, 40, 3))
        self.assertEqual(tuple(px[10, 5]), (255, 0, 0))    # left half red
        self.assertEqual(tuple(px[10, 35]), (0, 0, 255))   # right half blue

    def test_sixel_is_a_complete_escape_sequence(self):
        s = pictures.sixel(pictures.render(str(self.svg), 12))
        self.assertTrue(s.startswith("\x1bP") and s.endswith("\x1b\\"))
        self.assertIn('"1;1;12;6', s)  # width and height

    def test_blocks_draw_two_pixels_per_character(self):
        text = pictures.blocks(pictures.render(str(self.svg), 8))
        self.assertEqual(text.plain.count("▀"), 8 * 2)  # 8 wide, 4 pixel rows -> 2 lines

    def test_a_broken_picture_is_none_not_a_crash(self):
        bad = self.svg.with_name("bad.svg")
        bad.write_text("<svg", encoding="utf-8")
        self.assertIsNone(pictures.render(str(bad), 10))
        console = Console(file=open(tempfile.mktemp(), "w"), force_terminal=True)
        self.assertFalse(pictures.show_row(console, {"pictures": "blocks"}, [("a", bad)]))

    def test_mode(self):
        self.assertEqual(pictures.mode({"pictures": "off"}), "off")
        with mock.patch("sys.stdout.isatty", return_value=True), mock.patch.dict("os.environ", {"WT_SESSION": "1"}):
            self.assertEqual(pictures.mode({"pictures": "auto"}), "sixel")
        with mock.patch("sys.stdout.isatty", return_value=True), mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(pictures.mode({"pictures": "auto"}), "blocks")


class InTheExam(unittest.TestCase):
    def test_missing_pictures_are_found_by_the_checker(self):
        self.assertIn("not found", exams.check_picture("nope/none.svg")[0])
        self.assertEqual(exams.check_picture("test.svg"), [])


if __name__ == "__main__":
    unittest.main()
