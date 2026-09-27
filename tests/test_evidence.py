import unittest

from pvm.evidence import SourceText, check_evidence, display_policy, is_open, loose, normalize
from pvm.schema import parse_storyboard
from tests.helpers import ABSTRACT, FINDING, TITLE, board, fixture_paper


def texts(**parts):
    base = {"title": TITLE, "abstract": ABSTRACT}
    base.update(parts)
    return {"src1": SourceText("src1", base)}


class NormalizeTest(unittest.TestCase):
    def test_ligatures_hyphenation_and_quotes(self):
        self.assertEqual(normalize("The ﬁrst “ﬁnding”:\npartici-\npants"), 'the first "finding": participants')

    def test_loose_keeps_only_letters_and_digits(self):
        self.assertEqual(loose("Self-Assessment, in  novices"), "selfassessmentinnovices")


class FindExcerptTest(unittest.TestCase):
    def test_exact_loose_and_missing(self):
        pdf = SourceText("src1", {"pdf": "Across three studies, novice partic ipants consistently over-\n"
                                         "estimated their own performance."})
        self.assertEqual(pdf.find("novice participants consistently overestimated their own performance"),
                         ("loose", "pdf"))
        abstract = SourceText("src1", {"abstract": ABSTRACT})
        self.assertEqual(abstract.find(FINDING), ("exact", "abstract"))
        self.assertEqual(abstract.find("novices overestimate everything they ever do"), (None, None))


class CheckEvidenceTest(unittest.TestCase):
    papers = {"src1": fixture_paper()}

    def test_excerpts_found_in_the_abstract(self):
        errors, warnings, results = check_evidence(parse_storyboard(board()), texts(), self.papers, strict=True)
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual([r.status for r in results], ["found", "found", "found"])

    def test_invented_quote_fails_when_the_full_text_exists(self):
        data = board()
        data["claims"][2]["evidence"][0]["excerpt"] = "participants always overestimate everything they attempt"
        errors, _, _ = check_evidence(parse_storyboard(data), texts(pdf="The body of the paper, without that."),
                                      self.papers, strict=False)
        self.assertTrue(any("excerpt not found" in e for e in errors), errors)

    def test_unverifiable_quote_warns_in_drafts_and_fails_strict(self):
        data = board()
        data["claims"][2]["evidence"][0]["excerpt"] = "a sentence that only appears in the body of the paper"
        errors, warnings, _ = check_evidence(parse_storyboard(data), texts(), self.papers, strict=False)
        self.assertEqual(errors, [])
        self.assertTrue(any("no full text" in w for w in warnings), warnings)
        errors, _, _ = check_evidence(parse_storyboard(data), texts(), self.papers, strict=True)
        self.assertTrue(any("no full text" in e for e in errors), errors)

    def test_scroll_needs_an_open_license_or_permission(self):
        data = board()
        data["scenes"][0] = {"id": "open", "type": "paper_scroll", "sentences": [1, 3]}
        t = texts(pdf="page text")
        _, warnings, _ = check_evidence(parse_storyboard(data), t, self.papers, strict=False)
        self.assertTrue(any("paper_scroll shows whole pages" in w for w in warnings), warnings)

        data["scenes"][0]["rights"] = "permitted"
        errors, warnings, _ = check_evidence(parse_storyboard(data), t, self.papers, strict=True)
        self.assertFalse(any("paper_scroll" in m for m in errors + warnings))

        data["scenes"][0]["rights"] = "auto"
        open_papers = {"src1": fixture_paper(license="cc-by", license_version="publishedVersion", is_oa=True)}
        errors, warnings, _ = check_evidence(parse_storyboard(data), t, open_papers, strict=True)
        self.assertFalse(any("paper_scroll" in m for m in errors + warnings))


class DisplayPolicyTest(unittest.TestCase):
    def test_license_decides_what_is_shown(self):
        cc_by = fixture_paper(license="cc-by", license_version="publishedVersion")
        self.assertEqual(display_policy(cc_by, True), "page")
        self.assertEqual(display_policy(cc_by, False), "card")
        self.assertEqual(display_policy(fixture_paper(), True), "title_crop")
        manuscript = fixture_paper(license="cc-by", license_version="acceptedVersion")
        self.assertEqual(display_policy(manuscript, True), "title_crop")
        non_commercial = fixture_paper(license="cc-by-nc", license_version="publishedVersion")
        self.assertEqual(display_policy(non_commercial, True), "title_crop")
        self.assertFalse(is_open(None))


if __name__ == "__main__":
    unittest.main()
