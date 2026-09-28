import base64
import importlib.util
import io
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx
from PIL import Image, ImageDraw

from pvm import images, quota
from pvm.fonts import font
from pvm.images import ArkImageProvider, ImageRequest, check_labels, compile_prompt, generate_scene, request_size
from pvm.project import Project
from pvm.schema import parse_storyboard
from pvm.util import PvmError, write_json
from tests.helpers import SCRIPT, TempHome, board

STYLE = {"version": 1, "anchor": "paper-cut collage", "mascot": "an original researcher", "avoid": "no anime look"}


def png_bytes(color=(240, 235, 225), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def poster_scene():
    return parse_storyboard(board()).scenes[1]


class PromptTest(unittest.TestCase):
    def test_prompt_lists_panels_and_only_the_allowed_labels(self):
        prompt = compile_prompt(poster_scene(), STYLE)
        self.assertIn("3 stacked horizontal panels", prompt)
        self.assertIn("PANEL 2: mascot looks into a magnifying glass.", prompt)
        self.assertIn("only readable text allowed is these Chinese words on paper tags: 不会做、怎么知道", prompt)
        self.assertIn("no digits", prompt)

    def test_request_size_follows_the_panel_area(self):
        self.assertEqual(request_size((1000, 960)), (2048, 1968))
        self.assertEqual(request_size((1000, 2000)), (1024, 2048))


class LabelCheckTest(unittest.TestCase):
    def test_labels_found_even_across_lines(self):
        found = [("高收入", 0.99), ("朋友", 0.98), ("不同背景", 1.0)]
        self.assertTrue(check_labels(found, ["高收入朋友", "不同背景"]).ok)

    def test_missing_label_and_forbidden_text_fail(self):
        check = check_labels([("不同背景", 0.99), ("20%", 0.95), ("Nature", 0.9)], ["高收入朋友", "不同背景"])
        self.assertFalse(check.ok)
        self.assertEqual(check.missing, ["高收入朋友"])
        self.assertEqual(check.forbidden, ["20%", "Nature"])

    def test_low_confidence_noise_is_ignored_and_extra_text_only_warns(self):
        check = check_labels([("不同背景", 0.99), ("x", 0.3), ("意外文字", 0.97)], ["不同背景"])
        self.assertTrue(check.ok)
        self.assertEqual(check.extra, ["意外文字"])


class ArkProviderTest(unittest.TestCase):
    def test_request_shape_and_b64_response(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers["Authorization"]
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png_bytes()).decode(), "size": "2048x1968"}],
                                             "usage": {"generated_images": 1}})

        provider = ArkImageProvider("https://ark.example/api/plan/v3/", "key-123", "doubao-seedream-5.0-lite",
                                    transport=httpx.MockTransport(handler))
        out = provider.generate(ImageRequest("a prompt", (2048, 1968)))
        self.assertEqual(seen["url"], "https://ark.example/api/plan/v3/images/generations")
        self.assertEqual(seen["auth"], "Bearer key-123")
        self.assertEqual(seen["body"]["size"], "2048x1968")
        self.assertEqual(seen["body"]["response_format"], "b64_json")
        self.assertFalse(seen["body"]["watermark"])
        self.assertEqual(Image.open(io.BytesIO(out.data)).size, (64, 64))

    def test_errors_are_readable(self):
        transport = httpx.MockTransport(lambda r: httpx.Response(
            400, json={"error": {"code": "InvalidParameter", "message": "size out of range"}}))
        provider = ArkImageProvider("https://ark.example/v3", "k", "m", transport=transport)
        with self.assertRaises(PvmError) as ctx:
            provider.generate(ImageRequest("p", (10, 10)))
        self.assertIn("InvalidParameter size out of range", str(ctx.exception))


class FakeProvider:
    name, model = "fake", "fake-model"

    def __init__(self):
        self.calls = 0

    def generate(self, req):
        self.calls += 1
        return images.GeneratedImage(png_bytes((200 + self.calls, 200, 200)), {"size": f"{req.size[0]}x{req.size[1]}"})


class GenerateSceneTest(TempHome):
    def test_retry_until_the_ocr_gate_passes_then_reuse_the_cache(self):
        p, _ = Project.open_or_create("img")
        p.set_script(SCRIPT)
        write_json(p.storyboard_path, board())
        scene = poster_scene()
        settings = SimpleNamespace(afp_per_image=99, image_attempts=3)
        provider = FakeProvider()
        ocr_results = iter([[("不会做", 0.99)],  # attempt 1: one label missing
                            [("不会做", 0.99), ("怎么知道", 0.98)]])  # attempt 2: both labels found
        with mock.patch.object(images, "read_text", side_effect=lambda data: next(ocr_results)):
            result = generate_scene(p, scene, style=STYLE, box=(1000, 960), provider=provider, settings=settings,
                                    attempts=3)
        self.assertEqual(result.status, "accepted")
        self.assertEqual([a["ok"] for a in result.attempts], [False, True])
        self.assertEqual((provider.calls, result.afp), (2, 198))
        self.assertTrue((p.visuals_dir / "p1.png").exists())
        self.assertEqual(sum(e["afp"] for e in quota.entries()), 198)

        again = generate_scene(p, scene, style=STYLE, box=(1000, 960), provider=provider, settings=settings, attempts=3)
        self.assertEqual((again.status, provider.calls), ("up-to-date", 2))

    def test_budget_exhausted_leaves_a_candidate_for_review(self):
        p, _ = Project.open_or_create("img2")
        p.set_script(SCRIPT)
        write_json(p.storyboard_path, board())
        settings = SimpleNamespace(afp_per_image=99, image_attempts=2)
        with mock.patch.object(images, "read_text", return_value=[("AI 2024", 0.99)]):
            result = generate_scene(p, poster_scene(), style=STYLE, box=(1000, 960), provider=FakeProvider(),
                                    settings=settings, attempts=2)
        self.assertEqual(result.status, "review")
        self.assertTrue((p.visuals_dir / "p1.candidate.png").exists())
        self.assertFalse((p.visuals_dir / "p1.png").exists())
        images.accept_candidate(p, "p1")
        self.assertTrue((p.visuals_dir / "p1.png").exists())


@unittest.skipUnless(importlib.util.find_spec("rapidocr_onnxruntime"), "rapidocr_onnxruntime not installed")
class RealOcrTest(unittest.TestCase):
    def test_reads_labels_drawn_on_paper_tags(self):
        try:
            f = font("black", 64)
        except PvmError:
            self.skipTest("fonts not downloaded (run pvm fonts)")
        img = Image.new("RGB", (900, 500), (244, 239, 230))
        d = ImageDraw.Draw(img)
        for (x, y), label in (((60, 80), "高收入朋友"), ((420, 300), "不同背景")):
            d.rounded_rectangle((x - 20, y - 12, x + 20 + f.getlength(label), y + 86), 12, fill=(250, 246, 236),
                                outline=(60, 50, 40), width=3)
            d.text((x, y), label, font=f, fill=(30, 30, 30))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        self.assertTrue(check_labels(images.read_text(buf.getvalue()), ["高收入朋友", "不同背景"]).ok)


if __name__ == "__main__":
    unittest.main()
