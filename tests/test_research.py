import unittest

from pvm.research import Candidate, _crossref_paper, _openalex_paper, _score, enrich_from_openalex

WORK = {
    "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1234/OPEN.1", "title": "An Open Paper",
    "publication_year": 2022, "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
    "primary_location": {"source": {"display_name": "Nature"}, "landing_page_url": "https://example.org/a"},
    "best_oa_location": {"pdf_url": "https://example.org/a.pdf", "license": "cc-by", "version": "publishedVersion",
                         "is_oa": True},
    "locations": [], "open_access": {"is_oa": True, "oa_status": "hybrid"}, "cited_by_count": 10, "type": "article",
}
CROSSREF = {
    "DOI": "10.1234/closed.2", "title": ["A Closed Paper"], "container-title": ["Journal of Fixtures"],
    "issued": {"date-parts": [[2019]]}, "author": [{"given": "Alan", "family": "Turing"}], "type": "journal-article",
    "link": [{"URL": "https://publisher.example/tdm/closed.pdf", "content-type": "application/pdf"}],
}


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code, self._payload = status_code, payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params))
        return FakeResponse(200, self.payload)


class OpenAccessTest(unittest.TestCase):
    def test_openalex_is_the_authority(self):
        p = _openalex_paper(WORK)
        self.assertTrue(p.is_oa)
        self.assertEqual((p.license, p.license_version, p.oa_status), ("cc-by", "publishedVersion", "hybrid"))
        self.assertEqual(p.doi, "10.1234/open.1")
        self.assertEqual(p.pdf_urls[0], "https://example.org/a.pdf")

    def test_crossref_pdf_link_is_not_open_access(self):
        p = _crossref_paper(CROSSREF)
        self.assertIsNone(p.is_oa)
        c = Candidate(paper=p, ranks=[0], found_by=["crossref:q"])
        _score(c, 1, 2026)
        self.assertNotIn("OA", c.badges)

    def test_enrichment_fills_status_from_openalex(self):
        p = _crossref_paper(CROSSREF)
        client = FakeClient({"results": [{
            "id": "https://openalex.org/W2", "doi": "https://doi.org/10.1234/closed.2",
            "open_access": {"is_oa": False, "oa_status": "closed"}, "best_oa_location": None, "locations": []}]})
        self.assertEqual(enrich_from_openalex(client, [p]), 1)
        self.assertEqual((p.is_oa, p.oa_status, p.openalex_id), (False, "closed", "https://openalex.org/W2"))
        self.assertIn("doi:10.1234/closed.2", client.calls[0][1]["filter"])


if __name__ == "__main__":
    unittest.main()
