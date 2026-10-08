import unittest

from pvm.schema import check_storyboard, parse_storyboard
from pvm.script import sentences_hash, split_sentences
from pvm.util import PvmError
from tests.helpers import SCRIPT, board, fixture_paper

SENTENCES = [s.text for s in split_sentences(SCRIPT)]
SOURCES = {"src1"}


def run(data, **kw):
    return check_storyboard(parse_storyboard(data), SENTENCES, SOURCES, **kw)


class StoryboardCheckTest(unittest.TestCase):
    def test_fixture_script_has_six_sentences(self):
        self.assertEqual(len(SENTENCES), 6)

    def test_valid_board_passes_cleanly(self):
        self.assertEqual(run(board()), ([], []))

    def test_claims_are_required(self):
        errors, _ = run(board(claims=[]))
        self.assertTrue(any("claims missing" in e for e in errors), errors)

    def test_claims_must_cover_every_sentence(self):
        data = board()
        data["claims"] = data["claims"][:-1]
        errors, _ = run(data)
        self.assertTrue(any("claims cover sentences 1-5" in e for e in errors), errors)

    def test_source_fact_needs_evidence(self):
        data = board()
        data["claims"][2]["evidence"] = []
        errors, _ = run(data)
        self.assertTrue(any("source_fact needs evidence" in e for e in errors), errors)

    def test_short_excerpt_is_rejected(self):
        data = board()
        data["claims"][2]["evidence"][0]["excerpt"] = "overestimated"
        errors, _ = run(data)
        self.assertTrue(any("too short" in e for e in errors), errors)

    def test_unknown_source_is_rejected(self):
        data = board()
        data["claims"][2]["evidence"][0]["source"] = "src9"
        errors, _ = run(data)
        self.assertTrue(any("unknown source 'src9'" in e for e in errors), errors)

    def test_hook_claim_is_required_and_basis_recommended(self):
        errors, _ = run(board(hook_claim=None))
        self.assertTrue(any("hook_claim missing" in e for e in errors), errors)
        errors, warnings = run(board(hook_claim={"type": "advice"}))
        self.assertEqual(errors, [])
        self.assertTrue(any("should state its basis" in w for w in warnings), warnings)

    def test_research_wording_outside_source_fact_warns(self):
        data = board()
        data["claims"][1] = {"sentences": [2, 2], "type": "interpretation"}  # sentence 2 mentions 期刊 / 研究
        _, warnings = run(data)
        self.assertTrue(any("sentence 2 uses research wording" in w for w in warnings), warnings)

    def test_labels_cannot_hold_digits_or_latin(self):
        data = board()
        data["scenes"][1]["sections"][0]["labels"] = ["20%"]
        errors, _ = run(data)
        self.assertTrue(any("contains digits or Latin" in e for e in errors), errors)

    def test_anchor_detects_script_edits(self):
        data = board(sentences_hash=sentences_hash(SENTENCES))
        self.assertEqual(run(data)[0], [])
        edited = SENTENCES[:]
        edited[3] = "问题不在于不懂。"
        errors, _ = check_storyboard(parse_storyboard(data), edited, SOURCES)
        self.assertTrue(any("script.txt changed" in e for e in errors), errors)
        errors, _ = check_storyboard(parse_storyboard(data), edited, SOURCES, ignore_anchor=True)
        self.assertEqual(errors, [])

    def test_landing_screenshots_are_rejected(self):
        data = board()
        data["scenes"][0]["source"] = "landing"
        errors, _ = run(data)
        self.assertTrue(any("landing" in e for e in errors), errors)

    def test_schema_errors_name_the_field(self):
        data = board()
        data["claims"][0]["type"] = "opinion"
        with self.assertRaises(PvmError) as ctx:
            parse_storyboard(data)
        self.assertIn("claims.0.type", str(ctx.exception))


class PaperPagesTest(unittest.TestCase):
    def test_article_numbers_are_cited_once(self):
        # OpenAlex gives Scientific Reports articles first_page = last_page = the article number
        self.assertEqual(fixture_paper(pages="7730–7730").pages, "7730")
        self.assertEqual(fixture_paper(pages="e123-e123").pages, "e123")
        self.assertEqual(fixture_paper(pages="45–67").pages, "45–67")
        self.assertIn("9(1), 7730.", fixture_paper(volume="9", issue="1", pages="7730–7730").citation())


if __name__ == "__main__":
    unittest.main()
