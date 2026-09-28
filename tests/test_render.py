import unittest

import numpy as np
from PIL import Image

from pvm.fonts import font
from pvm.project import Project
from pvm.qa import run_qa
from pvm.render.assets import zoom
from pvm.render.paper import draw_citation, torn_bottom
from pvm.render.scenes import split_bands
from pvm.render.style import layout
from pvm.render.video import Composer, render
from pvm.schema import parse_storyboard
from pvm.timeline import build_timeline
from pvm.util import PvmError, write_json, write_wav
from pvm.voice import SentenceAudio, VoiceTrack
from tests.helpers import TempHome, fixture_paper


def fonts_available() -> bool:
    try:
        font("black", 20)
        return True
    except PvmError:
        return False


class BandsTest(unittest.TestCase):
    def test_cuts_at_the_gutters_nearest_equal_splits(self):
        img = np.full((900, 300), 240, dtype=np.uint8)
        for a, b in ((20, 280), (320, 610), (650, 880)):  # three panels, gutters at 280-320 and 610-650
            img[a:b, 20:280] = 60
        bands = split_bands(Image.fromarray(img), 3)
        self.assertEqual(bands[0][0], 0)
        self.assertEqual(bands[-1][1], 900)
        self.assertTrue(280 <= bands[0][1] <= 320, bands)
        self.assertTrue(610 <= bands[1][1] <= 650, bands)

    def test_equal_splits_without_gutters(self):
        noise = np.random.default_rng(1).integers(0, 255, (900, 300), dtype=np.uint8)
        self.assertEqual(split_bands(Image.fromarray(noise), 3), [(0, 300), (300, 600), (600, 900)])


class AssetsTest(unittest.TestCase):
    def test_zoom_keeps_size_and_moves_sub_pixel(self):
        img = Image.fromarray(np.random.default_rng(2).integers(0, 255, (144, 108, 3), dtype=np.uint8))
        a, b = zoom(img, 1.02, 54, 72), zoom(img, 1.02, 54.3, 72)
        self.assertEqual(a.size, img.size)
        self.assertGreater(np.abs(np.asarray(a, int) - np.asarray(b, int)).sum(), 0)

    def test_torn_bottom_is_transparent_below_the_tear(self):
        out = torn_bottom(Image.new("RGB", (400, 200), "white"), 12)
        alpha = np.asarray(out.getchannel("A"))
        self.assertTrue((alpha[0] == 255).all())
        self.assertTrue((alpha[-1] == 0).any())

    @unittest.skipUnless(fonts_available(), "fonts not downloaded (run pvm fonts)")
    def test_citation_card_is_drawn_from_metadata(self):
        card = draw_citation(fixture_paper(volume="12", issue="3", pages="45–67"), 900, layout().s)
        self.assertEqual(card.width, 900)
        self.assertGreater(card.height, 200)
        cjk = draw_citation(fixture_paper(title="社会资本与经济流动"), 900, layout().s, compact=True, label="文献信息")
        self.assertEqual(cjk.width, 900)


SCRIPT = "有些人明明不懂却很自信。\n问题在于看不见自己的盲区。\n所以多问一句你是怎么知道的。"
STORYBOARD = {
    "version": 2, "title": "渲染测试", "hook": ["看不见", "盲区"], "hook_until": 1,
    "hook_claim": {"type": "interpretation", "basis": "a framing question, not a finding"},
    "claims": [{"sentences": [1, 2], "type": "interpretation"}, {"sentences": [3, 3], "type": "advice"}],
    "scenes": [
        {"id": "t1", "type": "text", "sentences": [1, 1], "lines": ["看不见的盲区"]},
        {"id": "p1", "type": "poster", "sentences": [2, 2], "title": "盲区", "sections": [
            {"heading": "不自知", "visual": "mascot with a blindfold", "labels": ["盲区"]},
            {"heading": "多问一句", "visual": "mascot raising a hand", "labels": ["为什么"]}]},
        {"id": "end", "type": "summary", "sentences": [3, 3], "transition": "fade", "sections": [
            {"heading": "盲区", "visual": "mascot", "labels": []}, {"heading": "提问", "visual": "mascot", "labels": []}]},
    ],
}


def synthetic_voice(p: Project) -> VoiceTrack:
    """A speech-like signal with pauses, written as audio/voice.wav, and its sentence timings."""
    sr, t, sentences, chunks = 44100, 0.3, [], [np.zeros(int(0.3 * 44100), dtype=np.float32)]
    for n, s in enumerate(p.sentences(), 1):
        dur = 1.2
        x = np.arange(int(dur * sr)) / sr
        voice = 0.3 * np.sin(2 * np.pi * 180 * x) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * x))
        chunks += [voice.astype(np.float32), np.zeros(int(0.25 * sr), dtype=np.float32)]
        sentences.append(SentenceAudio(n, s.text, round(t, 3), round(t + dur, 3), s.para_end))
        t += dur + 0.25
    chunks.append(np.zeros(sr, dtype=np.float32))
    audio = np.concatenate(chunks)
    write_wav(p.audio_dir / "voice.wav", audio, sr)
    return VoiceTrack("audio/voice.wav", round(len(audio) / sr, 3), {"engine": "test"}, sentences)


@unittest.skipUnless(fonts_available(), "fonts not downloaded (run pvm fonts)")
class RenderSmokeTest(TempHome):
    def make(self):
        p, _ = Project.open_or_create("render-test")
        p.set_script(SCRIPT)
        write_json(p.storyboard_path, STORYBOARD)
        sb = p.storyboard()
        tl = build_timeline(sb, synthetic_voice(p))
        write_json(p.audio_dir / "timeline.json", tl.to_json())
        return p, sb, tl

    def test_every_scene_type_draws_a_full_frame(self):
        p, sb, tl = self.make()
        comp = Composer(p, sb, tl, layout("9x16", animatic=True), animatic=True, strict=False)
        for t in (0.1, 2.0, 3.5, tl.scenes[-1].start + 0.1, tl.duration - 0.1):
            self.assertEqual(comp.frame(t).size, (540, 960))

    def test_paper_display_follows_the_license(self):
        p, sb, tl = self.make()
        p.sources_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (612, 792), "white").save(p.source_pdf("src1"))  # a PDF page without a text layer
        for paper, expected in ((fixture_paper(), "title_crop"),
                                (fixture_paper(license="cc-by", license_version="publishedVersion"), "page")):
            p.set_paper(paper)
            data = dict(STORYBOARD, scenes=[{"id": "open", "type": "paper", "sentences": [1, 3]}])
            board = parse_storyboard(data)
            comp = Composer(p, board, build_timeline(board, synthetic_voice(p)), layout("3x4", animatic=True),
                            animatic=True, strict=False)
            comp.frame(0.5)
            self.assertEqual(comp.ctx.displays["open"], expected)

    def test_draft_render_passes_qa(self):
        p, sb, tl = self.make()
        summary = render(p, sb, tl, ratio="3x4", kind="draft", jobs=1, verbose=False)
        self.assertTrue((p.dir / summary["file"]).exists())
        result = run_qa(p, "3x4", "draft")
        self.assertTrue(result["passed"], [c for c in result["checks"] if not c["ok"]])


if __name__ == "__main__":
    unittest.main()
