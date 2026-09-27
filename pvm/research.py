"""Topic research: search scholarly APIs, merge, rank, and write a candidate list for the agent."""
from __future__ import annotations

import html
import math
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from . import __version__
from .config import get_settings
from .schema import Paper
from .util import ROOT, PvmError, ensure_dir, log, now_iso, read_json, slugify, warn, write_json, write_text

RESEARCH_DIR = ROOT / "research"
ALL_SOURCES = ("openalex", "crossref", "europepmc", "arxiv", "s2")
DEFAULT_SOURCES = ("openalex", "crossref")

# Venues a general audience recognises as authoritative ("顶刊"). Lower-case, exact match.
TOP_VENUES = {
    "nature", "science", "cell", "the lancet", "lancet", "new england journal of medicine",
    "the new england journal of medicine", "jama", "bmj", "the bmj", "nature medicine",
    "nature human behaviour", "nature neuroscience", "nature communications", "science advances",
    "proceedings of the national academy of sciences", "psychological science",
    "journal of personality and social psychology", "psychological bulletin", "psychological review",
    "annual review of psychology", "american psychologist", "trends in cognitive sciences",
    "behavioral and brain sciences", "journal of experimental psychology: general", "neuron",
    "current biology", "nature reviews psychology", "nature reviews neuroscience", "jama psychiatry",
    "the lancet psychiatry", "american journal of psychiatry", "world psychiatry",
    "american economic review", "the quarterly journal of economics", "quarterly journal of economics",
    "journal of political economy", "econometrica", "the review of economic studies", "management science",
    "journal of consumer research", "organizational behavior and human decision processes",
    "journal of applied psychology", "academy of management journal", "child development",
    "developmental psychology", "personality and social psychology review", "emotion",
    "journal of abnormal psychology", "clinical psychological science", "social science & medicine",
    "plos medicine", "elife", "plos biology",
}


@dataclass
class Candidate:
    paper: Paper
    found_by: list[str] = field(default_factory=list)
    ranks: list[int] = field(default_factory=list)
    score: float = 0.0
    badges: list[str] = field(default_factory=list)
    id: str = ""


# ---------------------------------------------------------------- HTTP

def _client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=15.0),
        follow_redirects=True,
        headers={"User-Agent": f"pvm/{__version__} (paper-video-maker research tool)"},
    )


def _get(client: httpx.Client, url: str, params: dict | None = None, headers: dict | None = None, tries: int = 3):
    delay = 2.0
    last = None
    for attempt in range(tries):
        try:
            r = client.get(url, params=params, headers=headers)
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                if attempt < tries - 1:
                    time.sleep(delay)
                    delay *= 2.5
                    continue
                return r
            return r
        except httpx.HTTPError as e:
            last = str(e)
            if attempt < tries - 1:
                time.sleep(delay)
                delay *= 2.5
    raise PvmError(f"network error for {url}: {last}")


def _norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi.lower() or None


def _strip_tags(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(re.sub(r"\s+", " ", s)).strip()
    s = re.sub(r"^(abstract|summary)[:.\s]+", "", s, flags=re.I)
    return s or None


# ---------------------------------------------------------------- sources

def _openalex_abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        positions.extend((i, word) for i in idxs)
    return " ".join(w for _, w in sorted(positions)) or None


def _openalex_paper(w: dict) -> Paper:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    biblio = w.get("biblio") or {}
    pages = None
    if biblio.get("first_page"):
        pages = biblio["first_page"] + (f"–{biblio['last_page']}" if biblio.get("last_page") else "")
    pdfs: list[str] = []
    for l in [w.get("best_oa_location") or {}, loc] + list(w.get("locations") or []):
        u = (l or {}).get("pdf_url")
        if u and u not in pdfs:
            pdfs.append(u)
    return Paper(
        title=_strip_tags(w.get("title") or w.get("display_name")) or "(untitled)",
        authors=[(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])],
        year=w.get("publication_year"),
        venue=src.get("display_name"),
        volume=biblio.get("volume"),
        issue=biblio.get("issue"),
        pages=pages,
        doi=_norm_doi(w.get("doi")),
        url=loc.get("landing_page_url"),
        pdf_urls=pdfs,
        abstract=_openalex_abstract(w.get("abstract_inverted_index")),
        cited_by=w.get("cited_by_count"),
        type=w.get("type"),
        is_oa=(w.get("open_access") or {}).get("is_oa"),
        openalex_id=w.get("id"),
        origin="openalex",
    )


def _openalex_params(extra: dict) -> dict:
    s = get_settings()
    params = dict(extra)
    if s.contact_email:
        params["mailto"] = s.contact_email
    if s.openalex_api_key:
        params["api_key"] = s.openalex_api_key
    return params


def search_openalex(client, query: str, limit: int, since: int | None) -> list[Paper]:
    filters = ["type:article|review|preprint"]
    if since:
        filters.append(f"from_publication_date:{since}-01-01")
    r = _get(client, "https://api.openalex.org/works", _openalex_params({
        "search": query, "filter": ",".join(filters), "per_page": min(limit, 50),
    }))
    if r.status_code != 200:
        warn(f"openalex: HTTP {r.status_code} for '{query}'")
        return []
    return [_openalex_paper(w) for w in r.json().get("results", [])]


def search_crossref(client, query: str, limit: int, since: int | None) -> list[Paper]:
    filters = ["type:journal-article"]
    if since:
        filters.append(f"from-pub-date:{since}")
    params = {"query.bibliographic": query, "rows": min(limit, 40), "filter": ",".join(filters),
              "select": "DOI,title,container-title,issued,author,is-referenced-by-count,type,volume,issue,page,abstract,link,URL"}
    if get_settings().contact_email:
        params["mailto"] = get_settings().contact_email
    r = _get(client, "https://api.crossref.org/works", params)
    if r.status_code != 200:
        warn(f"crossref: HTTP {r.status_code} for '{query}'")
        return []
    return [_crossref_paper(it) for it in r.json()["message"].get("items", [])]


def _crossref_paper(it: dict) -> Paper:
    year = None
    parts = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
    if parts and parts[0]:
        year = int(parts[0])
    authors = []
    for a in it.get("author") or []:
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name", "")
        if name:
            authors.append(name)
    pdfs = [l["URL"] for l in it.get("link") or [] if l.get("content-type") == "application/pdf" and l.get("URL")]
    return Paper(
        title=_strip_tags((it.get("title") or ["(untitled)"])[0]) or "(untitled)",
        authors=authors,
        year=year,
        venue=(it.get("container-title") or [None])[0],
        volume=it.get("volume"),
        issue=it.get("issue"),
        pages=(it.get("page") or "").replace("-", "–") or None,
        doi=_norm_doi(it.get("DOI")),
        url=it.get("URL"),
        pdf_urls=pdfs,
        abstract=_strip_tags(it.get("abstract")),
        cited_by=it.get("is-referenced-by-count"),
        type=it.get("type"),
        origin="crossref",
    )


def search_europepmc(client, query: str, limit: int, since: int | None) -> list[Paper]:
    q = query + (f" AND PUB_YEAR:[{since} TO 3000]" if since else "")
    r = _get(client, "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
             {"query": q, "format": "json", "pageSize": min(limit, 50), "resultType": "core"})
    if r.status_code != 200:
        warn(f"europepmc: HTTP {r.status_code} for '{query}'")
        return []
    out = []
    for p in r.json().get("resultList", {}).get("result", []):
        pdfs = []
        if p.get("isOpenAccess") == "Y" and p.get("pmcid"):
            pdfs.append(f"https://europepmc.org/articles/{p['pmcid']}?pdf=render")
        for ft in ((p.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
            if ft.get("documentStyle") == "pdf" and ft.get("availabilityCode") in ("OA", "F") and ft.get("url"):
                pdfs.append(ft["url"])
        authors = [a.get("fullName", "") for a in ((p.get("authorList") or {}).get("author") or []) if a.get("fullName")]
        journal = ((p.get("journalInfo") or {}).get("journal") or {}).get("title")
        out.append(Paper(
            title=_strip_tags(p.get("title")) or "(untitled)",
            authors=authors,
            year=int(p["pubYear"]) if str(p.get("pubYear", "")).isdigit() else None,
            venue=journal,
            volume=(p.get("journalInfo") or {}).get("volume"),
            issue=(p.get("journalInfo") or {}).get("issue"),
            pages=p.get("pageInfo"),
            doi=_norm_doi(p.get("doi")),
            url=f"https://europepmc.org/article/{p.get('source', 'MED')}/{p.get('id')}",
            pdf_urls=pdfs,
            abstract=_strip_tags(p.get("abstractText")),
            cited_by=p.get("citedByCount"),
            type="review" if "review" in str(p.get("pubType", "")).lower() else "article",
            is_oa=p.get("isOpenAccess") == "Y",
            origin="europepmc",
        ))
    return out


def search_arxiv(client, query: str, limit: int, since: int | None) -> list[Paper]:
    r = _get(client, "https://export.arxiv.org/api/query",
             {"search_query": f"all:{query}", "max_results": min(limit, 30), "sortBy": "relevance"})
    if r.status_code != 200:
        warn(f"arxiv: HTTP {r.status_code} for '{query}'")
        return []
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    out = []
    for e in ET.fromstring(r.content).findall("a:entry", ns):
        year = int((e.findtext("a:published", "", ns) or "0")[:4] or 0) or None
        if since and year and year < since:
            continue
        abs_url = e.findtext("a:id", "", ns)
        pdf = next((l.get("href") for l in e.findall("a:link", ns) if l.get("title") == "pdf"), None)
        out.append(Paper(
            title=re.sub(r"\s+", " ", e.findtext("a:title", "", ns)).strip(),
            authors=[a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)],
            year=year,
            venue="arXiv",
            doi=_norm_doi(e.findtext("x:doi", None, ns)),
            url=abs_url,
            pdf_urls=[pdf] if pdf else [],
            abstract=re.sub(r"\s+", " ", e.findtext("a:summary", "", ns)).strip() or None,
            type="preprint",
            is_oa=True,
            origin="arxiv",
        ))
    return out


def search_s2(client, query: str, limit: int, since: int | None) -> list[Paper]:
    key = get_settings().s2_api_key
    params = {"query": query, "limit": min(limit, 50),
              "fields": "title,year,venue,citationCount,externalIds,openAccessPdf,authors,abstract,publicationTypes,journal,url"}
    if since:
        params["year"] = f"{since}-"
    r = _get(client, "https://api.semanticscholar.org/graph/v1/paper/search", params,
             headers={"x-api-key": key} if key else None, tries=2)
    if r.status_code != 200:
        warn(f"semantic scholar: HTTP {r.status_code} (set SEMANTIC_SCHOLAR_API_KEY for reliable access)")
        return []
    out = []
    for p in r.json().get("data", []):
        journal = p.get("journal") or {}
        pdf = (p.get("openAccessPdf") or {}).get("url")
        out.append(Paper(
            title=p.get("title") or "(untitled)",
            authors=[a.get("name", "") for a in p.get("authors") or []],
            year=p.get("year"),
            venue=journal.get("name") or p.get("venue") or None,
            volume=journal.get("volume"),
            pages=journal.get("pages"),
            doi=_norm_doi((p.get("externalIds") or {}).get("DOI")),
            url=p.get("url"),
            pdf_urls=[pdf] if pdf else [],
            abstract=p.get("abstract"),
            cited_by=p.get("citationCount"),
            type="review" if "Review" in (p.get("publicationTypes") or []) else "article",
            origin="s2",
        ))
    return out


SEARCHERS = {
    "openalex": search_openalex,
    "crossref": search_crossref,
    "europepmc": search_europepmc,
    "arxiv": search_arxiv,
    "s2": search_s2,
}


# ---------------------------------------------------------------- lookup by DOI

def lookup_doi(doi: str) -> Paper:
    doi_n = _norm_doi(doi)
    if not doi_n:
        raise PvmError(f"not a DOI: {doi}")
    with _client() as client:
        r = _get(client, f"https://api.openalex.org/works/doi:{doi_n}", _openalex_params({}))
        if r.status_code == 200:
            paper = _openalex_paper(r.json())
            if not paper.abstract or not paper.venue:
                _fill_from_crossref(client, paper)
            return paper
        r = _get(client, f"https://api.crossref.org/works/{doi_n}")
        if r.status_code == 200:
            return _crossref_paper(r.json()["message"])
    raise PvmError(f"DOI {doi_n} not found in OpenAlex or Crossref")


def _fill_from_crossref(client, paper: Paper) -> None:
    try:
        r = _get(client, f"https://api.crossref.org/works/{paper.doi}", tries=1)
    except PvmError:
        return
    if r.status_code != 200:
        return
    cr = _crossref_paper(r.json()["message"])
    for name in ("abstract", "venue", "volume", "issue", "pages"):
        if not getattr(paper, name) and getattr(cr, name):
            setattr(paper, name, getattr(cr, name))


# ---------------------------------------------------------------- merge + rank

def _key(p: Paper) -> str:
    if p.doi:
        return "doi:" + p.doi
    return "t:" + re.sub(r"[^a-z0-9]", "", p.title.lower())[:80]


def _merge(into: Paper, other: Paper) -> None:
    for name in ("abstract", "venue", "volume", "issue", "pages", "url", "year", "type", "openalex_id"):
        if not getattr(into, name) and getattr(other, name):
            setattr(into, name, getattr(other, name))
    if len(other.authors) > len(into.authors):
        into.authors = other.authors
    into.cited_by = max(into.cited_by or 0, other.cited_by or 0) or into.cited_by
    for u in other.pdf_urls:
        if u not in into.pdf_urls:
            into.pdf_urls.append(u)
    if other.is_oa:
        into.is_oa = True


def _score(c: Candidate, n_queries: int, this_year: int) -> None:
    p = c.paper
    rel = max((1.0 - r / 30.0) for r in c.ranks) if c.ranks else 0.0
    rel = max(rel, 0.0) + 0.08 * (len(set(c.found_by)) - 1)
    cites = min(1.0, math.log10((p.cited_by or 0) + 1) / 4.0)
    venue = (p.venue or "").strip().lower()
    top = venue in TOP_VENUES
    venue_s = 1.0 if top else (0.35 if venue else 0.0)
    oa = 1.0 if (p.is_oa or p.pdf_urls) else 0.0
    age = this_year - (p.year or this_year - 30)
    recency = 1.0 if age <= 6 else max(0.3, 1.0 - (age - 6) / 40.0)
    ptype = (p.type or "").lower()
    type_s = 1.0 if ptype in ("article", "review", "journal-article") else (0.5 if ptype == "preprint" else 0.2)
    title_l = p.title.lower()
    review = ptype == "review" or "meta-analy" in title_l or "review" in title_l
    has_abs = 1.0 if p.abstract else 0.0
    c.score = round(0.36 * rel + 0.24 * cites + 0.12 * venue_s + 0.1 * oa + 0.08 * recency
                    + 0.05 * type_s + 0.05 * has_abs, 4)
    if top:
        c.badges.append("top-venue")
    if (p.cited_by or 0) >= 500:
        c.badges.append("highly-cited")
    if age <= 5:
        c.badges.append("recent")
    if review:
        c.badges.append("review/meta")
    if oa:
        c.badges.append("OA")
    if ptype == "preprint":
        c.badges.append("preprint")


def run_research(topic: str, queries: list[str], *, slug: str | None = None, limit: int = 15,
                 per_query: int = 25, since: int | None = None, sources: tuple[str, ...] = DEFAULT_SOURCES,
                 oa_only: bool = False) -> tuple[Path, list[Candidate]]:
    queries = [q.strip() for q in (queries or [topic]) if q.strip()]
    unknown = [s for s in sources if s not in SEARCHERS]
    if unknown:
        raise PvmError(f"unknown sources {unknown}; choose from {', '.join(ALL_SOURCES)}")
    slug = slug or slugify(topic, "topic")
    out_dir = ensure_dir(RESEARCH_DIR / slug)
    merged: dict[str, Candidate] = {}
    with _client() as client:
        for q in queries:
            for src in sources:
                try:
                    papers = SEARCHERS[src](client, q, per_query, since)
                except PvmError as e:
                    warn(f"{src}: {e}")
                    continue
                log(f"  {src:<9} {len(papers):>3} results for: {q}")
                for rank, p in enumerate(papers):
                    k = _key(p)
                    if k in merged:
                        _merge(merged[k].paper, p)
                    else:
                        merged[k] = Candidate(paper=p)
                    merged[k].found_by.append(f"{src}:{q}")
                    merged[k].ranks.append(rank)
    this_year = datetime.now().year
    cands = [c for c in merged.values() if c.paper.title and c.paper.title != "(untitled)"]
    if oa_only:
        cands = [c for c in cands if c.paper.is_oa or c.paper.pdf_urls]
    for c in cands:
        _score(c, len(queries), this_year)
    cands.sort(key=lambda c: c.score, reverse=True)
    cands = cands[:limit]
    for i, c in enumerate(cands, 1):
        c.id = f"c{i:02d}"

    payload = {
        "topic": topic,
        "slug": slug,
        "queries": queries,
        "sources": list(sources),
        "since": since,
        "created": now_iso(),
        "candidates": [
            {"id": c.id, "score": c.score, "badges": c.badges, "found_by": sorted(set(c.found_by)),
             "paper": c.paper.model_dump(exclude_none=True)}
            for c in cands
        ],
    }
    write_json(out_dir / "candidates.json", payload)
    write_text(out_dir / "candidates.md", render_candidates_md(payload))
    return out_dir, cands


def render_candidates_md(payload: dict) -> str:
    lines = [f"# Candidates: {payload['topic']}", "",
             f"Queries: {'; '.join(payload['queries'])}  ", f"Sources: {', '.join(payload['sources'])}  ",
             f"Generated: {payload['created']}", "",
             "| id | year | venue | cites | tags | title |", "|---|---|---|---|---|---|"]
    for c in payload["candidates"]:
        p = c["paper"]
        title = p["title"].replace("|", "/")
        lines.append(f"| {c['id']} | {p.get('year', '')} | {(p.get('venue') or '')[:40]} | {p.get('cited_by', '')} | "
                     f"{' '.join(c['badges'])} | {title} |")
    lines.append("")
    for c in payload["candidates"]:
        p = c["paper"]
        lines.append(f"## {c['id']} · {p['title']}")
        authors = ", ".join(p.get("authors", [])[:6]) + (" et al." if len(p.get("authors", [])) > 6 else "")
        lines.append(f"- {authors} ({p.get('year', 'n.d.')}) *{p.get('venue') or ''}*")
        if p.get("doi"):
            lines.append(f"- DOI: https://doi.org/{p['doi']}")
        lines.append(f"- cited by {p.get('cited_by', 0)}; OA: {bool(p.get('is_oa') or p.get('pdf_urls'))}; score {c['score']}")
        if p.get("abstract"):
            lines.append(f"- Abstract: {p['abstract'][:900]}{'…' if len(p['abstract']) > 900 else ''}")
        lines.append("")
    return "\n".join(lines)


def load_candidates(slug: str) -> dict:
    data = read_json(RESEARCH_DIR / slug / "candidates.json")
    if data is None:
        raise PvmError(f"no research found for '{slug}' (looked in research/{slug}/candidates.json)")
    return data


def pick_candidate(ref: str) -> Paper:
    """Resolve '<research-slug>:<cid>' (e.g. sunk-cost:c03) to a Paper."""
    if ":" not in ref:
        raise PvmError("use --pick <research-slug>:<candidate-id>, e.g. --pick sunk-cost:c03")
    slug, cid = ref.rsplit(":", 1)
    for c in load_candidates(slug)["candidates"]:
        if c["id"] == cid:
            return Paper.model_validate(c["paper"])
    raise PvmError(f"candidate {cid} not found in research/{slug}")


def list_research() -> list[dict]:
    out = []
    if RESEARCH_DIR.exists():
        for d in sorted(RESEARCH_DIR.iterdir()):
            data = read_json(d / "candidates.json")
            if data:
                out.append({"slug": d.name, "topic": data.get("topic"), "n": len(data.get("candidates", [])),
                            "created": data.get("created")})
    return out
