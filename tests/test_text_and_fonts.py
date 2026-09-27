import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pvm import fonts
from pvm.render.text import balanced_wrap, text_sprite
from pvm.util import PvmError


class FontPolicyTest(unittest.TestCase):
    def test_no_silent_fallback_to_system_fonts(self):
        missing = {role: [Path("Z:/missing.otf")] for role in fonts.FREE}
        system = {role: [Path(__file__)] for role in fonts.SYSTEM}  # any existing file stands in for YaHei
        with mock.patch.dict(fonts.FREE, missing), mock.patch.dict(fonts.SYSTEM, system):
            with mock.patch.object(fonts, "get_settings", return_value=SimpleNamespace(allow_system_fonts=False)):
                with self.assertRaises(PvmError):
                    fonts.font_path("black")
            with mock.patch.object(fonts, "get_settings", return_value=SimpleNamespace(allow_system_fonts=True)):
                self.assertEqual(fonts.font_path("black"), Path(__file__))


class SpriteTest(unittest.TestCase):
    def setUp(self):
        try:
            self.font = fonts.font("black", 72)
        except PvmError:
            self.skipTest("fonts not downloaded (run pvm fonts)")

    def test_trim_x_keeps_a_fixed_height(self):
        heights = {text_sprite([t], self.font, (255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255),
                               trim="x").height
                   for t in ["研究发现", "一二三", "Nature 2022", "gypsy"]}
        self.assertEqual(len(heights), 1, heights)

    def test_balanced_wrap_avoids_orphans(self):
        lines = balanced_wrap("财富上限往往不是由努力决定", self.font, 11 * 72)
        self.assertEqual(len(lines), 2)
        self.assertLessEqual(abs(len(lines[0]) - len(lines[1])), 1, lines)


if __name__ == "__main__":
    unittest.main()
