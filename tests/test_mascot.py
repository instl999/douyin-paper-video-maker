import io
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw

from pvm import mascot
from pvm.images import GeneratedImage
from tests.helpers import TempHome

BACKGROUND = (247, 243, 234)


def figure(size=(600, 800)) -> Image.Image:
    """A dark-outlined figure whose shirt is almost the background color, on an off-white background."""
    img = Image.new("RGB", size, BACKGROUND)
    d = ImageDraw.Draw(img)
    d.ellipse((220, 120, 380, 280), fill=(250, 226, 200), outline=(40, 40, 40), width=6)  # head
    d.rounded_rectangle((200, 290, 400, 640), 30, fill=(243, 236, 222), outline=(40, 40, 40), width=6)  # cream shirt
    d.rectangle((230, 640, 370, 720), fill=(31, 58, 95), outline=(40, 40, 40), width=6)  # trousers
    return img


class CutOutTest(TempHome):
    def test_background_goes_transparent_but_the_enclosed_shirt_stays(self):
        out, fraction = mascot.cut_out(figure())
        self.assertTrue(0.03 < fraction < 0.7, fraction)
        alpha = np.asarray(out.getchannel("A"))
        self.assertEqual(alpha[0, 0], 0)  # crop margin is transparent background
        # the shirt centre, although nearly background-colored, is inside the outline and stays opaque
        shirt = np.asarray(out.convert("RGBA"))[alpha.shape[0] // 2, alpha.shape[1] // 2]
        self.assertEqual(shirt[3], 255)
        self.assertLess(out.width, 600)  # cropped to the character

    def test_pale_leftovers_and_specks_go_but_colorful_pieces_stay(self):
        img = figure()
        d = ImageDraw.Draw(img)
        d.rectangle((20, 20, 140, 90), fill=(226, 222, 214))  # a pale lighting patch, detached from the figure
        d.rectangle((500, 60, 530, 90), fill=(220, 60, 60))  # a colorful confetti piece, also detached
        for x in range(430, 470, 8):
            d.point((x, 400), fill=(255, 255, 255))  # white specks
        out, _ = mascot.cut_out(img)
        alpha = np.asarray(out.getchannel("A"))
        rgba = np.asarray(out)
        red = (rgba[..., 0] > 180) & (rgba[..., 1] < 100) & (alpha > 200)
        self.assertTrue(red.any())
        pale = (np.abs(rgba[..., :3].astype(int) - (226, 222, 214)).sum(axis=2) < 12) & (alpha > 200)
        self.assertFalse(pale.any())

    def test_contact_sheet_lays_out_poses(self):
        paths = []
        for i in range(3):
            path = Path(self.home) / f"p{i}.png"
            mascot.cut_out(figure())[0].save(path)
            paths.append(path)
        self.assertEqual(mascot.contact_sheet(paths, cell=100, columns=2).size, (200, 200))


class FakeProvider:
    name, model = "fake", "fake-model"

    def __init__(self):
        self.requests = []

    def generate(self, req):
        self.requests.append(req)
        buf = io.BytesIO()
        figure().save(buf, "PNG")
        return GeneratedImage(buf.getvalue())


class RunMascotTest(TempHome):
    def setUp(self):
        super().setUp()
        self.dir = Path(tempfile.mkdtemp(prefix="pvm-mascot-"))
        shutil.copy(mascot.MASCOT_DIR / "mascot.json", self.dir / "mascot.json")
        self.patch = mock.patch.object(mascot, "MASCOT_DIR", self.dir)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.dir, ignore_errors=True)
        super().tearDown()

    def test_sheet_then_poses_with_the_sheet_as_reference(self):
        provider = FakeProvider()
        settings = SimpleNamespace(afp_per_image=99, image_attempts=2)
        with mock.patch.object(mascot, "read_text", return_value=[]), \
                mock.patch.object(mascot, "get_settings", return_value=settings):
            results = mascot.run_mascot(poses=["front", "wave"], provider=provider)
        self.assertEqual([r.status for r in results], ["accepted", "accepted", "accepted"])
        self.assertEqual(provider.requests[0].references, [])
        self.assertEqual(provider.requests[1].references, [self.dir / "sheet.png"])
        self.assertTrue((self.dir / "poses" / "wave.png").exists())
        with Image.open(self.dir / "poses" / "wave.png") as wave:
            self.assertEqual(wave.mode, "RGBA")
        self.assertTrue((self.dir / "originals" / "wave.jpg").exists())  # kept for later re-cuts
        self.assertTrue((self.dir / "contact.png").exists())

    def test_stray_text_sends_the_image_to_review(self):
        settings = SimpleNamespace(afp_per_image=99, image_attempts=1)
        with mock.patch.object(mascot, "read_text", return_value=[("Hello", 0.95)]), \
                mock.patch.object(mascot, "get_settings", return_value=settings):
            results = mascot.run_mascot(sheet_only=True, provider=FakeProvider())
        self.assertEqual(results[0].status, "review")
        self.assertTrue((self.dir / "sheet.candidate.png").exists())
