import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from pvm import util
from pvm.project import Project
from pvm.util import PvmError, write_json
from tests.helpers import SCRIPT, TempHome, board, fixture_paper


class ProjectCheckTest(TempHome):
    def make(self) -> Project:
        p, created = Project.open_or_create("demo")
        self.assertTrue(created)
        p.set_script(SCRIPT)
        p.set_paper(fixture_paper())
        write_json(p.storyboard_path, board())
        return p

    def test_check_anchor_and_script_drift(self):
        p = self.make()
        report = p.check()
        self.assertEqual(report.errors, [])
        self.assertEqual(len(report.evidence), 3)  # hook + two source_fact claims
        p.anchor_storyboard(report.sentences_hash)
        self.assertEqual(p.storyboard().sentences_hash, report.sentences_hash)

        # Split sentence 4 and merge 5 + 6: still six sentences, but the numbering has shifted.
        edited = (SCRIPT.replace("问题不在于不懂，而在于", "问题不在于不懂。而在于")
                  .replace("怎么知道的。你身边", "怎么知道的，你身边"))
        p.set_script(edited)
        self.assertEqual(len(p.sentences()), 6)
        with self.assertRaises(PvmError) as ctx:
            p.storyboard()
        self.assertIn("script.txt changed", str(ctx.exception))
        self.assertEqual(p.check(ignore_anchor=True).errors, [])

    def test_asset_checks_flag_missing_highlights_and_unknown_poses(self):
        p = self.make()
        p.sources_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (612, 792), "white").save(p.source_pdf())  # a real PDF; highlight_pages is mocked
        data = board()
        data["scenes"][1] = {"id": "t1", "type": "text", "sentences": [4, 6], "lines": ["你呢"], "pose": "moonwalk"}
        write_json(p.storyboard_path, data)
        with mock.patch("pvm.render.paper.highlight_pages", return_value=(1, ["overestimated"])):
            report = p.check()
        self.assertTrue(any("highlight 'overestimated' is not on page 1" in w for w in report.warnings),
                        report.warnings)
        self.assertTrue(any("unknown mascot pose 'moonwalk'" in e for e in report.errors), report.errors)

    def test_legacy_single_paper_becomes_src1(self):
        p, _ = Project.open_or_create("legacy")
        p.update_meta(paper=fixture_paper().model_dump(exclude_none=True))
        self.assertEqual(p.paper().title, fixture_paper().title)
        p.set_paper(fixture_paper(title="Second Paper"), "src2")
        meta = json.loads(p.meta_path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(meta["sources"]), ["src1", "src2"])
        self.assertNotIn("paper", meta)


class AtomicWriteTest(unittest.TestCase):
    def test_retries_while_windows_holds_a_lock(self):
        real = os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError(13, "locked")
            real(src, dst)

        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "project.json"
            with mock.patch.object(util.os, "replace", flaky), mock.patch.object(util.time, "sleep"):
                util.write_text(target, "ok")
            self.assertEqual(target.read_text(encoding="utf-8"), "ok")
            self.assertEqual(calls["n"], 3)
            self.assertEqual([f.name for f in Path(d).iterdir()], ["project.json"])  # no temp files left behind


if __name__ == "__main__":
    unittest.main()
